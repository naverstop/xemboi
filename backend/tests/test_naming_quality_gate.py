# -*- coding: utf-8 -*-
"""작명 이름 품질 하드 게이트 — 기괴한 이름 재발 방지 (2026-07-10 전문가 격노 대응).

실측: '功孟(공맹)·茂嘸(무무)·芳孟(방맹)·怠稻(태도)·芽耳(아이)·芽油(아유)' 같은 비(非)이름이 1위 노출.
근본원인: 이름 품질이 정렬의 **동점 tiebreaker**에 불과해, 점수(오행·수리)가 분화되는 순간 무력화됐고
(발음오행 관법 도입이 방아쇠), 품질을 **blocklist**(_BAD_DEFN·_BAD_CHARS)로 지키려 해 구멍이 무한했다
(耳·油·而·夷·怠는 전부 상용한자라 통과).

해결: 후보 생성을 **이름 한자 allowlist**(data/naming/name_hanja.json)로 제한하는 **하드 게이트**.
이 테스트가 그 게이트를 영구 고정한다 — 누가 점수 로직을 바꿔도 기괴한 이름은 나올 수 없다.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.app.saju import naming as N
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType

_CHARTS = [(1985, 3, 3), (1990, 5, 5), (1995, 7, 7), (2000, 11, 11),
           (2005, 1, 20), (1978, 9, 9), (2010, 6, 15), (1966, 12, 1)]


def _allowed_chars() -> set[str]:
    syl = N._name_hanja().get("syllables") or {}
    return {ch for chars in syl.values() for ch in chars}


def test_allowlist_data_loads():
    d = N._name_hanja()
    assert d.get("syllables") and d.get("male") and d.get("female")
    assert len(_allowed_chars()) >= 100          # 오행·수리 제약을 만족할 만큼 충분


@pytest.mark.parametrize("ymd", _CHARTS)
@pytest.mark.parametrize("gender", ["male", "female"])
def test_top_names_only_use_name_hanja(ymd, gender):
    """상위 추천 이름의 모든 글자가 '실제 이름 한자' allowlist 안에 있어야 한다."""
    ch = build_chart(BirthInput(birth_date=date(*ymd), calendar=CalendarType.SOLAR))
    cands = N.recommend_names("김", ch, top=10, gender=gender)
    assert cands, f"후보 생성 실패: {ymd} {gender}"
    allowed = _allowed_chars()
    for c in cands:
        for ch_ in c.given:
            assert ch_ in allowed, f"이름 밖 한자 노출: {c.given}({c.reading}) '{ch_}' [{ymd} {gender}]"


@pytest.mark.parametrize("ymd", _CHARTS)
@pytest.mark.parametrize("gender", ["male", "female"])
def test_no_repeated_syllable(ymd, gender):
    """같은 음절 반복(民敏=민민, 徒稻=도도) 금지 — 한국 이름으로 쓰지 않는다."""
    ch = build_chart(BirthInput(birth_date=date(*ymd), calendar=CalendarType.SOLAR))
    for c in N.recommend_names("김", ch, top=10, gender=gender):
        syls = list(c.reading)
        assert len(set(syls)) == len(syls), f"음절 반복: {c.given}({c.reading})"


@pytest.mark.parametrize("ymd", _CHARTS)
@pytest.mark.parametrize("gender", ["male", "female"])
def test_top_names_have_lucky_suri(ymd, gender):
    """수리(81수) 4격에 '흉'이 있는 이름은 상위에 노출되지 않는다(길격 하드 보장)."""
    ch = build_chart(BirthInput(birth_date=date(*ymd), calendar=CalendarType.SOLAR))
    for c in N.recommend_names("김", ch, top=10, gender=gender):
        assert "흉" not in c.suri_grade, f"흉격 노출: {c.given}({c.reading}) {c.suri_grade}"


def test_ranking_prefers_natural_popular_names():
    """[전문가 결정] 자연스러운 인기 이름 우선 — 실제 Top20 이름이 있으면 상위에 와야 한다.

    종전엔 정렬 1순위가 점수라, 오행만 맞는 비자연 조합(명범·민강)이 예준·서준을 눌렀다.
    """
    ch = build_chart(BirthInput(birth_date=date(1990, 5, 5), calendar=CalendarType.SOLAR))
    top = N.recommend_names("김", ch, top=5, gender="male")
    readings = [c.reading for c in top]
    assert any(N._is_top_name(r, "male") for r in readings), f"인기 이름 미노출: {readings}"


def test_bad_meaning_chars_blocked():
    """실측 유출 글자(怠 게으를·耳 귀·油 기름·夷 오랑캐·孟 맏)는 어떤 풀에도 없어야 한다.

    1차 게이트=allowlist(구조적 보장), 2차=폴백 풀의 _BAD_CHARS 방어(안전망)."""
    leaked = "怠耳油而夷偶孟嘸沛溥只徒態"
    for el in ("木", "火", "土", "金", "水"):
        for g in ("male", "female"):
            pool = set(N._name_hanja_pool(el, g)) | set(N._popular_hanja_pool(el, g))
            bad = [c for c in leaked if c in pool]
            assert not bad, f"비이름 글자 유출 {bad} ({el}/{g})"
