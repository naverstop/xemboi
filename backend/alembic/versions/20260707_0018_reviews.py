"""B-3 이용 후기 — 수집(회원)→관리자 승인→공개 노출. 표시명은 저장 시점 마스킹 스냅샷. 멱등 DDL."""
from __future__ import annotations

from alembic import op


revision: str = "20260707_0018_reviews"
down_revision = "20260707_0017_consult_reserve"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
            source VARCHAR(16) NOT NULL DEFAULT 'chat',
            content TEXT NOT NULL,
            rating INTEGER NOT NULL DEFAULT 5,
            display_name VARCHAR(32) NOT NULL DEFAULT '익명',
            status VARCHAR(12) NOT NULL DEFAULT 'pending',
            reward_granted INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_reviews_user_id ON reviews (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reviews_source ON reviews (source)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reviews_status ON reviews (status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reviews")
