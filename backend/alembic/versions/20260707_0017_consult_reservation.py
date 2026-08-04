"""A-2 상담 예약제 — 상담사 슬롯(consultation_slots) + 세션의 예약 출처(reservation_id).

예약은 선결제(홀드): 예약 시 차감, 취소 정책(시작 N시간 전 100%/이후 M%)·상담사 취소/노쇼 100% 환불.
시각 도래 시 예약 드라이버가 세션을 자동 생성(requested)하고 양측에 웹푸시. 멱등 DDL.
"""
from __future__ import annotations

from alembic import op


revision: str = "20260707_0017_consult_reserve"
down_revision = "20260707_0016_consult_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS consultation_slots (
            id VARCHAR(64) PRIMARY KEY,
            consultant_id BIGINT NOT NULL REFERENCES consultants(id) ON DELETE CASCADE,
            start_at TIMESTAMP NOT NULL,
            duration_min INTEGER NOT NULL DEFAULT 30,
            status VARCHAR(12) NOT NULL DEFAULT 'open',
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
            booked_at TIMESTAMP,
            consent_at TIMESTAMP,
            price_p INTEGER NOT NULL DEFAULT 0,
            commission_pct INTEGER,
            charged_p INTEGER NOT NULL DEFAULT 0,
            refunded BOOLEAN NOT NULL DEFAULT FALSE,
            refund_p INTEGER NOT NULL DEFAULT 0,
            reminder_sent BOOLEAN NOT NULL DEFAULT FALSE,
            session_id VARCHAR(64)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_consultation_slots_consultant_id ON consultation_slots (consultant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_consultation_slots_start_at ON consultation_slots (start_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_consultation_slots_status ON consultation_slots (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_consultation_slots_user_id ON consultation_slots (user_id)")
    op.execute("ALTER TABLE consultation_sessions ADD COLUMN IF NOT EXISTS reservation_id VARCHAR(64)")


def downgrade() -> None:
    op.execute("ALTER TABLE consultation_sessions DROP COLUMN IF EXISTS reservation_id")
    op.execute("DROP TABLE IF EXISTS consultation_slots")
