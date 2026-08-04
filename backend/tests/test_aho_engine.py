# -*- coding: utf-8 -*-
"""아호(雅號) 전용 엔진 회귀 테스트.

배경: 종전 아호는 신생아 작명 엔진을 성(姓)만 비워 호출했다. 그 엔진은 후보를 실제
아기 이름 allowlist 로 게이트하고 2024 신생아 Top30 에 1000점을 주므로, 라이브 아호
세션 15건의 1순위가 전부 시우·하준·유준·지호·서윤·서지였다. AHO_SYSTEM 이 "신생아처럼
쓰지 마세요"라고 지시해도 **후보표 자체가 신생아 이름이라** 프롬프트로는 고칠 수 없었다.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.app.saju import naming as N
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType, Gender

CHARTS = [
    (date(1985, 3, 15), Gender.MALE),
    (date(1990, 11, 2), Gender.FEMALE),
    (date(1978, 8, 12), Gender.MALE),
    (date(2001, 1, 9), Gender.FEMALE),
]


@pytest.fixture(scope="module")
def charts():
    return [build_chart(BirthInput(birth_date=d, birth_time="09:30",
                                   calendar=CalendarType.SOLAR, gender=g)) for d, g in CHARTS]


def test_lexicon_loaded_and_self_consistent():
    """글자 풀의 독음·획수·자원오행은 손으로 적은 값이 아니라 사전에서 산출한 값이어야 한다."""
    lex = N.aho_lexicon()
    assert len(lex) >= 50
    for c in lex:
        ent = N._hanja().get(c["char"])
        assert ent, f"hanja_dict 에 없는 글자: {c['char']}"
        ko = ent.get("ko") or []
        ko = ko if isinstance(ko, list) else [ko]
        # 독음은 **사전이 가진 독음 중 하나**여야 한다. 첫 값 고정이 아니다 —
        # 北 은 사전 첫 값이 '배'(敗北 전용)이고 露·蓮·蘭·樓 는 두음법칙으로 자리마다 다르다.
        assert c["reading"] in ko, f"{c['char']} 독음 '{c['reading']}' 이 사전에 없다: {ko}"
        assert c.get("reading_tail", c["reading"]) in ko, f"{c['char']} 뒷자리 독음이 사전에 없다"
        assert c["strokes"] == ent.get("strokes"), f"{c['char']} 획수 불일치"
        assert c["element"] == (N._char_element(c["char"]) or ""), f"{c['char']} 자원오행 불일치"


def test_no_baby_name_chars_leak(charts):
    """아호 후보에 신생아 이름 음절이 나오면 안 된다 — 이게 이 엔진을 만든 이유다."""
    baby = {"시우", "하준", "유준", "지호", "서윤", "서지", "도윤", "서준", "예준", "지안"}
    for ch in charts:
        for c in N.recommend_aho(ch, top=12):
            assert c.reading not in baby, f"신생아 이름이 아호로 나왔다: {c.given}({c.reading})"


def test_candidates_come_only_from_aho_pool(charts):
    """후보 글자는 아호 전용 풀 안에서만 나와야 한다(작명 allowlist 유입 차단)."""
    pool = {c["char"] for c in N.aho_lexicon()}
    for ch in charts:
        for c in N.recommend_aho(ch, top=12):
            assert set(c.given) <= pool, f"풀 밖 글자: {c.given}"


def test_no_single_char_domination(charts):
    """한 글자가 후보표를 독식하면 '고를 게 없는' 리포트가 된다(실측: 露 가 5개)."""
    for ch in charts:
        cands = N.recommend_aho(ch, top=8)
        assert len(cands) >= 6
        counts: dict[str, int] = {}
        for c in cands:
            for x in c.given:
                counts[x] = counts.get(x, 0) + 1
        assert max(counts.values()) <= 2, f"한 글자 편중: {counts}"


def test_readings_avoid_everyday_word_collisions(charts):
    """국자·창자·청각·서자처럼 일상어와 동음인 조합은 유료 리포트에 올릴 수 없다."""
    for ch in charts:
        for c in N.recommend_aho(ch, top=12):
            assert c.reading not in N._AHO_BAD_READING


def test_every_candidate_has_a_type(charts):
    """작호 유형은 글자 group → type 결정적 매핑이라 빈 값이 나오면 매핑에 구멍이 있다."""
    codes = {t["code"] for t in (N.aho_types().get("types") or [])}
    for ch in charts:
        for c in N.recommend_aho(ch, top=12):
            assert c.aho_type in codes, f"유형 미배정: {c.given} → {c.aho_type!r}"


def test_type_data_records_provenance():
    """'고전이 정한 4법'이라는 사칭을 막는 것이 origin 필드의 목적이다.

    이규보 「백운거사어록」이 든 것은 세 가지이고, 네 유형 정리와 그 용어는 현대 연구의 것이다."""
    types = N.aho_types()
    assert types.get("types")
    for t in types["types"]:
        assert t.get("origin") in {"classic", "modern_summary_of_classic", "modern_addition"}
        assert t.get("source")
    # 소지이호는 후대에 더해진 유형이다 — 이 사실이 데이터에 남아 있어야 한다
    soji = next(t for t in types["types"] if t["code"] == "soji")
    assert soji["origin"] == "modern_addition"


def test_examples_without_verified_origin_have_no_story():
    """유래가 확인 안 된 사례는 호 표기만 남기고 이야기를 지어내지 않는다."""
    for e in N.aho_examples():
        if not e.get("origin_story"):
            assert e.get("origin_status"), f"유래 없는 사례에 상태 표기 누락: {e.get('ho')}"


def test_naming_engine_untouched(charts):
    """작명(jakmyeong)은 종전대로 동작해야 한다 — 아호 작업의 회귀 위험 0을 고정."""
    got = N.recommend_names("金", charts[0], top=5, gender="male")
    assert got and all(len(c.given) == 2 for c in got)
    assert all(hasattr(c, "suri_grade") for c in got)


def test_aho_briefing_has_no_suri_and_shows_type(charts):
    """아호 브리핑에 81수가 들어가면 안 된다 — 성이 없어 4격이 성립하지 않는다."""
    from backend.app.services.tool_service import _render_aho

    cands = N.recommend_aho(charts[2], top=12)
    brief = _render_aho({"kind": "aho", "surname": "",
                         "candidates": [c.model_dump(mode="json") for c in cands],
                         "deficient": N._deficient_elements(charts[2])})
    assert "81수" not in brief and "4격" not in brief
    assert "소처이호" in brief and "작호" in brief
    assert "퇴계" in brief          # 검증된 사례가 근거로 실린다
    assert "고전이 정한 4법" in brief   # 사칭 금지 문구가 프롬프트까지 전달된다
    assert len(brief) < 3000        # 프롬프트 예산 — 브리핑 비대로 답변이 잘린 전례가 있다


# ── blocklist 실효성 (감수 재확인 2026-07-22) ────────────────────────
def _all_combo_readings():
    lex = N.aho_lexicon()
    heads = [c for c in lex if c["role"] in ("head", "both")]
    tails = [c for c in lex if c["role"] in ("suffix", "both")]
    return {(a["reading"] or "") + (b.get("reading_tail") or b["reading"] or "")
            for a in heads for b in tails if a["char"] != b["char"]}


@pytest.mark.parametrize("bad", [
    "중풍", "사악", "야옹", "노루", "암담", "난산", "동사", "목사", "석사",
    "상사", "송사", "심사", "고사", "악운", "암초", "상해", "초상", "중상",
])
def test_dangerous_readings_blocked(bad):
    """1차 목록은 손으로 짜낸 것이라 이런 조합이 통째로 뚫려 있었다(실측 67개).
    중풍(中風)·동사(凍死)·목사(牧師)가 유료 아호 리포트에 실리면 치명적이다."""
    assert bad in N._AHO_BAD_READING, f"{bad} 가 차단 목록에서 빠졌다"


def test_no_dangerous_reading_reachable():
    """차단 목록이 **실제 생성 가능한 조합**을 덮는지 — 허수만 늘리면 의미가 없다."""
    combos = _all_combo_readings()
    for bad in ("중풍", "사악", "야옹", "목사", "동사", "우산", "난산"):
        if bad in combos:
            assert bad in N._AHO_BAD_READING


def test_overblocking_released():
    """靑山·白露·中山은 부정적 동음어가 없다(표준국어대사전 확인) — 막을 이유가 없다."""
    for ok in ("청산", "백로", "중산"):
        assert ok not in N._AHO_BAD_READING, f"{ok} 는 과잉 차단이다"


def test_attested_suffix_only_from_two_char_ho():
    """3~4자 호의 마지막 글자는 접미가 아니다.

    백운거사(白雲居士)에서 '士'만 떼면 居士가 한 단위인 걸 무시하는 것이고,
    그 결과 士가 +20 가산을 받아 목사·석사·동사·정사·상사가 상단을 점거했다."""
    suf = N._aho_attested_suffixes()
    assert "士" not in suf, "백운거사(4자)에서 士를 접미로 뽑으면 안 된다"
    assert "堂" not in suf, "여유당(3자)에서 堂을 접미로 뽑으면 안 된다"
    assert {"溪", "潭", "山", "隱"} <= suf, "2자 호의 접미는 남아야 한다"


def test_candidates_never_use_blocked_reading(charts):
    for ch in charts:
        for c in N.recommend_aho(ch, top=12):
            assert c.reading not in N._AHO_BAD_READING


def test_candidate_pool_still_sufficient(charts):
    """차단을 늘린 뒤에도 후보표가 비지 않아야 한다."""
    for ch in charts:
        assert len(N.recommend_aho(ch, top=8)) == 8
