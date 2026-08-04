"""주제 이탈(핵심 질문 이탈) 방지 로직 검증.

실측: 취업운 상담 직후 '남자친구 언제 생겨요?'에 답이 다시 취업으로 흐름. 원인은
초안 단계에 '지금 질문 주제 집중' 지시가 없던 것. 시스템 규칙(QUESTION_FOCUS_RULE)과
질문 직후 지시가 항상 들어가는지 순수 함수 단위로 검증한다(LLM 호출 없음).
"""
from __future__ import annotations

from backend.app.services import chat_service as cs


def test_compose_sys_includes_question_focus_rule():
    sys = cs._compose_sys_content("기본 시스템", dialect="standard", explain_level="normal")
    assert "[핵심 질문 집중" in sys
    assert "이어가지 말고" in sys
    # [2026-07-25] 연애 예시 지뢰 제거 후 신설된 '한 낱말 넘겨짚기 금지' 가드가 들어가는지 고정
    assert "넘겨짚어 다른 주제로 바꾸지 마세요" in sys
    # 규칙 본문에 연애 편중 예시('남자친구→연애·인연')를 다시 넣지 않았는지(동문서답 재발 방지)
    assert "남자친구는 언제 생길까요" not in sys


def test_user_prompt_focuses_on_current_question_and_is_last():
    out = cs._build_user_prompt("남자친구는 언제 생길까요?", [], None)
    assert "[지금 질문]" in out
    assert "남자친구는 언제 생길까요?" in out
    # 주제 집중 지시가 포함되고, 질문 블록이 맨 끝(최강 가중 위치)에 온다
    assert "지금 질문의 주제로만 새로 풀이" in out
    assert out.rstrip().endswith("이어서 답).")


def test_refine_systems_have_topic_and_date_guards():
    # 보강(qwen·Claude) 시스템에 주제집중 + 날짜/간지 가드가 모두 포함
    assert "[현재 질문 집중]" in cs._QWEN_REFINE_SYSTEM
    assert "[날짜·간지]" in cs._QWEN_REFINE_SYSTEM
    from backend.app.services import external_llm as ex
    assert "[현재 질문 집중]" in ex._REFINE_SYSTEM
    assert "계묘=癸卯" in ex._REFINE_SYSTEM
