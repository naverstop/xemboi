"""adjust_credit(idem_key=…) 멱등성 검증 — 리컨실 재실행·재시도 이중차감/이중환불 차단.

idem_key 지정 시 같은 키의 거래는 1회만 반영되어야 한다(부분 UNIQUE 인덱스 ux_credit_tx_idem +
SAVEPOINT 게이트). idem_key=None 은 기존 비멱등 동작(매 호출 반영) 그대로임도 함께 확인한다.
"""
from __future__ import annotations

import pytest
from sqlalchemy import BigInteger, create_engine, func, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from backend.app.repositories import auth_models  # noqa: F401  테이블 메타 등록
from backend.app.repositories.auth_models import CreditTransaction, User
from backend.app.repositories.models import Base
from backend.app.services import auth_service


# SQLite 는 BigInteger PK 를 autoincrement 하지 않는다(운영 PostgreSQL 은 정상). adjust_credit 이
# CreditTransaction 을 id 없이 insert 하므로, 테스트 한정으로 BIGINT→INTEGER 로 컴파일해 rowid 자동증가시킨다.
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


def _mk(db) -> User:
    # SQLite 는 BigInteger PK 를 autoincrement 하지 않으므로 id 명시.
    u = User(id=1, email="u@u.com")
    db.add(u)
    db.flush()
    return u


def _txn_count(db, idem_key: str | None = None) -> int:
    q = select(func.count()).select_from(CreditTransaction)
    if idem_key is not None:
        q = q.where(CreditTransaction.idem_key == idem_key)
    return int(db.execute(q).scalar_one())


def test_idem_key_refund_applied_once(db):
    """같은 idem_key 로 두 번 +환불해도 잔액은 1회만 증가(이중환불 차단)."""
    _mk(db)
    auth_service.adjust_credit(db, 1, 1000, reason="admin_seed")          # 초기 1,000
    b1 = auth_service.adjust_credit(db, 1, 500, reason="refund", ref_id="c1", idem_key="receipt:1:refund")
    assert b1 == 1500
    # 리컨실 재실행/재시도 — 같은 키 → no-op, 잔액 불변
    b2 = auth_service.adjust_credit(db, 1, 500, reason="refund", ref_id="c1", idem_key="receipt:1:refund")
    assert b2 == 1500
    assert auth_service.get_balance(db, 1) == 1500
    assert _txn_count(db, "receipt:1:refund") == 1                        # 거래행도 1건뿐


def test_idem_key_charge_applied_once(db):
    """같은 idem_key 로 두 번 -차감해도 1회만 차감(이중차감 차단)."""
    _mk(db)
    auth_service.adjust_credit(db, 1, 1000, reason="admin_seed")
    b1 = auth_service.adjust_credit(db, 1, -300, reason="question", idem_key="q:42")
    assert b1 == 700
    b2 = auth_service.adjust_credit(db, 1, -300, reason="question", idem_key="q:42")
    assert b2 == 700                                                     # 재적용 없음
    assert auth_service.get_balance(db, 1) == 700
    assert _txn_count(db, "q:42") == 1


def test_no_idem_key_is_not_deduped(db):
    """idem_key 미지정(None)은 기존 비멱등 동작 — 매 호출 반영(회귀 없음)."""
    _mk(db)
    auth_service.adjust_credit(db, 1, 1000, reason="admin_seed")
    auth_service.adjust_credit(db, 1, -100, reason="question")
    auth_service.adjust_credit(db, 1, -100, reason="question")
    assert auth_service.get_balance(db, 1) == 800                        # 두 번 다 반영


def test_different_idem_keys_both_apply(db):
    """다른 idem_key 는 각각 반영(정상 연속 추가질문 차감이 막히지 않음)."""
    _mk(db)
    auth_service.adjust_credit(db, 1, 1000, reason="admin_seed")
    auth_service.adjust_credit(db, 1, -100, reason="tool_q", idem_key="t:1")
    auth_service.adjust_credit(db, 1, -100, reason="tool_q", idem_key="t:2")
    assert auth_service.get_balance(db, 1) == 800


def test_idem_gate_does_not_poison_on_insufficient(db):
    """잔액부족으로 실패한 idem 차감은 게이트행까지 원복 → 이후 잔액 생기면 같은 키로 정상 차감 가능."""
    _mk(db)
    auth_service.adjust_credit(db, 1, 100, reason="admin_seed")          # 잔액 100
    with pytest.raises(ValueError):
        auth_service.adjust_credit(db, 1, -300, reason="question", idem_key="q:99")  # 부족 → 실패
    assert _txn_count(db, "q:99") == 0                                   # 게이트행 미잔존(오염 없음)
    auth_service.adjust_credit(db, 1, 500, reason="admin_seed")          # 잔액 600
    b = auth_service.adjust_credit(db, 1, -300, reason="question", idem_key="q:99")  # 이제 성공
    assert b == 300
    assert _txn_count(db, "q:99") == 1
