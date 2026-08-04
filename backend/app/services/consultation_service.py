"""1:1 인적 상담 서비스 — 입점업체(상담사) CRUD·간판 업로드·정산 산출·실적 집계.

관리자 등록/조회, 사용자용 공개 리스트, 상담사별 개별 단가/시간/수수료의 전역 폴백,
정산(수수료·세금) 계산을 담당한다. 실시간 세션/과금(WS)은 Phase 2~3(consultation WS 모듈).
설계: [[consultation-1on1-plan]].
"""
from __future__ import annotations

from pathlib import Path

import json
import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.repositories.auth_models import User
from backend.app.repositories.consultation_models import (
    Consultant,
    ConsultationSession,
    ConsultationSettlement,
)
from backend.app.services import settings_service

SPECIALTIES = ("saju", "tarot", "both")
PRICE_UNITS = ("session", "minute", "hour")     # 회당 | 분당 | 시간당(표시), 실차감은 블록제
CONSULT_STATUSES = ("active", "coming_soon", "hidden")  # 정상 | 입점예정 | 숨김
KEYWORD_MAX = 8       # #키워드 최대 개수
KEYWORD_LEN = 12      # 키워드 1개 최대 글자수

# 간판 이미지 저장 경로(웹 서빙은 /api/consultation/signboards/{name} 엔드포인트) — 저장소 루트/data/media/consultants
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MEDIA_DIR = os.path.join(_ROOT, "data", "media", "consultants")
_ALLOWED_IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}


# ───────────────────────── #키워드(전문영역) ─────────────────────────

def parse_keywords(c: Consultant) -> list[str]:
    """저장된 keywords(JSON 배열 문자열) → 리스트. 손상/미설정이면 빈 리스트."""
    raw = getattr(c, "keywords", None)
    if not raw:
        return []
    try:
        v = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if not isinstance(v, list):
        return []
    return [str(x) for x in v if str(x).strip()][:KEYWORD_MAX]


def normalize_keywords(value: Any) -> str:
    """리스트 또는 CSV 문자열 → 정규화 JSON 배열 문자열. #제거·트림·중복제거·개수/길이 상한."""
    if isinstance(value, str):
        parts: list[str] = re.split(r"[,\n]", value)
    elif isinstance(value, (list, tuple)):
        parts = [str(x) for x in value]
    else:
        parts = []
    items: list[str] = []
    seen: set[str] = set()
    for p in parts:
        t = str(p).strip().lstrip("#").strip()[:KEYWORD_LEN]
        if not t:
            continue
        key = t.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append(t)
        if len(items) >= KEYWORD_MAX:
            break
    return json.dumps(items, ensure_ascii=False)


# ───────────────────────── 요일별 영업시간(KST) ─────────────────────────
# {"0":{"open":"10:00","close":"19:00"}, ... "6":...}  (0=월 ~ 6=일, datetime.weekday()). 없는 요일=휴무.
# 안내 표시 + 예약 슬롯 가능 범위 제한용. 즉시 '상담가능'(presence)과는 무관(무한대기 재발 방지).
_KST_OFFSET_H = 9  # 한국 표준시(DST 없음)
_WD_KEYS = ("0", "1", "2", "3", "4", "5", "6")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def parse_business_hours(c: Consultant) -> Optional[dict[str, Any]]:
    raw = getattr(c, "business_hours", None)
    if not raw:
        return None
    try:
        v = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return v if isinstance(v, dict) and v else None


def normalize_business_hours(value: Any) -> Optional[str]:
    """요일→{open,close} 정규화 JSON. 형식오류·역전(open>=close)·휴무는 제외. 전부 비면 None(상시)."""
    if value in (None, "", {}):
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return None
    if not isinstance(value, dict):
        return None
    out: dict[str, dict[str, str]] = {}
    for k in _WD_KEYS:
        ent = value.get(k, value.get(int(k)))
        if not isinstance(ent, dict):
            continue
        o, cl = str(ent.get("open", "")), str(ent.get("close", ""))
        if _TIME_RE.match(o) and _TIME_RE.match(cl) and o < cl:
            out[k] = {"open": o, "close": cl}
    return json.dumps(out, ensure_ascii=False) if out else None


def within_business_hours(c: Consultant, when_utc: datetime) -> bool:
    """when_utc(UTC)가 상담사 영업시간(KST) 내인지. 미설정=상시 True, 휴무일/시간외=False."""
    h = parse_business_hours(c)
    if not h:
        return True
    kst = when_utc + timedelta(hours=_KST_OFFSET_H)
    ent = h.get(str(kst.weekday()))
    if not isinstance(ent, dict) or not ent.get("open") or not ent.get("close"):
        return False
    return ent["open"] <= kst.strftime("%H:%M") < ent["close"]


# ───────────────────────── 단가/정산 산출 ─────────────────────────

def _raw_block_price(
    db: Session,
    *,
    price_unit: str,
    rate_p: Optional[int],
    per_min_p: Optional[int],
    per_hour_p: Optional[int],
    dur: int,
) -> int:
    """요금 단위 → 1회(=dur분) 블록 환산가(하한 미적용). 실제 차감은 이 블록가로 이뤄진다.

    minute: 분당 × 분. hour: 시간당 × 분 / 60(반올림). session/기타: rate_p(없으면 전역기본).
    """
    unit = price_unit or "session"
    if unit == "minute" and per_min_p is not None:
        return int(per_min_p) * int(dur)
    if unit == "hour" and per_hour_p is not None:
        return int(round(int(per_hour_p) * int(dur) / 60))
    return int(rate_p) if rate_p is not None else settings_service.get_int(db, "consultation_default_price_p", 59000)


def _validate_pricing(
    db: Session,
    *,
    price_unit: str,
    rate_p: Optional[int],
    per_min_p: Optional[int],
    per_hour_p: Optional[int],
    duration_min: Optional[int],
) -> None:
    """요금 정합성 검증 — 선택 단위의 요금이 실제 반영되도록(표시=실차감), 0P/하한 미만 방지.

    minute/hour 단위는 해당 요금(>0)이 반드시 있어야 한다(없으면 rate_p/전역으로 조용히 폴백해 표시와
    실차감이 어긋나므로 거부). session 단위의 rate_p 는 비우면 전역 기본값을 쓰므로 None 허용. 최종 1회
    블록 환산가가 max(1, 하한) 미만이면 거부(반올림 0P·오타 방지).
    """
    unit = price_unit or "session"
    if unit == "minute" and (per_min_p is None or per_min_p <= 0):
        raise ValueError("분당 요금(0보다 큰 값)을 입력해 주세요.")
    if unit == "hour" and (per_hour_p is None or per_hour_p <= 0):
        raise ValueError("시간당 요금(0보다 큰 값)을 입력해 주세요.")
    if unit == "session" and rate_p is not None and rate_p <= 0:
        raise ValueError("세션 요금은 0보다 커야 해요. (비우면 전역 기본값 적용)")
    dur = duration_min if duration_min is not None else settings_service.get_int(db, "consultation_default_duration_min", 30)
    raw = _raw_block_price(db, price_unit=unit, rate_p=rate_p, per_min_p=per_min_p, per_hour_p=per_hour_p, dur=dur)
    floor = settings_service.get_int(db, "consultation_min_price_p", 0)
    minimum = max(1, floor)
    if raw < minimum:
        if floor > 0:
            raise ValueError(f"1회({dur}분) 요금이 최소 금액 {floor:,}P보다 낮아요. 요금을 올려 주세요.")
        raise ValueError(f"1회({dur}분) 요금이 0P가 되지 않도록 요금을 확인해 주세요.")


def effective(db: Session, c: Consultant) -> tuple[int, int, int]:
    """상담사 개별 설정 우선, NULL 이면 전역 기본값으로 (단가P, 시간분, 수수료%) 반환.

    단가는 요금 단위(세션/분/시간)를 1회 블록가로 환산하고, 관리자 하한(consultation_min_price_p,
    0=제한없음) 미만이면 하한으로 끌어올린다(안전망). 실차감·정산·연장은 이 블록가를 그대로 쓴다.
    """
    dur = c.duration_min if c.duration_min is not None else settings_service.get_int(db, "consultation_default_duration_min", 30)
    comm = c.commission_pct if c.commission_pct is not None else settings_service.get_int(db, "consultation_commission_pct", 20)
    price = _raw_block_price(
        db,
        price_unit=getattr(c, "price_unit", "session") or "session",
        rate_p=c.rate_p,
        per_min_p=getattr(c, "per_min_p", None),
        per_hour_p=getattr(c, "per_hour_p", None),
        dur=dur,
    )
    floor = settings_service.get_int(db, "consultation_min_price_p", 0)
    if floor > 0 and price < floor:
        price = floor
    return price, dur, comm


def compute_settlement(revenue_p: int, commission_pct: int, tax_pct: float) -> dict[str, Any]:
    """정산 산출 — payout = 매출×(1−수수료%)×(1−세율%). 반올림(원 단위=P).

    예: 50,000P·수수료20%·세율3.3% → 수수료 10,000, 상담사몫 40,000, 원천징수 1,320, 실지급 38,680.
    """
    revenue_p = int(revenue_p or 0)
    commission_p = round(revenue_p * commission_pct / 100)
    taxable_p = revenue_p - commission_p
    tax_p = round(taxable_p * tax_pct / 100)
    payout_p = taxable_p - tax_p
    return {
        "revenue_p": revenue_p,
        "commission_pct": commission_pct,
        "commission_p": commission_p,
        "taxable_p": taxable_p,
        "tax_pct": tax_pct,
        "tax_p": tax_p,
        "payout_p": payout_p,
    }


# ───────────────────────── 직렬화(dict) ─────────────────────────

# ───────────────────────── 접속상태(presence) 정확도 ─────────────────────────

# 하트비트(25s)가 모바일/백그라운드 탭에서 스로틀·서스펜드되어도 진짜 온라인을 죽이지 않도록 넉넉히(5분).
# 단, 실제 콘솔 소켓 생존(_console_alive)을 last_seen 보다 우선 신뢰한다.
PRESENCE_STALE_SEC = 300


def _console_alive(consultant_id: int) -> bool:
    """이 프로세스(상담 워커)의 in-memory 콘솔 소켓 생존 여부. 워커에선 정확, 메인 앱에선 항상 False(폴백)."""
    try:
        from backend.app.services.consultation_rt import manager
        return manager.console_online(int(consultant_id))
    except Exception:  # noqa: BLE001
        return False


def _effective_presence(c: Consultant, now: Optional[datetime] = None) -> str:
    """표시용 접속상태 — DB presence=online 이어도 실제 연결이 없으면 offline 로 보정(가짜 대기중 방지).

    판정 우선순위: ①실제 콘솔 소켓 생존(_console_alive) → online 확정(false-offline 방지) ②소켓 없음+last_seen
    신선(≤5분) → online ③그 외 → offline. offline/busy(상담중)는 그대로(토글 off·세션 우선 존중).
    """
    p = c.presence or "offline"
    if p == "online":
        if _console_alive(c.id):
            return "online"
        ls = c.last_seen_at
        if ls is None or ((now or datetime.utcnow()) - ls).total_seconds() > PRESENCE_STALE_SEC:
            return "offline"
    return p


def reset_presence_all(db: Session) -> int:
    """워커/앱 기동 시 호출 — in-memory 콘솔 연결이 없으므로 모든 presence 를 offline 로 리셋(가짜 대기중 제거)."""
    from sqlalchemy import update
    res = db.execute(update(Consultant).where(Consultant.presence != "offline").values(presence="offline"))
    db.commit()
    return int(res.rowcount or 0)


def touch_last_seen(db: Session, consultant_id: int) -> None:
    """콘솔 하트비트 수신 시 last_seen_at 갱신(살아있음 표시). presence 는 변경하지 않음."""
    c = db.get(Consultant, consultant_id)
    if c is not None:
        c.last_seen_at = datetime.utcnow()
        db.commit()


def public_dict(db: Session, c: Consultant, eng: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """사용자 상담사 카드용 — PII 최소. 유효 단가/시간 + 실시간 상태 + 상담건수·만족도(간판)."""
    price, dur, _comm = effective(db, c)
    eng = eng or {}
    return {
        "id": c.id,
        "business_name": c.business_name,
        "specialty": c.specialty,
        "signboard_image_url": c.signboard_image_url,
        "intro": c.intro,
        "keywords": parse_keywords(c),                   # #전문영역 칩
        "price_p": price,                                # 1회(블록) 실제 차감가
        "duration_min": dur,
        "price_unit": getattr(c, "price_unit", "session") or "session",  # 표시용(session|minute|hour)
        "per_min_p": getattr(c, "per_min_p", None),      # 분당 요금(표시)
        "per_hour_p": getattr(c, "per_hour_p", None),    # 시간당 요금(표시)
        "status": getattr(c, "status", "active") or "active",  # active | coming_soon(입점예정)
        "business_hours": parse_business_hours(c),       # 요일별 영업시간(안내용, 없으면 null)
        "presence": _effective_presence(c),  # offline | online | busy (stale online → offline 보정)
        "session_count": eng.get("session_count", 0),   # 누적 상담건수(완료)
        "rating_avg": eng.get("rating_avg"),            # 평균 만족도(1~5, 없으면 null)
        "rating_count": eng.get("rating_count", 0),     # 평점 참여 수
    }


def self_dict(db: Session, c: Consultant) -> dict[str, Any]:
    """상담사 본인 설정 화면용 — 셀프 편집 가능한 필드 + 예상 차감가. PII·정산 통계 제외."""
    price, dur, _comm = effective(db, c)
    return {
        "id": c.id,
        "business_name": c.business_name,   # 읽기전용(관리자 통제)
        "specialty": c.specialty,           # 읽기전용
        "signboard_image_url": c.signboard_image_url,
        "intro": c.intro,
        "keywords": parse_keywords(c),
        "price_unit": getattr(c, "price_unit", "session") or "session",
        "rate_p": c.rate_p,
        "per_min_p": getattr(c, "per_min_p", None),
        "per_hour_p": getattr(c, "per_hour_p", None),
        "duration_min": dur,                # 유효 블록(분, 관리자 통제) — 예상가 계산용
        "eff_duration_min": dur,            # 콘솔 표시 호환(=duration_min)
        "duration_min_raw": c.duration_min,
        "eff_price_p": price,               # 1회 예상 차감가(하한 반영)
        "min_price_p": settings_service.get_int(db, "consultation_min_price_p", 0),  # 요금 하한(0=없음)
        "status": getattr(c, "status", "active") or "active",
        "business_hours": parse_business_hours(c) or {},  # 요일별 영업시간(편집용)
        "presence": c.presence,
        "is_active": c.is_active,
        "self_managed": bool(getattr(c, "self_managed", True)),
    }


def admin_dict(
    db: Session,
    c: Consultant,
    stats: Optional[dict[str, Any]] = None,
    eng: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """관리자 리스트용 — 전체 필드 + 실적/정산 집계 + 상담건수·만족도."""
    price, dur, comm = effective(db, c)
    eng = eng or {}
    return {
        "session_count": eng.get("session_count", 0),
        "rating_avg": eng.get("rating_avg"),
        "rating_count": eng.get("rating_count", 0),
        "id": c.id,
        "login_email": c.login_email,
        "user_id": c.user_id,
        "linked": c.user_id is not None,  # 로그인 계정 연결 여부
        "business_name": c.business_name,
        "specialty": c.specialty,
        "signboard_image_url": c.signboard_image_url,
        "intro": c.intro,
        "keywords": parse_keywords(c),
        # 원본(개별 설정, NULL=전역)
        "rate_p": c.rate_p,
        "duration_min_raw": c.duration_min,
        "commission_pct_raw": c.commission_pct,
        "price_unit": getattr(c, "price_unit", "session") or "session",
        "per_min_p": getattr(c, "per_min_p", None),
        "per_hour_p": getattr(c, "per_hour_p", None),
        # 유효값(폴백 반영)
        "eff_price_p": price,
        "eff_duration_min": dur,
        "eff_commission_pct": comm,
        "is_active": c.is_active,
        "status": getattr(c, "status", "active") or "active",
        "self_managed": bool(getattr(c, "self_managed", True)),
        "presence": _effective_presence(c),
        "sort_order": c.sort_order,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "stats": stats or _empty_stats(),
    }


def _empty_stats() -> dict[str, Any]:
    return {"sessions": 0, "revenue_p": 0, "payout_pending_p": 0, "payout_settled_p": 0}


# ───────────────────────── 조회 ─────────────────────────

def _engagement_by_consultant(db: Session) -> dict[int, dict[str, Any]]:
    """상담사별 참여 집계 — 완료 상담건수 + 평균 만족도 + 평점 참여수(간판 표시용)."""
    out: dict[int, dict[str, Any]] = {}
    stmt = (
        select(
            ConsultationSession.consultant_id,
            func.count().filter(ConsultationSession.status == "completed"),
            func.avg(ConsultationSession.rating),
            func.count(ConsultationSession.rating),
        )
        .group_by(ConsultationSession.consultant_id)
    )
    for cid, sessions, avg, rcount in db.execute(stmt).all():
        out[int(cid)] = {
            "session_count": int(sessions or 0),
            "rating_avg": round(float(avg), 1) if avg is not None else None,
            "rating_count": int(rcount or 0),
        }
    return out


def list_public(db: Session, specialty: Optional[str] = None) -> list[dict[str, Any]]:
    """사용자 화면 리스트 — 활성 상담사. 입점예정(coming_soon)은 노출(오버레이·신청불가), 숨김(hidden)은 제외.

    specialty 필터(해당 분야 또는 'both'). 간판 만족도 포함. 정렬: 입점예정은 뒤로(신청가능 우선).
    """
    stmt = select(Consultant).where(
        Consultant.is_active.is_(True), Consultant.status != "hidden"
    )
    if specialty in ("saju", "tarot"):
        stmt = stmt.where(Consultant.specialty.in_([specialty, "both"]))
    # 입점예정(coming_soon)을 하단으로 — 신청 가능한 상담사가 위에 오도록
    coming_last = (Consultant.status == "coming_soon")
    stmt = stmt.order_by(coming_last.asc(), Consultant.sort_order.asc(), Consultant.id.asc())
    rows = db.execute(stmt).scalars().all()
    eng = _engagement_by_consultant(db)
    return [public_dict(db, c, eng.get(c.id)) for c in rows]


def _stats_by_consultant(db: Session) -> dict[int, dict[str, Any]]:
    """정산 원장 집계 — 상담사별 세션수·매출·정산(대기/완료) 합계."""
    out: dict[int, dict[str, Any]] = {}
    stmt = (
        select(
            ConsultationSettlement.consultant_id,
            func.count(ConsultationSettlement.id),
            func.coalesce(func.sum(ConsultationSettlement.revenue_p), 0),
            func.coalesce(
                func.sum(
                    ConsultationSettlement.payout_p
                ).filter(ConsultationSettlement.status == "pending"),
                0,
            ),
            func.coalesce(
                func.sum(
                    ConsultationSettlement.payout_p
                ).filter(ConsultationSettlement.status == "settled"),
                0,
            ),
        )
        .group_by(ConsultationSettlement.consultant_id)
    )
    for cid, cnt, rev, pending, settled in db.execute(stmt).all():
        out[int(cid)] = {
            "sessions": int(cnt or 0),
            "revenue_p": int(rev or 0),
            "payout_pending_p": int(pending or 0),
            "payout_settled_p": int(settled or 0),
        }
    return out


def admin_list(db: Session) -> list[dict[str, Any]]:
    stats = _stats_by_consultant(db)
    eng = _engagement_by_consultant(db)
    rows = db.execute(
        select(Consultant).order_by(Consultant.sort_order.asc(), Consultant.id.asc())
    ).scalars().all()
    return [admin_dict(db, c, stats.get(c.id), eng.get(c.id)) for c in rows]


def settlement_dict(stl: ConsultationSettlement, consultant_name: Optional[str] = None) -> dict[str, Any]:
    """정산 원장 1건 직렬화 — 1P=1원이라 금액은 원으로 표기(프론트)."""
    return {
        "id": stl.id,
        "session_id": stl.session_id,
        "consultant_id": stl.consultant_id,
        "consultant_name": consultant_name,
        "revenue_p": stl.revenue_p,          # 매출(원)
        "commission_pct": stl.commission_pct,
        "commission_p": stl.commission_p,    # 플랫폼 수수료(원)
        "taxable_p": stl.taxable_p,          # 상담사 몫(과세대상, 원)
        "tax_pct": stl.tax_pct,
        "tax_p": stl.tax_p,                  # 원천징수(원)
        "payout_p": stl.payout_p,            # 실지급(원)
        "status": stl.status,                # pending | settled
        "settled_at": stl.settled_at.isoformat() if stl.settled_at else None,
        "created_at": stl.created_at.isoformat() if stl.created_at else None,
    }


def list_settlements(
    db: Session,
    consultant_id: Optional[int] = None,
    status: Optional[str] = None,
    cycle: Optional[str] = None,
    limit: int = 300,
) -> list[dict[str, Any]]:
    """정산 명세 목록(상담사명 조인). 상담사·상태·정산월(cycle 'YYYY-MM': 전월26~당월25) 필터."""
    stmt = (
        select(ConsultationSettlement, Consultant.business_name)
        .join(Consultant, ConsultationSettlement.consultant_id == Consultant.id)
    )
    if consultant_id is not None:
        stmt = stmt.where(ConsultationSettlement.consultant_id == consultant_id)
    if status in ("pending", "settled"):
        stmt = stmt.where(ConsultationSettlement.status == status)
    if cycle:
        from backend.app.services.settlement_cycle import cycle_window
        w0, w1 = cycle_window(cycle)
        stmt = stmt.where(ConsultationSettlement.created_at >= w0,
                          ConsultationSettlement.created_at < w1)
    stmt = stmt.order_by(ConsultationSettlement.created_at.desc()).limit(limit)
    return [settlement_dict(stl, name) for stl, name in db.execute(stmt).all()]


def settlement_totals(db: Session, cycle: Optional[str] = None) -> dict[str, int]:
    """정산 합계 — 매출·플랫폼 수수료(관리자 수익)·대기/완료 실지급(원). cycle 지정 시 해당 정산월만."""
    conds = []
    if cycle:
        from backend.app.services.settlement_cycle import cycle_window
        w0, w1 = cycle_window(cycle)
        conds = [ConsultationSettlement.created_at >= w0, ConsultationSettlement.created_at < w1]

    def q(col, *extra):
        st = select(func.coalesce(func.sum(col), 0)).where(*conds, *extra)
        return int(db.execute(st).scalar() or 0)

    return {
        "revenue_p": q(ConsultationSettlement.revenue_p),
        "commission_p": q(ConsultationSettlement.commission_p),   # 관리자(플랫폼) 수익 합계 — 별도 집계(운영자 지시)
        "tax_p": q(ConsultationSettlement.tax_p),
        "payout_pending_p": q(ConsultationSettlement.payout_p, ConsultationSettlement.status == "pending"),
        "payout_settled_p": q(ConsultationSettlement.payout_p, ConsultationSettlement.status == "settled"),
    }


def consultant_earnings(db: Session, consultant_id: int) -> dict[str, Any]:
    """상담사 본인 수익 요약 — 오늘/이번달/올해/전체의 상담건수·매출·실지급(수익). KST 기준 기간.

    정산행(세션 종료 시 생성)의 created_at 기준 집계. 금액은 원(1P=1원). 실지급 지급대기/완료도 함께.
    상담사 콘솔 '내 수익' 뷰 전용 — 자기 consultant_id 만 집계(권한은 라우터 require_consultant).
    """
    from datetime import timedelta, timezone

    KST = timezone(timedelta(hours=9))
    now_kst = datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(KST)
    day_kst = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    month_kst = day_kst.replace(day=1)
    year_kst = day_kst.replace(month=1, day=1)

    def _utc(dt: datetime) -> datetime:  # KST 경계 → DB(UTC naive) 경계
        return dt.astimezone(timezone.utc).replace(tzinfo=None)

    def _period(since: Optional[datetime]) -> dict[str, int]:
        stmt = select(
            func.count(ConsultationSettlement.id),
            func.coalesce(func.sum(ConsultationSettlement.revenue_p), 0),
            func.coalesce(func.sum(ConsultationSettlement.payout_p), 0),
        ).where(ConsultationSettlement.consultant_id == consultant_id)
        if since is not None:
            stmt = stmt.where(ConsultationSettlement.created_at >= since)
        cnt, rev, pay = db.execute(stmt).one()
        return {"count": int(cnt or 0), "revenue_p": int(rev or 0), "payout_p": int(pay or 0)}

    def _payout_by_status(status: str) -> int:
        return int(
            db.execute(
                select(func.coalesce(func.sum(ConsultationSettlement.payout_p), 0)).where(
                    ConsultationSettlement.consultant_id == consultant_id,
                    ConsultationSettlement.status == status,
                )
            ).scalar()
            or 0
        )

    return {
        "currency": "P",
        "today": _period(_utc(day_kst)),
        "month": _period(_utc(month_kst)),
        "year": _period(_utc(year_kst)),
        "total": _period(None),
        "payout_pending_p": _payout_by_status("pending"),  # 지급대기(현재 받을 예정 금액)
        "payout_settled_p": _payout_by_status("settled"),   # 지급완료 누계
    }


def set_settlement_status(db: Session, settlement_id: int, settled: bool) -> ConsultationSettlement:
    """정산 실지급 처리(pending→settled) / 취소(settled→pending)."""
    stl = db.get(ConsultationSettlement, settlement_id)
    if stl is None:
        raise LookupError("정산 내역을 찾을 수 없어요.")
    stl.status = "settled" if settled else "pending"
    stl.settled_at = datetime.utcnow() if settled else None
    db.commit()
    db.refresh(stl)
    return stl


def settle_all_for_consultant(db: Session, consultant_id: int) -> dict[str, int]:
    """상담사의 정산대기(pending) 전체를 일괄 실지급 처리."""
    rows = db.execute(
        select(ConsultationSettlement).where(
            ConsultationSettlement.consultant_id == consultant_id,
            ConsultationSettlement.status == "pending",
        )
    ).scalars().all()
    now = datetime.utcnow()
    total = 0
    for stl in rows:
        stl.status = "settled"
        stl.settled_at = now
        total += stl.payout_p
    if rows:
        db.commit()
    return {"settled": len(rows), "total_payout_p": int(total)}


def get_consultant(db: Session, consultant_id: int) -> Optional[Consultant]:
    return db.get(Consultant, consultant_id)


def get_consultant_by_user(db: Session, user_id: int) -> Optional[Consultant]:
    return db.execute(
        select(Consultant).where(Consultant.user_id == user_id)
    ).scalars().first()


# ───────────────────────── 생성/수정/삭제(관리자) ─────────────────────────

def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def _resolve_user_id(db: Session, login_email: str) -> Optional[int]:
    """login_email 과 일치하는 User.id 조회(가입 전이면 None → 이후 link_user 로 연결)."""
    u = db.execute(select(User).where(User.email == login_email)).scalars().first()
    return u.id if u else None


def create_consultant(
    db: Session,
    *,
    login_email: str,
    business_name: str,
    specialty: str = "saju",
    intro: Optional[str] = None,
    rate_p: Optional[int] = None,
    duration_min: Optional[int] = None,
    commission_pct: Optional[int] = None,
    is_active: bool = True,
    sort_order: int = 100,
    keywords: Any = None,
    price_unit: str = "session",
    per_min_p: Optional[int] = None,
    per_hour_p: Optional[int] = None,
    status: str = "active",
) -> Consultant:
    email = _norm_email(login_email)
    if not email or "@" not in email:
        raise ValueError("올바른 입점 ID(이메일)를 입력해 주세요.")
    if not (business_name or "").strip():
        raise ValueError("업체명을 입력해 주세요.")
    if specialty not in SPECIALTIES:
        raise ValueError("분야는 saju | tarot | both 중 하나여야 해요.")
    if price_unit not in PRICE_UNITS:
        raise ValueError("요금 단위는 session | minute | hour 중 하나여야 해요.")
    if status not in CONSULT_STATUSES:
        raise ValueError("상태는 active | coming_soon | hidden 중 하나여야 해요.")
    _validate_pricing(db, price_unit=price_unit, rate_p=rate_p, per_min_p=per_min_p, per_hour_p=per_hour_p, duration_min=duration_min)
    existing = db.execute(
        select(Consultant).where(Consultant.login_email == email)
    ).scalars().first()
    if existing is not None:
        raise ValueError("이미 등록된 입점 ID(이메일)예요.")
    c = Consultant(
        login_email=email,
        user_id=_resolve_user_id(db, email),
        business_name=business_name.strip(),
        specialty=specialty,
        intro=(intro or None),
        keywords=(normalize_keywords(keywords) if keywords is not None else None),
        rate_p=rate_p,
        duration_min=duration_min,
        commission_pct=commission_pct,
        price_unit=price_unit,
        per_min_p=per_min_p,
        per_hour_p=per_hour_p,
        is_active=is_active,
        status=status,
        sort_order=sort_order,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


_UPDATABLE = {
    "business_name", "specialty", "intro", "keywords", "rate_p", "duration_min",
    "commission_pct", "price_unit", "per_min_p", "per_hour_p",
    "is_active", "status", "self_managed", "sort_order", "signboard_image_url", "business_hours",
}

# 상담사 본인이 셀프 편집 가능한 필드. 상호(business_name)는 상담사가 직접 입력(카드 표시).
# 관리자 전용: specialty/commission_pct/sort_order/is_active/self_managed(간판은 별도 업로드 엔드포인트).
_SELF_UPDATABLE = {"business_name", "intro", "keywords", "price_unit", "rate_p", "per_min_p", "per_hour_p", "status", "business_hours"}


def update_consultant(db: Session, consultant_id: int, **fields: Any) -> Consultant:
    c = db.get(Consultant, consultant_id)
    if c is None:
        raise LookupError("상담사를 찾을 수 없어요.")
    if "specialty" in fields and fields["specialty"] not in SPECIALTIES:
        raise ValueError("분야는 saju | tarot | both 중 하나여야 해요.")
    if "business_name" in fields and not (fields["business_name"] or "").strip():
        raise ValueError("업체명을 비울 수 없어요.")
    if "price_unit" in fields and fields["price_unit"] not in PRICE_UNITS:
        raise ValueError("요금 단위는 session | minute | hour 중 하나여야 해요.")
    if "status" in fields and fields["status"] not in CONSULT_STATUSES:
        raise ValueError("상태는 active | coming_soon | hidden 중 하나여야 해요.")
    for k, v in fields.items():
        if k not in _UPDATABLE:
            continue
        if k == "keywords":
            v = normalize_keywords(v)
        elif k == "business_hours":
            v = normalize_business_hours(v)
        setattr(c, k, v)
    # 최종 상태로 요금 정합성 검증(단위-요금 일치·0P/하한 방지). 실패 시 롤백해 세션을 깨끗이 유지.
    try:
        _validate_pricing(
            db,
            price_unit=getattr(c, "price_unit", "session") or "session",
            rate_p=c.rate_p, per_min_p=getattr(c, "per_min_p", None), per_hour_p=getattr(c, "per_hour_p", None),
            duration_min=c.duration_min,
        )
    except ValueError:
        db.rollback()
        raise
    db.commit()
    db.refresh(c)
    return c


def update_self(db: Session, consultant: Consultant, **fields: Any) -> Consultant:
    """상담사 본인 프로필 셀프 수정 — _SELF_UPDATABLE 만 반영. 요금 하한 검증(커밋 전).

    self_managed=False(관리자 잠금)면 거부. status 는 active/coming_soon 만(hidden 은 관리자 전용).
    """
    if not bool(getattr(consultant, "self_managed", True)):
        raise PermissionError("관리자가 설정을 잠갔어요. 변경이 필요하면 문의해 주세요.")
    clean = {k: v for k, v in fields.items() if k in _SELF_UPDATABLE}
    if "price_unit" in clean and clean["price_unit"] not in PRICE_UNITS:
        raise ValueError("요금 단위는 세션당·분당·시간당 중 하나여야 해요.")
    if "status" in clean and clean["status"] not in ("active", "coming_soon"):
        raise ValueError("상태는 영업/입점예정 중 선택할 수 있어요.")
    # 요금 정합성(단위-요금 일치·0P/하한 방지)은 update_consultant 의 _validate_pricing 이 최종 상태로 검증.
    return update_consultant(db, consultant.id, **clean)


def delete_consultant(db: Session, consultant_id: int) -> None:
    c = db.get(Consultant, consultant_id)
    if c is None:
        raise LookupError("상담사를 찾을 수 없어요.")
    db.delete(c)
    db.commit()


def set_availability(db: Session, consultant: Consultant, online: bool) -> Consultant:
    """상담사 본인 영업 on/off — presence 를 online/offline 로. 단, 상담 중(busy)이면 세션이 우선(유지).

    요건: 상담사가 상담 화면에서 직접 접속상태를 켜고 끌 수 있다. 사용자 리스트의 상태 배지에 반영됨.
    """
    if consultant.presence != "busy":
        consultant.presence = "online" if online else "offline"
    consultant.last_seen_at = datetime.utcnow()
    db.commit()
    db.refresh(consultant)
    return consultant


def create_consultant_from_user(db: Session, user_id: int, specialty: str = "saju") -> Consultant:
    """회원관리에서 상담사 지정 — 해당 회원(이메일)으로 입점업체 생성/연결 + 분야(사주/타로/둘다) 지정.

    이미 상담사면 user_id 연결 보정 + 분야 갱신(재지정으로 분야 변경 가능). 신규면 업체명 기본=닉네임.
    """
    if specialty not in SPECIALTIES:
        raise ValueError("분야는 saju | tarot | both 중 하나여야 해요.")
    u = db.get(User, user_id)
    if u is None:
        raise LookupError("회원을 찾을 수 없어요.")
    email = _norm_email(u.email)
    existing = db.execute(
        select(Consultant).where(Consultant.login_email == email)
    ).scalars().first()
    if existing is not None:
        changed = False
        if existing.user_id != u.id:
            existing.user_id = u.id
            changed = True
        if existing.specialty != specialty:
            existing.specialty = specialty  # 재지정으로 분야 변경
            changed = True
        if changed:
            db.commit()
            db.refresh(existing)
        return existing
    return create_consultant(
        db, login_email=u.email, business_name=(u.nickname or email.split("@")[0]),
        specialty=specialty,
    )


def link_user(db: Session, user: User) -> Optional[Consultant]:
    """가입/로그인 시 — 이메일이 일치하는 미연결 입점업체가 있으면 user_id 연결(권한 부여).

    Phase 2 인증 흐름에서 호출. 이미 연결돼 있으면 그대로 반환.
    """
    if user is None or not user.email:
        return None
    c = db.execute(
        select(Consultant).where(Consultant.login_email == _norm_email(user.email))
    ).scalars().first()
    if c is None:
        return None
    if c.user_id != user.id:
        c.user_id = user.id
        db.commit()
        db.refresh(c)
    return c


# ───────────────────────── 간판 이미지 ─────────────────────────

def save_signboard(consultant_id: int, filename: str, content: bytes) -> str:
    """간판 이미지 저장 → 서빙 URL(/api/consultation/signboards/{name}) 반환.

    확장자 화이트리스트 + uuid 파일명(원본명 노출·충돌 방지). 반환 URL 을 consultants.signboard_image_url 에 저장.
    """
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in _ALLOWED_IMG_EXT:
        raise ValueError("이미지 파일(png/jpg/webp/gif/svg)만 등록할 수 있어요.")
    if not content:
        raise ValueError("빈 파일이에요.")
    if len(content) > 8 * 1024 * 1024:
        raise ValueError("이미지는 8MB 이하만 등록할 수 있어요.")
    os.makedirs(MEDIA_DIR, exist_ok=True)
    name = f"c{int(consultant_id)}_{uuid.uuid4().hex}{ext}"
    with open(os.path.join(MEDIA_DIR, name), "wb") as f:
        f.write(content)
    return f"/api/consultation/signboards/{name}"


_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")


def signboard_path(name: str) -> Optional[str]:
    """서빙용 — 안전한 파일명일 때만 실제 경로 반환(경로순회 차단)."""
    if not name or not _SAFE_NAME.match(name) or "/" in name or "\\" in name:
        return None
    p = os.path.realpath(os.path.join(MEDIA_DIR, name))
    root = os.path.realpath(MEDIA_DIR)
    if (p == root or p.startswith(root + os.sep)) and os.path.isfile(p):
        return p
    return None


# ───────────────────────── 입점 신청(운영자 지시 2026-07-11) ─────────────────────────

# 신청 서류 저장 루트 — 파일명은 uuid(경로순회·덮어쓰기 방지), 관리자 전용 열람.
_PARTNER_DOCS_DIR = Path(__file__).resolve().parents[3] / "data" / "partner_docs"
_DOC_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
_DOC_MAX = 10 * 1024 * 1024   # 10MB/파일


class DocValidationError(ValueError):
    """서류 형식·크기 위반 — 중복신청(409)과 구분해 400으로 응답하기 위한 타입."""


def save_application_docs(app_id: int, files: list[tuple[str, str, bytes]]) -> list[dict[str, Any]]:
    """신청 서류 저장 — files=[(kind, 원본파일명, bytes)]. 확장자 화이트리스트·크기 검증.
    전 파일 선검증 후 일괄 기록 — 중간 검증 실패로 앞선 파일(통장사본 등 PII)이 고아로 남는 것 방지.
    반환 메타 [{id, kind, name, path, size}] — docs_json에 저장(경로는 상대, 열람은 관리자 API만)."""
    import uuid as _uuid

    checked: list[tuple[str, str, str, bytes]] = []   # (kind, name, ext, data)
    for kind, name, data in files:
        ext = Path(name or "").suffix.lower()
        if ext not in _DOC_EXTS:
            raise DocValidationError(f"허용되지 않는 파일 형식이에요({ext or '확장자 없음'}) — 이미지(jpg/png/webp) 또는 PDF만 첨부할 수 있어요.")
        if len(data) > _DOC_MAX:
            raise DocValidationError("파일이 너무 커요 — 파일당 10MB 이하로 첨부해 주세요.")
        if len(data) == 0:
            continue
        checked.append((kind, name, ext, data))

    out: list[dict[str, Any]] = []
    base = _PARTNER_DOCS_DIR / str(app_id)
    base.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    try:
        for kind, name, ext, data in checked:
            fid = _uuid.uuid4().hex
            p = base / f"{fid}{ext}"
            p.write_bytes(data)
            written.append(p)
            out.append({"id": fid, "kind": kind, "name": (name or "문서")[:120],
                        "path": f"{app_id}/{fid}{ext}", "size": len(data)})
    except Exception:
        for p in written:                               # OS 오류 등 도중 실패 → 쓴 것 회수(PII 잔존 방지)
            p.unlink(missing_ok=True)
        try:
            base.rmdir()
        except OSError:
            pass
        raise
    return out


def application_doc_path(a: "ConsultantApplication", doc_id: str) -> tuple[Path, str]:
    """관리자 열람용 — docs_json에서 doc_id 검증 후 실제 경로 반환(임의 경로 접근 차단)."""
    docs = json.loads(a.docs_json or "[]")
    d = next((x for x in docs if x.get("id") == doc_id), None)
    if not d:
        raise LookupError("서류를 찾을 수 없어요.")
    p = (_PARTNER_DOCS_DIR / d["path"]).resolve()
    if not str(p).startswith(str(_PARTNER_DOCS_DIR.resolve())) or not p.exists():
        raise LookupError("서류 파일이 없어요.")
    return p, d.get("name") or p.name


# ── 입점 문의(신청 전 게이트, 운영자 확정 2026-07-12) ────────────────────────
# 프로세스: 푸터 '입점 문의' → 회원 메일 ID로 접수 → 관리자 [신청 허용] → 신청서 작성 가능.

def create_inquiry(db: Session, user: "User", note: Optional[str] = None) -> "PartnerInquiry":
    """입점 문의 접수 — 메일 ID 기준. pending/allowed 중복·기입점 계정은 차단."""
    from backend.app.repositories.consultation_models import ConsultantApplication, PartnerInquiry

    email = _norm_email(user.email)
    if db.execute(select(Consultant).where(Consultant.login_email == email)).scalars().first():
        raise ValueError("이미 입점된 계정이에요. 상담사 콘솔을 이용해 주세요.")
    if db.execute(select(ConsultantApplication).where(
            ConsultantApplication.email == email, ConsultantApplication.status == "pending")).scalars().first():
        raise ValueError("이미 심사 대기 중인 신청서가 있어요. 승인 결과를 기다려 주세요.")
    cur = db.execute(select(PartnerInquiry).where(
        PartnerInquiry.email == email, PartnerInquiry.status.in_(("pending", "allowed"))
    )).scalars().first()
    if cur is not None:
        if cur.status == "allowed":
            raise ValueError("이미 신청이 허용된 계정이에요. 바로 입점 신청서를 작성해 주세요.")
        raise ValueError("이미 접수된 문의가 있어요. 관리자 확인을 기다려 주세요.")
    q = PartnerInquiry(user_id=user.id, email=email, note=(note or "").strip()[:2000] or None)
    db.add(q)
    try:
        db.commit()
    except IntegrityError:
        # 동시 요청이 check-then-insert 를 뚫은 경우 — PG 부분 유니크 인덱스(email, pending)가 잡음
        db.rollback()
        raise ValueError("이미 접수된 문의가 있어요. 관리자 확인을 기다려 주세요.")
    db.refresh(q)
    return q


def my_inquiry(db: Session, user: "User") -> Optional["PartnerInquiry"]:
    """내 최신 문의 — 기각 이력보다 진행 중(pending/allowed)을 우선 반환."""
    from backend.app.repositories.consultation_models import PartnerInquiry
    email = _norm_email(user.email)
    rows = db.execute(
        select(PartnerInquiry).where(PartnerInquiry.email == email).order_by(PartnerInquiry.id.desc())
    ).scalars().all()
    for r in rows:
        if r.status in ("pending", "allowed"):
            return r
    return rows[0] if rows else None


def can_apply(db: Session, user: "User") -> bool:
    """신청서 작성 자격 — 관리자가 문의를 허용했거나, 과거 신청 이력(재신청)이 있으면 True."""
    from backend.app.repositories.consultation_models import ConsultantApplication, PartnerInquiry
    email = _norm_email(user.email)
    if db.execute(select(PartnerInquiry).where(
            PartnerInquiry.email == email, PartnerInquiry.status == "allowed")).scalars().first():
        return True
    return db.execute(select(ConsultantApplication).where(
        ConsultantApplication.email == email)).scalars().first() is not None


def inquiry_dict(q: "PartnerInquiry") -> dict[str, Any]:
    return {
        "id": q.id, "email": q.email, "note": q.note, "status": q.status,
        "decide_note": q.decide_note,
        "decided_at": q.decided_at.isoformat() if q.decided_at else None,
        "created_at": q.created_at.isoformat() if q.created_at else None,
    }


def list_inquiries(db: Session, status: Optional[str] = None) -> list[dict[str, Any]]:
    from backend.app.repositories.consultation_models import PartnerInquiry
    stmt = select(PartnerInquiry).order_by(PartnerInquiry.id.desc())
    if status:
        stmt = stmt.where(PartnerInquiry.status == status)
    return [inquiry_dict(q) for q in db.execute(stmt).scalars().all()]


def allow_inquiry(db: Session, inquiry_id: int) -> dict[str, Any]:
    """[신청 허용] — 사용자에게 신청서 작성 자격 부여 + 웹푸시 안내."""
    from backend.app.repositories.consultation_models import PartnerInquiry
    q = db.get(PartnerInquiry, inquiry_id)
    if q is None:
        raise LookupError("문의를 찾을 수 없어요.")
    if q.status != "pending":
        raise ValueError("이미 처리된 문의예요.")
    q.status = "allowed"
    q.decided_at = datetime.utcnow()
    db.commit()
    if q.user_id:
        try:
            from backend.app.services import push_service
            push_service.send_to_user(
                db, q.user_id, "🤝 입점 신청을 진행해 주세요",
                "관리자 확인이 완료됐어요. 입점 신청서(서류 첨부·약관 동의)를 작성하시면 심사가 시작됩니다.",
                url="/partner-apply",
            )
        except Exception:  # noqa: BLE001
            pass
    return inquiry_dict(q)


def dismiss_inquiry(db: Session, inquiry_id: int, reason: str = "") -> dict[str, Any]:
    from backend.app.repositories.consultation_models import PartnerInquiry
    q = db.get(PartnerInquiry, inquiry_id)
    if q is None:
        raise LookupError("문의를 찾을 수 없어요.")
    if q.status != "pending":
        raise ValueError("이미 처리된 문의예요.")
    q.status = "dismissed"
    q.decide_note = (reason or "").strip()[:300] or None
    q.decided_at = datetime.utcnow()
    db.commit()
    if q.user_id:
        try:
            from backend.app.services import push_service
            push_service.send_to_user(
                db, q.user_id, "입점 문의 안내",
                "아쉽지만 이번에는 입점 진행이 어려워요." + (f" 사유: {q.decide_note}" if q.decide_note else ""),
                url="/partner-apply",
            )
        except Exception:  # noqa: BLE001
            pass
    return inquiry_dict(q)


def create_application(
    db: Session, user: "User", *, specialty: str, business_name: str,
    contact: Optional[str] = None, intro: Optional[str] = None, ip: Optional[str] = None,
    docs: Optional[list[tuple[str, str, bytes]]] = None,
) -> "ConsultantApplication":
    """입점 신청 — 클릭랩 동의 증빙(서버 약관 전문 스냅샷·버전·해시·시각·IP)을 함께 기록.

    중복 방지: 심사 대기 신청이 있거나 이미 입점(consultants에 이메일 존재)이면 ValueError."""
    from backend.app.repositories.consultation_models import ConsultantApplication
    from backend.app.services import partner_terms

    email = _norm_email(user.email)
    if specialty not in ("saju", "tarot", "both"):
        raise ValueError("분야는 사주/타로/둘다 중에서 선택해 주세요.")
    if not (business_name or "").strip():
        raise ValueError("상담소(업체) 이름을 입력해 주세요.")
    dup = db.execute(
        select(ConsultantApplication).where(
            ConsultantApplication.email == email, ConsultantApplication.status == "pending"
        )
    ).scalars().first()
    if dup:
        raise ValueError("이미 심사 대기 중인 신청이 있어요. 승인 결과를 기다려 주세요.")
    exists = db.execute(select(Consultant).where(Consultant.login_email == email)).scalars().first()
    if exists:
        raise ValueError("이미 입점된 계정이에요. 상담사 콘솔을 이용해 주세요.")

    app = ConsultantApplication(
        user_id=user.id, email=email, specialty=specialty,
        business_name=business_name.strip()[:120],
        contact=(contact or "").strip()[:64] or None,
        intro=(intro or "").strip()[:2000] or None,
        terms_version=partner_terms.TERMS_VERSION,
        terms_sha256=partner_terms.terms_sha256(),
        terms_text=partner_terms.PARTNER_TERMS,
        agreed_ip=(ip or "")[:64] or None,
    )
    db.add(app)
    db.flush()                                   # id 확보 → 서류 저장 경로에 사용
    saved: list[dict[str, Any]] = []
    if docs:
        saved = save_application_docs(app.id, docs)
        app.docs_json = json.dumps(saved, ensure_ascii=False)
    try:
        db.commit()
    except Exception:                            # 커밋 실패 → 방금 쓴 서류 회수(DB 기록 없는 PII 잔존 방지)
        for d in saved:
            (_PARTNER_DOCS_DIR / d["path"]).unlink(missing_ok=True)
        try:
            (_PARTNER_DOCS_DIR / str(app.id)).rmdir()
        except OSError:
            pass
        raise
    db.refresh(app)
    return app


def application_dict(a: "ConsultantApplication") -> dict[str, Any]:
    return {
        "id": a.id, "email": a.email, "specialty": a.specialty,
        "business_name": a.business_name, "contact": a.contact, "intro": a.intro,
        "terms_version": a.terms_version, "agreed_at": a.agreed_at.isoformat() if a.agreed_at else None,
        "status": a.status, "reviewed_at": a.reviewed_at.isoformat() if a.reviewed_at else None,
        "reject_reason": a.reject_reason, "consultant_id": a.consultant_id,
        "docs": [{k: v for k, v in d.items() if k != "path"}   # 경로는 비노출 — 열람은 관리자 API 경유
                 for d in json.loads(a.docs_json or "[]")],
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def my_application(db: Session, user: "User") -> Optional[dict[str, Any]]:
    from backend.app.repositories.consultation_models import ConsultantApplication
    a = db.execute(
        select(ConsultantApplication)
        .where(ConsultantApplication.email == _norm_email(user.email))
        .order_by(ConsultantApplication.created_at.desc())
    ).scalars().first()
    return application_dict(a) if a else None


def list_applications(db: Session, status: Optional[str] = None) -> list[dict[str, Any]]:
    from backend.app.repositories.consultation_models import ConsultantApplication
    stmt = select(ConsultantApplication).order_by(ConsultantApplication.created_at.desc())
    if status in ("pending", "approved", "rejected"):
        stmt = stmt.where(ConsultantApplication.status == status)
    return [application_dict(a) for a in db.execute(stmt).scalars().all()]


def approve_application(db: Session, app_id: int) -> dict[str, Any]:
    """승인 — consultants 행 생성(login_email 매핑 → 기존 자동 연결로 권한 부여) + 신청서 상태 갱신."""
    from backend.app.repositories.consultation_models import ConsultantApplication
    a = db.get(ConsultantApplication, app_id)
    if a is None:
        raise LookupError("신청서를 찾을 수 없어요.")
    if a.status != "pending":
        raise ValueError("이미 처리된 신청이에요.")
    c = create_consultant(
        db, login_email=a.email, business_name=a.business_name,
        specialty=a.specialty, intro=a.intro,
    )
    a.status = "approved"
    a.reviewed_at = datetime.utcnow()
    a.consultant_id = c.id
    db.commit()
    # 승인 알림(웹푸시 — 실패 무시)
    if c.user_id:
        try:
            from backend.app.services import push_service
            push_service.send_to_user(
                db, c.user_id, "🎉 입점 승인 완료!",
                "상담사 입점이 승인됐어요. 콘솔에서 간판·요금·예약시간을 설정하고 영업을 시작해 보세요.",
                url="/consultation/console",
            )
        except Exception:  # noqa: BLE001
            pass
    return application_dict(a)


def reject_application(db: Session, app_id: int, reason: str = "") -> dict[str, Any]:
    from backend.app.repositories.consultation_models import ConsultantApplication
    a = db.get(ConsultantApplication, app_id)
    if a is None:
        raise LookupError("신청서를 찾을 수 없어요.")
    if a.status != "pending":
        raise ValueError("이미 처리된 신청이에요.")
    a.status = "rejected"
    a.reviewed_at = datetime.utcnow()
    a.reject_reason = (reason or "").strip()[:300] or None
    db.commit()
    if a.user_id:
        try:
            from backend.app.services import push_service
            push_service.send_to_user(
                db, a.user_id, "입점 신청 결과 안내",
                "아쉽지만 이번 입점 신청은 승인되지 않았어요." + (f" 사유: {a.reject_reason}" if a.reject_reason else ""),
                url="/partner-apply",
            )
        except Exception:  # noqa: BLE001
            pass
    return application_dict(a)
