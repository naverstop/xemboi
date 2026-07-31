"""빈 채팅 세션 자동정리 + 한도 산정 테스트.

배경: '상담 시작'은 질문 전에도 세션 행을 즉시 만든다. 반복 클릭/이탈 시 빈 세션
(메시지 0개)이 영구히 쌓여 max_sessions_per_user(기본 20)를 소진하고, 그 결과
세션 생성이 409로 막혀 프론트에 "이미 존재하는 정보예요"가 잘못 표시됐다.

수정: (1) 빈 세션은 한도 카운트에서 제외, (2) 세션 생성/로그아웃 시 빈 세션 자동삭제.
DB는 인메모리 SQLite로 자체 구성(외부 의존 없음).
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.repositories import chat_repo
from backend.app.repositories.models import Base, ChatMessage, ChatSession


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


def _mk_session(db, sid: str, user_id: int | None) -> ChatSession:
    row = ChatSession(session_id=sid, user_id=user_id, birth_date=date(1990, 1, 1))
    db.add(row)
    db.commit()
    return row


def _add_message(db, sid: str, role: str = "user", content: str = "질문") -> ChatMessage:
    m = ChatMessage(session_id=sid, role=role, content=content)
    db.add(m)
    db.commit()
    return m


# ---- repo 레벨 ----

def test_delete_empty_sessions_removes_only_empty(db):
    _mk_session(db, "empty1", 1)
    _mk_session(db, "empty2", 1)
    _mk_session(db, "real1", 1)
    _add_message(db, "real1")
    _mk_session(db, "other_empty", 2)  # 다른 회원 — 영향 없어야

    removed = chat_repo.delete_empty_sessions(db, 1)

    assert removed == 2
    assert {r.session_id for r in chat_repo.list_user_sessions(db, 1)} == {"real1"}
    # 다른 회원의 빈 세션은 보존
    assert {r.session_id for r in chat_repo.list_user_sessions(db, 2)} == {"other_empty"}


def test_delete_empty_sessions_noop_when_none(db):
    _mk_session(db, "real1", 1)
    _add_message(db, "real1")
    assert chat_repo.delete_empty_sessions(db, 1) == 0
    assert chat_repo.count_messages(db, "real1") == 1  # 실제 세션/메시지 보존


def test_count_user_sessions_excludes_empty(db):
    _mk_session(db, "empty1", 1)
    _mk_session(db, "real1", 1)
    _add_message(db, "real1")
    _mk_session(db, "real2", 1)
    _add_message(db, "real2", role="assistant", content="답변")

    # 빈 세션 1개는 제외 → 실제 상담 2개만 카운트
    assert chat_repo.count_user_sessions(db, 1) == 2


# ---- service 레벨 (create_session prune + 한도) ----

def _patch_limit(monkeypatch, n: int):
    from backend.app.services import chat_service
    s = chat_service.get_settings()
    monkeypatch.setattr(s, "max_sessions_per_user", n, raising=False)


def _birth():
    from backend.app.domain.chat_dto import BirthDTO
    return BirthDTO(birth_date=date(1990, 5, 5))


# 실제 행 INSERT(chat_repo.create_session)는 repo 테스트가 담당한다. 서비스 테스트는
# 'prune → 한도검사 → 생성' 오케스트레이션만 검증하므로 최종 INSERT는 스텁한다.
# (운영 Postgres는 ISO 날짜 문자열을 수용하지만 테스트용 SQLite는 date 객체만 허용)
def _stub_insert(monkeypatch):
    from backend.app.services import chat_service
    monkeypatch.setattr(
        chat_service.chat_repo,
        "create_session",
        lambda db_, **kw: SimpleNamespace(session_id=kw["session_id"]),
    )


def test_create_session_prunes_empty_then_succeeds(db, monkeypatch):
    from backend.app.services import chat_service
    user = SimpleNamespace(id=1)
    _patch_limit(monkeypatch, 3)
    _stub_insert(monkeypatch)

    # 실제 상담 2개 + 빈 세션 3개(상담시작 반복으로 쌓인 것)
    for i in range(2):
        _mk_session(db, f"real{i}", 1)
        _add_message(db, f"real{i}")
    for i in range(3):
        _mk_session(db, f"empty{i}", 1)

    sid, summary, chart = chat_service.create_session(db, _birth(), top_k=4, user=user)

    # 빈 세션 3개가 정리되어 실제 상담 2개만 남고, 생성은 성공한다
    assert sid
    assert {r.session_id for r in chat_repo.list_user_sessions(db, 1)} == {"real0", "real1"}
    assert chat_repo.count_user_sessions(db, 1) == 2


def test_create_session_raises_when_real_sessions_at_limit(db, monkeypatch):
    from backend.app.services import chat_service
    user = SimpleNamespace(id=1)
    _patch_limit(monkeypatch, 2)

    for i in range(2):
        _mk_session(db, f"real{i}", 1)
        _add_message(db, f"real{i}")
    # 빈 세션이 끼어 있어도 정리 후 실제 2개 == 한도 2 → 초과
    _mk_session(db, "empty", 1)

    with pytest.raises(chat_service.SessionLimitError) as ei:
        chat_service.create_session(db, _birth(), top_k=4, user=user)

    assert "session_limit_reached" in str(ei.value)
    # 빈 세션은 정리되어야 한다(실제 상담만 남음)
    assert {r.session_id for r in chat_repo.list_user_sessions(db, 1)} == {"real0", "real1"}


def test_create_session_anonymous_no_limit_no_prune(db, monkeypatch):
    from backend.app.services import chat_service
    _patch_limit(monkeypatch, 1)
    _stub_insert(monkeypatch)
    # 익명(user=None)은 한도/정리 대상 아님 — 항상 생성 성공
    sid, _, _ = chat_service.create_session(db, _birth(), top_k=4, user=None)
    assert sid
