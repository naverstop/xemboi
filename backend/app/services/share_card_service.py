"""B-6 공유 카드(V1·V5) — 오늘의 운세를 인스타 스토리 규격(9:16) 이미지로 합성.

바이럴 목적이라 무과금·비로그인 허용. 전부 결정적 데이터(일진·십성·행운색)로 PIL 합성:
12띠 캐릭터(영상 파이프라인과 동일 에셋) + 날짜 + 일진 간지 + 십성 한 줄 + 브랜드·QR 워터마크.
"결과 1건 = 광고 1장" — 날짜가 박혀 있어 유통기한이 공유 심리를 자극(V5).
"""
from __future__ import annotations

import io
import os
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import qrcode
from PIL import Image, ImageDraw, ImageFont, ImageOps

from backend.app.saju.constants import (
    TEN_GODS_KO, branch_korean, compute_ten_god, stem_korean,
)
from backend.app.saju.engine import build_chart
from backend.app.saju.pillars import compute_pillars
from backend.app.saju.types import BirthInput

_CARD_DIR = Path(__file__).resolve().parents[3] / "data" / "sharecard"
_ZODIAC_DIR = Path(__file__).resolve().parents[3] / "frontend" / "public" / "zodiac"
_ASSETS = Path(__file__).resolve().parent / "assets"
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")

# 배포 도메인 — QR 랜딩(공유받은 사람의 진입 동선). 환경변수로 오버라이드 가능.
_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://saju.songstock.art")

# 년지 → 12띠 동물(캐릭터 에셋 파일명과 동일)
_BRANCH_ANIMAL = {
    "子": "쥐", "丑": "소", "寅": "호랑이", "卯": "토끼", "辰": "용", "巳": "뱀",
    "午": "말", "未": "양", "申": "원숭이", "酉": "닭", "戌": "개", "亥": "돼지",
}
# 일진 천간 오행 → 행운색(B-2와 동일 결정 규칙)
_STEM_ELEM = {"甲": "목", "乙": "목", "丙": "화", "丁": "화", "戊": "토",
              "己": "토", "庚": "금", "辛": "금", "壬": "수", "癸": "수"}
_ELEM_LUCKY = {
    "목": ("초록·청색", "#2e7d32"), "화": ("빨강·주황", "#c62828"), "토": ("노랑·베이지", "#b8860b"),
    "금": ("흰색·금색", "#9e9d24"), "수": ("검정·남색", "#283593"),
}


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in ([r"C:\Windows\Fonts\malgunbd.ttf"] if bold else []) + [
        str(_ASSETS / "NotoSansKR-Regular.ttf"), r"C:\Windows\Fonts\malgun.ttf",
    ]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default(size)  # type: ignore[return-value]


_SHARECARD_BG = _ASSETS / "sharecard_bg.jpg"   # FLUX 베이크 골드 프레임(scripts/design/bake_sharecard_bg.py)


def _card_background(W: int, H: int) -> Image.Image:
    """공유카드 배경 — 베이크된 골드 프레임(있으면) 아니면 웜 아이보리 그라데이션 폴백."""
    if _SHARECARD_BG.exists():
        try:
            bg = Image.open(_SHARECARD_BG).convert("RGB")
            return bg if bg.size == (W, H) else bg.resize((W, H), Image.LANCZOS)
        except Exception:  # noqa: BLE001 — 손상 시 폴백
            pass
    img = Image.new("RGB", (W, H), "#fdf6ec")
    d = ImageDraw.Draw(img)
    top, bot = (253, 246, 236), (244, 227, 200)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bot)))
    d.ellipse([W - 420, -260, W + 260, 420], outline="#e8d5b5", width=3)
    d.ellipse([-300, H - 460, 380, H + 220], outline="#e8d5b5", width=3)
    return img


def _center(d: ImageDraw.ImageDraw, text: str, y: int, font: ImageFont.FreeTypeFont,
            fill: str, W: int = 1080) -> int:
    bb = d.textbbox((0, 0), text, font=font)
    d.text(((W - (bb[2] - bb[0])) / 2 - bb[0], y), text, font=font, fill=fill)
    return y + (bb[3] - bb[1])


def render_today_card(birth: BirthInput) -> tuple[bytes, dict[str, Any]]:
    """오늘의 운세 공유 카드(1080×1920 PNG) — 결정적 데이터만 사용."""
    from backend.app.services.push_service import _ILJIN_LINES

    W, H = 1080, 1920
    chart = build_chart(birth, with_daewoon=False)
    today = date.today()
    tfp = compute_pillars(BirthInput(birth_date=today))[0]
    t_stem, t_branch = tfp.day.stem, tfp.day.branch
    tg = compute_ten_god(chart.pillars.day.stem, t_stem)
    tg_ko = TEN_GODS_KO.get(tg, tg)
    line = _ILJIN_LINES.get(tg, "오늘의 기운을 차분히 살펴보세요.")
    elem = _STEM_ELEM.get(t_stem, "토")
    lucky_name, lucky_hex = _ELEM_LUCKY[elem]
    animal = _BRANCH_ANIMAL.get(chart.pillars.year.branch, "쥐")

    # ── 배경: FLUX 베이크 프리미엄 골드 프레임(그리팅카드 감성) — 중앙은 밝게 비워 글자 가독 보존.
    #    에셋 없으면 기존 웜 아이보리 그라데이션으로 자동 폴백(never-break). ──
    img = _card_background(W, H)
    d = ImageDraw.Draw(img)

    # ── 상단: 날짜 + 타이틀 ──
    y = 150
    y = _center(d, f"{today:%Y.%m.%d} ({'월화수목금토일'[today.weekday()]})", y, _font(44), "#8a7a5f") + 18
    y = _center(d, "오늘의 운세", y, _font(96, bold=True), "#2b2b2b") + 60

    # ── 12띠 캐릭터(원형) — 사용자 나이대에 맞는 단계(운영자 결정 2026-07: 개인화 맥락은 나이 맞춤) ──
    # 단계 기준은 프론트 lib/zodiacAvatar.ts lifeStage·video/scenario.py 와 동일(연 나이, 장식용 근사).
    age = today.year - birth.birth_date.year
    stage = "초년" if age < 8 else "유년" if age < 20 else "청년" if age < 40 else "장년" if age < 60 else "노년"
    zp = _ZODIAC_DIR / f"{animal}_{stage}.jpg"
    if zp.exists():
        av = Image.open(zp).convert("RGB")
        av = ImageOps.fit(av, (420, 420))
        mask = Image.new("L", (420, 420), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, 420, 420], fill=255)
        ring = Image.new("RGB", (444, 444), "#0496d8")
        rmask = Image.new("L", (444, 444), 0)
        ImageDraw.Draw(rmask).ellipse([0, 0, 444, 444], fill=255)
        img.paste(ring, ((W - 444) // 2, y), rmask)
        img.paste(av, ((W - 420) // 2, y + 12), mask)
        y += 444 + 48
    else:
        y += 20

    # ── 일진 간지 + 십성 ──
    iljin = f"{t_stem}{t_branch}"
    iljin_ko = f"{stem_korean(t_stem)}{branch_korean(t_branch)}"
    y = _center(d, f"오늘 일진 · {iljin}({iljin_ko})", y, _font(52), "#6a5a42") + 26
    y = _center(d, tg_ko, y, _font(150, bold=True), "#0496d8") + 44

    # 십성 한 줄(자동 줄바꿈, 최대 2줄)
    f_line = _font(46)
    words = line.split()
    lines, cur = [], ""
    for w_ in words:
        cand = (cur + " " + w_).strip()
        bb = d.textbbox((0, 0), cand, font=f_line)
        if bb[2] - bb[0] > W - 220 and cur:
            lines.append(cur)
            cur = w_
        else:
            cur = cand
    if cur:
        lines.append(cur)
    for ln in lines[:2]:
        y = _center(d, ln, y, f_line, "#4a4234") + 16
    y += 40

    # ── 행운색 칩 ──
    chip_w, chip_h = 520, 96
    cx0 = (W - chip_w) // 2
    d.rounded_rectangle([cx0, y, cx0 + chip_w, y + chip_h], radius=48, fill="#ffffff", outline="#e3d5bc", width=2)
    d.ellipse([cx0 + 28, y + 24, cx0 + 76, y + 72], fill=lucky_hex)
    d.text((cx0 + 100, y + 24), f"행운의 색  {lucky_name}", font=_font(40), fill="#4a4234")

    # ── 하단: 브랜드 + QR ──
    qr = qrcode.QRCode(box_size=9, border=2)
    qr.add_data(f"{_BASE_URL}/today")
    qr.make(fit=True)
    qim = qr.make_image(fill_color="#2b2b2b", back_color="#fdf6ec").convert("RGB")
    qim = qim.resize((240, 240))
    img.paste(qim, (W - 320, H - 330))
    d.text((90, H - 300), "인생상담 친구", font=_font(56, bold=True), fill="#0496d8")
    d.text((90, H - 220), "내 사주로 보는 오늘 — 무료", font=_font(40), fill="#8a7a5f")
    d.text((90, H - 130), _BASE_URL.replace("https://", ""), font=_font(34), fill="#b0a184")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    meta = {"iljin": iljin, "ten_god": tg_ko, "animal": animal, "stage": stage, "date": today.isoformat()}
    return buf.getvalue(), meta


def store_card(png: bytes, title: str) -> dict[str, Any]:
    _CARD_DIR.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    (_CARD_DIR / f"{token}.png").write_bytes(png)
    fname = re.sub(r"[^\w가-힣._-]", "", title) + ".png"
    try:
        (_CARD_DIR / f"{token}.name").write_text(fname, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return {"token": token, "url": f"/api/share-card/{token}",
            "download_url": f"/api/share-card/{token}?download=1", "filename": fname}


def card_path(token: str) -> tuple[Path, str]:
    if not _TOKEN_RE.match(token or ""):
        raise LookupError("잘못된 토큰")
    p = _CARD_DIR / f"{token}.png"
    if not p.exists():
        raise LookupError("공유 카드를 찾을 수 없어요.")
    name = "공유카드.png"
    np = _CARD_DIR / f"{token}.name"
    if np.exists():
        try:
            name = np.read_text(encoding="utf-8").strip() or name
        except Exception:  # noqa: BLE001
            pass
    return p, name
