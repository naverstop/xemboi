"""포인트 원장 정합성 요약 회귀 테스트 — 돈에 관한 불변식 고정.

사용자가 '충전 + 적립·환불 − 사용 = 현재 잔액'을 직접 대조할 수 있어야 하므로(운영자 지시 2026-07-19),
credit_ledger_summary 가 항상 purchased+rewarded-used == balance == computed_balance 를 만족하고,
표시 잔액과 원장 합이 어긋나면 consistent=False 를 내야 한다.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.repositories.models import Base
from backend.app.repositories.auth_models import Credit, CreditTransaction
from backend.app.services import admin_service


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


def _seed(db, uid: int, txns: list[tuple[str, int, int]], balance: int) -> None:
    # BigInteger PK 는 sqlite 에서 autoincrement 되지 않으므로 명시 id 부여(운영 PostgreSQL 은 자동).
    for i, (reason, delta, ba) in enumerate(txns, 1):
        db.add(CreditTransaction(id=uid * 100 + i, user_id=uid, delta=delta, reason=reason, balance_after=ba))
    db.add(Credit(user_id=uid, balance=balance))
    db.commit()


def test_summary_reconciles_and_categorizes(db):
    """충전(purchase)·적립(보너스)·사용(차감)이 올바르게 분류되고 대조식이 맞아야 한다."""
    # +30,000 결제충전, +10,000 가입보너스, -9,900 신년, -4,900 타로 → 잔액 25,200
    _seed(db, 5000, [
        ("purchase", 30000, 30000),
        ("signup_bonus", 10000, 40000),
        ("sinnyeon", -9900, 30100),
        ("tarot", -4900, 25200),
    ], balance=25200)
    s = admin_service.credit_ledger_summary(db, 5000)
    assert s["purchased"] == 30000           # 실결제만
    assert s["rewarded"] == 10000            # 보너스·환불·리워드
    assert s["used"] == 14800                # 9,900 + 4,900 (절대값)
    assert s["balance"] == 25200
    assert s["computed_balance"] == 25200    # Σdelta
    assert s["consistent"] is True
    assert s["count"] == 4
    # 사용자 대조식: 충전 + 적립 − 사용 == 잔액
    assert s["purchased"] + s["rewarded"] - s["used"] == s["balance"]


def test_summary_flags_inconsistency(db):
    """표시 잔액(credits.balance)이 원장 합과 다르면 consistent=False (사용자 경고 노출용)."""
    # 원장 합 = 100, 그러나 credits.balance = 999 (불일치 모사)
    _seed(db, 5001, [("purchase", 100, 100)], balance=999)
    s = admin_service.credit_ledger_summary(db, 5001)
    assert s["computed_balance"] == 100
    assert s["balance"] == 999
    assert s["consistent"] is False


def test_summary_empty_user(db):
    """거래가 없는 사용자 — 전부 0, consistent(0==0)=True."""
    db.add(Credit(user_id=5002, balance=0))
    db.commit()
    s = admin_service.credit_ledger_summary(db, 5002)
    assert s == {"purchased": 0, "rewarded": 0, "used": 0, "balance": 0,
                 "computed_balance": 0, "consistent": True, "count": 0}
