# -*- coding: utf-8 -*-
"""월번호↔간지 매핑 검증 — _verify_month_ganji (전문가 지적 케이스 #5, 2026-07).

실측: 월별 흐름에서 7월(丙申)·8월(丁酉)…로 표가 한 칸 밀림(정답 7월=乙未).
달력 월의 대표 간지(중순 기준)는 결정적 계산값이라 명식 없이 전수 대조한다.
"""
from __future__ import annotations

from datetime import date

from backend.app.services.chat_service import _upcoming_months, _verify_month_ganji

TODAY = date(2026, 7, 5)   # 실측 시점(절입 전 월초 — 함정 구간)


def test_flags_real_shifted_case():
    ans = ("7월 (병신(丙申)): 계획적인 접근이 필요한 시기입니다. "
           "8월 (정유(丁酉)): 세밀한 업무 처리와 계획적인 관리가.")
    bad = _verify_month_ganji(ans, today=TODAY)
    assert len(bad) == 2
    assert bad[0][0].startswith("7월 월운") and "을미" in bad[0][0]
    assert bad[1][0].startswith("8월 월운") and "병신" in bad[1][0]


def test_correct_mapping_passes():
    ans = ("7월 을미(乙未)에는 안정, 8월 (병신(丙申)) 협업, 9월 정유(丁酉) 성찰, "
           "10월 무술(戊戌), 11월 기해(己亥), 12월 경자(庚子)까지 무난합니다.")
    assert _verify_month_ganji(ans, today=TODAY) == []


def test_next_year_inference():
    # 7월 시점에 '1월'은 내년(2027) 1월로 추론 — 2027년 1월 정답과 비교
    from backend.app.saju.pillars import compute_pillars
    from backend.app.saju.types import BirthInput as BI, CalendarType as CT
    fp, *_ = compute_pillars(BI(birth_date=date(2027, 1, 15), calendar=CT.SOLAR))
    right = fp.month.stem + fp.month.branch
    assert _verify_month_ganji(f"1월 {right}에는 새 출발.", today=TODAY) == []
    wrong = "甲子" if right != "甲子" else "乙丑"
    assert len(_verify_month_ganji(f"1월 {wrong}에는 새 출발.", today=TODAY)) == 1


def test_past_context_untouched():
    assert _verify_month_ganji("작년 7월 갑오(甲午)에는 힘들었죠.", today=TODAY) == []
    assert _verify_month_ganji("2024년 7월 신미(辛未)의 일입니다.", today=TODAY) == []


def test_non_month_ganji_untouched():
    # 날짜 뒤 일진, 간지 없는 월 표기는 불개입
    assert _verify_month_ganji("7월 15일에 만나요. 12월에는 여행.", today=TODAY) == []


def test_upcoming_months_includes_current():
    ups = _upcoming_months(TODAY)
    assert ups[0][:2] == (2026, 7) and "을미" in ups[0][2]     # 당월 포함(케이스 #5 예방)
    assert ups[-1][1] == 12 and len(ups) == 6


# ── 월 독음 결정적 교정 — _fix_sinnyeon_month_reading (乙未→'으미' 환각, 2026-08) ──
def test_fix_month_reading_invalid_ganji_reading():
    from backend.app.services.chat_service import _fix_sinnyeon_month_reading as fx
    # 2026년 7월 월간지 = 乙未(을미). LLM이 '으미'(무효 독음)로 흘린 것을 결정적 교정.
    assert fx("7월 (으미월) 문서·후원", 2026) == "7월 (을미월) 문서·후원"
    # 이미 정확한 독음은 불변(멱등).
    assert fx("7월 (을미월)", 2026) == "7월 (을미월)"
    # 섹션 헤딩 한자 환각 환원.
    assert "영역별 심화" in fx("英域別深化 — 재물", 2026) and "英域" not in fx("英域別深化", 2026)


def test_fix_month_reading_guards():
    from backend.app.services.chat_service import _fix_sinnyeon_month_reading as fx
    # 과거/내년 문맥은 리포트 연도와 달라 불개입(오탐 방지).
    assert fx("작년 7월 (으미월)", 2026) == "작년 7월 (으미월)"
    assert fx("내년 7월 (으미월)", 2026) == "내년 7월 (으미월)"
    # 유효하지만 표밀림인 간지(병신)는 _verify_month_ganji 관할 — 이 교정기는 불개입.
    assert fx("7월 (병신월)", 2026) == "7월 (병신월)"


# ── 월 독음 교정 — 연도 추론(사주 상담 등 연도 미지정 경로) ──
def test_fix_month_reading_year_inference():
    from datetime import date as _d
    from backend.app.services.chat_service import _fix_sinnyeon_month_reading as fx
    T = _d(2026, 8, 3)
    # 연도 미지정 → 올해(2026) 세운으로 교정(2026 5월=계사).
    assert fx("5월 (으사월)", today=T) == "5월 (계사월)"
    # '내년' 문맥 → +1년(2027 5월=을사).
    assert fx("내년 5월 (으사월)", today=T) == "내년 5월 (을사월)"
    # 과거 회고 문맥은 불개입.
    assert fx("작년 5월 (으사월)", today=T) == "작년 5월 (으사월)"
    # 유효 독음(맞든 표밀림이든)은 불개입(검증기 관할).
    assert fx("5월 (병신월)", today=T) == "5월 (병신월)"
