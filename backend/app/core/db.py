"""SQLAlchemy 엔진 + 세션팩토리.

Settings.database_url 사용. 동기 엔진(개인 프로젝트 규모, 동시성 낮음).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.config import get_settings


@lru_cache(maxsize=1)
def get_engine():
    s = get_settings()
    url = s.database_url
    kwargs: dict = {"pool_pre_ping": True, "future": True}
    # PostgreSQL 등: 스트리밍 응답이 커넥션을 내내 점유 → 동시 스트림 다수에서 풀 고갈 방지로
    # 여유 설정. (sqlite 는 QueuePool 비대상이라 pool_size/max_overflow 인자 미지원 → 제외.)
    if not url.startswith("sqlite"):
        kwargs.update(pool_size=20, max_overflow=10, pool_recycle=1800)
    return create_engine(url, **kwargs)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI Depends 용 세션 dep."""
    sf = get_session_factory()
    with sf() as db:
        yield db
