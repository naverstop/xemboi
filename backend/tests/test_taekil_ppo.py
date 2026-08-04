# -*- coding: utf-8 -*-
"""택일 뽀 관법 회귀 (문헌 교차확증 2026-07-29, wf_5f52bbc9).

이사 = 재·일지·월지(익일) / 결혼 = 남재·여관·일지 + 비겁배제 + 官 남녀공통.
깨짐 = 충·형·파·해(申-亥만)·천간극 (원진은 택일 흉 아님). 재/관/일지/월지 깨짐 = 하드 배제(길일 불가).
"""
from __future__ import annotations

from datetime import date

from backend.app.saju.engine import build_chart
from backend.app.saju.taekil import (
    _day_breaks_branch,
    _stem_geuk,
    recommend_dates,
)
from backend.app.saju.types import BirthInput, CalendarType, Gender

def _chart(y, m, d, gender, t="12:00"):
    return build_chart(BirthInput(birth_date=date(y, m, d), birth_time=t,
                                  calendar=CalendarType.SOLAR, gender=gender))


# ---- 깨짐 관계 판정(순수) ----
def test_day_breaks_branch():
    assert _day_breaks_branch("子", "午") == {"충"}           # 충
    assert _day_breaks_branch("寅", "巳") == {"형"}           # 형(寅巳)
    assert _day_breaks_branch("申", "亥") == {"해"}           # 해는 申-亥만
    assert _day_breaks_branch("丑", "午") == set()            # 축오 원진/해 아님 → 깨짐 아님
    assert _day_breaks_branch("子", "未") == set()            # 자미 원진 → 택일 깨짐 아님(문헌)


def test_stem_geuk():
    assert _stem_geuk("庚", "甲") is True                     # 금극목
    assert _stem_geuk("丙", "庚") is True                     # 화극금
    assert _stem_geuk("甲", "丙") is False                    # 목생화(극 아님)


# ---- 설명 기능: rule_note + 날짜별 reason ----
def test_rule_note_and_reason_present():
    r = recommend_dates(_chart(1988, 5, 20, Gender.MALE), date(2026, 8, 1), days=40, purpose="moving")
    assert "재물" in r.rule_note and "일지" in r.rule_note
    assert all(d.reason for d in r.best)                      # 모든 길일에 이유
    assert all(d.reason for d in r.avoid)


# ---- 하드 배제: 재/관/일지/월지 깨진 날은 '추천 길일'에 못 온다 ----
# ⚠️ 재검증 wwh751a42 HIGH: clean일이 부족한 명식(1988-05-20, 60일 중 clean 2일)에서 best가
#    흉일/_disq로 채워지던 버그를 단일명식(1990-08-10) 테스트가 못 잡았다 → floor 필터 + 다명식으로 강화.
def _is_hard_daily(w: str) -> bool:
    """하드배제(재/관/일지/월지 깨짐) 일별 경고인가. soft 월운 흉월 배지('월운…')는 제외."""
    if w.startswith("월운"):
        return False
    return w.startswith(("일지", "월지", "관(")) or "재(돈)" in w


def test_hard_exclusion_never_in_best():
    # clean일이 넉넉한 명식과 매우 부족한 명식(1988-05-20) 모두에서 불변식이 성립해야 한다.
    for y, m, d in ((1990, 8, 10), (1988, 5, 20), (1985, 11, 2)):
        for g in (Gender.MALE, Gender.FEMALE):
            for purpose in ("moving", "wedding"):
                r = recommend_dates(_chart(y, m, d, g), date(2026, 8, 1), days=60, purpose=purpose)
                for b in r.best:
                    # floor: 추천 길일은 보통(50) 이상·흉일 아님 → 하드배제일(_disq→≤44)은 구조적으로 불가.
                    assert b.score >= 50 and b.grade != "흉일", \
                        f"{y}/{purpose}/{g}: 흉일이 추천 길일에 옴 {b.date} {b.score} {b.grade}"
                    assert not any(_is_hard_daily(w) for w in b.warnings), \
                        f"{y}/{purpose}/{g}: 하드배제 사유가 길일에 옴 {b.date} {b.warnings}"
                # 길일이 없으면 no_gil=True + 차선(alt)만, best는 비어야 한다.
                if not r.best:
                    assert r.no_gil and r.alt, f"{y}/{purpose}/{g}: best 비었는데 no_gil/alt 미설정"


# ---- 성별 분기: 남=재 / 여=관 ----
def test_gender_branch_wedding():
    male = recommend_dates(_chart(1988, 5, 20, Gender.MALE), date(2026, 8, 1), days=90, purpose="wedding")
    female = recommend_dates(_chart(1988, 5, 20, Gender.FEMALE), date(2026, 8, 1), days=90, purpose="wedding")
    male_warns = " ".join(w for d in male.avoid for w in d.warnings)
    female_warns = " ".join(w for d in female.avoid for w in d.warnings)
    # 남자 결혼 회피에는 '재(돈)' 깨짐이, 여자에는 '관' 깨짐이 등장(같은 사주·성별만 다름)
    assert "재(돈)" in male_warns
    assert "관(" in female_warns


def test_wedding_bigyeop_day_flagged():
    # 결혼 회피에 비겁일이 하나라도 잡히는지(비겁 배제 규칙 작동)
    r = recommend_dates(_chart(1992, 3, 15, Gender.FEMALE), date(2026, 8, 1), days=120, purpose="wedding")
    assert any("비겁일" in w for d in (r.avoid + r.best) for w in d.warnings)


def test_hap_bonus():
    # 재/관이 그날 일진과 합되는 날 = '매우 좋은 날' 가점(문헌 '제일 좋은 날'). 회피(깨짐)와 공존 안 함.
    r = recommend_dates(_chart(1988, 5, 20, Gender.MALE), date(2026, 8, 1), days=90, purpose="wedding")
    hap = [b for b in r.best if "합" in b.reason]
    assert hap, "재 합 길일 가점 미표시"
    for b in hap:
        # 合 가점은 깨짐(disq/회피)과 공존하지 않는다(재/관 合탈취 방어).
        assert not b.reason.startswith("회피")
        # 하드배제 사유(일지/재/관/월지 깨짐)와도 공존 불가 — 合가점 게이트(not disq)를 잠근다.
        #   soft '월운 흉월(월지…)' 배지는 하드 아님이므로 제외 후 검사(substring 충돌 방지).
        assert not any(_is_hard_daily(w) for w in b.warnings), \
            f"合 가점일에 하드깨짐 공존 {b.date} {b.warnings}"
        # 월운 흉월(④ soft 감점)이면 좋은 일진이라도 순위 하향(흉일 가능·단서 표기) — 그 외엔 흉일 아님.
        if "월운 흉월" not in b.reason:
            assert b.grade != "흉일"
