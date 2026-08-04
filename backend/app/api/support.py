"""고객센터(CONTACT US) API — 문의 접수/내역(회원) + 게시판/수신자 관리(관리자)."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from backend.app.core.db import get_db, get_session_factory
from backend.app.core.deps import get_current_user, get_optional_user, require_admin
from backend.app.repositories.auth_models import User
from backend.app.services import support_service as svc

router = APIRouter(prefix="/api/support", tags=["support"])
admin_router = APIRouter(
    prefix="/api/admin/support", tags=["admin-support"], dependencies=[Depends(require_admin)]
)


# ───────────────────────── 회원/방문자 ─────────────────────────
class TicketCreateReq(BaseModel):
    category: str = Field("refund", pattern="^(refund|payment|account|etc)$")
    contact_email: EmailStr
    contact_name: Optional[str] = Field(None, max_length=64)
    order_id: Optional[str] = Field(None, max_length=64)
    amount: Optional[int] = Field(None, ge=0)
    title: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1, max_length=4000)


def _notify(ticket: dict[str, Any]) -> None:
    """BackgroundTask 진입점 — 자체 DB 세션으로 활성 수신자 + SMTP 설정 조회 후 발송.

    (요청 세션은 응답 후 닫히므로 백그라운드에서 새 세션을 연다.)
    """
    from backend.app.services import settings_service

    sf = get_session_factory()
    with sf() as db:
        recipients = svc.active_recipient_emails(db)
        smtp = settings_service.get_smtp_config(db)
    svc.send_ticket_notification(ticket, recipients, smtp)


@router.post("/tickets", status_code=201)
def create_ticket(
    req: TicketCreateReq,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> dict[str, Any]:
    t = svc.create_ticket(
        db,
        user_id=user.id if user else None,
        category=req.category,
        contact_email=str(req.contact_email),
        contact_name=req.contact_name,
        order_id=req.order_id,
        amount=req.amount,
        title=req.title,
        message=req.message,
    )
    data = svc.to_dict(t)
    # 접수 알림 메일은 응답 후 백그라운드로(발송 실패가 접수를 막지 않음)
    background.add_task(_notify, data)
    return data


@router.get("/tickets/mine")
def my_tickets(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return {"items": svc.list_user_tickets(db, user.id, 50)}


@router.get("/categories")
def categories() -> dict[str, Any]:
    return {"items": [{"value": k, "label": v} for k, v in svc.CATEGORY_LABELS.items()]}


# ───────────────────────── 관리자 ─────────────────────────
@admin_router.get("/tickets")
def admin_list_tickets(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    items, total = svc.list_tickets(db, status=status, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


class TicketUpdateReq(BaseModel):
    status: Optional[str] = Field(None, pattern="^(received|in_progress|resolved|rejected)$")
    admin_note: Optional[str] = Field(None, max_length=4000)


@admin_router.patch("/tickets/{ticket_id}")
def admin_update_ticket(
    ticket_id: int, req: TicketUpdateReq, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        return svc.update_ticket(
            db, ticket_id, status=req.status, admin_note=req.admin_note
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class TicketRefundReq(BaseModel):
    reason: Optional[str] = Field(None, max_length=200)


@admin_router.post("/tickets/{ticket_id}/refund")
def admin_refund_ticket(
    ticket_id: int, req: TicketRefundReq, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """환불 요청 승인 → 실제 환불 자동 실행(I/F).

    문의에 연결된 주문번호로 토스 결제취소(실키 미설정 시 mock) + 크레딧 회수를 수행한 뒤,
    문의 상태를 '처리완료'로 바꾸고 처리 메모를 남긴다. 토스 실키 주입 시 자동으로 실제 취소가 호출된다.
    """
    t = svc.get_ticket(db, ticket_id)
    if t is None:
        raise HTTPException(status_code=404, detail="문의를 찾을 수 없어요.")
    if not t.order_id:
        raise HTTPException(
            status_code=400,
            detail="주문번호가 없는 문의는 자동 환불할 수 없어요. 주문번호를 확인하거나 수동 처리해 주세요.",
        )
    # 접수자(t.user_id)와 참조 주문의 소유자 일치 검증 — 남의 주문번호를 적어 타인 결제를 환불시키는 것 차단.
    # (로그인 접수 문의만 검증. 비로그인 문의는 접수자 식별 불가라 관리자 수동 판단에 맡긴다.)
    from backend.app.repositories.auth_models import Payment as _Payment
    from sqlalchemy import select as _select

    _pay = db.execute(_select(_Payment).where(_Payment.order_id == t.order_id)).scalar_one_or_none()
    if _pay is not None and t.user_id is not None and _pay.user_id != t.user_id:
        raise HTTPException(
            status_code=400,
            detail="문의 접수자와 결제 주문의 소유자가 달라 자동 환불할 수 없어요. 주문번호를 확인해 주세요.",
        )
    from backend.app.services import payment_service
    reason = (req.reason or "").strip() or f"고객센터 환불승인 #{ticket_id}"
    try:
        result = payment_service.refund_payment(db, t.order_id, reason)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    recovered = int(result.get("recovered_credits", 0) or 0)
    mock = " (mock)" if result.get("mock") else ""
    if result.get("already"):
        # 이미 환불된 주문 — 신규 환불이 일어나지 않았음을 정확히 기록(감사기록 오도 방지, 이중환불 없음).
        note = f"이미 환불된 주문이에요 — 주문 {t.order_id} (추가 환불 없음)"
    else:
        note = f"환불 처리 완료{mock} — 주문 {t.order_id}, 크레딧 {recovered:,}P 회수"
    ticket = svc.update_ticket(db, ticket_id, status="resolved", admin_note=note)
    return {"ticket": ticket, "refund": result}


@admin_router.get("/recipients")
def admin_list_recipients(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": svc.list_recipients(db)}


class RecipientCreateReq(BaseModel):
    email: EmailStr


@admin_router.post("/recipients", status_code=201)
def admin_add_recipient(req: RecipientCreateReq, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return svc.add_recipient(db, str(req.email))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class RecipientPatchReq(BaseModel):
    active: bool


@admin_router.patch("/recipients/{recipient_id}")
def admin_patch_recipient(
    recipient_id: int, req: RecipientPatchReq, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        return svc.set_recipient_active(db, recipient_id, req.active)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@admin_router.delete("/recipients/{recipient_id}", status_code=204)
def admin_delete_recipient(recipient_id: int, db: Session = Depends(get_db)) -> None:
    try:
        svc.delete_recipient(db, recipient_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
