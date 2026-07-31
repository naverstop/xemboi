# -*- coding: utf-8 -*-
"""12띠×5단계 3D 캐릭터 스틸(video_stills)을 웹 아바타로 가공.
768×1344 머리어깨 스틸 → 상단 얼굴 정사각 크롭 → 240px JPEG → frontend/public/zodiac/{띠}_{단계}.jpg"""
import os, sys

sys.stdout.reconfigure(encoding="utf-8")
from PIL import Image

SRC = r"D:\saju_agent\backend\app\services\assets\video_stills"
DST = r"D:\saju_agent\.claude\worktrees\design-premium-polish\frontend\public\zodiac"
os.makedirs(DST, exist_ok=True)

ZODIACS = ["쥐", "소", "호랑이", "토끼", "용", "뱀", "말", "양", "원숭이", "닭", "개", "돼지"]
STAGES = ["초년", "유년", "청년", "장년", "노년"]

def subject_bbox(img: Image.Image):
    """스튜디오 배경에서 피사체 bbox 추정.
    배경이 세로 그라데이션이므로 '행별' 좌우 가장자리 색을 그 행의 배경색으로 보고 비교
    (코너 평균 방식은 그라데이션이 강한 이미지에서 배경 전체를 피사체로 오탐)."""
    small = img.resize((96, 168), Image.BILINEAR)
    px = small.load()
    xs, ys = [], []
    for y in range(168):
        edge = [px[0, y], px[1, y], px[94, y], px[95, y]]
        br = sum(c[0] for c in edge) / 4
        bg_ = sum(c[1] for c in edge) / 4
        bb = sum(c[2] for c in edge) / 4
        for x in range(96):
            r, g, b = px[x, y][:3]
            if abs(r - br) + abs(g - bg_) + abs(b - bb) > 45:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    w, h = img.size
    return (min(xs) / 96 * w, min(ys) / 168 * h, max(xs) / 96 * w, max(ys) / 168 * h)


n = 0
for z in ZODIACS:
    for s in STAGES:
        src = os.path.join(SRC, f"{z}_{s}.png")
        if not os.path.exists(src):
            print(f"missing: {z}_{s}", flush=True)
            continue
        img = Image.open(src).convert("RGB")
        w, h = img.size  # 768×1344 기준
        if s == "초년":
            # 전신(앉은 아기) 구도 → 피사체 bbox 기준 얼굴 중심에 정사각 크롭.
            # 귀·볏이 긴 동물은 bbox 상단이 귀 끝이라 얼굴이 더 아래 → 동물별 (얼굴중심비율, 크롭크기비율) 오버라이드.
            FACE = {
                "토끼": (0.41, 0.63), "말": (0.38, 0.58), "닭": (0.37, 0.65),
                "쥐": (0.33, 0.68), "원숭이": (0.34, 0.60),
                "뱀": (0.20, 0.62),  # 머리가 몸 위로 솟은 구도 — 얼굴이 bbox 상단 20% 지점
                "호랑이": (0.27, 0.70), "개": (0.27, 0.70), "돼지": (0.26, 0.70),
            }
            fr, sr = FACE.get(z, (0.30, 0.62))
            bb = subject_bbox(img)
            if bb:
                bx0, by0, bx1, by1 = bb
                bh = by1 - by0
                cx = (bx0 + bx1) / 2
                cy = by0 + bh * fr
                side = max(int(bh * sr), int(w * 0.55))
            else:
                cx, cy, side = w / 2, h * 0.40, int(w * 0.70)
            side = min(side, w, h)
            left = int(min(max(cx - side / 2, 0), w - side))
            top = int(min(max(cy - side / 2, 0), h - side))
        else:
            # 머리어깨 인물 구도 → 상단 정사각 (기존 검증값)
            side = w
            left = 0
            top = int(h * 0.037)
        img = img.crop((left, top, left + side, top + side)).resize((240, 240), Image.LANCZOS)
        img.save(os.path.join(DST, f"{z}_{s}.jpg"), "JPEG", quality=85, optimize=True)
        n += 1
print(f"done {n}장 -> {DST}", flush=True)
