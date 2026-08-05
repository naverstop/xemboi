"""답변 공유 횟수 관리 API (계획 7.2 K).

실제 공유(카카오/메일)는 프론트에서 수행하고, 백엔드는 무료 공유 횟수만 관리한다.
Level5(비로그인) 제외 전 회원에게 기본 5회/30일 제공(패스 이용 시 20회). Level≤1(관리자)은 무제한.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.deps import get_current_user
from backend.app.repositories.auth_models import User
from backend.app.services import share_service
from backend.app.services.auth_service import effective_level

router = APIRouter(prefix="/api/share", tags=["share"])


# 한도·주기·소비 판정은 전부 share_service 로 옮겼다(2026-07-23).
# 여기와 pdf.py 에 같은 로직이 복제돼 있다가 갈라져 패스 구독자가 PDF 메일 공유만 5회에서
# 막히는 버그가 났다. 새 공유 경로도 반드시 share_service 를 쓸 것.


@router.get("/quota")
def share_quota(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return share_service.quota_payload(db, user)


class ShareReq(BaseModel):
    channel: str  # kakao | zalo | email | link (vi=Zalo, ko=Kakao)
    message_id: Optional[int] = None
    session_id: Optional[str] = None
    target: Optional[str] = None  # 메일주소 등


@router.post("")
def record_share(
    req: ShareReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    if effective_level(user) >= 5:
        raise HTTPException(status_code=403, detail="login required to share")
    try:
        payload = share_service.consume(db, user)   # 주기 리셋 → 한도 판정 → 원자 소비
    except share_service.QuotaExceeded:
        raise HTTPException(status_code=403, detail="share_quota_exceeded")
    from backend.app.services.usage_service import bump_daily
    bump_daily(db, "feat", "share")        # 실사용 실측(관리자 현재 통계) — 공유 '확정' 시점
    db.commit()
    return {"ok": True, **payload}
