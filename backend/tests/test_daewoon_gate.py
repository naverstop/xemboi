"""대운(大運) 결정적 검증 게이트(_verify_daewoon) 테스트.

답변이 '대운'으로 지목한 간지가 명식 대운 목록과 다르면 불일치로 잡아 교정 재생성을
트리거하는지 검증(LLM 불필요 — 순수 함수). 실측 환각('현재 대운 (갑자, 15~24세)') 케이스화.
"""
from __future__ import annotations

from backend.app.services import chat_service as cs

# 명식 대운 목록: 병오·정미·무신 (한글/한자 모두 허용집합)
_CHART = {
    "daewoon": {
        "direction": "forward",
        "start_age": 5.6,
        "entries": [
            {"start_age": 6, "pillar": {"stem": "丙", "branch": "午"}},   # 병오
            {"start_age": 16, "pillar": {"stem": "丁", "branch": "未"}},  # 정미
            {"start_age": 26, "pillar": {"stem": "戊", "branch": "申"}},  # 무신
        ],
    }
}


# ===== 역방향(적대적): 명식에 없는 대운 간지를 지목하면 반드시 잡힌다 =====

def test_adv_invented_current_daewoon_paren_form():
    bad = cs._verify_daewoon("현재 대운 (갑자, 15~24세)에는 큰 변화가 옵니다.", _CHART)
    assert bad and bad[0][0] == "대운 간지" and bad[0][1] == "갑자"


def test_adv_invented_daewoon_with_hanja():
    bad = cs._verify_daewoon("이 시기 대운은 갑자(甲子)로 흐릅니다.", _CHART)
    assert bad and bad[0][1] in ("갑자", "甲子")


def test_adv_invented_daewoon_reverse_order():
    # 간지 → 대운(역방향): 기축 대운(명식에 없음)
    bad = cs._verify_daewoon("기축(己丑) 대운으로 접어들면 답답합니다.", _CHART)
    assert bad and bad[0][1] in ("기축", "己丑")


# ===== 전방향(정상): 올바른 대운·일반 표현은 절대 손대지 않는다 =====

def test_fwd_valid_daewoon_cited_ok():
    assert cs._verify_daewoon("현재 대운 병오(丙午)는 화 기운이 강합니다.", _CHART) == []
    assert cs._verify_daewoon("무신(戊申) 대운으로 들어서면 안정됩니다.", _CHART) == []


def test_fwd_daewoon_count_no_ganji_ok():
    # '대운수 5.6세' — 간지 아님 → 오탐 없음
    assert cs._verify_daewoon("대운수 5.6세부터 운이 바뀝니다.", _CHART) == []


def test_fwd_no_false_positive_gapjagi_near_daewoon():
    # '대운의 흐름이 갑자기' — '갑자'가 간지지만 대운에 직접 안 붙음 → 보존
    assert cs._verify_daewoon("대운의 흐름이 갑자기 바뀌어 변동이 큽니다.", _CHART) == []


def test_fwd_no_chart_safe():
    assert cs._verify_daewoon("현재 대운 갑자에는", None) == []
    assert cs._verify_daewoon("", _CHART) == []


def test_truth_includes_daewoon_list():
    # 교정 기준값(_myeongsik_truth)에 대운목록이 포함돼야 재생성이 올바른 간지를 인용
    truth = cs._myeongsik_truth(_CHART)
    assert "대운목록=" in truth and "병오" in truth
