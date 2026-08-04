"""관리자 '현재 통계' — 익명 기기 heartbeat(usage_devices) + 일별 사용 집계(usage_daily). 멱등 DDL."""
from __future__ import annotations

from alembic import op


revision: str = "20260711_0021_usage_stats"
down_revision = "20260707_0020_compat_invites"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_devices (
            device_id VARCHAR(36) PRIMARY KEY,
            platform VARCHAR(16) NOT NULL DEFAULT 'other',
            is_pwa BOOLEAN NOT NULL DEFAULT FALSE,
            first_seen TIMESTAMP NOT NULL DEFAULT now(),
            last_seen TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_usage_devices_last_seen ON usage_devices(last_seen)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS usage_daily (
            id BIGSERIAL PRIMARY KEY,
            day DATE NOT NULL,
            kind VARCHAR(8) NOT NULL,
            key VARCHAR(64) NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT uq_usage_daily UNIQUE (day, kind, key)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_usage_daily_day ON usage_daily(day)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS usage_daily")
    op.execute("DROP TABLE IF EXISTS usage_devices")
