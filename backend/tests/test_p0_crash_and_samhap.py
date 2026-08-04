# -*- coding: utf-8 -*-
"""P0 회귀 고정 — ①음력 대월 크래시 ②궁합 같은 일지 삼합 오판 (2026-07-16 전수감사).

① pillars.py: 음력 2/29·2/30을 그레고리력 date에 직대입 → ValueError.
   실측 크래시일 5일(2025-03-28, 2026-04-16, 2027-04-05·06, 2028-03-25) — 그 날짜가 낀
   택일 창 전체·당일 부적 발행이 죽었다. 기둥 계산과 무관한 표시용 음력일만 클램프.
② compatibility.py + chat_service.py(미러): 같은 일지는 1원소 frozenset이라 삼합그룹
   진부분집합 검사에 항상 걸려(12지 전원 삼합국 소속) '반합 78점' 오판 — 저장 점수·펜타곤 오염.
   두 곳 동시 가드 필수(한쪽만 고치면 교정 루프가 수정을 되돌림).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.app.saju.compatibility import _score_day_branch
from backend.app.saju.constants import EARTHLY_BRANCHES
from backend.app.saju.pillars import compute_pillars
from backend.app.saju.types import BirthInput, CalendarType
from backend.app.services.chat_service import _compat_day_relations

_CRASH_DAYS = ["2025-03-28", "2026-04-16", "2027-04-05", "2027-04-06", "2028-03-25"]


@pytest.mark.parametrize("s", _CRASH_DAYS)
def test_lunar_big_month_no_crash(s: str):
    """실측 크래시 5일 전부 정상 계산(음력 표시는 그 달 마지막 유효일로 클램프)."""
    y, m, d = map(int, s.split("-"))
    fp, _sd, _st, lunar_d, _leap = compute_pillars(
        BirthInput(birth_date=date(y, m, d), calendar=CalendarType.SOLAR))
    assert fp.day.stem and lunar_d.day >= 28


def test_full_year_scan_no_crash():
    """1년 전일 스캔 무크래시 불변식(향후 음력 경계 회귀 방지)."""
    d = date(2027, 1, 1)
    while d <= date(2027, 12, 31):
        compute_pillars(BirthInput(birth_date=d, calendar=CalendarType.SOLAR))
        d += timedelta(days=1)


def test_same_day_branch_is_dongji_not_samhap():
    """같은 일지 12종 전부 '동지 60점' — 반합(삼합) 오판 금지."""
    for b in EARTHLY_BRANCHES:
        f = _score_day_branch(b, b)
        assert f.score == 60, f"{b}{b}: {f.score}점"
        assert "삼합" not in f.items[0].type and "반합" not in f.items[0].type


def test_normal_pairs_unchanged():
    """정상 쌍 회귀 없음: 육합 92 · 반합 78 · 충 28."""
    assert _score_day_branch("午", "未").score == 92
    assert _score_day_branch("寅", "戌").score == 78
    assert "삼합" in _score_day_branch("寅", "戌").items[0].type
    assert _score_day_branch("子", "午").score == 28


def test_mirror_verifier_consistent():
    """chat_service 미러 검증기도 같은 일지를 '삼합'으로 판정하지 않는다(교정 루프 정합)."""
    cj = lambda br: {"pillars": {"day": {"stem": "甲", "branch": br}}}  # noqa: E731
    for b in EARTHLY_BRANCHES:
        rel = _compat_day_relations(cj(b), cj(b))
        assert rel.get("일지관계") != "삼합", f"{b}{b} 미러 오판"
    assert _compat_day_relations(cj("寅"), cj("戌")).get("일지관계") == "삼합"  # 정상쌍 유지
    assert _compat_day_relations(cj("子"), cj("丑")).get("일지관계") == "육합"
