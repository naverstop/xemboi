"""사주 영역별 운세 비중(세운 반영) — 결정적 산출. 화면(chart_json 주입)·PDF 공통 단일 소스.

- 기질 6축은 타고난 성향이라 natal 고정(프론트/ PDF가 각자 표기) — 여기선 다루지 않음.
- 영역별 운세(직업/재물/대인/연애/건강)는 natal 경향 + '올해 세운'이 밀어주는 영역(부스트)로 산출 →
  해가 바뀌면(세운 변경) 값이 달라진다. 운영자 승인 규칙(2026-07):
    관성→직업(+여성 연애), 재성→재물(+남성 연애), 식상→대인(+재물 절반),
    인성→직업(절반)·건강, 비겁→대인, 건강운=세운 오행이 부족오행 보(補)면↑·과다면↓.
    부스트 세운 천간=+15(주), 세운 지지 본기=+7(보조). (관리자 조정 없음, 고정.)
"""
from __future__ import annotations

from datetime import date as _date
from typing import Any

from backend.app.saju.constants import (
    BRANCH_TO_WUXING, STEM_TO_WUXING, branch_korean, stem_korean,
)

# 십성 5분류(한자/한글) — chart_json.ten_gods 표면 7자리 집계용
_GROUP = {
    "比肩": "비겁", "劫財": "비겁", "食神": "식상", "傷官": "식상",
    "正財": "재성", "偏財": "재성", "正官": "관성", "偏官": "관성", "正印": "인성", "偏印": "인성",
}
# 오행 상생/상극(한자 오행)
_SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}   # X가 생하는 오행
_KE = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}       # X가 극하는 오행
_WX_KO = {"木": "목", "火": "화", "土": "토", "金": "금", "水": "수"}
_BOOST_MAIN = 15   # 세운 천간(주)
_BOOST_SUB = 7     # 세운 지지 본기(보조)


def _sc(n: float) -> int:
    return max(0, min(100, round(25 + n * 18)))


def _ten_god_groups(chart: dict) -> dict[str, int]:
    g = (chart or {}).get("ten_gods") or {}
    out = {"비겁": 0, "식상": 0, "재성": 0, "관성": 0, "인성": 0}
    for key in ("year_stem", "month_stem", "hour_stem", "year_branch", "month_branch", "day_branch", "hour_branch"):
        grp = _GROUP.get(g.get(key) or "")
        if grp:
            out[grp] += 1
    return out


def _wuxing_balance(chart: dict) -> float:
    w = (chart or {}).get("wuxing") or {}
    arr = [w.get(k, 0) for k in ("wood", "fire", "earth", "metal", "water")]
    mean = sum(arr) / 5
    if mean <= 0:
        return 0.5
    sd = (sum((x - mean) ** 2 for x in arr) / 5) ** 0.5
    return max(0.0, min(1.0, 1 - sd / mean / 1.4))


def _group_of(day_wx: str, other_wx: str) -> str | None:
    """일간 오행 대비 대상 오행의 십성 그룹(오행 생극)."""
    if not day_wx or not other_wx:
        return None
    if other_wx == day_wx:
        return "비겁"
    if _SHENG.get(day_wx) == other_wx:
        return "식상"
    if _SHENG.get(other_wx) == day_wx:
        return "인성"
    if _KE.get(day_wx) == other_wx:
        return "재성"
    if _KE.get(other_wx) == day_wx:
        return "관성"
    return None


def _seun_for(when: _date) -> tuple[str, str]:
    """해당 날짜의 세운(연주) 간지 — 입춘 반영(엔진 계산)."""
    from backend.app.saju.pillars import compute_pillars
    from backend.app.saju.types import BirthInput as _BI, CalendarType as _CT
    fp, *_ = compute_pillars(_BI(birth_date=when, calendar=_CT.SOLAR))
    return fp.year.stem, fp.year.branch


def domain_scores(chart: dict, when: _date | None = None) -> dict[str, Any]:
    """영역별 운세 비중(세운 반영) + 세운 표기. ten_gods 없으면 domains=None.

    반환: {"domains": [(label, value)...정렬], "seun": {stem,branch,stem_ko,branch_ko,year} | None}
    """
    if not (chart or {}).get("ten_gods"):
        return {"domains": None, "seun": None}
    when = when or _date.today()
    c = _ten_god_groups(chart)
    # natal 기준(프론트 sajuMetrics·PDF와 동일 공식)
    health_natal = round(35 + _wuxing_balance(chart) * 60)
    base = {
        "직업운": _sc(c["관성"] + c["인성"] * 0.5),
        "재물운": _sc(c["재성"]),
        "대인운": _sc((c["비겁"] + c["식상"]) / 2),
        "연애운": _sc((c["재성"] + c["관성"]) / 2),
        "건강운": max(0, min(100, health_natal)),
    }

    # 일간 오행
    day_stem = ((chart.get("pillars") or {}).get("day") or {}).get("stem")
    day_wx = STEM_TO_WUXING.get(day_stem or "")
    gender = str(((chart.get("input") or {}).get("gender")) or "").lower()
    is_female = "female" in gender

    seun_stem, seun_branch = _seun_for(when)
    seun_stem_wx = STEM_TO_WUXING.get(seun_stem)
    seun_branch_wx = BRANCH_TO_WUXING.get(seun_branch)

    boost = {"직업운": 0, "재물운": 0, "대인운": 0, "연애운": 0, "건강운": 0}

    def _apply(grp: str | None, amt: int) -> None:
        if grp == "관성":
            boost["직업운"] += amt
            if is_female:
                boost["연애운"] += amt      # 여성 배우자성=관성
        elif grp == "재성":
            boost["재물운"] += amt
            if not is_female:
                boost["연애운"] += amt      # 남성 배우자성=재성
        elif grp == "식상":
            boost["대인운"] += amt
            boost["재물운"] += amt // 2      # 식상생재
        elif grp == "인성":
            boost["직업운"] += amt // 2
            boost["건강운"] += amt
        elif grp == "비겁":
            boost["대인운"] += amt

    _apply(_group_of(day_wx, seun_stem_wx), _BOOST_MAIN)     # 세운 천간(주)
    _apply(_group_of(day_wx, seun_branch_wx), _BOOST_SUB)    # 세운 지지 본기(보조)

    # 건강운 조후: 세운 오행이 명식 부족오행을 보(補)하면 ↑, 과다오행을 더 태우면 ↓
    w = (chart or {}).get("wuxing") or {}
    wx_map = {"木": "wood", "火": "fire", "土": "earth", "金": "metal", "水": "water"}
    counts = {k: w.get(v, 0) for k, v in wx_map.items()}
    if counts:
        lack = min(counts, key=counts.get)
        over = max(counts, key=counts.get)
        if seun_stem_wx == lack:
            boost["건강운"] += _BOOST_SUB
        elif seun_stem_wx == over and counts[over] >= 3:
            boost["건강운"] -= _BOOST_SUB

    domains = [
        {"label": k, "value": max(0, min(100, base[k] + boost[k]))}
        for k in ("직업운", "재물운", "대인운", "연애운", "건강운")
    ]
    domains.sort(key=lambda d: d["value"], reverse=True)

    seun = {
        "stem": seun_stem, "branch": seun_branch,
        "stem_ko": stem_korean(seun_stem), "branch_ko": branch_korean(seun_branch),
        "year": when.year,
    }
    return {"domains": domains, "seun": seun}
