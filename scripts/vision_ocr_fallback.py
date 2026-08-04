# -*- coding: utf-8 -*-
"""격리(저화질 OCR) 스캔을 Claude 비전으로 전사 → 증분 색인하는 폴백.

흐름(요청 설계): 정상 PaddleOCR 1회 → 전량 격리(품질미달)된 소스를 받아 →
  PDF 페이지 렌더(fitz) → Claude 비전 전사 → data/ocr/<stem>.txt 갱신 →
  품질검사 통과 시 증분 색인(bge-m3·CPU·Qdrant) → 업로드 indexed 갱신.

Claude는 외부 API라 GPU 경합 없음(야간 배치에서 호출 가능).

※ Windows에서 fitz(PyMuPDF) 와 torch(sentence-transformers) 를 한 프로세스에 함께
  로드하면 DLL 충돌로 0xC0000005(access violation) 가 난다. 그래서 전사(fitz)와
  색인(torch)을 '별도 프로세스'로 분리한다(--index-only 로 자기 자신을 서브프로세스 호출).

사용:
  .venv\\Scripts\\python.exe -m scripts.vision_ocr_fallback              # 최신 quarantine reocr_sources 자동
  .venv\\Scripts\\python.exe -m scripts.vision_ocr_fallback <stem> ...   # 특정 소스 지정
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

OLD_DIR = PROJECT_ROOT / "학습자료_old"
NEW_DIR = PROJECT_ROOT / "학습자료_new"
QUAR_DIR = PROJECT_ROOT / "data" / "rag" / "quarantine"
OCR_DIR = PROJECT_ROOT / "data" / "ocr"

# 백로그 자동 재시도 상한 — 이 횟수만큼 비전 재전사에도 색인 실패하면 auto 대상에서 제외(무한 재전사 비용 방지).
#   순수 표·색인 페이지 등 재전사해도 안 되는 자료를 매일 Claude 로 다시 부르지 않게 한다.
#   (명시 인자로 호출하면 상한 무시 — 운영자 강제 재시도용.)
MAX_VISION_ATTEMPTS = 3


def _auto_targets() -> list[str]:
    """비전 재OCR 대상 자동 수집: 최신 quarantine summary의 reocr_sources + DB의 failed 업로드.

    종전엔 '최신 summary 1개'만 읽어 야간이 여러 번 돌면 밀린 대상이 유실됐다(실측:
    조용한 손실 13건). failed 상태 업로드(전량 격리분)를 DB에서 직접 집어 백로그를 없앤다."""
    out: list[str] = []
    sums = sorted(glob.glob(str(QUAR_DIR / "*.summary.json")), key=os.path.getmtime)
    if sums:
        try:
            d = json.loads(Path(sums[-1]).read_text(encoding="utf-8"))
            out += list(d.get("reocr_sources", []) or [])
        except Exception:  # noqa: BLE001
            pass
    try:
        from backend.app.core.db import get_session_factory
        from backend.app.repositories import upload_repo
        from backend.app.services.upload_service import _safe_title
        exhausted = 0
        with get_session_factory()() as db:
            for u in upload_repo.list_uploads(db, status="failed", limit=200):
                if u.file_kind not in ("pdf", "image"):
                    continue
                if (getattr(u, "vision_attempts", 0) or 0) >= MAX_VISION_ATTEMPTS:
                    exhausted += 1        # 상한 도달 — auto 재시도 제외(무한 재전사 방지)
                    continue
                out.append(f"u{u.id:05d}_{_safe_title(u.title)[:60]}")
        if exhausted:
            print(f"[vision] 재시도 상한({MAX_VISION_ATTEMPTS}) 도달 {exhausted}건 auto 제외 "
                  "— 순수 표/색인 페이지 가능성. 수동 강제 재시도는 stem 인자로.")
    except Exception as e:  # noqa: BLE001 — DB 불가 시 summary 분만이라도 진행
        print(f"[vision] failed 업로드 조회 건너뜀: {e}")
    return sorted(set(out))


def _bump_attempts(stems: list[str]) -> None:
    """이번에 시도하는 u접두 업로드의 vision_attempts +1 — 상한 도달분이 다음 auto 대상에서 빠지게 한다."""
    import re as _re
    uids = [int(m.group(1)) for s in stems if (m := _re.match(r"^u(\d{5})_", s))]
    if not uids:
        return
    try:
        from sqlalchemy import update as _upd

        from backend.app.core.db import get_session_factory
        from backend.app.repositories.upload_models import Upload
        with get_session_factory()() as db:
            db.execute(_upd(Upload).where(Upload.id.in_(uids))
                       .values(vision_attempts=Upload.vision_attempts + 1))
            db.commit()
    except Exception as e:  # noqa: BLE001 — 카운트 실패가 전사를 막지 않는다
        print(f"[vision] 시도횟수 기록 건너뜀: {e}")


def _find_pdf(stem: str) -> Path | None:
    for base in (OLD_DIR, NEW_DIR):
        p = base / f"{stem}.pdf"
        if p.exists():
            return p
        for f in base.glob(f"{stem}*"):
            if f.suffix.lower() == ".pdf":
                return f
    return None


# ---------------- 1단계: 전사(fitz + Claude, torch 미로드) ----------------
_PAGE_MARK_RE = None  # 지연 컴파일(re)


_VISION_HEADER = "<!-- vision-transcribed v1 -->"  # PaddleOCR txt와 구분(같은 p.N 마커를 쓰므로)


def _parse_pages(text: str) -> dict[int, str]:
    """기존 '비전 전사' txt → {페이지번호: 본문}. 이어전사(resume)용 — 성공분 재과금 방지.

    헤더 마커 없는 파일(PaddleOCR 산출물)은 재사용하지 않는다 — 깨진 페이지 보존 방지."""
    if not text.lstrip().startswith(_VISION_HEADER):
        return {}
    import re
    global _PAGE_MARK_RE
    if _PAGE_MARK_RE is None:
        _PAGE_MARK_RE = re.compile(r"^===== p\.(\d+) =====$", re.M)
    out: dict[int, str] = {}
    marks = list(_PAGE_MARK_RE.finditer(text))
    for j, m in enumerate(marks):
        end = marks[j + 1].start() if j + 1 < len(marks) else len(text)
        body = text[m.end(): end].strip()
        if body:
            out[int(m.group(1))] = body
    return out


def _transcribe_pdf(pdf: Path, done: dict[int, str], dpi: int = 144,
                    max_consec_fail: int = 8) -> tuple[str, bool]:
    """(전사텍스트, 완주여부). done의 페이지는 재사용(이어전사 — 크레딧 소진 재실행 대비).

    연속 max_consec_fail 실패 시 조기 중단(크레딧 소진이면 나머지 전부 실패라 헛호출 방지)
    — 부분 결과는 저장되고 다음 재실행에서 이어서 전사한다."""
    import fitz  # PyMuPDF (CPU 렌더)
    from backend.app.services import external_llm

    doc = fitz.open(str(pdf))
    parts: list[str] = []
    consec_fail = 0
    completed = True
    try:
        for i in range(len(doc)):
            pno = i + 1
            if pno in done:
                parts.append(f"===== p.{pno} =====\n{done[pno]}")
                continue
            png = doc[i].get_pixmap(dpi=dpi).tobytes("png")
            t = external_llm.vision_ocr_image(png)
            if t and t.strip():
                parts.append(f"===== p.{pno} =====\n{t.strip()}")
                consec_fail = 0
            else:
                print(f"    [vision] p.{pno} 전사 실패/빈약")
                consec_fail += 1
                if consec_fail >= max_consec_fail:
                    print(f"[vision] 연속 {consec_fail}페이지 실패 — 조기 중단(잔여 p.{pno + 1}~{len(doc)}). "
                          f"크레딧/API 복구 후 재실행하면 이어서 전사합니다.")
                    completed = False
                    break
    finally:
        doc.close()
    return "\n\n".join(parts), completed


def transcribe_phase(stems: list[str]) -> list[str]:
    """각 소스를 전사해 data/ocr/<stem>.txt 로 저장(기존 성공 페이지는 재사용). 저장 성공 stem 목록 반환."""
    OCR_DIR.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for stem in stems:
        pdf = _find_pdf(stem)
        if pdf is None:
            print(f"[vision] PDF 없음 — 건너뜀: {stem}")
            continue
        out = OCR_DIR / f"{stem}.txt"
        done: dict[int, str] = {}
        if out.exists():
            done = _parse_pages(out.read_text(encoding="utf-8", errors="replace"))
            if done:
                print(f"[vision] {stem}: 기존 전사 {len(done)}페이지 재사용(이어전사)")
        print(f"[vision] {stem} ← {pdf.name} : Claude 비전 전사 시작…")
        text, completed = _transcribe_pdf(pdf, done)
        if not text or len(text) < 30:
            print(f"[vision] 전사 결과 빈약 — 건너뜀: {stem}")
            continue
        out.write_text(f"{_VISION_HEADER}\n{text}", encoding="utf-8")
        state = "완료" if completed else "부분(이어전사 필요)"
        print(f"[vision] {stem} 전사 {state}: {len(text)}자")
        written.append(stem)
    return written


# ---------------- 2단계: 색인(torch, fitz 미로드) — 서브프로세스로 실행 ----------------
def index_phase(stems: list[str]) -> int:
    # Claude 전사는 신뢰(깨끗) → PaddleOCR용 강한 품질게이트(단일글자 干支 많은 명리글 오탐)를 우회.
    from scripts.nightly_learning import OCR_DIR as NL_OCR, _embed_and_upsert, _register_direct_learning_uploads
    from ml.data_pipeline.ingest_rag import source_meta

    paths = [NL_OCR / f"{s}.txt" for s in stems]
    paths = [p for p in paths if p.exists() and p.stat().st_size > 30]
    if not paths:
        print("[vision-index] 색인할 전사 txt 없음")
        return 0
    per: dict[str, int] = {}
    added = _embed_and_upsert(paths, source_fn=lambda p: source_meta(p),
                              label="비전OCR 색인", per_file=per, stage="index", trust=True)
    try:
        _register_direct_learning_uploads(per)
    except Exception as e:  # noqa: BLE001
        print(f"[vision-index] 업로드 stat 갱신 건너뜀: {e}")
    _mark_upload_rows_indexed(per)   # u접두 업로드: failed→indexed 전환(손실 복구 루프 완결)
    print(f"[vision-index] 색인 {added} chunks (Claude 전사 신뢰 — 품질게이트 우회)")
    return added


def _mark_upload_rows_indexed(per_file: dict[str, int]) -> None:
    """u#####_ 접두 stem의 Upload 행을 실제 청크 수와 함께 indexed 로 전환.

    전량 격리로 failed 였던 업로드가 비전 전사로 복구되면 여기서 상태·청크수가 맞춰진다
    (종전엔 아무도 갱신 안 해 DB가 0청크·failed 로 남았다)."""
    import re as _re
    targets = {int(m.group(1)): (stem, n) for stem, n in per_file.items()
               if n > 0 and (m := _re.match(r"^u(\d{5})_", stem))}
    if not targets:
        return
    try:
        from backend.app.core.db import get_session_factory
        from backend.app.repositories import upload_repo
        from backend.app.repositories.upload_models import Upload
        with get_session_factory()() as db:
            for uid, (stem, n) in targets.items():
                row = db.get(Upload, uid)
                if row is not None:
                    upload_repo.mark_indexed(db, row, source=stem, chunks=n)
        print(f"[vision-index] 업로드 {len(targets)}건 indexed 전환(비전 복구)")
    except Exception as e:  # noqa: BLE001
        print(f"[vision-index] 업로드 indexed 전환 건너뜀: {e}")


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--index-only":
        return 0 if index_phase(args[1:]) >= 0 else 1

    stems = args or _auto_targets()
    if not stems:
        print("[vision] 대상 소스 없음(격리 reocr_sources·failed 백로그 비어있음).")
        return 0
    _bump_attempts(stems)               # 시도 +1 (상한 도달분은 다음 auto 대상에서 제외)
    print(f"[vision] 대상 {len(stems)}건: {stems}")
    written = transcribe_phase(stems)   # fitz + Claude
    if not written:
        print("[vision] 전사된 소스 없음 — 색인 생략")
        return 0
    # torch 색인은 DLL 충돌 회피를 위해 '별도 프로세스'로 실행
    print(f"[vision] 색인 단계(별도 프로세스) 시작 — {len(written)}건")
    r = subprocess.run([sys.executable, "-u", "-X", "utf8", "-m",
                        "scripts.vision_ocr_fallback", "--index-only", *written],
                       cwd=str(PROJECT_ROOT))
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())
