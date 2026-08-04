"""B-4 AI 부적(符籍) 생성기 — 결정적 발행 룰 + FLUX 배경 + PIL 개인화 각인.

발행 결정은 LLM이 아니라 전부 결정적 규칙이다(로드맵 §6 P1-#4 확정 설계):
  ① 조후용신(궁통보감 120칸) → 보강 오행·오방색 결정
  ② 올해 세운 지지 vs 명식 4지지의 충·형·해·원진 + 삼재 → 액막이 판단
  ③ 사용자 목적 6종 × 위 상태 → 부적 유형 매핑표(AMULET_TYPES)

⚠️ 감수 대기: AMULET_TYPES 매핑표·부적명·삼재 산법은 전문가 감수 후 정적 고정하는 초안이다
   (조후용신 120칸·타로 78장 감수와 동일 절차). 룰 구조는 유지하고 데이터만 교체 가능하게 분리.

과금: 생성 시점 즉시 차감(amulet_cost_p, 기본 3,000P) + 렌더 실패 시 동일 트랜잭션 환불
      (영상 생성과 동일 정책 — [[video-billing-model]]). PNG 합성은 동기(<1s)라 잡 큐 불필요.
면책: 전통 문화 콘텐츠·오락 목적 고지 필수(효험 단정 금지) — 응답·각인 문구 포함.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy.orm import Session

from backend.app.repositories.auth_models import User
from backend.app.saju.constants import (
    BRANCH_CONFLICTS,
    BRANCH_HARM,
    BRANCH_PUNISH,
    BRANCH_WONJIN,
    STEM_TO_WUXING,
)
from backend.app.saju.engine import build_chart
from backend.app.saju.pillars import compute_pillars
from backend.app.saju.sinsal import samjae_phase
from backend.app.saju.types import BirthInput, SajuChart
from backend.app.services import auth_service, settings_service

# 저장 경로: data/amulet/{token}.png (+ .name) — PDF 토큰 패턴 미러
_AMULET_DIR = Path(__file__).resolve().parents[3] / "data" / "amulet"
_ASSETS = Path(__file__).resolve().parent / "assets"

# ── 목적 6종 × 부적 유형 매핑표 (⚠️ 감수 대기 초안 — 전문가 확인 후 고정) ──
AMULET_TYPES: dict[str, dict[str, str]] = {
    "wealth":  {"label": "재물",     "name": "재수대통부", "hanja": "財數大通符"},
    "love":    {"label": "애정",     "name": "인연화합부", "hanja": "因緣和合符"},
    "exam":    {"label": "합격·시험", "name": "학업성취부", "hanja": "學業成就符"},
    "health":  {"label": "건강",     "name": "무병장수부", "hanja": "無病長壽符"},
    "protect": {"label": "액막이",   "name": "액운소멸부", "hanja": "厄運消滅符"},
    "biz":     {"label": "개업·사업", "name": "사업번창부", "hanja": "事業繁昌符"},
}
# 액막이 목적 + 삼재년이면 삼재소멸부로 승격(감수 대기)
_SAMJAE_OVERRIDE = {"name": "삼재소멸부", "hanja": "三災消滅符"}

# 오방색(五方色) — 보강 오행의 전통 색·한자·표시용 hex
_OBANG = {
    "木": ("청(靑)", "#2b5f8e"),
    "火": ("적(赤)", "#a52a22"),
    "土": ("황(黃)", "#b8860b"),
    "金": ("백(白)", "#8a8a83"),
    "水": ("흑(黑)", "#2f2f38"),
}

_POS_KO = {"year": "년", "month": "월", "day": "일", "hour": "시"}


def decide_amulet(chart: SajuChart, purpose: str, today: Optional[date] = None) -> dict[str, Any]:
    """결정적 발행 판단 — 부적 유형 + 발행 근거 목록. LLM 미사용."""
    if purpose not in AMULET_TYPES:
        raise ValueError("알 수 없는 목적이에요.")
    today = today or date.today()
    t_pillars, *_ = compute_pillars(BirthInput(birth_date=today))
    year_branch = t_pillars.year.branch      # 올해 세운 연지(입춘 경계 반영)
    year_label = f"{t_pillars.year.stem}{t_pillars.year.branch}"

    spec = dict(AMULET_TYPES[purpose])
    reasons: list[str] = []

    # ① 조후용신 → 보강 오행·오방색
    element, obang_name, obang_hex = "", "", "#a52a22"
    if chart.johu_yongsin:
        primary = chart.johu_yongsin.primary
        element = STEM_TO_WUXING.get(primary, "")
        if element in _OBANG:
            obang_name, obang_hex = _OBANG[element]
        reasons.append(f"조후용신 {primary}({element}) — {obang_name} 기운을 보강하는 방향으로 발행")

    # ② 삼재(년지 삼합 통설 산법)
    samjae = samjae_phase(chart.pillars.year.branch, year_branch)
    if samjae:
        reasons.append(f"올해 {year_label}년은 {samjae}에 해당")
        if purpose == "protect":
            spec.update(_SAMJAE_OVERRIDE)

    # ③ 올해 세운 지지 vs 명식 4지지 — 충·형·해·원진(결정적 페어 테이블)
    for pos in ("year", "month", "day", "hour"):
        p = getattr(chart.pillars, pos)
        if p is None:
            continue
        pair = frozenset({year_branch, p.branch})
        if len(pair) < 2:
            # 자형(전수감사 Phase 3): 같은 글자 형(辰午酉亥) — 택일 등 타 경로는 전부 분기 보유인데
            # 여기만 누락돼 午午 사주×丙午년에 형 0건(실측). 동일 기준으로 정합.
            from backend.app.saju.constants import BRANCH_SELF_PUNISH
            if year_branch == p.branch and year_branch in BRANCH_SELF_PUNISH:
                reasons.append(f"올해 연지 {year_branch}와 {_POS_KO[pos]}지 {p.branch} 자형(自刑)")
            continue
        if pair in BRANCH_CONFLICTS:
            reasons.append(f"올해 연지 {year_branch}와 {_POS_KO[pos]}지 {p.branch} 충(沖)")
        if pair in BRANCH_WONJIN:
            reasons.append(f"올해 연지 {year_branch}와 {_POS_KO[pos]}지 {p.branch} 원진(怨嗔)")
        if pair in BRANCH_PUNISH:
            reasons.append(f"올해 연지 {year_branch}와 {_POS_KO[pos]}지 {p.branch} 형(刑)")
        if pair in BRANCH_HARM:
            reasons.append(f"올해 연지 {year_branch}와 {_POS_KO[pos]}지 {p.branch} 해(害)")

    # ④ 목적별 보조 근거 — 도화(년살)·공망
    if purpose == "love":
        dohwa_pos = [k for k, v in (chart.twelve_sinsal or {}).items() if "도화" in v or "년살" in v]
        if dohwa_pos:
            reasons.append(f"명식 {'·'.join(dohwa_pos)}에 도화(년살) — 인연 기운 활성")
    if purpose == "protect" and chart.gongmang:
        reasons.append(f"공망 {'·'.join(chart.gongmang)} — 비어 있는 자리를 다스리는 방향")

    # '충돌 없음' 폴백은 충돌 계열 근거가 실제로 0건일 때만 — 종전엔 개수(len<=1)만 봐서
    # 충(沖) 근거와 '특별한 충돌 없음'이 동시 출력되는 모순 문구가 가능했다(전수감사).
    _clash_words = ("충(沖)", "형(刑)", "자형(自刑)", "해(害)", "원진(怨嗔)")
    if len(reasons) <= 1 and not any(w in s for s in reasons for w in _clash_words):
        reasons.append("올해 세운과 명식 사이 특별한 충돌 없음 — 일상 기원용으로 발행")

    return {
        "purpose": purpose,
        "purpose_label": spec["label"],
        "name": spec["name"],
        "hanja": spec["hanja"],
        "element": element,
        "obang": obang_name,
        "color": obang_hex,
        "year": year_label,
        "samjae": samjae,
        "reasons": reasons,
        "review_status": "매핑표 감수 대기",   # 전문가 감수 완료 시 'reviewed' 로 교체
        "disclaimer": "본 부적은 전통 문화 콘텐츠(오락 목적)로, 특정 효험을 보장하지 않습니다.",
    }


# ── PNG 렌더링 (PIL, 동기) ──────────────────────────────────────

_W, _H = 744, 1600   # 실물 부적 비율(~1:2.15)로 세로 연장(운영자 요구 '길쭉하게') — 배경은 미세 스케일로 적응


def _font(size: int, serif: bool = True) -> ImageFont.FreeTypeFont:
    """한자 가능 폰트 — 바탕(궁서 느낌 세리프) 우선, 없으면 번들 NotoSansKR."""
    candidates = (
        [(r"C:\Windows\Fonts\batang.ttc", 0)] if serif else []
    ) + [(str(_ASSETS / "NotoSansKR-Regular.ttf"), None), (r"C:\Windows\Fonts\malgun.ttf", None)]
    for path, idx in candidates:
        try:
            if idx is not None:
                return ImageFont.truetype(path, size, index=idx)
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default(size)  # type: ignore[return-value]


def _fallback_bg() -> Image.Image:
    """베이크 배경이 없을 때의 결정적 폴백 — 황지 + 주사 테두리(기능 우선, 배경은 차후 교체)."""
    img = Image.new("RGB", (_W, _H), "#e7c874")
    d = ImageDraw.Draw(img)
    for i, w in ((28, 6), (44, 2)):
        d.rectangle([i, i, _W - i, _H - i], outline="#9e2a1e", width=w)
    return img


def _bg_for(purpose: str) -> Image.Image:
    p = _ASSETS / f"amulet_{purpose}.jpg"
    if p.exists():
        return Image.open(p).convert("RGB").resize((_W, _H))
    return _fallback_bg()


def _draw_vertical(d: ImageDraw.ImageDraw, text: str, cx: int, top: int,
                   font: ImageFont.FreeTypeFont, fill: str, gap: int = 6) -> int:
    """세로쓰기(위→아래) — 전통 부적 서식. 마지막 y 반환."""
    y = top
    for ch in text:
        bb = d.textbbox((0, 0), ch, font=font)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        d.text((cx - w / 2 - bb[0], y - bb[1]), ch, font=font, fill=fill)
        y += h + gap
    return y


# ── 부적체(符籍體) — 손으로 흘려 그린 경면주사 부적 글씨 스타일 ──────────
# 운영자 요구: 활자처럼 또렷하면 신뢰가 떨어진다 → 글자는 존재하되 세로로 길게 흘리고
# 획을 물결지게 왜곡·글자끼리 세로 획으로 연결해 '오묘하고 신비한' 손글씨로.
# 시드는 부적명에서 결정(같은 부적 유형 = 항상 같은 모양, 결정적 원칙 유지).

def _talisman_glyph(ch: str, px: int) -> Image.Image:
    """한 글자를 L 마스크로 렌더 후 내용 크롭."""
    f = _font(px)
    tmp = Image.new("L", (px * 2, px * 2), 0)
    td = ImageDraw.Draw(tmp)
    bb = td.textbbox((0, 0), ch, font=f)
    td.text((-bb[0] + (tmp.width - (bb[2] - bb[0])) // 2,
             -bb[1] + (tmp.height - (bb[3] - bb[1])) // 2), ch, font=f, fill=255)
    box = tmp.getbbox()
    return tmp.crop(box) if box else tmp


def _mystify(mask: Image.Image, seed: int, stretch: float, flip: bool = False) -> Image.Image:
    """글자 마스크 → 부적체: (반전·기울임) + 세로 늘림 + 가로/세로 물결 + 갈필 + 획 융합.

    '알아먹지 못하는 글자체' 요구 반영 — 좌우반전(전통 부적의 뒤집힌 글자)·기울임·2축 물결로
    글자 구조를 깨고, MaxFilter 융합으로 획을 뭉쳐 한자 '질감'만 남긴다."""
    import numpy as np
    from PIL import ImageFilter
    rng = np.random.default_rng(seed)
    if flip:
        mask = mask.transpose(Image.FLIP_LEFT_RIGHT)   # 뒤집힌 글자 — 판독 차단의 핵심
    mask = mask.rotate(float(rng.uniform(-8, 8)), expand=True, fillcolor=0)
    w, h = mask.size
    m = mask.resize((int(w * 2.05), int(h * stretch)), Image.LANCZOS)
    arr = np.asarray(m, dtype=np.float32)
    rows, cols = arr.shape
    yy = np.arange(rows)
    # ① 행별 가로 물결 — 획이 손으로 흘린 듯 좌우로 유영
    shift = (np.sin(yy / rows * np.pi * 2 * rng.uniform(0.7, 1.3) + rng.uniform(0, 6.28)) * rng.uniform(7, 12)
             + np.sin(yy / rows * np.pi * 2 * rng.uniform(2.6, 3.8) + rng.uniform(0, 6.28)) * rng.uniform(3, 6))
    out = np.zeros_like(arr)
    for i in range(rows):
        out[i] = np.roll(arr[i], int(round(shift[i])))
    # ② 열별 세로 물결 — 가로획을 비스듬히 흘려 활자 구조를 한 번 더 깬다
    xx = np.arange(cols)
    vshift = np.sin(xx / cols * np.pi * 2 * rng.uniform(0.8, 1.6) + rng.uniform(0, 6.28)) * rng.uniform(5, 9)
    for j in range(cols):
        out[:, j] = np.roll(out[:, j], int(round(vshift[j])))
    # ③ 갈필 질감 — 획 안쪽에만 노이즈를 섞어 가장자리를 거칠게
    noise = rng.normal(0, 24, out.shape)
    out = np.clip(out + (out > 12) * noise, 0, 255)
    img2 = Image.fromarray(out.astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(1.1))
    img2 = img2.point(lambda v: 255 if v > 98 else (0 if v < 50 else int((v - 50) * 255 / 48)))
    # ④ 획 융합 — 두껍게 뭉쳐 개별 획 판독을 어렵게(경면주사의 묵직한 덩어리 획)
    return img2.filter(ImageFilter.MaxFilter(5))


def _draw_talisman_title(img: Image.Image, text: str, cx: int, top: int, bottom: int,
                         fill: tuple[int, int, int]) -> None:
    """부적체 v4 — '구조적 토템'(운영자 실물 레퍼런스 반영, 2026-07-09).

    v3(랜덤 회전·물결·반전)는 낙서처럼 보였음 → 실물 부적의 문법으로 재설계:
    정돈된 좌우대칭 획 · 王형 머리단 · 사다리(目)형 연결단 · 부적명 한자(세로 늘림, 왜곡 없음)
    · 중앙 영맥(靈脈) 세로획이 전체를 관통 · 하단 갈래꼬리(지그재그 tassel).
    시드는 부적명 기반(같은 유형=항상 같은 모양, 결정적 원칙 유지) — 획 두께 등 미세 변주만.
    """
    import numpy as np
    from PIL import ImageFilter

    rng = np.random.default_rng(sum(ord(c) for c in text))
    zone = bottom - top
    # 전체 토템을 별도 L 마스크에 그린 뒤 한 번에 잉크 질감 처리(획 일체감)
    layer = Image.new("L", (_W, zone + 160), 0)
    ld = ImageDraw.Draw(layer)
    lcx = _W // 2
    sw = 12                                   # 기본 획 두께(균일 — 구조감의 핵심)
    uw = 82                                   # 유닛 반폭 — 좌우 간지 컬럼(±~200px)과 겹치지 않게 좁게

    def hbar(y: int, half: int, w: int = sw):
        ld.line([(lcx - half, y), (lcx + half, y)], fill=255, width=w)

    def vline(x: int, y0: int, y1: int, w: int = sw):
        ld.line([(x, y0), (x, y1)], fill=255, width=w)

    # ── 예산 기반 배치 — 머리·꼬리·연결단을 먼저 확보하고 남는 높이로 글자 크기 결정(잘림 방지) ──
    n = max(1, len(text))
    HEAD, TAIL = 168, 230
    ladders = min(n - 1, 2)                   # 연결단은 최대 2개(과밀 방지)
    LADDER_H = 72
    stretch = 1.32
    avail = zone - HEAD - TAIL - ladders * LADDER_H
    px = max(84, min(190, int(avail / (n * stretch))))

    y = 40
    # ① 서두 삼태점(∨∨∨)
    for k in (-56, 0, 56):
        ld.line([(lcx + k - 15, y), (lcx + k, y + 17), (lcx + k + 15, y - 4)], fill=255, width=9)
    y += 52
    # ② 王형 머리단 — 가로 대들보 3단 + 끝단 계단식 연결(좌우대칭, 좁은 폭)
    widths = [int(uw * r) for r in (1.35, 1.0, 1.2)]
    for i, half in enumerate(widths):
        hbar(y, half, sw + (2 if i == 0 else 0))
        if i < len(widths) - 1:
            vline(lcx + half, y, y + 30)
            vline(lcx - half, y, y + 30)
        y += 30
    y += 26

    # ③ 부적명 한자 — 세로 늘림만(회전·반전·물결 없음: 실물의 '정돈된' 인상), 일부 사이에 사다리(目)단
    used_ladders = 0
    for i, ch in enumerate(text):
        g = _talisman_glyph(ch, px)
        g = g.resize((int(g.width * 1.04), int(g.height * stretch)), Image.LANCZOS)  # 세로로 길게
        g = g.filter(ImageFilter.MaxFilter(3))        # 획을 묵직하게(경면주사 덩어리감)
        layer.paste(g, (lcx - g.width // 2, y), g)
        # 글자 허리 가로 관통획 — 글자와 영맥을 한 몸으로(부적 특유의 '획이 꿰뚫는' 인상)
        hbar(y + g.height // 2, int(uw * 0.95), sw - 4)
        y += g.height
        if used_ladders < ladders and i % 2 == 1 and i < n - 1:   # ④ 사다리(目)형 연결단(간헐)
            half = int(uw * rng.uniform(0.62, 0.78))
            ld.rectangle([lcx - half, y + 6, lcx + half, y + LADDER_H - 6], outline=255, width=sw - 3)
            hbar(y + LADDER_H // 2, half - sw // 2, sw - 4)
            y += LADDER_H
            used_ladders += 1
    y += 12

    # ⑤ 갈래꼬리(tassel) — 중앙 직선 + 좌우 대칭 지그재그 갈래(아래로 갈수록 짧게)
    tail_len = max(110, min(TAIL - 30, zone + 20 - y))   # 발행 문구 스크림 침범 방지
    for k, (dx, ln) in enumerate(((40, int(tail_len * 0.72)), (72, int(tail_len * 0.5)))):
        for s in (-1, 1):
            ld.line([(lcx + s * 12, y + 8), (lcx + s * dx, y + 46 + k * 8),
                     (lcx + s * (dx - 15), y + 46 + k * 8 + ln // 2),
                     (lcx + s * (dx + 5), y + 46 + k * 8 + ln)], fill=255, width=sw - 4)
    # 중앙 영맥 — 삼태점 아래부터 꼬리 끝까지 전체 관통(획들을 하나로 꿰맨다)
    vline(lcx, 96, y + tail_len, sw - 2)

    # 잉크 질감 — 경계 살짝 번짐 + 미세 갈필(랜덤 왜곡 없이 질감만)
    noise = rng.normal(0, 14, (layer.height, layer.width))
    arr = np.asarray(layer, dtype=np.float32)
    arr = np.clip(arr + (arr > 20) * noise, 0, 255)
    inked = Image.fromarray(arr.astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(0.8))
    inked = inked.point(lambda v: 255 if v > 110 else (0 if v < 60 else int((v - 60) * 255 / 50)))

    patch = Image.new("RGB", inked.size, fill)
    img.paste(patch, (0, top - 40), inked)


def _inner_bottom(img: Image.Image) -> int:
    """배경 안쪽 패널의 바닥 y 자동 측정 — 하단 테두리 장식(붉은 픽셀 밀집) 바로 위.
    배경마다 테두리 두께가 달라 하드코딩하면 문구가 장식과 겹친다(운영자 지적)."""
    import numpy as np
    arr = np.asarray(img.convert("RGB"), dtype=np.int16)
    strip = arr[_H // 2:_H - 60, 290:478]          # 중앙 좁은 스트립만 — 측면 모티프(모란 등) 오탐 방지
    red = (strip[:, :, 0] > 150) & (strip[:, :, 1] < 130)
    frac = red.mean(axis=1)
    clear = frac < 0.03
    run = 0
    # 아래→위로 '깨끗한 종이' 연속 40행 탐색 — 테두리 띠 안의 얇은 노란 틈(수~십행)에 속지 않게
    for i in range(len(clear) - 1, -1, -1):
        run = run + 1 if clear[i] else 0
        if run >= 40:
            return _H // 2 + i + run - 1
    return _H - 200


def render_amulet_png(chart: SajuChart, decision: dict[str, Any]) -> bytes:
    """부적 PNG 합성 — 배경 문양 + 부적명(부적체 세로 대자) + 4주 간지 + 관인 + 최하단 발행 소자."""
    import io

    img = _bg_for(decision["purpose"])
    d = ImageDraw.Draw(img)
    cinnabar = (142, 31, 20)
    safe_bottom = _inner_bottom(img)               # 안쪽 패널 바닥(테두리 장식 위)

    # 중앙: 부적명 — 부적체(세로 늘림·물결 왜곡·갈필·연결 획). 액막이=상단 호랑이 회피.
    title = decision["hanja"]
    zone_top = 430 if decision["purpose"] == "protect" else 300
    zone_bottom = safe_bottom - 230
    _draw_talisman_title(img, title, _W // 2, zone_top, zone_bottom, cinnabar)

    # 좌우: 4주 간지 세로 소자 — 오른쪽(년·월), 왼쪽(일·시). 전통 우→좌 배열. 테두리 안쪽(x=178).
    f_ganji = _font(42)
    cols = []
    pl = chart.pillars
    right = "".join(f"{p.stem}{p.branch}" for p in (pl.year, pl.month) if p)
    left = "".join(f"{p.stem}{p.branch}" for p in (pl.day, pl.hour) if p)
    if right:
        cols.append((right, _W - 178))
    if left:
        cols.append((left, 178))
    for text, cx in cols:
        _draw_vertical(d, text, cx, 350, f_ganji, "#5a4026", gap=8)

    # 관인(相談紙印) — 우하단 낙관(발행 문구 위)
    seal_p = _ASSETS / "seal.png"
    if seal_p.exists():
        seal = Image.open(seal_p).convert("RGBA").resize((96, 96))
        img.paste(seal, (_W - 236, safe_bottom - 214), seal)

    # 최하단: 발행 소자 한 줄 + 면책(패널 없이 텍스트만, 안쪽 패널 바닥에 붙여 — 운영자 요구)
    meta = f"{decision['name']} · {decision['year']}년 발행 · {datetime.now():%Y.%m.%d}"
    f_meta = _font(24, serif=False)
    bb = d.textbbox((0, 0), meta, font=f_meta)
    mx = (_W - (bb[2] - bb[0])) / 2
    # 텍스트 가독 스크림 — 박스가 아니라 배경 종이색의 반투명 받침(모란 등 측면 모티프와
    # 겹쳐도 읽히게). 종이색은 여러 지점 중 '가장 밝은' 픽셀(=획·문양이 아닌 종이)을 채택.
    samples = [img.getpixel((x, y))
               for x in (150, _W // 2, _W - 150)
               for y in (260, _H // 2 - 200, safe_bottom - 140)]
    paper = max(samples, key=lambda c: c[0] + c[1] + c[2])
    scrim = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(scrim)
    sd.rounded_rectangle([mx - 40, safe_bottom - 104, _W - mx + 14, safe_bottom - 28],
                         radius=14, fill=(*paper, 205))
    img.paste(scrim, (0, 0), scrim)
    # 보강 오행 점(오방색) — 발행 문구 왼쪽에 작게
    d.ellipse([mx - 26, safe_bottom - 96 + 5, mx - 10, safe_bottom - 96 + 21], fill=decision["color"])
    d.text((mx, safe_bottom - 96), meta, font=f_meta, fill="#5a4026")
    f_small = _font(18, serif=False)
    disc = "전통 문화 콘텐츠 · 오락 목적"
    bb = d.textbbox((0, 0), disc, font=f_small)
    d.text(((_W - (bb[2] - bb[0])) / 2, safe_bottom - 58), disc, font=f_small, fill="#8a774f")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ── 발행(과금 포함) + 저장/조회 ──────────────────────────────────

_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


def issue_amulet(db: Session, user: User, birth: BirthInput, purpose: str) -> dict[str, Any]:
    """차감 → 결정 → 렌더 → 저장. 렌더/저장 실패 시 같은 트랜잭션에서 환불."""
    # 폴백 기본값은 settings_service.DEFAULTS(3900)와 반드시 일치해야 한다.
    # [2026-07-22 감사] 여기만 3000 이라, DB 행 유실·조회 실패 시 3,900P 상품을 3,000P 에 팔아
    # 건당 900P 를 회사가 손실하는 경로였다(표시는 me.amulet_cost_p 로 3000, 실제도 3000이라
    # 사용자는 눈치채지 못함). api/auth.py 의 me 응답 폴백도 같은 이유로 3900 으로 맞춘다.
    cost = settings_service.get_int(db, "amulet_cost_p", 3900)
    # B-7 플러스 패스: 월 1회 부적 무료(원자적 선점)
    pass_free = False
    if cost > 0:
        try:
            from backend.app.services import pass_service
            _pass = pass_service.get_pass(db, user.id)
            if _pass is not None and _pass.tier == "plus" and \
                    settings_service.get_int(db, "pass_amulet_monthly", 1) > 0 and \
                    pass_service.claim_free_amulet(db, _pass.id):
                pass_free = True
                cost = 0
        except Exception:  # noqa: BLE001 — 패스 조회 실패가 발행을 막지 않음(정가 차감으로 진행)
            pass
    if cost > 0:
        auth_service.adjust_credit(db, user.id, -cost, reason="amulet")  # 부족 시 ValueError → 402
    try:
        chart = build_chart(birth, with_daewoon=False)
        decision = decide_amulet(chart, purpose)
        png = render_amulet_png(chart, decision)
        _AMULET_DIR.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        (_AMULET_DIR / f"{token}.png").write_bytes(png)
        fname = re.sub(r"[^\w가-힣._-]", "", f"{decision['name']}_{datetime.now():%Y%m%d}") + ".png"
        try:
            (_AMULET_DIR / f"{token}.name").write_text(fname, encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    except Exception:
        db.rollback()   # 차감 포함 원복(미커밋 트랜잭션) — 실패 시 무과금
        raise
    db.commit()
    return {
        "token": token,
        "url": f"/api/amulet/{token}",
        "download_url": f"/api/amulet/{token}?download=1",
        "filename": fname,
        "credits_charged": cost,
        "pass_free": pass_free,
        "amulet": decision,
    }


def amulet_path(token: str) -> tuple[Path, str]:
    """토큰 → (파일경로, 다운로드 파일명). 없으면 LookupError."""
    if not _TOKEN_RE.match(token or ""):
        raise LookupError("잘못된 토큰")
    p = _AMULET_DIR / f"{token}.png"
    if not p.exists():
        raise LookupError("부적을 찾을 수 없어요.")
    name = "부적.png"
    np = _AMULET_DIR / f"{token}.name"
    if np.exists():
        try:
            name = np.read_text(encoding="utf-8").strip() or name
        except Exception:  # noqa: BLE001
            pass
    return p, name
