"""베트남 로케일(vi) 골든 검증 — 이중 로케일 전환 Phase 1.

원칙(무오류): ko 경로 불변 + vi 경로의 (독음·십이지·역법·진태양시)를 권위 근거로 잠근다.
근거 약어:
  [뗏]  베트남 뗏(설) = 음력 1/1. 2007년 뗏 = 양 2007-02-17 (중국 춘절 2/18과 하루 차이).
  [HND] 호응옥득(Hồ Ngọc Đức) 베트남 음력 알고리즘(UTC+7). sxtwl 대조 tz=8 일치·왕복무결 검증됨.
  [십이지] 베트남 12 con giáp: 卯=Mèo(고양이), 丑=Trâu(물소).
  [TST] 진태양시 = (경도 − 표준자오선 105°E)×4분. 하노이 105.85° → +3.4분.
"""
from __future__ import annotations

from datetime import date, time

from backend.app.saju.constants import (
    branch_reading,
    stem_reading,
    ten_god_reading,
    wuxing_reading,
    zodiac_reading,
)
from backend.app.saju.engine import build_chart
from backend.app.saju.pillars import _adjust_time
from backend.app.saju.types import BirthInput, CalendarType


# ============================================================
# 1) 독음·십이지 로케일 갈림 (卯 토끼→Mèo, 丑 소→Trâu)
# ============================================================
def test_readings_vi_vs_ko():
    assert stem_reading("甲", "vi") == "Giáp" and stem_reading("甲", "ko") == "갑"
    assert branch_reading("卯", "vi") == "Mão" and branch_reading("卯", "ko") == "묘"
    assert wuxing_reading("水", "vi") == "Thủy" and wuxing_reading("水", "ko") == "수"
    assert ten_god_reading("正官", "vi") == "Chính quan"

def test_zodiac_cat_and_buffalo():
    # ★ 헤드라인: 卯 = 고양이(Mèo), 丑 = 물소(Trâu) — 한국과 갈림
    assert zodiac_reading("卯", "vi") == "Mèo" and zodiac_reading("卯", "ko") == "토끼"
    assert zodiac_reading("丑", "vi") == "Trâu" and zodiac_reading("丑", "ko") == "소"
    # 나머지는 동일 개념
    assert zodiac_reading("午", "vi") == "Ngựa"  # 말
    # 기본 인자는 ko (하위호환)
    assert zodiac_reading("卯") == "토끼"


# ============================================================
# 2) 음력 입력 divergence — VN 뗏 2007 [뗏][HND]
#    음력 1/1/2007 → vi 양력 2/17 / ko(중국) 양력 2/18 (하루 차이)
# ============================================================
def test_lunar_input_tet_2007_divergence():
    vi = BirthInput(birth_date=date(2007, 1, 1), calendar=CalendarType.LUNAR, locale="vi")
    ko = BirthInput(birth_date=date(2007, 1, 1), calendar=CalendarType.LUNAR, locale="ko")
    cv = build_chart(vi, with_daewoon=False)
    ck = build_chart(ko, with_daewoon=False)
    assert cv.solar_date == date(2007, 2, 17), "베트남 음력 1/1/2007 = 양력 2/17(뗏)"
    assert ck.solar_date == date(2007, 2, 18), "중국·한국 음력 1/1/2007 = 양력 2/18(춘절)"
    # 하루 차이 → 일주(日柱)가 통째로 달라진다
    assert cv.pillars.day.gz != ck.pillars.day.gz


# ============================================================
# 3) 양력 입력 → 음력 표시 divergence
#    2007-02-17: vi 음력 1/1(뗏) / ko 음력 2006-12-30
# ============================================================
def test_solar_to_lunar_display_divergence():
    vi = build_chart(BirthInput(birth_date=date(2007, 2, 17), locale="vi"), with_daewoon=False)
    ko = build_chart(BirthInput(birth_date=date(2007, 2, 17), locale="ko"), with_daewoon=False)
    assert (vi.lunar_date.month, vi.lunar_date.day) == (1, 1)      # 뗏
    assert (ko.lunar_date.month, ko.lunar_date.day) == (12, 30)    # 섣달그믐
    # 양력이 같으니 사주 간지(년월일)는 동일해야 한다 — 역법 표시만 다름
    assert vi.pillars.day.gz == ko.pillars.day.gz
    assert vi.pillars.year.gz == ko.pillars.year.gz


# ============================================================
# 4) 진태양시 — 베트남은 보정 미미(+3분), 한국은 -32분 [TST]
# ============================================================
def _adj_vi(y, m, d, hh, mm, lon=None):
    b = BirthInput(birth_date=date(y, m, d), birth_time=time(hh, mm),
                   locale="vi", apply_true_solar_time=True, birth_longitude=lon)
    _, _, at = _adjust_time(b, date(y, m, d))  # (표준일, 표준시각, 진태양시각)
    return at

def test_true_solar_vietnam_small_correction():
    # 하노이 105.85°E vs 표준자오선 105°E → +3.4분 ≈ +3분
    assert _adj_vi(2000, 7, 15, 12, 0, lon=105.85) == time(12, 3)
    # 경도 미지정 → 하노이 기본(105.85)
    assert _adj_vi(2000, 7, 15, 12, 0) == time(12, 3)
    # 호치민 106.63°E → (106.63-105)*4 = +6.5분 ≈ +7분
    assert _adj_vi(2000, 7, 15, 12, 0, lon=106.63) == time(12, 7)

def test_vietnam_no_dst_removal():
    # 베트남 현대는 서머타임 없음 → 진태양시 미적용이면 시계 그대로
    b = BirthInput(birth_date=date(2000, 7, 15), birth_time=time(12, 0),
                   locale="vi", apply_true_solar_time=False)
    _, _, at = _adjust_time(b, date(2000, 7, 15))
    assert at == time(12, 0)


# ============================================================
# 5) ko 경로 불변 안전판 — locale 필드 추가가 한국 결과를 흔들지 않음
# ============================================================
def test_language_guard_vi_vs_ko():
    from backend.app.saju.lang_guard import (
        clean_guard, looks_korean_clean, looks_vietnamese_clean, response_language_rule,
    )
    vi_good = ("Nhật chủ Giáp Mộc sinh vào tháng Ngọ, khí Hỏa vượng nên cần Dụng thần là Thủy "
               "để điều hậu. Vận trình sắp tới có nhiều cơ hội về tài lộc và công danh.")
    cn_drift = "日主甲木生于午月，火气旺盛，需要用水来调候，未来大运财运转好。"
    en_drift = "The day master is Yang Wood born in the Horse month with very strong fire energy."
    ko_good = ("갑목 일간이 오월에 태어나 화기가 왕성하니 조후용신으로 수(水)가 필요합니다. "
               "앞으로의 대운에서 재물운이 점차 좋아지는 흐름입니다.")
    # vi 가드: 정상통과 / 한자·영어 드리프트 폐기
    assert looks_vietnamese_clean(vi_good) is True
    assert looks_vietnamese_clean(cn_drift) is False   # 한자 = 중국어 드리프트
    assert looks_vietnamese_clean(en_drift) is False   # 순 ASCII = 영어 드리프트
    assert looks_vietnamese_clean("") is False
    # ko 가드: 한국어 통과 / 한자과다·비한국어 폐기 (기존 동작 보존)
    assert looks_korean_clean(ko_good) is True
    assert looks_korean_clean(cn_drift) is False
    assert looks_korean_clean(vi_good) is False
    # 셀렉터·응답언어 규칙
    assert clean_guard("vi") is looks_vietnamese_clean and clean_guard("ko") is looks_korean_clean
    assert "tiếng Việt" in response_language_rule("vi") and "한국어" in response_language_rule("ko")


def test_vi_model_config():
    from backend.app.core.config import get_settings
    s = get_settings()
    assert s.ollama_model_vi == "qwen3:14b" and s.ollama_refine_model_vi == "qwen3:14b"
    assert s.ollama_model == "qwen3:14b"   # ko 메인 엔진 qwen3 전환(saju 운영 2026-07-16)


def test_ko_chart_unchanged():
    # 전문가 만세력: 2026-06-09 10:48 → 丙午/甲午/甲寅/己巳 (test_saju_accuracy 와 동일)
    p = build_chart(BirthInput(birth_date=date(2026, 6, 9), birth_time=time(10, 48)),
                    with_daewoon=False).pillars
    got = (p.year.gz, p.month.gz, p.day.gz, p.hour.gz)
    assert got == ("丙午", "甲午", "甲寅", "己巳")

def test_pretty_readings_follow_locale():
    # 명식 출력의 간지 독음이 로케일을 따라간다 (2026-06-09 = 甲寅일: 甲 갑/Giáp, 寅 인/Dần)
    ko = build_chart(BirthInput(birth_date=date(2026, 6, 9), birth_time=time(10, 48), locale="ko"),
                     with_daewoon=False).pretty()
    vi = build_chart(BirthInput(birth_date=date(2026, 6, 9), birth_time=time(10, 48), locale="vi"),
                     with_daewoon=False).pretty()
    assert "甲(갑)" in ko and "寅(인)" in ko
    assert "甲(Giáp)" in vi and "寅(Dần)" in vi
    assert "甲(갑)" not in vi   # vi 출력에 한글 독음 병기는 없어야


def test_vi_chart_computes_valid_pillars():
    # vi 로케일도 간지(sxtwl 천문)는 정상 산출 — 양력 입력은 ko와 동일 명식
    vi = build_chart(BirthInput(birth_date=date(2026, 6, 9), birth_time=time(10, 48), locale="vi"),
                     with_daewoon=False).pillars
    ko = build_chart(BirthInput(birth_date=date(2026, 6, 9), birth_time=time(10, 48), locale="ko"),
                     with_daewoon=False).pillars
    assert (vi.year.gz, vi.month.gz, vi.day.gz, vi.hour.gz) == \
           (ko.year.gz, ko.month.gz, ko.day.gz, ko.hour.gz)
