# -*- coding: utf-8 -*-
"""검증기 오탐(정답을 오답으로 교정) 회귀 고정 — 2026-07-16 전수감사 P1.

원칙: 검증기 오탐은 '정답을 교정 재생성으로 파괴'하는 능동적 해악이라, 근거 풍부화보다
먼저 고쳐야 한다. 아래 문장들은 전부 감사에서 실측 재현된 케이스 그대로다.
"""
from __future__ import annotations

from datetime import date

from backend.app.services import chat_service as C
from backend.app.services import tool_service as T

def _tool_stream_body(mod):
    """툴 스트림 '본문'을 돌려준다 — 공개 stream_message 는 과금 보상 래퍼라 본문 가드가 그 안에 없다.

    [2026-07-23] 스트림 예외 시 선차감 미환불을 고치면서 본문을 _stream_message_inner 로 옮겼다.
    래퍼가 없어지면 다시 stream_message 를 보므로, 구조가 바뀌어도 이 헬퍼만 유지되면 된다.
    """
    return getattr(mod, "_stream_message_inner", mod.stream_message)


_TD = date(2026, 7, 16)  # 감사 시점 고정(월운 연도추론 검증용)


# ── _verify_month_ganji: '내년/올해' 문맥 연도추론 ──
def test_next_year_month_ganji_not_flagged():
    """'내년 8월 무신월'(2027-08=戊申 정답)을 올해 기준으로 오탐하지 않는다."""
    assert C._verify_month_ganji("내년 8월 무신월(戊申月)은 좋습니다.", today=_TD) == []


def test_this_year_past_month_not_flagged():
    """'올해 3월 신묘월'(2026-03=辛卯 정답·회고)을 내년 3월로 오탐하지 않는다."""
    assert C._verify_month_ganji("올해 3월 신묘월(辛卯月)에는 힘들었죠.", today=_TD) == []


def test_wrong_month_ganji_still_caught():
    """진짜 오류는 여전히 검출: 내년 8월(戊申)을 병신월로, 무문맥 8월(丙申)을 정유월로."""
    assert C._verify_month_ganji("내년 8월 병신월(丙申月)…", today=_TD)
    assert C._verify_month_ganji("8월 정유월(丁酉月)…", today=_TD)


def test_yearless_past_month_dual_year_check():
    """연도 무표기 과거월(신년운세형 '1월 (기축월)' 나열)은 올해·내년 둘 다 대조 —
    올해 정답(2026-01=己丑)을 내년 기준으로 오탐하지 않는다(라이브 스모크 실측 오탐)."""
    assert C._verify_month_ganji("1월 (기축월)은 새 출발의 달입니다.", today=_TD) == []   # 올해 정답
    assert C._verify_month_ganji("1월 신축월은 준비의 달.", today=_TD) == []              # 내년 정답
    assert C._verify_month_ganji("1월 갑오월은…", today=_TD)                              # 둘 다 불일치=환각


# ── _verify_branches: 날짜 문맥(오늘/N일은) 제외 ──
def test_today_iljin_description_not_flagged():
    """오늘운세 '오늘 일지 巳가…'(정답 일진 해설)를 본인 일지와 대조해 오탐하지 않는다."""
    allow = {"day": {"亥"}}
    assert C._verify_branches("오늘 일지 사(巳)가 본인 일지 해(亥)를 충합니다.",
                              allow, exclude_date_ctx=True) == []


def test_calendar_day_description_not_flagged():
    """캘린더 '6일은 일지가 巳라서…'(정답)를 오탐하지 않는다."""
    assert C._verify_branches("6일은 일지가 사(巳)라서 조심.", {"day": {"亥"}},
                              exclude_date_ctx=True) == []


def test_natal_branch_error_still_caught():
    """본인 명식 지지 오류는 여전히 검출(날짜 문맥 아님)."""
    assert C._verify_branches("당신의 일지 사(巳)는…", {"day": {"亥"}}, exclude_date_ctx=True)


def test_tool_no_date_covers_today_calendar():
    """today/calendar도 택일처럼 날짜문맥 제외를 받는다(tool_service 배선 회귀 방지)."""
    import inspect
    src = inspect.getsource(_tool_stream_body(T))
    assert '"today"' in src and '"calendar"' in src and '"taekil"' in src


# ── _verify_day_stem: '일간과 X' 비교 조사 제외 ──
def test_day_stem_comparison_not_flagged():
    """'오늘의 천간이 일간과 辛의 편관…'(비교 서술 정답)을 일간 환각으로 오탐하지 않는다."""
    cj = {"pillars": {"day": {"stem": "乙", "branch": "亥"}}}
    assert C._verify_day_stem("오늘의 천간이 일간과 辛의 편관 관계입니다.", cj) == []


def test_day_stem_error_still_caught():
    cj = {"pillars": {"day": {"stem": "乙", "branch": "亥"}}}
    assert C._verify_day_stem("당신의 일간 辛은…", cj)


# ── _COMPAT_NEG: '아닙니다/아닌' 부정문 ──
def test_compat_negation_not_flagged():
    """'육합이 아닙니다'(부정문)를 관계 단정으로 오탐하지 않는다."""
    a = {"pillars": {"day": {"stem": "甲", "branch": "子"}}}
    b = {"pillars": {"day": {"stem": "甲", "branch": "午"}}}  # 실제 관계: 충
    assert C._verify_compat_relations("두 분 일지는 육합이 아닙니다.", a, b) == []


def test_branch_verifier_skips_other_scope_branch():
    """[2026-07-22 전수감사] '내 월지와 세운 지지 오(午)가 파를 맺고 있어요' — 세운의 지지를
    명식 월지 주장으로 오인해 매번 교정 재생성(1~2분)을 헛돌게 만들었다. 위치어와 지지 사이에
    세운·대운·일진 등 다른 스코프어가 끼면 그 지지는 명식 것이 아니다."""
    from backend.app.services.chat_service import _verify_branches as V
    allow = {"month": {"卯"}, "day": {"酉"}, "year": {"午"}}

    # 오탐이었던 문장들 — 통과해야 한다
    assert V("특히, 내 월지와 세운 지지 오(午)가 파를 맺고 있어요.", allow) == []
    assert V("내 월지와 대운 지지 신(申)이 충합니다.", allow) == []
    assert V("내 일지와 오늘 일진 자(子)가 만납니다.", allow) == []

    # 진짜 명식 오류는 여전히 잡는다(무회귀)
    assert V("내 월지 오(午)는 화 기운입니다.", allow) == [("월지", "午", "卯")]
    assert V("내 일지 자(子)입니다.", allow) == [("일지", "子", "酉")]
    assert V("내 월지 묘(卯)는 목 기운입니다.", allow) == []
