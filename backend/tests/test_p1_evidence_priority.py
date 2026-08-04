# -*- coding: utf-8 -*-
"""P1: 자료 우선 층 분리 (RAG 전수감사 2026-07-22, 운영자 요구 'RAG가 우선되어야 함').

감사 결론: 프롬프트에서 '참고자료'가 나오는 곳이 **전부 금지·격하 문맥**이었고 우선 지침은
한 줄도 없었다. 그 결과 해석층은 규칙도 검증도 없이 '자료가 지배'하는 창발 상태였다.
→ 사실(값으로 제공된 계산값)은 계산값 절대우위, 해석·관법·시기론은 자료 우위로 명문화한다.
"""
from datetime import date

from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput
from backend.app.services import chat_service as C


class _Chunk:
    def __init__(self, source, text):
        self.source, self.text, self.chunk_id, self.score = source, text, 1, 0.61


def test_evidence_priority_rule_states_both_layers():
    r = C.EVIDENCE_PRIORITY_RULE
    assert "해석·관법" in r and "자료를 따르세요" in r          # 해석층 = 자료 우선
    assert "값으로 제공된 것" in r and "절대 바꾸지 마세요" in r  # 사실층 = 계산값 절대우위
    assert "그 사람 전용 판정" in r and "원리만" in r            # 타인 사례 전이 차단


def test_rag_block_always_carries_the_rule():
    blk = C.rag_context_block([_Chunk("u001.pdf", "재성과 인성이 합하면 계약운이 좋다.")])
    assert blk and "[자료1]" in blk
    assert C.EVIDENCE_PRIORITY_RULE in blk       # 자료를 주입하는 모든 경로가 같은 우선순위를 갖는다
    assert C.rag_context_block([]) is None


def test_chart_reconfirm_guard_available_for_all_menus():
    """chat 에만 있던 [명식 재확인] 가드를 tool·compat 이 함께 쓰도록 공용화(P1-4)."""
    cj = build_chart(BirthInput(birth_date=date(1990, 3, 21),
                                birth_time="09:30")).model_dump(mode="json")
    g = C.chart_reconfirm_block(cj)
    assert g and "[명식 재확인]" in g
    for pos in ("년주", "월주", "일주", "시주"):
        assert pos in g
    assert "다른 사람의 명식·간지가 있어도 쓰지 말고" in g
    assert C.chart_reconfirm_block(None) is None
    assert C.chart_reconfirm_block({}) is None


def test_expert_voice_no_longer_demotes_evidence():
    """'참고자료는 통달한 지식일 뿐'이라는 격하 문구를 제거 — 우선 지침과 정면 충돌했다."""
    assert "통달한 지식일 뿐" not in C.EXPERT_VOICE_RULE
    assert "감수를 거친 선생님 자료" in C.EXPERT_VOICE_RULE
    assert "자료에 의하면" in C.EXPERT_VOICE_RULE          # 출처 언급 금지(말투 규칙)는 유지


def test_compat_no_longer_contradicts_itself():
    """자료를 주입해 놓고 '이 근거에만 기반하라'던 정면 모순 해소(P1-3)."""
    from backend.app.services.compat_service import COMPAT_SYSTEM
    assert "이 근거에만 기반해 해설하세요" not in COMPAT_SYSTEM
    assert "간지·합충·신살·점수는 이 값만" in COMPAT_SYSTEM
    assert "[참고자료]가 있으면 그 자료를 우선 근거로" in COMPAT_SYSTEM


def test_active_system_prompt_scopes_the_no_quote_rule():
    """실제 활성 프롬프트는 template_service.DEFAULT_SYSTEM_PROMPT 다(chat_service.SYSTEM_PROMPT 아님).
    '출처 언급 금지'가 말투 규칙임을 명시해 자료 판단까지 버리지 않게 한다.

    [P3-E1 갱신] 자료 우선 지시는 **자료가 주어진 경우로 한정**한다 — 0건일 때도 무조건 붙으면
    없는 자료를 따르라는 유령 지시가 되어 근거를 지어낼 여지를 준다."""
    from backend.app.services.template_service import DEFAULT_SYSTEM_PROMPT as D
    assert "말투" in D and "자료를 따르되" in D
    assert "판단 자체는 따르세요" in D
    assert "주어진 경우" in D, "자료 우선 지시가 무조건문이면 0건일 때 환각을 부른다"
    assert "참고자료가 없으면" in D
