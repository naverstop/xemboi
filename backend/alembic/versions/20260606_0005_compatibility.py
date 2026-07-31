"""P? : 궁합(宮合) 테이블 추가 — compat_sessions / compat_messages.

신규 테이블은 create_all 로도 생성되지만(main.py), Alembic 관리 환경을 위해
멱등(CREATE TABLE IF NOT EXISTS)으로 함께 정의한다.

compat_sessions 는 요소별 근거점수(f_*)와 관법별 종합점수(total_*)를 컬럼으로
저장해, '전체 평균' 펜타곤 오버레이(궁합 본 사람들의 평균값)를 단순 AVG 집계로
산출할 수 있게 한다.
"""
from __future__ import annotations

from alembic import op


revision: str = "20260606_0005_compatibility"
down_revision = "20260606_0004_annual_quota"
branch_labels = None
depends_on = None


_UPGRADE_SQL = [
    """
    CREATE TABLE IF NOT EXISTS compat_sessions (
        compat_id VARCHAR(64) PRIMARY KEY,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        user_id BIGINT,
        a_label VARCHAR(64),
        a_birth_date DATE NOT NULL,
        a_birth_time TIME,
        a_calendar VARCHAR(16) NOT NULL DEFAULT 'solar',
        a_is_leap_month BOOLEAN NOT NULL DEFAULT FALSE,
        a_gender VARCHAR(8) NOT NULL DEFAULT 'male',
        a_apply_true_solar_time BOOLEAN NOT NULL DEFAULT FALSE,
        a_chart_json JSON,
        b_label VARCHAR(64),
        b_birth_date DATE NOT NULL,
        b_birth_time TIME,
        b_calendar VARCHAR(16) NOT NULL DEFAULT 'solar',
        b_is_leap_month BOOLEAN NOT NULL DEFAULT FALSE,
        b_gender VARCHAR(8) NOT NULL DEFAULT 'male',
        b_apply_true_solar_time BOOLEAN NOT NULL DEFAULT FALSE,
        b_chart_json JSON,
        result_json JSON,
        f_day_branch INTEGER NOT NULL DEFAULT 0,
        f_day_stem INTEGER NOT NULL DEFAULT 0,
        f_wuxing INTEGER NOT NULL DEFAULT 0,
        f_ten_god INTEGER NOT NULL DEFAULT 0,
        f_sinsal INTEGER NOT NULL DEFAULT 0,
        total_a INTEGER NOT NULL DEFAULT 0,
        total_b INTEGER NOT NULL DEFAULT 0,
        total_c INTEGER NOT NULL DEFAULT 0,
        is_preview BOOLEAN NOT NULL DEFAULT FALSE,
        credits_charged INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_compat_sessions_user_id ON compat_sessions(user_id)",
    "CREATE INDEX IF NOT EXISTS ix_compat_sessions_created_at ON compat_sessions(created_at)",
    """
    CREATE TABLE IF NOT EXISTS compat_messages (
        id BIGSERIAL PRIMARY KEY,
        compat_id VARCHAR(64) NOT NULL
            REFERENCES compat_sessions(compat_id) ON DELETE CASCADE,
        role VARCHAR(16) NOT NULL,
        content TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT now(),
        sources_json JSON,
        preview_revealed BOOLEAN NOT NULL DEFAULT FALSE,
        is_preview BOOLEAN NOT NULL DEFAULT FALSE,
        credits_charged INTEGER NOT NULL DEFAULT 0,
        reveal_credits_charged INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_compat_messages_compat_id ON compat_messages(compat_id)",
]

_DOWNGRADE_SQL = [
    "DROP TABLE IF EXISTS compat_messages",
    "DROP TABLE IF EXISTS compat_sessions",
]


def upgrade() -> None:
    for sql in _UPGRADE_SQL:
        op.execute(sql)


def downgrade() -> None:
    for sql in _DOWNGRADE_SQL:
        op.execute(sql)
