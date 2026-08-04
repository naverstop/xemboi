# -*- coding: utf-8 -*-
"""개명(이름 진단)이 작명과 **동일한 로직·원리**로 동작하는지 고정.

배경: 작명은 전문가 지적으로 여러 차례 교정됐다(발음오행 관법, 자원/발음 분리, 인기이름 우선).
개명은 별도 경로(`analyze_name`)라 같은 교정이 새는지 매번 확인해야 했다. 이 테스트가 그 표류를 막는다.

의도적 차이(고정): 개명은 후보를 **생성**하지 않고 기존 이름을 **진단**하므로
  - allowlist(name_hanja.json) 하드게이트 적용 안 함  (남의 이름을 못 쓰는 글자라 하면 안 됨)
  - 흉격 필터 적용 안 함                                (흉격은 오히려 보고해야 함)
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.app.saju import naming as N
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType

_BIRTHS = [
    date(1990, 5, 5), date(1985, 11, 20), date(2001, 2, 14),
    date(1978, 8, 8), date(1996, 6, 30), date(2010, 1, 3),
]


def _chart(d: date):
    return build_chart(BirthInput(birth_date=d, calendar=CalendarType.SOLAR))


@pytest.mark.parametrize("d", _BIRTHS)
def test_same_targets_and_factors(d: date):
    """같은 사주면 개명·작명이 같은 목표오행과 같은 4팩터를 쓴다."""
    ch = _chart(d)
    baleum_t, jawon_t = N._naming_targets(ch)
    assert baleum_t and jawon_t
    assert ch.day_master_element not in baleum_t or baleum_t == jawon_t  # 발음=비겁 제외

    a = N.analyze_name("金", "志宇", ch, reading="김지우")
    assert set(a.factors) == {"suri", "jawon", "baleum", "eumyang"}
    # 관점 가중치도 작명과 동일 테이블
    assert set(a.perspectives) == set(N.PERSPECTIVES)


@pytest.mark.parametrize("d", _BIRTHS)
def test_two_elements_exposed_separately(d: date):
    """발음오행(초성)과 자원오행(부수)을 글자별로 분리 노출 — 전문가가 잡은 '도하' 혼동 재발 차단."""
    ch = _chart(d)
    a = N.analyze_name("金", "稲河", ch, reading="김도하")
    assert a.elements == ["금", "불명", "수"], a.elements          # 稲=부수 미매핑 → 억지 오행 금지
    assert a.baleum_elements == ["목", "화", "토"], a.baleum_elements  # 김ㄱ=목 도ㄷ=화 하ㅎ=토
    assert a.elements != a.baleum_elements


def test_baleum_score_uses_actual_reading():
    """발음오행 점수는 사전 독음이 아니라 **실제 독음**으로 계산.

    실측: _reading('稲')=='' 라 그 글자가 통째로 누락돼 '초성오행 토'만 나왔다.
    """
    ch = _chart(date(1990, 5, 5))
    _, _ = N._naming_targets(ch)
    a = N.analyze_name("金", "稲河", ch, reading="김도하")
    d = a.factors["baleum"].detail
    assert "화" in d and "토" in d, d  # 도(火)·하(土) 둘 다 반영
    assert "판별 불가" not in d


def test_damum_hanja_reading_respected():
    """다음(多音) 한자: 辰 사전음 '신' 이어도 사용자가 '진'이면 그 초성(ㅈ=금)으로 본다."""
    assert N._reading("辰") == "신"
    ch = _chart(date(1990, 5, 5))
    a = N.analyze_name("宋", "辰秀", ch, reading="송진수")
    assert a.reading == "송진수"
    assert a.baleum_elements == ["금", "금", "금"], a.baleum_elements


@pytest.mark.parametrize("d", _BIRTHS)
def test_diagnosis_does_not_hide_bad_grades(d: date):
    """진단은 흉격을 숨기지 않는다(작명의 흉격 필터를 개명에 끌어오면 안 됨)."""
    a = N.analyze_name("金", "敏準", _chart(d), reading="김민준")
    assert 0 <= a.factors["suri"].score <= 100
    assert a.factors["suri"].detail  # 4격 길흉이 그대로 서술


def test_analyze_accepts_hanja_outside_allowlist():
    """allowlist(작명 생성용)를 개명 진단에 적용하면 남의 이름이 거부된다 — 그러면 안 된다."""
    pool = set()
    for chars in N._name_hanja().get("syllables", {}).values():
        pool.update(chars)
    assert "稲" not in pool  # 생성 풀 밖 글자
    a = N.analyze_name("金", "稲河", _chart(date(1990, 5, 5)), reading="김도하")
    assert a.name == "金稲河"  # 그래도 진단은 정상 수행
