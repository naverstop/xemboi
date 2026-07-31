"""면책고지 동의(최초 1회) 기록 컬럼 추가.

로그인 사용자가 면책고지에 동의한 시각·버전을 users 테이블에 기록(법적효력).
멱등(IF NOT EXISTS).
"""
from __future__ import annotations

from alembic import op


revision: str = "20260609_0008_disclaimer_agree"
down_revision = "20260609_0007_saju_profile"
branch_labels = None
depends_on = None


_UPGRADE_SQL = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS disclaimer_agreed_at TIMESTAMP",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS disclaimer_agreed_version VARCHAR(32)",
]
_DOWNGRADE_SQL = [
    "ALTER TABLE users DROP COLUMN IF EXISTS disclaimer_agreed_at",
    "ALTER TABLE users DROP COLUMN IF EXISTS disclaimer_agreed_version",
]


def upgrade() -> None:
    for sql in _UPGRADE_SQL:
        op.execute(sql)


def downgrade() -> None:
    for sql in _DOWNGRADE_SQL:
        op.execute(sql)
