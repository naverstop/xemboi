"""궁합(宮合) 엔진 — 두 사주명식(SajuChart) → 5요소 근거점수 + 관법별 종합.

설계 원칙(2026-06 확정):
  - 관법은 정답이 없다 → 우리가 가중치 하나를 강요하지 않는다.
  - **요소별 근거점수(일지·일간·오행상보·십성·신살)는 관법 중립으로 1회만 산출**하고,
    관법(A/B/C)은 그 점수에 곱하는 **가중치**만 다르다.
  - 충=가점 아닌 별도 감점, 일지는 육합>삼합, 도화는 길흉을 정하지 않고 양면 처리.

출력 CompatResult는 프론트의 펜타곤(perspectives[*].contributions 3겹) + 게이지 + 근거카드를 모두 지원.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .constants import (
    BRANCH_BREAK,
    BRANCH_CONFLICTS,
    BRANCH_GWIMUN,
    BRANCH_HARM,
    BRANCH_PUNISH,
    BRANCH_SELF_PUNISH,
    BRANCH_SIX_COMBINATIONS,
    BRANCH_TRIPLE_COMBINATIONS,
    BRANCH_WONJIN,
    DOHWA_BY_TRINE,
    HIDDEN_STEMS,
    STEM_COMBINATIONS,
    STEM_CONFLICTS,
    STEM_TO_WUXING,
    TEN_GODS_KO,
    WUXING_KOREAN,
    branch_korean,
    compute_ten_god,
    stem_korean,
)
from .types import SajuChart

# 오행 한자 → WuxingDistribution 속성명
_WX_ATTR = {"木": "wood", "火": "fire", "土": "earth", "金": "metal", "水": "water"}

# 관법별 가중치 (합 100). 리서치 기반 기본값, config로 조정 가능.
PERSPECTIVES: dict[str, dict] = {
    "A": {
        "label": "결혼·부부궁 중시",
        "weights": {"day_branch": 31, "day_stem": 18, "wuxing": 26, "ten_god": 13, "sinsal": 12},
    },
    "B": {
        "label": "균형",
        "weights": {"day_branch": 27, "day_stem": 22, "wuxing": 27, "ten_god": 12, "sinsal": 12},
    },
    "C": {
        "label": "연애·끌림 중시",
        "weights": {"day_branch": 22, "day_stem": 27, "wuxing": 22, "ten_god": 14, "sinsal": 15},
    },
}

# 십성(한자) → 궁합 점수(정배우자 正官/正財가 최고)
_TEN_GOD_SCORE = {
    "正官": 90, "正財": 90,
    "偏財": 75, "偏官": 75,
    "正印": 70, "偏印": 68,
    "食神": 65, "傷官": 55,
    "比肩": 50, "劫財": 45,
}


# ============================================================
# 출력 모델
# ============================================================
class FactorItem(BaseModel):
    type: str                       # "천간합", "지지충", "원진" 등
    detail: str                     # 사람이 읽는 근거 문구
    sign: int = 0                   # +1 가점 / -1 감점 / 0 중립


class Factor(BaseModel):
    key: str                        # day_branch | day_stem | wuxing | ten_god | sinsal
    label: str
    score: int                      # 0~100 (관법 중립)
    items: list[FactorItem] = Field(default_factory=list)


class Penalty(BaseModel):
    type: str
    detail: str


class Perspective(BaseModel):
    key: str                        # A | B | C
    label: str
    weights: dict[str, int]
    contributions: dict[str, float] # 축별 가중기여도(=score*weight/100) → 펜타곤 폴리곤
    total: int                      # 종합점수 0~100
    grade: str
    interpretation: str


class CompatResult(BaseModel):
    factors: dict[str, Factor]
    penalties: list[Penalty] = Field(default_factory=list)
    perspectives: dict[str, Perspective]
    dohwa_readings: list[str] = Field(default_factory=list)  # 도화 3가지 해석 병기


# ============================================================
# 요소별 근거점수 (관법 중립)
# ============================================================
def _score_day_stem(a: str, b: str) -> Factor:
    """일간 천간합/충."""
    items: list[FactorItem] = []
    pair = frozenset({a, b})
    sa, sb = stem_korean(a), stem_korean(b)
    if pair in STEM_COMBINATIONS:
        elem = WUXING_KOREAN[STEM_COMBINATIONS[pair]]
        score = 90
        items.append(FactorItem(type="천간합", sign=1,
                                detail=f"일간 {a}({sa})·{b}({sb}) 천간합 → {elem} 기운. 첫 끌림·이상적 결합"))
    elif pair in STEM_CONFLICTS:
        score = 30
        items.append(FactorItem(type="천간충", sign=-1,
                                detail=f"일간 {a}({sa})·{b}({sb}) 천간충 → 가치관 충돌 주의"))
    elif a == b:
        score = 58
        items.append(FactorItem(type="비화", detail=f"일간이 같음({a}{sa}) → 동질감, 단 경쟁 가능"))
    else:
        score = 60
        items.append(FactorItem(type="무관계", detail=f"일간 {a}({sa})·{b}({sb}) 특별한 합충 없음"))
    return Factor(key="day_stem", label="일간(천간합)", score=score, items=items)


def _score_day_branch(a: str, b: str) -> Factor:
    """일지 육합/삼합(반합)/충. 부부궁은 육합>삼합."""
    items: list[FactorItem] = []
    pair = frozenset({a, b})
    ba, bb = branch_korean(a), branch_korean(b)
    # len==2 가드: 같은 일지(a==b)는 원소 1개 frozenset이라 삼합그룹 진부분집합 검사에 항상 걸려
    # (12지 전원이 삼합국 소속) '반합 78점'으로 오판됐다(실측 8종 전부). 같은 글자는 아래 동지(60) 분기.
    half_trine = next((s for s in BRANCH_TRIPLE_COMBINATIONS if len(pair) == 2 and pair < s), None)
    if pair in BRANCH_SIX_COMBINATIONS:
        elem = WUXING_KOREAN[BRANCH_SIX_COMBINATIONS[pair]]
        score = 92
        items.append(FactorItem(type="지지육합", sign=1,
                                detail=f"일지 {a}({ba})·{b}({bb}) 육합 → {elem}. 부부 생활 호환 최상"))
    elif half_trine is not None:
        elem = WUXING_KOREAN[BRANCH_TRIPLE_COMBINATIONS[half_trine]]
        score = 78
        items.append(FactorItem(type="지지반합(삼합)", sign=1,
                                detail=f"일지 {a}({ba})·{b}({bb}) 삼합 일부 → {elem}. 협력 좋음(부부엔 육합 다음)"))
    elif pair in BRANCH_CONFLICTS:
        score = 28
        items.append(FactorItem(type="지지충", sign=-1,
                                detail=f"일지 {a}({ba})·{b}({bb}) 충 → 배우자궁 충돌, 변동·갈등 주의"))
    elif a == b:
        score = 60
        items.append(FactorItem(type="동지", detail=f"일지가 같음({a}{ba}) → 가치관 유사"))
    else:
        score = 60
        items.append(FactorItem(type="무관계", detail=f"일지 {a}({ba})·{b}({bb}) 특별한 합충 없음"))
    return Factor(key="day_branch", label="일지(부부궁)", score=score, items=items)


def _score_wuxing(a: SajuChart, b: SajuChart) -> Factor:
    """오행 상호보완 — 두 사람 오행을 합쳤을 때 균형이 좋을수록 상보적."""
    aw = a.wuxing
    bw = b.wuxing
    combined = [getattr(aw, k) + getattr(bw, k) for k in _WX_ATTR.values()]
    total = sum(combined) or 1
    ideal = total / 5
    # 불균형도 0(완전균형)~1(최대편중) → 점수 = 100*(1-불균형)
    imbalance = sum(abs(c - ideal) for c in combined) / (2 * ideal * 4)
    score = max(0, min(100, round(100 * (1 - imbalance))))

    # 상대가 채워주는 부족 오행 설명
    items: list[FactorItem] = []
    labels = list(WUXING_KOREAN.values())  # 목화토금수
    a_counts = [getattr(aw, k) for k in _WX_ATTR.values()]
    b_counts = [getattr(bw, k) for k in _WX_ATTR.values()]
    a_mean = (sum(a_counts) / 5) or 0
    filled = [labels[i] for i in range(5) if a_counts[i] < a_mean and b_counts[i] > a_counts[i]]
    if filled:
        items.append(FactorItem(type="상호보완", sign=1,
                                detail=f"한쪽의 부족 오행({'·'.join(filled)})을 상대가 보충 → 상보 관계"))
    else:
        items.append(FactorItem(type="오행분포", detail="오행 보완 효과는 보통 수준"))
    return Factor(key="wuxing", label="오행 상호보완", score=score, items=items)


def _score_ten_god(a_stem: str, b_stem: str) -> Factor:
    """일간 상호 십성 — 정관·정재(정배우자)면 길."""
    a_to_b = compute_ten_god(a_stem, b_stem)   # A 기준 B
    b_to_a = compute_ten_god(b_stem, a_stem)   # B 기준 A
    s = round((_TEN_GOD_SCORE.get(a_to_b, 55) + _TEN_GOD_SCORE.get(b_to_a, 55)) / 2)
    pos = a_to_b in ("正官", "正財") or b_to_a in ("正官", "正財")
    items = [FactorItem(
        type="십성관계", sign=1 if pos else 0,
        detail=f"상대를 보는 십성 — A→B: {TEN_GODS_KO.get(a_to_b, a_to_b)}, "
               f"B→A: {TEN_GODS_KO.get(b_to_a, b_to_a)}"
               + ("  (정배우자 관계)" if pos else ""),
    )]
    return Factor(key="ten_god", label="십성(정재·정관)", score=s, items=items)


def _dohwa_char(branch: str) -> str | None:
    """해당 일지가 속한 삼합국의 도화(왕지) 글자."""
    for trine, ch in DOHWA_BY_TRINE.items():
        if branch in trine:
            return ch
    return None


def _has_amhap(a: str, b: str) -> bool:
    """일지 지장간끼리 천간합(암합) 성립 여부."""
    for ha in HIDDEN_STEMS.get(a, ()):
        for hb in HIDDEN_STEMS.get(b, ()):
            if frozenset({ha, hb}) in STEM_COMBINATIONS:
                return True
    return False


def _score_sinsal(a: str, b: str) -> tuple[Factor, list[Penalty], list[str]]:
    """신살(神煞) — 도화·암합(가점) / 원진·귀문·형·파·해(감점). 일지 기준."""
    items: list[FactorItem] = []
    penalties: list[Penalty] = []
    pair = frozenset({a, b})
    ba, bb = branch_korean(a), branch_korean(b)
    score = 60

    # --- 감점(흉) ---
    neg = []
    if pair in BRANCH_WONJIN:
        neg.append(("원진", "애증·원망(궁합 강한 주의)"))
    if pair in BRANCH_GWIMUN:
        neg.append(("귀문", "예민·신경 곤두섬"))
    if pair in BRANCH_PUNISH or (a == b and a in BRANCH_SELF_PUNISH):
        neg.append(("형", "마찰·구설"))
    if pair in BRANCH_BREAK:
        neg.append(("파", "깨짐·분리 기운"))
    if pair in BRANCH_HARM:
        neg.append(("해", "방해·서운함"))
    for typ, desc in neg:
        score -= 12
        items.append(FactorItem(type=typ, sign=-1, detail=f"일지 {a}({ba})·{b}({bb}) {typ} → {desc}"))
        penalties.append(Penalty(type=typ, detail=f"{a}({ba})·{b}({bb}) {typ}: {desc}"))

    # --- 가점(길/인연) ---
    if _has_amhap(a, b):
        score += 12
        items.append(FactorItem(type="암합", sign=1,
                                detail=f"일지 지장간끼리 숨은 합(암합) → 드러나지 않는 인연·끌림"))

    # --- 도화(양면) ---
    dohwa_readings: list[str] = []
    a_dohwa, b_dohwa = _dohwa_char(a), _dohwa_char(b)
    is_dohwa = (b == a_dohwa) or (a == b_dohwa)
    if is_dohwa:
        score += 8  # 양면: 끌림 가점, 단 길흉 단정 안 함
        items.append(FactorItem(type="도화", sign=1,
                                detail=f"일지에 도화 작용 → 이성적 매력·끌림 강함 (해석 양면)"))
        dohwa_readings = [
            "양면: 강한 끌림과 매력이 작용하나, 끼·외도 가능성도 함께 보는 관점",
            "길(吉): 부부간 도화는 금슬·애정이 좋다고 보는 관점",
            "중립: 도화 자체는 길흉이 정해지지 않아 다른 구성과 함께 판단하는 관점",
        ]

    score = max(0, min(100, score))
    if not items:
        items.append(FactorItem(type="무관계", detail="특별한 신살 작용 없음"))
    return (
        Factor(key="sinsal", label="신살(神煞)", score=score, items=items),
        penalties,
        dohwa_readings,
    )


# ============================================================
# 종합
# ============================================================
def _grade(total: int) -> str:
    if total >= 80:
        return "천생연분"
    if total >= 68:
        return "좋은 궁합"
    if total >= 55:
        return "무난한 궁합"
    if total >= 42:
        return "노력 필요"
    return "신중히"


def _interpret(label: str, total: int, grade: str) -> str:
    return f"{label} 관점에서 {total}점 — {grade}."


def compute_compatibility(chart_a: SajuChart, chart_b: SajuChart) -> CompatResult:
    """두 사주명식의 궁합을 산출. 관법 중립 5요소 점수 + A/B/C 관법별 종합."""
    a_stem, a_br = chart_a.pillars.day.stem, chart_a.pillars.day.branch
    b_stem, b_br = chart_b.pillars.day.stem, chart_b.pillars.day.branch

    f_branch = _score_day_branch(a_br, b_br)
    f_stem = _score_day_stem(a_stem, b_stem)
    f_wuxing = _score_wuxing(chart_a, chart_b)
    f_tengod = _score_ten_god(a_stem, b_stem)
    f_sinsal, penalties, dohwa_readings = _score_sinsal(a_br, b_br)

    # 일지 충도 주의 배지에 추가
    if frozenset({a_br, b_br}) in BRANCH_CONFLICTS:
        penalties.insert(0, Penalty(
            type="일지충",
            detail=f"{a_br}({branch_korean(a_br)})·{b_br}({branch_korean(b_br)}) 충: 배우자궁 충돌",
        ))
    if frozenset({a_stem, b_stem}) in STEM_CONFLICTS:
        penalties.insert(0, Penalty(
            type="일간충",
            detail=f"{a_stem}({stem_korean(a_stem)})·{b_stem}({stem_korean(b_stem)}) 충: 가치관 충돌",
        ))

    factors = {
        "day_branch": f_branch,
        "day_stem": f_stem,
        "wuxing": f_wuxing,
        "ten_god": f_tengod,
        "sinsal": f_sinsal,
    }

    perspectives: dict[str, Perspective] = {}
    for key, cfg in PERSPECTIVES.items():
        weights = cfg["weights"]
        contributions = {fk: round(factors[fk].score * weights[fk] / 100, 1) for fk in factors}
        total = round(sum(contributions.values()))
        grade = _grade(total)
        perspectives[key] = Perspective(
            key=key, label=cfg["label"], weights=weights,
            contributions=contributions, total=total, grade=grade,
            interpretation=_interpret(cfg["label"], total, grade),
        )

    return CompatResult(
        factors=factors,
        penalties=penalties,
        perspectives=perspectives,
        dohwa_readings=dohwa_readings,
    )
