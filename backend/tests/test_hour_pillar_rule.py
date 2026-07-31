"""천간둔법(時干 계산) 일관성 테스트.

규칙: 日干(jia/yi/...)에 따라 子時의 天干이 결정됨 (五鼠遁).
  甲己日 → 甲子, 乙庚日 → 丙子, 丙辛日 → 戊子, 丁壬日 → 庚子, 戊癸日 → 壬子
이후 매 시간마다 천간/지지가 +1씩 순환.
"""
from __future__ import annotations

from datetime import date, time

import pytest

from backend.app.saju.constants import EARTHLY_BRANCHES, HEAVENLY_STEMS
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType, Gender

# 일간 → 子時 천간
JADON_STEMS = {
    "甲": "甲", "己": "甲",
    "乙": "丙", "庚": "丙",
    "丙": "戊", "辛": "戊",
    "丁": "庚", "壬": "庚",
    "戊": "壬", "癸": "壬",
}

# 자시(子)부터 해시(亥)까지의 시간 매핑 (시간 → 지지인덱스)
# 23:00~00:59 = 子, 01:00~02:59 = 丑, ...
HOUR_TO_BRANCH = {
    23: 0, 0: 0,
    1: 1, 2: 1,
    3: 2, 4: 2,
    5: 3, 6: 3,
    7: 4, 8: 4,
    9: 5, 10: 5,
    11: 6, 12: 6,
    13: 7, 14: 7,
    15: 8, 16: 8,
    17: 9, 18: 9,
    19: 10, 20: 10,
    21: 11, 22: 11,
}


def _expected_hour_pillar(day_stem: str, hour: int) -> tuple[str, str]:
    base_stem = JADON_STEMS[day_stem]
    branch_idx = HOUR_TO_BRANCH[hour]
    base_stem_idx = HEAVENLY_STEMS.index(base_stem)
    stem_idx = (base_stem_idx + branch_idx) % 10
    return HEAVENLY_STEMS[stem_idx], EARTHLY_BRANCHES[branch_idx]


@pytest.mark.parametrize(
    "birth_date, birth_time",
    [
        (date(1990, 3, 15), time(0, 30)),
        (date(1990, 3, 15), time(6, 0)),
        (date(1990, 3, 15), time(14, 30)),
        (date(1990, 3, 15), time(22, 30)),
        (date(2000, 1, 1), time(12, 0)),
        (date(2024, 5, 30), time(9, 0)),
        (date(1985, 7, 7), time(15, 45)),
        (date(1977, 12, 25), time(3, 0)),
        (date(2010, 8, 8), time(8, 8)),
        (date(1960, 6, 6), time(18, 30)),
    ],
)
def test_hour_pillar_follows_jadon_rule(birth_date: date, birth_time: time):
    """sxtwl의 시주 결과가 천간둔법(五鼠遁) 규칙과 일치하는지 검증."""
    chart = build_chart(
        BirthInput(
            birth_date=birth_date,
            birth_time=birth_time,
            calendar=CalendarType.SOLAR,
            gender=Gender.MALE,
        ),
        with_daewoon=False,
    )
    assert chart.pillars.hour is not None
    exp_stem, exp_branch = _expected_hour_pillar(chart.pillars.day.stem, birth_time.hour)
    assert chart.pillars.hour.stem == exp_stem, (
        f"{birth_date} {birth_time}: 일간 {chart.pillars.day.stem}, "
        f"기대 시간 {exp_stem}{exp_branch}, 실제 {chart.pillars.hour}"
    )
    assert chart.pillars.hour.branch == exp_branch
