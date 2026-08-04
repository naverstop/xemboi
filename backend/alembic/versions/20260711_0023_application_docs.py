"""입점 신청 서류 첨부(사업자등록증·증빙) — docs_json 컬럼(운영자 지시). 멱등 DDL."""
from __future__ import annotations

from alembic import op


revision: str = "20260711_0023_application_docs"
down_revision = "20260711_0022_consultant_applications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE consultant_applications ADD COLUMN IF NOT EXISTS docs_json TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE consultant_applications DROP COLUMN IF EXISTS docs_json")
