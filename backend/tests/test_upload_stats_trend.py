"""업로드 학습성과 통계 — 14일 추세의 '일별 청크 수' 집계 테스트.

청크 수가 핵심 지표라, 추세 그래프가 일별 파일 건수뿐 아니라 일별 색인 청크 수도
제공하는지 검증한다. Qdrant/스냅샷 의존부는 monkeypatch 로 차단.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.repositories.models import Base
import backend.app.repositories.upload_models  # noqa: F401
from backend.app.repositories.upload_models import Upload
from backend.app.services import upload_service


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = S()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _add(db, *, sha, chunks, indexed_at, status="indexed", kind="pdf"):
    row = Upload(
        title="t", category="user_upload", file_kind=kind, original_name="x",
        stored_path="p", size_bytes=1, sha256=sha, status=status,
        indexed_at=indexed_at, chunks_count=chunks,
    )
    db.add(row)
    db.commit()
    return row


def test_stats_trend_has_daily_chunks(db, monkeypatch):
    monkeypatch.setattr(upload_service, "corpus_chunk_count", lambda: 999)
    monkeypatch.setattr(upload_service, "record_corpus_snapshot", lambda *a, **k: None)
    monkeypatch.setattr(upload_service, "monthly_chunks", lambda: [])

    now = datetime.utcnow()
    yesterday = now - timedelta(days=1)
    _add(db, sha="a", chunks=10, indexed_at=now)
    _add(db, sha="b", chunks=5, indexed_at=now)
    _add(db, sha="c", chunks=7, indexed_at=yesterday)
    _add(db, sha="d", chunks=None, indexed_at=None, status="approved")  # 미색인 → 추세 제외

    out = upload_service.stats(db)
    trend = {t["date"]: t for t in out["trend"]}
    td = now.date().isoformat()
    yd = yesterday.date().isoformat()

    # 일별 파일 건수 + 청크 수 둘 다 집계
    assert trend[td]["indexed"] == 2
    assert trend[td]["chunks"] == 15      # 10 + 5
    assert trend[yd]["indexed"] == 1
    assert trend[yd]["chunks"] == 7
    # 색인 안 된(approved) 건은 추세/색인완료에 안 잡힘
    assert out["indexed_count"] == 3
    assert len(out["trend"]) == 14
