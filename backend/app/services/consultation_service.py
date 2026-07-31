"""1:1 인적 상담 서비스 — 입점업체(상담사) CRUD·간판 업로드·정산 산출·실적 집계.

관리자 등록/조회, 사용자용 공개 리스트, 상담사별 개별 단가/시간/수수료의 전역 폴백,
정산(수수료·세금) 계산을 담당한다. 실시간 세션/과금(WS)은 Phase 2~3(consultation WS 모듈).
설계: [[consultation-1on1-plan]].
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.repositories.auth_models import User
from backend.app.repositories.consultation_models import (
    Consultant,
    ConsultationSession,
    ConsultationSettlement,
)
from backend.app.services import settings_service

SPECIALTIES = ("saju", "tarot", "both")

# 간판 이미지 저장 경로(웹 서빙은 /api/consultation/signboards/{name} 엔드포인트) — 저장소 루트/data/media/consultants
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MEDIA_DIR = os.path.join(_ROOT, "data", "media", "consultants")
_ALLOWED_IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}


# ───────────────────────── 단가/정산 산출 ─────────────────────────

def effective(db: Session, c: Consultant) -> tuple[int, int, int]:
    """상담사 개별 설정 우선, NULL 이면 전역 기본값으로 (단가P, 시간분, 수수료%) 반환."""
    price = c.rate_p if c.rate_p is not None else settings_service.get_int(db, "consultation_default_price_p", 50000)
    dur = c.duration_min if c.duration_min is not None else settings_service.get_int(db, "consultation_default_duration_min", 30)
    comm = c.commission_pct if c.commission_pct is not None else settings_service.get_int(db, "consultation_commission_pct", 20)
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
        "price_p": price,
        "duration_min": dur,
        "presence": c.presence,  # offline | online | busy
        "session_count": eng.get("session_count", 0),   # 누적 상담건수(완료)
        "rating_avg": eng.get("rating_avg"),            # 평균 만족도(1~5, 없으면 null)
        "rating_count": eng.get("rating_count", 0),     # 평점 참여 수
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
        # 원본(개별 설정, NULL=전역)
        "rate_p": c.rate_p,
        "duration_min_raw": c.duration_min,
        "commission_pct_raw": c.commission_pct,
        # 유효값(폴백 반영)
        "eff_price_p": price,
        "eff_duration_min": dur,
        "eff_commission_pct": comm,
        "is_active": c.is_active,
        "presence": c.presence,
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
    """사용자 화면 리스트 — 활성 상담사만. specialty 필터(해당 분야 또는 'both'). 간판 만족도 포함."""
    stmt = select(Consultant).where(Consultant.is_active.is_(True))
    if specialty in ("saju", "tarot"):
        stmt = stmt.where(Consultant.specialty.in_([specialty, "both"]))
    stmt = stmt.order_by(Consultant.sort_order.asc(), Consultant.id.asc())
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
    limit: int = 300,
) -> list[dict[str, Any]]:
    """정산 명세 목록(상담사명 조인). 상담사·상태 필터."""
    stmt = (
        select(ConsultationSettlement, Consultant.business_name)
        .join(Consultant, ConsultationSettlement.consultant_id == Consultant.id)
    )
    if consultant_id is not None:
        stmt = stmt.where(ConsultationSettlement.consultant_id == consultant_id)
    if status in ("pending", "settled"):
        stmt = stmt.where(ConsultationSettlement.status == status)
    stmt = stmt.order_by(ConsultationSettlement.created_at.desc()).limit(limit)
    return [settlement_dict(stl, name) for stl, name in db.execute(stmt).all()]


def settlement_totals(db: Session) -> dict[str, int]:
    """전체 정산 합계 — 매출·정산대기 실지급·정산완료 실지급(원)."""
    rev = db.execute(select(func.coalesce(func.sum(ConsultationSettlement.revenue_p), 0))).scalar() or 0
    pending = db.execute(
        select(func.coalesce(func.sum(ConsultationSettlement.payout_p), 0)).where(
            ConsultationSettlement.status == "pending"
        )
    ).scalar() or 0
    settled = db.execute(
        select(func.coalesce(func.sum(ConsultationSettlement.payout_p), 0)).where(
            ConsultationSettlement.status == "settled"
        )
    ).scalar() or 0
    return {"revenue_p": int(rev), "payout_pending_p": int(pending), "payout_settled_p": int(settled)}


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
) -> Consultant:
    email = _norm_email(login_email)
    if not email or "@" not in email:
        raise ValueError("올바른 입점 ID(이메일)를 입력해 주세요.")
    if not (business_name or "").strip():
        raise ValueError("업체명을 입력해 주세요.")
    if specialty not in SPECIALTIES:
        raise ValueError("분야는 saju | tarot | both 중 하나여야 해요.")
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
        rate_p=rate_p,
        duration_min=duration_min,
        commission_pct=commission_pct,
        is_active=is_active,
        sort_order=sort_order,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


_UPDATABLE = {
    "business_name", "specialty", "intro", "rate_p", "duration_min",
    "commission_pct", "is_active", "sort_order", "signboard_image_url",
}


def update_consultant(db: Session, consultant_id: int, **fields: Any) -> Consultant:
    c = db.get(Consultant, consultant_id)
    if c is None:
        raise LookupError("상담사를 찾을 수 없어요.")
    if "specialty" in fields and fields["specialty"] not in SPECIALTIES:
        raise ValueError("분야는 saju | tarot | both 중 하나여야 해요.")
    if "business_name" in fields and not (fields["business_name"] or "").strip():
        raise ValueError("업체명을 비울 수 없어요.")
    for k, v in fields.items():
        if k in _UPDATABLE:
            setattr(c, k, v)
    db.commit()
    db.refresh(c)
    return c


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
