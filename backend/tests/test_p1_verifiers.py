# -*- coding: utf-8 -*-
"""전수감사 P1 검증기 — 공망·대운방향·연도세운·궁합관계 (2026-07).

전부 결정적: gongmang/daewoon.direction/연도세운(compute_pillars)/두 일지·일간 관계(constants).
좁은 앵커로 오탐을 억제(수식어·부정문·목록 제외).
"""
from __future__ import annotations

from backend.app.services.chat_service import (
    _verify_compat_relations,
    _verify_daewoon_direction,
    _verify_gongmang,
    _verify_year_ganji,
)

CHART = {
    "gongmang": ["戌", "亥"],
    "daewoon": {"direction": "backward", "entries": [
        {"start_age": 5, "pillar": {"stem": "壬", "branch": "寅"}}]},
}


# ── 공망 ─────────────────────────────
def test_gongmang_wrong_flagged():
    assert len(_verify_gongmang("공망은 자·축입니다.", CHART)) == 1        # 실제 戌·亥
    assert len(_verify_gongmang("공망(子丑) 작용", CHART)) == 1


def test_gongmang_correct_passes():
    assert _verify_gongmang("공망은 술·해(戌·亥)입니다.", CHART) == []
    assert _verify_gongmang("공망 戌亥", CHART) == []


def test_gongmang_modifier_usage_skipped():
    # 1글자·수식어 용법은 불개입
    assert _verify_gongmang("화개가 공망이면 종교성이 강합니다.", CHART) == []
    assert _verify_gongmang("일지가 공망일 때", CHART) == []


# ── 대운 방향 ─────────────────────────────
def test_direction_wrong_flagged():
    assert len(_verify_daewoon_direction("귀하의 대운은 순행합니다.", CHART)) == 1   # 실제 역행


def test_direction_correct_passes():
    assert _verify_daewoon_direction("대운은 역행하며 대운수는 4.6세입니다.", CHART) == []


def test_direction_negation_and_other_luck_skipped():
    assert _verify_daewoon_direction("세운이 순행하는 흐름", CHART) == []       # 세운은 관할 아님
    assert _verify_daewoon_direction("대운이 순행이 아니라 역행입니다.", CHART) == []  # 부정문 skip


# ── 연도↔세운 ─────────────────────────────
def test_year_ganji_wrong_flagged():
    # 2027=정미인데 갑자로 오기
    bad = _verify_year_ganji("2027년 갑자(甲子)에는 큰 변화가 옵니다.")
    assert len(bad) == 1 and "정미" in bad[0][2]


def test_year_ganji_correct_passes():
    assert _verify_year_ganji("2027년 정미(丁未)년에는") == []


def test_year_ganji_non_ganji_and_past_skipped():
    assert _verify_year_ganji("2027년 3월에 만나요") == []       # 뒤가 간지 아님
    assert _verify_year_ganji("2020년 경자에 힘들었죠") == []     # 과거연도 skip(scrub 관할)


# ── 궁합 관계 ─────────────────────────────
# 子(A)·丑(B) 일지 = 육합 / 甲(A)·己(B) 일간 = 천간합
A = {"pillars": {"day": {"stem": "甲", "branch": "子"}}}
B = {"pillars": {"day": {"stem": "己", "branch": "丑"}}}


def test_compat_relation_wrong_flagged():
    # 실제 일지 육합인데 '충'으로 단정
    bad = _verify_compat_relations("두 분의 일지는 충으로 배우자궁 갈등이 있습니다.", A, B)
    assert len(bad) == 1 and bad[0][2] == "육합"


def test_compat_relation_correct_passes():
    assert _verify_compat_relations("일지가 육합이라 부부궁이 좋고, 일간도 천간합입니다.", A, B) == []


def test_compat_relation_negation_skipped():
    assert _verify_compat_relations("일지는 충이 아니라 육합입니다.", A, B) == []


def test_compat_no_relation_safe():
    # 관계 없는 두 명식이면 판정 없음
    C = {"pillars": {"day": {"stem": "甲", "branch": "寅"}}}
    D = {"pillars": {"day": {"stem": "丙", "branch": "巳"}}}
    assert _verify_compat_relations("일지가 충입니다.", C, D) == []
