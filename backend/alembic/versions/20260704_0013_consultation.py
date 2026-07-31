"""1:1 인적 상담(입점업체) — consultants / consultation_sessions / messages / settlements.

입점업체 상담사↔사용자 실시간 채팅 상담 기능의 스키마. 신규 테이블은 create_all 로도
생성되지만 Alembic 관리용으로 멱등 정의(CREATE TABLE IF NOT EXISTS). 설계: [[consultation-1on1-plan]].
"""
from __future__ import annotations

from alembic import op


revision: str = "20260704_0013_consultation"
down_revision = "20260704_0012_tarot_overrides"
branch_labels = None
depends_on = None


_UPGRADE_SQL = [
    """
    CREATE TABLE IF NOT EXISTS consultants (
        id BIGSERIAL PRIMARY KEY,
        login_email VARCHAR(255) NOT NULL,
        user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
        business_name VARCHAR(120) NOT NULL,
        specialty VARCHAR(8) NOT NULL DEFAULT 'saju',
        signboard_image_url VARCHAR(512),
        intro TEXT,
        rate_p INTEGER,
        duration_min INTEGER,
        commission_pct INTEGER,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        presence VARCHAR(8) NOT NULL DEFAULT 'offline',
        last_seen_at TIMESTAMP,
        sort_order INTEGER NOT NULL DEFAULT 100,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        updated_at TIMESTAMP NOT NULL DEFAULT now(),
        CONSTRAINT uq_consultants_login_email UNIQUE (login_email)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_consultants_login_email ON consultants (login_email)",
    "CREATE INDEX IF NOT EXISTS ix_consultants_user_id ON consultants (user_id)",
    """
    CREATE TABLE IF NOT EXISTS consultation_sessions (
        id VARCHAR(64) PRIMARY KEY,
        user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
        consultant_id BIGINT NOT NULL REFERENCES consultants(id) ON DELETE CASCADE,
        specialty VARCHAR(8) NOT NULL DEFAULT 'saju',
        status VARCHAR(16) NOT NULL DEFAULT 'requested',
        price_p INTEGER NOT NULL DEFAULT 0,
        duration_min INTEGER NOT NULL DEFAULT 0,
        extended_min INTEGER NOT NULL DEFAULT 0,
        consent_at TIMESTAMP,
        requested_at TIMESTAMP NOT NULL DEFAULT now(),
        accepted_at TIMESTAMP,
        started_at TIMESTAMP,
        ended_at TIMESTAMP,
        elapsed_sec INTEGER NOT NULL DEFAULT 0,
        credits_charged INTEGER NOT NULL DEFAULT 0,
        refund_p INTEGER NOT NULL DEFAULT 0,
        refunded BOOLEAN NOT NULL DEFAULT FALSE,
        pdf_token VARCHAR(64),
        purge_after TIMESTAMP,
        purged BOOLEAN NOT NULL DEFAULT FALSE
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_consultation_sessions_user_id ON consultation_sessions (user_id)",
    "CREATE INDEX IF NOT EXISTS ix_consultation_sessions_consultant_id ON consultation_sessions (consultant_id)",
    "CREATE INDEX IF NOT EXISTS ix_consultation_sessions_status ON consultation_sessions (status)",
    "CREATE INDEX IF NOT EXISTS ix_consultation_sessions_purge_after ON consultation_sessions (purge_after)",
    """
    CREATE TABLE IF NOT EXISTS consultation_messages (
        id BIGSERIAL PRIMARY KEY,
        session_id VARCHAR(64) NOT NULL REFERENCES consultation_sessions(id) ON DELETE CASCADE,
        sender VARCHAR(12) NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_consultation_messages_session_id ON consultation_messages (session_id)",
    """
    CREATE TABLE IF NOT EXISTS consultation_settlements (
        id BIGSERIAL PRIMARY KEY,
        session_id VARCHAR(64) NOT NULL REFERENCES consultation_sessions(id) ON DELETE CASCADE,
        consultant_id BIGINT NOT NULL REFERENCES consultants(id) ON DELETE CASCADE,
        revenue_p INTEGER NOT NULL DEFAULT 0,
        commission_pct INTEGER NOT NULL DEFAULT 0,
        commission_p INTEGER NOT NULL DEFAULT 0,
        taxable_p INTEGER NOT NULL DEFAULT 0,
        tax_pct DOUBLE PRECISION NOT NULL DEFAULT 0,
        tax_p INTEGER NOT NULL DEFAULT 0,
        payout_p INTEGER NOT NULL DEFAULT 0,
        status VARCHAR(12) NOT NULL DEFAULT 'pending',
        settled_at TIMESTAMP,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        CONSTRAINT uq_consultation_settlements_session UNIQUE (session_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_consultation_settlements_consultant_id ON consultation_settlements (consultant_id)",
    "CREATE INDEX IF NOT EXISTS ix_consultation_settlements_status ON consultation_settlements (status)",
]

_DOWNGRADE_SQL = [
    "DROP TABLE IF EXISTS consultation_settlements",
    "DROP TABLE IF EXISTS consultation_messages",
    "DROP TABLE IF EXISTS consultation_sessions",
    "DROP TABLE IF EXISTS consultants",
]


def upgrade() -> None:
    for sql in _UPGRADE_SQL:
        op.execute(sql)


def downgrade() -> None:
    for sql in _DOWNGRADE_SQL:
        op.execute(sql)
