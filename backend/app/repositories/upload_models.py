"""업로드 자료 모델 — 사용자 제출 자료 검수/색인 파이프라인.

상태 흐름:
  pending  → approve → indexed
                    ↘ reject  → rejected

전처리(텍스트 추출, MP4 자막)는 별도 단계이며,
이 모델은 메타데이터만 저장한다.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.repositories.models import Base


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 메타
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    submitter: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="user_upload")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 파일 정보
    file_kind: Mapped[str] = mapped_column(String(16), nullable=False)  # txt|pdf|mp4
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # 검수 상태
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )  # pending|approved|rejected|indexed|failed
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 색인 결과
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    indexed_source: Mapped[str | None] = mapped_column(String(255), nullable=True)  # ingest_rag 의 source 식별자
    chunks_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
