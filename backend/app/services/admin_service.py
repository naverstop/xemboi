"""관리자 콘솔 서비스: 회원 목록/검색, 크레딧 수동 조정, 배너 CRUD, 통계."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.repositories.auth_models import (
    Banner,
    Credit,
    CreditTransaction,
    Payment,
    User,
)
from backend.app.repositories.models import ChatMessage
from backend.app.services import auth_service


# -------- 회원 --------

def list_users(
    db: Session,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    base = select(User).order_by(User.id.desc())
    if q:
        like = f"%{q.lower()}%"
        base = base.where(
            (func.lower(User.email).like(like)) | (func.lower(User.nickname).like(like))
        )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(base.limit(limit).offset(offset)).scalars().all()

    # 결제/사용 집계 — 현재 페이지의 회원만 그룹 쿼리 1회씩(전 회원 N+1 방지).
    ids = [u.id for u in rows]
    paid_map: dict[int, int] = {}        # 누적 결제(원, status=approved)
    refunded_map: dict[int, int] = {}    # 누적 환불(원, status=refunded)
    usage_map: dict[int, int] = {}       # 사용 횟수(유료질문+미리보기 해제 차감 건수)
    granted_map: dict[int, int] = {}     # 기본제공 포인트(무료 지급 합: signup_bonus/admin_seed/admin_grant 등, purchase·refund 제외)
    spent_map: dict[int, int] = {}       # 사용 금액(질문+미리보기 해제 차감 포인트 합)
    if ids:
        for uid, amt in db.execute(
            select(Payment.user_id, func.coalesce(func.sum(Payment.amount), 0))
            .where(Payment.user_id.in_(ids), Payment.status == "approved")
            .group_by(Payment.user_id)
        ).all():
            paid_map[int(uid)] = int(amt)
        # 환불 누계 = 실제 환불액(부분환불 반영) — raw_payload.refund.refunded_krw, 없으면 amount(레거시).
        for uid, amt, payload in db.execute(
            select(Payment.user_id, Payment.amount, Payment.raw_payload)
            .where(Payment.user_id.in_(ids), Payment.status == "refunded")
        ).all():
            rk = (payload.get("refund") or {}).get("refunded_krw") if isinstance(payload, dict) else None
            refunded_map[int(uid)] = refunded_map.get(int(uid), 0) + int(rk if rk is not None else amt)
        for uid, cnt in db.execute(
            select(CreditTransaction.user_id, func.count(CreditTransaction.id))
            .where(
                CreditTransaction.user_id.in_(ids),
                CreditTransaction.reason.in_(("question", "preview_reveal")),
            )
            .group_by(CreditTransaction.user_id)
        ).all():
            usage_map[int(uid)] = int(cnt)
        for uid, amt in db.execute(
            select(CreditTransaction.user_id, func.coalesce(func.sum(CreditTransaction.delta), 0))
            .where(
                CreditTransaction.user_id.in_(ids),
                CreditTransaction.delta > 0,
                CreditTransaction.reason.notin_(("purchase", "refund")),
            )
            .group_by(CreditTransaction.user_id)
        ).all():
            granted_map[int(uid)] = int(amt)
        for uid, amt in db.execute(
            select(CreditTransaction.user_id, func.coalesce(func.sum(-CreditTransaction.delta), 0))
            .where(
                CreditTransaction.user_id.in_(ids),
                CreditTransaction.reason.in_(("question", "preview_reveal")),
            )
            .group_by(CreditTransaction.user_id)
        ).all():
            spent_map[int(uid)] = int(amt)

    out: list[dict[str, Any]] = []
    for u in rows:
        bal = auth_service.get_balance(db, u.id)
        out.append({
            "id": u.id,
            "email": u.email,
            "nickname": u.nickname,
            "role": u.role,
            "balance": bal,
            "paid_krw": paid_map.get(u.id, 0),         # 결제금액(승인된 결제 합, 원)
            "refunded_krw": refunded_map.get(u.id, 0),  # 환불금액(환불된 결제 합, 원)
            "granted_free": granted_map.get(u.id, 0),   # 기본제공 포인트(무료 지급 합)
            "spent": spent_map.get(u.id, 0),            # 사용 금액(차감 포인트 합)
            "usage_count": usage_map.get(u.id, 0),      # 유료 사용 횟수
            "free_used": u.free_used_count,             # 무료 사용 누적
            "is_premium": u.is_premium,
            "ads_hidden": u.ads_hidden,
            "must_change_password": u.must_change_password,
            "daily_free_used_at": u.daily_free_used_at.isoformat() if u.daily_free_used_at else None,
            "created_at": u.created_at.isoformat(),
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        })
    return out, int(total)


def list_user_payments(db: Session, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """회원의 결제 내역(최신순). 환불 가능 여부(refundable)는 status=approved 일 때만 True."""
    rows = db.execute(
        select(Payment)
        .where(Payment.user_id == user_id)
        .order_by(Payment.id.desc())
        .limit(limit)
    ).scalars().all()
    out: list[dict[str, Any]] = []
    for p in rows:
        refund_info = (p.raw_payload or {}).get("refund") if isinstance(p.raw_payload, dict) else None
        out.append({
            "id": p.id,
            "order_id": p.order_id,
            "amount": p.amount,
            "credit_granted": p.credit_granted,
            "status": p.status,
            "toss_payment_key": p.toss_payment_key,
            "refundable": p.status == "approved",
            "refunded_recovered": (refund_info or {}).get("recovered") if refund_info else None,
            "refunded_krw": (refund_info or {}).get("refunded_krw") if refund_info else None,
            "refund_partial": bool((refund_info or {}).get("partial")) if refund_info else False,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "approved_at": p.approved_at.isoformat() if p.approved_at else None,
        })
    return out


def list_transactions(db: Session, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    rows = db.execute(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user_id)
        .order_by(CreditTransaction.id.desc())
        .limit(limit)
    ).scalars().all()
    return [
        {
            "id": r.id,
            "delta": r.delta,
            "reason": r.reason,
            "ref_id": r.ref_id,
            "balance_after": r.balance_after,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


def credit_ledger_summary(db: Session, user_id: int) -> dict[str, Any]:
    """포인트 원장 정합성 요약 — 사용자가 '충전+적립−사용 = 현재 잔액'을 직접 대조(정합성 검증)할 수 있게.

    전체 거래를 집계(목록 limit 과 무관). consistent = (원장 합 == credits.balance).
    돈에 관한 화면이므로, 표시 잔액과 원장 합이 어긋나면 consistent=False 로 사용자에게 경고 노출.
    """
    rows = db.execute(
        select(CreditTransaction.reason, CreditTransaction.delta)
        .where(CreditTransaction.user_id == user_id)
    ).all()
    PURCHASE = {"purchase", "topup"}
    purchased = sum(d for r, d in rows if d > 0 and r in PURCHASE)          # 실제 결제 충전
    rewarded = sum(d for r, d in rows if d > 0 and r not in PURCHASE)       # 보너스·환불·리워드·지급
    used = -sum(d for r, d in rows if d < 0)                                # 사용(차감) 절대값
    computed = sum(d for _, d in rows)                                      # 원장 합
    bal = db.execute(select(Credit.balance).where(Credit.user_id == user_id)).scalar() or 0
    return {
        "purchased": int(purchased),
        "rewarded": int(rewarded),
        "used": int(used),
        "balance": int(bal),
        "computed_balance": int(computed),
        "consistent": int(bal) == int(computed),
        "count": len(rows),
    }


def grant_credit(db: Session, user_id: int, delta: int, reason: str = "admin_grant") -> int:
    """관리자가 임의로 크레딧 +/- 조정. 부족 시 ValueError."""
    user = auth_service.get_user_by_id(db, user_id)
    if user is None:
        raise LookupError(f"user {user_id} not found")
    new_balance = auth_service.adjust_credit(db, user_id, delta, reason=reason)
    db.commit()
    return new_balance


# -------- 배너 --------

VALID_SLOTS = {"top", "chat_top_1", "chat_top_2", "side_1", "side_2", "answer_bottom"}

# 채팅 상단 기본 배너(요건: "인생상담 친구" 신규 제작, 관리자 수정 가능)
DEFAULT_TOP_BANNER = {
    "slot": "top",
    "image_url": "/banners/life-consult.svg",
    "link_url": None,
    "title": "인생상담 친구",
    "weight": 10,
    "active": True,
}


def seed_default_banners(db: Session) -> None:
    """top 슬롯에 배너가 하나도 없으면 기본 '인생상담 친구' 배너를 1회 생성(멱등).

    관리자가 이후 수정/삭제 가능. 관리자가 top 배너를 1개라도 유지하면 재시드하지 않음.
    """
    existing = db.execute(
        select(func.count()).select_from(Banner).where(Banner.slot == "top")
    ).scalar_one()
    if existing and existing > 0:
        return
    db.add(Banner(**DEFAULT_TOP_BANNER))
    db.commit()


def list_banners(db: Session, slot: Optional[str] = None) -> list[dict[str, Any]]:
    stmt = select(Banner).order_by(Banner.slot.asc(), Banner.weight.desc(), Banner.id.desc())
    if slot:
        stmt = stmt.where(Banner.slot == slot)
    rows = db.execute(stmt).scalars().all()
    return [_banner_dict(b) for b in rows]


def create_banner(
    db: Session,
    *,
    slot: str,
    image_url: str,
    link_url: Optional[str] = None,
    title: Optional[str] = None,
    weight: int = 10,
    active: bool = True,
) -> dict[str, Any]:
    if slot not in VALID_SLOTS:
        raise ValueError(f"invalid slot: {slot}")
    b = Banner(
        slot=slot,
        image_url=image_url,
        link_url=link_url,
        title=title,
        weight=weight,
        active=active,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return _banner_dict(b)


def update_banner(db: Session, banner_id: int, **fields: Any) -> dict[str, Any]:
    b = db.get(Banner, banner_id)
    if b is None:
        raise LookupError(f"banner {banner_id} not found")
    if "slot" in fields and fields["slot"] not in VALID_SLOTS:
        raise ValueError(f"invalid slot: {fields['slot']}")
    for k, v in fields.items():
        if v is None:
            continue
        if hasattr(b, k):
            setattr(b, k, v)
    db.commit()
    db.refresh(b)
    return _banner_dict(b)


def delete_banner(db: Session, banner_id: int) -> None:
    b = db.get(Banner, banner_id)
    if b is None:
        raise LookupError(f"banner {banner_id} not found")
    db.delete(b)
    db.commit()


def _banner_dict(b: Banner) -> dict[str, Any]:
    return {
        "id": b.id,
        "slot": b.slot,
        "image_url": b.image_url,
        "link_url": b.link_url,
        "title": b.title,
        "weight": b.weight,
        "active": b.active,
        "created_at": b.created_at.isoformat(),
    }


# -------- 통계 --------

def get_stats(db: Session) -> dict[str, Any]:
    today = date.today()
    today_start = datetime.combine(today, datetime.min.time())
    yesterday_start = today_start - timedelta(days=1)

    total_users = db.execute(select(func.count(User.id))).scalar_one()
    today_signups = db.execute(
        select(func.count(User.id)).where(User.created_at >= today_start)
    ).scalar_one()
    yest_signups = db.execute(
        select(func.count(User.id))
        .where(User.created_at >= yesterday_start)
        .where(User.created_at < today_start)
    ).scalar_one()

    today_questions = db.execute(
        select(func.count(ChatMessage.id))
        .where(ChatMessage.role == "user")
        .where(ChatMessage.created_at >= today_start)
    ).scalar_one()

    total_revenue = db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "approved")
    ).scalar_one()

    # 기간별 매출(승인 결제 합) — 결제 시각은 승인시각 우선(없으면 생성시각). 오늘/이번주/이번달/올해.
    def _rev_since(start: "datetime") -> int:
        return int(db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .where(Payment.status == "approved")
            .where(func.coalesce(Payment.approved_at, Payment.created_at) >= start)
        ).scalar_one())

    week_start = today_start - timedelta(days=today.weekday())          # 이번 주 월요일 00:00
    month_start = datetime.combine(today.replace(day=1), datetime.min.time())
    year_start = datetime.combine(date(today.year, 1, 1), datetime.min.time())
    revenue_today = _rev_since(today_start)
    revenue_week = _rev_since(week_start)
    revenue_month = _rev_since(month_start)
    revenue_year = _rev_since(year_start)

    total_balance = db.execute(
        select(func.coalesce(func.sum(Credit.balance), 0))
    ).scalar_one()

    today_charged = db.execute(
        select(func.coalesce(func.sum(-CreditTransaction.delta), 0))
        .where(CreditTransaction.reason.in_(("question", "preview_reveal")))
        .where(CreditTransaction.created_at >= today_start)
    ).scalar_one()

    return {
        "total_users": int(total_users),
        "today_signups": int(today_signups),
        "yesterday_signups": int(yest_signups),
        "today_questions": int(today_questions),
        "today_credits_spent": int(today_charged),
        "total_revenue_krw": int(total_revenue),
        "revenue_today_krw": revenue_today,
        "revenue_week_krw": revenue_week,
        "revenue_month_krw": revenue_month,
        "revenue_year_krw": revenue_year,
        "total_outstanding_credits": int(total_balance),
    }


def list_all_payments(db: Session, limit: int = 20, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    """전 회원 결제 내역(최신순, 페이지네이션) — 회원 이메일 포함. 관리자 통계 리스트용."""
    total = db.execute(select(func.count(Payment.id))).scalar_one()
    rows = db.execute(
        select(Payment, User.email)
        .join(User, User.id == Payment.user_id, isouter=True)
        .order_by(Payment.id.desc())
        .limit(limit).offset(offset)
    ).all()
    items = [
        {
            "order_id": p.order_id,
            "email": email or "(탈퇴/없음)",
            "amount": int(p.amount or 0),
            "credit_granted": int(getattr(p, "credit_granted", 0) or 0),
            "status": p.status,
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "approved_at": p.approved_at.isoformat() if p.approved_at else None,
        }
        for p, email in rows
    ]
    return items, int(total)
