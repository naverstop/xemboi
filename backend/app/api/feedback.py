"""답변 피드백 👍👎 API (계획 7-D). 로그인/비로그인 모두 가능."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.db import get_db
from backend.app.core.deps import get_optional_user
from backend.app.repositories.auth_models import CreditTransaction, MessageFeedback, User
from backend.app.services import auth_service

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


def _message_paid(db: Session, source: str, message_id: int) -> int:
    """해당 답변(메시지)에 실제 차감된 포인트(차감 + reveal 차감). 리워드 산정 기준."""
    from backend.app.repositories.models import ChatMessage, CompatibilityMessage, TarotMessage, ToolMessage
    model = {"chat": ChatMessage, "compat": CompatibilityMessage, "tool": ToolMessage, "tarot": TarotMessage}.get(source)
    if model is None:
        return 0
    m = db.get(model, message_id)
    if m is None:
        return 0
    return int(getattr(m, "credits_charged", 0) or 0) + int(getattr(m, "reveal_credits_charged", 0) or 0)


def _is_message_owner(db: Session, source: str, message_id: int, uid: int) -> bool:
    """리워드 대상 메시지가 uid 소유 세션의 것인지 검증(IDOR 차단 — 타인 결제분 파밍 방지)."""
    from backend.app.repositories.models import (
        ChatMessage, ChatSession, CompatibilityMessage, CompatibilitySession,
        TarotMessage, TarotSession, ToolMessage, ToolSession,
    )
    mapping = {
        "chat": (ChatMessage, ChatSession, "session_id"),
        "compat": (CompatibilityMessage, CompatibilitySession, "compat_id"),
        "tool": (ToolMessage, ToolSession, "tool_id"),
        "tarot": (TarotMessage, TarotSession, "tarot_id"),
    }
    msg_model, sess_model, fk = mapping.get(source, (None, None, None))
    if msg_model is None:
        return False
    m = db.get(msg_model, message_id)
    if m is None:
        return False
    sess = db.get(sess_model, getattr(m, fk, None))
    return sess is not None and sess.user_id is not None and sess.user_id == uid


def _grant_feedback_reward(db: Session, uid: int, source: str, message_id: int) -> int:
    """첫 피드백 시 결제액의 N%를 적립(일일 상한 내). 적립액 반환(0=없음). 관리자 설정값 우선."""
    # IDOR 차단: 남의(또는 익명) 메시지에 피드백해 결제액 10%를 파밍하는 것을 막는다.
    if not _is_message_owner(db, source, message_id, uid):
        return 0
    from backend.app.services import settings_service
    s = get_settings()
    pct = settings_service.get_int(db, "feedback_reward_pct", s.feedback_reward_pct)
    cap = settings_service.get_int(db, "feedback_reward_daily_cap", s.feedback_reward_daily_cap)
    base = (_message_paid(db, source, message_id) * max(0, pct)) // 100
    if base <= 0:
        return 0
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    used = db.execute(
        select(func.coalesce(func.sum(CreditTransaction.delta), 0)).where(
            CreditTransaction.user_id == uid,
            CreditTransaction.reason == "feedback_reward",
            CreditTransaction.created_at >= start,
        )
    ).scalar() or 0
    remaining = max(0, int(cap) - int(used))
    reward = min(base, remaining)
    if reward <= 0:
        return 0
    auth_service.adjust_credit(db, uid, reward, reason="feedback_reward", ref_id=f"{source}:{message_id}")
    return reward


class FeedbackReq(BaseModel):
    message_id: int
    session_id: Optional[str] = None
    rating: Literal[1, -1]
    comment: Optional[str] = Field(None, max_length=1000)
    # 메시지 출처(메뉴) — chat(사주)/tool(택일·작명)/compat(궁합)/tarot(타로). id 충돌 방지용 네임스페이스.
    source: Literal["chat", "tool", "compat", "tarot"] = "chat"


@router.post("", status_code=201)
def submit_feedback(
    req: FeedbackReq,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> dict[str, Any]:
    uid = user.id if user else None
    row = None
    if uid is not None:
        row = db.execute(
            select(MessageFeedback).where(
                MessageFeedback.message_id == req.message_id,
                MessageFeedback.source == req.source,
                MessageFeedback.user_id == uid,
            )
        ).scalars().first()
    elif req.session_id:
        # 익명: 평점 클릭 → 이유 팝업 제출이 2회 호출되므로 세션 기준으로 upsert
        row = db.execute(
            select(MessageFeedback).where(
                MessageFeedback.message_id == req.message_id,
                MessageFeedback.source == req.source,
                MessageFeedback.session_id == req.session_id,
                MessageFeedback.user_id.is_(None),
            )
        ).scalars().first()
    created = row is None
    if created:
        row = MessageFeedback(
            message_id=req.message_id,
            source=req.source,
            session_id=req.session_id,
            user_id=uid,
            rating=req.rating,
            comment=req.comment,
        )
        db.add(row)
        try:
            db.flush()  # 유니크(message_id,source,user_id) 위반 = 동시 첫 피드백 경쟁
        except IntegrityError:
            # 경쟁에서 짐 — 다른 요청이 먼저 저장. 멱등 처리(리워드는 이긴 쪽만, 여기선 0) 후 업데이트.
            db.rollback()
            created = False
            row = None
            if uid is not None:
                row = db.execute(
                    select(MessageFeedback).where(
                        MessageFeedback.message_id == req.message_id,
                        MessageFeedback.source == req.source,
                        MessageFeedback.user_id == uid,
                    )
                ).scalars().first()
            elif req.session_id:
                row = db.execute(
                    select(MessageFeedback).where(
                        MessageFeedback.message_id == req.message_id,
                        MessageFeedback.source == req.source,
                        MessageFeedback.session_id == req.session_id,
                        MessageFeedback.user_id.is_(None),
                    )
                ).scalars().first()
            if row is not None:
                row.rating = req.rating
                if req.comment is not None:
                    row.comment = req.comment
    else:
        row.rating = req.rating
        if req.comment is not None:
            row.comment = req.comment
    # 첫 피드백(로그인 회원) → 결제액 N% 리워드 적립(답변당 1회·일일 상한). 실패해도 피드백은 저장.
    reward = 0
    if created and uid is not None:
        try:
            reward = _grant_feedback_reward(db, uid, req.source, req.message_id)
            row.reward_granted = reward
        except Exception:  # noqa: BLE001
            reward = 0
    db.commit()
    if row is None:
        # 경쟁 처리 후에도 행을 못 찾은 드문 경우 — 멱등 성공 응답(리워드 0).
        return {"message_id": req.message_id, "source": req.source, "rating": req.rating, "reward_granted": 0}
    db.refresh(row)
    out: dict[str, Any] = {
        "id": row.id, "message_id": row.message_id, "source": row.source, "rating": row.rating,
        "reward_granted": reward,  # 이번 호출에서 새로 적립한 금액(반복 피드백 시 0 → 중복 토스트 방지)
    }
    if uid is not None and reward > 0:
        out["balance"] = auth_service.get_balance(db, uid)
    return out
