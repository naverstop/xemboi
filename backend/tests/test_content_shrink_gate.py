# -*- coding: utf-8 -*-
"""검증/교정 후 유료 답변 급삭감 차단(운영자 지적 #7 '검증하면서 내용이 확 줄어든다').

두 누수를 막는다:
- _safe_replace 의 '원본<800자→0.6 완화'가 교정(0.85)·보강(0.9/1.0)을 조용히 무력화 → hard_floor.
- _correct_nonresponsive(동문서답 교정)가 게이트 없이 80자 하한만 있어 긴 답을 짧게 통째 교체 → 삭감 게이트.
"""
from __future__ import annotations

import backend.app.services.chat_service as C


def _para(n: int) -> str:
    base = "당신은 성실하고 책임감 있는 분이며 올해는 재물운이 좋고 인간관계도 원만합니다. "
    return (base * (n // len(base) + 1))[:n].rstrip() + " 좋은 흐름이 이어지겠습니다."


# ── hard_floor: 짧은 원본 완화 차단 ────────────────────────────────
def test_hard_floor_blocks_short_original_relax():
    o = _para(600)          # 800자 미만
    c = _para(400)          # 33% 삭감
    # 종전(완화): min_ratio=0.85 여도 원본<800이면 0.6로 낮춰져 통과됐다
    assert C._safe_replace(o, c, min_ratio=0.85) is not None            # 완화 경로(하위호환)
    # hard_floor: 0.85 그대로 강제 → 33% 삭감 거부
    assert C._safe_replace(o, c, min_ratio=0.85, hard_floor=True) is None
    # 소폭(5%)은 hard_floor 여도 통과
    assert C._safe_replace(o, _para(570), min_ratio=0.85, hard_floor=True) is not None


def test_hard_floor_boost_must_not_shrink():
    o = _para(500)
    # 분량보강(1.0)은 짧은 원본에서도 '더 길 때만' — 짧은 후보 거부
    assert C._safe_replace(o, _para(450), min_ratio=1.0, hard_floor=True) is None
    assert C._safe_replace(o, _para(620), min_ratio=1.0, hard_floor=True) is not None


def test_strict_callers_use_hard_floor():
    """교정/보강/분량보강 호출부가 hard_floor 없이 다시 느슨해지지 않도록 소스 고정."""
    import io, pathlib
    base = pathlib.Path(__file__).resolve().parents[1] / "app" / "services"
    src = io.open(base / "chat_service.py", encoding="utf-8").read()
    assert "min_ratio=0.85, hard_floor=True" in src, "교정(0.85) hard_floor 누락"
    assert src.count("min_ratio=0.9, hard_floor=True") >= 3, "보강(0.9) hard_floor 3곳 유지"
    assert "min_ratio=1.0, hard_floor=True" in src, "분량보강(1.0) hard_floor 누락"
    tsrc = io.open(base / "tool_service.py", encoding="utf-8").read()
    csrc = io.open(base / "compat_service.py", encoding="utf-8").read()
    assert "min_ratio=1.0, hard_floor=True" in tsrc and "min_ratio=1.0, hard_floor=True" in csrc


# ── _correct_nonresponsive: 급삭감 거부 ───────────────────────────
def test_nonresponsive_rejects_drastic_shrink(monkeypatch):
    long_ans = _para(1500)   # 긴 유료 답변(>=500 → rich)
    # 원본만 동문서답으로 판정, 재생성본은 통과(주제 교정됨)로 가정
    monkeypatch.setattr(C, "_verify_nonresponsive",
                        lambda ans, q: [("q", "연애운")] if ans == long_ans else [])
    monkeypatch.setattr(C, "_build_user_prompt", lambda *a, **k: "USER")
    # 80자는 넘지만 원본의 0.7배(1050)에 못 미치는 짧은 재생성(200자)
    monkeypatch.setattr(C, "_call_ollama", lambda *a, **k: "다" * 200)
    out = C._correct_nonresponsive(long_ans, "연애운 어때?", sys_content="S",
                                   saju_summary=None, chart_json=None)
    assert out == long_ans, "긴 원본을 짧은 재생성본으로 교체하면 안 됨(원본 보존)"


def test_nonresponsive_accepts_adequate_length(monkeypatch):
    long_ans = _para(1500)
    monkeypatch.setattr(C, "_verify_nonresponsive",
                        lambda ans, q: [("q", "연애운")] if ans == long_ans else [])
    monkeypatch.setattr(C, "_build_user_prompt", lambda *a, **k: "USER")
    good = _para(1250)       # 0.7*1500=1050 이상 → 분량 유지된 교정본
    monkeypatch.setattr(C, "_call_ollama", lambda *a, **k: good)
    out = C._correct_nonresponsive(long_ans, "연애운 어때?", sys_content="S",
                                   saju_summary=None, chart_json=None)
    assert out == good, "분량 유지된 정당한 교정본은 채택돼야 함"


def test_nonresponsive_rejects_truncated(monkeypatch):
    # [P2 2026-07-29] 길이는 넘어도 문장 중간에 끊긴(잘린) 재생성본은 거부(_looks_truncated 게이트)
    long_ans = _para(1500)
    monkeypatch.setattr(C, "_verify_nonresponsive",
                        lambda ans, q: [("q", "연애운")] if ans == long_ans else [])
    monkeypatch.setattr(C, "_build_user_prompt", lambda *a, **k: "USER")
    truncated = _para(1300)[:-len(" 좋은 흐름이 이어지겠습니다.")] + " 그런데 재물운은 **에너지가"  # 열린 굵게로 끊김
    monkeypatch.setattr(C, "_call_ollama", lambda *a, **k: truncated)
    out = C._correct_nonresponsive(long_ans, "연애운 어때?", sys_content="S",
                                   saju_summary=None, chart_json=None)
    assert out == long_ans, "잘린 재생성본은 거부하고 원본 보존해야 함"


# ── P3: 스트리밍 분량 바닥 백스톱 가드(종합만 보강, 집중·후속·brief 제외) ──────────
def _concise_intent(explain_level, message, is_followup):
    """스트리밍 백스톱 제외조건과 동일 로직(chat_service _post_message_stream_inner) — 회귀 고정."""
    return (explain_level == "brief"
            or bool(C._focused_topic_labels(message or ""))
            or (is_followup and not C._wants_comprehensive(message or "")))


def test_streaming_boost_guard_only_comprehensive():
    # 종합 첫 풀이(짧으면 보강 대상) → 제외 아님
    assert _concise_intent("normal", "내 사주 전체적으로 봐줘", False) is False
    # 종합 요청 추가질문(월별/전체는 늘려도 됨) → 제외 아님
    assert _concise_intent("normal", "올해 전체 운세 다시 정리해줘", True) is False
    # brief 모드 → 제외
    assert _concise_intent("brief", "내 사주 봐줘", False) is True
    # 특정 주제(집중) → 제외(강제 확장이 집중설계와 충돌)
    assert _concise_intent("normal", "올해 이직운 어때", False) is True
    # 비종합 추가질문 → 제외
    assert _concise_intent("normal", "그럼 건강은?", True) is True


def test_streaming_min_chars_backstop_present():
    """스트리밍 경로에 분량 바닥 백스톱(제외가드 + '더 길 때만' 채택)이 유지되는지 소스 고정."""
    import io
    import pathlib
    src = io.open(pathlib.Path(__file__).resolve().parents[1] / "app" / "services" / "chat_service.py",
                  encoding="utf-8").read()
    assert "_concise_intent" in src, "스트리밍 분량 백스톱 제외가드 누락"
    assert "len(answer_full) < s.answer_min_chars" in src, "스트리밍 분량 하한 판정 누락"
    assert "len(_bc) > len(answer_full)" in src, "'더 길 때만 채택' 가드 누락"
