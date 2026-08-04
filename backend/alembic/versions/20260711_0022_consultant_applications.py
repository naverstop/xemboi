"""입점 신청서 — 신청·심사 이력 + 클릭랩 동의 증빙 스냅샷(운영자 지시 2026-07-11). 멱등 DDL."""
from __future__ import annotations

from alembic import op


revision: str = "20260711_0022_consultant_applications"
down_revision = "20260711_0021_usage_stats"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS consultant_applications (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
            email VARCHAR(255) NOT NULL,
            specialty VARCHAR(8) NOT NULL DEFAULT 'saju',
            business_name VARCHAR(120) NOT NULL,
            contact VARCHAR(64),
            intro TEXT,
            terms_version VARCHAR(16) NOT NULL,
            terms_sha256 VARCHAR(64) NOT NULL,
            terms_text TEXT NOT NULL,
            agreed_at TIMESTAMP NOT NULL DEFAULT now(),
            agreed_ip VARCHAR(64),
            status VARCHAR(12) NOT NULL DEFAULT 'pending',
            reviewed_at TIMESTAMP,
            reject_reason VARCHAR(300),
            consultant_id BIGINT,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_capp_status ON consultant_applications(status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_capp_email ON consultant_applications(email)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS consultant_applications")
