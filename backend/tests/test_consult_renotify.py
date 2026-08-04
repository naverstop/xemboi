"""미응답 상담 재푸시(운영자 지시 2026-07-11) — 45초 간격, 응답 시 중지, 15분 상한."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.repositories.models import Base
from backend.app.repositories import auth_models  # noqa: F401 — create_all 등록
from backend.app.repositories.consultation_models import Consultant, ConsultationSession


@pytest.fixture()
def db_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    from backend.app.services import scheduler
    monkeypatch.setattr(scheduler, "get_session_factory", lambda: SessionLocal)
    scheduler._consult_repush.clear()
    yield SessionLocal
    engine.dispose()


def _mk(db, status="requested", minutes_ago=1):
    c = Consultant(id=1, user_id=77, business_name="테스트상담소", login_email="probe@test.internal")  # sqlite: BigInteger PK 수동 지정
    db.add(c); db.flush()
    s = ConsultationSession(id=uuid.uuid4().hex, consultant_id=c.id, user_id=1,
                            status=status,
                            requested_at=datetime.utcnow() - timedelta(minutes=minutes_ago))
    db.add(s); db.commit()
    return s


def test_renotify_waits_then_pushes_and_stops(db_factory, monkeypatch):
    from backend.app.services import scheduler
    sent = []
    monkeypatch.setattr("backend.app.services.push_service.send_to_user",
                        lambda db, uid, title, body, url="/chat", tag=None: sent.append((uid, tag)) or 1)
    db = db_factory()
    s = _mk(db)

    # 1틱: 최초 발견 — API가 접수 푸시를 이미 보냈으므로 재푸시 안 함(대기 등록만)
    scheduler._run_consult_request_renotify()
    assert sent == []
    # 2틱(45초 경과 시뮬): 재푸시 발생 + consult-request 태그
    scheduler._consult_repush[s.id] -= 46
    scheduler._run_consult_request_renotify()
    assert sent == [(77, "consult-request")]
    # 45초 미만이면 재푸시 없음
    scheduler._run_consult_request_renotify()
    assert len(sent) == 1
    # 수락됨 → 추적 종료·재푸시 중지
    s2 = db.query(ConsultationSession).first()
    s2.status = "accepted"; db.commit()
    scheduler._consult_repush[s.id] = time.time() - 100
    scheduler._run_consult_request_renotify()
    assert len(sent) == 1
    assert s.id not in scheduler._consult_repush


def test_renotify_respects_15min_cap(db_factory, monkeypatch):
    from backend.app.services import scheduler
    sent = []
    monkeypatch.setattr("backend.app.services.push_service.send_to_user",
                        lambda *a, **k: sent.append(1) or 1)
    db = db_factory()
    _mk(db, minutes_ago=20)   # 15분 상한 초과 — 재푸시 대상 아님
    scheduler._run_consult_request_renotify()
    scheduler._run_consult_request_renotify()
    assert sent == []
