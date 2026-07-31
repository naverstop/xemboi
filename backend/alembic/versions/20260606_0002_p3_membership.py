"""P3/P4: users 회원등급·무료한도·방언·멤버십 컬럼 추가.

신규 테이블(app_settings / answer_templates / message_feedback / push_subscriptions)은
create_all 로 생성되므로 여기서는 users 컬럼 ALTER 만 멱등 수행한다.
"""
from __future__ import annotations

from alembic import op


revision: str = "20260606_0002_p3_membership"
down_revision = "20260602_0001_startup_ddl"
branch_labels = None
depends_on = None


_UPGRADE_SQL = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS level INTEGER",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS free_used_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS answer_dialect VARCHAR(16) NOT NULL DEFAULT 'standard'",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS membership_expires_at TIMESTAMP",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_premium BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS first_paid_at TIMESTAMP",
]

_DOWNGRADE_SQL = [
    "ALTER TABLE users DROP COLUMN IF EXISTS level",
    "ALTER TABLE users DROP COLUMN IF EXISTS free_used_count",
    "ALTER TABLE users DROP COLUMN IF EXISTS answer_dialect",
    "ALTER TABLE users DROP COLUMN IF EXISTS membership_expires_at",
    "ALTER TABLE users DROP COLUMN IF EXISTS is_premium",
    "ALTER TABLE users DROP COLUMN IF EXISTS first_paid_at",
]


def upgrade() -> None:
    for sql in _UPGRADE_SQL:
        op.execute(sql)


def downgrade() -> None:
    for sql in _DOWNGRADE_SQL:
        op.execute(sql)
