# -*- coding: utf-8 -*-
"""호칭(이메일 @앞) + 중국어 드리프트 차단 (2026-07 실측: '연수님' 하드코딩 예시 복사, 월별 중국어).

① _display_name: 로그인 사용자 호칭을 이메일 로컬파트(@앞)로 결정(닉네임 미사용).
② _lead_verdict_rule: 예시에 이름 하드코딩 제거(약한 LLM이 '연수님'을 실제 호칭으로 베낌).
③ _looks_korean_clean: 긴 한국어 뒤 월별이 중국어로 드리프트해도 전체비율로 통과하던 누출 차단.
"""
from __future__ import annotations

from backend.app.services.chat_service import (
    _display_name,
    _lead_verdict_rule,
    _looks_korean_clean,
)


class _U:
    def __init__(self, email, nickname=None):
        self.email = email
        self.nickname = nickname


# ── ① 호칭 = 이메일 @앞 ─────────────────────────────
def test_display_name_uses_email_local_part():
    assert _display_name(_U("orion0321@gmail.com", nickname="연수")) == "orion0321"
    assert _display_name(_U("hong@naver.com")) == "hong"
    assert _display_name(None) == ""
    assert _display_name(_U("")) == ""


# ── ② 예시 이름 하드코딩 제거 ─────────────────────────────
def test_lead_verdict_rule_no_hardcoded_name():
    # 예시문에 '연수님'이 남아있으면 약한 LLM이 베낌 → 제거 확인
    assert "연수님" not in _lead_verdict_rule("orion0321")
    assert "연수" not in _lead_verdict_rule("")
    # 이름 있으면 그 이름만, 없으면 호칭 만들지 말라는 지시
    assert "orion0321님" in _lead_verdict_rule("orion0321")
    assert "만들어 붙이지" in _lead_verdict_rule("")


# ── ③ 중국어 드리프트 차단 ─────────────────────────────
_KOR_LONG = "성격은 안정적이고 견고하며 인내심이 강합니다. 육친과 건강운도 원만한 편입니다. " * 12


def test_chinese_drift_in_monthly_blocked():
    # 긴 한국어 + 월별 중국어 → 전체비율은 낮아도 차단돼야
    txt = _KOR_LONG + "\n9月 职业及财富 土和金的和谐有助于稳定的职业表现\n人际关系及恋爱 维持和谐"
    assert _looks_korean_clean(txt) is False


def test_simplified_markers_blocked():
    assert _looks_korean_clean(_KOR_LONG + " 职业和财富的发展") is False   # 간체 다수
    assert _looks_korean_clean(_KOR_LONG + " 这是一个问题") is False       # 중문 문법자


def test_clean_korean_with_hanja_passes():
    ok = ("성격은 안정적입니다. 일간 무신(戊申)은 토(土) 기운이 강하고 식신(食神)이 독립심을 뜻합니다. "
          "정관(正官)·편재(偏財)의 조화로 현실감각이 좋고 올해는 재물운도 기대됩니다. 건강은 소화기를 관리하세요.")
    assert _looks_korean_clean(ok) is True
    # 정상 한자 병기(정자)는 마커에 안 걸림
    assert _looks_korean_clean("용신(用神)은 庚金이고 대운(大運)은 순행합니다. " * 4) is True
