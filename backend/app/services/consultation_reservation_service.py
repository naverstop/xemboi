"""A-2 상담 예약제 — 슬롯 등록(상담사)·예약(선결제 홀드)·전환(세션 자동 생성)·취소/노쇼 환불.

정책(관리자 설정):
  · consultation_reserve_full_refund_hours(기본 24): 시작 N시간 전 사용자 취소 = 100% 환불
  · consultation_reserve_late_refund_pct(기본 50):  N시간 이내 사용자 취소 = M% 환불
  · consultation_reserve_grace_min(기본 10):        전환 후 상담사 미수락 유예 — 초과 시 노쇼·전액 환불
상담사 측 취소(슬롯 삭제 포함)는 항상 100% 환불. 모든 시각은 UTC(naive) — 기존 세션 서비스와 동일.
알림(웹푸시·콘솔 WS)은 API 계층/드라이버가 담당, 본 서비스는 DB 상태 전이만.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.repositories.auth_models import User
from backend.app.repositories.consultation_models import (
    Consultant,
    ConsultationSession,
    ConsultationSlot,
)
from backend.app.services import auth_service, consultation_service as csvc, settings_service


def _now() -> datetime:
    return datetime.utcnow()


def to_utc_naive(dt: datetime) -> datetime:
    """tz-aware 입력(ISO Z 등)을 UTC naive 로 정규화 — DB 저장 규약(기존 서비스와 동일)."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def slot_dict(db: Session, s: ConsultationSlot, *, include_user: bool = False) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": s.id,
        "consultant_id": s.consultant_id,
        "start_at": s.start_at.isoformat() + "Z",  # UTC 명시 — 프론트 로컬 표기 변환용
        "duration_min": s.duration_min,
        "status": s.status,
        "price_p": s.price_p,
        "charged_p": s.charged_p,
        "refund_p": s.refund_p,
        "session_id": s.session_id,
    }
    if include_user:
        d["user_id"] = s.user_id
        d["booked_at"] = s.booked_at.isoformat() + "Z" if s.booked_at else None
    return d


def reserve_policy(db: Session) -> dict[str, int]:
    return {
        "full_refund_hours": settings_service.get_int(db, "consultation_reserve_full_refund_hours", 24),
        "late_refund_pct": settings_service.get_int(db, "consultation_reserve_late_refund_pct", 50),
        "grace_min": settings_service.get_int(db, "consultation_reserve_grace_min", 10),
    }


# ───────────────────────── 상담사: 슬롯 관리 ─────────────────────────

def add_slot(db: Session, consultant: Consultant, start_at: datetime) -> ConsultationSlot:
    start_at = to_utc_naive(start_at)
    if start_at <= _now():
        raise ValueError("지난 시각에는 예약 시간을 열 수 없어요.")
    # 영업시간(요일별)이 설정돼 있으면 그 범위 안에서만 예약 슬롯 개설 허용(P5: 예약범위 제한).
    if not csvc.within_business_hours(consultant, start_at):
        raise ValueError("영업시간 외에는 예약 시간을 열 수 없어요. '간판·요금·설정'의 영업시간을 확인해 주세요.")
    _p, dur, _c = csvc.effective(db, consultant)
    # 동일 상담사의 겹치는(블록 시간 기준) open/booked 슬롯 방지
    span = timedelta(minutes=dur)
    near = db.execute(
        select(ConsultationSlot).where(
            ConsultationSlot.consultant_id == consultant.id,
            ConsultationSlot.status.in_(["open", "booked"]),
            ConsultationSlot.start_at > start_at - span,
            ConsultationSlot.start_at < start_at + span,
        )
    ).scalars().first()
    if near is not None:
        raise ValueError("겹치는 예약 시간이 이미 있어요.")
    s = ConsultationSlot(
        id=uuid.uuid4().hex,
        consultant_id=consultant.id,
        start_at=start_at,
        duration_min=dur,
        status="open",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def list_consultant_slots(db: Session, consultant: Consultant, *, days_back: int = 2) -> list[ConsultationSlot]:
    since = _now() - timedelta(days=days_back)
    return list(
        db.execute(
            select(ConsultationSlot)
            .where(
                ConsultationSlot.consultant_id == consultant.id,
                ConsultationSlot.start_at >= since,
            )
            .order_by(ConsultationSlot.start_at.asc())
        ).scalars().all()
    )


def remove_slot(db: Session, consultant: Consultant, slot_id: str) -> tuple[ConsultationSlot, int]:
    """open=삭제(cancelled), booked=상담사 취소(100% 환불). 반환: (슬롯, 환불액)."""
    # 행잠금 — 상담사 슬롯삭제(remove_slot)와 사용자 예약취소(cancel_by_user)가 같은 슬롯에 동시 진입해
    #   각각 환불하던 이중환불을 직렬화로 차단(cancel_by_user 는 이미 with_for_update).
    s = db.get(ConsultationSlot, slot_id, with_for_update=True)
    if s is None or s.consultant_id != consultant.id:
        raise LookupError("예약 시간을 찾을 수 없어요.")
    db.refresh(s)  # 락 후 최신값(preload stale 방지 — 이중환불 차단)
    if s.status not in ("open", "booked"):
        raise ValueError("이미 진행되었거나 취소된 예약 시간이에요.")
    refund = 0
    if s.status == "booked" and s.charged_p and not s.refunded:
        refund = s.charged_p
        auth_service.adjust_credit(db, s.user_id, refund, reason="consultation_reserve_refund", ref_id=s.id)
        s.refunded = True
        s.refund_p = refund
    s.status = "cancelled"
    db.commit()
    db.refresh(s)
    return s, refund


# ───────────────────────── 사용자: 예약/취소 ─────────────────────────

def list_open_slots(db: Session, consultant_id: int, *, days: int = 14) -> list[ConsultationSlot]:
    until = _now() + timedelta(days=days)
    return list(
        db.execute(
            select(ConsultationSlot)
            .where(
                ConsultationSlot.consultant_id == consultant_id,
                ConsultationSlot.status == "open",
                ConsultationSlot.start_at > _now(),
                ConsultationSlot.start_at <= until,
            )
            .order_by(ConsultationSlot.start_at.asc())
        ).scalars().all()
    )


def reserve(db: Session, user: User, slot_id: str, *, consent: bool = False) -> ConsultationSlot:
    """예약 확정 — 슬롯 행잠금 → 선결제(즉시 차감=홀드) → booked."""
    # 개인정보 처리(대화 저장·7일 후 파기) + 선결제·취소정책 동의는 입장 전 필수 — 서버 강제.
    if not consent:
        raise ValueError("대화 저장·7일 후 파기 및 선결제·취소 정책에 동의해야 예약할 수 있어요.")
    s = db.execute(
        select(ConsultationSlot).where(ConsultationSlot.id == slot_id).with_for_update()
    ).scalars().first()
    if s is None:
        raise LookupError("예약 시간을 찾을 수 없어요.")
    if s.status != "open" or s.start_at <= _now():
        raise ValueError("이미 마감된 예약 시간이에요.")
    c = db.get(Consultant, s.consultant_id)
    if c is None or not c.is_active or getattr(c, "status", "active") != "active":
        raise ValueError("지금은 예약을 받을 수 없는 상담사예요.")
    # 내 활성 예약(미전환) 중복 제한 — 같은 상담사 시간대 혼선 방지, 최대 3건
    mine = db.execute(
        select(ConsultationSlot).where(
            ConsultationSlot.user_id == user.id,
            ConsultationSlot.status == "booked",
        )
    ).scalars().all()
    if len(mine) >= 3:
        raise ValueError("예약은 동시에 3건까지만 잡을 수 있어요.")
    price, _dur, comm = csvc.effective(db, c)
    bal = auth_service.get_balance(db, user.id)
    if bal < price:
        raise ValueError(f"포인트가 부족해요. (필요 {price:,}P · 보유 {bal:,}P)")
    # 선결제(홀드) — 취소/노쇼 정책에 따라 환불
    auth_service.adjust_credit(db, user.id, -price, reason="consultation_reserve", ref_id=s.id)
    s.user_id = user.id
    s.status = "booked"
    s.booked_at = _now()
    s.consent_at = _now() if consent else None
    s.price_p = price
    s.commission_pct = comm
    s.charged_p = price
    db.commit()
    db.refresh(s)
    return s


def my_reservations(db: Session, user: User) -> list[ConsultationSlot]:
    since = _now() - timedelta(days=1)
    return list(
        db.execute(
            select(ConsultationSlot)
            .where(
                ConsultationSlot.user_id == user.id,
                ConsultationSlot.status.in_(["booked", "converted"]),
                ConsultationSlot.start_at >= since,
            )
            .order_by(ConsultationSlot.start_at.asc())
        ).scalars().all()
    )


def cancel_by_user(db: Session, user: User, slot_id: str) -> tuple[ConsultationSlot, int]:
    """사용자 취소 — 시작 N시간 전 100%, 이내 M% 환불(관리자 설정). 반환: (슬롯, 환불액)."""
    s = db.execute(
        select(ConsultationSlot).where(ConsultationSlot.id == slot_id).with_for_update()
    ).scalars().first()
    if s is None or s.user_id != user.id:
        raise LookupError("내 예약을 찾을 수 없어요.")
    if s.status != "booked":
        raise ValueError("이미 시작되었거나 취소된 예약이에요.")
    pol = reserve_policy(db)
    hours_left = (s.start_at - _now()).total_seconds() / 3600.0
    ratio = 1.0 if hours_left >= pol["full_refund_hours"] else max(0, min(100, pol["late_refund_pct"])) / 100.0
    refund = int(round((s.charged_p or 0) * ratio))
    if refund > 0 and not s.refunded:
        auth_service.adjust_credit(db, user.id, refund, reason="consultation_reserve_refund", ref_id=s.id)
    s.refunded = True
    s.refund_p = refund
    s.status = "cancelled"
    db.commit()
    db.refresh(s)
    return s, refund


# ───────────────────────── 드라이버: 알림/전환/노쇼 ─────────────────────────

def due_reminders(db: Session, *, lead_min: int = 10) -> list[ConsultationSlot]:
    """시작 lead_min 전 리마인더 대상 — 호출 시 reminder_sent 마킹까지 수행."""
    now = _now()
    rows = list(
        db.execute(
            select(ConsultationSlot).where(
                ConsultationSlot.status == "booked",
                ConsultationSlot.reminder_sent.is_(False),
                ConsultationSlot.start_at <= now + timedelta(minutes=lead_min),
                ConsultationSlot.start_at > now,
            )
        ).scalars().all()
    )
    for s in rows:
        s.reminder_sent = True
    if rows:
        db.commit()
    return rows


def convert_due(db: Session) -> list[tuple[ConsultationSlot, ConsultationSession]]:
    """시작 시각 도래한 booked 슬롯 → 상담 세션(requested, 선결제 완료) 자동 생성."""
    now = _now()
    rows = list(
        db.execute(
            select(ConsultationSlot)
            .where(ConsultationSlot.status == "booked", ConsultationSlot.start_at <= now)
            .with_for_update(skip_locked=True)
        ).scalars().all()
    )
    out: list[tuple[ConsultationSlot, ConsultationSession]] = []
    for s in rows:
        c = db.get(Consultant, s.consultant_id)
        sess_row = ConsultationSession(
            id=uuid.uuid4().hex,
            user_id=s.user_id,
            consultant_id=s.consultant_id,
            specialty=c.specialty if c else "saju",
            status="requested",
            price_p=s.price_p,
            duration_min=s.duration_min,
            commission_pct=s.commission_pct,
            credits_charged=s.charged_p,  # 예약 선결제 — 수락 시 재차감 금지(세션 서비스가 인지)
            reservation_id=s.id,
            consent_at=s.consent_at,
            requested_at=now,
        )
        db.add(sess_row)
        s.status = "converted"
        s.session_id = sess_row.id
        out.append((s, sess_row))
    if out:
        db.commit()
        for _s, sess_row in out:
            db.refresh(sess_row)
    return out
