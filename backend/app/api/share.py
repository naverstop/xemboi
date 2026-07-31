"""답변 공유 횟수 관리 API (계획 7.2 K).

실제 공유(카카오/메일)는 프론트에서 수행하고, 백엔드는 무료 공유 횟수만 관리한다.
Level5(비로그인) 제외 전 회원에게 기본 5회 제공. Level≤1(관리자)은 무제한.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.db import get_db
from backend.app.core.deps import get_current_user
from backend.app.repositories.auth_models import User
from backend.app.services.auth_service import effective_level

router = APIRouter(prefix="/api/share", tags=["share"])


def _quota_payload(user: User) -> dict[str, Any]:
    s = get_settings()
    used = user.share_used_count or 0
    unlimited = effective_level(user) <= 1
    remaining = -1 if unlimited else max(0, s.share_quota_default - used)
    return {
        "used": used,
        "limit": s.share_quota_default,
        "remaining": remaining,
        "unlimited": unlimited,
    }


@router.get("/quota")
def share_quota(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return _quota_payload(user)


class ShareReq(BaseModel):
    channel: str  # kakao | email | link
    message_id: Optional[int] = None
    session_id: Optional[str] = None
    target: Optional[str] = None  # 메일주소 등


@router.post("")
def record_share(
    req: ShareReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    s = get_settings()
    if effective_level(user) >= 5:
        raise HTTPException(status_code=403, detail="login required to share")
    unlimited = effective_level(user) <= 1
    used = user.share_used_count or 0
    if not unlimited and used >= s.share_quota_default:
        raise HTTPException(status_code=403, detail="share_quota_exceeded")
    if not unlimited:
        user.share_used_count = used + 1
        db.commit()
    return {"ok": True, **_quota_payload(user)}
