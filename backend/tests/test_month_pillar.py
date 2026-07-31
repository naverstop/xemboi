"""월주의 만세력 검증 — 절기(節) 경계 + 五虎遁(월간 결정 규칙).

규칙:
 - 월주의 지지는 절(節)을 경계로 한다 (입춘=寅月, 경칩=卯月, 청명=辰月, ...).
 - 월주의 천간은 五虎遁: 년간 + 지지인덱스 기반.
   甲己年 → 丙寅月, 乙庚年 → 戊寅月, 丙辛年 → 庚寅月, 丁壬年 → 壬寅月, 戊癸年 → 甲寅月
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.app.saju.constants import EARTHLY_BRANCHES, HEAVENLY_STEMS
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, Gender

# 년간 → 寅月 천간
OHODON_STEMS = {
    "甲": "丙", "己": "丙",
    "乙": "戊", "庚": "戊",
    "丙": "庚", "辛": "庚",
    "丁": "壬", "壬": "壬",
    "戊": "甲", "癸": "甲",
}


def _expected_month_stem(year_stem: str, month_branch: str) -> str:
    base = OHODON_STEMS[year_stem]
    # 寅을 0번으로 보고 인덱스 차
    branch_offset = (EARTHLY_BRANCHES.index(month_branch) - EARTHLY_BRANCHES.index("寅")) % 12
    return HEAVENLY_STEMS[(HEAVENLY_STEMS.index(base) + branch_offset) % 10]


@pytest.mark.parametrize(
    "birth_date",
    [
        date(1990, 3, 15),    # 卯月 (경칩 3/6 ~ 청명 4/5)
        date(2024, 5, 30),    # 巳月
        date(2024, 2, 5),     # 寅月 (입춘 2/4 직후)
        date(2024, 2, 3),     # 丑月 (입춘 전)
        date(2024, 12, 25),   # 子月 (대설 ~ 소한)
        date(2000, 8, 15),    # 申月
        date(1985, 7, 7),     # 小暑 직후 → 未月
        date(1977, 12, 25),   # 子月
        date(2010, 8, 8),     # 立秋 직후 → 申月
        date(1960, 6, 6),     # 芒種 직후 → 午月
    ],
)
def test_month_stem_follows_ohodon(birth_date: date):
    chart = build_chart(
        BirthInput(birth_date=birth_date, gender=Gender.MALE),
        with_daewoon=False,
    )
    expected = _expected_month_stem(chart.pillars.year.stem, chart.pillars.month.branch)
    assert chart.pillars.month.stem == expected, (
        f"{birth_date}: 년간 {chart.pillars.year.stem}, 월지 {chart.pillars.month.branch}, "
        f"기대 월간 {expected}, 실제 {chart.pillars.month.stem}"
    )


def test_lichun_month_branch():
    """입춘 이후는 寅月로 시작."""
    chart = build_chart(BirthInput(birth_date=date(2024, 2, 10), gender=Gender.MALE), with_daewoon=False)
    assert chart.pillars.month.branch == "寅"


def test_jingzhe_changes_month():
    """경칩(약 3/5) 이후는 卯月."""
    chart_before = build_chart(BirthInput(birth_date=date(2024, 3, 4), gender=Gender.MALE), with_daewoon=False)
    chart_after = build_chart(BirthInput(birth_date=date(2024, 3, 10), gender=Gender.MALE), with_daewoon=False)
    assert chart_before.pillars.month.branch == "寅"
    assert chart_after.pillars.month.branch == "卯"
