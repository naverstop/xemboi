# -*- coding: utf-8 -*-
"""[별건] 하노이 온라인 부동산 · Hanoi Estate 타이포 워드마크 (실제 서체 조판, FLUX 아님).

첨부 레퍼런스 느낌: HANOI(대문자·넓은 자간) + 브라스 헤어라인 + 하위 라틴 텍스트.
운영자 요청: 하위 'ESTATE'+'온라인 부동산'을 전부 영문으로, 세련되게.
→ HANOI / ─── / ESTATE / ONLINE REAL ESTATE (전 영문), 조용한 럭셔리.
3배 슈퍼샘플링 후 LANCZOS 다운스케일로 글자 안티에일리어싱.
출력: D:\\saju_agent\\image\\hanoi_estate\\wordmark_*.png
"""
import os
from PIL import Image, ImageDraw, ImageFont

OUT = r"D:\saju_agent\image\hanoi_estate"
os.makedirs(OUT, exist_ok=True)
SS = 3  # 슈퍼샘플

FONTS = {
    "bookman": r"C:\Windows\Fonts\BOOKOS.TTF",
    "georgia": r"C:\Windows\Fonts\georgia.ttf",
    "times":   r"C:\Windows\Fonts\times.ttf",
    "cambria": r"C:\Windows\Fonts\cambria.ttc",
}

# 팔레트
CHARCOAL = (26, 29, 35)      # 다크 배경
IVORY    = (244, 240, 232)   # 밝은 글자/배경
BRASS    = (201, 168, 106)   # 샴페인 브라스(헤어라인·태그라인)
GREY     = (168, 164, 156)   # 서브 텍스트(다크 위)
INKGREY  = (92, 90, 86)      # 서브 텍스트(밝은 위)


def font(path, px):
    return ImageFont.truetype(path, px * SS, index=0)


def tracked_width(draw, text, fnt, tracking_px):
    w = 0
    for ch in text:
        bb = draw.textbbox((0, 0), ch, font=fnt)
        w += (bb[2] - bb[0]) + tracking_px * SS
    return w - tracking_px * SS if text else 0


def draw_tracked(draw, text, fnt, tracking_px, cx, cy, fill):
    """자간(tracking) 적용해 (cx,cy) 중심으로 한 줄 그리기. baseline 정렬용 top 기준."""
    total = tracked_width(draw, text, fnt, tracking_px)
    x = cx - total / 2
    # 세로 중앙 정렬: 대문자 높이 기준
    asc, desc = fnt.getmetrics()
    for ch in text:
        bb = draw.textbbox((0, 0), ch, font=fnt)
        chw = bb[2] - bb[0]
        draw.text((x - bb[0], cy - asc / 2), ch, font=fnt, fill=fill)
        x += chw + tracking_px * SS


def make(variant, serif, dark=True):
    W, H = 1200, 760
    bg = CHARCOAL if dark else IVORY
    main = IVORY if dark else CHARCOAL
    sub = GREY if dark else INKGREY
    img = Image.new("RGB", (W * SS, H * SS), bg)
    d = ImageDraw.Draw(img)
    cx = W * SS // 2

    f_hanoi = font(FONTS[serif], 128)
    f_estate = font(FONTS[serif], 30)
    f_tag = font(FONTS[serif], 21)

    # HANOI (넓은 자간)
    draw_tracked(d, "HANOI", f_hanoi, 34, cx, int(H * 0.40) * SS, main)
    hanoi_w = tracked_width(d, "HANOI", f_hanoi, 34)

    # 브라스 헤어라인 (HANOI 폭에 맞춤)
    ry = int(H * 0.545) * SS
    half = hanoi_w / 2
    d.line([(cx - half, ry), (cx + half, ry)], fill=BRASS, width=max(1, SS))

    # ESTATE (브라스, 아주 넓은 자간)
    draw_tracked(d, "ESTATE", f_estate, 22, cx, int(H * 0.625) * SS, BRASS)

    # ONLINE REAL ESTATE (서브 태그라인, 영문)
    draw_tracked(d, "ONLINE REAL ESTATE", f_tag, 10, cx, int(H * 0.72) * SS, sub)

    img = img.resize((W, H), Image.LANCZOS)
    path = os.path.join(OUT, f"wordmark_{variant}.png")
    img.save(path)
    print(f"saved {os.path.basename(path)}")


def make_wide(variant, serif):
    """가로형 헤더 락업(웹 상단용) — 다크."""
    W, H = 1600, 440
    img = Image.new("RGB", (W * SS, H * SS), CHARCOAL)
    d = ImageDraw.Draw(img)
    cx = W * SS // 2
    f_hanoi = font(FONTS[serif], 96)
    f_tag = font(FONTS[serif], 22)
    draw_tracked(d, "HANOI ESTATE", f_hanoi, 26, cx, int(H * 0.42) * SS, IVORY)
    w = tracked_width(d, "HANOI ESTATE", f_hanoi, 26)
    ry = int(H * 0.60) * SS
    d.line([(cx - w / 2, ry), (cx + w / 2, ry)], fill=BRASS, width=max(1, SS))
    draw_tracked(d, "ONLINE REAL ESTATE · HANOI", f_tag, 12, cx, int(H * 0.74) * SS, BRASS)
    img = img.resize((W, H), Image.LANCZOS)
    path = os.path.join(OUT, f"wordmark_{variant}.png")
    img.save(path)
    print(f"saved {os.path.basename(path)}")


make("dark_bookman", "bookman", dark=True)
make("dark_times", "times", dark=True)
make("dark_georgia", "georgia", dark=True)
make("light_bookman", "bookman", dark=False)
make_wide("wide_bookman", "bookman")
print("done")
