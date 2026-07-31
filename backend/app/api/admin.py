"""관리자 콘솔 API. require_admin 으로 가드."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.deps import require_admin
from backend.app.repositories.auth_models import User
from backend.app.services import admin_service as svc

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# -------- 통계 --------

@router.get("/stats")
def get_stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    return svc.get_stats(db)


# -------- 회원 --------

@router.get("/users")
def list_users(
    q: Optional[str] = Query(None, description="이메일/닉네임 부분일치"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    items, total = svc.list_users(db, q=q, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/users/{user_id}/transactions")
def list_user_transactions(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return {"items": svc.list_transactions(db, user_id, limit=limit)}


@router.get("/users/{user_id}/payments")
def list_user_payments(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """회원 결제/환불 내역 — 관리자 환불 처리 대상 목록."""
    return {"items": svc.list_user_payments(db, user_id, limit=limit)}


class AdminRefundReq(BaseModel):
    reason: str = Field("admin refund", max_length=200)


@router.post("/payments/{order_id}/refund")
def admin_refund_payment(
    order_id: str,
    req: AdminRefundReq,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """관리자 환불 실행 — 토스 결제취소(실키 미설정 시 mock) + 크레딧 회수 + status=refunded.
    토스 연동 전(DUMMY 키)에는 mock 으로 동작하고, 실키 주입 시 자동으로 실제 취소가 호출된다."""
    from backend.app.services import payment_service
    try:
        return payment_service.refund_payment(db, order_id, req.reason)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


class GrantReq(BaseModel):
    delta: int = Field(..., description="+ 충전 / - 차감")
    reason: str = Field("admin_grant", max_length=32)


@router.post("/users/{user_id}/grant")
def grant_credit(
    user_id: int,
    req: GrantReq,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        new_balance = svc.grant_credit(db, user_id, req.delta, reason=req.reason)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"user_id": user_id, "balance": new_balance}


class AdsToggleReq(BaseModel):
    ads_hidden: bool


@router.patch("/users/{user_id}/ads")
def admin_set_ads_hidden(
    user_id: int,
    req: AdsToggleReq,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from backend.app.repositories.auth_models import User as _U

    u = db.get(_U, user_id)
    if u is None:
        raise HTTPException(status_code=404, detail="user not found")
    u.ads_hidden = req.ads_hidden
    db.commit()
    return {"user_id": user_id, "ads_hidden": u.ads_hidden}


# -------- 배너 --------

class BannerCreateReq(BaseModel):
    slot: str
    image_url: str
    link_url: Optional[str] = None
    title: Optional[str] = None
    weight: int = 10
    active: bool = True


class BannerUpdateReq(BaseModel):
    slot: Optional[str] = None
    image_url: Optional[str] = None
    link_url: Optional[str] = None
    title: Optional[str] = None
    weight: Optional[int] = None
    active: Optional[bool] = None


@router.get("/banners")
def list_banners(
    slot: Optional[str] = None,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return {"items": svc.list_banners(db, slot=slot)}


@router.post("/banners", status_code=201)
def create_banner(req: BannerCreateReq, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return svc.create_banner(db, **req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/banners/{banner_id}")
def update_banner(banner_id: int, req: BannerUpdateReq, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return svc.update_banner(db, banner_id, **req.model_dump(exclude_unset=True))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/banners/{banner_id}", status_code=204)
def delete_banner(banner_id: int, db: Session = Depends(get_db)) -> None:
    try:
        svc.delete_banner(db, banner_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


# -------- 과금/한도 설정 (계획 4.3) --------

class SettingsPatchReq(BaseModel):
    free_quota_count: Optional[int] = Field(None, ge=0, le=1000)
    free_quota_reset: Optional[str] = Field(None, pattern="^(none|daily|monthly)$")
    credit_cost_basic: Optional[int] = Field(None, ge=0)
    credit_cost_deep: Optional[int] = Field(None, ge=0)
    preview_reveal_cost: Optional[int] = Field(None, ge=0)
    preview_max_chars: Optional[int] = Field(None, ge=1, le=5000)
    feedback_reward_pct: Optional[int] = Field(None, ge=0, le=100)
    feedback_reward_daily_cap: Optional[int] = Field(None, ge=0)
    external_llm_enabled: Optional[bool] = None
    # 프리미엄 메뉴 입장료(메뉴별) + 공통 행사 할인%
    entry_cost_compat: Optional[int] = Field(None, ge=0)
    entry_cost_taekil: Optional[int] = Field(None, ge=0)
    entry_cost_jakmyeong: Optional[int] = Field(None, ge=0)
    entry_cost_gaemyeong: Optional[int] = Field(None, ge=0)
    entry_cost_aho: Optional[int] = Field(None, ge=0)
    entry_cost_tarot: Optional[int] = Field(None, ge=0)
    premium_entry_discount_pct: Optional[int] = Field(None, ge=0, le=100)


@router.get("/settings")
def get_settings_admin(db: Session = Depends(get_db)) -> dict[str, Any]:
    from backend.app.services import settings_service
    return {"settings": settings_service.get_all(db)}


@router.patch("/settings")
def patch_settings_admin(req: SettingsPatchReq, db: Session = Depends(get_db)) -> dict[str, Any]:
    from backend.app.services import settings_service
    items: dict[str, Any] = {}
    for k, v in req.model_dump(exclude_unset=True).items():
        if v is None:
            continue
        items[k] = ("true" if v else "false") if isinstance(v, bool) else v
    updated = settings_service.set_many(db, items)
    return {"settings": updated}


# -------- 운영/법무 설정: 사업자 정보 · 약관 버전/본문 · 메일(SMTP) --------

class SiteSettingsPatchReq(BaseModel):
    # 사업자(통신판매업자) 정보
    service_name: Optional[str] = None
    biz_name: Optional[str] = None
    biz_ceo: Optional[str] = None
    biz_reg_no: Optional[str] = None
    biz_mailorder_no: Optional[str] = None
    biz_address: Optional[str] = None
    biz_tel: Optional[str] = None
    biz_email: Optional[str] = None
    biz_privacy_officer: Optional[str] = None
    biz_hosting: Optional[str] = None
    # 약관 버전·연령
    terms_version: Optional[str] = None
    privacy_version: Optional[str] = None
    refund_version: Optional[str] = None
    min_age_years: Optional[str] = None
    # 약관 본문 덮어쓰기(Markdown)
    legal_body_terms: Optional[str] = None
    legal_body_privacy: Optional[str] = None
    legal_body_refund: Optional[str] = None
    legal_body_disclaimer: Optional[str] = None
    # 메일(SMTP)
    smtp_enabled: Optional[bool] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None
    smtp_use_tls: Optional[bool] = None


@router.get("/site-settings")
def get_site_settings_admin(db: Session = Depends(get_db)) -> dict[str, Any]:
    from backend.app.services import settings_service
    return {"settings": settings_service.get_site_settings(db)}


@router.patch("/site-settings")
def patch_site_settings_admin(req: SiteSettingsPatchReq, db: Session = Depends(get_db)) -> dict[str, Any]:
    from backend.app.services import settings_service
    items: dict[str, Any] = {}
    for k, v in req.model_dump(exclude_unset=True).items():
        if v is None:
            continue
        items[k] = ("true" if v else "false") if isinstance(v, bool) else str(v)
    settings_service.set_many(db, items)
    return {"settings": settings_service.get_site_settings(db)}


# -------- 타로 카드 해석/키워드 편집 (정적 덱 위 오버레이, 저장 즉시 라이브 반영) --------

class TarotCardUpdateReq(BaseModel):
    keywords_up: list[str] = Field(..., description="정방향 키워드(1~12개)")
    keywords_rev: list[str] = Field(..., description="역방향 키워드(1~12개)")
    interp_up: str = Field(..., description="정방향 해석 서술")
    interp_rev: str = Field(..., description="역방향 해석 서술")


@router.get("/tarot/cards")
def admin_list_tarot_cards(db: Session = Depends(get_db)) -> dict[str, Any]:
    from backend.app.services import tarot_content
    return {"items": tarot_content.list_cards(db)}


@router.patch("/tarot/cards/{code}")
def admin_update_tarot_card(
    code: str,
    req: TarotCardUpdateReq,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    from backend.app.services import tarot_content
    try:
        return tarot_content.update_card(db, code, admin_id=user.id, **req.model_dump())
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/tarot/cards/{code}/reset")
def admin_reset_tarot_card(code: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """편집분 삭제 → JSON 시드(초안)로 되돌림."""
    from backend.app.services import tarot_content
    try:
        return tarot_content.reset_card(db, code)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
