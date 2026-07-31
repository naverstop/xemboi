# -*- coding: utf-8 -*-
"""윤달(閏月) 음→양력 변환·검증 회귀 테스트(감사 R4).

핵심: 윤달은 '음→양력 변환'에만 영향(사주는 절기·양력 기준). 같은 음력일이라도 평달/윤달이면
양력일이 약 한 달 차이 → 명식이 달라야 정상. 없는 윤달은 명시 오류, 양력+윤달은 정규화.
"""
from datetime import date

import pytest

from backend.app.saju.pillars import compute_pillars
from backend.app.saju.types import BirthInput, CalendarType


def _calc(y: int, m: int, d: int, leap: bool, cal: CalendarType = CalendarType.LUNAR):
    bi = BirthInput(birth_date=date(y, m, d), calendar=cal, is_leap_month=leap)
    fp, solar_d, _t, _lunar, is_leap = compute_pillars(bi)
    return solar_d, fp, is_leap


def test_leap_vs_regular_2020_yun4():
    """2020년 윤4월 실재 — 음력 4/15 평달 vs 윤달: 양력 약 30일·月柱·日柱 달라야."""
    solar_reg, fp_reg, _ = _calc(2020, 4, 15, False)
    solar_leap, fp_leap, leap_flag = _calc(2020, 4, 15, True)
    assert solar_reg == date(2020, 5, 7)
    assert solar_leap == date(2020, 6, 6)
    assert leap_flag is True
    assert fp_reg.month.gz != fp_leap.month.gz      # 月柱 다름
    assert fp_reg.day.gz != fp_leap.day.gz          # 日柱 다름


def test_leap_vs_regular_2023_yun2():
    """2023년 윤2월 실재 — 윤달은 평달 다음 달로 양력 한 달 뒤 매핑."""
    solar_reg, _, _ = _calc(2023, 2, 10, False)
    solar_leap, _, _ = _calc(2023, 2, 10, True)
    assert solar_reg == date(2023, 3, 1)
    assert solar_leap == date(2023, 3, 31)


def test_nonexistent_leap_raises():
    """그 해·월에 윤달이 없으면(2021년 윤4월 없음) 무경고 평달폴백 대신 명시 오류(R1).
    Pydantic ValidationError 는 ValueError 서브클래스라 엔드포인트 except ValueError → 400."""
    with pytest.raises(ValueError) as ei:
        BirthInput(birth_date=date(2021, 4, 15), calendar=CalendarType.LUNAR, is_leap_month=True)
    assert "윤달이 없습니다" in str(ei.value)


def test_solar_with_leap_is_coerced():
    """양력+윤달 모순 입력 → 거부(422) 대신 leap=False 정규화(R2/R3 근본차단)."""
    bi = BirthInput(birth_date=date(1986, 10, 8), calendar=CalendarType.SOLAR, is_leap_month=True)
    assert bi.is_leap_month is False
    # 정규화 후 정상 계산되어야(에러 없음)
    _fp, solar_d, *_ = compute_pillars(bi)
    assert solar_d == date(1986, 10, 8)


def test_ten_gods_yukchin_differ_by_leap():
    """윤달로 십성(→육친)이 달라짐 = 성격·육친 해석이 달라지는 근거. 육친 매핑이 십성을 커버."""
    from datetime import time

    from backend.app.saju.constants import TEN_GODS_YUKCHIN
    from backend.app.saju.engine import build_chart

    def chart(leap: bool):
        return build_chart(BirthInput(birth_date=date(2020, 4, 15), calendar=CalendarType.LUNAR,
                                      is_leap_month=leap, birth_time=time(10, 30)))
    c0, c1 = chart(False), chart(True)
    assert c0.ten_gods.month_stem != c1.ten_gods.month_stem   # 윤달로 월간 십성 달라짐
    for tg in (c0.ten_gods.month_stem, c1.ten_gods.month_stem):
        assert tg in TEN_GODS_YUKCHIN                         # 매핑표가 모든 십성 커버
