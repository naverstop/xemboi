"""택일(擇日) 엔진 — 기간 내 날짜별 길흉 점수 → 길일 추천.

요소(관법 중립):
  ① 황도흑도(黃道黑道) — 월지·일지 기준 12신 중 황도6(길)/흑도6(흉)
  ② 본인 사주 회피     — 그날 일지 vs 본인 일지의 충/원진/형 (기존 합충테이블 재사용)
  ③ 손없는날           — 음력 끝자리 9·0 (이사·개업 민속)
용도(7종+)는 가중치(관법)로 반영. 정밀 생기복덕(팔택유년)은 후속 정제.
"""
from __future__ import annotations

from datetime import date, timedelta

from pydantic import BaseModel, Field

from .constants import (
    BRANCH_CONFLICTS,
    BRANCH_PUNISH,
    BRANCH_SELF_PUNISH,
    BRANCH_WONJIN,
    EARTHLY_BRANCHES,
    branch_korean,
    stem_korean,
)
from .engine import build_chart
from .types import BirthInput, SajuChart

# 황도흑도 12신 (청룡부터). (이름, 황/흑)
_SHIN = [
    ("청룡", "황"), ("명당", "황"), ("천형", "흑"), ("주작", "흑"),
    ("금궤", "황"), ("천덕", "황"), ("백호", "흑"), ("옥당", "황"),
    ("천뢰", "흑"), ("현무", "흑"), ("사명", "황"), ("구진", "흑"),
]
# 월지 → 청룡(시작) 일지
_CHEONGYONG_START = {
    "寅": "子", "申": "子", "卯": "寅", "酉": "寅", "辰": "辰", "戌": "辰",
    "巳": "午", "亥": "午", "午": "申", "子": "申", "未": "戌", "丑": "戌",
}

# 건제십이신(建除十二神/십이직성) — 중단(中段) 택일의 핵심.
# 월지와 같은 일지인 날이 建, 이후 일지 순서대로 除滿平定執破危成收開閉 배당.
# 길흉(고전 구결): "建滿平收黑, 除危定執黃, 成開可用, 閉破不可當"
#   → 길: 除·危·定·執·成·開 / 흉: 建·滿·平·收·閉·破 (破·閉 大凶, 成·開·定 大吉)
# ※ 절입일에 신이 겹치는(重) 정밀 보정은 미반영(월지-일지 차로 근사).
_GEONJE_ORDER = ["建", "除", "滿", "平", "定", "執", "破", "危", "成", "收", "開", "閉"]
_GEONJE_KO = {
    "建": "건", "除": "제", "滿": "만", "平": "평", "定": "정", "執": "집",
    "破": "파", "危": "위", "成": "성", "收": "수", "開": "개", "閉": "폐",
}
# (점수0~100, 한 줄 의미)
_GEONJE_INFO: dict[str, tuple[int, str]] = {
    "成": (92, "이룸 — 혼인·개업·입학 등 만사 대길"),
    "開": (90, "열림 — 개업·입주·개통에 대길(장례는 피함)"),
    "定": (82, "안정 — 결혼·계약·입주에 길(소송·이동은 흉)"),
    "除": (78, "묵은 것 제거 — 치료·청소·제사에 길"),
    "危": (70, "황도 길신 — 대체로 길(등산·승선은 주의)"),
    "執": (68, "잡음 — 결혼·건축·계약에 길(이사·재물은 흉)"),
    "平": (52, "평탄 — 무난(도로·담장에 길)"),
    "收": (48, "거둠 — 수금·매입에 길(장례·개업은 흉)"),
    "滿": (45, "가득참 — 창고·연못엔 길이나 복약·매장은 흉"),
    "建": (42, "세움 — 우두머리 기운이나 동토·매장은 흉"),
    "閉": (28, "닫음 — 매장·둑막이 외 대체로 흉"),
    "破": (20, "깨짐 — 만사 대흉(파옥·치료만 길)"),
}

# ── 이십팔수(二十八宿) ──────────────────────────────────────────
# 매일 1수씩 +1 순환(28일). 칠요(요일)와 위상이 고정 → 자가검증 가능.
# 표준 순서(角부터). 앵커: 2026-06-09 = 室(index 12).
#   출처: 일본 코요미 2곳(koyominote·rekichu) 6/8危·6/9室·6/10壁·6/11奎 일치 +
#         한국 위키백과 '이십팔수' 칠요표와 요일·순서 교차검증.
#   ※ 잔여: 한·일 위상 동일성(7/14/21일 어긋남)은 한국 만세력 1회 스팟확인 권장.
_SU28 = "角亢氐房心尾箕斗牛女虛危室壁奎婁胃昴畢觜參井鬼柳星張翼軫"
_SU28_KO = "각항저방심미기두우여허위실벽규루위묘필자삼정귀류성장익진"
_SU28_ANCHOR_ORD = date(2026, 6, 9).toordinal()
_SU28_ANCHOR_IDX = 12  # 室
# 길흉 한 줄(출처: 歳事暦 saijigoyomi). good=True 길수 / False 흉 비중 큰 수.
_SU28_NOTE: dict[str, str] = {
    "角": "길 · 혼인·건축·개점(장례 흉)", "亢": "길 · 혼인·파종(건축·이사·여행 흉)",
    "氐": "길 · 혼인·농경·개축(물가 흉)", "房": "길 · 혼인·여행·상량(소송 흉)",
    "心": "혼인·장례 흉 · 제사·이사·여행엔 길", "尾": "길 · 혼인·개점·여행(재단·장례 흉)",
    "箕": "혼인·장례 흉 · 양조·매입엔 길", "斗": "길 · 혼인·부동산·조작",
    "牛": "大吉 · 만사에 길(길상숙)", "女": "공무·학예엔 길(혼인·장례·신축 흉)",
    "虛": "건축·혼인 흉, 상담 大凶 · 입학엔 길", "危": "혼인·이사 흉, 등산·고소 大凶",
    "室": "길 · 제사·혼인·조작(장례·원행 흉)", "壁": "길 · 신축·혼인(남향 진출 흉)",
    "奎": "길 · 혼인·상량·벌목(개점·소송 흉)", "婁": "大吉 · 혼인·여행·재단(소송 흉)",
    "胃": "취직·혼인엔 길(장례 大凶)", "昴": "길 · 기원·축하·개점(재단 흉)",
    "畢": "길 · 제사·혼인·신축·부동산(투자·구설 흉)", "觜": "혼인 흉일 · 입학·건축엔 길",
    "參": "길 · 상거래·개업·혼인·취직(장례·이사 흉)", "井": "길 · 제사·혼인·건축·부동산(장례 흉)",
    "鬼": "大吉 · 공적 식전 최고(혼인만 흉)", "柳": "혼인 흉, 장송 大凶 · 강맹사엔 길",
    "星": "혼인·축하 흉 · 운전·요양·파종엔 길", "張": "大吉 · 혼인·개업·파종·양잠(재단 흉)",
    "翼": "혼인 大凶(이혼) · 경작·식목엔 길", "軫": "길 · 혼인·상량·부동산(재단·여행 흉)",
}


# 28수 일반 길흉(0~100) — 歳事暦. 大吉宿(牛婁鬼張)>일반 吉>주의(흉 요소 큰 수).
_SU28_SCORE: dict[str, int] = {
    "牛": 90, "婁": 90, "鬼": 90, "張": 88,                       # 大吉宿
    "室": 74, "角": 72, "房": 72, "尾": 72, "斗": 72, "壁": 72,    # 吉
    "昴": 72, "畢": 72, "參": 72, "井": 72,
    "亢": 70, "氐": 70, "奎": 70, "軫": 70, "女": 68, "胃": 68,
    "星": 60, "心": 60, "箕": 58, "虛": 58, "危": 58, "柳": 58,    # 주의(흉 요소 큼)
    "觜": 56, "翼": 56,
}
# 혼인·출산엔 '婚礼凶'인 수를 강하게 감점 (歳事暦): 心箕虛危觜鬼柳星翼
_SU28_WEDDING_BAD = set("心箕虛危觜鬼柳星翼")


def _su28_score(su_ch: str, purpose: str) -> int:
    s = _SU28_SCORE.get(su_ch, 68)
    if purpose in ("wedding", "birth") and su_ch in _SU28_WEDDING_BAD:
        s = min(s, 35)   # 혼인·출산엔 婚礼凶 수 강한 감점
    return s


def _su28_index(d: date) -> int:
    """그 날의 28수 인덱스(0=角..27=軫). 칠요(요일) 자가검증 포함."""
    idx = (_SU28_ANCHOR_IDX + (d.toordinal() - _SU28_ANCHOR_ORD)) % 28
    # 칠요 잠금(위키): (i+3)%7 == 파이썬 요일(월0..일6). 어긋나면 앵커/계산 오류.
    assert (idx + 3) % 7 == d.weekday(), f"28수 칠요 불일치: {d.isoformat()} idx={idx}"
    return idx


def _su28(d: date) -> tuple[str, str, str]:
    """(한자, 한글, 길흉 한 줄). 예: ('室','실','길 · 제사·혼인·조작…')."""
    i = _su28_index(d)
    ch = _SU28[i]
    return ch, _SU28_KO[i], _SU28_NOTE.get(ch, "")


# 용도(8종+). '출산'은 혼인 다음(자식과의 관계)으로 배치.
PURPOSES = {
    "wedding": "혼인", "birth": "출산", "moving": "이사", "opening": "개업", "contract": "계약",
    "ceremony": "고사·제사", "surgery": "수술", "travel": "여행", "general": "일반",
}

# 용도별 다관법 가중치(합 100): 황도흑도/사주조화/손없는날/건제십이신/이십팔수/생기복덕
_PURPOSE_WEIGHTS = {
    "wedding": {"hwangdo": 20, "saju": 26, "sonless": 11, "geonje": 18, "su28": 13, "saenggi": 12},
    # 출산: 아이-부모 궁합을 가장 중시 → saju 비중↑
    "birth": {"hwangdo": 20, "saju": 36, "sonless": 7, "geonje": 16, "su28": 11, "saenggi": 10},
    "moving": {"hwangdo": 18, "saju": 18, "sonless": 27, "geonje": 16, "su28": 11, "saenggi": 10},
    "opening": {"hwangdo": 20, "saju": 18, "sonless": 22, "geonje": 18, "su28": 12, "saenggi": 10},
    "contract": {"hwangdo": 22, "saju": 27, "sonless": 9, "geonje": 18, "su28": 13, "saenggi": 11},
    "ceremony": {"hwangdo": 27, "saju": 22, "sonless": 9, "geonje": 18, "su28": 13, "saenggi": 11},
    "surgery": {"hwangdo": 22, "saju": 31, "sonless": 6, "geonje": 18, "su28": 12, "saenggi": 11},
    "travel": {"hwangdo": 27, "saju": 22, "sonless": 9, "geonje": 18, "su28": 13, "saenggi": 11},
    "general": {"hwangdo": 23, "saju": 23, "sonless": 14, "geonje": 18, "su28": 11, "saenggi": 11},
}
# 공통 제시용 3관법(용도 무관 비교용)
PERSPECTIVES = {
    "H": {"label": "황도·중단 중시", "weights": {"hwangdo": 30, "saju": 16, "sonless": 9, "geonje": 23, "su28": 13, "saenggi": 9}},
    "B": {"label": "균형", "weights": {"hwangdo": 22, "saju": 24, "sonless": 14, "geonje": 20, "su28": 12, "saenggi": 8}},
    "M": {"label": "민속(손없는날) 중시", "weights": {"hwangdo": 18, "saju": 18, "sonless": 30, "geonje": 15, "su28": 11, "saenggi": 8}},
}


class DayScore(BaseModel):
    date: str
    ganzhi: str                 # 일진 간지(한글(한자))
    hwangdo: str                # 황/흑 + 신 이름
    sonless: bool
    warnings: list[str] = Field(default_factory=list)  # 충/원진/형
    factors: dict[str, int]     # hwangdo/saju/sonless/geonje raw 0~100
    geonje: str = ""            # 건제신 "성(成)"
    geonje_note: str = ""       # 건제신 한 줄 의미
    su28: str = ""              # 이십팔수 "실(室)"
    su28_note: str = ""         # 28수 길흉 한 줄
    saenggi: str = ""           # 생기복덕 라벨(생기/복덕/절명…)
    best_hours: list[dict] = Field(default_factory=list)   # 출산: 추천 시(時)
    score: int                  # 용도 가중 종합
    grade: str


class TaekilResult(BaseModel):
    purpose: str
    purpose_label: str
    user_day_branch: str
    best: list[DayScore]        # 추천 길일
    avoid: list[DayScore]       # 회피일
    perspectives: dict[str, dict]  # 관법별 라벨 + 추천 1위(다관법 비교)


def _bidx(b: str) -> int:
    return EARTHLY_BRANCHES.index(b)


def _geonje(month_branch: str, day_branch: str) -> tuple[str, int, str]:
    """건제십이신 (한자기호, 점수0~100, 의미). 월지와 같은 일지 = 建."""
    idx = (_bidx(day_branch) - _bidx(month_branch)) % 12
    ch = _GEONJE_ORDER[idx]
    score, note = _GEONJE_INFO[ch]
    return ch, score, note


def _hwangdo(month_branch: str, day_branch: str) -> tuple[str, str, bool]:
    """(신이름, 황/흑, 길여부)."""
    start = _CHEONGYONG_START.get(month_branch)
    if not start:
        return ("미상", "?", False)
    pos = (_bidx(day_branch) - _bidx(start)) % 12
    name, hb = _SHIN[pos]
    return (name, hb, hb == "황")


def _compat_avg(parent_chart: SajuChart, baby_chart: SajuChart) -> tuple[int, list[str]]:
    """아이-부모 궁합(5요소 A/B/C 평균)과 주의 신살."""
    from .compatibility import compute_compatibility
    compat = compute_compatibility(parent_chart, baby_chart)
    score = round(sum(p.total for p in compat.perspectives.values()) / max(1, len(compat.perspectives)))
    return score, [p.type for p in compat.penalties[:3]]


# 12시진 대표 시각(자시 모호 회피용 중간값)
_SIJIN = [("子", "00:30"), ("丑", "02:30"), ("寅", "04:30"), ("卯", "06:30"),
          ("辰", "08:30"), ("巳", "10:30"), ("午", "12:30"), ("未", "14:30"),
          ("申", "16:30"), ("酉", "18:30"), ("戌", "20:30"), ("亥", "22:30")]


def _best_hours(d: date, parent_chart: SajuChart, parent2_chart: SajuChart | None, top: int = 3) -> list[dict]:
    """출산 후보일의 12시진별 아이-부모 궁합 → 추천 시(時) 상위."""
    from datetime import time as _time
    out = []
    for branch, label in _SIJIN:
        hh, mm = int(label[:2]), int(label[3:])
        baby = build_chart(BirthInput(birth_date=d, birth_time=_time(hh, mm)), with_daewoon=False)
        s1, _ = _compat_avg(parent_chart, baby)
        score = s1 if parent2_chart is None else round((s1 + _compat_avg(parent2_chart, baby)[0]) / 2)
        hp = baby.pillars.hour
        out.append({"sijin": f"{branch}시", "time": label,
                    "ganzhi": f"{hp.stem}{hp.branch}" if hp else "", "score": score})
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:top]


def _score_day(d: date, parent_chart: SajuChart, purpose: str, bonmyeong: str = "",
               parent2_chart: SajuChart | None = None) -> DayScore:
    ch = build_chart(BirthInput(birth_date=d), with_daewoon=False)
    mb = ch.pillars.month.branch
    db = ch.pillars.day.branch
    ds = ch.pillars.day.stem
    user_branch = parent_chart.pillars.day.branch
    pair = frozenset({db, user_branch})

    # ① 황도흑도
    shin, hb, is_hwangdo = _hwangdo(mb, db)
    f_hwangdo = 85 if is_hwangdo else 30

    warns: list[str] = []
    if purpose == "birth":
        # ② 출산: 그날 태어날 아이와 부모의 궁합. 양부모면 둘의 평균.
        s1, w1 = _compat_avg(parent_chart, ch)
        if parent2_chart is not None:
            s2, w2 = _compat_avg(parent2_chart, ch)
            f_saju = round((s1 + s2) / 2)
            warns = list(dict.fromkeys(w1 + w2))[:3]
        else:
            f_saju, warns = s1, w1
    else:
        # ② 본인 사주 회피(일지 충/원진/형)
        f_saju = 70
        if pair in BRANCH_CONFLICTS:
            f_saju -= 45; warns.append("일지충")
        if pair in BRANCH_WONJIN:
            f_saju -= 20; warns.append("원진")
        if pair in BRANCH_PUNISH or (db == user_branch and db in BRANCH_SELF_PUNISH):
            f_saju -= 15; warns.append("형")
    f_saju = max(0, min(100, f_saju))

    # ③ 손없는날 (음력 끝자리 9·0)
    lday = ch.lunar_date.day
    sonless = (lday % 10) in (9, 0)
    f_sonless = 90 if sonless else 55

    # ④ 건제십이신 (중단 택일)
    gj_ch, f_geonje, gj_note = _geonje(mb, db)
    if f_geonje <= 28:  # 破·閉 = 大凶 → 경고 배지
        warns.append(f"{_GEONJE_KO[gj_ch]}({gj_ch})")

    # ⑤ 이십팔수(28수) 길흉 (歳事暦)
    su_ch, su_ko, su_note = _su28(d)
    f_su28 = _su28_score(su_ch, purpose)

    # ⑥ 생기복덕 (본명괘 + 그날 일지 → 생기/복덕/절명…)
    from .sinsal import saenggi_bokdeok
    sb_label, sb_gil = saenggi_bokdeok(bonmyeong, db) if bonmyeong else ("", "")
    f_saenggi = {"길": 85, "반": 55, "흉": 28}.get(sb_gil, 60)
    if sb_gil == "흉":
        warns.append(sb_label)

    factors = {"hwangdo": f_hwangdo, "saju": f_saju, "sonless": f_sonless,
               "geonje": f_geonje, "su28": f_su28, "saenggi": f_saenggi}
    w = _PURPOSE_WEIGHTS.get(purpose, _PURPOSE_WEIGHTS["general"])
    score = round(sum(factors[k] * w[k] / 100 for k in w))
    grade = "대길일" if score >= 80 else "길일" if score >= 65 else "보통" if score >= 50 else "흉일"

    return DayScore(
        date=d.isoformat(),
        ganzhi=f"{stem_korean(ds)}{branch_korean(db)}({ds}{db})",
        hwangdo=f"{shin}({hb}도)",
        sonless=sonless,
        warnings=warns,
        factors=factors,
        geonje=f"{_GEONJE_KO[gj_ch]}({gj_ch})",
        geonje_note=gj_note,
        su28=f"{su_ko}({su_ch})",
        su28_note=su_note,
        saenggi=sb_label,
        score=score,
        grade=grade,
    )


def recommend_dates(
    user_chart: SajuChart,
    start: date,
    days: int = 60,
    purpose: str = "general",
    top: int = 10,
    user_chart2: SajuChart | None = None,
) -> TaekilResult:
    """기간(start~start+days) 내 날짜 점수화 → 길일 top / 회피일.
    user_chart2: 출산택일의 두 번째 부모(선택)."""
    purpose = purpose if purpose in PURPOSES else "general"
    ub = user_chart.pillars.day.branch
    # 본명괘(구성 본명성, 생년·성별) → 생기복덕용. 출산은 부모 기준.
    from .sinsal import bonmyeong_gwae
    from .types import Gender
    bonmyeong = bonmyeong_gwae(user_chart.input.birth_date.year, user_chart.input.gender == Gender.MALE)
    p2 = user_chart2 if purpose == "birth" else None
    scored = [_score_day(start + timedelta(days=i), user_chart, purpose, bonmyeong, p2) for i in range(max(1, days))]
    best = sorted(scored, key=lambda x: x.score, reverse=True)[:top]
    avoid = [s for s in sorted(scored, key=lambda x: x.score) if s.warnings or s.grade == "흉일"][:5]

    # 출산: 추천 길일별 최적 시(時) 산출(상위 일자만 — 12시진×궁합)
    if purpose == "birth":
        from datetime import date as _d
        for ds_ in best:
            ds_.best_hours = _best_hours(_d.fromisoformat(ds_.date), user_chart, p2)

    # 관법별 추천 1위(다관법 비교) — 같은 기간을 관법마다 다르게 가중해 1위가 갈림
    persp: dict[str, dict] = {}
    for k, v in PERSPECTIVES.items():
        w = v["weights"]
        ranked = sorted(
            scored, key=lambda s: sum(s.factors[fk] * w[fk] / 100 for fk in w), reverse=True
        )
        topday = ranked[0]
        persp[k] = {
            "label": v["label"],
            "top_date": topday.date,
            "top_ganzhi": topday.ganzhi,
            "top_score": round(sum(topday.factors[fk] * w[fk] / 100 for fk in w)),
        }

    return TaekilResult(
        purpose=purpose,
        purpose_label=PURPOSES[purpose],
        user_day_branch=f"{branch_korean(ub)}({ub})",
        best=best,
        avoid=avoid,
        perspectives=persp,
    )
