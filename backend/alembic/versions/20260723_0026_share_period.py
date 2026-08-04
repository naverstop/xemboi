"""users.share_period_start 추가 — 공유 쿼터를 '평생 누적'에서 '월(30일) 주기'로 전환.

[계기 2026-07-23 실측] 화면은 "공유 월 20회 (기본 5회 → 4배)"라고 안내하는데 share_used_count 를
0으로 되돌리는 코드가 저장소 어디에도 없었다. 즉 실제로는 **평생 한도**였다.
라이브 재현: 라이트 패스 구독자가 20회를 소진한 뒤 30일 갱신을 태우면 갱신비 3,900P 는 차감되는데
(잔액 46,100→42,200) 공유 잔여는 0 그대로였고 공유 요청은 403 이었다 — 2개월차부터 돈만 내고
공유 혜택이 없는 상태.

이 컬럼이 주기 앵커다. 리셋은 스케줄러 없이 '지연 평가'로 수행한다(share_service.roll_period).
pass_service 의 갱신 방식과 같은 패턴이라 재기동에 안전하다.

기존 사용자는 앵커만 NOW() 로 심고 **사용량은 건드리지 않는다**(0으로 밀지 않음).
지금까지 쓴 횟수를 '이번 첫 주기의 사용분'으로 인정하는 보수적 처리이며, 적용 시점의 최대
사용량이 3회(한도 5)라 이 때문에 즉시 막히는 사용자는 없다.
"""
from __future__ import annotations

from alembic import op


revision: str = "20260723_0026_share_period"
down_revision = "20260713_0025_pricing_agent"
branch_labels = None
depends_on = None


_UPGRADE_SQL = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS share_period_start TIMESTAMP NULL",
    # 앵커 백필 — NULL 이면 첫 접근 시 코드가 심지만, 기존 사용자는 여기서 한 번에 맞춰 둔다.
    "UPDATE users SET share_period_start = NOW() AT TIME ZONE 'UTC' WHERE share_period_start IS NULL",
]

_DOWNGRADE_SQL = [
    "ALTER TABLE users DROP COLUMN IF EXISTS share_period_start",
]


def upgrade() -> None:
    for sql in _UPGRADE_SQL:
        op.execute(sql)


def downgrade() -> None:
    for sql in _DOWNGRADE_SQL:
        op.execute(sql)
