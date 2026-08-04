"""결제 API."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.deps import get_current_user, require_admin
from backend.app.repositories.auth_models import User
from backend.app.services import payment_service as svc

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.get("/packages")
def get_packages() -> dict[str, Any]:
    return {"items": svc.list_packages()}


class CreateOrderReq(BaseModel):
    amount: int = Field(..., gt=0)


@router.post("/orders")
def create_order(
    req: CreateOrderReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return svc.create_order(db, user, req.amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class ConfirmReq(BaseModel):
    payment_key: str
    order_id: str
    amount: int


@router.post("/confirm")
def confirm(
    req: ConfirmReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        return svc.confirm_payment(db, user, req.payment_key, req.order_id, req.amount)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/me")
def my_history(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return {"items": svc.list_my_payments(db, user)}


@router.get("/transactions")
def my_transactions(
    limit: int = Query(100, ge=1, le=300),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """회원 본인 포인트 원장(충전·차감·환불·리워드 전부, 최신순) — 비로그인 401.

    '잔액은 줄었는데 쓴 기록이 없다'는 오해를 없애기 위한 사용자용 투명 조회.
    관리자용 list_transactions 를 그대로 재사용(본인 user.id 로 스코프 고정)."""
    from backend.app.services import admin_service
    return {
        "items": admin_service.list_transactions(db, user.id, limit=limit),
        "summary": admin_service.credit_ledger_summary(db, user.id),   # 충전+적립−사용=잔액 정합성 대조용
    }


class RefundReq(BaseModel):
    order_id: str
    reason: str = "admin refund"


@router.post("/refund")
def refund(
    req: RefundReq,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> dict[str, Any]:
    try:
        return svc.refund_payment(db, req.order_id, req.reason)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/webhook")
async def webhook(req: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    raw = await req.body()
    signature = req.headers.get("toss-signature") or req.headers.get("x-toss-signature")
    from backend.app.core.config import get_settings
    s = get_settings()
    if s.toss_webhook_secret:
        import hashlib
        import hmac
        expected = hmac.new(
            s.toss_webhook_secret.encode("utf-8"), raw, hashlib.sha256
        ).hexdigest()
        if not signature or not hmac.compare_digest(expected, signature.lower()):
            raise HTTPException(status_code=401, detail="invalid signature")
    elif not getattr(s, "allow_mock_payment", False):
        # fail-closed: 서명키 미설정 시 위조 웹훅으로 결제상태 오염 가능 → 거부(테스트 mock 제외)
        raise HTTPException(status_code=401, detail="webhook secret not configured")
    import json as _json
    try:
        body = _json.loads(raw or b"{}")
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")
    return svc.handle_webhook(db, body)
