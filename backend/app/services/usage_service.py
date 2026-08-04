"""사용 현황 집계 헬퍼 — usage_daily 카운터 증분(클라 beat + 서버 실측 공용).

kind:
- 'page'/'click': 클라이언트 수집(api/usage.py beat)
- 'feat': 서버 실측 — DB 테이블이 없는 기능 실행(PDF 생성·감정서·공유 확정 등)을
  실행 성공 시점에 서버가 직접 기록(클라 이벤트 유실·조작 무관한 진실값).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from backend.app.repositories.usage_models import UsageDaily


def bump_daily(db: Session, kind: str, key: str, n: int = 1, day: date | None = None) -> None:
    """일별 카운터 증분 — update 먼저, 없으면 insert(동시 최초 삽입 경합은 유니크 제약 후 재시도).
    호출자 트랜잭션에 편승(commit은 호출자가). 실패해도 본 기능을 깨지 않도록 예외는 삼킨다."""
    d = day or date.today()
    try:
        row = (
            db.query(UsageDaily)
            .filter(UsageDaily.day == d, UsageDaily.kind == kind, UsageDaily.key == key)
            .first()
        )
        if row:
            row.count = row.count + n
            return
        db.add(UsageDaily(day=d, kind=kind, key=key, count=n))
        db.flush()
    except Exception:  # noqa: BLE001 — 집계는 부가 기능: 실패가 본 기능(PDF 등)을 막으면 안 됨
        try:
            db.rollback()
            row = (
                db.query(UsageDaily)
                .filter(UsageDaily.day == d, UsageDaily.kind == kind, UsageDaily.key == key)
                .first()
            )
            if row:
                row.count = row.count + n
        except Exception:  # noqa: BLE001
            pass
