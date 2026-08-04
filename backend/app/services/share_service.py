"""공유 쿼터 단일 소스 — 한도 계산·주기 리셋·소비·환원을 여기서만 한다.

[재발 방지] 판정 로직이 api/share.py 와 api/pdf.py 에 **복제**돼 있었고 둘이 갈라졌다.
pdf.py 는 패스 확대를 반영하는 _share_limit 대신 get_settings().share_quota_default(=5)를
직접 읽어서, 패스 구독자가 PDF 메일 공유만 5회에서 막혔다. 바로 위 주석은
"record_share(share.py)와 동일 규칙"이라고 적혀 있었지만 실제로는 달랐다(주석은 검증되지 않는다).
→ 두 경로가 같은 함수를 호출하게 합친다. **새 공유 경로도 반드시 이 모듈을 쓸 것.**

[주기] 화면은 "공유 월 20회 (기본 5회 → 4배)"라고 안내하는데 share_used_count 를 0으로
되돌리는 코드가 저장소 어디에도 없어 사실상 '평생 한도'였다. 라이브 재현 결과 라이트 패스
구독자가 2개월차 갱신비 3,900P 를 내고도 공유 잔여 0·403 이었다.
→ share_period_start 앵커 + 지연 평가로 30일마다 리셋한다. 스케줄러가 없어도 되고(요청 시 평가)
  재기동에 안전하다 — pass_service._renew_or_expire 와 같은 방식.

[주기 길이] 월 패스와 동일한 30일(pass_service.PERIOD_DAYS). 이 서비스에서 '월'은 30일을 뜻한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, update as _upd
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.repositories.auth_models import User

PERIOD_DAYS = 30


class QuotaExceeded(Exception):
    """이번 주기 공유 한도 소진. 호출부가 403 share_quota_exceeded 로 변환한다."""


def base_limit() -> int:
    """비패스 기본 한도. 표시(패스 혜택 문구)와 판정이 같은 값을 보게 하려고 여기로 모았다."""
    return get_settings().share_quota_default


def limit(db: Session, user: User) -> int:
    """이 사용자의 이번 주기 공유 한도 — B-7 월 패스 이용 중이면 확대(pass_share_quota).

    ⚠️ tier 를 구분하지 않는다(라이트·플러스 모두 확대). '광고 제거 + 공유 확대'는 라이트 혜택이고
    플러스는 '라이트 혜택 전체'를 포함하므로 의도된 동작이다.
    """
    base = base_limit()
    try:
        from backend.app.services import pass_service, settings_service
        if pass_service.get_pass(db, user.id) is not None:
            return max(base, settings_service.get_int(db, "pass_share_quota", 20))
    except Exception:  # noqa: BLE001
        pass
    return base


def roll_period(db: Session, user: User) -> None:
    """주기(30일)가 지났으면 사용량을 0으로 되돌린다(지연 평가). 필요 시에만 커밋.

    동시요청 안전: 앵커를 조건부 UPDATE(WHERE share_period_start = 내가 읽은 값)로 전진시켜
    승자 1명만 리셋한다. 패자는 이미 리셋된 상태를 다시 읽으므로 이중 리셋이 없다.
    """
    now = datetime.utcnow()
    start = user.share_period_start
    if start is None:
        # 앵커 미설정(마이그레이션 이전 가입자·신규) → 지금을 주기 시작으로 심는다.
        # 기존 사용량은 '이번 주기 사용분'으로 인정하고 0으로 밀지 않는다(보수적).
        db.execute(_upd(User).where(User.id == user.id, User.share_period_start.is_(None))
                   .values(share_period_start=now))
        db.commit()
        db.refresh(user)
        return
    if now - start < timedelta(days=PERIOD_DAYS):
        return
    # 주기 경과 — 여러 주기를 건너뛴 경우에도 '지금'부터 새 주기 1개만 시작한다(소급 계산 없음).
    db.execute(_upd(User).where(User.id == user.id, User.share_period_start == start)
               .values(share_used_count=0, share_period_start=now))
    db.commit()
    db.refresh(user)


def _unlimited(user: User) -> bool:
    from backend.app.services.auth_service import effective_level
    return effective_level(user) <= 1          # 관리자 = 무제한


def quota_payload(db: Session, user: User) -> dict[str, Any]:
    """화면 표시용 잔여 — 조회 시점에 주기 리셋을 먼저 반영한다(표시와 실제가 어긋나지 않게)."""
    roll_period(db, user)
    used = user.share_used_count or 0
    lim = limit(db, user)
    unlimited = _unlimited(user)
    return {
        "used": used,
        "limit": lim,
        "remaining": -1 if unlimited else max(0, lim - used),
        "unlimited": unlimited,
        "period_days": PERIOD_DAYS,
        "period_start": user.share_period_start.isoformat() if user.share_period_start else None,
    }


def consume(db: Session, user: User) -> dict[str, Any]:
    """공유 1회를 원자적으로 소비한다. 한도 초과면 QuotaExceeded.

    동시 공유 lost-update 방지: read-modify-write 대신 WHERE(사용량 < 한도) 조건부 UPDATE +
    rowcount 검사. PostgreSQL 행잠금·EvalPlanQual 로 최신값에 WHERE 가 재평가된다.
    """
    if _unlimited(user):
        return quota_payload(db, user)
    roll_period(db, user)
    lim = limit(db, user)
    res = db.execute(
        _upd(User)
        .where(User.id == user.id, func.coalesce(User.share_used_count, 0) < lim)
        .values(share_used_count=func.coalesce(User.share_used_count, 0) + 1)
    )
    if res.rowcount == 0:
        db.rollback()
        raise QuotaExceeded()
    db.commit()
    db.refresh(user)
    return quota_payload(db, user)


def refund(db: Session, user: User) -> None:
    """소비 직후 실패(메일 발송 실패 등) 시 1회 환원. 0 미만으로는 내려가지 않는다."""
    db.execute(
        _upd(User)
        .where(User.id == user.id, func.coalesce(User.share_used_count, 0) > 0)
        .values(share_used_count=func.coalesce(User.share_used_count, 0) - 1)
    )
    db.commit()
