"""사주 종합 엔진 — BirthInput → SajuChart."""
from __future__ import annotations

from .constants import STEM_TO_WUXING
from .daewoon import _previous_and_next_jieqi, compute_daewoon
from .pillars import compute_pillars
from .sinsal import gongmang, napeum, saryeong, twelve_life_stage, twelve_sinsal
from .types import BirthInput, SajuChart
from .wuxing import (
    collect_hidden_stems,
    compute_ten_gods,
    compute_wuxing,
    determine_strength,
)
from .yongsin import compute_johu_yongsin


def build_chart(birth: BirthInput, with_daewoon: bool = True) -> SajuChart:
    pillars, solar_d, solar_t, lunar_d, is_leap = compute_pillars(birth)
    wx_full, wx_branch = compute_wuxing(pillars)
    tg = compute_ten_gods(pillars)
    strength = determine_strength(pillars, wx_full)
    # 조후용신(궁통보감 일간×월지) — 결정적 계산값(LLM 환각 차단의 핵심 앵커)
    try:
        johu = compute_johu_yongsin(pillars.day.stem, pillars.month.branch)
    except Exception:  # noqa: BLE001 — 표 누락 등 방어(차트 생성은 계속)
        johu = None
    hidden = collect_hidden_stems(pillars)
    daewoon = compute_daewoon(pillars, birth.gender, solar_d) if with_daewoon else None

    # 십이운성(일간 기준)·십이신살(년지 기준)·공망(일주 기준)
    ds = pillars.day.stem
    yb = pillars.year.branch
    _cols = {"년": pillars.year, "월": pillars.month, "일": pillars.day, "시": pillars.hour}
    twelve_life = {k: twelve_life_stage(ds, p.branch) for k, p in _cols.items() if p}
    twelve_sin = {k: twelve_sinsal(yb, p.branch) for k, p in _cols.items() if p}
    gm = gongmang(ds, pillars.day.branch)
    napeum_map = {k: napeum(p.stem, p.branch)[0] for k, p in _cols.items() if p}

    # 사령(司令) — 절기 계산이 필요해 명식 표시용(with_daewoon)일 때만(택일 루프 성능 보호)
    saryeong_stem = ""
    if with_daewoon:
        try:
            from datetime import datetime as _dt
            prev_jq, _ = _previous_and_next_jieqi(solar_d)
            days_after = (_dt(solar_d.year, solar_d.month, solar_d.day) - prev_jq).total_seconds() / 86400.0
            saryeong_stem = saryeong(pillars.month.branch, days_after)
        except Exception:  # noqa: BLE001
            saryeong_stem = ""

    return SajuChart(
        input=birth,
        solar_date=solar_d,
        solar_time=solar_t,
        lunar_date=lunar_d,
        is_leap_month=is_leap,
        pillars=pillars,
        wuxing=wx_full,
        wuxing_branch_only=wx_branch,
        ten_gods=tg,
        day_master_element=STEM_TO_WUXING[pillars.day_master],
        day_master_strength=strength,
        daewoon=daewoon,
        hidden_stems=hidden,
        twelve_life=twelve_life,
        twelve_sinsal=twelve_sin,
        gongmang=gm,
        napeum=napeum_map,
        saryeong=saryeong_stem,
        johu_yongsin=johu,
    )
