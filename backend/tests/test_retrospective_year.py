# -*- coding: utf-8 -*-
"""과거 연도 회고 질문 — 동문서답/두루뭉술 방지 (Track A, 2026-07-12).

실측 버그: "임인년 사업 시작, 계묘년 갑진년 사업운 어땠을까"에 '올해 병오'로 답함(동문서답).
근본원인: ① 간지연도(계묘=2023)·절대연도 파서 부재로 그 해 세운 미주입 ② 미래지향 규칙이 과거
서술 차단 ③ 출력단 scrub이 과거 간지를 '올해'로 파괴. Track A는 명시된 과거 연도에 한해
세운을 결정적으로 주입하고 규칙·scrub을 완화한다.

★ 핵심 안전원칙: 비회고 질문은 종전과 100% 동일 동작(반대방향 환각 회귀 차단). 아래 T3/T4가 고정.
"""
from __future__ import annotations

import pytest

from backend.app.services import chat_service as C

_TODAY_Y = __import__("datetime").date.today().year


def test_ganzhi_to_year_matches_engine():
    """간지→서기연도 역매핑이 엔진 계산과 일치(과거 방향)."""
    assert C._ganzhi_to_year("계묘", 2026, "past") == 2023
    assert C._ganzhi_to_year("갑진", 2026, "past") == 2024
    assert C._ganzhi_to_year("임인", 2026, "past") == 2022
    assert C._ganzhi_to_year("병오", 2026, "past") == 2026  # anchor 자신
    # 엔진과 일치 여부를 최근 40년에 걸쳐 교차검증
    for y in range(_TODAY_Y - 40, _TODAY_Y + 1):
        gz = C._year_ganzhi_ko(y)
        assert C._ganzhi_to_year(gz, _TODAY_Y, "past") == y


def test_target_years_extracted():
    """T1 — 간지연도·절대연도가 실제 과거연도로 추출된다."""
    q = "임인년 사업을 시작했어요 계묘년 갑진년 사업운이 어땠을까요"
    assert C._question_target_years(q, __import__("datetime").date(2026, 7, 12)) == [2022, 2023, 2024]
    assert C._question_target_years("2023년 재물운은 어땠나요", __import__("datetime").date(2026, 1, 1)) == [2023]


def test_years_block_injects_seun():
    """T1 — 질문 연도 세운이 프롬프트 블록으로 주입(계묘·갑진)."""
    q = "계묘년 갑진년 사업운이 어땠을까요"
    blk = C._question_years_block(q, __import__("datetime").date(2026, 7, 12))
    assert "계묘(癸卯)" in blk and "갑진(甲辰)" in blk
    assert "[질문한 연도 세운]" in blk


def test_retrospective_gate():
    """회고 게이트 — 과거연도 명시 질문만 True."""
    assert C._is_retrospective("계묘년 갑진년 사업운 어땠을까", __import__("datetime").date(2026, 7, 12))
    assert not C._is_retrospective("올해 사업운 어때요")
    assert not C._is_retrospective("내년 이직운 어떤가요")
    assert not C._is_retrospective("성격이 어떤가요")


def test_retrospective_rule_swapped():
    """회고 질문은 RETROSPECTIVE_RULE, 비회고는 FUTURE_ORIENTED_RULE(무회귀)."""
    q = "계묘년 갑진년 사업운 어땠을까"
    sys_r = C._compose_sys_content("SP", None, "normal", question=q)
    sys_n = C._compose_sys_content("SP", None, "normal", question="올해 사업운 어때요")
    assert "과거 회고 허용" in sys_r and "미래지향" not in sys_r
    assert "미래지향" in sys_n and "과거 회고 허용" not in sys_n


def test_scrub_preserves_retro_years():
    """T4 — 질문 연도(들)는 scrub이 보존, 미명시 과거연도는 여전히 중화."""
    s = "계묘년(2023)에 사업이 흥했고 갑진년(2024)에는 어려움이 있었습니다."
    kept = C._scrub_stale_year_ganji(s, allowed_years=[2023, 2024])
    assert "계묘" in kept and "갑진" in kept and "2023" in kept and "2024" in kept
    # 회고 대상에 없는 연도(2021)는 중화
    s2 = "신축년(2021)에는 부진했습니다."
    assert "신축" not in C._scrub_stale_year_ganji(s2, allowed_years=[2023])


def test_scrub_nonretro_unchanged():
    """T3 — 비회고(allowed_years=None)는 종전과 동일하게 과거 간지 파괴(무회귀)."""
    s = "계묘년(2023)에 사업이 흥했고 갑진년(2024)에는 어려움이 있었습니다."
    scrubbed = C._scrub_stale_year_ganji(s)
    assert "계묘" not in scrubbed and "갑진" not in scrubbed
    assert "올해" in scrubbed
    # 올해/내년 실제 간지는 비회고에서도 보존
    cur = _TODAY_Y
    ko = C._year_ganzhi_ko(cur)
    assert ko in C._scrub_stale_year_ganji(f"{ko}년({cur}년)에는 좋습니다.")


def test_nonretro_luck_block_keeps_guard():
    """T3 — 비회고 질문 luck block은 '지난 연도 지어내지 마세요' 제약 유지."""
    assert "지난 연도" in C._current_luck_block(question="올해 사업운 어때요")
    assert "지난 연도(예: 2023년)" not in C._current_luck_block(
        question="계묘년 갑진년 사업운 어땠을까")


def test_future_absolute_year_not_retrospective():
    """미래 절대연도(2030년)는 회고 대상 아님 — 과거만 추출."""
    assert C._question_target_years("2030년 사업운은 어떨까요", __import__("datetime").date(2026, 1, 1)) == []
