"""B-7 월 패스 — 포인트 자동차감형(지연 갱신). 멱등 DDL."""
from __future__ import annotations

from alembic import op


revision: str = "20260707_0019_user_passes"
down_revision = "20260707_0018_reviews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS user_passes (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            tier VARCHAR(8) NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            auto_renew BOOLEAN NOT NULL DEFAULT TRUE,
            started_at TIMESTAMP NOT NULL DEFAULT now(),
            current_start TIMESTAMP NOT NULL DEFAULT now(),
            next_renewal_at TIMESTAMP NOT NULL,
            price_p INTEGER NOT NULL DEFAULT 0,
            free_basic_used INTEGER NOT NULL DEFAULT 0,
            amulet_used INTEGER NOT NULL DEFAULT 0,
            canceled_at TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_user_passes_next_renewal_at ON user_passes (next_renewal_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_passes")
