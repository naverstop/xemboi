"""폰트 매핑 깨진 PDF용 GPU OCR 파이프라인 (PaddleOCR 2.7.x, 한국어+한자).

대상: `학습자료/명리전 1 최종.pdf` 처럼 PyMuPDF로 글자가 깨지는 PDF.

처리 흐름:
 1) PyMuPDF로 페이지 → 고해상도 PNG 바이트 (기본 300dpi)
 2) PaddleOCR(lang='korean', use_gpu=True).ocr(img, cls=True)
 3) 라인 결합 → `data/ocr/{이름}.txt`
 4) 페이지별 raw JSON → `data/ocr/{이름}/page_xxxx.json`

사용:
  python ml/data_pipeline/ocr_pdf.py --file "명리전 1 최종.pdf"
  python ml/data_pipeline/ocr_pdf.py --file "명리전 1 최종.pdf" --start 1 --end 5
  python ml/data_pipeline/ocr_pdf.py --file "..." --no-gpu
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# NVIDIA CUDA/cuDNN DLL 의존성 해결:
# paddle 3.0 cu126 wheel은 nvidia-* 패키지 bin(12.6)을 add_dll_directory로
# 미리 등록해야 cudnn_cnn64_9.dll 로딩에 성공. PATH는 건드리지 않는다
# (torch cu124의 자체 DLL과 충돌 회피 — OCR 프로세스에서는 torch import 금지).
def _register_gpu_dll_dirs() -> None:
    try:
        import site
        for sp in site.getsitepackages() + [site.getusersitepackages()]:
            nvidia = Path(sp) / "nvidia"
            if not nvidia.is_dir():
                continue
            for sub in nvidia.iterdir():
                bin_dir = sub / "bin"
                if bin_dir.is_dir():
                    try:
                        os.add_dll_directory(str(bin_dir))
                    except (OSError, AttributeError):
                        pass
    except Exception:
        pass

_register_gpu_dll_dirs()

import fitz  # PyMuPDF
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = ROOT / "학습자료"
DEFAULT_DST = ROOT / "data" / "ocr"


def render_page_array(page: fitz.Page, dpi: int = 300) -> np.ndarray:
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    # BGR (PaddleOCR 기대 형식; OpenCV 관례)
    if pix.n == 3:
        arr = arr[:, :, ::-1].copy()
    return arr


def _flatten_lines(raw_result) -> list[dict]:
    """PaddleOCR 2.7.x .ocr() 결과 → [{text,conf,box}, ...].

    결과 구조: list (배치) -> list (페이지) -> [ [box, (text, conf)], ... ]
    배치=1이므로 raw_result[0] 가 페이지의 라인 리스트.
    """
    if not raw_result:
        return []
    page = raw_result[0]
    if not page:
        return []
    lines: list[dict] = []
    for item in page:
        try:
            box, txt_conf = item
            text, conf = txt_conf
        except Exception:
            continue
        lines.append(
            {
                "text": str(text),
                "conf": float(conf),
                "box": [[float(x), float(y)] for x, y in box],
            }
        )
    return lines


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--dst", type=Path, default=DEFAULT_DST)
    ap.add_argument("--file", type=str, required=True)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--start", type=int, default=1, help="시작 페이지(1-base)")
    ap.add_argument("--end", type=int, default=None, help="끝 페이지(포함)")
    ap.add_argument("--lang", type=str, default="korean")
    ap.add_argument("--no-gpu", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    pdf_path: Path = args.src / args.file
    if not pdf_path.exists():
        print(f"[ERR] file not found: {pdf_path}", file=sys.stderr)
        return 2

    try:
        from paddleocr import PaddleOCR
    except ImportError:
        print('[ERR] paddleocr 미설치. pip install "paddleocr==2.7.3"', file=sys.stderr)
        return 3

    use_gpu = not args.no_gpu
    print(f"== OCR 시작: {pdf_path.name} (lang={args.lang}, GPU={use_gpu}, DPI={args.dpi}) ==")
    print("  PaddleOCR 모델 로딩... (최초 1회 다운로드 발생 가능)", flush=True)

    ocr = PaddleOCR(
        use_angle_cls=True,
        lang=args.lang,
        use_gpu=use_gpu,
        show_log=False,
    )

    doc = fitz.open(str(pdf_path))
    n_pages = len(doc)
    start = max(1, args.start)
    end = min(args.end or n_pages, n_pages)

    out_root = args.dst / pdf_path.stem
    out_root.mkdir(parents=True, exist_ok=True)
    out_txt = args.dst / f"{pdf_path.stem}.txt"

    all_chunks: list[str] = []
    t0 = time.time()

    for idx in range(start - 1, end):
        page_no = idx + 1
        page_json = out_root / f"page_{page_no:04d}.json"

        if page_json.exists() and not args.force:
            try:
                lines = json.loads(page_json.read_text(encoding="utf-8"))
                elapsed = time.time() - t0
                done = page_no - start + 1
                rate = done / max(elapsed, 0.001)
                print(
                    f"  p.{page_no}/{end}  lines={len(lines):>3}  [skip cached]  "
                    f"{rate:.2f} p/s",
                    flush=True,
                )
                continue
            except Exception:
                pass  # 캐시 손상 → 재OCR

        img = render_page_array(doc[idx], dpi=args.dpi)
        raw = ocr.ocr(img, cls=True)
        lines = _flatten_lines(raw)

        page_json.write_text(
            json.dumps(lines, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        elapsed = time.time() - t0
        done = page_no - start + 1
        total = end - start + 1
        rate = done / max(elapsed, 0.001)
        eta = (total - done) / max(rate, 0.001)
        print(
            f"  p.{page_no}/{end}  lines={len(lines):>3}  "
            f"{rate:.2f} p/s  ETA {eta/60:.1f}min",
            flush=True,
        )

    # 최종 txt는 1~end 모든 JSON에서 재조립 (resume 시 이전 페이지 손실 방지)
    for idx in range(0, end):
        page_no = idx + 1
        page_json = out_root / f"page_{page_no:04d}.json"
        if not page_json.exists():
            continue
        try:
            lines = json.loads(page_json.read_text(encoding="utf-8"))
        except Exception:
            continue
        page_text = "\n".join(ln["text"] for ln in lines)
        all_chunks.append(f"\n\n===== p.{page_no} =====\n{page_text}")

    out_txt.write_text("".join(all_chunks), encoding="utf-8")
    print(f"\n== 완료: {out_txt}  ({time.time()-t0:.1f}s) ==")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
