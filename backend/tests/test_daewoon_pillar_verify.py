# -*- coding: utf-8 -*-
"""대운 나이구간·현재대운·4주 간지 재서술 검증 — 전수감사 P0 3종 (2026-07).

기존 _verify_daewoon은 간지 집합 멤버십만 봐서 나이구간↔간지 짝 밀림·현재대운 오배정을
놓쳤고, _verify_branches는 '지지' 위치어만 앵커해 '일주 신미' 柱어 재서술을 100% 놓쳤다.
셋 다 명식(daewoon.entries·birth_date·pillars)으로 완전 결정적이라 재계산해 대조한다.
"""
from __future__ import annotations

from datetime import date

from backend.app.services.chat_service import (
    _verify_current_daewoon,
    _verify_daewoon_age_range,
    _verify_pillar_ganji,
)

# 2007-03-20 남 — 역행, 5~14 壬寅 / 15~24 辛丑 / 25~34 庚子 / 35~44 己亥 / 45~54 戊戌
CHART = {
    "input": {"birth_date": "2007-03-20"},
    "pillars": {"year": {"stem": "丁", "branch": "亥"}, "month": {"stem": "癸", "branch": "卯"},
                "day": {"stem": "癸", "branch": "丑"}, "hour": {"stem": "壬", "branch": "子"}},
    "daewoon": {"direction": "backward", "start_age": 4.57, "entries": [
        {"start_age": 5, "pillar": {"stem": "壬", "branch": "寅"}},
        {"start_age": 15, "pillar": {"stem": "辛", "branch": "丑"}},
        {"start_age": 25, "pillar": {"stem": "庚", "branch": "子"}},
        {"start_age": 35, "pillar": {"stem": "己", "branch": "亥"}},
        {"start_age": 45, "pillar": {"stem": "戊", "branch": "戌"}},
    ]},
}
TODAY = date(2026, 7, 5)   # 만 19세 → 현재 대운 15~24세 辛丑


# ── V1 나이구간↔간지 ─────────────────────────────
def test_age_range_shift_flagged():
    # 辛丑은 15~24세인데 25~34세로 밀려 적음
    bad = _verify_daewoon_age_range("25~34세: 신축(辛丑) 시기입니다.", CHART)
    assert len(bad) == 1 and "신축" in bad[0][1] and "15~24세" in bad[0][2]


def test_age_range_correct_passes():
    ok = "5~14세: 임인(壬寅), 15~24세: 신축(辛丑), 25~34세: 경자(庚子)"
    assert _verify_daewoon_age_range(ok, CHART) == []


def test_age_range_pm1_tolerance():
    # 15↔16세 경계 반올림 허용
    assert _verify_daewoon_age_range("16~25세 신축(辛丑)", CHART) == []


def test_age_range_ignores_invented_ganji():
    # 간지 자체 환각(丁未∉대운)은 _verify_daewoon 관할 — 여기선 불개입
    assert _verify_daewoon_age_range("21~30세: 정미(丁未)", CHART) == []


# ── V2 현재대운 ─────────────────────────────
def test_current_daewoon_wrong_flagged():
    # 실측 화법 재현: 19세인데 갑오/임인 등 다른 대운으로 단정
    bad = _verify_current_daewoon("현재 약 19세로 추정되므로, 현재 대운은 임인(壬寅)에 해당합니다.", CHART, today=TODAY)
    assert len(bad) == 1 and "신축" in bad[0][2]


def test_current_daewoon_correct_passes():
    assert _verify_current_daewoon("현재 대운은 신축(辛丑)입니다.", CHART, today=TODAY) == []


def test_current_daewoon_ignores_list_enumeration():
    # '목록 나열'에는 '현재/약 N세' 문맥어가 없어 불개입(오탐 방지)
    assert _verify_current_daewoon("5~14세: 임인(壬寅), 15~24세: 신축(辛丑)", CHART, today=TODAY) == []


# ── V3 4주 간지 재서술 ─────────────────────────────
def test_pillar_ganji_wrong_flagged():
    assert len(_verify_pillar_ganji("일주 신미(辛未)의 특성상", CHART)) == 1     # 실제 일주 癸丑
    assert len(_verify_pillar_ganji("월주 병신(丙申)", CHART)) == 1              # 실제 월주 癸卯


def test_pillar_ganji_correct_passes():
    ok = "년주 정해(丁亥), 월주 계묘(癸卯), 일주 계축(癸丑), 시주 임자(壬子)"
    assert _verify_pillar_ganji(ok, CHART) == []


def test_myeongsik_gate_catches_daewoon_ganji():
    # 실측(2027 무인대운): 연도 없는 순수 '무인 대운' 환각을 게이트 _verify_myeongsik이 잡아야 함
    from backend.app.services.chat_service import _verify_myeongsik
    txt = "무인(戊寅) 대운으로 접어들면서 이직 기운이 활발해집니다."
    bad = _verify_myeongsik(txt, CHART)
    assert any(b[0] == "대운 간지" for b in bad)
    # 실제 대운(壬寅=CHART 첫 대운)은 통과
    assert not any(b[0] == "대운 간지" for b in _verify_myeongsik("임인(壬寅) 대운입니다.", CHART))


def test_year_ganji_catches_2027_muin():
    # 실측 핵심: '2027년 무인(戊寅)'은 2027=정미(丁未)라 연도↔간지 오류
    from backend.app.services.chat_service import _verify_year_ganji
    bad = _verify_year_ganji("2027년 무인(戊寅) 대운으로 접어들면서")
    assert len(bad) == 1 and "정미" in bad[0][2]


def test_future_daewoon_past_cited_as_next_year():
    # 실측(51세): '내년 대운이 무인(戊寅)으로'인데 무인은 과거(19~28세) 대운 → 과거오인 플래그
    from datetime import date
    from backend.app.services.chat_service import _verify_future_daewoon
    chart = {"input": {"birth_date": "1975-05-05"},
             "pillars": {"day": {"stem": "丙", "branch": "子"}},
             "daewoon": {"direction": "forward", "entries": [
                 {"start_age": 9, "pillar": {"stem": "丁", "branch": "丑"}},
                 {"start_age": 19, "pillar": {"stem": "戊", "branch": "寅"}},   # 무인 19~28 과거
                 {"start_age": 49, "pillar": {"stem": "辛", "branch": "巳"}}]}}  # 현재 신사
    bad = _verify_future_daewoon("내년 대운이 무인(戊寅)으로 바뀌면서", chart, today=date(2026, 7, 5))
    assert len(bad) == 1 and "신사" in bad[0][2]


def test_relative_year_conflation_scrub():
    from backend.app.services.chat_service import _fix_relative_year_conflation
    assert _fix_relative_year_conflation("• 내년 (올해, 2027년)") == "• 내년 (2027년)"
    assert _fix_relative_year_conflation("내년(올해 2027년)에는") == "내년(2027년)에는"
    # 정상 표기 보존
    assert _fix_relative_year_conflation("올해는 2026년입니다") == "올해는 2026년입니다"
    assert _fix_relative_year_conflation("내년 2027년에는") == "내년 2027년에는"


def test_day_stem_korean_notation_caught():
    # 실측(무신 일주에 일간 계 표시): '일간 계수' 한글전용 오독을 잡아야(종전 한자만 발화하던 갭)
    from backend.app.services.chat_service import _verify_day_stem
    ch = {"pillars": {"day": {"stem": "戊", "branch": "申"}}}   # 일간 무(戊)
    assert _verify_day_stem("일간은 계수라 창의적입니다", ch)      # 계→무 불일치
    assert _verify_day_stem("일간 계(癸) 기준 오늘의 기운", ch)
    assert _verify_day_stem("본인 일간 무토(戊土)", ch) == []      # 정답 통과
    # 오탐 가드: 일반어 불개입
    assert _verify_day_stem("일간이 신약한 편이라", ch) == []
    assert _verify_day_stem("일간 강약은 중화입니다", ch) == []


def test_pillar_ganji_no_chart_safe():
    assert _verify_pillar_ganji("일주 신미", None) == []
    assert _verify_daewoon_age_range("25~34세 갑자", None) == []
    assert _verify_current_daewoon("현재 대운 갑자", None) == []
