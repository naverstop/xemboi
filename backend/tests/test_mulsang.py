# -*- coding: utf-8 -*-
"""물상 조합 사전 주입 — mulsang_block (명리전 원문 발췌의 결정적 선별).

명식에 실존하는 조합만, 성격·관계류 질문에만, 최대 2항목 발췌로 주입된다.
사전은 scripts/extract_mulsang.py 가 만든 data/rag/mulsang_pairs.json(244항목) 실물 사용.
"""
from __future__ import annotations

from backend.app.saju.mulsang import _excerpt, _load_pairs, mulsang_block

CHART = {"pillars": {"year": {"stem": "癸", "branch": "巳"}, "month": {"stem": "甲", "branch": "子"},
                     "day": {"stem": "甲", "branch": "戌"}, "hour": {"stem": "庚", "branch": "午"}}}


def test_dictionary_loaded_full():
    pairs = _load_pairs()
    assert len(pairs) == 244
    assert ("branch", "戌", "子") in pairs      # 일지↔월지 실존 조합
    assert ("stem", "甲", "甲") in pairs


def test_injects_for_personality_question():
    b = mulsang_block("이 사람 성격이 어떤가요?", CHART)
    assert b and "[명리전 물상" in b
    assert "일간↔월간" in b and "甲木에" in b and "甲木이" in b   # 일간 甲 + 월간 甲(2권 무공백 원문)
    assert "일지↔월지" in b                                     # 戌이 子를 만나면
    assert b.count("·") >= 2 and len(b) < 1400                  # 최대 2항목 캡


def test_no_injection_for_other_topics():
    assert mulsang_block("내년 매매운은 어떤가요?", CHART) is None   # 관법 룰 영역
    assert mulsang_block("오늘 뭐 먹을까요?", CHART) is None


def test_no_chart_safe():
    assert mulsang_block("성격이 어떤가요?", None) is None
    assert mulsang_block("성격이 어떤가요?", {"pillars": {}}) is None


def test_excerpt_sentence_boundary():
    t = "첫 문장이다. 둘째 문장이다. " + "셋째 문장 아주 길다" * 50
    e = _excerpt(t, 30)
    assert e.endswith("다.") and len(e) <= 30
