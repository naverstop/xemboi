"""상담/타로 기록 일괄삭제(체크 → 일괄삭제) — bulk-delete 엔드포인트 핵심 동작 검증.

엔드포인트(POST /chat/sessions/bulk-delete, POST /tarot/bulk-delete)는 delete_session 을
소유검증과 함께 반복하며 '부분 성공'을 허용한다: 본인 소유만 삭제하고, 타인 세션
(PermissionError)·없는 세션(False/KeyError)은 조용히 건너뛰며 삭제 성공 건수를 반환한다.
개별 DELETE 반복(클라)의 레이트리밋·부분실패·목록 stale 문제를 서버 단일요청으로 대체한 것.

DB는 인메모리 SQLite 로 자체 구성(외부 의존 없음).
"""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.repositories import chat_repo, tarot_repo
from backend.app.repositories.models import Base, ChatSession, TarotSession


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


# 엔드포인트 루프를 그대로 재현(소유검증 + 부분성공).
def _chat_bulk(db, ids, user_id):
    deleted = 0
    for sid in ids:
        try:
            if chat_repo.delete_session(db, sid, user_id):
                deleted += 1
        except PermissionError:
            pass
    return deleted


def _tarot_bulk(db, ids, user_id):
    deleted = 0
    for tid in ids:
        try:
            if tarot_repo.delete_session(db, tid, user_id):
                deleted += 1
        except (KeyError, PermissionError):
            pass
    return deleted


def test_chat_bulk_deletes_owned_and_skips_others_and_missing(db):
    for sid in ("a", "b", "c"):
        db.add(ChatSession(session_id=sid, user_id=1, birth_date=date(1990, 1, 1)))
    db.add(ChatSession(session_id="other", user_id=2, birth_date=date(1990, 1, 1)))
    db.commit()

    # a·b(본인) + other(타인) + missing(없음) → 본인 2개만 삭제
    deleted = _chat_bulk(db, ["a", "b", "other", "missing"], user_id=1)

    assert deleted == 2
    assert {r.session_id for r in chat_repo.list_user_sessions(db, 1)} == {"c"}
    # 타인 세션은 절대 삭제되지 않음(소유 격리)
    assert {r.session_id for r in chat_repo.list_user_sessions(db, 2)} == {"other"}


def test_chat_bulk_empty_ids_noop(db):
    db.add(ChatSession(session_id="a", user_id=1, birth_date=date(1990, 1, 1)))
    db.commit()
    assert _chat_bulk(db, [], user_id=1) == 0
    assert {r.session_id for r in chat_repo.list_user_sessions(db, 1)} == {"a"}


def _mk_tarot(db, tid, user_id):
    db.add(TarotSession(tarot_id=tid, user_id=user_id, section="love", question="", spread_type="horseshoe7"))
    db.commit()


def test_tarot_bulk_deletes_owned_and_skips_others_and_missing(db):
    for tid in ("t1", "t2", "t3"):
        _mk_tarot(db, tid, 1)
    _mk_tarot(db, "tother", 2)

    deleted = _tarot_bulk(db, ["t1", "t2", "tother", "nope"], user_id=1)

    assert deleted == 2
    assert {r["tarot_id"] for r in tarot_repo.list_user_sessions(db, 1)} == {"t3"}
    assert {r["tarot_id"] for r in tarot_repo.list_user_sessions(db, 2)} == {"tother"}
