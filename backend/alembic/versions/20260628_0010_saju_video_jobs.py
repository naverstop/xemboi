"""사주 답변 → 1분 쇼츠 영상 생성 작업 테이블 (부록 C-3).

chat(사주) 전용. 클릭 즉시 20,000P 차감 + 실패 멱등 환불(refunded), 48h 보관 후 삭제.
멱등(IF NOT EXISTS). 이중발행(이중차감) 차단을 위한 부분 유니크 인덱스 포함.
"""
from __future__ import annotations

from alembic import op


revision: str = "20260628_0010_saju_video_jobs"
down_revision = "20260612_0009_retrieval_logs"
branch_labels = None
depends_on = None


_UPGRADE_SQL = [
    """
    CREATE TABLE IF NOT EXISTS saju_video_jobs (
        id BIGSERIAL PRIMARY KEY,
        job_token VARCHAR(32) NOT NULL UNIQUE,
        session_id VARCHAR(64) NOT NULL REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
        message_id INTEGER NOT NULL,
        user_id INTEGER,
        status VARCHAR(16) NOT NULL DEFAULT 'queued',
        stage VARCHAR(24),
        progress_pct INTEGER NOT NULL DEFAULT 0,
        detail TEXT,
        aspect VARCHAR(8) NOT NULL DEFAULT '9x16',
        scenario_json JSON,
        master_path TEXT,
        delivery_path TEXT,
        encoder_used VARCHAR(8),
        gpu_gate_fallback BOOLEAN NOT NULL DEFAULT FALSE,
        credits_charged INTEGER NOT NULL DEFAULT 0,
        refunded BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        completed_at TIMESTAMP,
        expires_at TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_svj_user ON saju_video_jobs (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_svj_retention ON saju_video_jobs (status, expires_at)",
    # 동일 답변 중복 발행(이중 20000P 차감) 차단: 활성(queued/running) job은 message_id당 1건
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ix_svj_active_dedup
        ON saju_video_jobs (message_id)
        WHERE status IN ('queued', 'running')
    """,
]
_DOWNGRADE_SQL = [
    "DROP TABLE IF EXISTS saju_video_jobs",
]


def upgrade() -> None:
    for sql in _UPGRADE_SQL:
        op.execute(sql)


def downgrade() -> None:
    for sql in _DOWNGRADE_SQL:
        op.execute(sql)
