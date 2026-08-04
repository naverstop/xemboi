"""B-10 궁합 상대 초대 — 7일 만료 초대 링크 + 등급 티저. 멱등 DDL."""
from __future__ import annotations

from alembic import op


revision: str = "20260707_0020_compat_invites"
down_revision = "20260707_0019_user_passes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS compat_invites (
            id BIGSERIAL PRIMARY KEY,
            token VARCHAR(32) NOT NULL UNIQUE,
            inviter_user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            inviter_name VARCHAR(32) NOT NULL DEFAULT '익명',
            a_birth_json TEXT NOT NULL,
            b_birth_json TEXT,
            status VARCHAR(12) NOT NULL DEFAULT 'pending',
            teaser_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            expires_at TIMESTAMP NOT NULL,
            accepted_at TIMESTAMP
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_compat_invites_inviter ON compat_invites (inviter_user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_compat_invites_status ON compat_invites (status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS compat_invites")
