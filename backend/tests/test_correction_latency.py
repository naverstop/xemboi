# -*- coding: utf-8 -*-
"""교정 대기시간 단축 회귀 고정 (운영자 승인 2026-07-16, A+B / 2026-07-21 백스톱 제거 반영).

실측: '확인하는 중이에요' 장기대기의 진범은 검증 배터리(ms)가 아니라 교정 '재생성'
LLM 호출(비스트리밍, 긴 답변 회당 1~3분 × 종전 최대 2회). 승인안:
A) 게이트(_verify_myeongsik) 결과를 initial_bad로 전달 — 진입 직후 동일 배터리 중복 제거.
B) 재생성 max_tries 2→1.
C) [2026-07-21] 미해소 시 "※ 정확한 명식 지지" 백스톱 헤더 노출 제거 — 내부 진실값을
   고객 본문·PDF에 노출하던 문제. 미해소 불일치는 관리자 로그로만 남기고 본문은 유지.
"""
from __future__ import annotations

import inspect
from unittest.mock import patch

from backend.app.services import chat_service as C


def test_max_tries_default_is_one():
    """B — 재생성 기본 1회(최악 대기 절반). 2로 되돌리면 여기서 깨진다."""
    assert inspect.signature(C._correct_branches).parameters["max_tries"].default == 1
    assert inspect.signature(C._correct_chart).parameters["max_tries"].default == 1


def test_single_retry_no_header_exposure():
    """재생성 1회로 못 잡아도 백스톱 헤더를 고객 본문에 붙이지 않는다(로그만).

    [2026-07-22 교체 안전 게이트] 완결 문장으로 끝나는 재생성본만 교체 대상 — 미완결이면 원본 유지."""
    calls = {"n": 0}
    def fake(msgs, **kw):
        calls["n"] += 1
        return "재생성했지만 여전히 일지 사(巳)로 틀린 답변입니다."   # 완결 문장(게이트 통과형)
    with patch.object(C, "_call_ollama", fake):
        out = C._correct_branches(
            "당신의 일지 사(巳)는 이러합니다.", allowed={"day": {"亥"}}, truth="일지=해(亥)",
            question="q", sys_content="s", saju_summary=None,
            initial_bad=[("일지", "巳", "亥")])
    assert calls["n"] == 1                        # LLM 재생성 정확히 1회
    assert out == "재생성했지만 여전히 일지 사(巳)로 틀린 답변입니다."
    assert not out.startswith("※")                # 내부 진실값 헤더 미노출


def test_truncated_regen_rejected_keeps_original():
    """[교체 안전 게이트] 잘린 모양('**열림'·미완결)의 재생성본은 검증 통과 여부와 무관하게
    교체 거부 — 잘 나온 원본이 잘린 것으로 대체되던 실측 사고(신년운세 9월 절단) 재발 방지."""
    orig = ("완결된 원본 답변입니다. " * 80).strip() + " 마무리 조언까지 완결했습니다."
    with patch.object(C, "_call_ollama", lambda m, **k: "일지 해(亥)가 맞습니다만 **잘림"):
        out = C._correct_branches(
            orig + " 당신의 일지 사(巳)는 이러합니다.", allowed={"day": {"亥"}}, truth="t",
            question="q", sys_content="s", saju_summary=None,
            initial_bad=[("일지", "巳", "亥")])
    assert out.startswith("완결된 원본")           # 원본 유지(잘린 재생성본 폐기)


def test_initial_bad_skips_duplicate_battery():
    """A — 게이트가 '이상 없음'([])을 전달하면 재검증·재생성 없이 원문 즉시 반환."""
    calls = {"n": 0}
    def fake(msgs, **kw):
        calls["n"] += 1
        return "x"
    with patch.object(C, "_call_ollama", fake):
        out = C._correct_branches(
            "무해한 답변", allowed={"day": {"亥"}}, truth="t",
            question="q", sys_content="s", saju_summary=None, initial_bad=[])
    assert calls["n"] == 0 and out == "무해한 답변"


def test_successful_regen_no_backstop():
    """재생성이 성공(불일치 해소)하면 교정본 그대로(헤더 없음)."""
    with patch.object(C, "_call_ollama", lambda m, **kw: "교정된 답변 — 일지 해(亥)가 맞습니다"):
        out = C._correct_branches(
            "당신의 일지 사(巳)는…", allowed={"day": {"亥"}}, truth="일지=해(亥)",
            question="q", sys_content="s", saju_summary=None,
            initial_bad=[("일지", "巳", "亥")])
    assert "일지 해(亥)" in out and not out.startswith("※")


def test_monthly_flow_wolji_not_flagged():
    """[2026-07-21 오탐 가드] 월별 흐름 단락의 '월지 X'(월운 지지)는 명식 월지 오류로 잡지 않는다."""
    txt = "11월은 기해월로, 월지 해(亥)와 일지 인(寅)이 파 관계를 이루고 있어 주의가 필요합니다."
    bad = C._verify_branches(txt, {"month": {"卯"}, "day": {"寅"}})
    assert all(p != "월지" for (p, _, _) in bad)  # 11월=亥月 → 월운 서술로 인정


def test_real_wolji_error_still_flagged():
    """월 문맥이 없는 진짜 명식 월지 오류는 가드 후에도 검출된다."""
    txt = "당신의 월지 해(亥)는 지혜를 뜻합니다."
    bad = C._verify_branches(txt, {"month": {"卯"}})
    assert any(p == "월지" and c == "亥" for (p, c, _) in bad)
