"""학습자료 PDF 텍스트 추출 가능 여부 빠른 점검."""
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1] / "학습자료"

print(f"{'파일명':<40} {'페이지':>6} {'샘플텍스트길이':>14} {'추정형식'}")
print("-" * 90)

for pdf_path in sorted(ROOT.glob("*.pdf")):
    try:
        reader = PdfReader(str(pdf_path))
        n_pages = len(reader.pages)
        # 앞쪽 3페이지 텍스트 추출 시도
        sample = ""
        for i in range(min(3, n_pages)):
            try:
                sample += reader.pages[i].extract_text() or ""
            except Exception:
                pass
        sample_len = len(sample.strip())
        if sample_len > 200:
            kind = "텍스트 PDF (추출 OK)"
        elif sample_len > 20:
            kind = "혼합/일부 텍스트"
        else:
            kind = "스캔 이미지 추정 (OCR 필요)"
        print(f"{pdf_path.name:<40} {n_pages:>6} {sample_len:>14} {kind}")
    except Exception as e:
        print(f"{pdf_path.name:<40} ERROR: {e}")

print()
print("=== 첫 텍스트 PDF 샘플(앞 500자) ===")
for pdf_path in sorted(ROOT.glob("*.pdf")):
    try:
        reader = PdfReader(str(pdf_path))
        for i in range(min(3, len(reader.pages))):
            t = (reader.pages[i].extract_text() or "").strip()
            if len(t) > 200:
                print(f"\n[{pdf_path.name} p.{i+1}]")
                print(t[:500])
                break
        else:
            continue
        break
    except Exception:
        continue
