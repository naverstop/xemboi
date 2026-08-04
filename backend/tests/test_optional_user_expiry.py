"""get_optional_user — 만료·무효 토큰 처리 회귀 테스트.

배경(전수 감사 w623828ym): 과거 get_optional_user는 만료·서명오류 토큰의 예외까지
`except Exception: return None`으로 삼켜 '토큰 없음(진짜 비로그인)'과 동일하게 익명(None)으로
강등했다. 그 결과 optional 라우트(꿈해몽·오늘운세·신년·궁합·타로 등)가 401 대신 200(익명
미리보기)을 반환했고, 프론트 강제로그아웃(notifySessionExpired)·무음갱신(refresh)은 모두
401에서만 발동하므로 '로그인 상태(캐시 잔액)인데 미리보기'로 새어나가는 사고가 반복됐다.

수정: 토큰이 '없으면' None(익명 허용) 유지, 토큰이 '실려 왔는데 만료·무효'면 401을 던진다.
→ 프론트가 무음갱신/강제로그아웃을 정상 트리거한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_settings
from backend.app.core.deps import get_optional_user
from backend.app.repositories.models import Base
import backend.app.repositories.auth_models  # noqa: F401  (users 테이블 등록)


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


def _token(sub: str, *, minutes: int) -> str:
    """유효 서명 토큰 — minutes<0 이면 만료(exp 과거)."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "typ": "access",
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def test_no_token_stays_anonymous(db):
    """Authorization 헤더 없음 = 진짜 비로그인 → None(익명 미리보기 허용, 200 경로)."""
    assert get_optional_user(authorization=None, db=db) is None


def test_non_bearer_header_stays_anonymous(db):
    """Bearer 스킴이 아니면 토큰 미추출 → None(익명). (예: 잘못된 헤더 형식)"""
    assert get_optional_user(authorization="Basic zzz", db=db) is None


def test_garbage_token_raises_401(db):
    """토큰이 실려 왔는데 디코드 불가(서명오류) → 401 (조용한 익명 강등 금지)."""
    with pytest.raises(HTTPException) as ei:
        get_optional_user(authorization="Bearer not.a.real.jwt", db=db)
    assert ei.value.status_code == 401


def test_expired_token_raises_401(db):
    """유효 서명이지만 exp 만료 → 401 (프론트 refresh/강제로그아웃 트리거 보존)."""
    with pytest.raises(HTTPException) as ei:
        get_optional_user(authorization=f"Bearer {_token('1', minutes=-5)}", db=db)
    assert ei.value.status_code == 401


def test_valid_token_unknown_user_raises_401(db):
    """서명·만료 모두 정상이지만 해당 사용자가 없음(삭제됨) → 무효 세션 → 401."""
    with pytest.raises(HTTPException) as ei:
        get_optional_user(authorization=f"Bearer {_token('999999', minutes=30)}", db=db)
    assert ei.value.status_code == 401
