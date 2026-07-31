"""년주의 만세력 검증 — 입춘(立春) 경계.

규칙: 사주의 년주는 양력 1월 1일이 아니라 입춘(약 2월 4일) 기준으로 바뀜.
검증: 같은 양력 연도라도 입춘 이전이면 직전 년주.

또한 60갑자 순환 테스트.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType, Gender


@pytest.mark.parametrize(
    "birth_date, expected_year_pillar",
    [
        # 입춘 경계 케이스 (입춘은 통상 2/4 전후, 시간 단위 정확도)
        # 2024년 입춘: 2024-02-04 16:27 KST
        # → 2024-02-04 자정~16:26 사이는 아직 직전 년주(癸卯)
        # → 입춘 시각 이후는 새 년주(甲辰)
        # 단순 일자 기준 테스트 (간략화: 입춘 익일은 확실히 새 년주)
        (date(2024, 2, 5), "甲辰"),     # 입춘 다음날
        (date(2024, 2, 3), "癸卯"),     # 입춘 전날
        (date(2024, 12, 31), "甲辰"),   # 연말도 같은 년주
        # 60갑자 한 바퀴(1924년 갑자년 → 1984년 갑자년)
        (date(1924, 3, 1), "甲子"),
        (date(1984, 3, 1), "甲子"),
        (date(2044, 3, 1), "甲子"),
        # 1990 庚午, 2000 庚辰, 2010 庚寅, 2020 庚子
        (date(1990, 6, 1), "庚午"),
        (date(2000, 6, 1), "庚辰"),
        (date(2010, 6, 1), "庚寅"),
        (date(2020, 6, 1), "庚子"),
        # 임진왜란 1592년 → 壬辰
        (date(1592, 6, 1), "壬辰"),
        # 1년차이 연속 확인
        (date(2023, 3, 1), "癸卯"),
        (date(2025, 3, 1), "乙巳"),
    ],
)
def test_year_pillar_lichun_boundary(birth_date: date, expected_year_pillar: str):
    chart = build_chart(
        BirthInput(birth_date=birth_date, calendar=CalendarType.SOLAR, gender=Gender.MALE),
        with_daewoon=False,
    )
    assert chart.pillars.year.gz == expected_year_pillar, (
        f"{birth_date}: 기대 년주 {expected_year_pillar}, 실제 {chart.pillars.year.gz}"
    )


def test_year_pillar_60_cycle():
    """60년 주기로 같은 년주가 반복."""
    base = build_chart(
        BirthInput(birth_date=date(1984, 6, 1), gender=Gender.MALE),
        with_daewoon=False,
    )
    later = build_chart(
        BirthInput(birth_date=date(2044, 6, 1), gender=Gender.MALE),
        with_daewoon=False,
    )
    assert base.pillars.year.gz == later.pillars.year.gz == "甲子"
