"""RAG 검색 점수 로그 테이블 (일일 질문 인사이트 — 코퍼스 갭 분석용).

질문별 Qdrant top-k 점수를 남겨, max_score가 낮은 질문 군집 = 학습자료 미커버
주제를 일일 배치(scripts/daily_question_insight.py)가 찾아낸다. 멱등(IF NOT EXISTS).
"""
from __future__ import annotations

from alembic import op


revision: str = "20260612_0009_retrieval_logs"
down_revision = "20260609_0008_disclaimer_agree"
branch_labels = None
depends_on = None


_UPGRADE_SQL = [
    """
    CREATE TABLE IF NOT EXISTS retrieval_logs (
        id BIGSERIAL PRIMARY KEY,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        session_id VARCHAR(64),
        question TEXT NOT NULL,
        top_k INTEGER NOT NULL DEFAULT 0,
        max_score DOUBLE PRECISION NOT NULL DEFAULT 0,
        avg_score DOUBLE PRECISION NOT NULL DEFAULT 0,
        results_json JSON
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_retrieval_logs_created_at ON retrieval_logs (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_retrieval_logs_session_id ON retrieval_logs (session_id)",
]
_DOWNGRADE_SQL = [
    "DROP TABLE IF EXISTS retrieval_logs",
]


def upgrade() -> None:
    for sql in _UPGRADE_SQL:
        op.execute(sql)


def downgrade() -> None:
    for sql in _DOWNGRADE_SQL:
        op.execute(sql)
