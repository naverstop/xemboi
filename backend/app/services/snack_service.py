"""B-11 무료 스낵 테스트(바이럴 V3) — 사주 기반 유형 테스트. 무과금·비로그인·무저장.

전부 결정적 계산(LLM 아님): 명식의 십성·도화(삼합 왕지)로 유형을 뽑고, 미리 감수한 유형별
문구를 붙인다. 운명 단정 대신 밝고 재미있는 화법(바이럴 목적)이되 겁주지 않는다.
결과는 유형 카드(9:16 PNG)로도 뽑아 공유 유통(V1 규격 재사용).

두 테스트:
  1) dohwa  — "내 도화 매력 등급": 삼합 도화(함지·목욕지) 글자가 명식에 몇 개인지(0~4)로 5등급
     ('시 모름'은 3지지만 계산 → 최고 등급(4)은 시주 포함 명식만 도달. 재미 콘텐츠라 허용)
  2) wealth — "올해가 아닌, 타고난 재물 기질": 십성의 재성/식상/비겁/관성/인성 분포로 6유형
"""
from __future__ import annotations

import io
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw

from backend.app.saju.constants import DOHWA_BY_TRINE
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, SajuChart

_CARD_DIR = Path(__file__).resolve().parents[3] / "data" / "snackcard"
# 결과 타입별 FLUX 일러스트(프론트 정적자산과 공용) — 카드 PNG 에도 같은 그림을 합성해 통일감.
_ICON_DIR = Path(__file__).resolve().parents[3] / "frontend" / "public" / "snack"
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")

TEST_IDS = ("dohwa", "wealth")
TEST_META = {
    "dohwa": {"title": "내 도화 매력 등급", "emoji": "🌸", "badge": "桃花",
              "desc": "생년월일만 넣으면, 타고난 매력의 결을 봐드려요."},
    "wealth": {"title": "타고난 재물 기질", "emoji": "💰", "badge": "財",
               "desc": "돈과 나는 어떤 궁합일까? 사주 속 재물 기질을 유형으로."},
}


# ── 공통: 도화(함지) 글자 집합 — 년지·일지 기준 삼합 그룹에서 도출 ──
# ⚠️ 도화는 삼합국의 '왕지'가 아니라 장생지 다음 글자(목욕지)다: 申子辰→酉, 寅午戌→卯,
#    巳酉丑→午, 亥卯未→子. DOHWA_BY_TRINE 값이 이미 올바른 도화 글자이므로 그대로 쓴다.
def _dohwa_chars(chart: SajuChart) -> set[str]:
    """명식의 년지·일지가 속한 삼합 그룹의 도화(함지·목욕지) 글자들."""
    refs = {chart.pillars.year.branch, chart.pillars.day.branch}
    out: set[str] = set()
    for trine, dohwa in DOHWA_BY_TRINE.items():
        if refs & trine:
            out.add(dohwa)
    return out


# ============================================================
# 테스트 1: 도화 매력 등급
# ============================================================
_DOHWA_TIERS = [
    {"key": "classic", "label": "은은한 클래식 매력", "emoji": "🕊️", "color": "#6b8cae",
     "headline": "서두르지 않아도 진가를 알아보는 사람이 곁에 남아요.",
     "body": "화려함보다 신뢰로 마음을 얻는 타입이에요. 오래 볼수록 좋아지는 사람, 딱 그 매력이에요."},
    {"key": "cozy", "label": "다가가고 싶은 편안한 매력", "emoji": "☕", "color": "#c08a4a",
     "headline": "함께 있으면 마음이 놓이는, 그런 사람이에요.",
     "body": "부담 없이 곁을 내주는 편안함이 무기예요. 낯선 자리에서도 금세 사람을 모으는 힘이 있어요."},
    {"key": "spark", "label": "은근히 눈길을 끄는 매력", "emoji": "✨", "color": "#c0518a",
     "headline": "튀지 않는데 자꾸 눈이 가는, 은근한 끌림이 있어요.",
     "body": "존재감이 조용히 번지는 타입이에요. 첫인상보다 두 번째·세 번째에 더 빛나는 사람이에요."},
    {"key": "magnetic", "label": "치명적인 도화 매력", "emoji": "🌹", "color": "#c0392b",
     "headline": "한번 스치면 오래 기억에 남는, 강한 끌림의 소유자예요.",
     "body": "매력이 많은 만큼 인연도 다채로워요. 좋은 인연을 고르는 눈만 곁들이면 완벽해요."},
    {"key": "star", "label": "타고난 스타 오라", "emoji": "👑", "color": "#b8860b",
     "headline": "가만히 있어도 시선이 모이는, 타고난 스타 기질이에요.",
     "body": "어딜 가나 중심이 되는 오라가 있어요. 그 에너지를 즐기되, 소중한 인연엔 진심을 아끼지 마세요."},
]


def _score_dohwa(chart: SajuChart) -> dict[str, Any]:
    dohwa = _dohwa_chars(chart)
    # 기둥 정체성 기준 라벨링(위치 인덱스 아님) — 시주 외 기둥이 None 이어도 라벨이 안 밀린다
    pos_branches = [(label, getattr(chart.pillars, p).branch)
                    for label, p in (("년", "year"), ("월", "month"), ("일", "day"), ("시", "hour"))
                    if getattr(chart.pillars, p) is not None]
    count = sum(1 for _, b in pos_branches if b in dohwa)   # 0~4 ('시 모름'은 최대 3)
    tier = _DOHWA_TIERS[min(count, 4)]
    reasons = []
    hit = [f"{label}지({b})" for label, b in pos_branches if b in dohwa]
    if hit:
        reasons.append(f"명식 {'·'.join(hit)}에 도화(桃花) 글자 — 매력 지수 {count}")
    else:
        reasons.append("명식에 도화 글자가 없어 담백·클래식 매력형")
    return {"result_key": tier["key"], "label": tier["label"], "emoji": tier["emoji"],
            "color": tier["color"], "headline": tier["headline"], "body": tier["body"],
            "meter": {"value": count, "max": 4, "label": "도화 지수"}, "reasons": reasons}


# ============================================================
# 테스트 2: 재물 기질
# ============================================================
_WEALTH_TYPES = {
    "pyeonjae": {"label": "과감한 승부사형", "emoji": "🎲", "color": "#c0392b",
                 "headline": "큰 판을 읽는 눈, 기회 앞에서 망설이지 않는 재물 기질이에요.",
                 "body": "편재(偏財)의 기운이 도드라져요. 흐름을 크게 보고 베팅하는 스타일 — 분산과 타이밍만 챙기면 큰 자산으로 이어져요."},
    "jeongjae": {"label": "차곡차곡 자산가형", "emoji": "🏦", "color": "#2e7d32",
                 "headline": "꾸준함이 곧 재산이 되는, 안정형 재물 기질이에요.",
                 "body": "정재(正財)의 기운이 탄탄해요. 무리한 승부보다 성실한 축적으로 크는 타입 — 복리와 시간이 가장 든든한 편이에요."},
    "siksang": {"label": "만들어내는 재주꾼형", "emoji": "🎨", "color": "#0496d8",
                "headline": "재능과 아이디어가 곧 돈이 되는, 창조형 재물 기질이에요.",
                "body": "식상(食傷)이 재성을 생하는 흐름이에요. 내가 만든 것·표현한 것으로 버는 타입 — 콘텐츠·기술·창작에 강해요."},
    "bigyeop": {"label": "함께 크는 협업가형", "emoji": "🤝", "color": "#8a5cc0",
                "headline": "사람이 곧 재산인, 관계형 재물 기질이에요.",
                "body": "비겁(比劫)의 기운이 강해요. 혼자보다 팀·동업·네트워크에서 커지는 타입 — 좋은 파트너가 최고의 투자예요."},
    "inseong": {"label": "느긋한 관리형", "emoji": "📚", "color": "#b8860b",
                "headline": "욕심보다 안정, 지키는 데 강한 재물 기질이에요.",
                "body": "인성(印星)의 기운이 도드라져요. 크게 벌기보다 잃지 않게 지키고 불리는 타입 — 공부·자격·전문성이 든든한 밑천이에요."},
    "gwanseong": {"label": "신용이 자산인 반듯한 리더형", "emoji": "🏛️", "color": "#3f5b8a",
                  "headline": "책임감과 신뢰가 곧 재산으로 돌아오는 재물 기질이에요.",
                  "body": "관성(官星)의 기운이 도드라져요. 자리와 평판이 돈을 부르는 타입 — 조직·직책·공적인 무대에서 안정적으로 커져요."},
}
# 십성(정기) → 그룹
_TG_GROUP = {
    "正財": "jae", "偏財": "jae", "食神": "sik", "傷官": "sik",
    "比肩": "bi", "劫財": "bi", "正印": "in", "偏印": "in",
    "正官": "gwan", "偏官": "gwan",
}


def _score_wealth(chart: SajuChart) -> dict[str, Any]:
    tg = chart.ten_gods.model_dump() if hasattr(chart.ten_gods, "model_dump") else dict(chart.ten_gods)
    vals = [v for v in tg.values() if v]
    cnt = {"jeongjae": 0, "pyeonjae": 0, "sik": 0, "bi": 0, "in": 0, "gwan": 0}
    for v in vals:
        if v == "正財":
            cnt["jeongjae"] += 1
        elif v == "偏財":
            cnt["pyeonjae"] += 1
        else:
            g = _TG_GROUP.get(v)
            if g in ("sik", "bi", "in", "gwan"):
                cnt[g] += 1
    jae = cnt["jeongjae"] + cnt["pyeonjae"]
    # 결정 규칙(우선순위 고정):
    #  ① 재성이 있으면 편재>정재 로 승부사/자산가 구분
    #  ② 재성이 약(0)하면 식상강→재주꾼 / 비겁강→협업가 / 관성강→리더형 / 인성→관리형
    #    (어드버서리 검증 반영: 관성 우세 명식이 인성 카피로 새는 문제 → 관성 전용 유형 신설)
    if jae >= 1 and cnt["pyeonjae"] >= cnt["jeongjae"] and cnt["pyeonjae"] >= 1:
        key = "pyeonjae"
    elif jae >= 1 and cnt["jeongjae"] >= 1:
        key = "jeongjae"
    elif cnt["sik"] >= max(cnt["bi"], cnt["gwan"], cnt["in"]) and cnt["sik"] >= 1:
        key = "siksang"
    elif cnt["bi"] >= max(cnt["gwan"], cnt["in"]) and cnt["bi"] >= 1:
        key = "bigyeop"
    elif cnt["gwan"] >= cnt["in"] and cnt["gwan"] >= 1:
        key = "gwanseong"
    else:
        key = "inseong"
    t = _WEALTH_TYPES[key]
    reasons = [f"십성 분포 — 정재 {cnt['jeongjae']}·편재 {cnt['pyeonjae']}·식상 {cnt['sik']}"
               f"·비겁 {cnt['bi']}·관성 {cnt['gwan']}·인성 {cnt['in']}"]
    return {"result_key": key, "label": t["label"], "emoji": t["emoji"], "color": t["color"],
            "headline": t["headline"], "body": t["body"],
            "meter": {"value": jae, "max": max(4, jae), "label": "재성(財) 개수"}, "reasons": reasons}


_SCORERS = {"dohwa": _score_dohwa, "wealth": _score_wealth}


def run_test(test_id: str, birth: BirthInput) -> dict[str, Any]:
    if test_id not in _SCORERS:
        raise ValueError("알 수 없는 테스트예요.")
    chart = build_chart(birth, with_daewoon=False)
    res = _SCORERS[test_id](chart)
    meta = TEST_META[test_id]
    return {
        "test_id": test_id, "title": meta["title"], "emoji": meta["emoji"],
        **res,
        # 결과 타입별 FLUX 일러스트(이모지 대체) — 파일명이 결정적이라 별도 매핑 불필요.
        # 프론트는 이 경로를 <img> 로 쓰고, 없으면 emoji 로 폴백한다.
        "icon": f"/snack/{test_id}_{res['result_key']}.webp",
        "disclaimer": "재미로 보는 사주 콘텐츠예요. 결정은 언제나 나의 몫!",
    }


# ── 결과 공유 카드 (1080×1920 PNG) — share_card 헬퍼 재사용 ──
def render_result_card(test_id: str, result: dict[str, Any]) -> bytes:
    from backend.app.services.share_card_service import _font, _center

    W, H = 1080, 1920
    accent = result.get("color", "#0496d8")
    img = Image.new("RGB", (W, H), "#fdf6ec")
    d = ImageDraw.Draw(img)
    top, bot = (253, 246, 236), (243, 232, 214)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bot)))
    # 상단 테스트명
    y = 220
    y = _center(d, TEST_META[test_id]["title"], y, _font(50), "#8a7a5f") + 80
    # 큰 원형 일러스트(결과 캐릭터, FLUX) — 카드 중앙이 비어 밍밍하다는 운영자 지적으로 도입.
    # 파일이 없거나 열기 실패해도 카드 생성은 계속돼야 하므로 종전 단색 원+한자로 폴백.
    hanja = TEST_META[test_id].get("badge", "")
    icon = _ICON_DIR / f"{test_id}_{result.get('result_key', '')}.webp"
    drawn = False
    r = 250 if icon.exists() else 150
    cx, cy = W // 2, y + r + 10
    if icon.exists():
        try:
            art = Image.open(icon).convert("RGB").resize((2 * r, 2 * r), Image.LANCZOS)
            mask = Image.new("L", (2 * r, 2 * r), 0)
            ImageDraw.Draw(mask).ellipse([0, 0, 2 * r - 1, 2 * r - 1], fill=255)
            img.paste(art, (cx - r, cy - r), mask)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=accent, width=9)
            # 한자 인장(전통 낙관 느낌) — 일러스트 우하단 배지로 브랜드 유지
            if hanja:
                sr = 64
                sx, sy = cx + int(r * 0.70), cy + int(r * 0.70)
                d.ellipse([sx - sr, sy - sr, sx + sr, sy + sr], fill=accent, outline="#ffffff", width=5)
                hb = d.textbbox((0, 0), hanja, font=_font(50, bold=True))
                d.text((sx - (hb[2] - hb[0]) / 2 - hb[0], sy - (hb[3] - hb[1]) / 2 - hb[1]),
                       hanja, font=_font(50, bold=True), fill="#ffffff")
            drawn = True
        except Exception:  # noqa: BLE001 — 이미지 문제로 카드 생성이 실패하면 안 됨
            drawn = False
    if not drawn:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent)
        d.ellipse([cx - r + 14, cy - r + 14, cx + r - 14, cy + r - 14], outline="#ffffff", width=4)
        hb = d.textbbox((0, 0), hanja, font=_font(120, bold=True))
        d.text((cx - (hb[2] - hb[0]) / 2 - hb[0], cy - (hb[3] - hb[1]) / 2 - hb[1]), hanja, font=_font(120, bold=True), fill="#ffffff")
    y = cy + r + 60
    # 유형명
    y = _center(d, result["label"], y, _font(80, bold=True), accent) + 34
    # 헤드라인(자동 줄바꿈)
    f_head = _font(44)
    words = result["headline"].split()
    line, lines = "", []
    for w_ in words:
        cand = (line + " " + w_).strip()
        if d.textbbox((0, 0), cand, font=f_head)[2] > W - 200 and line:
            lines.append(line); line = w_
        else:
            line = cand
    if line:
        lines.append(line)
    for ln in lines[:3]:
        y = _center(d, ln, y, f_head, "#4a4234") + 14

    # 지표 게이지(도화 지수·재성 개수 등) — 카드만 봐도 '내 등급'이 읽히게
    m = result.get("meter") or {}
    if m.get("max"):
        y += 30
        bw, bh = W - 340, 26
        bx = (W - bw) // 2
        d.rounded_rectangle([bx, y, bx + bw, y + bh], radius=bh // 2, fill="#e8ddc8")
        fill_w = int(bw * min(1.0, max(0.0, m.get("value", 0) / max(1, m["max"]))))
        if fill_w > 6:
            d.rounded_rectangle([bx, y, bx + fill_w, y + bh], radius=bh // 2, fill=accent)
        y += bh + 16
        y = _center(d, f"{m.get('label', '')} {m.get('value', 0)}/{m['max']}", y, _font(34), "#8a7a5f") + 30

    # 본문 요약 — 종전엔 헤드라인 아래가 통째로 비어 카드가 허전했다(운영자 지적).
    f_body = _font(38)
    bline, blines = "", []
    for w_ in (result.get("body") or "").split():
        cand = (bline + " " + w_).strip()
        if d.textbbox((0, 0), cand, font=f_body)[2] > W - 220 and bline:
            blines.append(bline); bline = w_
        else:
            bline = cand
    if bline:
        blines.append(bline)
    for ln in blines[:5]:
        y = _center(d, ln, y, f_body, "#6a6152") + 12

    # 하단 브랜드
    d.text((90, H - 250), "인생상담 친구", font=_font(52, bold=True), fill=accent)
    d.text((90, H - 175), "내 사주로 보는 무료 테스트", font=_font(38), fill="#8a7a5f")
    try:
        import qrcode
        qr = qrcode.QRCode(box_size=8, border=2)
        import os
        qr.add_data(f"{os.getenv('PUBLIC_BASE_URL', 'https://saju.songstock.art')}/snack/{test_id}")
        qr.make(fit=True)
        qim = qr.make_image(fill_color="#2b2b2b", back_color="#fdf6ec").convert("RGB").resize((210, 210))
        img.paste(qim, (W - 300, H - 300))
    except Exception:  # noqa: BLE001
        pass
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def store_card(png: bytes, test_id: str) -> dict[str, Any]:
    _CARD_DIR.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    (_CARD_DIR / f"{token}.png").write_bytes(png)
    return {"token": token, "url": f"/api/snack-card/{token}",
            "download_url": f"/api/snack-card/{token}?download=1", "filename": f"{test_id}_{datetime.now():%Y%m%d}.png"}


def card_path(token: str) -> Path:
    if not _TOKEN_RE.match(token or ""):
        raise LookupError("잘못된 토큰")
    p = _CARD_DIR / f"{token}.png"
    if not p.exists():
        raise LookupError("카드를 찾을 수 없어요.")
    return p
