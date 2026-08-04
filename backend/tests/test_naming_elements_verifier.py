# -*- coding: utf-8 -*-
"""자원오행·발음오행 값 대조 검증기 (전수감사 2026-07-22: 작명·아호 4런 중 3런 오답).

실측 오류 유형: 순서 반전 / 자원↔발음 칸 뒤섞기 / 통째 오답.
두 오행은 엔진이 확정 계산하므로 답변의 재서술을 그대로 대조한다.
"""
from backend.app.services.tool_service import _verify_naming_elements as V

AHO = {"kind": "aho", "candidates": [
    {"given": "賢雨", "reading": "현우", "elements": ["금", "수"], "baleum_elements": ["토", "토"]},
    {"given": "知準", "reading": "지준", "elements": ["금", "수"], "baleum_elements": ["금", "금"]},
]}
GAE = {"kind": "gaemyeong", "analysis": {
    "name": "金民秀", "reading": "김민수",
    "elements": ["금", "화", "목"], "baleum_elements": ["목", "수", "금"]}}


def test_inline_comparison_form_detected():
    """'- **賢雨(현우)**: … **발음오행이 수와 토로만 구성**' (표는 토·토)."""
    bad = V("- **賢雨(현우)**: 훌륭함과 비를 결합해 **발음오행이 수와 토로만 구성**되어 부족하다.", AHO)
    assert bad and bad[0][0] == "賢雨 발음오행" and bad[0][1] == "수·토" and bad[0][2] == "토·토"


def test_labeled_form_and_correct_values_pass():
    """'**발음오행**: 金·金 — …'는 知準의 표 값과 같으므로 통과해야 한다(오탐 방지)."""
    assert V("### 추천 1: 知準(지준)\n**자원오행**: 金·水 — 부족오행을 반영합니다.\n"
             "**발음오행**: 金·金 — '지'는 금을, '준'은 금을 나타냅니다.", AHO) == []


def test_quoted_pair_form_detected():
    """라벨 없이 글자마다 말하는 형태 — 키가 한글이면 발음오행으로 본다."""
    bad = V("- **賢雨(현우)**: '현'은 '수'를, '우'는 '토'를 포함하여 부족합니다.", AHO)
    assert bad and bad[0][0] == "賢雨 발음오행" and bad[0][2] == "토·토"


def test_gaemyeong_bold_paren_form_detected():
    """개명은 '**金(금)**은 **금(金)** 오행' 형식. 표 자원 금·화·목인데 금·목·수라 씀."""
    bad = V("현재 이름 **金民秀(김민수)**를 봅니다.\n"
            "자원오행은 한자의 부수로 판단합니다. **金(금)**은 **금(金)** 오행, "
            "**民(민)**은 **목(木)** 오행, **秀(수)**는 **수(水)** 오행에 해당합니다.", GAE)
    assert bad and bad[0][0] == "金民秀 자원오행"
    assert bad[0][1] == "금·목·수" and bad[0][2] == "금·화·목"


def test_no_data_or_ambiguous_is_not_flagged():
    """표가 없거나 개수가 안 맞으면 불개입 — 잘못된 재생성을 부르지 않는다."""
    assert V("아무 내용", {"kind": "aho", "candidates": []}) == []
    assert V("", AHO) == []
    # 값 개수가 표와 다르면(부분 인용) 판단하지 않는다
    assert V("- **賢雨(현우)**: 발음오행이 토로 구성된다.", AHO) == []
