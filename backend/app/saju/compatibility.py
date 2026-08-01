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
    TEN_GODS_VI,
    WUXING_LIST,
    Locale,
    branch_reading,
    compute_ten_god,
    stem_reading,
    wuxing_reading,
)
from .types import SajuChart

# ============================================================
# 로케일 문자열 — ko 는 기존 산출값 그대로(한국 서비스 불변), vi 는 한월음(Hán-Việt) 기반.
# 동적 간지 독음은 stem_reading/branch_reading/wuxing_reading(x, locale) 로 로케일 반영.
# ============================================================
# 종합 등급: 로케일 무관 stable key + 로케일 표시 라벨.
_GRADE_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (80, "soulmate"), (68, "good"), (55, "fair"), (42, "effort"),
)
_GRADE_LABEL: dict[str, dict[str, str]] = {
    "ko": {"soulmate": "천생연분", "good": "좋은 궁합", "fair": "무난한 궁합",
           "effort": "노력 필요", "caution": "신중히"},
    "vi": {"soulmate": "Duyên trời định", "good": "Hợp tốt", "fair": "Hợp vừa",
           "effort": "Cần cố gắng", "caution": "Cần thận trọng"},
}
# 관법(A/B/C) 라벨
_PERSP_LABEL: dict[str, dict[str, str]] = {
    "ko": {"A": "결혼·부부궁 중시", "B": "균형", "C": "연애·끌림 중시"},
    "vi": {"A": "Trọng hôn nhân·cung phu thê", "B": "Cân bằng", "C": "Trọng tình cảm·sức hút"},
}
# 요소 라벨(Factor.label)
_FACTOR_LABEL_L: dict[str, dict[str, str]] = {
    "ko": {"day_stem": "일간(천간합)", "day_branch": "일지(부부궁)", "wuxing": "오행 상호보완",
           "ten_god": "십성(정재·정관)", "sinsal": "신살(神煞)"},
    "vi": {"day_stem": "Thiên can ngày (hợp can)", "day_branch": "Địa chi ngày (cung phu thê)",
           "wuxing": "Ngũ hành tương bổ", "ten_god": "Thập thần (Chính tài·Chính quan)",
           "sinsal": "Thần sát"},
}
# 근거/페널티 유형명(FactorItem.type, Penalty.type). ko 는 항등, vi 만 치환.
_TYPE_VI: dict[str, str] = {
    "천간합": "Hợp can", "천간충": "Xung can", "비화": "Tỷ hòa", "무관계": "Không quan hệ",
    "지지육합": "Lục hợp địa chi", "지지반합(삼합)": "Bán hợp (tam hợp)", "지지충": "Xung địa chi",
    "동지": "Cùng địa chi", "상호보완": "Tương bổ", "오행분포": "Phân bố ngũ hành",
    "십성관계": "Quan hệ thập thần", "원진": "Oán sân", "귀문": "Quỷ môn", "형": "Hình",
    "파": "Phá", "해": "Hại", "암합": "Ám hợp", "도화": "Đào hoa",
    "일지충": "Xung địa chi ngày", "일간충": "Xung thiên can ngày",
}
# 신살 흉작용 설명(원진/귀문/형/파/해)
_SINSAL_DESC: dict[str, dict[str, str]] = {
    "ko": {"원진": "애증·원망(궁합 강한 주의)", "귀문": "예민·신경 곤두섬", "형": "마찰·구설",
           "파": "깨짐·분리 기운", "해": "방해·서운함"},
    "vi": {"원진": "Yêu·hận·oán trách (rất cần lưu ý)", "귀문": "Nhạy cảm·căng thẳng thần kinh",
           "형": "Va chạm·thị phi", "파": "Khí đổ vỡ·chia lìa", "해": "Cản trở·hờn dỗi"},
}
# 도화 3관점 해석
_DOHWA_READINGS: dict[str, list[str]] = {
    "ko": [
        "양면: 강한 끌림과 매력이 작용하나, 끼·외도 가능성도 함께 보는 관점",
        "길(吉): 부부간 도화는 금슬·애정이 좋다고 보는 관점",
        "중립: 도화 자체는 길흉이 정해지지 않아 다른 구성과 함께 판단하는 관점",
    ],
    "vi": [
        "Hai mặt: sức hút·quyến rũ mạnh, nhưng cũng xét khả năng lăng nhăng·ngoại tình",
        "Cát: đào hoa giữa vợ chồng được xem là tình cảm·ân ái tốt",
        "Trung lập: bản thân đào hoa chưa định cát hung, cần xét cùng cấu trúc khác",
    ],
}


def _typ(t: str, locale: Locale) -> str:
    """유형명 로케일화(ko 항등)."""
    return _TYPE_VI.get(t, t) if locale == "vi" else t


def _tg(hanja: str, locale: Locale) -> str:
    """십성 한자 → 로케일 독음."""
    d = TEN_GODS_VI if locale == "vi" else TEN_GODS_KO
    return d.get(hanja, hanja)

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
    grade: str                      # 로케일 표시 라벨
    grade_key: str = ""             # 로케일 무관 stable key: soulmate|good|fair|effort|caution
    interpretation: str


class CompatResult(BaseModel):
    factors: dict[str, Factor]
    penalties: list[Penalty] = Field(default_factory=list)
    perspectives: dict[str, Perspective]
    dohwa_readings: list[str] = Field(default_factory=list)  # 도화 3가지 해석 병기


# ============================================================
# 요소별 근거점수 (관법 중립)
# ============================================================
def _score_day_stem(a: str, b: str, locale: Locale = "ko") -> Factor:
    """일간 천간합/충."""
    vi = locale == "vi"
    items: list[FactorItem] = []
    pair = frozenset({a, b})
    sa, sb = stem_reading(a, locale), stem_reading(b, locale)
    if pair in STEM_COMBINATIONS:
        elem = wuxing_reading(STEM_COMBINATIONS[pair], locale)
        score = 90
        detail = (f"Thiên can ngày {sa}·{sb} hợp can → khí {elem}. Sức hút ban đầu·kết hợp lý tưởng"
                  if vi else f"일간 {a}({sa})·{b}({sb}) 천간합 → {elem} 기운. 첫 끌림·이상적 결합")
        items.append(FactorItem(type=_typ("천간합", locale), sign=1, detail=detail))
    elif pair in STEM_CONFLICTS:
        score = 30
        detail = (f"Thiên can ngày {sa}·{sb} xung can → lưu ý xung đột quan niệm sống"
                  if vi else f"일간 {a}({sa})·{b}({sb}) 천간충 → 가치관 충돌 주의")
        items.append(FactorItem(type=_typ("천간충", locale), sign=-1, detail=detail))
    elif a == b:
        score = 58
        detail = (f"Thiên can ngày giống nhau ({sa}) → đồng điệu, nhưng có thể cạnh tranh"
                  if vi else f"일간이 같음({a}{sa}) → 동질감, 단 경쟁 가능")
        items.append(FactorItem(type=_typ("비화", locale), detail=detail))
    else:
        score = 60
        detail = (f"Thiên can ngày {sa}·{sb} không có hợp xung đặc biệt"
                  if vi else f"일간 {a}({sa})·{b}({sb}) 특별한 합충 없음")
        items.append(FactorItem(type=_typ("무관계", locale), detail=detail))
    return Factor(key="day_stem", label=_FACTOR_LABEL_L[locale]["day_stem"], score=score, items=items)


def _score_day_branch(a: str, b: str, locale: Locale = "ko") -> Factor:
    """일지 육합/삼합(반합)/충. 부부궁은 육합>삼합."""
    vi = locale == "vi"
    items: list[FactorItem] = []
    pair = frozenset({a, b})
    ba, bb = branch_reading(a, locale), branch_reading(b, locale)
    half_trine = next((s for s in BRANCH_TRIPLE_COMBINATIONS if pair < s), None)
    if pair in BRANCH_SIX_COMBINATIONS:
        elem = wuxing_reading(BRANCH_SIX_COMBINATIONS[pair], locale)
        score = 92
        detail = (f"Địa chi ngày {ba}·{bb} lục hợp → {elem}. Tương hợp đời sống vợ chồng cao nhất"
                  if vi else f"일지 {a}({ba})·{b}({bb}) 육합 → {elem}. 부부 생활 호환 최상")
        items.append(FactorItem(type=_typ("지지육합", locale), sign=1, detail=detail))
    elif half_trine is not None:
        elem = wuxing_reading(BRANCH_TRIPLE_COMBINATIONS[half_trine], locale)
        score = 78
        detail = (f"Địa chi ngày {ba}·{bb} một phần tam hợp → {elem}. Hợp tác tốt (với vợ chồng chỉ sau lục hợp)"
                  if vi else f"일지 {a}({ba})·{b}({bb}) 삼합 일부 → {elem}. 협력 좋음(부부엔 육합 다음)")
        items.append(FactorItem(type=_typ("지지반합(삼합)", locale), sign=1, detail=detail))
    elif pair in BRANCH_CONFLICTS:
        score = 28
        detail = (f"Địa chi ngày {ba}·{bb} xung → xung khắc cung phối ngẫu, lưu ý biến động·mâu thuẫn"
                  if vi else f"일지 {a}({ba})·{b}({bb}) 충 → 배우자궁 충돌, 변동·갈등 주의")
        items.append(FactorItem(type=_typ("지지충", locale), sign=-1, detail=detail))
    elif a == b:
        score = 60
        detail = (f"Địa chi ngày giống nhau ({ba}) → quan niệm sống tương đồng"
                  if vi else f"일지가 같음({a}{ba}) → 가치관 유사")
        items.append(FactorItem(type=_typ("동지", locale), detail=detail))
    else:
        score = 60
        detail = (f"Địa chi ngày {ba}·{bb} không có hợp xung đặc biệt"
                  if vi else f"일지 {a}({ba})·{b}({bb}) 특별한 합충 없음")
        items.append(FactorItem(type=_typ("무관계", locale), detail=detail))
    return Factor(key="day_branch", label=_FACTOR_LABEL_L[locale]["day_branch"], score=score, items=items)


def _score_wuxing(a: SajuChart, b: SajuChart, locale: Locale = "ko") -> Factor:
    """오행 상호보완 — 두 사람 오행을 합쳤을 때 균형이 좋을수록 상보적."""
    vi = locale == "vi"
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
    labels = [wuxing_reading(w, locale) for w in WUXING_LIST]  # 목화토금수 / Mộc Hỏa Thổ Kim Thủy
    a_counts = [getattr(aw, k) for k in _WX_ATTR.values()]
    b_counts = [getattr(bw, k) for k in _WX_ATTR.values()]
    a_mean = (sum(a_counts) / 5) or 0
    filled = [labels[i] for i in range(5) if a_counts[i] < a_mean and b_counts[i] > a_counts[i]]
    if filled:
        detail = (f"Đối phương bổ sung ngũ hành thiếu ({'·'.join(filled)}) → quan hệ tương bổ"
                  if vi else f"한쪽의 부족 오행({'·'.join(filled)})을 상대가 보충 → 상보 관계")
        items.append(FactorItem(type=_typ("상호보완", locale), sign=1, detail=detail))
    else:
        detail = "Hiệu quả bổ sung ngũ hành ở mức trung bình" if vi else "오행 보완 효과는 보통 수준"
        items.append(FactorItem(type=_typ("오행분포", locale), detail=detail))
    return Factor(key="wuxing", label=_FACTOR_LABEL_L[locale]["wuxing"], score=score, items=items)


def _score_ten_god(a_stem: str, b_stem: str, locale: Locale = "ko") -> Factor:
    """일간 상호 십성 — 정관·정재(정배우자)면 길."""
    vi = locale == "vi"
    a_to_b = compute_ten_god(a_stem, b_stem)   # A 기준 B
    b_to_a = compute_ten_god(b_stem, a_stem)   # B 기준 A
    s = round((_TEN_GOD_SCORE.get(a_to_b, 55) + _TEN_GOD_SCORE.get(b_to_a, 55)) / 2)
    pos = a_to_b in ("正官", "正財") or b_to_a in ("正官", "正財")
    if vi:
        detail = (f"Thập thần nhìn đối phương — A→B: {_tg(a_to_b, locale)}, "
                  f"B→A: {_tg(b_to_a, locale)}" + ("  (quan hệ chính phối ngẫu)" if pos else ""))
    else:
        detail = (f"상대를 보는 십성 — A→B: {_tg(a_to_b, locale)}, "
                  f"B→A: {_tg(b_to_a, locale)}" + ("  (정배우자 관계)" if pos else ""))
    items = [FactorItem(type=_typ("십성관계", locale), sign=1 if pos else 0, detail=detail)]
    return Factor(key="ten_god", label=_FACTOR_LABEL_L[locale]["ten_god"], score=s, items=items)


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


def _score_sinsal(a: str, b: str, locale: Locale = "ko") -> tuple[Factor, list[Penalty], list[str]]:
    """신살(神煞) — 도화·암합(가점) / 원진·귀문·형·파·해(감점). 일지 기준."""
    vi = locale == "vi"
    items: list[FactorItem] = []
    penalties: list[Penalty] = []
    pair = frozenset({a, b})
    ba, bb = branch_reading(a, locale), branch_reading(b, locale)
    desc_map = _SINSAL_DESC[locale]
    score = 60

    # --- 감점(흉) ---
    neg: list[str] = []
    if pair in BRANCH_WONJIN:
        neg.append("원진")
    if pair in BRANCH_GWIMUN:
        neg.append("귀문")
    if pair in BRANCH_PUNISH or (a == b and a in BRANCH_SELF_PUNISH):
        neg.append("형")
    if pair in BRANCH_BREAK:
        neg.append("파")
    if pair in BRANCH_HARM:
        neg.append("해")
    for typ in neg:
        score -= 12
        tl, desc = _typ(typ, locale), desc_map[typ]
        if vi:
            idet = f"Địa chi ngày {ba}·{bb} {tl} → {desc}"
        else:
            idet = f"일지 {a}({ba})·{b}({bb}) {tl} → {desc}"
        items.append(FactorItem(type=tl, sign=-1, detail=idet))
        penalties.append(Penalty(type=tl, detail=f"{ba}·{bb} {tl}: {desc}"))

    # --- 가점(길/인연) ---
    if _has_amhap(a, b):
        score += 12
        adet = ("Tàng can trong địa chi ngày hợp ngầm (ám hợp) → duyên·sức hút tiềm ẩn"
                if vi else "일지 지장간끼리 숨은 합(암합) → 드러나지 않는 인연·끌림")
        items.append(FactorItem(type=_typ("암합", locale), sign=1, detail=adet))

    # --- 도화(양면) ---
    dohwa_readings: list[str] = []
    a_dohwa, b_dohwa = _dohwa_char(a), _dohwa_char(b)
    is_dohwa = (b == a_dohwa) or (a == b_dohwa)
    if is_dohwa:
        score += 8  # 양면: 끌림 가점, 단 길흉 단정 안 함
        ddet = ("Địa chi ngày có tác dụng đào hoa → sức hút·quyến rũ mạnh (luận giải hai mặt)"
                if vi else "일지에 도화 작용 → 이성적 매력·끌림 강함 (해석 양면)")
        items.append(FactorItem(type=_typ("도화", locale), sign=1, detail=ddet))
        dohwa_readings = list(_DOHWA_READINGS[locale])

    score = max(0, min(100, score))
    if not items:
        ndet = "Không có tác dụng thần sát đặc biệt" if vi else "특별한 신살 작용 없음"
        items.append(FactorItem(type=_typ("무관계", locale), detail=ndet))
    return (
        Factor(key="sinsal", label=_FACTOR_LABEL_L[locale]["sinsal"], score=score, items=items),
        penalties,
        dohwa_readings,
    )


# ============================================================
# 종합
# ============================================================
def _grade(total: int, locale: Locale = "ko") -> tuple[str, str]:
    """종합점수 → (stable grade_key, 로케일 표시 라벨)."""
    key = "caution"
    for th, k in _GRADE_THRESHOLDS:
        if total >= th:
            key = k
            break
    return key, _GRADE_LABEL[locale][key]


def _interpret(label: str, total: int, grade: str, locale: Locale = "ko") -> str:
    if locale == "vi":
        return f"Theo góc nhìn {label}: {total} điểm — {grade}."
    return f"{label} 관점에서 {total}점 — {grade}."


def compute_compatibility(
    chart_a: SajuChart, chart_b: SajuChart, locale: Locale = "ko"
) -> CompatResult:
    """두 사주명식의 궁합을 산출. 관법 중립 5요소 점수 + A/B/C 관법별 종합.

    locale='ko'(기본)은 한국 서비스와 완전히 동일. 'vi'는 라벨·근거문구를 한월음 기반 베트남어로.
    grade_key(soulmate|good|fair|effort|caution)는 로케일 무관 stable key.
    """
    vi = locale == "vi"
    a_stem, a_br = chart_a.pillars.day.stem, chart_a.pillars.day.branch
    b_stem, b_br = chart_b.pillars.day.stem, chart_b.pillars.day.branch

    f_branch = _score_day_branch(a_br, b_br, locale)
    f_stem = _score_day_stem(a_stem, b_stem, locale)
    f_wuxing = _score_wuxing(chart_a, chart_b, locale)
    f_tengod = _score_ten_god(a_stem, b_stem, locale)
    f_sinsal, penalties, dohwa_readings = _score_sinsal(a_br, b_br, locale)

    # 일지 충도 주의 배지에 추가
    if frozenset({a_br, b_br}) in BRANCH_CONFLICTS:
        ra, rb = branch_reading(a_br, locale), branch_reading(b_br, locale)
        det = (f"{ra}·{rb} xung: xung khắc cung phối ngẫu"
               if vi else f"{a_br}({ra})·{b_br}({rb}) 충: 배우자궁 충돌")
        penalties.insert(0, Penalty(type=_typ("일지충", locale), detail=det))
    if frozenset({a_stem, b_stem}) in STEM_CONFLICTS:
        ra, rb = stem_reading(a_stem, locale), stem_reading(b_stem, locale)
        det = (f"{ra}·{rb} xung: xung đột quan niệm sống"
               if vi else f"{a_stem}({ra})·{b_stem}({rb}) 충: 가치관 충돌")
        penalties.insert(0, Penalty(type=_typ("일간충", locale), detail=det))

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
        label = _PERSP_LABEL[locale][key]
        contributions = {fk: round(factors[fk].score * weights[fk] / 100, 1) for fk in factors}
        total = round(sum(contributions.values()))
        grade_key, grade = _grade(total, locale)
        perspectives[key] = Perspective(
            key=key, label=label, weights=weights,
            contributions=contributions, total=total, grade=grade, grade_key=grade_key,
            interpretation=_interpret(label, total, grade, locale),
        )

    return CompatResult(
        factors=factors,
        penalties=penalties,
        perspectives=perspectives,
        dohwa_readings=dohwa_readings,
    )
