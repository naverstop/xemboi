"""답변 표준양식/로직 관리 API (계획 L). 관리자 전용."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.deps import require_admin
from backend.app.services import template_service

router = APIRouter(
    prefix="/api/admin/templates",
    tags=["admin", "templates"],
    dependencies=[Depends(require_admin)],
)


class TemplateCreateReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    body: str = Field(..., min_length=1)
    active: bool = False


class TemplateUpdateReq(BaseModel):
    name: Optional[str] = None
    body: Optional[str] = None
    active: Optional[bool] = None


@router.get("")
def list_templates(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": template_service.list_templates(db)}


@router.post("", status_code=201)
def create_template(req: TemplateCreateReq, db: Session = Depends(get_db)) -> dict[str, Any]:
    return template_service.create_template(db, name=req.name, body=req.body, active=req.active)


@router.patch("/{template_id}")
def update_template(
    template_id: int, req: TemplateUpdateReq, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        return template_service.update_template(db, template_id, **req.model_dump(exclude_unset=True))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{template_id}/activate")
def activate_template(template_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return template_service.activate_template(db, template_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{template_id}", status_code=204)
def delete_template(template_id: int, db: Session = Depends(get_db)) -> None:
    try:
        template_service.delete_template(db, template_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
