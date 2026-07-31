"""Baseline (no-op): 기존 create_all로 만들어진 스키마를 alembic이 인식하도록 stamp.

신규 환경에선 이 리비전 적용 후 후속 마이그레이션을 받는다.
기존 환경에선 `alembic stamp 20260601_0000_baseline` 으로 베이스라인 처리.
"""
from __future__ import annotations

from alembic import op  # noqa: F401
import sqlalchemy as sa  # noqa: F401


revision: str = "20260601_0000_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
