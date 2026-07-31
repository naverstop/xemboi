"""대운(大運) 계산.

규칙:
 - 순행/역행: (양년 남자) 또는 (음년 여자) → 순행. (양년 여자) 또는 (음년 남자) → 역행.
 - 대운수: 출생일에서 다음 절기까지(순행) 또는 직전 절기까지(역행)의 일수를 3으로 나눔 (3일=1년)
 - 시작 천간/지지: 월주를 기준으로 순행이면 +1, 역행이면 -1 씩 진행
"""
from __future__ import annotations

from datetime import date, datetime

import sxtwl

from .constants import (
    EARTHLY_BRANCHES,
    HEAVENLY_STEMS,
    STEM_IS_YANG,
)
from .types import Daewoon, DaewoonEntry, FourPillars, Gender, Pillar


def _previous_and_next_jieqi(solar_d: date) -> tuple[datetime, datetime]:
    """주어진 양력일 직전/직후 절(節) 시각 반환.

    sxtwl.getJieQiByYear(year) 는 해당 연도의 24절기를 시간순으로 반환하며,
    각 항목은 .jd (율리우스일) 와 .jqIndex 를 가진다.
    24절기 순서(0부터): 冬至, 小寒, 大寒, 立春, 雨水, 驚蟄, 春分, 清明, 穀雨,
                      立夏, 小滿, 芒種, 夏至, 小暑, 大暑, 立秋, 處暑, 白露,
                      秋分, 寒露, 霜降, 立冬, 小雪, 大雪
    → 홀수 인덱스(1,3,5,...,23)가 12개 절(節). 대운 계산에 사용.
    """
    candidates: list[datetime] = []
    for y in (solar_d.year - 1, solar_d.year, solar_d.year + 1):
        for jq in sxtwl.getJieQiByYear(y):
            if jq.jqIndex % 2 == 0:        # 짝수=중기 → 건너뜀
                continue
            t = sxtwl.JD2DD(jq.jd)
            candidates.append(
                datetime(int(t.Y), int(t.M), int(t.D), int(t.h), int(t.m), int(t.s))
            )
    candidates.sort()
    target = datetime(solar_d.year, solar_d.month, solar_d.day)
    prev = max((c for c in candidates if c <= target), default=candidates[0])
    nxt = min((c for c in candidates if c > target), default=candidates[-1])
    return prev, nxt


def compute_daewoon(
    pillars: FourPillars,
    gender: Gender,
    solar_d: date,
    n_entries: int = 9,
) -> Daewoon:
    year_stem = pillars.year.stem
    is_year_yang = STEM_IS_YANG[year_stem]
    is_male = gender == Gender.MALE
    # 순행 조건
    forward = (is_year_yang and is_male) or (not is_year_yang and not is_male)
    direction = "forward" if forward else "backward"

    prev_jq, next_jq = _previous_and_next_jieqi(solar_d)
    birth_dt = datetime(solar_d.year, solar_d.month, solar_d.day)
    if forward:
        delta_days = (next_jq - birth_dt).total_seconds() / 86400.0
    else:
        delta_days = (birth_dt - prev_jq).total_seconds() / 86400.0
    start_age = round(delta_days / 3.0, 2)   # 3일 = 1년

    # 시작 인덱스: 월주에서 시작
    start_stem_i = HEAVENLY_STEMS.index(pillars.month.stem)
    start_branch_i = EARTHLY_BRANCHES.index(pillars.month.branch)

    step = 1 if forward else -1
    entries: list[DaewoonEntry] = []
    for k in range(1, n_entries + 1):
        si = (start_stem_i + step * k) % 10
        bi = (start_branch_i + step * k) % 12
        entries.append(
            DaewoonEntry(
                start_age=int(round(start_age + (k - 1) * 10)),
                pillar=Pillar(stem=HEAVENLY_STEMS[si], branch=EARTHLY_BRANCHES[bi]),
                direction=direction,
            )
        )

    return Daewoon(direction=direction, start_age=start_age, entries=entries)
