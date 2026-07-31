"""Web Push 구독 API (PWA, 계획 2.7.6).

- POST   /api/push/subscribe    구독 저장(로그인/익명 모두 허용)
- DELETE /api/push/unsubscribe  구독 해제
- GET    /api/push/public-key   VAPID 공개키 조회(프론트 구독용)
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.db import get_db
from backend.app.core.deps import get_optional_user
from backend.app.repositories.auth_models import User
from backend.app.services import push_service

router = APIRouter(prefix="/api/push", tags=["push"])


class SubscribeReq(BaseModel):
    endpoint: str
    p256dh: str
    auth: str


class UnsubscribeReq(BaseModel):
    endpoint: str


@router.get("/public-key")
def public_key() -> dict[str, Any]:
    s = get_settings()
    return {"public_key": s.vapid_public_key, "enabled": push_service.is_enabled()}


@router.post("/subscribe")
def subscribe(
    req: SubscribeReq,
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    push_service.save_subscription(
        db, user.id if user else None, req.endpoint, req.p256dh, req.auth
    )
    return {"ok": True}


@router.delete("/unsubscribe")
def unsubscribe(
    req: UnsubscribeReq,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    push_service.remove_subscription(db, req.endpoint)
    return {"ok": True}
