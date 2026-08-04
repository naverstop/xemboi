# -*- coding: utf-8 -*-
"""특정 주제 질문 → 집중 답변 결정적 라우팅 (동문서답 차단, 2026-07 실측).

실측: '내년 이직운 몇월'을 물었는데 성격·육친·건강 종합 템플릿으로 답함. ANSWER_BASE_RULE이
질문 종류 무관하게 항상 주입돼 약한 LLM이 큰 템플릿에 이끌린 것. 특정 주제를 결정적으로 감지해
종합 템플릿 대신 집중 규칙을 준다.
"""
from __future__ import annotations

from backend.app.services.chat_service import (
    ANSWER_BASE_RULE,
    _compose_sys_content,
    _focused_topic_labels,
)


def test_specific_topics_detected():
    assert _focused_topic_labels("내년에 이직운 알아보고 싶어요 좋다면 몇월이 좋은지") == ["직업·이직"]
    assert _focused_topic_labels("결혼은 언제쯤 할까요?") == ["연애·결혼"]
    assert _focused_topic_labels("건강이 걱정돼요") == ["건강"]
    assert _focused_topic_labels("매매운 있나요") == ["계약·매매"]


def test_general_stays_comprehensive():
    assert _focused_topic_labels("올해 운세 어때요?") == []
    assert _focused_topic_labels("제 사주 전체적으로 봐주세요") == []
    assert _focused_topic_labels("사주 종합적으로 풀이해줘") == []
    # 특정 주제어가 섞여도 '전체' 마커가 있으면 종합
    assert _focused_topic_labels("연애랑 건강 등 전체적으로 다 봐주세요") == []


def test_compose_swaps_template_for_focused():
    # 특정 주제 → 집중 규칙 주입, 종합 템플릿(ANSWER_BASE_RULE) 미포함
    focused = _compose_sys_content("SYS", None, "normal", question="이직운 몇월이 좋아요?")
    assert "집중 답변" in focused and "성격 총평으로 시작하지" in focused
    assert ANSWER_BASE_RULE not in focused
    # 일반 질문 → 종합 템플릿 유지
    general = _compose_sys_content("SYS", None, "normal", question="올해 운세 어때요?")
    assert ANSWER_BASE_RULE in general


def test_no_question_defaults_comprehensive():
    # 질문 미전달(하위호환) → 종합 유지
    assert ANSWER_BASE_RULE in _compose_sys_content("SYS", None, "normal")


def test_followup_defaults_focused():
    # 실측: 추가질문 '스트레스 관리법'에 월별 재물운까지 주저리 → 추가질문은 기본 집중
    q = "내면의 예민함을 조절하고 스트레스를 관리하는 방법은 무엇인가요?"
    fu = _compose_sys_content("SYS", None, "normal", question=q, is_followup=True)
    assert "추가질문 — 집중" in fu and ANSWER_BASE_RULE not in fu
    # 같은 질문이 첫 풀이면 종합 유지
    first = _compose_sys_content("SYS", None, "normal", question=q, is_followup=False)
    assert ANSWER_BASE_RULE in first


def test_followup_comprehensive_when_explicitly_asked():
    # 추가질문이라도 '올해 운세/월별/전체'를 콕 집으면 종합·월별 편다
    for q in ["올해 운세는 어때요?", "월별 흐름 알려줘", "전체적으로 다시 정리해줘", "몇 월이 좋아요?"]:
        c = _compose_sys_content("SYS", None, "normal", question=q, is_followup=True)
        assert ANSWER_BASE_RULE in c or "집중 답변 — 특정" in c, q
        assert "추가질문 — 집중" not in c, q


# ---- 성향·행실 질문 라우팅 (2026-07-25 동문서답 '남자 술주정있을까요' 실측) ----
# 종전엔 '술주정·주사·바람기' 등 행실 표현이 어느 키워드에도 안 걸려 route=[]→ 연애로 튀었다.
def test_behavior_trait_topics_detected():
    for q in ["남자 술주정있을까요", "술버릇 있나요", "주사 심한가요", "음주 문제 있을까요",
              "바람기 있나요", "폭력적인가요", "성실한가요", "게으른 편인가요",
              "고집 센가요", "거짓말 잘하나요", "씀씀이 어때요", "효자인가요"]:
        assert _focused_topic_labels(q) == ["성격·성향"], q


def test_behavior_trait_no_false_collisions():
    # 부분문자열 오탐 점검 — '기술/미술/예술/수술'이 성격으로 새면 안 됨
    assert "성격·성향" not in _focused_topic_labels("기술을 배우면 좋을까요")
    assert "성격·성향" not in _focused_topic_labels("미술 전공 어때요")
    assert "성격·성향" not in _focused_topic_labels("예술적 재능 있나요")
    assert _focused_topic_labels("수술 받을 일 있나요") == ["건강"]  # 수술=건강, 성격 아님


# ---- P4(#8): 집중·비종합후속은 서식 완화(3문장·마무리 필수 해제), 종합/첫풀이는 유지 ----
_RELAX = "서식 완화 — 짧고 집중"


def test_style_relax_applied_to_concise():
    # 집중(특정 주제) — 완화 적용
    assert _RELAX in _compose_sys_content("SYS", None, "normal", question="올해 이직운 어때")
    # 비종합 추가질문 — 완화 적용
    assert _RELAX in _compose_sys_content("SYS", None, "normal", question="그럼 건강은?", is_followup=True)


def test_style_relax_not_applied_to_comprehensive():
    # 종합 첫 풀이 — 완화 미적용(전체 풀이는 3문장·### 마무리 유지)
    assert _RELAX not in _compose_sys_content("SYS", None, "normal", question="내 사주 전체적으로 봐줘")
    # 종합 요청 추가질문 — 완화 미적용(월별/전체는 펼침)
    assert _RELAX not in _compose_sys_content("SYS", None, "normal", question="올해 전체 운세 다시", is_followup=True)


def test_focused_structure_rule_has_formatting():
    from backend.app.services.chat_service import _focused_structure_rule
    r = _focused_structure_rule(["직업·이직"])
    assert "**굵게**" in r and ("소제목" in r or "불릿" in r)
