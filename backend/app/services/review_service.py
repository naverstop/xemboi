"""B-3 이용 후기 서비스 — 수집(회원, 소스별 1일 1건) → 관리자 승인 → 공개 노출.

support_service 패턴 미러. 표시명은 저장 시점 서버 마스킹 스냅샷(원본 닉네임/이메일 공개 API 미노출).
리워드(review_reward_p, 기본 500P)는 '승인' 시점 1회 지급 — 미승인 후기로는 포인트 파밍 불가.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.repositories.auth_models import Review, User
from backend.app.services import auth_service, settings_service

STATUS_LABELS = {"pending": "대기", "approved": "승인", "rejected": "반려"}
_VALID_STATUS = set(STATUS_LABELS)
_VALID_SOURCE = {"chat", "compat", "tarot", "tool", "sinnyeon", "consultation"}

SOURCE_LABELS = {
    "chat": "사주 상담", "compat": "궁합", "tarot": "타로",
    "tool": "택일·작명", "sinnyeon": "신년운세", "consultation": "1:1 상담",
}


def mask_display_name(user: User | None) -> str:
    """공개 표기용 마스킹 — 닉네임 우선(첫 글자+**), 없으면 이메일 로컬파트 앞 2글자+***."""
    if user is None:
        return "익명"
    nick = (user.nickname or "").strip()
    if nick:
        return nick[0] + "*" * max(1, min(3, len(nick) - 1))
    local = (user.email or "").split("@")[0]
    if len(local) >= 2:
        return local[:2] + "***"
    return "익명"


def to_dict(r: Review) -> dict[str, Any]:
    return {
        "id": r.id,
        "source": r.source,
        "source_label": SOURCE_LABELS.get(r.source, r.source),
        "content": r.content,
        "rating": r.rating,
        "display_name": r.display_name,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def create_review(db: Session, user: User, *, source: str, content: str, rating: int) -> Review:
    if source not in _VALID_SOURCE:
        raise ValueError("알 수 없는 메뉴예요.")
    content = " ".join((content or "").split())
    if not (5 <= len(content) <= 200):
        raise ValueError("후기는 5~200자로 적어 주세요.")
    rating = max(1, min(5, int(rating or 5)))
    # 소스별 1일 1건(남용 방지)
    since = datetime.utcnow() - timedelta(days=1)
    dup = db.execute(
        select(func.count()).select_from(Review).where(
            Review.user_id == user.id, Review.source == source, Review.created_at >= since,
        )
    ).scalar_one()
    if dup:
        raise ValueError("이 메뉴 후기는 하루에 한 번만 남길 수 있어요.")
    r = Review(
        user_id=user.id, source=source, content=content, rating=rating,
        display_name=mask_display_name(user), status="pending",
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def list_public(db: Session, *, source: Optional[str] = None, limit: int = 20) -> list[dict[str, Any]]:
    q = select(Review).where(Review.status == "approved")
    if source:
        q = q.where(Review.source == source)
    rows = db.execute(q.order_by(Review.created_at.desc()).limit(max(1, min(50, limit)))).scalars().all()
    return [to_dict(r) for r in rows]


def list_admin(db: Session, *, status: Optional[str] = None, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    q = select(Review)
    cq = select(func.count()).select_from(Review)
    if status:
        q = q.where(Review.status == status)
        cq = cq.where(Review.status == status)
    total = db.execute(cq).scalar_one()
    rows = db.execute(q.order_by(Review.created_at.desc()).limit(limit).offset(offset)).scalars().all()
    return [to_dict(r) for r in rows], int(total)


def update_status(db: Session, review_id: int, status: str) -> Review:
    if status not in _VALID_STATUS:
        raise ValueError("알 수 없는 상태예요.")
    # 행잠금 — 동시 승인(관리자 더블클릭/다중 관리자)이 reward_granted=0 을 함께 읽어 리워드가 이중 지급되는
    #   read-check-set 레이스를 직렬화로 차단(두 번째는 대기 후 reward_granted 를 보고 스킵).
    r = db.get(Review, review_id, with_for_update=True)
    if r is None:
        raise LookupError("후기를 찾을 수 없어요.")
    r.status = status
    # 승인 시 1회 리워드(멱등) — 반려/재승인 반복으로 중복 지급 불가
    if status == "approved" and not r.reward_granted and r.user_id:
        reward = settings_service.get_int(db, "review_reward_p", 500)
        if reward > 0:
            try:
                auth_service.adjust_credit(db, r.user_id, reward, reason="review_reward", ref_id=str(r.id))
                r.reward_granted = reward
            except Exception:  # noqa: BLE001 — 리워드 실패가 승인 자체를 막지 않음
                pass
    db.commit()
    db.refresh(r)
    return r
