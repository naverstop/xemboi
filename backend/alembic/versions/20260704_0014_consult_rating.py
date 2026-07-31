"""1:1 상담 세션에 사용자 만족도 평점(rating) 컬럼 추가 — 간판 만족도 집계용.

멱등(ADD COLUMN IF NOT EXISTS). create_all 은 기존 테이블에 컬럼을 추가하지 않으므로 이 마이그레이션
(및 main.py 기동 시 멱등 ALTER)로 보강한다. 설계: [[consultation-1on1-plan]].
"""
from __future__ import annotations

from alembic import op


revision: str = "20260704_0014_consult_rating"
down_revision = "20260704_0013_consultation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE consultation_sessions ADD COLUMN IF NOT EXISTS rating INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE consultation_sessions DROP COLUMN IF EXISTS rating")
