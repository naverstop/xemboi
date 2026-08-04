"""관리자 '현재 통계' — usage beat 수집 + admin 요약 (2026-07-11)."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.repositories.models import Base
# usage_summary의 실사용 집계가 참조하는 전 모델을 Base에 등록(create_all 포함되게)
from backend.app.repositories import auth_models  # noqa: F401
from backend.app.repositories import consultation_models  # noqa: F401
from backend.app.api.usage import usage_beat, BeatIn, BeatEvent
from backend.app.api.admin import usage_summary
from backend.app.repositories.usage_models import UsageDaily, UsageDevice


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


def _beat(db, dev, platform="ios", standalone=False, events=None):
    body = BeatIn(device_id=dev, platform=platform, standalone=standalone,
                  events=[BeatEvent(**e) for e in (events or [])])
    return usage_beat(body, db)


def test_beat_creates_device_and_counters(db):
    dev = str(uuid.uuid4())
    r = _beat(db, dev, platform="ios", standalone=True,
              events=[{"kind": "page", "key": "today"}, {"kind": "click", "key": "today:cta"}])
    assert r["ok"] is True
    d = db.get(UsageDevice, dev)
    assert d is not None and d.platform == "ios" and d.is_pwa is True
    rows = {(x.kind, x.key): x.count for x in db.query(UsageDaily).all()}
    assert rows[("page", "today")] == 1
    assert rows[("click", "today:cta")] == 1


def test_beat_increments_and_pwa_ratchet(db):
    dev = str(uuid.uuid4())
    _beat(db, dev, standalone=True)
    _beat(db, dev, standalone=False,
          events=[{"kind": "page", "key": "chat", "n": 2}, {"kind": "page", "key": "chat"}])
    d = db.get(UsageDevice, dev)
    assert d.is_pwa is True                      # 래칫: 한 번 standalone이면 유지
    row = db.query(UsageDaily).filter_by(kind="page", key="chat").first()
    assert row.count == 3


def test_beat_rejects_bad_device_and_key(db):
    assert _beat(db, "N" * 36)["ok"] is False    # 36자여도 uuid 형식 아니면 거부(regex)
    dev = str(uuid.uuid4())
    _beat(db, dev, events=[{"kind": "page", "key": "잘못된키!"}])   # 화이트리스트 밖 → 무시
    assert db.query(UsageDaily).count() == 0


def test_usage_summary_aggregates(db):
    a, b, c = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    _beat(db, a, platform="ios", standalone=True, events=[{"kind": "page", "key": "today"}])
    _beat(db, b, platform="android", standalone=True, events=[{"kind": "page", "key": "today"}])
    _beat(db, c, platform="desktop", events=[{"kind": "click", "key": "today:cta"}])
    # c는 6분 전 접속으로 밀어 온라인 5분 창 검증
    db.get(UsageDevice, c).last_seen = datetime.now() - timedelta(minutes=6)
    db.commit()

    s = usage_summary(db)
    assert s["online_now"] == 2                  # a, b (c는 5분 밖)
    assert s["today_visitors"] == 3
    assert s["pwa"]["total"] == 2 and s["pwa"]["ios"] == 1 and s["pwa"]["android"] == 1
    menus = {m["key"]: m for m in s["menus"]}
    assert menus["today"]["today"] == 2 and menus["today"]["week"] == 2
    assert s["clicks"][0]["key"] == "today:cta"
