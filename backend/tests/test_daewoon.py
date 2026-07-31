"""대운 방향성 테스트.

규칙: 년간이 陽이면 男=順行 女=逆行, 년간이 陰이면 男=逆行 女=順行.
시작 나이는 출생일과 인접 절(節)의 거리 / 3.
"""
from __future__ import annotations

from datetime import date, time

import pytest

from backend.app.saju.constants import HEAVENLY_STEMS
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, Gender

# 양 천간: 甲, 丙, 戊, 庚, 壬 (인덱스 짝수)
YANG_STEMS = {"甲", "丙", "戊", "庚", "壬"}


def _is_yang(stem: str) -> bool:
    return stem in YANG_STEMS


@pytest.mark.parametrize(
    "birth_date, gender",
    [
        (date(1990, 3, 15), Gender.MALE),    # 庚午年(陽) 남자 → 順行
        (date(1990, 3, 15), Gender.FEMALE),  # 庚午年(陽) 여자 → 逆行
        (date(1985, 7, 7), Gender.MALE),     # 乙丑年(陰) 남자 → 逆行
        (date(1985, 7, 7), Gender.FEMALE),   # 乙丑年(陰) 여자 → 順行
        (date(2024, 5, 30), Gender.MALE),    # 甲辰年(陽) 남자 → 順行
        (date(2024, 5, 30), Gender.FEMALE),  # 甲辰年(陽) 여자 → 逆行
    ],
)
def test_daewoon_direction(birth_date: date, gender: Gender):
    chart = build_chart(BirthInput(birth_date=birth_date, birth_time=time(12, 0), gender=gender))
    assert chart.daewoon is not None
    yang_year = _is_yang(chart.pillars.year.stem)
    is_male = gender == Gender.MALE
    expected_forward = (yang_year and is_male) or (not yang_year and not is_male)
    actual_forward = chart.daewoon.direction == "forward"
    assert actual_forward == expected_forward, (
        f"{birth_date} {gender.value}: 년간 {chart.pillars.year.stem} "
        f"(양={yang_year}), 기대 forward={expected_forward}, 실제 {chart.daewoon.direction}"
    )


def test_daewoon_first_pillar_is_adjacent_to_month():
    """대운 첫 주는 월주의 다음(순행) 또는 이전(역행) 갑자."""
    chart = build_chart(BirthInput(birth_date=date(1990, 3, 15), birth_time=time(14, 30), gender=Gender.MALE))
    assert chart.daewoon is not None and chart.daewoon.entries
    month_gz = chart.pillars.month.gz  # 己卯
    first_gz = chart.daewoon.entries[0].pillar.gz
    month_stem_idx = HEAVENLY_STEMS.index(month_gz[0])
    first_stem_idx = HEAVENLY_STEMS.index(first_gz[0])
    if chart.daewoon.direction == "forward":
        assert (first_stem_idx - month_stem_idx) % 10 == 1
    else:
        assert (month_stem_idx - first_stem_idx) % 10 == 1


def test_daewoon_start_age_in_range():
    """시작 나이는 0 이상 10 미만."""
    chart = build_chart(BirthInput(birth_date=date(1990, 3, 15), birth_time=time(14, 30), gender=Gender.MALE))
    assert chart.daewoon is not None
    assert 0.0 <= chart.daewoon.start_age < 10.0
