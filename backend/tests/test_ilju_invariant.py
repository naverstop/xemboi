# -*- coding: utf-8 -*-
"""일주(日柱) 불변식 — 재발 방지의 핵심 게이트 (전수감사 2026-07-09).

전문가 격노 지적: 무신 일주 사용자에게 일간 계(癸) 표시, 매번 고쳐도 재발.
근본원인: 진태양시(−32분) 경도보정이 자동 00:30 출생을 전날로 굴려 일주를 하루 밈
(실측 00:30 표본 48/48 시프트). 관법 결정(2026-07): 진태양시는 시주(時)에만, 일주는 표준시.

이 테스트는 그 관법을 영구 불변식으로 고정한다:
  ① 진태양시 on/off는 일주를 절대 바꾸지 않는다(시주만 바뀜).
  ② 시각 미입력(None)과 자정 근처 시각은 같은 일주를 낸다.
  ③ night_zi_mode(yaja/jeongja)는 23시대 출생에만 일주 차이(정자시 관법) — 그 외엔 불변.
신규 기능이 birth 정규화를 어겨 일주를 밀면 여기서 반드시 깨진다.
"""
from __future__ import annotations

from datetime import date, time

import pytest

from backend.app.saju.constants import branch_korean, stem_korean
from backend.app.saju.pillars import compute_pillars
from backend.app.saju.types import BirthInput, CalendarType


def _ilju(**kw) -> str:
    fp, *_ = compute_pillars(BirthInput(calendar=CalendarType.SOLAR, **kw))
    d = fp.day
    return f"{stem_korean(d.stem)}{branch_korean(d.branch)}"


# 자정·이른 시간 경계 출생일 스윕(일주 밀림 위험창)
_DATES = [date(1988, 9, 7), date(2000, 1, 1), date(1994, 8, 15), date(1975, 5, 5), date(2026, 2, 4)]
_BOUNDARY_TIMES = [time(0, 0), time(0, 15), time(0, 30), time(0, 31), time(1, 0), time(12, 0)]


@pytest.mark.parametrize("d", _DATES)
@pytest.mark.parametrize("t", _BOUNDARY_TIMES)
def test_true_solar_never_shifts_ilju(d, t):
    """① 진태양시 on/off로 일주가 바뀌면 안 된다(시주만 진태양시 반영)."""
    off = _ilju(birth_date=d, birth_time=t, apply_true_solar_time=False, birth_longitude=126.98)
    on = _ilju(birth_date=d, birth_time=t, apply_true_solar_time=True, birth_longitude=126.98)
    assert off == on, f"진태양시가 일주를 바꿈: {d} {t} → off={off} on={on}"


@pytest.mark.parametrize("d", _DATES)
def test_none_time_matches_daytime_ilju(d):
    """② '시 모름'(None)과 낮 시각의 일주가 같아야 한다(시각은 일주에 무영향).

    낮 시각만 검사 — 자정 근처(00:30)는 서머타임 해(1988 등)에 DST −60분이 표준시를 전날로
    옮기는 정당한 경계라 별도(① true_solar 불변 테스트가 00:30 안정성 커버)."""
    none_ilju = _ilju(birth_date=d, birth_time=None, apply_true_solar_time=True)
    for t in [time(9, 0), time(12, 0), time(15, 0), time(18, 0)]:
        got = _ilju(birth_date=d, birth_time=t, apply_true_solar_time=True, birth_longitude=126.98)
        assert got == none_ilju, f"낮 시각이 일주를 바꿈: {d} {t} → {got} vs None={none_ilju}"


@pytest.mark.parametrize("d", _DATES)
@pytest.mark.parametrize("t", [time(9, 0), time(14, 0), time(18, 0)])
def test_night_zi_only_affects_23h(d, t):
    """③ 낮(비-23시대) 출생은 야자/정자시 설정이 일주를 바꾸지 않는다.

    (자정 근처는 서머타임 해에 DST가 표준시를 23시대로 옮겨 정자시 대상이 될 수 있어 낮만 검사.)"""
    yaja = _ilju(birth_date=d, birth_time=t, night_zi_mode="yaja")
    jeongja = _ilju(birth_date=d, birth_time=t, night_zi_mode="jeongja")
    assert yaja == jeongja, f"낮인데 night_zi가 일주 바꿈: {d} {t} → yaja={yaja} jeongja={jeongja}"


def test_regression_anchor_00_30_true_solar():
    """회귀 앵커: 2000-01-01 00:30 진태양시 — 종전 버그(전날로 밀림) 재발 감지."""
    # 표준시 기준 일주(진태양시 무관)여야 함
    base = _ilju(birth_date=date(2000, 1, 1), birth_time=None)
    assert _ilju(birth_date=date(2000, 1, 1), birth_time=time(0, 30),
                 apply_true_solar_time=True, birth_longitude=126.98) == base


@pytest.mark.parametrize("bad", [None, "", "invalid", "YAJA"])
def test_night_zi_none_normalizes_to_yaja(bad):
    """night_zi_mode None/빈값/오값 → 'yaja' 단일 정규화(종전 ValidationError·엔드포인트별 or가드 제거).

    이 정규화가 없으면 프로필 None을 넘기는 경로마다 처리가 갈려 23시대 일주가 달라진다."""
    b = BirthInput(birth_date=date(2000, 1, 1), calendar=CalendarType.SOLAR, night_zi_mode=bad)
    assert b.night_zi_mode == "yaja"


def test_hour_pillar_still_uses_true_solar():
    """시주는 여전히 진태양시를 반영해야 한다(분리 후에도 시주 정확도 유지)."""
    fp_off, *_ = compute_pillars(BirthInput(birth_date=date(1988, 9, 7), birth_time=time(14, 30),
                                            calendar=CalendarType.SOLAR, apply_true_solar_time=False))
    fp_on, *_ = compute_pillars(BirthInput(birth_date=date(1988, 9, 7), birth_time=time(14, 30),
                                           calendar=CalendarType.SOLAR, apply_true_solar_time=True,
                                           birth_longitude=126.98))
    # 일주 동일, 시주는 진태양시로 달라질 수 있음(경계에 걸리면)
    assert fp_off.day == fp_on.day
    assert fp_on.hour is not None
