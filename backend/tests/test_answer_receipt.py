"""answer_receipts 수명주기 검증 — 선차감(pending) → 완결(complete)/환불(refunded) 결정적 전이.

크래시 orphan = 'pending 으로 남은 영수증'. finalize/close 는 조건부(status='pending')라 이미 마감된 건을
덮어쓰지 않는다(리컨실·완결 레이스에서 상태 보존). open 은 실현금(amount>0)·회원만 대상.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

from backend.app.repositories import auth_models  # noqa: F401  테이블 메타 등록
from backend.app.repositories.auth_models import AnswerReceipt, Credit, User
from backend.app.repositories.models import Base
from backend.app.services import auth_service, receipt_service


# SQLite 는 BigInteger PK 를 autoincrement 하지 않음 → 테스트 한정 BIGINT→INTEGER.
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


def _get(db, rid) -> AnswerReceipt:
    return db.execute(select(AnswerReceipt).where(AnswerReceipt.id == rid)).scalar_one()


def test_open_only_for_cash_member(db):
    """실현금(amount>0)·회원만 영수증 생성. 무료슬롯(amount=0)·비회원(user None)은 대상 아님."""
    assert receipt_service.open_receipt(db, user_id=None, menu="tool_q", ref_id="t1", amount=1000) is None
    assert receipt_service.open_receipt(db, user_id=1, menu="tool_q", ref_id="t1", amount=0) is None
    rid = receipt_service.open_receipt(db, user_id=1, menu="tool_q", ref_id="t1", amount=1000)
    assert rid is not None
    r = _get(db, rid)
    assert (r.status, r.amount, r.user_id, r.menu) == ("pending", 1000, 1, "tool_q")


def test_finalize_pending_to_complete(db):
    rid = receipt_service.open_receipt(db, user_id=1, menu="compatibility_q", ref_id="c1", amount=3000)
    receipt_service.finalize_receipt(db, rid, message_id=42, ref_id="c1")
    r = _get(db, rid)
    assert r.status == "complete"
    assert r.message_id == 42
    assert r.finalized_at is not None


def test_close_pending_to_refunded(db):
    rid = receipt_service.open_receipt(db, user_id=1, menu="tarot_q", ref_id="k1", amount=1000)
    receipt_service.close_refunded(db, rid)
    assert _get(db, rid).status == "refunded"


def test_finalize_does_not_override_refunded(db):
    """이미 환불된 영수증에 finalize 가 와도 complete 로 덮어쓰지 않는다(조건부 전이)."""
    rid = receipt_service.open_receipt(db, user_id=1, menu="tool_q", ref_id="t1", amount=1000)
    receipt_service.close_refunded(db, rid)
    receipt_service.finalize_receipt(db, rid, message_id=7)   # no-op 이어야 함
    r = _get(db, rid)
    assert r.status == "refunded"
    assert r.message_id is None


def test_close_does_not_override_complete(db):
    """이미 완결된 영수증에 close 가 와도 refunded 로 덮어쓰지 않는다(정상 답변을 환불로 오인 금지)."""
    rid = receipt_service.open_receipt(db, user_id=1, menu="tarot_q", ref_id="k1", amount=1000)
    receipt_service.finalize_receipt(db, rid, message_id=9)
    receipt_service.close_refunded(db, rid)                   # no-op 이어야 함
    assert _get(db, rid).status == "complete"


def test_none_receipt_id_is_noop(db):
    """receipt_id=None(무료슬롯·비회원·explain)은 finalize/close 모두 조용히 no-op."""
    receipt_service.finalize_receipt(db, None, message_id=1)
    receipt_service.close_refunded(db, None)
    assert db.execute(select(AnswerReceipt)).first() is None


# ───────────────────────── 리컨실(orphan 환불) ─────────────────────────

def _user_with_balance(db, bal: int) -> None:
    db.add(User(id=1, email="u@u.com"))
    db.add(Credit(user_id=1, balance=bal))
    db.flush()


def test_reconcile_refunds_old_orphan(db):
    """pending + 임계 경과 = 크래시 orphan → 환불 + status=refunded."""
    _user_with_balance(db, 500)
    old = datetime.utcnow() - timedelta(minutes=25)
    db.add(AnswerReceipt(user_id=1, menu="tool_q", ref_id="t1", amount=1000, status="pending", created_at=old))
    db.flush()
    assert receipt_service.reconcile_orphans(db, older_than_min=20) == 1
    assert auth_service.get_balance(db, 1) == 1500
    assert db.execute(select(AnswerReceipt)).scalar_one().status == "refunded"


def test_reconcile_idempotent(db):
    """리컨실 재실행은 이미 refunded 라 대상 없음 — 이중환불 불가(status 가드 + idem_key)."""
    _user_with_balance(db, 0)
    old = datetime.utcnow() - timedelta(minutes=25)
    db.add(AnswerReceipt(id=7, user_id=1, menu="tarot_q", ref_id="k1", amount=3000, status="pending", created_at=old))
    db.flush()
    assert receipt_service.reconcile_orphans(db, older_than_min=20) == 1
    assert auth_service.get_balance(db, 1) == 3000
    assert receipt_service.reconcile_orphans(db, older_than_min=20) == 0
    assert auth_service.get_balance(db, 1) == 3000


def test_reconcile_skips_recent_and_finalized(db):
    """임계 미달(생성 중일 수 있음)·complete·refunded 는 대상 아님(오환불 금지)."""
    _user_with_balance(db, 0)
    now = datetime.utcnow()
    db.add(AnswerReceipt(user_id=1, menu="tool_q", ref_id="a", amount=1000, status="pending",
                         created_at=now - timedelta(minutes=2)))     # 임계 미달
    db.add(AnswerReceipt(user_id=1, menu="tool_q", ref_id="b", amount=1000, status="complete",
                         created_at=now - timedelta(minutes=30)))    # 정상 완결
    db.add(AnswerReceipt(user_id=1, menu="tool_q", ref_id="c", amount=1000, status="refunded",
                         created_at=now - timedelta(minutes=30)))    # 이미 환불
    db.flush()
    assert receipt_service.reconcile_orphans(db, older_than_min=20) == 0
    assert auth_service.get_balance(db, 1) == 0


# ───────────────────────── 무료슬롯 orphan ─────────────────────────

def test_open_for_bill_kinds(db):
    """bill → slot_kind 판정: 현금/멤버십/pass/무료/일일, 무슬롯은 None."""
    db.add(User(id=1, email="u@u.com"))
    db.flush()
    rid = receipt_service.open_for_bill(db, user_id=1, menu="tool_q", ref_id="t",
                                        bill={"credits_to_charge": 1000}, charged=1000)
    assert (_get(db, rid).slot_kind, _get(db, rid).amount) == ("cash", 1000)
    rid = receipt_service.open_for_bill(db, user_id=1, menu="question", ref_id="s",
                                        bill={"use_membership": True}, charged=0)
    assert (_get(db, rid).slot_kind, _get(db, rid).amount) == ("membership", 0)
    rid = receipt_service.open_for_bill(db, user_id=1, menu="question", ref_id="s",
                                        bill={"use_pass_free": True, "pass_id": 42}, charged=0)
    assert (_get(db, rid).slot_kind, _get(db, rid).pass_id) == ("pass", 42)
    rid = receipt_service.open_for_bill(db, user_id=1, menu="question", ref_id="s",
                                        bill={"use_free_quota": True}, charged=0)
    assert _get(db, rid).slot_kind == "free"
    # 무슬롯(관리자 등)·비회원 → None
    assert receipt_service.open_for_bill(db, user_id=1, menu="question", ref_id="s", bill={}, charged=0) is None
    assert receipt_service.open_for_bill(db, user_id=None, menu="question", ref_id="s",
                                         bill={"use_membership": True}, charged=0) is None


def test_reconcile_restores_membership_slot(db):
    """멤버십 슬롯 orphan → 카운터 복원(포인트 환불 아님)."""
    db.add(User(id=1, email="u@u.com", membership_used_count=5))
    db.flush()
    old = datetime.utcnow() - timedelta(minutes=25)
    db.add(AnswerReceipt(user_id=1, menu="question", ref_id="s1", amount=0, slot_kind="membership",
                         status="pending", created_at=old))
    db.flush()
    assert receipt_service.reconcile_orphans(db, older_than_min=20) == 1
    assert db.get(User, 1).membership_used_count == 4                 # 복원
    assert db.execute(select(AnswerReceipt)).scalar_one().status == "refunded"


def test_reconcile_restores_free_and_daily(db):
    """무료 카운터·일일무료 orphan 복원. 카운터 0 미만으로 가지 않음(조건부)."""
    db.add(User(id=1, email="u@u.com", free_used_count=3, daily_free_used_at=datetime.utcnow()))
    db.flush()
    old = datetime.utcnow() - timedelta(minutes=25)
    db.add(AnswerReceipt(user_id=1, menu="question", ref_id="f", amount=0, slot_kind="free",
                         status="pending", created_at=old))
    db.add(AnswerReceipt(user_id=1, menu="question", ref_id="d", amount=0, slot_kind="daily",
                         status="pending", created_at=old))
    db.flush()
    assert receipt_service.reconcile_orphans(db, older_than_min=20) == 2
    u = db.get(User, 1)
    assert u.free_used_count == 2                                     # 무료 1회 복원
    assert u.daily_free_used_at is None                              # 일일무료 복원


def test_purge_terminal_keeps_pending(db):
    """종결(complete/refunded) 오래된 것만 삭제, pending 은 절대 삭제 안 함."""
    db.add(User(id=1, email="u@u.com"))
    db.flush()
    old = datetime.utcnow() - timedelta(days=10)
    db.add(AnswerReceipt(user_id=1, menu="question", ref_id="a", amount=0, slot_kind="free",
                         status="pending", created_at=old))
    db.add(AnswerReceipt(user_id=1, menu="question", ref_id="b", amount=1000, slot_kind="cash",
                         status="complete", created_at=old, finalized_at=old))
    db.add(AnswerReceipt(user_id=1, menu="question", ref_id="c", amount=1000, slot_kind="cash",
                         status="refunded", created_at=old, finalized_at=old))
    db.flush()
    assert receipt_service.purge_terminal(db, older_than_days=7) == 2
    remaining = db.execute(select(AnswerReceipt)).scalars().all()
    assert len(remaining) == 1 and remaining[0].status == "pending"
