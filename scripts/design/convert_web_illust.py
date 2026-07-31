# -*- coding: utf-8 -*-
"""선별된 웹 일러스트 후보를 랜딩 카드 규격 JPEG로 변환.
사용: python convert_web_illust.py sang=42 gunghap=7 ... hero=21
  → image/web_illust/{key}/seed{n}.png 을 880px 폭 JPEG(q85)로 frontend/public/features/{key}.jpg 저장.
FeatImg 가 /features/{key}.jpg 를 우선 로드하므로 마크업 변경 불필요."""
import os, sys

sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image

SRC = r"D:\saju_agent\image\web_illust"
DST = r"D:\saju_agent\.claude\worktrees\design-premium-polish\frontend\public\features"
os.makedirs(DST, exist_ok=True)

for arg in sys.argv[1:]:
    key, seed = arg.split("=")
    src = os.path.join(SRC, key, f"seed{seed}.png")
    img = Image.open(src).convert("RGB")
    w = 880 if key != "hero" else 1200
    h = round(img.height * w / img.width)
    img = img.resize((w, h), Image.LANCZOS)
    dst = os.path.join(DST, f"{key}.jpg")
    img.save(dst, "JPEG", quality=85, optimize=True, progressive=True)
    print(f"{key}: seed{seed} -> {dst} ({os.path.getsize(dst)//1024}KB)", flush=True)
print("done", flush=True)
