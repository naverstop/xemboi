"""이중 로케일(ko/vi) — 사용자·세션·프로필에 locale 컬럼 추가.

베트남 서비스(locale=vi)와 한국 서비스(locale=ko)가 한 코드베이스를 공유하되 언어·역법·독음이
로케일로 갈린다. 기존 행은 DEFAULT 'ko' 로 백필 → 한국 서비스 무영향(불변). 멱등(IF NOT EXISTS).
create_all 은 기존 테이블에 컬럼을 추가하지 않으므로 이 마이그레이션(및 main.py 멱등 ALTER)로 보강.
설계: [[vietnam-dual-locale-plan]].
"""
from __future__ import annotations

from alembic import op


revision: str = "20260731_0015_locale"
down_revision = "20260704_0014_consult_rating"
branch_labels = None
depends_on = None

# 로케일 컬럼을 붙일 테이블 — 사용자 선호 + 익명 세션(회원 없이도 언어 유지)까지.
_TABLES = (
    "users",
    "chat_sessions",
    "saju_profiles",
    "compat_sessions",
    "tool_sessions",
    "tarot_sessions",
    "consultation_sessions",
)


def upgrade() -> None:
    for t in _TABLES:
        op.execute(
            f"ALTER TABLE {t} ADD COLUMN IF NOT EXISTS locale VARCHAR(2) NOT NULL DEFAULT 'ko'"
        )


def downgrade() -> None:
    for t in _TABLES:
        op.execute(f"ALTER TABLE {t} DROP COLUMN IF EXISTS locale")
