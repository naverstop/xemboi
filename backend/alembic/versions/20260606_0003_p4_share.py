"""P4: users.share_used_count 컬럼 추가.

신규 테이블(saju_profiles)은 create_all 로 생성되므로 여기서는 users 컬럼 ALTER 만 멱등 수행한다.
"""
from __future__ import annotations

from alembic import op


revision: str = "20260606_0003_p4_share"
down_revision = "20260606_0002_p3_membership"
branch_labels = None
depends_on = None


_UPGRADE_SQL = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS share_used_count INTEGER NOT NULL DEFAULT 0",
]

_DOWNGRADE_SQL = [
    "ALTER TABLE users DROP COLUMN IF EXISTS share_used_count",
]


def upgrade() -> None:
    for sql in _UPGRADE_SQL:
        op.execute(sql)


def downgrade() -> None:
    for sql in _DOWNGRADE_SQL:
        op.execute(sql)
