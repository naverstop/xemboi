"""업로드 리포지토리."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.repositories.upload_models import Upload


def create_upload(db: Session, **kwargs: Any) -> Upload:
    row = Upload(**kwargs)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_upload(db: Session, upload_id: int) -> Upload | None:
    return db.get(Upload, upload_id)


def list_uploads(db: Session, status: str | None = None, limit: int = 50) -> list[Upload]:
    stmt = select(Upload).order_by(Upload.id.desc()).limit(limit)
    if status:
        stmt = select(Upload).where(Upload.status == status).order_by(Upload.id.desc()).limit(limit)
    return list(db.execute(stmt).scalars().all())


def find_by_sha(db: Session, sha256: str) -> Upload | None:
    stmt = select(Upload).where(Upload.sha256 == sha256)
    return db.execute(stmt).scalar_one_or_none()


def update_review(
    db: Session,
    row: Upload,
    *,
    status: str,
    reviewer: str | None,
    comment: str | None,
) -> Upload:
    row.status = status
    row.reviewer = reviewer
    row.review_comment = comment
    row.reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


def mark_indexed(
    db: Session,
    row: Upload,
    *,
    source: str,
    chunks: int,
) -> Upload:
    row.status = "indexed"
    row.indexed_at = datetime.utcnow()
    row.indexed_source = source
    row.chunks_count = chunks
    db.commit()
    db.refresh(row)
    return row
