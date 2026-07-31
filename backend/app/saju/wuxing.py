"""오행 분포, 십성 매핑, 지장간, 신강/신약 판별."""
from __future__ import annotations

from typing import Literal

from .constants import (
    BRANCH_TO_WUXING,
    HIDDEN_STEMS,
    STEM_TO_WUXING,
    compute_ten_god,
)
from .types import (
    FourPillars,
    TenGodAssignment,
    WuxingDistribution,
)

_EL_TO_FIELD = {"木": "wood", "火": "fire", "土": "earth", "金": "metal", "水": "water"}


def _add(dist: dict[str, int], elem: str, n: int = 1) -> None:
    dist[_EL_TO_FIELD[elem]] += n


def compute_wuxing(pillars: FourPillars) -> tuple[WuxingDistribution, WuxingDistribution]:
    """
    오행 분포 두 가지를 반환:
      1) full: 천간(가중치 1) + 지지 본기(1) + 지지 지장간 여기/중기(0.5 → 정수로 합산위해 2배 스케일)
      2) branch_only: 지지 본기만
    여기서는 단순화를 위해 모두 정수 가중치 1로 합산하고,
    `full`은 천간 + 지지 본기 + 지지 지장간 전체(여기/중기/정기) 카운트.
    `branch_only`는 지지 본기(=BRANCH_TO_WUXING)만.
    """
    full = WuxingDistribution().model_dump()
    branch_only = WuxingDistribution().model_dump()

    for s in pillars.all_stems():
        _add(full, STEM_TO_WUXING[s])

    for b in pillars.all_branches():
        elem_main = BRANCH_TO_WUXING[b]
        _add(branch_only, elem_main)
        _add(full, elem_main)
        # 지장간 추가 (정기 제외 - 정기는 BRANCH_TO_WUXING 과 동일하므로 중복 방지)
        hidden = HIDDEN_STEMS[b]
        for hs in hidden[:-1]:   # 마지막은 정기(이미 카운트됨)
            _add(full, STEM_TO_WUXING[hs])

    return WuxingDistribution(**full), WuxingDistribution(**branch_only)


def compute_ten_gods(pillars: FourPillars) -> TenGodAssignment:
    dm = pillars.day_master

    def br_main_god(branch: str) -> str:
        # 지지의 정기(正氣) 천간을 기준으로 십성 산출
        main_stem = HIDDEN_STEMS[branch][-1]
        return compute_ten_god(dm, main_stem)

    return TenGodAssignment(
        year_stem=compute_ten_god(dm, pillars.year.stem),
        month_stem=compute_ten_god(dm, pillars.month.stem),
        hour_stem=compute_ten_god(dm, pillars.hour.stem) if pillars.hour else None,
        year_branch=br_main_god(pillars.year.branch),
        month_branch=br_main_god(pillars.month.branch),
        day_branch=br_main_god(pillars.day.branch),
        hour_branch=br_main_god(pillars.hour.branch) if pillars.hour else None,
    )


#: 월령(月令) 득령 가중치 — 월지 본기는 신강/신약의 핵심(적천수 억부론).
#: 단순 개수합산이 놓치던 '득령/실령'을 월지 오행에 추가 비중으로 반영한다.
#: (월지 본기는 wuxing_full 에 이미 1회 계산됨 → 여기에 +MONTH_RULING_WEIGHT 로 강조)
MONTH_RULING_WEIGHT = 3


def determine_strength(
    pillars: FourPillars,
    wuxing_full: WuxingDistribution,
) -> Literal["strong", "weak", "neutral"]:
    """
    신강/신약 판별 — 오행 개수 + 월령(月令) 득령 가중.

    일간을 돕는 오행(같은 오행=비겁, 일간을 생하는 오행=인성)의 점수가
    설기/극하는 오행(식상/재성/관성)보다 우세하면 신강. 여기에 월지 본기가
    일간을 돕는지(득령) 여부를 핵심 가중으로 반영한다.

    근거: 명리에서 월령(월지)은 강약 판정의 가장 큰 변수(득령/실령). 단순 개수합산만으로는
          월지 비중이 과소평가되어 억부용신 방향이 어긋난다 → 월지 본기에 MONTH_RULING_WEIGHT 가중.
    학파별 정밀 분석(통근·투간 등)은 LLM/조후가 보완. 여기서는 빠르고 일관된 분류용.
    """
    dm_elem = STEM_TO_WUXING[pillars.day_master]
    # 일간을 생하는 오행: WUXING_GENERATES 의 역
    from .constants import BRANCH_TO_WUXING, WUXING_GENERATES
    gen_to_me = {v: k for k, v in WUXING_GENERATES.items()}[dm_elem]
    helpers = {dm_elem, gen_to_me}   # 일간을 돕는 오행(비겁 + 인성)

    counts = wuxing_full.model_dump()
    support = counts[_EL_TO_FIELD[dm_elem]] + counts[_EL_TO_FIELD[gen_to_me]]
    total = wuxing_full.total()
    drain = total - support

    # 월령 득령 가중 — 월지 본기가 일간을 도우면 득령(강), 아니면 실령(약)
    month_elem = BRANCH_TO_WUXING[pillars.month.branch]
    if month_elem in helpers:
        support += MONTH_RULING_WEIGHT
    else:
        drain += MONTH_RULING_WEIGHT

    if support >= drain * 1.2:
        return "strong"
    if drain >= support * 1.2:
        return "weak"
    return "neutral"


def collect_hidden_stems(pillars: FourPillars) -> dict[str, list[str]]:
    """주별 지지의 지장간 목록 반환 (출력/설명용)."""
    result: dict[str, list[str]] = {}
    label_branch = {
        "년지": pillars.year.branch,
        "월지": pillars.month.branch,
        "일지": pillars.day.branch,
    }
    if pillars.hour:
        label_branch["시지"] = pillars.hour.branch
    for label, br in label_branch.items():
        result[label] = list(HIDDEN_STEMS[br])
    return result
