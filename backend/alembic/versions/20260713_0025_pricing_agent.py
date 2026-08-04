"""마케팅 가격 에이전트 — 경쟁사 시트·가드레일·권장가 테이블. 운영자 확정 2026-07-13.

시장조사(관리자 수동 시트) → 결정적 권장가 산출 → 관리자 최종 승인(클릭) → 가격 변경.
자동 적용 없음. 설계: docs/마케팅_가격에이전트_추진계획서.md.

Revision ID: 20260713_0025
Revises: 20260712_0024
Create Date: 2026-07-13
"""
from alembic import op

revision = "20260713_0025_pricing_agent"
down_revision = "20260712_0024_partner_inquiries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS competitor_prices (
            id BIGSERIAL PRIMARY KEY,
            competitor_name VARCHAR(80) NOT NULL,
            menu_key VARCHAR(48) NOT NULL,
            price_krw INTEGER NOT NULL,
            note VARCHAR(200),
            verified_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_by VARCHAR(255),
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_competitor_prices_menu_key ON competitor_prices (menu_key)")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pricing_guardrails (
            menu_key VARCHAR(48) PRIMARY KEY,
            floor_p INTEGER NOT NULL DEFAULT 0,
            ceiling_p INTEGER NOT NULL DEFAULT 1000000,
            max_change_pct INTEGER NOT NULL DEFAULT 20,
            undercut_pct INTEGER NOT NULL DEFAULT 5,
            round_unit INTEGER NOT NULL DEFAULT 100,
            round_tail INTEGER NOT NULL DEFAULT 900,
            enabled BOOLEAN NOT NULL DEFAULT true,
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pricing_recommendations (
            id BIGSERIAL PRIMARY KEY,
            batch_id VARCHAR(32) NOT NULL,
            menu_key VARCHAR(48) NOT NULL,
            current_price INTEGER NOT NULL,
            competitor_min INTEGER,
            competitor_median INTEGER,
            recommended_price INTEGER NOT NULL,
            rationale TEXT,
            status VARCHAR(12) NOT NULL DEFAULT 'pending',
            applied_from INTEGER,
            decided_at TIMESTAMP,
            decided_by VARCHAR(255),
            created_at TIMESTAMP NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_pricing_recommendations_batch ON pricing_recommendations (batch_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pricing_recommendations_menu ON pricing_recommendations (menu_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pricing_recommendations_status ON pricing_recommendations (status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pricing_recommendations")
    op.execute("DROP TABLE IF EXISTS pricing_guardrails")
    op.execute("DROP TABLE IF EXISTS competitor_prices")
