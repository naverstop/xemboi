"""5.1: 연간회원 무과금 사용횟수 카운터(membership_used_count) 추가.

연간회원(Level2)은 멤버십 기간 내 settings.membership_annual_quota(기본 1,000)회까지
무과금 사용, 소진 시 차단(갱신 유도). 멤버십 갱신/신규 시 0으로 리셋.
"""
from __future__ import annotations

from alembic import op


revision: str = "20260606_0004_annual_quota"
down_revision = "20260606_0003_p4_share"
branch_labels = None
depends_on = None


_UPGRADE_SQL = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS membership_used_count INTEGER NOT NULL DEFAULT 0",
]

_DOWNGRADE_SQL = [
    "ALTER TABLE users DROP COLUMN IF EXISTS membership_used_count",
]


def upgrade() -> None:
    for sql in _UPGRADE_SQL:
        op.execute(sql)


def downgrade() -> None:
    for sql in _DOWNGRADE_SQL:
        op.execute(sql)
