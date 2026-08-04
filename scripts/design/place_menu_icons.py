# -*- coding: utf-8 -*-
"""메뉴 아이콘 후보(image/menu_icons/{key}/seed{n}.png) 중 선별본을
96px webp 로 줄여 frontend/public/icons/menu/{key}.webp 에 배치.
SELECT 는 육안 검수로 확정(make_menu_icons.py 베이크 후)."""
import os, sys

sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image

SRC = r"D:\saju_agent\image\menu_icons"
DST = r"D:\saju_agent\frontend\public\icons\menu"
os.makedirs(DST, exist_ok=True)

# key -> 채택 seed (육안 선별 2026-07-04 / 신규 7종 2026-07-08: 통일감·모티프 가독·텍스트 아티팩트 없음 기준)
SELECT = {
    "chat": 7, "gunghap": 42, "taekil": 7, "jakmyeong": 7, "gaemyeong": 42,
    "aho": 7, "tarot": 7, "bolt": 7, "gear": 7, "folder": 7,
    "chart": 7, "wrench": 7, "mail": 7,
    # 2026-07 로드맵 신규 메뉴 7종
    "today": 42, "fcalendar": 42, "sinnyeon": 7, "amulet": 7,
    "dream": 42, "snack": 7, "reviews": 42,
    # 2026-07-11 앱 설치(사이드바 통일 UI)
    "install": 42,
    # 2026-07-11 입점 신청
    "partner": 7,
}
CROP = 0.86  # 중앙 86% — 모서리 문양·하단 잔글씨(FLUX 가장자리 아티팩트) 제거, 메달리온은 안쪽에 안착
# 사이드바는 원형 크롭(border-radius 50%) — 세로형 모티프는 중앙을 더 당겨 원 안에 가득 차게
CROP_OVERRIDE = {"amulet": 0.63, "today": 0.80, "reviews": 0.80, "install": 0.62, "partner": 0.40}

n = 0
for key, seed in SELECT.items():
    src = os.path.join(SRC, key, f"seed{seed}.png")
    if not os.path.exists(src):
        print(f"missing: {key}/seed{seed}", flush=True)
        continue
    img = Image.open(src).convert("RGB")
    w, h = img.size
    side = int(min(w, h) * CROP_OVERRIDE.get(key, CROP))
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    # → 96px — 사이드바 26px 표시의 레티나(2~3x)용
    img = img.resize((96, 96), Image.LANCZOS)
    img.save(os.path.join(DST, f"{key}.webp"), "WEBP", quality=88, method=6)
    n += 1
print(f"done {n}장 -> {DST}", flush=True)
