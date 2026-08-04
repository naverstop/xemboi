"""미완료 결제 pending 만료 처리 검증 — 유령/테스트 주문 정리, 자동결제 위험 0.

대상은 오직 'status=pending AND toss_payment_key IS NULL AND 오래됨'. paymentKey 있는 주문·최근 주문·
approved/refunded 는 절대 만료시키지 않는다(무결제 크레딧·오적립 차단). confirm_payment 는 expired 를 승인불가로 막는다.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from backend.app.repositories import auth_models  # noqa: F401  테이블 메타 등록
from backend.app.repositories.auth_models import Payment
from backend.app.repositories.models import Base
from backend.app.services import payment_service


@compiles(BigInteger, "sqlite")
def _bigint_as_integer_sqlite(type_, compiler, **kw):  # noqa: ANN001, ARG001
    return "INTEGER"


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _pay(db, *, oid, status="pending", key=None, age_h=48, amount=11000):
    db.add(Payment(
        user_id=1, order_id=oid, amount=amount, credit_granted=amount, status=status,
        toss_payment_key=key, created_at=datetime.utcnow() - timedelta(hours=age_h),
    ))
    db.flush()


def _status(db, oid) -> str:
    return db.execute(select(Payment.status).where(Payment.order_id == oid)).scalar_one()


def test_expires_only_abandoned_old_pending(db):
    _pay(db, oid="old_nokey", status="pending", key=None, age_h=48)      # 대상
    _pay(db, oid="recent_nokey", status="pending", key=None, age_h=2)    # 최근 → 보존
    _pay(db, oid="old_withkey", status="pending", key="pk_123", age_h=48)  # 결제키 있음 → 보존
    _pay(db, oid="old_approved", status="approved", key="pk_9", age_h=48)  # 승인 → 불변
    _pay(db, oid="old_refunded", status="refunded", key="pk_r", age_h=48)  # 환불 → 불변
    db.flush()

    n = payment_service.expire_pending_orders(db, older_than_hours=24)
    assert n == 1                                    # 오래된 미완료 pending 1건만
    assert _status(db, "old_nokey") == "expired"
    assert _status(db, "recent_nokey") == "pending"
    assert _status(db, "old_withkey") == "pending"   # 결제키 있으면 만료 안 함(오결제 방지)
    assert _status(db, "old_approved") == "approved"
    assert _status(db, "old_refunded") == "refunded"


def test_threshold_respected(db):
    _pay(db, oid="p10h", status="pending", key=None, age_h=10)
    db.flush()
    assert payment_service.expire_pending_orders(db, older_than_hours=24) == 0   # 10h < 24h
    assert payment_service.expire_pending_orders(db, older_than_hours=6) == 1    # 10h > 6h
    assert _status(db, "p10h") == "expired"


def test_confirm_rejects_expired():
    """confirm_payment 가드에 'expired' 포함 확인(만료 후 뒤늦은 confirm=무결제 크레딧 차단)."""
    import inspect
    src = inspect.getsource(payment_service.confirm_payment)
    assert '"expired"' in src and "not approvable" in src
