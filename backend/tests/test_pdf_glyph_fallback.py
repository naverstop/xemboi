# -*- coding: utf-8 -*-
"""PDF 인쇄물에서 기호가 소리 없이 사라지던 결함 (전수감사 2026-07-22).

택일 리포트의 경고 표시 ⚠ 3개가 화면에는 있는데 PDF에서만 증발해
'다만,  주의 표기가 있는 날에는'처럼 빈칸만 남았다(본문 글꼴에 글리프가 없어 .notdef 출력).
화면과 인쇄물의 뜻이 달라지므로 렌더 직전에 표현 가능한 기호로 바꾼다.
"""
import io

import pytest

from backend.app.services import pdf_service as P


def test_glyph_fallback_map_is_applied():
    assert P._sub_missing_glyphs("⚠ 주의 ✓ 확인") == "※ 주의 √ 확인"
    assert P._sub_missing_glyphs("그대로 ※ 유지 ★ 됨") == "그대로 ※ 유지 ★ 됨"
    assert P._sub_missing_glyphs("") == ""


def test_pdf_keeps_warning_marker_visible():
    reader = pytest.importorskip("pypdf")
    body = "⚠ 이 날은 조심하세요. 체크 ✓ 도 있습니다."
    pdf = P.generate_consultation_pdf(doc_title="마커시험", person_line="테 스 트 님",
                                      item="택일", content=body, when=None)
    text = "\n".join((p.extract_text() or "")
                     for p in reader.PdfReader(io.BytesIO(pdf)).pages)
    assert "※" in text and "√" in text     # 대체 기호로 살아 있음
    assert "\x00" not in text                        # 표현 불가 글리프(.notdef)가 남지 않음
    assert "이 날은 조심하세요" in text


def test_tarot_pdf_stays_small_enough_to_share():
    """[2026-07-22 전수감사] 카드 원본(440x760)을 무손실 PNG로 그대로 실어 11장 스프레드가
    10.11MB — 메일 첨부·모바일 공유가 실패할 크기였다. 배치 크기의 3배로 줄이고 JPEG 로 저장."""
    import glob
    import os
    reader = pytest.importorskip("pypdf")
    files = sorted(glob.glob(os.path.join(
        os.path.dirname(P.__file__), "..", "..", "..", "frontend", "public", "tarot", "cards", "*.webp")))
    if len(files) < 11:
        pytest.skip("타로 카드 이미지가 없는 환경")
    cards = [{"position_name": f"{i+1}번", "name_kr": "카드", "name_en": "Card",
              "orientation": "reversed" if i % 3 == 0 else "upright",
              "image_url": "/tarot/cards/" + os.path.basename(n)}
             for i, n in enumerate(files[:11])]
    pdf = P.generate_consultation_pdf(doc_title="타로", person_line="테 스 트 님", item="타로",
                                      content="타로 상담 본문입니다." * 30, when=None,
                                      tarot_cards=cards)
    assert len(pdf) < 2 * 1024 * 1024, f"{len(pdf)} bytes — 공유 실패 위험 크기"
    pages = reader.PdfReader(io.BytesIO(pdf)).pages
    imgs = [im for pg in pages for im in (pg.images or [])]
    assert len(imgs) >= 11                    # 카드가 빠지지 않았다
    assert all(im.image.width >= 100 for im in imgs)   # 인쇄 가능한 해상도는 유지


def test_font_candidate_chain_survives_non_windows():
    """[운영자 결정 2026-07-22] 폰트 경로가 C:/Windows/Fonts 고정이라 리눅스 이관 시
    PDF 기능이 통째로 죽었다(500 pdf_generation_failed). 후보를 순서대로 시도하고,
    저장소 번들 글꼴까지 폴백해 최소한 한글은 인쇄되게 한다."""
    import io as _io
    reader = pytest.importorskip("pypdf")
    saved_cands, saved_ok = P._FONT_CANDIDATES, P._FONTS_OK
    try:
        # 리눅스 상황 재현: 시스템 폰트 후보를 모두 빼고 번들만 남긴다
        P._FONT_CANDIDATES = tuple(c for c in saved_cands if "tarot" in c[0])
        P._FONTS_OK = None
        P._font_codepoints.cache_clear()
        assert P._register_fonts() is True
        pdf = P.generate_consultation_pdf(doc_title="폴백", person_line="테 스 트 님",
                                          item="확인", content="한글 본문은 정상 인쇄되어야 합니다.",
                                          when=None)
        text = "".join((p.extract_text() or "")
                       for p in reader.PdfReader(_io.BytesIO(pdf)).pages).replace(" ", "")
        assert "한글본문은정상" in text
        # 후보가 하나도 없으면 조용히 죽지 말고 False 를 돌려 준다(로그로 설치 안내)
        P._FONT_CANDIDATES, P._FONTS_OK = (), None
        assert P._register_fonts() is False
    finally:
        P._FONT_CANDIDATES, P._FONTS_OK = saved_cands, saved_ok
        P._font_codepoints.cache_clear()
        P._register_fonts()


def test_today_brief_no_longer_carries_yearly_scores():
    """[운영자 결정] 오늘의운세 브리핑에서 '올해 배경' 영역 점수를 뺀다 —
    지시로는 9회 중 8회 '오늘은 건강운이…'로 오귀속을 못 막았다."""
    from types import SimpleNamespace
    from backend.app.services.tool_service import _render
    row = SimpleNamespace(
        tool="today", kind="today", input_json={}, chart_json=None,
        result_json={"date": "2026-07-22", "iljin": {"label": "을유"},
                     "ten_god": {"ko": "편재", "hanja": "偏財", "line": "x"},
                     "lucky": {"color": "백", "direction": "서", "element": "금"},
                     "day_master": {"ko": "을"}, "relations_all": [],
                     "year": {"seun": {"year": 2026, "stem_ko": "병", "branch_ko": "오"},
                              "domains": [{"label": "건강운", "value": 100},
                                          {"label": "재물운", "value": 43}]}})
    brief = _render(row)
    # 점수 '값'이 사라져야 한다(문구 '영역 점수'는 금지 지시 안에 남는다)
    assert "건강운" not in brief and "올해 강한 영역" not in brief and "100" not in brief
    assert "0~100" not in brief
    assert "연간 운세나 영역 점수 같은" in brief      # 끌어오지 말라는 지시는 남긴다
