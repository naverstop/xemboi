"""입점 문의(신청 전 게이트) 테이블 — 운영자 확정 2026-07-12.

푸터 '입점 문의' → 회원 메일 ID로 접수 → 관리자 [신청 허용] 후에만 입점 신청서 작성 가능.

Revision ID: 20260712_0024
Revises: 20260711_0023
Create Date: 2026-07-12
"""
from alembic import op

revision = "20260712_0024_partner_inquiries"
down_revision = "20260711_0023_application_docs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS partner_inquiries (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
            email VARCHAR(255) NOT NULL,
            note TEXT,
            status VARCHAR(12) NOT NULL DEFAULT 'pending',
            decide_note VARCHAR(300),
            decided_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_partner_inquiries_user_id ON partner_inquiries (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_partner_inquiries_email ON partner_inquiries (email)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_partner_inquiries_status ON partner_inquiries (status)")
    # 이메일당 진행 중(pending) 문의 1건 — check-then-insert 동시성 우회(TOCTOU) DB 백스톱
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_partner_inquiries_email_pending "
        "ON partner_inquiries (email) WHERE status = 'pending'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS partner_inquiries")
