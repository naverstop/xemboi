# -*- coding: utf-8 -*-
"""택일 학파선택 6항목 회귀 (학파조사 wf_wqlmz9ssc 권고 1안 반영, 2026-07-30).

① 십악대패(C설·라벨) ② 이사 印 옵션(기본 OFF) ③b 비겁 어드바이저리
④ 다층운 월운 soft/strict ⑤ 天德·月德귀인 가점 ⑥ 세운 자문.
"""
from __future__ import annotations

import contextlib
from datetime import date, timedelta

from backend.app.saju import taekil
from backend.app.saju.engine import build_chart
from backend.app.saju.taekil import (
    _CHEONWOLDEOK_BONUS,
    _cheon_wol_deok,
    _day_breaks_branch,
    _score_day,
    _sewoon_advisory,
    _SIBAK_TAEPAE,
    recommend_dates,
)
from backend.app.saju.types import BirthInput, CalendarType, Gender


def _chart(y, m, d, gender, t="12:00"):
    return build_chart(BirthInput(birth_date=date(y, m, d), birth_time=t,
                                  calendar=CalendarType.SOLAR, gender=gender))


@contextlib.contextmanager
def _opts(**over):
    """TAEKIL_OPTIONS 임시 오버라이드(복원 보장)."""
    old = dict(taekil.TAEKIL_OPTIONS)
    taekil.TAEKIL_OPTIONS.update(over)
    try:
        yield
    finally:
        taekil.TAEKIL_OPTIONS.clear()
        taekil.TAEKIL_OPTIONS.update(old)


def _find_day(pred, start=date(2026, 1, 1), span=365):
    """조건(pred(ds, db)=True)을 만족하는 첫 날짜의 (date, ds, db)."""
    for i in range(span):
        d = start + timedelta(days=i)
        ch = build_chart(BirthInput(birth_date=d), with_daewoon=False)
        ds, db = ch.pillars.day.stem, ch.pillars.day.branch
        if pred(ds, db):
            return d, ds, db
    raise AssertionError("조건 만족 날짜 없음")


# ── ⑤ 天德·月德귀인 표(코퍼스 완전일치) ───────────────────────────
def test_cheon_wol_deok_table():
    # 天德 천간형: 寅월 → 丁(천간). 일간 丁이면 천덕귀인.
    assert "천덕귀인" in _cheon_wol_deok("寅", "丁", "子")
    # 天德 지지형(왕지월): 卯월 → 申(지지). 일지 申이면 천덕귀인.
    assert "천덕귀인" in _cheon_wol_deok("卯", "乙", "申")
    # 月德: 午월(寅午戌 삼합 →丙). 일간 丙이면 월덕귀인(천덕 午→亥는 일지 子라 미해당).
    assert _cheon_wol_deok("午", "丙", "子") == ["월덕귀인"]
    # 卯월 月德=甲 (코퍼스 OCR 교정, 卯→申 오류 배제).
    assert "월덕귀인" in _cheon_wol_deok("卯", "甲", "子")
    # 무관한 날은 빈 목록.
    assert _cheon_wol_deok("寅", "戊", "子") == []


def test_cheonwoldeok_bonus_applied():
    # 천월덕 성립일을 찾아 결혼택일에서 on/off 점수를 비교(소폭 가점).
    ch0 = None
    for i in range(365):
        dd = date(2026, 1, 1) + timedelta(days=i)
        c = build_chart(BirthInput(birth_date=dd), with_daewoon=False)
        if _cheon_wol_deok(c.pillars.month.branch, c.pillars.day.stem, c.pillars.day.branch):
            ch0 = dd
            break
    assert ch0 is not None, "천월덕 성립일 없음"
    user = _chart(1990, 3, 3, Gender.MALE)
    with _opts(cheonwoldeok_bonus=False, month_luck_mode="off"):
        base = _score_day(ch0, user, "wedding").score
    with _opts(cheonwoldeok_bonus=True, month_luck_mode="off"):
        boosted = _score_day(ch0, user, "wedding")
    # 하드배제(disq)만 아니면 정확히 +_CHEONWOLDEOK_BONUS 가점(정량 잠금). disq면 둘 다 동일(가점 스킵).
    if "회피" not in boosted.reason:
        assert boosted.score == base + _CHEONWOLDEOK_BONUS
        assert "귀인" in boosted.reason


def test_cheonwoldeok_skipped_when_disq():
    # ⑤ 형충취소(음성경로): 천월덕일이라도 그날 일지 등이 깨져 disq면 가점을 스킵한다(문헌 '형충되면 무력').
    #   천월덕 AND 일지 깨짐(_disq)인 결정적 날을 찾아 base==boosted(가점 없음)를 잠근다.
    user = _chart(1990, 3, 3, Gender.MALE)
    ub = user.pillars.day.branch
    target = None
    for i in range(365):
        dd = date(2026, 1, 1) + timedelta(days=i)
        c = build_chart(BirthInput(birth_date=dd), with_daewoon=False)
        db = c.pillars.day.branch
        if _cheon_wol_deok(c.pillars.month.branch, c.pillars.day.stem, db) and _day_breaks_branch(db, ub):
            target = dd
            break
    assert target is not None, "천월덕 AND 일지깨짐 날 없음"
    with _opts(cheonwoldeok_bonus=False, month_luck_mode="off"):
        base = _score_day(target, user, "wedding")
    with _opts(cheonwoldeok_bonus=True, month_luck_mode="off"):
        boosted = _score_day(target, user, "wedding")
    assert "회피" in boosted.reason           # disq → 회피 사유
    assert boosted.score == base.score        # 가점 스킵(형충 무력)


# ── ① 십악대패일(C설·라벨, 하드배제 금지) ─────────────────────────
def test_sibak_taepae_set():
    assert _SIBAK_TAEPAE == frozenset(
        {"甲辰", "乙巳", "丙申", "丁亥", "戊戌", "己丑", "庚辰", "辛巳", "壬申", "癸亥"})
    assert len(_SIBAK_TAEPAE) == 10


def test_sibak_taepae_label_and_penalize():
    d, ds, db = _find_day(lambda s, b: f"{s}{b}" in _SIBAK_TAEPAE)
    user = _chart(1990, 3, 3, Gender.MALE)
    with _opts(sibak_taepae_mode="off", month_luck_mode="off"):
        off = _score_day(d, user, "general")
    with _opts(sibak_taepae_mode="label", month_luck_mode="off"):
        lab = _score_day(d, user, "general")
    with _opts(sibak_taepae_mode="penalize", month_luck_mode="off"):
        pen = _score_day(d, user, "general")
    # 라벨 모드: 경고 배지는 붙되 점수는 off와 동일(감점 0).
    assert any("십악대패" in w for w in lab.warnings)
    assert not any("십악대패" in w for w in off.warnings)
    assert lab.score == off.score
    # penalize 모드: 소폭 감점(하드배제 아님 — 0으로 떨어지지 않음).
    assert pen.score < lab.score
    assert pen.score > 0


# ── ② 이사 인수(印) 보호 옵션(기본 OFF) ───────────────────────────
def test_insu_option_default_off():
    user = _chart(1988, 5, 20, Gender.MALE)
    with _opts(moving_protect_insu=False):
        r = recommend_dates(user, date(2026, 8, 1), days=60, purpose="moving")
    assert not any("인수" in w for d in (r.best + r.avoid) for w in d.warnings), \
        "기본값(OFF)인데 인수 경고가 붙음"


def test_insu_option_on_can_flag():
    user = _chart(1988, 5, 20, Gender.MALE)
    with _opts(moving_protect_insu=True, month_luck_mode="off"):
        on = recommend_dates(user, date(2026, 8, 1), days=90, purpose="moving")
    with _opts(moving_protect_insu=False, month_luck_mode="off"):
        off = recommend_dates(user, date(2026, 8, 1), days=90, purpose="moving")
    on_has = any("인수" in w for d in (on.best + on.alt + on.avoid) for w in d.warnings)
    off_has = any("인수" in w for d in (off.best + off.alt + off.avoid) for w in d.warnings)
    # 이 fixture(1988-05-20 남)는 원국 인수 보유가 결정적 → ON에서 인수 경고가 떠야 하고 OFF는 없어야 한다.
    #   (taekil.py checks.append(("인수",...)) 제거 회귀를 실제로 포착.)
    assert on_has and not off_has


# ── ③b 비겁 어드바이저리(비배제) vs penalize(구 배제형) ───────────
def test_bigyeop_advisory_not_hard_excluded():
    # 전체 기간에서 비겁일 라벨이 표시되고, 비겁 '단독'일(하드배제 아님)은 회피 처리되지 않아야 한다.
    #   ⚠️ best/avoid만 보면 하드깨짐 비겁일만 잡혀 오판(가중치·명식에 취약) → 전 스코어 집합에서 검사.
    user = _chart(1992, 3, 15, Gender.FEMALE)
    with _opts(wedding_bigyeop_mode="advisory", month_luck_mode="off"):
        scored = [_score_day(date(2026, 8, 1) + timedelta(days=i), user, "wedding") for i in range(120)]
    bigyeop = [d for d in scored if any("비겁일" in w for w in d.warnings)]
    assert bigyeop, "비겁일 라벨 미표시"
    # score>44 ⟹ 하드배제(_disq→min(score,44)) 아님 = 비겁 단독. 이런 날이 존재하고 회피가 아니어야 한다.
    advisory_ok = [d for d in bigyeop if d.score > 44 and not d.reason.startswith("회피")]
    assert advisory_ok, "비겁 단독일이 전부 배제됨(어드바이저리 강등 실패)"


def test_bigyeop_penalize_restores_exclusion():
    user = _chart(1992, 3, 15, Gender.FEMALE)
    with _opts(wedding_bigyeop_mode="advisory", month_luck_mode="off"):
        adv = recommend_dates(user, date(2026, 8, 1), days=120, purpose="wedding")
    with _opts(wedding_bigyeop_mode="penalize", month_luck_mode="off"):
        pen = recommend_dates(user, date(2026, 8, 1), days=120, purpose="wedding")
    # penalize에선 비겁일이 '비겁(연적…)' 회피 사유로 등장(bad 경로).
    pen_bad = any("비겁(연적" in " ".join(d.reason for d in (pen.best + pen.avoid)) for _ in [0])
    assert pen_bad
    # advisory에선 그 회피 문구가 없다.
    assert "비겁(연적" not in " ".join(d.reason for d in (adv.best + adv.avoid))


# ── ④ 다층운 월운 soft / strict ───────────────────────────────────
def test_month_luck_soft_lowers_and_labels():
    user = _chart(1988, 5, 20, Gender.MALE)
    day = date(2026, 8, 10)   # 申월(원국 월지·일지·재와 충돌하는 흉월)
    with _opts(month_luck_mode="off"):
        off = _score_day(day, user, "moving")
    with _opts(month_luck_mode="soft"):
        soft = _score_day(day, user, "moving")
    assert any("월운 흉월" in w for w in soft.warnings), "월운 흉월 배지 미표시"
    assert soft.score <= off.score, "soft 월운이 흉월 점수를 낮추지 않음"


def test_month_luck_strict_hard_excludes():
    user = _chart(1988, 5, 20, Gender.MALE)
    day = date(2026, 8, 10)   # 이 명식·이 절기월은 원국 월지를 깨는 흉월(재검증 실측)
    with _opts(month_luck_mode="soft"):
        soft = _score_day(day, user, "moving")
    assert any(("월운 흉월" in w and "월지" in w) for w in soft.warnings), "전제: 월지 깨짐 흉월이어야 함"
    with _opts(month_luck_mode="strict"):
        strict = _score_day(day, user, "moving")
    assert strict.score <= 44   # strict → 월지 깨진 달은 하드배제


# ── ⑥ 세운 자문(무점수) ──────────────────────────────────────────
def test_sewoon_advisory_fn():
    user = _chart(1988, 5, 20, Gender.MALE)
    um = user.pillars.month.branch
    # '충' 분기: 원국 월지를 충하는 지지(인덱스+6)를 세운으로 → '발동한 해' 문구.
    from backend.app.saju.constants import EARTHLY_BRANCHES
    opp = EARTHLY_BRANCHES[(EARTHLY_BRANCHES.index(um) + 6) % 12]
    note = _sewoon_advisory(user, opp, "moving", 2030)
    assert "2030" in note and "이사運" in note and "충" in note
    # '합' 분기: 월지와 육합·무깨짐인 세운 지지 → '가도 되고 안 가도' 문구.
    user2 = _chart(1990, 6, 6, Gender.MALE)
    assert user2.pillars.month.branch == "午"    # 전제(월지 午 → 육합 未)
    note2 = _sewoon_advisory(user2, "未", "wedding", 2033)
    assert "합해" in note2 and "서두를 필요" in note2 and "결혼運" in note2 and "가도 되고" in note2


def test_sewoon_note_wired_in_result():
    # ⑥ wiring 잠금: 세운 지지가 원국 월지를 깨는 시작연도(2031: 년지 亥, 원국 월지 巳 → 巳亥충)로 강제.
    user = _chart(1988, 5, 20, Gender.MALE)
    assert user.pillars.month.branch == "巳"      # 전제
    start = date(2031, 3, 1)
    with _opts(sewoon_advisory=True):
        r = recommend_dates(user, start, days=30, purpose="moving")
    assert r.sewoon_note != "" and "이사運" in r.sewoon_note and "2031" in r.sewoon_note
    with _opts(sewoon_advisory=False):
        r2 = recommend_dates(user, start, days=30, purpose="moving")
    assert r2.sewoon_note == ""   # 게이트 OFF → 빈 문자열


def test_sewoon_note_year_matches_branch_pre_ipchun():
    # 재검증 wwh751a42 MEDIUM 회귀락: 입춘 전 시작일이어도 라벨연도의 세운 지지로 판정해야 한다.
    #   과거 버그: start=2026-01-15가 전년(2025) 세운 지지로 '올해(2026)…발동' 거짓문구 생성.
    user = _chart(1988, 5, 20, Gender.MALE)   # 월지 巳
    with _opts(sewoon_advisory=True):
        r = recommend_dates(user, date(2026, 1, 15), days=30, purpose="moving")
    # 2026 세운 지지=午(丙午), 午-巳 무깨짐 → 빈 문구(전년 巳의 巳亥충을 2026으로 오라벨하면 안 됨).
    assert r.sewoon_note == ""


# ── ⑥ 6팩터 가중치 뽀-정합 재조정 ────────────────────────────────
def test_weights_saju_dominant_and_sum100():
    from backend.app.saju.taekil import _PURPOSE_WEIGHTS, PERSPECTIVES
    # 채택관법(뽀 A설) 정합: 뽀 택일이 다루는 용도는 saju가 최상위 비중, 전 용도 합 100.
    for p, w in _PURPOSE_WEIGHTS.items():
        assert sum(w.values()) == 100, (p, sum(w.values()))
    for p in ("wedding", "birth", "moving", "opening", "contract", "surgery", "general"):
        w = _PURPOSE_WEIGHTS[p]
        assert w["saju"] == max(w.values()), f"{p}: saju가 최상위 비중이 아님 {w}"
    # 사주(뽀) 중심 관점(P) 신설 — saju 최상위.
    assert "P" in PERSPECTIVES and PERSPECTIVES["P"]["weights"]["saju"] == max(PERSPECTIVES["P"]["weights"].values())
    assert sum(PERSPECTIVES["P"]["weights"].values()) == 100


def test_unknown_hour_smoke():
    # 시 모름(birth_time 미입력) 명식으로도 전 관법이 예외 없이 계산돼야 한다(HIDDEN_STEMS/시주 null guard).
    ch = build_chart(BirthInput(birth_date=date(1991, 7, 7), calendar=CalendarType.SOLAR, gender=Gender.FEMALE))
    assert ch.pillars.hour is None
    for purpose in ("wedding", "moving", "opening", "general", "birth"):
        r = recommend_dates(ch, date(2026, 8, 1), days=30, purpose=purpose)
        assert isinstance(r.best, list) and isinstance(r.alt, list)


# ── ③a 커플 정밀택일(상대 명식) ──────────────────────────────────
_GROOM = (1990, 3, 15, Gender.MALE)
_BRIDE = (1988, 9, 9, Gender.FEMALE)


def test_couple_applied_rule_label():
    u, p = _chart(*_GROOM), _chart(*_BRIDE)
    assert recommend_dates(u, date(2026, 8, 1), days=30, purpose="wedding").applied_rule.startswith("편법")
    assert recommend_dates(u, date(2026, 8, 1), days=30, purpose="wedding",
                           user_chart2=p).applied_rule.startswith("정식")
    with _opts(wedding_couple_mode=False):   # 관리자 토글 OFF → 상대명식 있어도 단인
        assert recommend_dates(u, date(2026, 8, 1), days=30, purpose="wedding",
                               user_chart2=p).applied_rule.startswith("편법")


def test_couple_both_bigyeop_hard_excluded():
    # 양측(신랑·신부) 동시 비겁일은 하드배제, 단인(본인 비겁)은 어드바이저리(배제 아님).
    u, p = _chart(*_GROOM), _chart(*_BRIDE)
    with _opts(wedding_couple_mode=True, month_luck_mode="off", wedding_bigyeop_mode="advisory"):
        couple = _score_day(date(2026, 1, 3), u, "wedding", parent2_chart=p)
        single = _score_day(date(2026, 1, 3), u, "wedding")
    assert any("양측 비겁" in w for w in couple.warnings)
    assert couple.score <= 44                     # 양측 동시 비겁 → 하드배제
    assert not any("양측 비겁" in w for w in single.warnings)
    assert single.score > 44                      # 단인은 비겁만으론 배제 안 됨


def test_couple_both_bigyeop_hard_excluded_even_when_mode_off():
    # 양측 동시 비겁 하드배제 = A설 문헌 근거 → 단인용 wedding_bigyeop_mode='off'에도 유지돼야 한다.
    #   ('양측 비겁일' 라벨은 커플 양측 분기에서만 나오므로 그 존재가 분기 실행을 증명 = fix 회귀락.)
    u, p = _chart(*_GROOM), _chart(*_BRIDE)
    with _opts(wedding_couple_mode=True, month_luck_mode="off", wedding_bigyeop_mode="off"):
        couple = _score_day(date(2026, 1, 3), u, "wedding", parent2_chart=p)
    assert any("양측 비겁" in w for w in couple.warnings)
    assert couple.score <= 44


def test_couple_partner_break_excludes_otherwise_clean_day():
    # 본인은 깨끗한데 상대 명식이 깨져 커플에서만 배제되는 날이 실재해야 한다(상대 하드 판정 배선).
    u, p = _chart(*_GROOM), _chart(*_BRIDE)
    found = None
    with _opts(wedding_couple_mode=True, month_luck_mode="off"):
        for i in range(120):
            d = date(2026, 8, 1) + timedelta(days=i)
            single = _score_day(d, u, "wedding")
            couple = _score_day(d, u, "wedding", parent2_chart=p)
            if single.score > 44 and couple.score <= 44 and any("상대" in w for w in couple.warnings):
                found = (d, single.score, couple.score); break
    assert found, "상대 명식 깨짐으로 커플에서만 배제되는 날을 찾지 못함"


def test_couple_simultaneous_hap_bonus():
    # 신랑 재·신부 관이 그날 일진과 '동시에 合'되는 날 = 최고 길일 가점(단인 합보다 큼).
    u, p = _chart(1979, 12, 1, Gender.MALE), _chart(1983, 8, 8, Gender.FEMALE)
    with _opts(wedding_couple_mode=True, month_luck_mode="off"):
        couple = _score_day(date(2026, 2, 16), u, "wedding", parent2_chart=p)
        single = _score_day(date(2026, 2, 16), u, "wedding")
    assert "양측 재·관 동시 합" in couple.reason
    assert couple.score > single.score            # 동시 合 가점(+18) > 단인 合(+12)


def test_couple_single_path_regression():
    # 상대 명식이 없으면 커플 토글과 무관하게 단인 결과가 동일해야 한다(단인 경로 불변).
    u = _chart(*_GROOM)
    with _opts(wedding_couple_mode=True):
        on = [b.date for b in recommend_dates(u, date(2026, 8, 1), days=60, purpose="wedding").best]
    with _opts(wedding_couple_mode=False):
        off = [b.date for b in recommend_dates(u, date(2026, 8, 1), days=60, purpose="wedding").best]
    assert on == off
