"""B-7 월 패스 서비스 — 포인트 자동차감형 구독(빌링키·PG 구독계약 불필요, §5-2 확정 설계).

혜택(관리자 설정으로 즉시 조정):
  라이트(pass_lite_price_p, 기본 3,900P/30일): 광고 제거 + 공유 쿼터 확대(pass_share_quota)
  플러스(pass_plus_price_p, 기본 9,900P/30일): 라이트 전체 + 추가질문 할인(pass_followup_discount_pct)
        + 월 1회 기본질문 무료(pass_free_basic_monthly) + 월 1회 부적 무료(pass_amulet_monthly)

갱신: '지연 평가' — get_pass() 호출 시점에 주기 경과면 차감 시도(스케줄러 불필요, 재기동 안전).
잔액 부족 → 비활성 + 충전 유도 웹푸시. 오래 미접속이어도 밀린 주기를 소급 다중과금하지 않는다
(현재 시점부터 새 주기 1회만 차감 — 사용자에게 유리한 쪽).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.app.repositories.auth_models import User, UserPass
from backend.app.services import auth_service, settings_service

PERIOD_DAYS = 30

TIER_LABELS = {"lite": "라이트 패스", "plus": "플러스 패스"}


def price_p(db: Session, tier: str) -> int:
    if tier == "plus":
        return settings_service.get_int(db, "pass_plus_price_p", 9900)
    return settings_service.get_int(db, "pass_lite_price_p", 3900)


def _renew_or_expire(db: Session, row: UserPass) -> UserPass:
    """주기 경과 시 갱신 차감(또는 비활성). 커밋 포함."""
    now = datetime.utcnow()
    if not row.active or row.next_renewal_at > now:
        return row
    if not row.auto_renew:
        row.active = False
        db.commit()
        return row
    cost = price_p(db, row.tier)
    # 주기 전진을 '원자적으로 선점' — 만료경계 동시요청/더블클릭이 둘 다 갱신비를 차감하던 이중과금 차단.
    #   next_renewal_at<=now 인 동안만 승자 1명이 주기를 전진(rowcount==1)하고 그 승자만 차감한다.
    res = db.execute(
        update(UserPass)
        .where(UserPass.id == row.id, UserPass.active == True,  # noqa: E712
               UserPass.auto_renew == True, UserPass.next_renewal_at <= now)  # noqa: E712
        .values(current_start=now, next_renewal_at=now + timedelta(days=PERIOD_DAYS),
                price_p=cost, free_basic_used=0, amulet_used=0)
    )
    if res.rowcount != 1:
        # 다른 요청이 먼저 갱신함(또는 조건 불충족) → 나는 차감하지 않고 최신 상태만 재로드.
        db.commit()
        db.refresh(row)
        return row
    try:
        # 승자 — 새 주기 1회분 차감. 소급 다중과금 금지는 위 조건부 전진으로 이미 보장.
        if cost > 0:
            auth_service.adjust_credit(db, row.user_id, -cost, reason="pass_renew", ref_id=row.tier)
        db.commit()
    except ValueError:
        # 잔액 부족 → 방금 전진한 주기를 보상 롤백하고 비활성 + 충전 유도 푸시(실패해도 무시)
        db.rollback()
        row.active = False
        db.commit()
        try:
            from backend.app.services import push_service
            push_service.send_to_user(
                db, row.user_id,
                title="월 패스 갱신 실패",
                body=f"{TIER_LABELS.get(row.tier, row.tier)} 갱신 포인트가 부족해요. 충전하면 다시 이용할 수 있어요.",
                url="/payments",
            )
        except Exception:  # noqa: BLE001
            pass
    return row


def get_pass(db: Session, user_id: int) -> Optional[UserPass]:
    """활성 패스 조회(지연 갱신 포함). 없거나 만료-비활성이면 None."""
    row = db.execute(select(UserPass).where(UserPass.user_id == user_id)).scalar_one_or_none()
    if row is None:
        return None
    row = _renew_or_expire(db, row)
    return row if row.active else None


def subscribe(db: Session, user: User, tier: str) -> UserPass:
    if tier not in TIER_LABELS:
        raise ValueError("알 수 없는 패스예요.")
    existing = db.execute(select(UserPass).where(UserPass.user_id == user.id)).scalar_one_or_none()
    if existing is not None:
        existing = _renew_or_expire(db, existing)
        if existing.active:
            raise ValueError("이미 이용 중인 패스가 있어요. 만료 후 변경할 수 있어요.")
    cost = price_p(db, tier)
    if cost > 0:
        auth_service.adjust_credit(db, user.id, -cost, reason=f"pass_{tier}")  # 부족 시 ValueError → 402
    now = datetime.utcnow()
    if existing is None:
        existing = UserPass(user_id=user.id, tier=tier, started_at=now, next_renewal_at=now)
        db.add(existing)
    existing.tier = tier
    existing.active = True
    existing.auto_renew = True
    existing.current_start = now
    existing.next_renewal_at = now + timedelta(days=PERIOD_DAYS)
    existing.price_p = cost
    existing.free_basic_used = 0
    existing.amulet_used = 0
    existing.canceled_at = None
    db.commit()
    db.refresh(existing)
    return existing


def cancel(db: Session, user: User) -> Optional[UserPass]:
    """자동갱신 해지 — 남은 기간은 그대로 이용."""
    row = db.execute(select(UserPass).where(UserPass.user_id == user.id)).scalar_one_or_none()
    if row is None or not row.active:
        raise LookupError("이용 중인 패스가 없어요.")
    row.auto_renew = False
    row.canceled_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def claim_free_basic(db: Session, pass_id: int) -> bool:
    """플러스 월 무료 기본질문 원자적 선점(동시요청 이중 무료 차단).

    [버그 2026-07-22] quota 가 1 로 하드코딩돼 있어, 설정(pass_free_basic_monthly)을 5로 올려도
    실제로는 1회만 무료였다(표시는 5회 → 과금은 1회, 실측으로 발견). 호출부가 설정으로 게이트하지만
    최종 상한은 이 UPDATE 의 WHERE 가 정하므로 여기서도 같은 설정을 읽어야 한다.
    ⚠️ 원자성은 그대로 — 상한만 설정값으로 바뀌고 판정은 여전히 단일 UPDATE + rowcount.
    """
    quota = settings_service.get_int(db, "pass_free_basic_monthly", 5)
    if quota <= 0:
        return False
    res = db.execute(
        update(UserPass)
        .where(UserPass.id == pass_id, UserPass.active == True,  # noqa: E712
               UserPass.free_basic_used < quota)
        .values(free_basic_used=UserPass.free_basic_used + 1)
    )
    db.flush()
    return res.rowcount == 1


def refund_free_basic(db: Session, pass_id: int) -> None:
    """생성 실패 시 claim_free_basic 으로 선점한 월 무료 기본질문을 원자적으로 되돌린다(-1, 0 미만 방지)."""
    db.execute(
        update(UserPass)
        .where(UserPass.id == pass_id, UserPass.free_basic_used > 0)
        .values(free_basic_used=UserPass.free_basic_used - 1)
    )


def claim_free_amulet(db: Session, pass_id: int) -> bool:
    """플러스 월 무료 부적 원자적 선점. 상한은 설정(pass_amulet_monthly) — claim_free_basic 과 동일 이유로
    하드코딩(<1)을 제거했다. 설정을 올려도 1회만 나가던 표시/과금 불일치 방지."""
    quota = settings_service.get_int(db, "pass_amulet_monthly", 1)
    if quota <= 0:
        return False
    res = db.execute(
        update(UserPass)
        .where(UserPass.id == pass_id, UserPass.active == True,  # noqa: E712
               UserPass.amulet_used < quota)
        .values(amulet_used=UserPass.amulet_used + 1)
    )
    db.flush()
    return res.rowcount == 1


def to_dict(db: Session, row: Optional[UserPass]) -> Optional[dict[str, Any]]:
    if row is None or not row.active:
        return None
    free_q = settings_service.get_int(db, "pass_free_basic_monthly", 5) if row.tier == "plus" else 0
    am_q = settings_service.get_int(db, "pass_amulet_monthly", 1) if row.tier == "plus" else 0
    return {
        "tier": row.tier,
        "label": TIER_LABELS.get(row.tier, row.tier),
        "price_p": row.price_p,
        "auto_renew": row.auto_renew,
        "current_start": row.current_start.isoformat(),
        "next_renewal_at": row.next_renewal_at.isoformat(),
        "free_basic_remaining": max(0, free_q - (row.free_basic_used or 0)),
        "amulet_free_remaining": max(0, am_q - (row.amulet_used or 0)),
    }
