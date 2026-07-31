"""무료/멤버십/일일 무료 슬롯의 원자적 선점(claim) 검증 — G3 lost-update 차단.

배경: 기존 무료 카운터는 read-modify-write(`used = user.free_used_count; ... used+1`)라,
두 동시요청이 같은 used 를 읽으면 둘 다 `used<quota` 로 판정돼 모두 무료가 되고 카운터는
1만 증가하는 race(무료 N회 치팅)가 있었다. claim_* 헬퍼는 단일
`UPDATE ... WHERE coalesce(used,0)<quota` 로 1슬롯만 원자적으로 선점한다(rowcount 로 성공판정).
한도 초과 선점이 구조적으로 불가능함을 검증한다.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.repositories import auth_models  # noqa: F401  테이블 메타 등록
from backend.app.repositories.auth_models import User
from backend.app.repositories.models import Base
from backend.app.services import auth_service


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


def _mk(db, **kw) -> User:
    # SQLite 는 BigInteger PK 를 autoincrement 하지 않으므로 id 를 명시.
    u = User(id=kw.pop("id", 1), email=kw.pop("email", "u@u.com"), **kw)
    db.add(u)
    db.flush()
    return u


def test_claim_free_quota_enforces_limit(db):
    u = _mk(db, free_used_count=0)
    quota = 3
    # 한도까지는 모두 선점 성공
    assert [auth_service.claim_free_quota(db, u, quota) for _ in range(3)] == [True, True, True]
    assert u.free_used_count == 3
    # 한도 초과 선점은 실패(False) — 무료 N회 치팅 불가
    assert auth_service.claim_free_quota(db, u, quota) is False
    assert u.free_used_count == 3  # 카운터가 더 늘지 않음


def test_claim_free_quota_partial_remaining(db):
    # 이미 2회 사용(quota 3) → 1슬롯만 남음
    u = _mk(db, free_used_count=2)
    assert auth_service.claim_free_quota(db, u, 3) is True
    assert u.free_used_count == 3
    assert auth_service.claim_free_quota(db, u, 3) is False


def test_claim_membership_quota_enforces_limit(db):
    u = _mk(db, membership_used_count=999)
    assert auth_service.claim_membership_quota(db, u, 1000) is True
    assert u.membership_used_count == 1000
    # 연 한도 소진 → 더 이상 무과금 선점 불가
    assert auth_service.claim_membership_quota(db, u, 1000) is False
    assert u.membership_used_count == 1000


def test_claim_daily_free_once_per_day(db):
    today = date.today()
    u = _mk(db)
    assert auth_service.claim_daily_free(db, u, today) is True
    assert u.daily_free_used_at == today
    # 같은 날 재선점 불가(1일 1건)
    assert auth_service.claim_daily_free(db, u, today) is False
    # 날짜가 바뀌면 다시 가능
    assert auth_service.claim_daily_free(db, u, today + timedelta(days=1)) is True
    assert u.daily_free_used_at == today + timedelta(days=1)
