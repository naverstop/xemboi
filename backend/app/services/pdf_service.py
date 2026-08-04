"""상담서 PDF 생성 — 상장풍 고급 양식 + 사각 관인(相談之印). 6개 메뉴 공통.

reportlab platypus 로 작성해 내용이 길면 2·3장으로 자동 연결된다(멀티페이지).
테두리는 매 페이지, 헤더(제목/대상/항목/일자)는 첫 페이지, 관인·면책은 마지막
페이지 하단에 그린다(FurnitureCanvas). 한글은 시스템 폰트(맑은고딕·바탕) 등록.
"""
from __future__ import annotations

import io
import logging
import re
from datetime import date
from functools import lru_cache
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

W, H = A4  # 595.27 x 841.89 pt

NAVY = (0.10, 0.23, 0.36)
GOLD = (0.77, 0.65, 0.28)
GOLD_TX = (0.54, 0.46, 0.21)
INK = (0.10, 0.15, 0.23)
BODY = (0.17, 0.21, 0.25)
SEAL = (0.749, 0.212, 0.133)
FAINT = (0.55, 0.57, 0.60)
BRAND = (0.016, 0.588, 0.847)      # #0496d8 — 앱 브랜드 블루(레이더/바)
BRAND_DK = (0.008, 0.467, 0.714)   # #0277b6 — 1위 강조
BRAND_LT = (0.80, 0.92, 0.98)      # 레이더 채움/바 트랙

DISCLAIMER = (
    "본 상담서는 인생상담 친구(AI)의 상담 내용을 기반으로 작성되었으며, "
    "의료·법률·투자 자문을 대신할 수 없으며 그 어떤 법적 책임이 없음을 고지합니다."
)

# ── 로케일 라벨(문서 크롬) — vi 는 vi 폰트로 그려야 하므로 문구 자체를 분기한다 ──
_PDF_L: dict[str, dict[str, str]] = {
    "ko": {
        "brand": "인 생 상 담 친 구",
        "item": "상담 항목", "date": "상담 일자",
        "disclaimer": DISCLAIMER,
        "qr_cta": "QR을 스캔해 지금 바로 만나보세요",
        "qr_brand": "Xem Bói  ·  xemboi.io",
        "qr_sub": "사주·궁합·택일·타로까지 한 곳에서",
        "sec_content": "상담 내용", "sec_cards": "뽑은 카드",
        "sec_compat_a": "첫 번째 분의 사주명식", "sec_compat_b": "두 번째 분의 사주명식",
        "sec_pentagon": "궁합 요소 분석 (5요소 펜타곤)",
        "sign": "인생상담 친구", "rule": "―――",
    },
    "vi": {
        "brand": "X E M  B Ó I",
        "item": "Hạng mục tư vấn", "date": "Ngày tư vấn",
        "disclaimer": ("Bản tư vấn này được lập dựa trên nội dung tư vấn của Xem Bói (AI); "
                        "không thay thế tư vấn y tế·pháp lý·đầu tư và không chịu trách nhiệm pháp lý nào."),
        "qr_cta": "Quét mã QR để trải nghiệm ngay",
        "qr_brand": "Xem Bói  ·  xemboi.io",
        "qr_sub": "Tứ Trụ · Xem tuổi · Chọn ngày · Tarot — tất cả một nơi",
        "sec_content": "Nội dung tư vấn", "sec_cards": "Các lá bài đã rút",
        "sec_compat_a": "Lá số của người thứ nhất", "sec_compat_b": "Lá số của người thứ hai",
        "sec_pentagon": "Phân tích 5 yếu tố hợp tuổi (ngũ giác)",
        "sign": "Xem Bói", "rule": "———",
    },
}


def _lbl(key: str) -> str:
    return _PDF_L.get(_loc(), _PDF_L["ko"]).get(key, _PDF_L["ko"].get(key, key))


_CJK_RUN = re.compile(r"([⺀-⻿㐀-䶿一-鿿豈-﫿가-힣]+)")


def _wrap_cjk_vi(t: str) -> str:
    """vi 모드에서 한자·한글 run 을 KO 폰트 태그로 래핑 — vi 본문 폰트(BVP)엔 CJK 글리프가 없어
    .notdef 로 인쇄되는 것을 방지(간지 병기 '(乙巳)' 등). ko 모드는 무변환."""
    if _loc() != "vi" or not t:
        return t
    ko = _font_hanja(_F)
    return _CJK_RUN.sub(lambda m: f'<font name="{ko}">{m.group(1)}</font>', t)


def _fmt_when(d) -> str:
    return f"{d:%d/%m/%Y}" if _loc() == "vi" else f"{d:%Y년 %m월 %d일}"

# 마크다운 제거(이중 안전망) — 프론트가 이미 strip하지만 API 직접 호출 등 어떤 경로로도
# PDF에 #·**·- 같은 기호가 남지 않도록 헤더/굵게/이탤릭/불릿을 줄글로 정리한다.
_MD_HEADER = re.compile(r"(?m)^[ \t]*#{1,6}[ \t]+")
_MD_BULLET = re.compile(r"(?m)^([ \t]*)[-*+•][ \t]+")
_MD_BOLD = re.compile(r"\*\*([^\n*]+?)\*\*")
_MD_ITALIC = re.compile(r"\*([^*\n]+?)\*")


def _strip_md(text: str) -> str:
    t = text or ""
    t = _MD_HEADER.sub("", t)
    t = _MD_BULLET.sub(r"\1• ", t)
    t = _MD_BOLD.sub(r"\1", t)
    t = _MD_ITALIC.sub(r"\1", t)
    return t


def _md_inline(line: str) -> str:
    """마크다운 인라인 → reportlab 마크업: esc 먼저(injection 안전), **x**→<b>x</b>, *x* 언랩.

    [2026-07-21 운영자 요구] PDF도 화면(renderRich)처럼 굵게·소제목을 살린다 — _strip_md 평문화 대체.
    _strip_md 자체는 video/scenario.py·source.py(TTS 자막 평문화)가 import하므로 존치."""
    t = (line or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    t = _MD_BOLD.sub(r"<b>\1</b>", t)
    return _MD_ITALIC.sub(r"\1", t)

_FONTS_OK: bool | None = None
_F = "MalgunKR"
_FB = "MalgunKRBold"  # <b> 볼드 렌더용(맑은고딕 볼드) — 본문 마크다운 강조에 사용
_FT = "BatangKR"     # 제목·대상(명조 격식)
_FS = "GungsuhKR"    # 관인 폴백 폰트(궁서체)
_F_VI = "XemBoiViet"      # vi 본문(Be Vietnam Pro) — 베트남어 성조 글리프 전체 커버
_FB_VI = "XemBoiVietBold"
# PDF 활성 로케일 — generate_*(locale=) 가 설정. vi 면 _font()가 vi 폰트로 매핑(한자 지점은 _font_hanja).
# ThreadPool 동시요청 교차오염 방지 위해 contextvars(요청 컨텍스트별 독립).
import contextvars as _ctxv
_PDF_LOCALE = _ctxv.ContextVar("pdf_locale", default="ko")


def _loc() -> str:
    return _PDF_LOCALE.get()

# 관인 이미지(「相談紙印」 상담지인) — scripts/gen_seal.py 로 생성. 있으면 이걸 날인.
_SEAL_IMG = Path(__file__).resolve().parent / "assets" / "seal.png"
# 명식 패널 배경(한지+원목 테두리) — scripts/design/make_myeongsik_bg.py(FLUX)로 생성.
_MYEONGSIK_BG = Path(__file__).resolve().parent / "assets" / "myeongsik_bg.jpg"

# 오행 전통색(인쇄 대비 조정) — (배경, 글자). 목=청록, 화=적, 토=황, 금=백(먹글자), 수=현(흑).
_WX_TILE: dict[str, tuple[tuple[float, float, float], tuple[float, float, float]]] = {
    "木": ((0.16, 0.44, 0.26), (1, 1, 1)),
    "火": ((0.70, 0.19, 0.14), (1, 1, 1)),
    "土": ((0.88, 0.72, 0.29), (0.25, 0.17, 0.03)),
    "金": ((0.96, 0.95, 0.90), (0.20, 0.22, 0.26)),
    "水": ((0.15, 0.17, 0.22), (1, 1, 1)),
}


class _MyeongsikPanel(Flowable):
    """사주명식 패널 — 한지+원목 배경(FLUX 베이크) 위에 시/일/월/년 기둥을 오행색 패로 날염.

    글자·격자는 벡터(폰트)로 그려 어떤 배율에서도 선명하다. 배경 이미지가 없으면
    한지색 단색으로 폴백. pillars: [(라벨, 천간한자, 지지한자), ...] 왼→오른쪽(시일월년).
    """

    def __init__(self, width: float, pillars: list[tuple[str, str, str]], caption: str = ""):
        super().__init__()
        self.width = width
        # 배경(1152×480)의 원목 테두리(상하 ~12%)를 피해 내용을 한지 영역 안에 배치할 여유 확보
        self.height = 208
        self._pillars = pillars
        self._caption = caption

    def draw(self) -> None:  # noqa: C901
        from backend.app.saju.constants import (
            BRANCH_TO_WUXING, STEM_TO_WUXING, branch_korean, stem_korean,
        )
        c = self.canv
        w, h = self.width, self.height
        f, ft = _font_hanja(_F), _font_hanja(_FT)
        # 배경 — FLUX 한지 패널(비율 유지 꽉 채움), 없으면 한지색+원목 테두리 폴백
        c.saveState()
        if _MYEONGSIK_BG.is_file():
            try:
                c.drawImage(ImageReader(str(_MYEONGSIK_BG)), 0, 0, w, h,
                            preserveAspectRatio=False, mask=None)
            except Exception:  # noqa: BLE001
                c.setFillColorRGB(0.96, 0.93, 0.85)
                c.rect(0, 0, w, h, stroke=0, fill=1)
        else:
            c.setFillColorRGB(0.96, 0.93, 0.85)
            c.rect(0, 0, w, h, stroke=0, fill=1)
            c.setStrokeColorRGB(0.36, 0.24, 0.13)
            c.setLineWidth(5)
            c.rect(2.5, 2.5, w - 5, h - 5)
        # 제목 + 캡션(생년월일시) — 원목 테두리(상단 ~12%)를 피해 한지 영역 안에
        c.setFillColorRGB(*INK)
        c.setFont(ft, 13)
        top = h - 42
        c.drawCentredString(w / 2, top, "사 주 명 식 (四柱命式)")
        if self._caption:
            c.setFont(_font(_F), 8.5)   # 캡션은 로케일 본문 폰트(vi 성조 렌더)
            c.setFillColorRGB(0.32, 0.26, 0.16)
            top -= 14
            c.drawCentredString(w / 2, top, self._caption)
        # 기둥 격자 — 패널 중앙 배치
        n = len(self._pillars)
        if n:
            cell_w, gap = 64.0, 12.0
            grid_w = n * cell_w + (n - 1) * gap
            x0 = (w - grid_w) / 2
            y_label = top - 22
            tile_h = 42.0
            y_stem = y_label - 8 - tile_h
            y_branch = y_stem - 5 - tile_h

            def tile(x: float, y: float, ch: str, reading: str, wx: str) -> None:
                bg, tx = _WX_TILE.get(wx, ((0.9, 0.9, 0.9), (0, 0, 0)))
                c.setFillColorRGB(*bg)
                c.setStrokeColorRGB(*GOLD)
                c.setLineWidth(1.1)
                c.roundRect(x, y, cell_w, tile_h, 7, stroke=1, fill=1)
                c.setFillColorRGB(*tx)
                c.setFont(ft, 24)
                c.drawCentredString(x + cell_w / 2 - 8, y + tile_h / 2 - 8.5, ch)
                c.setFont(f, 8)
                c.drawCentredString(x + cell_w / 2 + 20, y + tile_h / 2 - 3, reading)

            for i, (label, st, br) in enumerate(self._pillars):
                x = x0 + i * (cell_w + gap)
                c.setFillColorRGB(*GOLD_TX)
                c.setFont(ft, 11.5)
                c.drawCentredString(x + cell_w / 2, y_label, label)
                if st:
                    tile(x, y_stem, st, stem_korean(st), STEM_TO_WUXING.get(st, ""))
                if br:
                    tile(x, y_branch, br, branch_korean(br), BRANCH_TO_WUXING.get(br, ""))
        c.restoreState()


def _build_myeongsik_panel(width: float, saju_chart: dict | None,
                           caption: str = "") -> "_MyeongsikPanel | None":
    """chart_json.pillars → 명식 패널 flowable. 명식이 없으면 None(패널 생략)."""
    pillars_src = (saju_chart or {}).get("pillars") or {}
    cols: list[tuple[str, str, str]] = []
    for label, key in (("시주(時)", "hour"), ("일주(日)", "day"),
                       ("월주(月)", "month"), ("년주(年)", "year")):
        p = pillars_src.get(key) or {}
        st, br = p.get("stem"), p.get("branch")
        if st and br:
            cols.append((label, st, br))
    if not cols:
        return None
    return _MyeongsikPanel(width, cols, caption)


# ---- 기질 6축 + 영역별 운세 (frontend/src/lib/sajuMetrics.ts 와 동일 결정적 산출) ----
# chart_json(ten_gods·wuxing)만으로 계산(환각 0). TS 로직과 수치 일치 유지.
_TEN_GOD_GROUP = {
    "比肩": "비겁", "劫財": "비겁", "食神": "식상", "傷官": "식상",
    "正財": "재성", "偏財": "재성", "正官": "관성", "偏官": "관성", "正印": "인성", "偏印": "인성",
    "비견": "비겁", "겁재": "비겁", "식신": "식상", "상관": "식상",
    "정재": "재성", "편재": "재성", "정관": "관성", "편관": "관성", "정인": "인성", "편인": "인성",
}


def _ten_god_groups(chart: dict) -> dict[str, int]:
    g = (chart or {}).get("ten_gods") or {}
    out = {"비겁": 0, "식상": 0, "재성": 0, "관성": 0, "인성": 0}
    for key in ("year_stem", "month_stem", "hour_stem", "year_branch", "month_branch", "day_branch", "hour_branch"):
        grp = _TEN_GOD_GROUP.get(g.get(key) or "")
        if grp:
            out[grp] += 1
    return out


def _sc(n: float) -> int:
    return max(0, min(100, round(25 + n * 18)))


def _traits(chart: dict) -> list[tuple[str, int]]:
    c = _ten_god_groups(chart)
    return [
        ("자기주도", _sc(c["비겁"])), ("표현력", _sc(c["식상"])), ("재물감각", _sc(c["재성"])),
        ("책임감", _sc(c["관성"])), ("배움", _sc(c["인성"])), ("관계유연", _sc((c["비겁"] + c["식상"]) / 2)),
    ]


def _wuxing_balance(chart: dict) -> float:
    w = (chart or {}).get("wuxing") or {}
    arr = [w.get(k, 0) for k in ("wood", "fire", "earth", "metal", "water")]
    mean = sum(arr) / 5
    if mean <= 0:
        return 0.5
    sd = (sum((x - mean) ** 2 for x in arr) / 5) ** 0.5
    return max(0.0, min(1.0, 1 - sd / mean / 1.4))


def _domains(chart: dict) -> list[tuple[str, int]]:
    c = _ten_god_groups(chart)
    health = round(35 + _wuxing_balance(chart) * 60)
    out = [
        ("직업운", _sc(c["관성"] + c["인성"] * 0.5)), ("재물운", _sc(c["재성"])),
        ("대인운", _sc((c["비겁"] + c["식상"]) / 2)), ("연애운", _sc((c["재성"] + c["관성"]) / 2)),
        ("건강운", max(0, min(100, health))),
    ]
    out.sort(key=lambda t: t[1], reverse=True)
    return out


class _MetricsPanel(Flowable):
    """기질 6축 레이더(십성 분포) + 영역별 운세 비중 바 — 결정적 계산값(참고 경향치).
    영역별은 올해 세운 반영(seun_label로 연도·세운 표기)."""

    def __init__(self, width: float, traits: list[tuple[str, int]], domains: list[tuple[str, int]], seun_label: str = ""):
        super().__init__()
        self.width = width
        self.height = 186
        self._traits = traits
        self._domains = domains
        self._seun_label = seun_label

    def draw(self) -> None:
        import math
        c = self.canv
        w, h = self.width, self.height
        f, ft = _font_hanja(_F), _font_hanja(_FT)
        # 소제목 (영역별은 올해 세운 반영)
        c.setFillColorRGB(*GOLD_TX)
        c.setFont(ft, 10.5)
        _sub = f"기질 6축 · 영역별 운세{self._seun_label}  (십성·오행 분포로 본 참고 경향치)"
        c.drawString(2, h - 12, _sub)

        # ── 좌: 레이더 ──────────────────────────────
        n = len(self._traits)
        cx, cy, R = w * 0.24, h * 0.44, 46.0

        def ang(i: int) -> float:
            return math.radians(-90 + 360.0 / n * i)

        def pt(i: int, r: float) -> tuple[float, float]:
            # reportlab은 y가 위로 증가 → 화면(SVG, y 아래로)과 방향 맞추려 sin 부호 반전(자기주도=상단)
            return cx + math.cos(ang(i)) * r, cy - math.sin(ang(i)) * r

        def poly(pts: list[tuple[float, float]], stroke, fill=None, lw=0.6):
            p = c.beginPath()
            for j, (x, y) in enumerate(pts):
                (p.moveTo if j == 0 else p.lineTo)(x, y)
            p.close()
            if fill is not None:
                c.setFillColorRGB(*fill)
            c.setStrokeColorRGB(*stroke)
            c.setLineWidth(lw)
            c.drawPath(p, stroke=1, fill=(1 if fill is not None else 0))

        for frac in (0.25, 0.5, 0.75, 1.0):   # 격자 링
            poly([pt(i, R * frac) for i in range(n)], (0.80, 0.83, 0.87), lw=0.4)
        c.setStrokeColorRGB(0.80, 0.83, 0.87)
        c.setLineWidth(0.4)
        for i in range(n):                      # 축선
            x, y = pt(i, R)
            c.line(cx, cy, x, y)
        poly([pt(i, R * v / 100) for i, (_, v) in enumerate(self._traits)],  # 값 폴리곤
             BRAND, fill=BRAND_LT, lw=1.3)
        for i, (label, v) in enumerate(self._traits):   # 라벨+수치
            lx, ly = pt(i, R + 13)
            c.setFillColorRGB(*BODY)
            c.setFont(f, 7.5)
            c.drawCentredString(lx, ly, label)
            c.setFillColorRGB(*BRAND_DK)
            c.setFont(f, 7)
            c.drawCentredString(lx, ly - 8.5, str(v))

        # ── 우: 영역별 바 ──────────────────────────────
        # 라벨(bx)~바~숫자(패널 우측 w-2 우측정렬)가 모두 패널 폭(w) 안에 들어오게 정렬(경계 넘침 방지).
        bx = w * 0.50
        num_x = w - 2               # 숫자 우측 = 패널 오른쪽 경계
        bar_w = (num_x - 24) - (bx + 42)   # 숫자 자리(24) 확보 후 바 폭
        row_h = (h - 24) / max(1, len(self._domains))
        for i, (label, v) in enumerate(self._domains):
            y = h - 24 - i * row_h - row_h * 0.5
            c.setFillColorRGB(*BODY)
            c.setFont(f, 8.5)
            c.drawString(bx, y - 3, label)
            tx = bx + 42
            c.setFillColorRGB(*BRAND_LT)          # 트랙
            c.roundRect(tx, y - 3.5, bar_w, 7, 3.5, stroke=0, fill=1)
            fill_col = BRAND_DK if i == 0 else BRAND
            c.setFillColorRGB(*fill_col)          # 채움
            c.roundRect(tx, y - 3.5, max(3.0, bar_w * v / 100), 7, 3.5, stroke=0, fill=1)
            c.setFillColorRGB(*(BRAND_DK if i == 0 else FAINT))
            c.setFont(f, 8.5)
            c.drawRightString(num_x, y - 3, str(v))   # 패널 오른쪽 경계에 우측정렬


def _build_metrics_panel(width: float, saju_chart: dict | None) -> "_MetricsPanel | None":
    """chart_json → 기질(natal)/영역별(세운 반영) 패널. ten_gods 없으면 None."""
    if not (saju_chart or {}).get("ten_gods"):
        return None
    from backend.app.saju import metrics
    aug = metrics.domain_scores(saju_chart)            # 영역별=올해 세운 반영(단일 소스)
    domains = [(d["label"], d["value"]) for d in (aug["domains"] or [])]
    seun = aug.get("seun") or {}
    seun_label = f" ({seun['year']} 세운 {seun['stem_ko']}{seun['branch_ko']})" if seun else ""
    return _MetricsPanel(width, _traits(saju_chart), domains, seun_label)


# 타로 카드 이미지 경로(프론트 public) — API 응답 image_url("/tarot/cards/x.webp")의 basename 매핑
_CARD_DIR = Path(__file__).resolve().parents[3] / "frontend" / "public" / "tarot" / "cards"


class _TarotSpread(Flowable):
    """뽑은 타로 카드들을 이미지 그리드로 날인 — 카드 아래 자리·카드명·방향. 역방향은 180° 회전.

    cards: [{position_name, name_kr, name_en, orientation('upright'|'reversed'), image_url}]
    사주 명식 패널(_MyeongsikPanel)의 타로판 — 상담 내용 앞에 배치한다.
    """

    def __init__(self, width: float, cards: list[dict]):
        super().__init__()
        import math
        self.width = width
        self.cards = cards or []
        n = len(self.cards)
        self.cols = 4 if n <= 8 else 6
        self.gap = 14.0
        self.card_w = min(70.0, (width - (self.cols + 1) * self.gap) / self.cols)
        self.card_h = self.card_w * 1.6
        self.label_h = 26.0
        self.row_gap = 12.0
        self.rows = max(1, math.ceil(n / self.cols))
        self.height = 22 + self.rows * (self.card_h + self.label_h) + (self.rows - 1) * self.row_gap

    def _img(self, image_url: str, reversed_: bool):
        name = (image_url or "").rsplit("/", 1)[-1]
        p = _CARD_DIR / name
        if not name or not p.is_file():
            return None
        try:
            from PIL import Image
            im = Image.open(str(p)).convert("RGB")
            if reversed_:
                im = im.rotate(180)
            # 원본(440x760)을 무손실 PNG로 그대로 실으면 11장 스프레드가 10MB를 넘어
            # 메일 첨부·모바일 공유가 실패한다(실측 10.11MB). 인쇄 배치 크기의 3배(약 216dpi)로
            # 줄이고 JPEG 로 저장 — 인쇄 품질은 유지되면서 용량이 수십 분의 1이 된다.
            target = (int(self.card_w * 3), int(self.card_h * 3))
            if im.width > target[0]:
                im = im.resize(target, Image.LANCZOS)
            bio = io.BytesIO()
            im.save(bio, "JPEG", quality=88, optimize=True)
            bio.seek(0)
            return ImageReader(bio)
        except Exception:  # noqa: BLE001
            try:
                return ImageReader(str(p))
            except Exception:  # noqa: BLE001
                return None

    def draw(self) -> None:
        c = self.canv
        f, ft = _font_hanja(_F), _font_hanja(_FT)
        w, cw, ch = self.width, self.card_w, self.card_h
        c.setFillColorRGB(*GOLD_TX)
        c.setFont(ft, 10.5)
        c.drawString(2, self.height - 12, _lbl("sec_cards"))
        top = self.height - 22
        for idx, card in enumerate(self.cards):
            r, col = idx // self.cols, idx % self.cols
            in_row = min(self.cols, len(self.cards) - r * self.cols)
            row_w = in_row * cw + (in_row - 1) * self.gap
            x = (w - row_w) / 2 + col * (cw + self.gap)
            y = top - (r + 1) * (ch + self.label_h) - r * self.row_gap + self.label_h
            reversed_ = str(card.get("orientation")) == "reversed"
            img = self._img(str(card.get("image_url") or ""), reversed_)
            if img is not None:
                c.drawImage(img, x, y, cw, ch, preserveAspectRatio=False, mask=None)
            else:
                c.setFillColorRGB(0.93, 0.93, 0.95)
                c.rect(x, y, cw, ch, stroke=0, fill=1)
            c.setStrokeColorRGB(*GOLD)
            c.setLineWidth(1)
            c.rect(x, y, cw, ch)
            ori = "역방향" if reversed_ else "정방향"
            c.setFillColorRGB(*GOLD_TX)
            c.setFont(f, 7.5)
            c.drawCentredString(x + cw / 2, y - 10, f"{idx + 1}. {card.get('position_name', '')}"[:16])
            c.setFillColorRGB(*BODY)
            c.setFont(f, 7)
            c.drawCentredString(x + cw / 2, y - 19, f"{card.get('name_kr', '')} · {ori}"[:20])


# PDF 한글 글꼴 후보 — (디렉터리, 본문, 굵게, 명조, 명조 subfontIndex).
# 윈도우 경로 고정이면 리눅스 이관 시 PDF 기능이 통째로 죽는다(실측 500) → 순서대로 시도한다.
# ⚠️ 마지막 후보(저장소 번들 고운바탕)는 한글만 있고 **한자가 없다** — 잡히면 경고를 남긴다.
_BUNDLED_FONT_DIR = Path(__file__).resolve().parents[3] / "tarot" / "fonts"
_FONT_CANDIDATES: tuple[tuple[str, str, str, str, int], ...] = (
    ("C:/Windows/Fonts", "malgun.ttf", "malgunbd.ttf", "batang.ttc", 0),
    ("/usr/share/fonts/opentype/noto", "NotoSansCJK-Regular.ttc", "NotoSansCJK-Bold.ttc", "NotoSerifCJK-Regular.ttc", 0),
    ("/usr/share/fonts/truetype/nanum", "NanumGothic.ttf", "NanumGothicBold.ttf", "NanumMyeongjo.ttf", 0),
    ("/usr/share/fonts/truetype/unfonts-core", "UnDotum.ttf", "UnDotumBold.ttf", "UnBatang.ttf", 0),
    (str(_BUNDLED_FONT_DIR), "GowunBatang-Regular.ttf", "GowunBatang-Bold.ttf", "GowunBatang-Regular.ttf", 0),
)


def _register_fonts() -> bool:
    global _FONTS_OK
    if _FONTS_OK is not None:
        return _FONTS_OK
    for base, normal, bold, serif, serif_idx in _FONT_CANDIDATES:
        d = Path(base)
        if not (d / normal).is_file():
            continue
        try:
            pdfmetrics.registerFont(TTFont(_F, str(d / normal)))
        except Exception:  # noqa: BLE001 — 다음 후보로
            continue
        try:
            pdfmetrics.registerFont(TTFont(_FB, str(d / bold)))
            pdfmetrics.registerFontFamily(_F, normal=_F, bold=_FB, italic=_F, boldItalic=_FB)
        except Exception:  # noqa: BLE001
            pass  # 볼드 없으면 <b>는 보통 굵기로 자연 강등(무해)
        for name, idx in ((_FT, serif_idx), (_FS, serif_idx + 2 if serif_idx == 0 else serif_idx)):
            try:
                pdfmetrics.registerFont(TTFont(name, str(d / serif), subfontIndex=idx))
            except Exception:  # noqa: BLE001
                pass
        _FONTS_OK = True
        _warn_if_no_hanja(str(d / normal))
        _register_vi_fonts()
        return _FONTS_OK
    _register_vi_fonts()
    _FONTS_OK = False
    logging.getLogger("saju.pdf").error(
        "PDF 한글 폰트를 찾지 못했습니다. 리눅스라면 한자까지 있는 CJK 폰트를 설치하세요"
        " (예: apt install fonts-noto-cjk 또는 fonts-nanum). 탐색한 경로: %s",
        ", ".join(c[0] for c in _FONT_CANDIDATES))
    return _FONTS_OK


def _warn_if_no_hanja(path: str) -> None:
    """고른 폰트에 한자가 없으면 경고 — 간지·십성 병기가 인쇄물에서 통째로 사라진다."""
    try:
        cm = getattr(pdfmetrics.getFont(_F).face, "charToGlyph", {}) or {}
        if not all(ord(c) in cm for c in "\u4e19\u5348\u6b63\u8ca1"):
            logging.getLogger("saju.pdf").warning(
                "PDF 본문 글꼴(%s)에 한자가 없습니다 — 간지·십성 병기가 인쇄물에서 빠집니다."
                " 한자까지 있는 CJK 폰트를 설치하세요.", path)
    except Exception:  # noqa: BLE001 — 경고는 부가 기능
        pass



_VI_FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"


def _register_vi_fonts() -> None:
    """vi(베트남어) 본문 폰트 등록 — Be Vietnam Pro(성조 글리프 96/96). 실패해도 ko 체인 무영향."""
    try:
        if _F_VI not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(_F_VI, str(_VI_FONT_DIR / "BeVietnamPro-Regular.ttf")))
            pdfmetrics.registerFont(TTFont(_FB_VI, str(_VI_FONT_DIR / "BeVietnamPro-Bold.ttf")))
            pdfmetrics.registerFontFamily(_F_VI, normal=_F_VI, bold=_FB_VI, italic=_F_VI, boldItalic=_FB_VI)
    except Exception:  # noqa: BLE001
        logging.getLogger("saju.pdf").warning("vi PDF 폰트(BeVietnamPro) 등록 실패 — vi 성조가 인쇄에서 빠질 수 있음")

def _font(name: str) -> str:
    # vi 활성 시 본문/제목/볼드를 vi 폰트로 매핑(등록돼 있을 때만). 간지·한자 지점은 _font_hanja 사용.
    if _loc() == "vi" and _F_VI in pdfmetrics.getRegisteredFontNames():
        vi_map = {_F: _F_VI, _FB: _FB_VI, _FT: _FB_VI, _FS: _F_VI}
        name = vi_map.get(name, name)
    return name if name in pdfmetrics.getRegisteredFontNames() else (
        _F_VI if _loc() == "vi" and _F_VI in pdfmetrics.getRegisteredFontNames() else _F)


def _font_hanja(name: str) -> str:
    """간지·한자 전용 해석 — 로케일 무관 KO 체인(맑은고딕 등, 한자 글리프 보유)."""
    return name if name in pdfmetrics.getRegisteredFontNames() else _F


def _draw_seal(c: canvas.Canvas, cx: float, cy: float, size: float = 72) -> None:
    """「相談紙印」(상담지인) 관인 — 도장 이미지를 날인. 이미지 없으면 폰트로 폴백."""
    if _SEAL_IMG.is_file():
        try:
            c.drawImage(ImageReader(str(_SEAL_IMG)), cx - size / 2, cy - size / 2,
                        size, size, mask="auto", preserveAspectRatio=True)
            return
        except Exception:  # noqa: BLE001
            pass
    # 폴백: 폰트로 相談紙印 (전통 배치 — 우열 相談, 좌열 紙印)
    ft = _font_hanja(_FS)
    half = size / 2
    c.saveState()
    c.setStrokeColorRGB(*SEAL)
    c.setLineWidth(3)
    c.rect(cx - half, cy - half, size, size)
    c.setFillColorRGB(*SEAL)
    fs = size * 0.40
    c.setFont(ft, fs)
    q = size / 4
    for ch, dx, dy in [("紙", -q, q), ("相", q, q), ("印", -q, -q), ("談", q, -q)]:
        c.drawCentredString(cx + dx, cy + dy - fs * 0.35, ch)
    c.restoreState()


def _draw_qr_cta(c: canvas.Canvas, x: float, y: float, size: float = 54) -> None:
    """관인 옆(좌하단) — 사이트 방문 QR + 유도 문구. 스캔 시 https://saju.songstock.art/ 로 이동.

    reportlab 내장 벡터 QR(QrCodeWidget) — 외부 라이브러리·이미지 파일 없이 배율 무관 선명.
    실패해도(예: 드로잉 오류) PDF 생성 자체엔 영향 없다.
    """
    url = "https://xemboi.io/"
    try:
        from reportlab.graphics.barcode.qr import QrCodeWidget
        from reportlab.graphics.shapes import Drawing
        from reportlab.graphics import renderPDF
        qr = QrCodeWidget(url)
        b = qr.getBounds()
        qw, qh = (b[2] - b[0]) or 1, (b[3] - b[1]) or 1
        d = Drawing(size, size, transform=[size / qw, 0, 0, size / qh, 0, 0])
        d.add(qr)
        # 흰 배경(스캔 여백) + 옅은 골드 테두리(카드감)
        c.saveState()
        c.setFillColorRGB(1, 1, 1)
        c.rect(x - 4, y - 4, size + 8, size + 8, fill=1, stroke=0)
        c.setStrokeColorRGB(*GOLD)
        c.setLineWidth(0.8)
        c.rect(x - 4, y - 4, size + 8, size + 8, fill=0, stroke=1)
        c.restoreState()
        renderPDF.draw(d, c, x, y)
    except Exception:  # noqa: BLE001
        return
    # 유도 문구(QR 오른쪽, 상단 정렬)
    f = _font(_F)
    tx = x + size + 14
    top = y + size
    c.setFillColorRGB(*INK)
    c.setFont(f, 10)
    c.drawString(tx, top - 11, _lbl("qr_cta"))
    c.setFillColorRGB(*NAVY)
    c.setFont(f, 9)
    c.drawString(tx, top - 26, _lbl("qr_brand"))
    c.setFillColorRGB(*FAINT)
    c.setFont(f, 8)
    c.drawString(tx, top - 40, _lbl("qr_sub"))


class FurnitureCanvas(canvas.Canvas):
    """페이지별 장식: 테두리(매 페이지) + 마지막 페이지에 관인·서명·면책.

    총 페이지 수를 알아야 '마지막 페이지'를 판정하므로, 페이지 상태를 모았다가
    save() 시점에 일괄 그린다.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_states: list[dict] = []

    def showPage(self):  # noqa: N802
        self._saved_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_states)
        for i, state in enumerate(self._saved_states):
            self.__dict__.update(state)
            self._draw_furniture(i + 1, total)
            super().showPage()
        super().save()

    def _draw_furniture(self, page_no: int, total: int) -> None:
        self.setStrokeColorRGB(*NAVY)
        self.setLineWidth(3)
        self.rect(20, 20, W - 40, H - 40)
        self.setStrokeColorRGB(*GOLD)
        self.setLineWidth(0.8)
        self.rect(28, 28, W - 56, H - 56)
        f = _font(_F)
        if total > 1:
            self.setFont(f, 8.5)
            self.setFillColorRGB(*FAINT)
            self.drawCentredString(W / 2, 40, f"- {page_no} / {total} -")
        if page_no == total:
            self.setFont(f, 12)
            self.setFillColorRGB(*INK)
            self.drawCentredString(W - 96, 132, _lbl("sign"))
            _draw_seal(self, W - 96, 86)
            self.setFont(f, 8)
            self.setFillColorRGB(*FAINT)
            # 폭을 관인(우하단) 왼쪽으로 제한해 겹침 방지
            for j, ln in enumerate(simpleSplit(_lbl("disclaimer"), f, 8, W - 210)):
                self.drawString(55, 70 - j * 11, ln)
            # 사이트 방문 QR + 유도 문구(관인 왼쪽 빈 영역, 면책 위)
            _draw_qr_cta(self, 54, 84, 60)


# 본문 글꼴에 없는 기호는 인쇄물에서 '소리 없이' 사라진다(실측 2026-07-22: ⚠·✓ 소실, ※·★·●·√는 정상).
# 택일 리포트의 경고 표시 ⚠ 3개가 PDF에서만 증발해 '다만,  주의 표기가 있는 날에는'처럼 빈칸만
# 남던 사고 — 화면과 인쇄물의 뜻이 달라지므로 렌더 직전에 표현 가능한 기호로 바꾼다.
_PDF_GLYPH_FALLBACK = {"⚠": "※", "✓": "√", "✔": "√"}


_ASCII_OK = set(range(0x20, 0x7F))


_CP_CACHE: dict[str, frozenset[int]] = {}


def _font_codepoints() -> frozenset[int]:
    """본문 글꼴이 실제로 그릴 수 있는 코드포인트 집합. 실패하면 빈 집합(=검사 생략).

    reportlab 이 폰트를 등록하며 이미 파싱해 둔 cmap(charToGlyph)을 그대로 쓴다 —
    별도 의존성(fontTools) 없이, 실제로 렌더에 쓰일 바로 그 폰트를 근거로 판정한다.
    """
    key = _loc()
    if key in _CP_CACHE:
        return _CP_CACHE[key]
    try:
        _register_fonts()
        face = getattr(pdfmetrics.getFont(_font(_F)), "face", None)
        cps = frozenset(getattr(face, "charToGlyph", {}) or {})
        if key == "vi":
            # vi 본문에 한자 병기('(乙巳)')가 섞여도 삭제하지 않게 ko 폰트 cmap 합집합으로 판정.
            ko_face = getattr(pdfmetrics.getFont(_font_hanja(_F)), "face", None)
            cps = cps | frozenset(getattr(ko_face, "charToGlyph", {}) or {})
    except Exception:  # noqa: BLE001 — 글리프 검사는 부가 기능
        cps = frozenset()
    _CP_CACHE[key] = cps
    return cps


def _sub_missing_glyphs(t: str) -> str:
    """글꼴에 없는 글자를 표현 가능한 기호로 바꾸고, 대체가 없으면 지운다.

    그대로 두면 .notdef 로 인쇄돼 화면엔 있는 표시가 인쇄물에서만 사라진다(실측: ⚠·✓ 소실,
    🎁·🔮·✦ 전멸). 텍스트 추출 시에도 NUL 로 남아 복사·검색이 깨진다.
    """
    if not t:
        return t
    for bad, good in _PDF_GLYPH_FALLBACK.items():
        if bad in t:
            t = t.replace(bad, good)
    cps = _font_codepoints()
    if not cps:
        return t
    out = []
    for ch in t:
        o = ord(ch)
        if o in _ASCII_OK or ch in "\n\r\t" or o in cps:
            out.append(ch)
        # 그릴 수 없는 글자는 버린다(빈칸도 남기지 않는다 — 문장이 어색해지지 않도록).
    return "".join(out)


def _build_compat_pentagon(width: float, factors: list):
    """궁합 5요소 펜타곤(레이더) — 화면 Pentagon 과 동일 5축을 PDF에 그린다(운영자 지적 #12).
    factors: [(짧은라벨, 점수0~100), ...]. Drawing(Flowable) 반환, 실패/부족 시 None(패널 생략)."""
    try:
        import math
        from reportlab.graphics.shapes import Drawing, Polygon, Line, String
        from reportlab.lib.colors import Color
        pts = [(str(lb), max(0, min(100, int(sc or 0)))) for lb, sc in (factors or [])]
        n = len(pts)
        if n < 3:
            return None
        gold, goldtx, ink = Color(*GOLD), Color(*GOLD_TX), Color(*INK)
        grid = Color(0.80, 0.76, 0.66)
        fill = Color(GOLD[0], GOLD[1], GOLD[2], 0.18)   # 반투명 금색 면
        HH = 210.0
        cx, cy, R = width / 2.0, HH / 2.0 + 2, 70.0

        def _pt(i, frac):
            ang = math.pi / 2 - (2 * math.pi * i / n)   # 위(90°)에서 시계방향
            return (cx + R * frac * math.cos(ang), cy + R * frac * math.sin(ang))

        d = Drawing(width, HH)
        for g in (0.25, 0.5, 0.75, 1.0):                # 배경 그리드 링
            ring: list = []
            for i in range(n):
                x, y = _pt(i, g)
                ring += [x, y]
            d.add(Polygon(ring, strokeColor=grid, strokeWidth=0.4, fillColor=None))
        for i in range(n):                              # 축선
            x, y = _pt(i, 1.0)
            d.add(Line(cx, cy, x, y, strokeColor=grid, strokeWidth=0.4))
        data: list = []                                 # 점수 폴리곤
        for i, (_, sc) in enumerate(pts):
            x, y = _pt(i, sc / 100.0)
            data += [x, y]
        d.add(Polygon(data, strokeColor=gold, strokeWidth=1.5, fillColor=fill))
        fnt = _font_hanja(_F)
        for i, (lb, sc) in enumerate(pts):              # 꼭짓점 라벨 + 점수
            lx, ly = _pt(i, 1.17)
            d.add(String(lx, ly, lb, fontName=fnt, fontSize=8, fillColor=ink, textAnchor="middle"))
            d.add(String(lx, ly - 9, f"{sc}점", fontName=fnt, fontSize=7.5, fillColor=goldtx, textAnchor="middle"))
        return d
    except Exception:  # noqa: BLE001 — 시각요소 실패해도 본문 PDF는 생성
        return None


def generate_consultation_pdf(
    *,
    doc_title: str,
    person_line: str,
    item: str,
    content: str,
    when: date | None = None,
    saju_chart: dict | None = None,
    saju_caption: str = "",
    tarot_cards: list[dict] | None = None,
    compat: dict | None = None,
    locale: str = "ko",
) -> bytes:
    """상담서 PDF(bytes). 내용이 길면 자동으로 2·3장으로 연결된다.

    saju_chart(chat_sessions.chart_json)가 있으면 상담 내용 앞에 사주명식 패널
    (한지+원목 배경 위 오행색 기둥)을 넣는다. saju_caption=생년월일시 등 부가 표기.

    compat(궁합)가 있으면 두 사람의 명식 2개 + 5요소 펜타곤을 넣는다(운영자 지적 #12).
    형식: {"a_chart","a_cap","b_chart","b_cap","factors":[(라벨,점수)...]}. 기본 None → 하위호환.
    """
    _PDF_LOCALE.set("vi" if locale == "vi" else "ko")   # 폰트 매핑·글리프 검사 기준(컨텍스트 로컬)
    _register_fonts()
    # 심층 방어 — 인쇄물은 되돌릴 수 없으므로 렌더러가 스스로 정리한다(전수감사 실측: 종합 감정서
    # 경로가 정리 체인을 안 타 '---' 5줄과 십성 한자 단독 '劫財'가 그대로 인쇄됐다). 체인은 멱등이라
    # 이미 정리된 본문에는 아무 일도 하지 않는다.
    try:
        from backend.app.saju.constants import fix_term_hanja as _ftj
        content = _ftj(content or "")
    except Exception:  # noqa: BLE001 — 정리 실패해도 인쇄는 계속
        pass
    # 본문은 마크다운 변환기를 타므로 esc()를 안 거친다 — 글리프 치환은 입력 단계에서 한 번에.
    content = _sub_missing_glyphs(content or "")
    when = when or date.today()
    f, ft = _font(_F), _font(_FT)
    buf = io.BytesIO()

    # 본문 프레임: 테두리 안, 하단은 관인·면책 공간(150pt) 확보
    frame = Frame(52, 150, W - 104, H - 150 - 56, id="body",
                  leftPadding=8, rightPadding=8, topPadding=10, bottomPadding=6)
    doc = BaseDocTemplate(buf, pagesize=A4,
                          pageTemplates=[PageTemplate(id="main", frames=[frame])])

    s_brand = ParagraphStyle("brand", fontName=f, fontSize=11, leading=16,
                             alignment=1, textColor=GOLD_TX, spaceAfter=14)
    s_title = ParagraphStyle("title", fontName=ft, fontSize=25, leading=32,
                             alignment=1, textColor=INK, spaceAfter=6)
    s_rule = ParagraphStyle("rule", fontName=f, fontSize=2, leading=2, alignment=1,
                            textColor=GOLD)
    s_person = ParagraphStyle("person", fontName=f, fontSize=15, leading=22,
                              alignment=1, textColor=INK, spaceBefore=8, spaceAfter=16)
    s_label = ParagraphStyle("label", fontName=f, fontSize=11, leading=16,
                             textColor=GOLD_TX, spaceBefore=6, spaceAfter=6)
    s_body = ParagraphStyle("body", fontName=f, fontSize=11, leading=18, textColor=BODY)

    def esc(t: str) -> str:
        t = _sub_missing_glyphs(t or "")
        t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return _wrap_cjk_vi(t)

    story: list = [
        Paragraph(_lbl("brand"), s_brand),
        Paragraph(esc(doc_title), s_title),
        Paragraph(_lbl("rule"), s_rule),
    ]
    if (person_line or "").strip():
        story.append(Paragraph(esc(person_line), s_person))
    else:
        story.append(Spacer(1, 10))
    # 항목 값은 Paragraph 로 — raw 문자열이면 줄바꿈이 안 돼 긴 항목명(약 48자~)이 테두리 밖으로
    # 밀려 잘렸다(전수감사 실측: 160자 입력 시 x=605pt > 페이지 폭 595pt).
    s_cell = ParagraphStyle("cell", fontName=f, fontSize=11, leading=15, textColor=BODY)
    info = Table(
        [[_lbl("item"), Paragraph(esc(item), s_cell)], [_lbl("date"), _fmt_when(when)]],
        colWidths=[70, W - 104 - 70 - 16],
    )
    info.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), f, 11),
        ("TEXTCOLOR", (0, 0), (0, -1), GOLD_TX),
        ("TEXTCOLOR", (1, 0), (1, -1), BODY),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, (0.90, 0.88, 0.81)),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(info)
    story.append(Spacer(1, 12))
    # 사주명식 패널 — 본인 명식(命式)을 고급 한지 패널로 날염(상담 문의 등 연락처는 넣지 않음)
    panel = _build_myeongsik_panel(W - 104 - 16, saju_chart, saju_caption)
    if panel is not None:
        story.append(panel)
        story.append(Spacer(1, 10))
        # 명식 아래 — 기질 6축 레이더 + 영역별 운세 비중(화면과 동일 결정적 산출)
        metrics = _build_metrics_panel(W - 104 - 16, saju_chart)
        if metrics is not None:
            story.append(metrics)
            story.append(Spacer(1, 12))
    # 궁합 — 두 사람의 명식 2개 + 5요소 펜타곤(운영자 지적 #12 '두 명의 사주·펜타곤·평가가 PDF에').
    #   평가 점수 텍스트는 본문(content=pdfHeader+해설)에 이미 있고, 여기서 시각요소를 더한다.
    if compat:
        try:
            pa = _build_myeongsik_panel(W - 104 - 16, compat.get("a_chart"), compat.get("a_cap") or "")
            if pa is not None:
                story.append(Paragraph(_lbl("sec_compat_a"), s_label))
                story.append(pa); story.append(Spacer(1, 10))
            pb = _build_myeongsik_panel(W - 104 - 16, compat.get("b_chart"), compat.get("b_cap") or "")
            if pb is not None:
                story.append(Paragraph(_lbl("sec_compat_b"), s_label))
                story.append(pb); story.append(Spacer(1, 10))
        except Exception:  # noqa: BLE001 — 명식 패널 실패해도 본문은 생성
            pass
        try:
            penta = _build_compat_pentagon(W - 104 - 16, compat.get("factors") or [])
            if penta is not None:
                story.append(Paragraph(_lbl("sec_pentagon"), s_label))
                story.append(penta); story.append(Spacer(1, 12))
        except Exception:  # noqa: BLE001
            pass
    # 타로 스프레드 — 뽑은 카드 이미지 그리드(역방향 180° 회전). 상담 내용 앞에 배치.
    if tarot_cards:
        try:
            story.append(_TarotSpread(W - 104 - 16, tarot_cards))
            story.append(Spacer(1, 12))
        except Exception:  # noqa: BLE001
            pass  # 카드 패널 실패해도 본문은 생성
    story.append(Paragraph(_lbl("sec_content"), s_label))
    # [2026-07-21] 마크다운을 제거하지 않고 렌더 — ### 소제목=굵은 제목 줄, **강조**=<b>, 불릿=•.
    # 평문 입력(궁합·타로 등 strip 선적용 경로, 종합 감정서)은 변환기 통과 시 무변화(하위 호환).
    s_head = ParagraphStyle("mdhead", fontName=_font(_FB), fontSize=12, leading=18,
                            textColor=INK, spaceBefore=8, spaceAfter=4)
    for blk in (content or "").split("\n\n"):
        blk = blk.strip()
        if not blk:
            continue
        lines_out: list[str] = []
        for ln in blk.split("\n"):
            hm = _MD_HEADER.match(ln)
            if hm:  # 헤더 줄 — 내부 ** 언랩 후 줄 전체 굵은 제목(중첩 <b> 회피)
                body = _MD_BOLD.sub(r"\1", ln[hm.end():])
                body = _MD_ITALIC.sub(r"\1", body)
                if lines_out:  # 헤더 전까지의 본문을 먼저 문단으로
                    story.append(Paragraph("<br/>".join(lines_out), s_body))
                    story.append(Spacer(1, 8))
                    lines_out = []
                story.append(Paragraph(esc(body), s_head))
                continue
            ln = _MD_BULLET.sub(r"\1• ", ln)
            lines_out.append(_wrap_cjk_vi(_md_inline(ln)))
        if lines_out:
            story.append(Paragraph("<br/>".join(lines_out), s_body))
            story.append(Spacer(1, 8))

    doc.build(story, canvasmaker=FurnitureCanvas)
    return buf.getvalue()
