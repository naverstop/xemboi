"""상담서 PDF 생성 — 상장풍 고급 양식 + 사각 관인(相談之印). 6개 메뉴 공통.

reportlab platypus 로 작성해 내용이 길면 2·3장으로 자동 연결된다(멀티페이지).
테두리는 매 페이지, 헤더(제목/대상/항목/일자)는 첫 페이지, 관인·면책은 마지막
페이지 하단에 그린다(FurnitureCanvas). 한글은 시스템 폰트(맑은고딕·바탕) 등록.
"""
from __future__ import annotations

import io
import re
from datetime import date
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

DISCLAIMER = (
    "본 상담서는 인생상담 친구(AI)의 상담 내용을 기반으로 작성되었으며, "
    "의료·법률·투자 자문을 대신할 수 없으며 그 어떤 법적 책임이 없음을 고지합니다."
)

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

_FONTS_OK: bool | None = None
_F = "MalgunKR"
_FT = "BatangKR"     # 제목·대상(명조 격식)
_FS = "GungsuhKR"    # 관인 폴백 폰트(궁서체)

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
        f, ft = _font(_F), _font(_FT)
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
            c.setFont(f, 8.5)
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


def _register_fonts() -> bool:
    global _FONTS_OK
    if _FONTS_OK is not None:
        return _FONTS_OK
    d = Path("C:/Windows/Fonts")
    try:
        pdfmetrics.registerFont(TTFont(_F, str(d / "malgun.ttf")))
        try:
            pdfmetrics.registerFont(TTFont(_FT, str(d / "batang.ttc"), subfontIndex=0))
        except Exception:  # noqa: BLE001
            pass
        try:
            pdfmetrics.registerFont(TTFont(_FS, str(d / "batang.ttc"), subfontIndex=2))
        except Exception:  # noqa: BLE001
            pass
        _FONTS_OK = True
    except Exception:  # noqa: BLE001
        _FONTS_OK = False
    return _FONTS_OK


def _font(name: str) -> str:
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
    ft = _font(_FS)
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
            self.drawCentredString(W - 96, 132, "인생상담 친구")
            _draw_seal(self, W - 96, 86)
            self.setFont(f, 8)
            self.setFillColorRGB(*FAINT)
            # 폭을 관인(우하단) 왼쪽으로 제한해 겹침 방지
            for j, ln in enumerate(simpleSplit(DISCLAIMER, f, 8, W - 210)):
                self.drawString(55, 70 - j * 11, ln)


def generate_consultation_pdf(
    *,
    doc_title: str,
    person_line: str,
    item: str,
    content: str,
    when: date | None = None,
    saju_chart: dict | None = None,
    saju_caption: str = "",
) -> bytes:
    """상담서 PDF(bytes). 내용이 길면 자동으로 2·3장으로 연결된다.

    saju_chart(chat_sessions.chart_json)가 있으면 상담 내용 앞에 사주명식 패널
    (한지+원목 배경 위 오행색 기둥)을 넣는다. saju_caption=생년월일시 등 부가 표기.
    """
    _register_fonts()
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
        return (t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    story: list = [
        Paragraph("인 생 상 담 친 구", s_brand),
        Paragraph(esc(doc_title), s_title),
        Paragraph("―――", s_rule),
    ]
    if (person_line or "").strip():
        story.append(Paragraph(esc(person_line), s_person))
    else:
        story.append(Spacer(1, 10))
    info = Table(
        [["상담 항목", esc(item)], ["상담 일자", f"{when:%Y년 %m월 %d일}"]],
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
        story.append(Spacer(1, 14))
    story.append(Paragraph("상담 내용", s_label))
    for blk in _strip_md(content).split("\n\n"):
        blk = blk.strip()
        if blk:
            story.append(Paragraph(esc(blk).replace("\n", "<br/>"), s_body))
            story.append(Spacer(1, 8))

    doc.build(story, canvasmaker=FurnitureCanvas)
    return buf.getvalue()
