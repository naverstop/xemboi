"""Promote startup DDL to managed migration.

기존엔 main.py startup에서 ALTER TABLE ADD COLUMN IF NOT EXISTS 11건을 수행했다.
이를 Alembic 관리 하에 옮긴다. 이미 컬럼이 존재하는 환경에서도 IF NOT EXISTS 덕분에
멱등하게 동작한다.
"""
from __future__ import annotations

from alembic import op


revision: str = "20260602_0001_startup_ddl"
down_revision = "20260601_0000_baseline"
branch_labels = None
depends_on = None


_UPGRADE_SQL = [
    "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_id INTEGER",
    "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS preview_revealed BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS is_preview BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS credits_charged INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS reveal_credits_charged INTEGER NOT NULL DEFAULT 0",
    "CREATE INDEX IF NOT EXISTS ix_chat_sessions_user_id ON chat_sessions(user_id)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_agreed_version VARCHAR(32)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS privacy_agreed_version VARCHAR(32)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS refund_agreed_version VARCHAR(32)",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_agreed_at TIMESTAMP",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS birth_date_enc VARCHAR(255)",
]

_DOWNGRADE_SQL = [
    "DROP INDEX IF EXISTS ix_chat_sessions_user_id",
    "ALTER TABLE chat_sessions DROP COLUMN IF EXISTS user_id",
    "ALTER TABLE chat_messages DROP COLUMN IF EXISTS preview_revealed",
    "ALTER TABLE chat_messages DROP COLUMN IF EXISTS is_preview",
    "ALTER TABLE chat_messages DROP COLUMN IF EXISTS credits_charged",
    "ALTER TABLE chat_messages DROP COLUMN IF EXISTS reveal_credits_charged",
    "ALTER TABLE users DROP COLUMN IF EXISTS terms_agreed_version",
    "ALTER TABLE users DROP COLUMN IF EXISTS privacy_agreed_version",
    "ALTER TABLE users DROP COLUMN IF EXISTS refund_agreed_version",
    "ALTER TABLE users DROP COLUMN IF EXISTS terms_agreed_at",
    "ALTER TABLE users DROP COLUMN IF EXISTS birth_date_enc",
]


def upgrade() -> None:
    for sql in _UPGRADE_SQL:
        op.execute(sql)


def downgrade() -> None:
    for sql in _DOWNGRADE_SQL:
        op.execute(sql)
