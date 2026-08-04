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


def compute_wuxing_eight(pillars: FourPillars) -> WuxingDistribution:
    """팔자(八字) 8글자 기준 오행 개수 — 천간4 + 지지 '본기'4 (합 8, 시 모름이면 6).

    [2026-07-22 운영자 지적] 화면 명식표의 오행 막대가 full(천간+지지본기+지장간 여기·중기, 합 14)
    을 그려 사용자가 읽는 8글자와 어긋났다. 예: 시丁卯·일己丑·월壬寅·년壬子 는 팔자에 금(金)이
    하나도 없는데 화면·프롬프트는 '금 1'(丑 중기 辛)로 표시 → LLM 이 없는 금을 있다고 서술.

    ⚠️ 이 분포는 **표시·프롬프트 전용**이다. 신강/신약(determine_strength)은 지장간 통근을 반영해야
    하는 억부 정설이라 계속 full 을 쓴다. 여기를 강약에 넣으면 중화(neutral)가 수학적으로 0%가 되고
    판정이 대량 뒤집힌다(시뮬 3만건: strong 25.6%→40.2%, neutral 16.3%→0%).
    """
    d = WuxingDistribution().model_dump()
    for s in pillars.all_stems():
        _add(d, STEM_TO_WUXING[s])
    for b in pillars.all_branches():
        _add(d, BRANCH_TO_WUXING[b])
    return WuxingDistribution(**d)


def wuxing_eight_of(chart) -> WuxingDistribution:
    """차트에서 팔자8 분포를 얻는다 — 필드가 없는 '옛 저장 chart_json' 도 pillars 로 즉시 재계산.

    저장된 세션(chat_sessions.chart_json / compat a·b / tool_sessions)에는 wuxing_eight 가 없으므로
    마이그레이션 없이도 항상 올바른 값이 나오게 한다.
    """
    w = getattr(chart, "wuxing_eight", None)
    return w if w is not None else compute_wuxing_eight(chart.pillars)


def wuxing_eight_ko_from_json(chart_json: dict) -> dict[str, int]:
    """저장된 chart_json(dict) → 팔자8 오행 개수(한글 키). pillars 만 있으면 동작.

    실패 시 빈 dict 를 돌려 호출부가 기존 표기로 안전하게 폴백하도록 한다.
    """
    try:
        p = (chart_json or {}).get("pillars") or {}
        ko = {"木": "목", "火": "화", "土": "토", "金": "금", "水": "수"}
        out = {"목": 0, "화": 0, "토": 0, "금": 0, "수": 0}
        for pos in ("year", "month", "day", "hour"):
            pil = p.get(pos)
            if not pil:
                continue
            st, br = pil.get("stem"), pil.get("branch")
            if st in STEM_TO_WUXING:
                out[ko[STEM_TO_WUXING[st]]] += 1
            if br in BRANCH_TO_WUXING:
                out[ko[BRANCH_TO_WUXING[br]]] += 1
        return out if sum(out.values()) else {}
    except Exception:  # noqa: BLE001 — 표시용 보조값이라 실패해도 답변 생성을 막지 않는다
        return {}


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
