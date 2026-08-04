# -*- coding: utf-8 -*-
"""Track B — 답변 전 사전 선택질문(애매질문 → 추정 대신 사용자에게 맥락 질문).

실측: "내년에 새 학교 vs 취업?"에 AI가 '고등학생으로 추정'하며 학업으로 편향. 전문가 지침:
애매하면 추정하지 말고 선택지를 물어라. reviewed:true 폼만 발동(뽀 감수 게이트), '[상담맥락]'이
붙은 재질문엔 다시 묻지 않는다.
"""
from __future__ import annotations

from backend.app.services import chat_service as C


def test_school_vs_job_triggers():
    """학교 vs 취업 애매질문 → career 선택폼 발동."""
    f = C._clarify_form("내년에 새로운 학교를 가는 운일까요? 아니면 취업하는 운일까요?")
    assert f and f["key"] == "career_school_vs_job"
    assert len(f["options"]) == 3 and f["skippable"] is True


def test_no_trigger_for_unambiguous():
    """무관/명확한 질문은 사전질문 없음."""
    assert C._clarify_form("올해 사업운 어때요") is None
    assert C._clarify_form("성격이 어떤가요") is None
    assert C._clarify_form("건강운 봐주세요") is None


def test_no_reask_when_context_present():
    """이미 '[상담맥락]'이 붙은 재질문엔 다시 묻지 않는다(무한루프 차단)."""
    q = "내년에 새 학교 가는 운? 아니면 취업?\n\n[상담맥락] 진학을 생각 중이에요"
    assert C._clarify_form(q) is None


def test_unreviewed_forms_inactive():
    """reviewed:false(뽀 감수 전) 폼은 발동하지 않는다."""
    # 직장/연애 폼은 초안(reviewed:false) — 발동 금지
    assert C._clarify_form("연애운 언제 인연이 생기나요") is None
    data = C._clarify_forms_data()
    keys = {f["key"] for f in data.get("forms", [])}
    assert "job_move_vs_new" in keys and "love_current_status" in keys  # 초안은 존재하되
    active = [f["key"] for f in data.get("forms", []) if f.get("reviewed")]
    assert active == ["career_school_vs_job"]  # 활성은 감수 완료본만


def test_empty_question():
    assert C._clarify_form("") is None
    assert C._clarify_form(None) is None
