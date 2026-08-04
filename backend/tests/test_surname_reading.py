# -*- coding: utf-8 -*-
"""성(姓) 독음 보정 (전수감사 2026-07-22).

사용자가 reading 을 안 보내면 한자사전 대표음이 그대로 쓰여 유료 개명 리포트에
이름이 잘못 찍혔다(金民秀 → '금민수'). 더 중요한 건 초성이 달라져 **발음오행까지 오염**되는
것이다(李: 리=ㄹ 화 / 이=ㅇ 토). 성씨 사전으로 보정한다.
"""
from datetime import date

from backend.app.saju import naming as N
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput

CHART = build_chart(BirthInput(birth_date=date(1990, 3, 21)))


def test_surname_reading_uses_surname_dictionary():
    assert N.surname_reading("金") == "김"      # 대표음 '금' → 통용 성씨음 '김'
    assert N.surname_reading("李") == "이"      # 대표음 '리'
    assert N.surname_reading("車") == "차"      # 대표음 '거'
    assert N.surname_reading("南宮") == "남궁"  # 복성 — 대표음은 빈 문자열이었다
    assert N.surname_reading("朴") == "박"
    assert N.surname_reading("羅") == "나"      # 중의(나/라) → 통용 표기


def test_analyze_name_reading_and_baleum_fixed():
    a = N.analyze_name("金", "民秀", CHART)
    assert a.reading == "김민수"
    b = N.analyze_name("李", "敏浩", CHART)
    assert b.reading == "이민호"
    assert b.baleum_elements[0] == "토"          # '이'=ㅇ 토 (종전 '리'=ㄹ 화로 오염)
    c = N.analyze_name("南宮", "民秀", CHART)
    assert c.reading == "남궁민수" and len(c.baleum_elements) == 4


def test_explicit_reading_still_wins():
    """사용자가 보낸 독음(다음자 등)은 계속 최우선."""
    assert N.analyze_name("金", "民秀", CHART, reading="김민수").reading == "김민수"
    assert N.analyze_name("辰", "秀", CHART, reading="신수").reading == "신수"
