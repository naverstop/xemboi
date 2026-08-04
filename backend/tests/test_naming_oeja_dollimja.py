# -*- coding: utf-8 -*-
"""작명 확장 회귀 — 외자 이름·돌림자(항렬자) 고정·복성 처리.

[계기 2026-07-28] 운영자: '구씨 vs 구본씨' 2유형 확인 요청 → 외자 이름(구본式)과 돌림자 고정
(구+本+○ / 구+○+本)이 둘 다 미지원이었다. recommend_names 에 count·fixed_char/fixed_pos 추가.
복성(南宮·皇甫)은 종전부터 지원 — 회귀로 고정한다.
"""
from __future__ import annotations

from datetime import date, time

import pytest

from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput
from backend.app.saju import naming as N


@pytest.fixture(scope="module")
def chart():
    return build_chart(BirthInput(birth_date=date(1988, 8, 8), birth_time=time(9, 30)))


# ── ① 외자 이름(count=1) ───────────────────────────────────────────
def test_oeja_all_single_char(chart):
    cands = N.recommend_names("具", chart, count=1, top=20, gender="male")
    assert cands, "외자 후보가 비었습니다"
    assert all(len(c.given) == 1 for c in cands), "외자인데 이름이 1글자가 아님"


def test_oeja_suri_uses_phantom_stroke(chart):
    """외자는 4격을 허수 1로 계산 — 계산이 깨지지 않고 4격 등급 문자열이 4개다."""
    cands = N.recommend_names("具", chart, count=1, top=5, gender="male")
    for c in cands:
        assert len(c.suri_grade.split("·")) == 4


# ── ② 돌림자(항렬자) 고정(count=2) ─────────────────────────────────
def test_dollimja_back_fixed(chart):
    """뒤 고정: 구 + ○ + 本 → 모든 이름이 本으로 끝난다."""
    cands = N.recommend_names("具", chart, top=15, gender="male", fixed_char="本", fixed_pos=1)
    assert cands
    assert all(c.given.endswith("本") and len(c.given) == 2 for c in cands)
    # 자유 자리는 本이 아니어야(같은 글자 반복 금지)
    assert all(c.given[0] != "本" for c in cands)


def test_dollimja_front_fixed(chart):
    """앞 고정: 구 + 本 + ○ → 모든 이름이 本으로 시작한다."""
    cands = N.recommend_names("具", chart, top=15, gender="male", fixed_char="本", fixed_pos=0)
    assert cands
    assert all(c.given.startswith("本") and len(c.given) == 2 for c in cands)
    assert all(c.given[1] != "本" for c in cands)


def test_dollimja_ignored_for_oeja(chart):
    """외자(count=1)엔 돌림자 고정이 무의미 — 무시하고 1글자 후보를 낸다."""
    cands = N.recommend_names("具", chart, count=1, top=10, gender="male", fixed_char="本", fixed_pos=1)
    assert cands and all(len(c.given) == 1 for c in cands)


def test_dollimja_blank_falls_back_to_free(chart):
    """빈 문자열/공백 돌림자는 None 취급 — 일반 2자 자유작명."""
    cands = N.recommend_names("具", chart, top=8, gender="male", fixed_char="  ", fixed_pos=1)
    assert cands and all(len(c.given) == 2 for c in cands)


# ── ③ 복성(두 글자 성) 회귀 ─────────────────────────────────────────
def test_compound_surname_two_char_given(chart):
    cands = N.recommend_names("南宮", chart, top=8, gender="male")
    assert cands and all(len(c.given) == 2 for c in cands)


def test_compound_surname_dollimja(chart):
    """복성 + 돌림자 조합도 성립(남궁 + ○ + 本)."""
    cands = N.recommend_names("皇甫", chart, top=8, gender="female", fixed_char="本", fixed_pos=1)
    assert cands and all(c.given.endswith("本") for c in cands)


# ── ④ 기본(2자 자유) 회귀 — 기존 동작 불변 ───────────────────────────
def test_default_two_char_unchanged(chart):
    cands = N.recommend_names("具", chart, top=10, gender="male")
    assert cands and all(len(c.given) == 2 for c in cands)
    # 정상 경로는 길격 보장(_clean) — 상위 후보에 흉이 없어야 한다
    assert "흉" not in cands[0].suri_grade
