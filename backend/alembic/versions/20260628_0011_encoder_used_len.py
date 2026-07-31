"""encoder_used 컬럼 길이 확대 VARCHAR(8)→(16).

'hevc_nvenc'(10자)가 VARCHAR(8)에 안 들어가 nvenc 인코딩 시 DataError 발생하던 잠복 버그 수정.
멱등(USING 캐스트 없이 단순 길이 확대).
"""
from __future__ import annotations

from alembic import op


revision: str = "20260628_0011_encoder_used_len"
down_revision = "20260628_0010_saju_video_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE saju_video_jobs ALTER COLUMN encoder_used TYPE VARCHAR(16)")


def downgrade() -> None:
    op.execute("ALTER TABLE saju_video_jobs ALTER COLUMN encoder_used TYPE VARCHAR(8)")
