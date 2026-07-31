"""본인 사주 기본 프로필(saju_profile) 컬럼 추가.

로그인 사용자가 재입력 없이 본인 사주를 자동으로 불러오도록 users 테이블에
JSON 텍스트 컬럼 추가. 멱등(IF NOT EXISTS).
"""
from __future__ import annotations

from alembic import op


revision: str = "20260609_0007_saju_profile"
down_revision = "20260606_0006_tools"
branch_labels = None
depends_on = None


_UPGRADE_SQL = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS saju_profile TEXT",
]
_DOWNGRADE_SQL = [
    "ALTER TABLE users DROP COLUMN IF EXISTS saju_profile",
]


def upgrade() -> None:
    for sql in _UPGRADE_SQL:
        op.execute(sql)


def downgrade() -> None:
    for sql in _DOWNGRADE_SQL:
        op.execute(sql)
