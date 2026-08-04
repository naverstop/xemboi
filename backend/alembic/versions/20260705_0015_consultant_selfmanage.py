"""상담사 자율설정 — #키워드·분당/시간당 요금·입점예정 상태·셀프편집 잠금 + 세션 수수료 스냅샷.

상담사가 스스로 요금(세션/분/시간)·간판·#키워드를 관리하고, '입점예정(coming_soon)'을 카드에 노출하기
위한 consultants 컬럼 + 정산 수수료를 요청 시 고정하는 consultation_sessions.commission_pct.
멱등(ADD COLUMN IF NOT EXISTS). create_all 은 기존 테이블에 컬럼을 추가하지 않으므로 이 마이그레이션
(및 main.py 기동 시 멱등 ALTER)로 보강한다. 설계: [[consultation-1on1-plan]].
"""
from __future__ import annotations

from alembic import op


revision: str = "20260705_0015_consultant_self"
down_revision = "20260704_0014_consult_rating"
branch_labels = None
depends_on = None


_COLS = (
    "ADD COLUMN IF NOT EXISTS keywords TEXT",
    "ADD COLUMN IF NOT EXISTS price_unit VARCHAR(8) NOT NULL DEFAULT 'session'",
    "ADD COLUMN IF NOT EXISTS per_min_p INTEGER",
    "ADD COLUMN IF NOT EXISTS per_hour_p INTEGER",
    "ADD COLUMN IF NOT EXISTS status VARCHAR(12) NOT NULL DEFAULT 'active'",
    "ADD COLUMN IF NOT EXISTS self_managed BOOLEAN NOT NULL DEFAULT TRUE",
)
_DROPS = ("keywords", "price_unit", "per_min_p", "per_hour_p", "status", "self_managed")


def upgrade() -> None:
    for clause in _COLS:
        op.execute(f"ALTER TABLE consultants {clause}")
    # 정산 수수료 스냅샷(요청 시 고정)
    op.execute("ALTER TABLE consultation_sessions ADD COLUMN IF NOT EXISTS commission_pct INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE consultation_sessions DROP COLUMN IF EXISTS commission_pct")
    for col in _DROPS:
        op.execute(f"ALTER TABLE consultants DROP COLUMN IF EXISTS {col}")
