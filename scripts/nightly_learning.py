# -*- coding: utf-8 -*-
"""통합 야간 학습 배치 (전 과정 CPU 전용).

자정 이후 1일 1회, 관리자가 낮 동안 적재해 둔 학습 대상을 한꺼번에 처리한다.
영상생성(GPU0) 등 다른 워크로드와의 GPU 경합을 피하려고 OCR·임베딩·STT를
모두 CPU 로 수행한다(CUDA_VISIBLE_DEVICES="-1" 강제). 대상이 없는 단계는 건너뛴다.

처리 트랙:
  1) 학습자료_new PDF  → CPU OCR(.venv_ocr) → data/ocr/<stem>.txt
  2) 1)에서 새로 생긴 txt → CPU 증분 색인(bge-m3) → Qdrant
  3) 학습자료_new → 학습자료_old 아카이브 + 승인된 PDF 업로드 indexed 마킹
  4) 승인된 txt 업로드 → CPU 색인 → indexed 마킹
  5) 승인된 mp4 업로드 → CPU STT+색인(process_mp4_uploads)

단일 인스턴스 락으로 중복 실행을 막는다. scheduler 가 00:30 에 .venv 로 호출.

수동 실행:
  python -m scripts.nightly_learning [--ocr-only] [--skip-ocr]
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# CPU 전용 강제 — torch/paddle import 이전에 GPU 숨김.
# "-1" 사용: 빈 문자열("")은 torch 에서 GPU 를 숨기지 못함(실측). "-1" 이라야 차단됨.
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

# stdout/stderr 를 UTF-8 로 고정 — 로그 파일 리다이렉트 시 Windows 기본 cp949 가
# em대시(—) 등 비ASCII 출력을 인코딩 못해 UnicodeEncodeError 로 죽는 것을 방지(실측).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

LEARN_NEW = PROJECT_ROOT / "학습자료_new"
OCR_DIR = PROJECT_ROOT / "data" / "ocr"
UPLOADS_TXT_DIR = PROJECT_ROOT / "data" / "processed" / "uploads"
OCR_PY = PROJECT_ROOT / ".venv_ocr" / "Scripts" / "python.exe"
LOCK_PATH = PROJECT_ROOT / "data" / "logs" / "nightly_learning.lock"
PROGRESS_PATH = PROJECT_ROOT / "data" / "logs" / "learning_progress.json"
_PROGRESS = {"started_at": None}

# 단계 한글 라벨(관리자 화면 표시용)
_STAGE_LABEL = {
    "start": "시작", "ocr": "OCR 인식", "index": "색인(임베딩)", "archive": "아카이브",
    "uploads": "업로드 처리", "mp4": "음성/영상 STT", "snapshot": "스냅샷",
    "done": "완료", "error": "오류",
}

# 전체 진행율 산출용 단계 순서 + 가중치(무거운 OCR/STT 비중↑, 합 100).
# 단계를 건너뛰어도(대상 없음) 다음 단계 시작 시 직전까지 가중치가 채워져 0~100%가 단조 증가.
_STAGE_ORDER = ["ocr", "index", "archive", "uploads", "mp4", "snapshot"]
_STAGE_WEIGHT = {"ocr": 35, "index": 25, "archive": 4, "uploads": 8, "mp4": 25, "snapshot": 3}


def write_progress(stage, message="", current=None, total=None, chunks=None,
                   done=False, error=None, current_file=None):
    """학습 배치 진행상황을 JSON으로 기록(관리자 화면 실시간 표시용).

    current/total = 현재 단계 내 진척(파일 N/M), current_file = 처리 중 파일명,
    overall_pct = 전 단계 가중 전체 진행율(단계가 바뀌어도 0~100% 단조 증가),
    stage_index/stage_count = 단계 순번(예: 2/6).
    """
    import json
    from datetime import datetime as _dt
    if _PROGRESS["started_at"] is None and stage not in ("done", "error"):
        _PROGRESS["started_at"] = _dt.now().isoformat(timespec="seconds")
    overall_pct = None
    stage_index = None
    if stage in _STAGE_ORDER:
        stage_index = _STAGE_ORDER.index(stage) + 1
        before = sum(_STAGE_WEIGHT[s] for s in _STAGE_ORDER[:stage_index - 1])
        frac = (current / total) if (current and total and total > 0) else 0.0
        overall_pct = round(min(100.0, before + _STAGE_WEIGHT[stage] * frac), 1)
    elif stage == "done":
        overall_pct, stage_index = 100.0, len(_STAGE_ORDER)
    data = {
        "stage": stage, "stage_label": _STAGE_LABEL.get(stage, stage), "message": message,
        "current": current, "total": total, "chunks": chunks, "current_file": current_file,
        "stage_index": stage_index, "stage_count": len(_STAGE_ORDER), "overall_pct": overall_pct,
        "started_at": _PROGRESS["started_at"],
        "updated_at": _dt.now().isoformat(timespec="seconds"),
        "done": done, "error": error,
    }
    try:
        PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROGRESS_PATH.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}   # OCR 대상 이미지

# OCR 품질 가드 임계값
#   실측: 깨진 손글씨 meaning_ratio≈0.28 / 한자 많은 명리고전(자평진전) 0.478 /
#         정상 한글 인쇄본 ≥0.80. 0.4 는 손글씨(거부)와 한자고전(통과) 사이 안전선.
QUALITY_MIN_CHARS = 30           # 이하 = 내용 부족(빈/실패 OCR)
QUALITY_MIN_MEANING_RATIO = 0.4  # 이하 = OCR 깨짐(의미있는 2글자+ 한글/한자 단어 비율)


def _is_meaning_char(c: str) -> bool:
    """의미 문자 = 한글(가-힣) 또는 한자(CJK 통합 4E00-9FFF).

    명리학 고전(자평진전·연해자평 등)은 한자 원문 비율이 높아 한글만 세면
    정상 인쇄본도 거부되므로(false reject), 한자도 의미 문자로 인정한다.
    """
    return ("가" <= c <= "힣") or ("一" <= c <= "鿿")


def assess_text_quality(txt: str) -> tuple[bool, str, dict]:
    """OCR 산출 텍스트가 학습에 쓸 만한지 판정. (통과여부, 사유, 지표).

    손글씨·저화질·회전 이미지의 깨진 OCR(의미 없는 단일 글자·기호 나열)이
    코퍼스에 들어가 검색 노이즈가 되는 것을 막는다. PaddleOCR confidence 는
    깨진 손글씨에서도 높게 나와 변별력이 없으므로(실측), '의미있는 한글/한자
    단어 비율'(2글자+ 토큰)을 주 지표로 쓴다.
    """
    body = re.sub(r"=====.*?=====", " ", txt)          # 페이지 구분선 제거
    clean = body.strip()
    total = len(re.sub(r"\s", "", clean))               # 공백 제외 글자수
    meaning_chars = sum(1 for c in clean if _is_meaning_char(c))   # 한글+한자
    toks = clean.split()
    meaning = [t for t in toks if sum(1 for c in t if _is_meaning_char(c)) >= 2]
    mr = len(meaning) / len(toks) if toks else 0.0
    hr = meaning_chars / total if total else 0.0        # 유의미 문자(한글+한자) 비율
    m = {"chars": total, "tokens": len(toks),
         "hangul_ratio": round(hr, 2), "meaning_ratio": round(mr, 2)}
    if total < QUALITY_MIN_CHARS:
        return False, f"내용부족(chars={total})", m
    if mr < QUALITY_MIN_MEANING_RATIO:
        return False, f"OCR품질미달(의미단어비율={mr:.2f})", m
    return True, "ok", m


# ---------------- 단일 인스턴스 락 ----------------

def acquire_lock() -> bool:
    """중복 실행 방지. 살아있는 PID 가 점유 중이면 False."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.exists():
        try:
            pid = int(LOCK_PATH.read_text(encoding="utf-8").strip() or "0")
        except Exception:
            pid = 0
        if pid and _pid_alive(pid):
            print(f"[skip] 이미 실행 중(pid={pid})")
            return False
    LOCK_PATH.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _pid_alive(pid: int) -> bool:
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        return False
    except Exception:
        return False


def release_lock() -> None:
    try:
        LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass


# ---------------- 트랙 1·2: 학습자료_new OCR → 증분 색인 ----------------

def run_ocr_cpu() -> list[str]:
    """학습자료_new PDF/이미지를 CPU OCR. OCR 된(또는 이미 캐시된) 신규 stem 목록 반환."""
    if not LEARN_NEW.exists():
        print("[1] 학습자료_new 없음 — OCR 생략")
        return []
    pdfs = sorted(LEARN_NEW.glob("*.pdf"))
    imgs = sorted(p for p in LEARN_NEW.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXTS)
    targets = pdfs + imgs
    if not targets:
        print("[1] 학습자료_new PDF/이미지 없음 — OCR 생략")
        return []
    stems = [p.stem for p in targets]
    if not OCR_PY.exists():
        print(f"[1][warn] OCR venv 없음: {OCR_PY} — OCR 생략")
        return []
    print(f"[1] 학습자료_new PDF {len(pdfs)} + 이미지 {len(imgs)} CPU OCR 시작")
    write_progress("ocr", f"학습자료_new {len(targets)}개 OCR 인식 중", 0, len(targets))
    env = dict(os.environ)
    env["SAJU_OCR_GPU"] = "cpu"          # CPU 강제(oneDNN)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # OCR 진행상황 모니터(산출 txt 개수로 추정) — 서브프로세스라 직접 카운트
    import threading
    _stop = threading.Event()

    def _ocr_monitor() -> None:
        while not _stop.wait(3):
            done = sum(1 for st in stems if (OCR_DIR / f"{st}.txt").exists())
            write_progress("ocr", "학습자료_new OCR 인식 중", done, len(targets))

    _mt = threading.Thread(target=_ocr_monitor, daemon=True)
    _mt.start()
    # --no-archive: 색인 성공 후(트랙3)에 이동
    r = subprocess.run(
        [str(OCR_PY), str(PROJECT_ROOT / "scripts" / "ocr_batch_new.py"), "--no-archive"],
        cwd=str(PROJECT_ROOT), env=env,
    )
    _stop.set()
    write_progress("ocr", "OCR 인식 완료", len(targets), len(targets))
    if r.returncode not in (0,):
        print(f"[1][warn] OCR rc={r.returncode} — 일부 실패 가능")
    return stems


def index_new_txts(stems: list[str]) -> tuple[int, list[str], list[str]]:
    """OCR 산출 txt 를 품질 검사 후 통과분만 CPU 증분 색인.

    Returns: (색인 chunks 수, 통과 stem 목록, 거부 stem 목록, {stem: 파일별 청크 수}).
    마지막 stem_chunks 는 업로드 레코드의 파일별 청크 수 기록(process_uploads)에 쓰인다.
    거부 사유/지표는 로그로 출력 — 깨진 OCR 이 코퍼스에 들어가지 않게 막는다.
    """
    paths = [OCR_DIR / f"{s}.txt" for s in stems]
    paths = [p for p in paths if p.exists() and p.stat().st_size > 0]
    if not paths:
        print("[2] 색인할 신규 OCR txt 없음 — 생략")
        return 0, [], [], {}

    good, rejected = [], []
    for p in paths:
        ok, reason, m = assess_text_quality(p.read_text(encoding="utf-8"))
        if ok:
            good.append(p)
        else:
            rejected.append(p.stem)
            print(f"    [품질거부] {p.stem}: {reason} {m}")

    print(f"[2] 품질통과 {len(good)} / 거부 {len(rejected)} — 통과분 CPU 증분 색인")
    write_progress("index", f"학습자료 {len(good)}개 색인 시작", 0, len(good))
    if not good:
        return 0, [], rejected, {}
    from ml.data_pipeline.ingest_rag import source_meta  # source=stem, category=pdf
    stem_chunks: dict[str, int] = {}
    added = _embed_and_upsert(good, source_fn=lambda p: source_meta(p),
                              label="학습자료 색인", per_file=stem_chunks, stage="index")
    # [집계 A안 2026-06-18] 학습자료_new 직접 투입분(업로드ID 프리픽스 없음)을
    #   Upload(indexed)로 등록 → 색인완료·총업로드·14일추세 통계에 야간/수동분도 잡히게.
    _register_direct_learning_uploads(stem_chunks)
    return added, [p.stem for p in good], rejected, stem_chunks


def _register_direct_learning_uploads(stem_chunks: dict[str, int]) -> int:
    """학습자료_new 직접 투입분을 Upload(indexed)로 등록(통계 누락 보정, A안).

    업로드 화면 경유분(u00000_ 프리픽스)은 트랙3에서 별도 indexed 처리되므로 제외하고,
    관리자/야간이 학습자료_new 폴더에 직접 넣은 자료만 대상으로 한다. sha 중복(이미 등록)은
    건너뛰어 신규분만 반영. stats()는 Upload 테이블 기반이라 이 등록이 있어야 야간/수동
    학습분이 '색인완료 파일·총 업로드·14일 추세'에 집계된다(코퍼스 청크는 Qdrant 전체라 무관).
    Returns: 신규 등록 건수.
    """
    import re
    import hashlib
    from backend.app.core.db import get_session_factory
    from backend.app.repositories import upload_repo

    old_dir = PROJECT_ROOT / "학습자료_old"
    img_ext = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
    sf = get_session_factory()
    n = 0
    with sf() as db:
        for stem, ch in stem_chunks.items():
            if re.match(r"u\d{5}_", stem):
                continue  # 업로드 승인분 — 트랙3에서 indexed 처리됨
            # 원본 파일: 색인 직후엔 학습자료_new, 아카이브 후엔 학습자료_old 에 존재
            orig = None
            for base in (LEARN_NEW, old_dir):
                if not base.exists():
                    continue
                cand = [c for c in sorted(base.glob(f"{stem}.*")) if c.is_file()]
                if cand:
                    orig = cand[0]
                    break
            if orig is not None:
                sha = hashlib.sha256(orig.read_bytes()).hexdigest()
                ext, size = orig.suffix.lower(), orig.stat().st_size
                stored, name = str(orig.relative_to(PROJECT_ROOT)), orig.name
            else:
                sha = hashlib.sha256(f"direct:{stem}".encode("utf-8")).hexdigest()
                ext, size, stored, name = ".pdf", 0, f"학습자료_old/{stem}.pdf", f"{stem}.pdf"
            if upload_repo.find_by_sha(db, sha):
                continue  # 이미 등록 — 신규분만
            kind = "image" if ext in img_ext else "pdf"
            try:
                row = upload_repo.create_upload(
                    db, title=stem, category="admin_direct", submitter="nightly",
                    file_kind=kind, original_name=name, stored_path=stored,
                    size_bytes=size, sha256=sha, status="indexed",
                )
                upload_repo.mark_indexed(db, row, source=stem, chunks=ch)
                n += 1
            except Exception as _e:  # noqa: BLE001
                print(f"    [직접분 등록 실패] {stem}: {_e}")
    if n:
        print(f"[2b] 학습자료_new 직접분 {n}건 Upload(indexed) 등록 (통계 반영)")
    return n


def _embed_and_upsert(paths: list[Path], *, source_fn, label: str = "색인",
                      per_file: dict | None = None, stage: str = "index",
                      trust: bool = False) -> int:
    """공통 색인기: 여러 txt → bge-m3(CPU) → Qdrant. source_fn(path)->meta dict.

    per_file: 주어지면 {stem: chunks}로 파일별 색인 청크 수를 채운다(직접분 Upload 등록용).
    stage: 진행상황 단계 키(index/uploads 등) — 전체 진행율 계산에 사용.
    """
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qm
    from sentence_transformers import SentenceTransformer

    from backend.app.core.config import get_settings
    from ml.data_pipeline.chunker import chunk_file
    from ml.data_pipeline.ingest_rag import COLLECTION, EMB_DIM, MODEL_NAME, stable_point_id

    s = get_settings()
    model = SentenceTransformer(MODEL_NAME, device="cpu")   # CPU 강제
    client = QdrantClient(url=s.qdrant_url, timeout=60.0)
    if not client.collection_exists(COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=qm.VectorParams(size=EMB_DIM, distance=qm.Distance.COSINE),
        )
        client.create_payload_index(COLLECTION, "source", qm.PayloadSchemaType.KEYWORD)
        client.create_payload_index(COLLECTION, "category", qm.PayloadSchemaType.KEYWORD)
        client.create_payload_index(COLLECTION, "trust_tier", qm.PayloadSchemaType.INTEGER)
        client.create_payload_index(COLLECTION, "low_quality", qm.PayloadSchemaType.BOOL)
        client.create_payload_index(COLLECTION, "is_example", qm.PayloadSchemaType.BOOL)

    # 입력 품질 게이트: 저품질(OCR 깨짐)·예시명식은 메인 코퍼스에서 보류(검역)
    import time as _time
    from ml.data_pipeline.quarantine import partition, record as record_quarantine

    total = 0
    n = len(paths)
    all_quarantined: list = []
    src_stats: dict = {}
    for i, p in enumerate(paths, 1):
        meta = source_fn(p)
        src = meta["source"]
        chunks = chunk_file(p, source=src, target_size=700, max_size=1000, overlap_size=120)
        if not chunks:
            if per_file is not None:
                per_file[p.stem] = 0
            write_progress(stage, f"{label} 중 ({src[:28]})", i, n, total, current_file=src[:40])
            continue
        if trust:
            # 신뢰 소스(Claude 비전 전사 등) — 청크 품질게이트 우회, 고신뢰 태그로 전량 수용.
            accepted_pairs = [(c, {"trust_tier": 1, "low_quality": False, "is_example": False}) for c in chunks]
            quarantined = []
        else:
            accepted_pairs, quarantined = partition(chunks, meta.get("category", "pdf"))
        src_stats[src] = {"total": len(chunks), "quarantined": len(quarantined)}
        all_quarantined.extend(quarantined)
        if not accepted_pairs:  # 파일 전체가 보류(깨진 스캔 등)
            if per_file is not None:
                per_file[p.stem] = 0
            write_progress(stage, f"{label} 중 ({src[:28]})", i, n, total, current_file=src[:40])
            print(f"    [검역] {src}: {len(chunks)}청크 전부 보류(저품질/예시) → 색인 제외")
            continue
        accepted = [c for c, _t in accepted_pairs]
        vecs = model.encode([c.text for c in accepted], batch_size=16,
                            normalize_embeddings=True, show_progress_bar=False,
                            convert_to_numpy=True)
        points = [
            qm.PointStruct(
                id=stable_point_id(c.source, c.chunk_id),
                vector=v.tolist(),
                payload={**meta, "chunk_id": c.chunk_id, "text": c.text,
                         "char_len": c.char_len, **tags},  # 신뢰성 태그 포함
            )
            for (c, tags), v in zip(accepted_pairs, vecs)
        ]
        client.upsert(collection_name=COLLECTION, points=points, wait=True)
        total += len(points)
        if per_file is not None:
            per_file[p.stem] = len(points)
        write_progress(stage, f"{label} 중 ({src[:28]})", i, n, total, current_file=src[:40])
        held = f" (+{len(quarantined)} 보류)" if quarantined else ""
        print(f"    [{meta.get('category','pdf')}] {src}: {len(points)} chunks{held}")
    if all_quarantined:
        reocr = record_quarantine(f"nightly_{int(_time.time())}", all_quarantined, src_stats)
        print(f"  [검역] 총 {len(all_quarantined)}청크 보류 → data/rag/quarantine 기록"
              + (f", 재OCR 권고 {len(reocr)}소스: {reocr[:5]}" if reocr else ""))
    return total


def run_vision_fallback(since_ts: float) -> int:
    """이번 run에서 PaddleOCR이 전량 실패(reocr_sources)한 저화질·손글씨 스캔을 Claude 비전으로
    전사·색인하는 폴백. 별도 프로세스로 실행(fitz+torch DLL 충돌 회피). Claude는 외부 API라
    GPU 경합 없음. 반환: 색인된 chunks 수."""
    import json
    import re as _re
    quar = PROJECT_ROOT / "data" / "rag" / "quarantine"
    sums = sorted(quar.glob("*.summary.json"), key=lambda p: p.stat().st_mtime)
    if not sums or sums[-1].stat().st_mtime < since_ts - 1:
        return 0  # 이번 run의 격리 없음
    try:
        reocr = list(json.loads(sums[-1].read_text(encoding="utf-8")).get("reocr_sources", []) or [])
    except Exception:  # noqa: BLE001
        return 0
    if not reocr:
        return 0
    print(f"[7] 비전 OCR 폴백 — PaddleOCR 실패 {len(reocr)}건 Claude 전사·색인: {reocr}")
    write_progress("uploads", f"저화질 스캔 {len(reocr)}건 Claude 비전 전사 중", chunks=None)
    try:
        r = subprocess.run(
            [sys.executable, "-u", "-X", "utf8", "-m", "scripts.vision_ocr_fallback", *reocr],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=1800,
        )
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        for ln in out.splitlines():
            if "[vision" in ln or "전사 완료" in ln:
                print("   " + ln.strip())
        m = _re.findall(r"색인\s+(\d+)\s+chunks", out)
        return int(m[-1]) if m else 0
    except Exception as e:  # noqa: BLE001
        print(f"[7][warn] 비전 폴백 실패: {e}")
        return 0


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    i = 1
    while True:
        cand = path.with_name(f"{path.stem}-{i}{path.suffix}")
        if not cand.exists():
            return cand
        i += 1


def archive_results(good_stems: list[str], rejected_stems: list[str]) -> None:
    """학습자료_new 원본을 품질 판정에 따라 처리.

    - 통과(색인됨)   → 학습자료_old 로 이동(아카이브)
    - 품질미달        → 원본 파일 삭제 + data/ocr 깨진 캐시 제거
                        (학습 기준 미달 자료는 서버에 남기지 않는다)
    """
    if not LEARN_NEW.exists():
        return
    old = PROJECT_ROOT / "학습자료_old"
    old.mkdir(parents=True, exist_ok=True)
    moved_ok = deleted_bad = 0
    for f in list(LEARN_NEW.iterdir()):
        if not f.is_file():
            continue
        if f.stem in rejected_stems:
            f.unlink(missing_ok=True)                       # 품질미달 원본 삭제
            (OCR_DIR / f"{f.stem}.txt").unlink(missing_ok=True)
            shutil.rmtree(OCR_DIR / f.stem, ignore_errors=True)
            deleted_bad += 1
        elif f.stem in good_stems:
            shutil.move(str(f), str(_unique(old / f.name)))
            moved_ok += 1
    print(f"[3] 아카이브: 학습자료_old {moved_ok}개 / 품질미달 삭제 {deleted_bad}개")


# ---------------- 트랙 3·4·5: 업로드 레코드 처리 ----------------

def process_uploads(rejected_stems: list[str] | None = None,
                    chunk_map: dict[str, int] | None = None) -> dict:
    """승인된 업로드를 종류별로 색인하고 indexed 로 전이.

    rejected_stems: OCR 품질 검사에서 거부된 stem 목록 → 해당 pdf/이미지 업로드는
        indexed 가 아니라 rejected 로 전이(어드민 UI 에서 사유 확인).
    chunk_map: {stem: 파일별 색인 청크 수}. 트랙 1·2 OCR 색인에서 산출된 값으로,
        pdf/이미지 업로드의 chunks_count 를 실제 값으로 기록한다(0 대신).
    """
    from backend.app.core.db import get_session_factory
    from backend.app.repositories import upload_repo
    from backend.app.services.upload_service import APPROVED_DIR, _safe_title

    rejected_stems = set(rejected_stems or [])
    chunk_map = chunk_map or {}
    sf = get_session_factory()
    stats = {"ocr": 0, "txt": 0, "rejected": 0}
    with sf() as db:
        approved = [u for u in upload_repo.list_uploads(db, status="approved", limit=500)]
        txt_rows = [u for u in approved if u.file_kind == "txt"]
        ocr_rows = [u for u in approved if u.file_kind in ("pdf", "image")]

        # 트랙 4: txt 업로드 — APPROVED_DIR 에 추출본이 이미 저장됨
        txt_paths, txt_map = [], {}
        for u in txt_rows:
            stem = f"u{u.id:05d}_{_safe_title(u.title)[:60]}"
            p = APPROVED_DIR / f"{stem}.txt"
            if p.exists() and p.stat().st_size > 0:
                txt_paths.append(p)
                txt_map[str(p)] = (u, f"upload/{u.id}_{_safe_title(u.title)[:60]}")
        if txt_paths:
            print(f"[4] 승인 txt 업로드 {len(txt_paths)}건 CPU 색인")
            txt_chunks: dict[str, int] = {}
            n = _embed_and_upsert(
                txt_paths,
                source_fn=lambda p: {"source": txt_map[str(p)][1], "category": "user_upload"},
                label="업로드 색인", stage="uploads", per_file=txt_chunks,
            )
            for path_str, (u, src) in txt_map.items():
                from pathlib import Path as _P
                upload_repo.mark_indexed(db, u, source=src, chunks=int(txt_chunks.get(_P(path_str).stem, 0)))
            stats["txt"] = len(txt_paths)

        # 트랙 3-b: pdf/이미지 업로드 — 품질 판정에 따라 indexed/rejected 전이
        for u in ocr_rows:
            stem = f"u{u.id:05d}_{_safe_title(u.title)[:60]}"
            if stem in rejected_stems:
                # 학습 기준 미달 → 원본(inbox) 삭제 + rejected 통보(사유 기록)
                try:
                    sp = PROJECT_ROOT / u.stored_path
                    sp.unlink(missing_ok=True)
                except Exception:  # noqa: BLE001
                    pass
                upload_repo.update_review(
                    db, u, status="rejected", reviewer="nightly",
                    comment="OCR 인식 품질이 학습 기준에 미달하여 자동 거부되었습니다(파일 삭제됨). "
                            "손글씨·저화질·회전 이미지는 인식이 어렵습니다. 텍스트로 옮겨 .txt로 올려 주세요.",
                )
                stats["rejected"] += 1
            elif (OCR_DIR / f"{stem}.txt").exists():
                chunks = int(chunk_map.get(stem, 0))
                if chunks > 0:
                    upload_repo.mark_indexed(db, u, source=stem, chunks=chunks)
                    stats["ocr"] += 1
                else:
                    # 전량 격리(수용 청크 0) — indexed 로 마킹하면 조용한 손실이 된다
                    # (실측 2026-07: 손글씨 13건이 indexed·0청크로 유실). failed 로 남겨
                    # 비전 재OCR 대기열(vision_ocr_fallback._auto_targets)이 집도록 한다.
                    upload_repo.update_review(
                        db, u, status="failed", reviewer="nightly",
                        comment="OCR 전량 격리(수용 청크 0) — Claude 비전 재전사 대기열 등록. "
                                "비전 전사 성공 시 자동으로 색인완료로 전환됩니다.",
                    )
                    stats["reocr_wait"] = stats.get("reocr_wait", 0) + 1
    return stats


def process_mp4() -> int:
    """승인된 mp4 업로드 STT+색인 (CPU). 기존 워커 재사용."""
    from backend.app.core.config import get_settings
    s = get_settings()
    cmd = [
        sys.executable, "-u", "-m", "scripts.process_mp4_uploads",
        "--model", s.uploads_stt_model, "--device", "cpu",
        "--limit", str(s.uploads_stt_limit),
    ]
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = "-1"   # "" 은 torch 에서 무효 → "-1" 로 확실히 GPU 차단
    env.setdefault("PYTHONPATH", str(PROJECT_ROOT))
    print("[5] 승인 mp4 업로드 CPU STT+색인")
    r = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env)
    return r.returncode


def _run_eval_after_learning(tag: str) -> None:
    """학습으로 코퍼스가 바뀐 직후 RAG 검색품질 평가 1회 → 추세에 즉시 반영.

    수동 '지금 평가 실행'과 동일 경로(같은 평가셋·top_k=8). 별도 프로세스로 격리(임베더 중복적재 방지).
    CPU 임베딩이지만 점수는 GPU와 동일함을 검증함(차이는 속도뿐) — 야간/수동 추세가 어긋나지 않는다.
    """
    from datetime import datetime as _dt

    from backend.app.core.config import get_settings
    s = get_settings()
    log_path = PROJECT_ROOT / "data" / "logs" / f"rag_eval_{_dt.now():%Y%m%d_%H%M%S}.log"
    cmd = [sys.executable, "-X", "utf8", "-m", "ml.eval.eval_retrieval",
           "--tag", tag, "--qdrant-url", s.qdrant_url, "--collection", s.qdrant_collection]
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")  # 평가 출력의 비ASCII(✅ 등) cp949 크래시 방지
    print(f"[8] 코퍼스 변경 감지 → 검색품질 평가 실행(tag={tag}, log={log_path.name})")
    with log_path.open("w", encoding="utf-8") as f:
        subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=str(PROJECT_ROOT), env=env, timeout=1800)
    print("[8] 평가 완료 → 추세에 반영됨")


def main() -> int:
    ap = argparse.ArgumentParser(description="통합 야간 학습 배치 (CPU 전용)")
    ap.add_argument("--skip-ocr", action="store_true", help="학습자료_new OCR 단계 생략")
    ap.add_argument("--skip-uploads", action="store_true", help="업로드 레코드 처리 생략")
    ap.add_argument("--skip-mp4", action="store_true", help="mp4 STT 단계 생략")
    args = ap.parse_args()

    if not acquire_lock():
        return 0
    _PROGRESS["started_at"] = None
    write_progress("start", "학습 배치 시작 (CPU)")
    t0 = time.time()
    print(f"===== 야간 학습 배치 시작 (CPU 전용) =====")
    total_chunks = 0
    corpus_changed = False  # 색인으로 코퍼스가 바뀌었는지 → 학습 후 평가 실행 여부 결정
    try:
        rejected: list[str] = []
        st: dict[str, int] = {}               # 업로드 처리 결과(ocr/txt/rejected)
        learned_chunks: dict[str, int] = {}   # {stem: 파일별 청크 수} — 업로드 chunks_count 기록용
        if not args.skip_ocr:
            stems = run_ocr_cpu()
            if stems:
                added, good, rejected, learned_chunks = index_new_txts(stems)
                total_chunks += added
                print(f"[2] 신규 색인 {added} chunks")
                write_progress("archive", "학습자료 아카이브 정리 중", chunks=total_chunks)
                archive_results(good, rejected)
        if not args.skip_uploads:
            write_progress("uploads", "승인 업로드 색인·정리 중", chunks=total_chunks)
            st = process_uploads(rejected_stems=rejected, chunk_map=learned_chunks)
            print(f"[3·4] 업로드 색인: pdf/이미지={st['ocr']}, txt={st['txt']}, 품질거부={st['rejected']}")
            # 비전 OCR 폴백 — PaddleOCR이 전량 실패한 저화질·손글씨 스캔을 Claude로 전사·색인.
            vc = run_vision_fallback(t0)
            if vc:
                total_chunks += vc
                print(f"[7] 비전 폴백 색인 {vc} chunks")
        if not args.skip_mp4:
            write_progress("mp4", "음성/영상 STT 처리 중", chunks=total_chunks)
            process_mp4()
        # 색인 후 코퍼스 청크 수를 이번 달 스냅샷으로 기록(관리자 월별 증가량 그래프용)
        write_progress("snapshot", "코퍼스 스냅샷 기록 중", chunks=total_chunks)
        try:
            from backend.app.services import upload_service as _us
            _us.record_corpus_snapshot()
            print("[6] 코퍼스 스냅샷 기록 완료")
        except Exception as _e:  # noqa: BLE001
            print(f"[6][warn] 스냅샷 기록 실패: {_e}")
        elapsed = time.time() - t0
        uploads_done = int(st.get("ocr", 0)) + int(st.get("txt", 0))
        corpus_changed = (total_chunks > 0 or uploads_done > 0)
        rejected_q = int(st.get("rejected", 0))
        if total_chunks == 0 and uploads_done == 0:
            msg = f"신규 학습할 자료가 없습니다 — 이미 모두 학습 완료된 상태예요 (소요 {elapsed:.0f}초)"
        else:
            msg = f"학습 완료 — 신규 {total_chunks}청크 색인 (소요 {elapsed:.0f}초)"
        if rejected_q:
            msg += f" · 저화질·손글씨 스캔 {rejected_q}건은 OCR 인식 불가로 색인 제외(선명히 재스캔 권장)"
        write_progress("done", msg, chunks=total_chunks, done=True)
    except Exception as _e:  # noqa: BLE001
        write_progress("error", f"학습 중 오류: {str(_e)[:160]}", error=str(_e)[:200], done=True)
        raise
    finally:
        release_lock()
    # 코퍼스가 바뀐 경우에만 평가 1회 자동 실행 → 추세에 즉시 반영(수동 실행과 동일 효과).
    # 변경이 없으면 평가를 건너뛰어 +0.0p 더미 점이 쌓이지 않게 한다. 실패해도 학습 결과엔 영향 없음.
    if corpus_changed:
        try:
            from datetime import datetime as _dt
            _run_eval_after_learning(f"learn_{_dt.now():%Y%m%d_%H%M}")
        except Exception as _e:  # noqa: BLE001
            print(f"[8][warn] 학습 후 평가 실패(무시): {_e}")
    print(f"===== 완료, 소요 {time.time() - t0:.1f}s =====")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
