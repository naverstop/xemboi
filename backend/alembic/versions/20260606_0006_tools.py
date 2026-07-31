"""명리 도구(작명/개명/아호/택일) 테이블 — tool_sessions / tool_messages.

신규 테이블은 create_all 로도 생성되지만 Alembic 관리용으로 멱등 정의.
naming/taekil 공용 단일 세션 테이블(tool 컬럼으로 구분).
"""
from __future__ import annotations

from alembic import op


revision: str = "20260606_0006_tools"
down_revision = "20260606_0005_compatibility"
branch_labels = None
depends_on = None


_UPGRADE_SQL = [
    """
    CREATE TABLE IF NOT EXISTS tool_sessions (
        tool_id VARCHAR(64) PRIMARY KEY,
        tool VARCHAR(16) NOT NULL,
        kind VARCHAR(24) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        user_id BIGINT,
        birth_date DATE NOT NULL,
        birth_time TIME,
        calendar VARCHAR(16) NOT NULL DEFAULT 'solar',
        is_leap_month BOOLEAN NOT NULL DEFAULT FALSE,
        gender VARCHAR(8) NOT NULL DEFAULT 'male',
        apply_true_solar_time BOOLEAN NOT NULL DEFAULT FALSE,
        chart_json JSON,
        input_json JSON,
        result_json JSON,
        is_preview BOOLEAN NOT NULL DEFAULT FALSE,
        credits_charged INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_tool_sessions_user_id ON tool_sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS ix_tool_sessions_tool ON tool_sessions(tool)",
    """
    CREATE TABLE IF NOT EXISTS tool_messages (
        id BIGSERIAL PRIMARY KEY,
        tool_id VARCHAR(64) NOT NULL
            REFERENCES tool_sessions(tool_id) ON DELETE CASCADE,
        role VARCHAR(16) NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        is_preview BOOLEAN NOT NULL DEFAULT FALSE,
        preview_revealed BOOLEAN NOT NULL DEFAULT FALSE,
        credits_charged INTEGER NOT NULL DEFAULT 0,
        reveal_credits_charged INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_tool_messages_tool_id ON tool_messages(tool_id)",
]

_DOWNGRADE_SQL = [
    "DROP TABLE IF EXISTS tool_messages",
    "DROP TABLE IF EXISTS tool_sessions",
]


def upgrade() -> None:
    for sql in _UPGRADE_SQL:
        op.execute(sql)


def downgrade() -> None:
    for sql in _DOWNGRADE_SQL:
        op.execute(sql)
