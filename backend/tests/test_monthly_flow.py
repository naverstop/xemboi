# -*- coding: utf-8 -*-
"""월별 흐름 — 월운 '년'오표기 교정 + 내년 질문의 연도 스코프 (2026-07 실측).

실측: ①'7월 (을미년)' — 월운 간지를 '년'으로 오표기(을미월이 맞음) ②'내년 매수운 몇월'인데
올해 월별로 답함. 둘 다 결정적으로 교정: 출력단 년→월 라벨 교정 + 상대연도 감지로 그 해 월 제공.
"""
from __future__ import annotations

import re

from backend.app.services.chat_service import (
    _current_luck_block,
    _fix_month_ganji_label,
    _months_of_year,
    _target_year_offset,
)


# ── 년→월 라벨 교정 ─────────────────────────────
def test_month_label_year_to_month():
    assert _fix_month_ganji_label("• 7월 (을미년): 협업 기회") == "• 7월 (을미월): 협업 기회"
    assert _fix_month_ganji_label("8월 병신년 직업운") == "8월 병신월 직업운"
    assert _fix_month_ganji_label("12월(경자년)") == "12월(경자월)"


def test_month_label_preserves_real_year():
    # 월 헤딩이 아닌 '세운 년' 표기는 보존
    assert _fix_month_ganji_label("올해는 병오년입니다") == "올해는 병오년입니다"
    assert _fix_month_ganji_label("내년 정미년에는") == "내년 정미년에는"
    # 'N월' 뒤라도 구분자 밖(문장)은 불개입 — '7월에 계사년생을 만나'
    assert _fix_month_ganji_label("7월에 계사년생을 만나") == "7월에 계사년생을 만나"


# ── 상대연도 스코프 ─────────────────────────────
def test_target_year_offset():
    assert _target_year_offset("내년에 매수운 몇월이 좋아요") == 1
    assert _target_year_offset("후년 이사운") == 2
    assert _target_year_offset("올해 매수운") == 0
    assert _target_year_offset("매수운 어때요") == 0


def test_months_of_year_full_12():
    ms = _months_of_year(2027)
    assert len(ms) == 12 and ms[0][0] == 2027 and ms[0][1] == 1
    assert all(g.endswith("月)") and "월(" in g for (_, _, g) in ms)   # 월 표기


def test_next_year_question_uses_next_year_months():
    blk = _current_luck_block(question="내년에 매수운 알아보고 싶어요 몇월이 좋은지")
    m = re.search(r"\[월별 간지[^\]]*\]", blk)
    assert m and "내년" in m.group(0)
    # 올해 질문은 '이번 달부터'
    blk2 = _current_luck_block(question="올해 매수운 어때요")
    m2 = re.search(r"\[월별 간지[^\]]*\]", blk2)
    assert m2 and "이번 달부터" in m2.group(0)
