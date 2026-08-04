"""B-3 이용 후기 API — 공개 목록(승인분만) + 회원 작성 + 관리자 승인/반려.

banners.py(공개 GET)·support.py(admin_router) 패턴 미러.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.deps import get_current_user, require_admin
from backend.app.repositories.auth_models import User
from backend.app.services import review_service as svc

router = APIRouter(prefix="/api/reviews", tags=["reviews"])
admin_router = APIRouter(
    prefix="/api/admin/reviews", tags=["admin-reviews"], dependencies=[Depends(require_admin)]
)


@router.get("")
def list_reviews(
    source: Optional[str] = Query(None, pattern="^(chat|compat|tarot|tool|sinnyeon|consultation)$"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """공개 후기 목록 — 승인된 것만, 마스킹된 표시명만 노출(비인증)."""
    return {"items": svc.list_public(db, source=source, limit=limit)}


class ReviewCreateReq(BaseModel):
    source: str = Field(pattern="^(chat|compat|tarot|tool|sinnyeon|consultation)$")
    content: str = Field(min_length=5, max_length=200)
    rating: int = Field(default=5, ge=1, le=5)


@router.post("", status_code=201)
def create_review(
    req: ReviewCreateReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """회원 후기 작성 — 승인 후 게시, 승인 시 리워드(관리자 설정) 지급."""
    try:
        r = svc.create_review(db, user, source=req.source, content=req.content, rating=req.rating)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.to_dict(r)


@admin_router.get("")
def admin_list(
    status: Optional[str] = Query(None, pattern="^(pending|approved|rejected)$"),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    items, total = svc.list_admin(db, status=status, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


class ReviewUpdateReq(BaseModel):
    status: str = Field(pattern="^(pending|approved|rejected)$")


@admin_router.patch("/{review_id}")
def admin_update(
    review_id: int,
    req: ReviewUpdateReq,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        r = svc.update_status(db, review_id, req.status)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.to_dict(r)
