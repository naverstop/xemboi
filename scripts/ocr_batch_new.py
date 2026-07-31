"""학습자료_new 폴더 전체를 OCR (기본: CPU/oneDNN — 야간 학습 배치용).

ocr_pdf.py 의 렌더링/플래튼 로직을 재사용하되, PaddleOCR 모델을 1회만 로드해
폴더 내 모든 PDF를 순회 처리한다(파일당 모델 재로드 오버헤드 제거).

디바이스 선택 (환경변수 SAJU_OCR_GPU, paddle import 이전 최상단 처리):
  - 기본 "cpu" → CPU 전용(oneDNN). 영상생성(GPU0) 등과의 GPU 경합을 원천 차단.
    nightly_learning.py(통합 야간 배치)가 이 기본값으로 호출한다.
  - "0"/"1" 등 PCI 인덱스 지정 시 해당 GPU 사용(수동 고속 OCR용, 선택).

페이지별 JSON 캐시(data/ocr/<stem>/page_xxxx.json)가 있으면 스킵 → 재실행 안전.
clean 재생성이 필요하면 --recreate 로 새 파일들의 캐시를 먼저 비운다.

사용:
  .venv_ocr\Scripts\python.exe scripts\ocr_batch_new.py            # CPU(기본)
  set SAJU_OCR_GPU=0 & .venv_ocr\Scripts\python.exe scripts\ocr_batch_new.py  # GPU0 수동
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

# --- 디바이스 선택: paddle import 보다 먼저 환경변수 확정 ---
# SAJU_OCR_GPU="cpu"(또는 ""/"-1") → CPU 전용(oneDNN). 야간 학습 배치 기본값:
# 영상생성(GPU0)과의 VRAM 경합을 원천 차단. CPU(20코어) 페이지당 ~4s로 야간 수용 가능.
GPU_ID = os.environ.get("SAJU_OCR_GPU", "cpu")   # 기본 CPU(야간 배치). GPU 쓰려면 "0"/"1" 명시
USE_CPU = GPU_ID.strip().lower() in ("cpu", "-1", "")
if USE_CPU:
    os.environ["CUDA_VISIBLE_DEVICES"] = "-1"      # GPU 숨김 → paddle CPU 강제("" 는 일부 런타임서 무효)
else:
    os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"   # CUDA 인덱스 = nvidia-smi(PCI) 순서
    os.environ["CUDA_VISIBLE_DEVICES"] = GPU_ID       # 선택 GPU만 노출 → paddle device 0 으로 매핑

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml" / "data_pipeline"))

import ocr_pdf  # noqa: E402  (등록: _register_gpu_dll_dirs)
import fitz  # noqa: E402

SRC = ROOT / "학습자료_new"
ARCHIVE = ROOT / "학습자료_old"   # 학습 완료(OCR된) 원본 보관소
DST = ROOT / "data" / "ocr"
DPI = 300
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


def _collect_targets() -> list[Path]:
    """학습자료_new 의 OCR 대상(PDF + 스캔 이미지) 정렬 목록."""
    if not SRC.exists():
        return []
    pdfs = sorted(SRC.glob("*.pdf"))
    imgs = sorted(p for p in SRC.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXTS)
    return pdfs + imgs


def archive_pdf(pdf_path: Path) -> Path:
    """학습에 사용 완료된 원본(PDF/이미지)을 학습자료_old로 이동.

    OCR 산출물(data/ocr/<stem>.txt)이 학습 아티팩트로 남으므로 원본은
    더 필요 없다. 동명 파일이 이미 보관소에 있으면 -1, -2 … 접미사로 회피.
    """
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    dst = ARCHIVE / pdf_path.name
    if dst.exists():
        i = 1
        while True:
            cand = ARCHIVE / f"{pdf_path.stem}-{i}{pdf_path.suffix}"
            if not cand.exists():
                dst = cand
                break
            i += 1
    shutil.move(str(pdf_path), str(dst))
    return dst


def process_pdf(ocr, pdf_path: Path) -> tuple[int, int]:
    out_root = DST / pdf_path.stem
    out_root.mkdir(parents=True, exist_ok=True)
    out_txt = DST / f"{pdf_path.stem}.txt"

    doc = fitz.open(str(pdf_path))
    n_pages = len(doc)
    total_lines = 0
    t0 = time.time()
    for idx in range(n_pages):
        page_no = idx + 1
        page_json = out_root / f"page_{page_no:04d}.json"
        if page_json.exists():
            try:
                lines = json.loads(page_json.read_text(encoding="utf-8"))
                total_lines += len(lines)
                continue
            except Exception:
                pass
        img = ocr_pdf.render_page_array(doc[idx], dpi=DPI)
        raw = ocr.ocr(img, cls=True)
        lines = ocr_pdf._flatten_lines(raw)
        page_json.write_text(json.dumps(lines, ensure_ascii=False, indent=2), encoding="utf-8")
        total_lines += len(lines)
        rate = page_no / max(time.time() - t0, 0.001)
        print(f"    p.{page_no}/{n_pages} lines={len(lines):>3} {rate:.2f}p/s", flush=True)

    # 전체 페이지 JSON에서 txt 재조립
    chunks = []
    for idx in range(n_pages):
        pj = out_root / f"page_{idx + 1:04d}.json"
        if not pj.exists():
            continue
        try:
            lines = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            continue
        page_text = "\n".join(ln["text"] for ln in lines)
        chunks.append(f"\n\n===== p.{idx + 1} =====\n{page_text}")
    out_txt.write_text("".join(chunks), encoding="utf-8")
    return n_pages, total_lines


def process_image(ocr, img_path: Path) -> tuple[int, int]:
    """단일 스캔 이미지(jpg/png 등) OCR → data/ocr/<stem>.txt + page 캐시.

    PaddleOCR 은 이미지 경로를 직접 받아 OCR 한다(이미지 네이티브). PDF 와 동일한
    캐시 레이아웃(<stem>/page_0001.json)을 써서 재실행 안전 + 증분 색인과 호환.
    """
    out_root = DST / img_path.stem
    out_root.mkdir(parents=True, exist_ok=True)
    out_txt = DST / f"{img_path.stem}.txt"
    page_json = out_root / "page_0001.json"

    lines = None
    if page_json.exists():
        try:
            lines = json.loads(page_json.read_text(encoding="utf-8"))
        except Exception:
            lines = None
    if lines is None:
        raw = ocr.ocr(str(img_path), cls=True)
        lines = ocr_pdf._flatten_lines(raw)
        page_json.write_text(json.dumps(lines, ensure_ascii=False, indent=2), encoding="utf-8")

    page_text = "\n".join(ln["text"] for ln in lines)
    out_txt.write_text(f"\n\n===== p.1 =====\n{page_text}", encoding="utf-8")
    return 1, len(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recreate", action="store_true",
                    help="새 파일들의 기존 OCR 캐시(JSON/txt)를 비우고 처음부터 재생성")
    ap.add_argument("--no-archive", dest="archive", action="store_false",
                    help="OCR 완료 후 원본을 학습자료_old로 이동하지 않음(기본: 이동함)")
    ap.add_argument("--archive-only", action="store_true",
                    help="OCR 없이 학습자료_new의 PDF/이미지를 학습자료_old로 이동만 함"
                         "(색인 성공 후 호출용 — nightly_learning.py)")
    ap.set_defaults(archive=True)
    args = ap.parse_args()

    targets = _collect_targets()
    if not targets:
        # 이동 전용 모드에서 신규 파일이 없는 건 정상(이미 처리됨) → 0 반환
        print(f"[INFO] 처리할 PDF/이미지 없음: {SRC}", file=sys.stderr)
        return 0 if args.archive_only else 2

    # --- 이동 전용: OCR/모델로드 생략하고 학습자료_old로 이동만 ---
    if args.archive_only:
        moved = 0
        for f in targets:
            dst = archive_pdf(f)
            moved += 1
            print(f"  [moved] {f.name} -> {dst.relative_to(ROOT)}", flush=True)
        print(f"== 이동 완료: {moved}개 → 학습자료_old ==", flush=True)
        return 0

    if args.recreate:
        for f in targets:
            cache_dir = DST / f.stem
            if cache_dir.exists():
                shutil.rmtree(cache_dir, ignore_errors=True)
            txt = DST / f"{f.stem}.txt"
            if txt.exists():
                txt.unlink()
        print(f"  [recreate] {len(targets)}개 파일 캐시 삭제 완료", flush=True)

    n_pdf = sum(1 for f in targets if f.suffix.lower() == ".pdf")
    n_img = len(targets) - n_pdf
    dev_label = "CPU(oneDNN)" if USE_CPU else f"GPU PCI#{GPU_ID}, DEVICE_ORDER=PCI_BUS_ID"
    print(f"== 배치 OCR: PDF {n_pdf} + 이미지 {n_img} ({dev_label}, DPI={DPI}) ==", flush=True)

    from paddleocr import PaddleOCR
    print("  PaddleOCR 모델 로딩...", flush=True)
    t_load = time.time()
    ocr = PaddleOCR(use_angle_cls=True, lang="korean", use_gpu=not USE_CPU, show_log=False)
    print(f"  모델 로드 {time.time() - t_load:.1f}s", flush=True)

    grand = time.time()
    archived = 0
    for i, f in enumerate(targets, 1):
        t0 = time.time()
        is_img = f.suffix.lower() in IMG_EXTS
        print(f"\n[{i}/{len(targets)}] {f.name}{' (이미지)' if is_img else ''}", flush=True)
        pages, lines = process_image(ocr, f) if is_img else process_pdf(ocr, f)
        msg = f"  -> {pages}p, {lines} lines, {time.time() - t0:.1f}s"
        # OCR 성공(텍스트가 실제로 잡힘) 시에만 원본을 학습자료_old로 이동
        if args.archive and lines > 0:
            dst = archive_pdf(f)
            archived += 1
            msg += f"  [archived -> {dst.relative_to(ROOT)}]"
        elif args.archive:
            msg += "  [archive skip: lines=0]"
        print(msg, flush=True)

    note = f", 보관이동 {archived}개" if args.archive else ""
    print(f"\n== 전체 완료: {len(targets)}개{note}, {time.time() - grand:.1f}s ==", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
