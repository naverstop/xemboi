"""타로 카드 해석/키워드 관리자 편집 오버레이 — tarot_card_overrides.

정적 덱(backend/app/data/tarot_deck_kr.json)은 시드/기본값으로 두고, 관리자가 수시로 수정하는
키워드(정/역)·해석 서술(interp_up/rev)만 code 단위로 이 테이블에 저장(오버레이). row 가 없으면
JSON 시드 그대로 사용. 카드명·방향·이미지 등 구조 필드는 JSON 이 단일 소스(편집 불가).
신규 테이블은 create_all 로도 생성되지만 Alembic 관리용으로 멱등 정의.
"""
from __future__ import annotations

from alembic import op


revision: str = "20260704_0012_tarot_overrides"
down_revision = "20260628_0011_encoder_used_len"
branch_labels = None
depends_on = None


_UPGRADE_SQL = [
    """
    CREATE TABLE IF NOT EXISTS tarot_card_overrides (
        code VARCHAR(24) PRIMARY KEY,
        keywords_up JSON,
        keywords_rev JSON,
        interp_up TEXT,
        interp_rev TEXT,
        updated_at TIMESTAMP NOT NULL DEFAULT now(),
        updated_by BIGINT
    )
    """,
]

_DOWNGRADE_SQL = [
    "DROP TABLE IF EXISTS tarot_card_overrides",
]


def upgrade() -> None:
    for sql in _UPGRADE_SQL:
        op.execute(sql)


def downgrade() -> None:
    for sql in _DOWNGRADE_SQL:
        op.execute(sql)
