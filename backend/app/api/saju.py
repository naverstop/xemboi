"""사주명식 API."""
from __future__ import annotations

from datetime import date as date_t
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.deps import get_locale, get_optional_user
from backend.app.domain.chat_dto import BirthDTO
from backend.app.repositories.auth_models import User
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, SajuChart

router = APIRouter(prefix="/api/saju", tags=["saju"])

# 오행 배속(전통 표준) — 오늘 일간의 오행 → 행운 색/방위. 결정적 장식 요소(단정 화법 아님).
_STEM_ELEM = {"甲": "목", "乙": "목", "丙": "화", "丁": "화", "戊": "토", "己": "토",
              "庚": "금", "辛": "금", "壬": "수", "癸": "수"}
_ELEM_LUCKY = {
    "목": {"color": "청록·초록", "direction": "동쪽"},
    "화": {"color": "빨강·주황", "direction": "남쪽"},
    "토": {"color": "노랑·베이지", "direction": "중앙(안정)"},
    "금": {"color": "흰색·금색", "direction": "서쪽"},
    "수": {"color": "검정·네이비", "direction": "북쪽"},
}


@router.post("/chart", response_model=SajuChart)
def post_chart(birth: BirthDTO, locale: str = Depends(get_locale)) -> SajuChart:
    """생년월일/시/성별 → 사주 8자 + 오행 + 십성 + 대운.

    locale(요청 로케일 X-Locale→user→Accept-Language→default)이 역법/경도를 결정한다:
    vi 면 105°E·hongoc_duc, ko 면 서울·sxtwl. birth_longitude/균시차/자시관법도 함께 전달.
    """
    try:
        bi = BirthInput(
            birth_date=birth.birth_date,
            birth_time=birth.birth_time,
            calendar=birth.calendar,
            is_leap_month=birth.is_leap_month,
            gender=birth.gender,
            apply_true_solar_time=birth.apply_true_solar_time,
            birth_longitude=birth.birth_longitude,          # 드롭 복구 — /today와 동일화(전수감사 P0-4)
            apply_equation_of_time=birth.apply_equation_of_time,
            night_zi_mode=birth.night_zi_mode,
            locale=locale,
        )
    except ValueError as e:  # 없는 윤달 입력 등 → 깔끔한 400(R1 메시지 전달)
        raise HTTPException(status_code=400, detail=str(e))
    return build_chart(bi)


@router.post("/today")
def post_today(
    birth: BirthDTO,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> dict[str, Any]:
    """B-2 오늘의 운세 — 무과금 결과 + tool 세션 발급(해설 무과금·추가질문 프리미엄 과금).
    오늘 일진 간지 × 본인 일간의 십성/충합(결정적) + 올해 배경.

    계산은 전부 기존 엔진 재사용: compute_pillars(오늘 일진), compute_ten_god(십성),
    BRANCH_CONFLICTS/SIX_COMBINATIONS(충·합), push_service._ILJIN_LINES(십성 한 줄),
    metrics.domain_scores(올해 배경 — 연 단위임을 명시해 표기).
    """
    from backend.app.saju import metrics as metrics_engine
    from backend.app.saju.constants import (
        BRANCH_CONFLICTS, BRANCH_SIX_COMBINATIONS, TEN_GODS_KO,
        branch_korean, compute_ten_god, stem_korean,
    )
    from backend.app.saju.pillars import compute_pillars
    from backend.app.services.push_service import _ILJIN_LINES

    try:
        bi = BirthInput(
            birth_date=birth.birth_date,
            birth_time=birth.birth_time,
            calendar=birth.calendar,
            is_leap_month=birth.is_leap_month,
            gender=birth.gender,
            apply_true_solar_time=birth.apply_true_solar_time,
            birth_longitude=birth.birth_longitude,
            apply_equation_of_time=birth.apply_equation_of_time,
            night_zi_mode=birth.night_zi_mode,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    chart = build_chart(bi, with_daewoon=False)
    today = date_t.today()
    today_fp = compute_pillars(BirthInput(birth_date=today))[0]
    u_stem, u_branch = chart.pillars.day.stem, chart.pillars.day.branch
    t_stem, t_branch = today_fp.day.stem, today_fp.day.branch
    tg = compute_ten_god(u_stem, t_stem)
    pair = frozenset({u_branch, t_branch})
    relation = None
    if u_branch != t_branch and pair in BRANCH_CONFLICTS:
        relation = {"kind": "chung", "note": "오늘 일지가 본인 일지를 충(沖) — 변동·이동수가 있으니 신중하게."}
    elif u_branch != t_branch and pair in BRANCH_SIX_COMBINATIONS:
        relation = {"kind": "hap", "note": "오늘 일지가 본인 일지와 합(合) — 인연·협조의 기운이 도와요."}
    # 일진↔내 4주 전관계(전수감사 Phase 3) — 종전엔 '일지↔일지 충·육합' 2종뿐이라 을신충(천간충)·
    # 형·파·해·원진·자형·타 궁위가 전부 누락(실측: 辛卯일×乙일간 relation=None). 공용 relations
    # 모듈(감수 엔진+확장, '오늘' 스코프 라벨)로 결정적 계산 — 없으면 '없음' 명시(창작 차단).
    from backend.app.saju.relations import luck_natal_relations
    relations_all = luck_natal_relations(chart, t_stem, t_branch, scope="오늘")
    elem = _STEM_ELEM.get(t_stem, "토")
    ds = metrics_engine.domain_scores(chart.model_dump(mode="json"), today)
    result = {
        "date": today.isoformat(),
        "iljin": {
            "stem": t_stem, "branch": t_branch,
            "label": f"{stem_korean(t_stem)}{branch_korean(t_branch)}({t_stem}{t_branch})",
        },
        "day_master": {"stem": u_stem, "ko": stem_korean(u_stem)},
        "ten_god": {"hanja": tg, "ko": TEN_GODS_KO.get(tg, tg), "line": _ILJIN_LINES.get(tg, "")},
        "relation": relation,
        "relations_all": relations_all,   # 일진↔내 4주 전관계(궁위 포함, 결정적) — 해설 근거
        "lucky": {"element": elem, **_ELEM_LUCKY.get(elem, {})},
        "year": ds,  # {"domains":[...], "seun":{...}} — 연 단위 배경(올해 내내 동일)
    }
    # 해설·추가질문(공용 tools 스트림)용 세션 — 결과 무과금, 추가질문은 프리미엄 표준(1,000/3,000P)
    from backend.app.services import tool_service
    result["tool_id"] = tool_service.persist_free_session(
        db, "today", today.isoformat(), birth_date=birth.birth_date, birth_time=birth.birth_time,
        calendar=str(getattr(birth.calendar, "value", birth.calendar)),
        is_leap_month=birth.is_leap_month,
        gender=str(getattr(birth.gender, "value", birth.gender)),
        apply_true_solar_time=birth.apply_true_solar_time,
        chart_json=chart.model_dump(mode="json"), result_json=result, user=user,
    )
    result["is_preview"] = user is None
    return result


# ── B-8 운세 캘린더 — 월별 일진표 + 개인 길흉(택일 엔진 셀 재사용) ──────────

# sxtwl jqIndex → 24절기 이름 (0=동지 기준, 2026년 실측 검증: 3=입춘 02-04·13=소서 07-07)
_JIEQI_NAMES = [
    "동지", "소한", "대한", "입춘", "우수", "경칩", "춘분", "청명", "곡우",
    "입하", "소만", "망종", "하지", "소서", "대서", "입추", "처서", "백로",
    "추분", "한로", "상강", "입동", "소설", "대설",
]


def _jieqi_map(year: int) -> dict[str, str]:
    """해당 연도 부근의 절기 날짜 → 이름. 연 경계(1월) 커버를 위해 전년도 포함."""
    import sxtwl
    from sxtwl import JD2DD
    out: dict[str, str] = {}
    for y in (year - 1, year, year + 1):
        for jq in sxtwl.getJieQiByYear(y):
            t = JD2DD(jq.jd)
            key = f"{int(t.Y):04d}-{int(t.M):02d}-{int(t.D):02d}"
            if 0 <= jq.jqIndex < 24:
                out[key] = _JIEQI_NAMES[jq.jqIndex]
    return out


# 택일 엔진 등급 → 캘린더 4색 배지
_GRADE_BADGE = {"대길일": "대길", "길일": "길", "보통": "평", "흉일": "흉"}


@router.post("/calendar")
def post_calendar(
    req: dict[str, Any],
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> dict[str, Any]:
    """B-8 운세 캘린더 — 무과금 결과 + tool 세션 발급(해설 무과금·추가질문 프리미엄 과금).
    한 달 치 일진 간지 + 개인 길흉 배지 + 충형해 경고 + 손없는날 + 절기.
    점수는 택일 엔진(_score_day, purpose=general)을 셀 단위로 재사용."""
    import calendar as _cal
    from backend.app.saju.constants import BRANCH_HARM
    from backend.app.saju.taekil import _score_day

    try:
        birth = BirthDTO(**{k: v for k, v in req.items() if k not in ("year", "month")})
        year = int(req.get("year") or date_t.today().year)
        month = int(req.get("month") or date_t.today().month)
        if not (1950 <= year <= 2100 and 1 <= month <= 12):
            raise ValueError("지원 범위는 1950~2100년이에요.")
        bi = BirthInput(
            birth_date=birth.birth_date, birth_time=birth.birth_time, calendar=birth.calendar,
            is_leap_month=birth.is_leap_month, gender=birth.gender,
            apply_true_solar_time=birth.apply_true_solar_time, birth_longitude=birth.birth_longitude,
            apply_equation_of_time=birth.apply_equation_of_time, night_zi_mode=birth.night_zi_mode,
        )
    except (ValueError, TypeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    chart = build_chart(bi, with_daewoon=False)
    user_db = chart.pillars.day.branch
    # 생기복덕(본명괘) 전달(전수감사 Phase 3) — 종전 미전달로 같은 날·같은 general 목적인데
    # 택일과 점수 27/31일 상이·등급 3일 뒤집힘(실측). 생년·성별이 있으므로 택일과 동일 계산.
    from backend.app.saju.sinsal import bonmyeong_gwae
    from backend.app.saju.types import Gender as _G
    bonmyeong = bonmyeong_gwae(chart.input.birth_date.year, chart.input.gender == _G.MALE)
    jieqi = _jieqi_map(year)
    days: list[dict[str, Any]] = []
    for dd in range(1, _cal.monthrange(year, month)[1] + 1):
        d = date_t(year, month, dd)
        s = _score_day(d, chart, "general", bonmyeong)
        warnings = list(s.warnings)
        # 해(害)는 택일 점수에 미반영(엔진 불변) — 캘린더 경고 아이콘으로만 추가
        day_branch = s.ganzhi[s.ganzhi.find("(") + 2] if "(" in s.ganzhi else ""
        if day_branch and day_branch != user_db and frozenset({day_branch, user_db}) in BRANCH_HARM:
            warnings.append("일지해")
        days.append({
            "date": d.isoformat(),
            "day": dd,
            "weekday": d.weekday(),
            "ganzhi": s.ganzhi,
            "grade": _GRADE_BADGE.get(s.grade, "평"),
            "score": s.score,
            "sonless": s.sonless,
            "warnings": warnings,
            "jieqi": jieqi.get(d.isoformat()),
        })
    result = {
        "year": year, "month": month, "today": date_t.today().isoformat(),
        "user_day_branch": user_db,
        "days": days,
        "note": "일반(general) 기준 길흉이에요. 결혼·이사 등 목적별 정밀 택일은 택일 메뉴에서 보실 수 있어요.",
    }
    # 해설·추가질문(공용 tools 스트림)용 세션 — 결과 무과금, 추가질문은 프리미엄 표준(1,000/3,000P)
    from backend.app.services import tool_service
    result["tool_id"] = tool_service.persist_free_session(
        db, "calendar", f"{year}-{month:02d}", birth_date=birth.birth_date, birth_time=birth.birth_time,
        calendar=str(getattr(birth.calendar, "value", birth.calendar)),
        is_leap_month=birth.is_leap_month,
        gender=str(getattr(birth.gender, "value", birth.gender)),
        apply_true_solar_time=birth.apply_true_solar_time,
        chart_json=chart.model_dump(mode="json"), result_json=result, user=user,
    )
    result["is_preview"] = user is None
    return result
