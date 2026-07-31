"""학습자료 PDF → 일반 텍스트 추출 (Phase 2 데이터 파이프라인 0단계).

- 정상 텍스트 PDF: PyMuPDF로 빠르게 추출 → `data/processed/{이름}.txt`
- 폰트 매핑 깨진 PDF(예: 명리전 1 최종): `--ocr` 옵션으로 별도 OCR 스크립트 안내

사용:
  python ml/data_pipeline/extract_pdfs.py
  python ml/data_pipeline/extract_pdfs.py --src "학습자료" --dst "data/processed"
  python ml/data_pipeline/extract_pdfs.py --file "명리전 1 최종.pdf" --force
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SRC = ROOT / "학습자료"
DEFAULT_DST = ROOT / "data" / "processed"

# OCR 판정 기준: 페이지당 평균 "유효 글자(한글/한자)" 가 이 값 미만이면 OCR 대상
OCR_MIN_VALID_CHARS_PER_PAGE = 30
# 또는 전체 텍스트에서 유효 글자 비율이 이 값 미만이면 OCR 대상
OCR_MIN_VALID_RATIO = 0.10
# 글자 깨짐(/HFT, /CID 등) 직접 감지
GLYPH_NOISE_RE = re.compile(r"/(HFT|CID|FID|GID)\d+")
# 한글(가-힣, 자모) + CJK 한자 (확장 일부 포함)
VALID_CHAR_RE = re.compile(
    r"[\uac00-\ud7a3"        # 한글 음절
    r"\u1100-\u11ff"          # 한글 자모
    r"\u3130-\u318f"          # 한글 호환 자모
    r"\u4e00-\u9fff"          # CJK 통합 한자
    r"\u3400-\u4dbf"          # CJK 확장 A
    r"]"
)


def clean_text(t: str) -> str:
    t = re.sub(r"\r\n?", "\n", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def count_valid_chars(s: str) -> int:
    return len(VALID_CHAR_RE.findall(s))


def extract_pdf(path: Path, dst_dir: Path, force: bool = False) -> dict:
    out_txt = dst_dir / f"{path.stem}.txt"
    if out_txt.exists() and not force:
        return {"file": path.name, "status": "skip(exists)", "out": out_txt}

    doc = fitz.open(str(path))
    pages_text: list[str] = []
    total_chars = 0
    valid_chars = 0
    noise_hits = 0

    for page in doc:
        t = page.get_text() or ""
        if GLYPH_NOISE_RE.search(t):
            noise_hits += 1
        pages_text.append(t)
        total_chars += len(t.strip())
        valid_chars += count_valid_chars(t)

    n = len(doc)
    avg_valid = valid_chars / max(n, 1)
    valid_ratio = valid_chars / max(total_chars, 1)
    needs_ocr = (
        avg_valid < OCR_MIN_VALID_CHARS_PER_PAGE
        or valid_ratio < OCR_MIN_VALID_RATIO
        or noise_hits > n * 0.3
    )

    if needs_ocr:
        return {
            "file": path.name,
            "status": "needs_ocr",
            "pages": n,
            "avg_valid": int(avg_valid),
            "valid_ratio": round(valid_ratio, 3),
            "noise_pages": noise_hits,
            "out": None,
        }

    full = clean_text("\n\n".join(pages_text))
    dst_dir.mkdir(parents=True, exist_ok=True)
    out_txt.write_text(full, encoding="utf-8")

    return {
        "file": path.name,
        "status": "ok",
        "pages": n,
        "chars": len(full),
        "valid_chars": valid_chars,
        "out": out_txt,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--dst", type=Path, default=DEFAULT_DST)
    ap.add_argument("--file", type=str, default=None, help="단일 파일명만 처리")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    src: Path = args.src
    dst: Path = args.dst
    if not src.exists():
        print(f"[ERR] src not found: {src}", file=sys.stderr)
        return 2

    files = [src / args.file] if args.file else sorted(src.glob("*.pdf"))
    if not files:
        print("[ERR] no PDF found", file=sys.stderr)
        return 2

    print(f"{'파일':<40} {'상태':<14} {'페이지':>6} {'유효글자':>10}  비고")
    print("-" * 110)

    ocr_targets: list[str] = []
    for f in files:
        if not f.exists():
            print(f"{f.name:<40} {'NOT FOUND':<14}")
            continue
        r = extract_pdf(f, dst, force=args.force)
        pages = r.get("pages", "")
        valid = r.get("valid_chars") or (r.get("avg_valid", 0) * (r.get("pages") or 1)) or ""
        note = ""
        if r["status"] == "needs_ocr":
            note = (
                f"avg_valid={r['avg_valid']}/page, "
                f"ratio={r['valid_ratio']}, glyph-noise={r['noise_pages']}p"
            )
            ocr_targets.append(f.name)
        elif r["status"] == "ok":
            note = str(r["out"].relative_to(ROOT))
        print(f"{f.name:<40} {r['status']:<14} {pages:>6} {str(valid):>10}  {note}")

    if ocr_targets:
        print("\n[!] OCR 필요 파일:")
        for t in ocr_targets:
            print(f"   - {t}")
        print("\n다음 명령으로 OCR 처리:")
        for t in ocr_targets:
            print(f'   python ml\\data_pipeline\\ocr_pdf.py --file "{t}"')

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
