"""A-1 상담 컨텍스트 자동 전달 — 접수 시 사주 명식/타로 카드 스냅샷을 세션에 저장.

상담사가 채팅방 입장 즉시 요청자의 명식표(사주) 또는 뽑은 카드(타로)를 보게 하여 중복 질문을 없앤다.
스냅샷은 PII 이므로 7일 파기 배치에서 source_context 를 함께 마스킹한다.
멱등(ADD COLUMN IF NOT EXISTS). main.py 기동 시 멱등 ALTER 와 동일 내용.
"""
from __future__ import annotations

from alembic import op


revision: str = "20260707_0016_consult_source"
down_revision = "20260705_0015_consultant_self"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE consultation_sessions ADD COLUMN IF NOT EXISTS source_kind VARCHAR(8)")
    op.execute("ALTER TABLE consultation_sessions ADD COLUMN IF NOT EXISTS source_context JSON")


def downgrade() -> None:
    op.execute("ALTER TABLE consultation_sessions DROP COLUMN IF EXISTS source_context")
    op.execute("ALTER TABLE consultation_sessions DROP COLUMN IF EXISTS source_kind")
