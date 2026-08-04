# -*- coding: utf-8 -*-
"""반복 퇴행(degeneration) 방어 회귀 — 감지기·재생성 가드·Ollama 옵션·개명 규칙.

실측(2026-07-27): 개명 답변 '연, 영, 연, 영…' 2천자, 신년운세 tool#305 '인연에 대한 기회가
생길 때까지는' 228회 저장·과금. A(repeat_penalty)+B(감지·조기중단·가드)+C(개명 규칙)+D(퇴행 시
과금 방지) 로 대응. 감지기는 ①진성 폭주는 잡고 ②정상(월별·불릿·번호·구분선)은 절대 안 잡아야 한다
(오탐이 정상 답변을 재생성/환불시키면 안 됨)."""
from __future__ import annotations

import inspect

from backend.app.core.config import get_settings
from backend.app.services import chat_service as C
from backend.app.services import compat_service as CP
from backend.app.services import tool_service as TS


# ---- 감지기: 진성 퇴행 ----
def test_flags_phrase_repetition():
    assert C._looks_degenerate("답변입니다. " + "금이아닌" * 120)
    assert C._looks_degenerate("수 오행 예시는 " + "연, 영, " * 200)
    assert C._looks_degenerate("인연에 대한 기회가 생길 때까지는 " * 40)  # 실제 #305 패턴


def test_flags_single_char_flood():
    assert C._looks_degenerate("결론은 " + "금" * 150 + " 입니다")


def test_flags_low_diversity_variant():
    # 변주가 섞인 근사 반복(연/영/호…)도 글자 다양성이 바닥이라 잡힌다
    assert C._looks_degenerate("예: 해, 재, " + "연, 영, 연, 호, 연, 영, 연, 영, " * 80)


# ---- 감지기: 정상 답변은 절대 안 잡는다(오탐 금지) ----
def test_no_flag_monthly_flow():
    ans = ("1월은 재물운이 좋습니다. 2월은 건강을 조심하세요. 3월은 이동수가 있습니다. "
           "4월은 계약운이 좋고, 5월은 인연이 들어옵니다. 6월은 문서운, 7월은 이사에 유리합니다. "
           "8월은 승진 기회가 있으며 9월은 지출을 단속하세요. 10월은 투자에 신중하고 11월은 안정기, "
           "12월은 한 해를 정리하기 좋습니다.")
    assert not C._looks_degenerate(ans)


def test_no_flag_bullets_and_numbers():
    ans = ("### 총평\n- 정관(正官): 안정 지향\n- 편재(偏財): 활동적\n- 식신(食神): 표현력\n"
           "① 첫째로 성실합니다. ② 둘째로 리더십이 있습니다. ③ 셋째로 고집이 셉니다.\n"
           "--- \n**강점**은 추진력이고 **약점**은 예민함입니다. 水(수) 기운이 부족하니 보완이 필요합니다.")
    assert not C._looks_degenerate(ans)


def test_no_flag_normal_prose():
    ans = ("현재 이름은 사주에 부족한 오행인 수와 금을 어느 정도 보완하고 있습니다. 발음오행에서는 "
           "금이 충족되어 유리하지만, 자원오행에서는 목만 나타나 한계가 있습니다. 개명이 필요하다면 "
           "수 기운을 담은 방향의 글자를 찾는 것이 좋습니다. 전체적으로 균형을 맞추는 것이 핵심입니다.")
    assert not C._looks_degenerate(ans)


def test_short_answer_never_flagged():
    assert not C._looks_degenerate("네, 그렇습니다. 조심하세요.")


# ---- 스트림 조기감지(더 민감) ----
def test_stream_early_detection():
    assert C._stream_is_degenerating("인연에 대한 기회가 생길 때까지는 " * 8)
    assert not C._stream_is_degenerating("1월 재물, 2월 건강, 3월 이동, 4월 계약, 5월 인연, 6월 문서운입니다")


# ---- A: Ollama 옵션에 repeat_penalty/repeat_last_n 존재 ----
def test_ollama_options_have_repeat_penalty():
    s = get_settings()
    assert s.ollama_repeat_penalty >= 1.2
    assert s.ollama_repeat_last_n >= 128
    for fn in (C._call_ollama, C._stream_ollama):
        src = inspect.getsource(fn)
        assert "repeat_penalty" in src and "repeat_last_n" in src, fn.__name__


# ---- B/D: _correct_degenerate 재생성 — 구제 성공/실패 ----
def test_correct_degenerate_passthrough_when_clean():
    clean = "정상 답변입니다. 반복 없이 각 문장이 서로 다릅니다. 잘 작성되었습니다."
    assert C._correct_degenerate(clean, sys_content="s", base_user="u") == clean


def test_correct_degenerate_recovers(monkeypatch):
    bad = "예시: " + "연, 영, " * 200
    good = ("현재 이름은 금은 충족되나 수가 부족합니다. 수 기운을 담은 방향의 글자를 찾으면 좋습니다. "
            "전체적으로 오행 균형과 수리 길격을 함께 고려하세요.")
    monkeypatch.setattr(C, "_call_ollama", lambda *a, **k: good)
    assert C._correct_degenerate(bad, sys_content="s", base_user="u") == good


def test_correct_degenerate_force_regenerates_non_degenerate(monkeypatch):
    # 조기중단으로 끊긴 '잘린 부분답'은 퇴행 판정에 안 걸려도 force=True 면 재생성한다(잘린 답 저장 방지)
    partial = "현재 이름의 총평을 보면 수 기운이 부족하고 금은 어느 정도"  # 문장 중간 끊김(퇴행 아님)
    good = ("현재 이름은 발음오행에서 금은 충족되나 자원오행에서 수가 부족합니다. 개명이 필요하다면 수 "
            "기운을 담은 방향의 글자를 찾는 것이 좋습니다. 전체적으로 오행 균형과 수리 길격을 함께 "
            "고려하는 것이 핵심이며, 무리한 개명보다 신중한 검토를 권합니다.")
    monkeypatch.setattr(C, "_call_ollama", lambda *a, **k: good)
    assert not C._looks_degenerate(partial)                       # 퇴행 아님
    assert C._correct_degenerate(partial, sys_content="s", base_user="u") == partial  # force 없으면 통과
    assert C._correct_degenerate(partial, sys_content="s", base_user="u", force=True) == good  # force면 재생성


def test_correct_degenerate_unrecoverable_returns_empty(monkeypatch):
    bad = "예시: " + "연, 영, " * 200
    # 재생성도 또 퇴행 → '' 반환(호출부가 빈답변 경로로 환불/미저장)
    monkeypatch.setattr(C, "_call_ollama", lambda *a, **k: "또 " + "금이아닌" * 120)
    assert C._correct_degenerate(bad, sys_content="s", base_user="u") == ""


# ---- C: 개명 프롬프트 반복/나열 금지 규칙 ----
def test_gaemyeong_prompt_forbids_enumeration_and_repetition():
    assert "나열 금지" in TS.GAEMYEONG_SYSTEM
    assert "반복 금지" in TS.GAEMYEONG_SYSTEM


# ---- D: 퇴행 최종 가드가 각 서비스 finalize 에 배선됐는지 ----
def test_degeneration_guard_wired_in_services():
    # 사용자 답변을 생성하는 전 스트리밍 서비스(chat·tool·compat·tarot)에 퇴행 가드+조기중단 배선.
    from backend.app.services import tarot_service as TT
    for mod in (TS, CP, TT):
        src = inspect.getsource(mod)
        assert "_correct_degenerate" in src, f"{mod.__name__}: 퇴행 최종가드 누락"
        assert "_stream_is_degenerating" in src, f"{mod.__name__}: 스트림 조기중단 누락"
    # chat: 정의1 + 스트림·비스트림 두 경로
    assert inspect.getsource(C).count("_correct_degenerate(") >= 3
    assert "_stream_is_degenerating" in inspect.getsource(C)
