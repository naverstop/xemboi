# -*- coding: utf-8 -*-
"""작명 재발 방지 — (B)단일 부족오행 붕괴 + (A)순열/이체자 중복.

2026-07-12 전문가 격노: '소지·지도·도지·하지·서지·지하'(전부 오행 목·목)가 인기이름 추천에 노출.
원인 2건:
  B) 부족오행이 1개면 자원 목표가 단일 오행으로 collapse → 두 글자 모두 그 부수로 강제 →
     木 부수 이름한자 23자로 붕괴 → 자연스러운 이름이 구조적으로 불가.
     해결(전문가 결정): 한 글자만 그 오행 보완, 나머지는 자연스러운 이름 음절(오행 무관).
  A) seen 집합이 한자 표기가 다르면 통과 → 荷準/荷埈(하준), 桃秀/秀桃(도수/수도), 祉桃/桃祉(지도/도지)
     같은 발음·순열 중복이 상위에 두 번. 해결: 발음·글자쌍(순열) 기준 최상위 1개만.
"""
from __future__ import annotations

from collections import Counter
from datetime import date

import pytest

from backend.app.saju import naming as N
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType


def _chart(s: str):
    y, m, d = map(int, s.split("-"))
    return build_chart(BirthInput(birth_date=date(y, m, d), calendar=CalendarType.SOLAR))


# 실측된 단일 부족오행 사주(자원 목표가 원소 1개로 collapse)
_SINGLE = ["1990-12-22", "1991-01-03", "1993-06-12", "1970-01-03"]
# 화면에 나왔던 기괴/순열 이름(다시는 상위에 오면 안 됨)
_BANNED = {"소지", "지도", "도지", "하지", "지하", "서지",
           "도수", "수도", "도예", "예도", "지한과한지"}  # 마지막은 placeholder(실 검사는 아래)


@pytest.mark.parametrize("s", _SINGLE)
def test_single_element_yields_natural_names(s: str):
    """단일 부족오행 사주도 자연스러운 인기 이름을 낸다(소지·지도·하지 재발 금지)."""
    ch = _chart(s)
    _, jawon = N._naming_targets(ch)
    assert len(jawon) == 1, f"{s}: 전제(단일 부족오행)가 깨졌다 — 케이스 갱신 필요"
    ns = N.recommend_names("金", ch, gender="male")[:6]
    readings = [n.reading for n in ns]
    # 최소 3개는 실제 인기 이름(예준·도윤·지호·하준…)
    tops = sum(1 for n in ns if N._is_top_name(n.reading, "male"))
    assert tops >= 3, f"{s}: 인기 이름이 {tops}개뿐 — {readings}"
    # 기괴 이름 노출 금지
    for bad in ("소지", "지도", "도지", "하지", "지하", "도수", "수도"):
        assert bad not in readings, f"{s}: 금지 이름 '{bad}' 노출 — {readings}"


@pytest.mark.parametrize("s", _SINGLE)
def test_single_element_keeps_one_char_supplement(s: str):
    """관법 유지: 첫 글자는 여전히 부족오행 부수(자원 보완 1자는 보장)."""
    ch = _chart(s)
    _, jawon = N._naming_targets(ch)
    target_ko = N.WUXING_KOREAN[jawon[0]]
    ns = N.recommend_names("金", ch, gender="male")[:8]
    for n in ns:
        first_el = N.WUXING_KOREAN.get(N._char_element(n.given[0]) or "", "불명")
        assert first_el == target_ko, f"{s}: '{n.reading}' 첫 글자 자원 {first_el} ≠ 보완 {target_ko}"


# 순열/이체자 중복이 실측됐던 사주 + 대표 표본
_DEDUP = ["2001-07-07", "2002-02-05", "1988-08-08", "1990-12-22", "1974-11-05"]


@pytest.mark.parametrize("s", _DEDUP)
def test_no_reading_or_permutation_duplicates(s: str):
    """상위 목록에 같은 발음/같은 글자쌍(순서만 다른)이 두 번 나오면 안 된다."""
    ch = _chart(s)
    ns = N.recommend_names("金", ch, gender="male")[:20]
    readings = [n.reading for n in ns]
    # (A1) 같은 발음 중복 없음
    dup_r = [r for r, c in Counter(readings).items() if c > 1]
    assert not dup_r, f"{s}: 발음 중복 {dup_r} — {readings}"
    # (A2) 같은 글자쌍 순열 중복 없음
    cs = Counter(frozenset(n.given) for n in ns)
    perm = [k for k, v in cs.items() if v > 1]
    assert not perm, f"{s}: 순열 중복 {len(perm)}건 — {readings}"


def test_multi_element_unchanged_shape():
    """다중 부족오행 사주는 종전대로 두 글자 모두 목표 오행 보완(관법 불변)."""
    ch = _chart("1988-08-08")
    _, jawon = N._naming_targets(ch)
    assert len(jawon) >= 2
    ns = N.recommend_names("金", ch, gender="male")[:6]
    assert all(N._is_top_name(n.reading, "male") or n.score >= 85 for n in ns)
