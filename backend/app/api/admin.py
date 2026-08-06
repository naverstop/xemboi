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


@router.get("/payments")
def list_all_payments(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """전 회원 결제 내역(최신순·페이지네이션) — 관리자 통계 매출 리스트."""
    items, total = svc.list_all_payments(db, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


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


def _require_user(db: Session, user_id: int) -> None:
    """존재하지 않는 user_id 는 404 — grant/ads 와 동일한 관례(오타 ID 를 '내역 없음'으로 오인 방지)."""
    from backend.app.repositories.auth_models import User as _U
    if db.get(_U, user_id) is None:
        raise HTTPException(status_code=404, detail="user not found")


@router.get("/users/{user_id}/transactions")
def list_user_transactions(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _require_user(db, user_id)
    return {"items": svc.list_transactions(db, user_id, limit=limit)}


@router.get("/users/{user_id}/payments")
def list_user_payments(
    user_id: int,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """회원 결제/환불 내역 — 관리자 환불 처리 대상 목록."""
    _require_user(db, user_id)
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
    if req.delta == 0:
        raise HTTPException(status_code=400, detail="증감할 포인트(0이 아닌 값)를 입력해 주세요.")
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
    review_reward_p: Optional[int] = Field(None, ge=0)  # B-3 후기 승인 시 1회 리워드(P)
    amulet_cost_p: Optional[int] = Field(None, ge=0)    # B-4 부적 발행 1회 차감(P)
    video_gen_cost: Optional[int] = Field(None, ge=0)   # 사주 영상 생성 1회 차감(P)
    # B-7 월 패스
    pass_lite_price_p: Optional[int] = Field(None, ge=0)
    pass_plus_price_p: Optional[int] = Field(None, ge=0)
    pass_share_quota: Optional[int] = Field(None, ge=0)
    pass_followup_discount_pct: Optional[int] = Field(None, ge=0, le=100)
    external_llm_enabled: Optional[bool] = None
    # 프리미엄 메뉴 입장료(메뉴별) + 공통 행사 할인%
    entry_cost_compat: Optional[int] = Field(None, ge=0)
    entry_cost_taekil: Optional[int] = Field(None, ge=0)
    entry_cost_jakmyeong: Optional[int] = Field(None, ge=0)
    entry_cost_gaemyeong: Optional[int] = Field(None, ge=0)
    entry_cost_aho: Optional[int] = Field(None, ge=0)
    entry_cost_tarot: Optional[int] = Field(None, ge=0)
    entry_cost_sinnyeon: Optional[int] = Field(None, ge=0)  # B-1 신년운세 입장료
    premium_entry_discount_pct: Optional[int] = Field(None, ge=0, le=100)
    # 마케팅 가격 에이전트 — 조사 토글(자동적용은 미구현·승인게이트 필수)
    pricing_survey_enabled: Optional[bool] = None
    pricing_auto_apply_enabled: Optional[bool] = None


@router.get("/settings")
def get_settings_admin(db: Session = Depends(get_db)) -> dict[str, Any]:
    from backend.app.services import settings_service
    return {"settings": settings_service.mask_secrets(settings_service.get_all(db))}


@router.patch("/settings")
def patch_settings_admin(req: SettingsPatchReq, db: Session = Depends(get_db)) -> dict[str, Any]:
    from backend.app.services import settings_service
    items: dict[str, Any] = {}
    for k, v in req.model_dump(exclude_unset=True).items():
        if v is None:
            continue
        items[k] = ("true" if v else "false") if isinstance(v, bool) else v
    updated = settings_service.set_many(db, items)
    return {"settings": settings_service.mask_secrets(updated)}


# -------- 마케팅 가격 에이전트(2026-07-13) — 경쟁사 시트·가드레일·권장·승인 --------
# 시장조사 → 결정적 권장가 → 관리자 [적용] 클릭으로만 가격변경. 자동적용 없음.

class CompetitorReq(BaseModel):
    id: Optional[int] = None
    competitor_name: str = Field(..., min_length=1, max_length=80)
    menu_key: str = Field(..., max_length=48)
    price_krw: int = Field(..., ge=0)
    note: Optional[str] = Field(None, max_length=200)


class GuardrailReq(BaseModel):
    menu_key: str = Field(..., max_length=48)
    floor_p: Optional[int] = Field(None, ge=0)
    ceiling_p: Optional[int] = Field(None, ge=0)
    max_change_pct: Optional[int] = Field(None, ge=0, le=100)
    undercut_pct: Optional[int] = Field(None, ge=0, le=100)
    round_unit: Optional[int] = Field(None, ge=1)
    round_tail: Optional[int] = Field(None, ge=0)
    enabled: Optional[bool] = None


@router.get("/pricing/overview")
def pricing_overview(db: Session = Depends(get_db)) -> dict[str, Any]:
    """가격 에이전트 대시보드 한 번에 — 경쟁사·가드레일·pending 권장·이력·3소스 diff."""
    from backend.app.services import pricing_agent_service as p, settings_service
    return {
        "competitors": p.list_competitors(db),
        "guardrails": p.list_guardrails(db),
        "pending": p.list_recommendations(db, status="pending"),
        "history": p.list_recommendations(db, limit=50),
        "sync_diff": p.sync_diff(db),
        "survey_enabled": settings_service.get_bool(db, "pricing_survey_enabled"),
    }


@router.post("/pricing/competitors")
def pricing_upsert_competitor(req: CompetitorReq, admin: User = Depends(require_admin),
                              db: Session = Depends(get_db)) -> dict[str, Any]:
    from backend.app.services import pricing_agent_service as p
    try:
        return p.upsert_competitor(db, id=req.id, competitor_name=req.competitor_name,
                                   menu_key=req.menu_key, price_krw=req.price_krw,
                                   note=req.note, updated_by=admin.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/pricing/competitors/{cid:int}", status_code=204)
def pricing_delete_competitor(cid: int, db: Session = Depends(get_db)) -> None:
    from backend.app.services import pricing_agent_service as p
    p.delete_competitor(db, cid)


@router.patch("/pricing/guardrails")
def pricing_update_guardrail(req: GuardrailReq, db: Session = Depends(get_db)) -> dict[str, Any]:
    from backend.app.services import pricing_agent_service as p
    try:
        return p.update_guardrail(db, req.menu_key, req.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/pricing/survey")
def pricing_run_survey(db: Session = Depends(get_db)) -> dict[str, Any]:
    """지금 시장조사 — 권장가 산출(pending 적재). ⛔ 가격 변경 없음."""
    from backend.app.services import pricing_agent_service as p
    return p.run_survey(db)


@router.post("/pricing/recommendations/{rid:int}/apply")
def pricing_apply(rid: int, admin: User = Depends(require_admin),
                  db: Session = Depends(get_db)) -> dict[str, Any]:
    """관리자 최종 승인 — 유일한 가격변경 경로."""
    from backend.app.services import pricing_agent_service as p
    try:
        return p.apply_recommendation(db, rid, admin.email)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/pricing/recommendations/{rid:int}/dismiss")
def pricing_dismiss(rid: int, admin: User = Depends(require_admin),
                    db: Session = Depends(get_db)) -> dict[str, Any]:
    from backend.app.services import pricing_agent_service as p
    try:
        return p.dismiss_recommendation(db, rid, admin.email)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/pricing/recommendations/{rid:int}/rollback")
def pricing_rollback(rid: int, admin: User = Depends(require_admin),
                     db: Session = Depends(get_db)) -> dict[str, Any]:
    from backend.app.services import pricing_agent_service as p
    try:
        return p.rollback_recommendation(db, rid, admin.email)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


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
    return {"settings": settings_service.mask_secrets(settings_service.get_site_settings(db))}


@router.patch("/site-settings")
def patch_site_settings_admin(req: SiteSettingsPatchReq, db: Session = Depends(get_db)) -> dict[str, Any]:
    from backend.app.services import settings_service
    items: dict[str, Any] = {}
    for k, v in req.model_dump(exclude_unset=True).items():
        if v is None:
            continue
        items[k] = ("true" if v else "false") if isinstance(v, bool) else str(v)
    settings_service.set_many(db, items)
    return {"settings": settings_service.mask_secrets(settings_service.get_site_settings(db))}


class TestEmailReq(BaseModel):
    to: Optional[str] = None  # 없으면 관리자 본인 메일로


@router.post("/settings/test-email")
def send_test_email_admin(
    req: TestEmailReq,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict[str, Any]:
    """저장된 SMTP 설정으로 테스트 메일을 즉시 발송(설정 검증). 실패 사유를 그대로 반환."""
    from backend.app.services import settings_service, support_service
    smtp = settings_service.get_smtp_config(db)
    to = (req.to or "").strip() or (admin.email or "")
    ok, detail = support_service.send_test_email(smtp, to)
    return {"ok": ok, "detail": detail, "to": to}


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


@router.get("/tarot/learn-status")
def admin_tarot_learn_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    """타로 덱 학습 상태 — 최종 학습일시·버전·패리티(학습 후 편집 발생 여부)."""
    from backend.app.services import tarot_content
    return tarot_content.learn_status(db)


@router.post("/tarot/relearn")
def admin_tarot_relearn(
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """수동 재학습(1일 1회) — 캐시 재적재 + 확정 스냅샷 버전 저장. 초과 시 409."""
    from backend.app.services import tarot_content
    try:
        return tarot_content.relearn(db, mode="manual", admin_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


# -------- 현재 통계(사용 현황) — 운영자 지시 2026-07-11 --------

@router.get("/usage-summary")
def usage_summary(db: Session = Depends(get_db)) -> dict:
    """현재 접속·오늘 방문·PWA 설치(플랫폼별)·메뉴 사용도·버튼 클릭 현황."""
    from datetime import date, datetime, timedelta

    from sqlalchemy import func

    from backend.app.repositories.usage_models import UsageDaily, UsageDevice

    now = datetime.now()
    today = date.today()
    week_ago = today - timedelta(days=6)

    online_now = db.query(func.count(UsageDevice.device_id)).filter(
        UsageDevice.last_seen >= now - timedelta(minutes=5)).scalar() or 0
    today_visitors = db.query(func.count(UsageDevice.device_id)).filter(
        UsageDevice.last_seen >= datetime.combine(today, datetime.min.time())).scalar() or 0

    pwa_rows = (db.query(UsageDevice.platform, func.count(UsageDevice.device_id))
                .filter(UsageDevice.is_pwa.is_(True)).group_by(UsageDevice.platform).all())
    pwa = {"total": sum(int(c) for _, c in pwa_rows)}
    for plat, c in pwa_rows:
        pwa[plat] = int(c)

    # 설치율(전환 지표) = 앱 설치 기기 / 전체 방문 기기(전 기간 누적). '방문 중 몇 %가 앱으로 설치했나'.
    #  ⚠️ iOS Safari 는 appinstalled 자동신호가 없어 is_pwa 는 standalone 실행 시에만 래칫된다 —
    #     '설치했지만 아직 홈아이콘으로 실행 안 한' iOS 는 미집계라 실제 설치율은 이 값 이상일 수 있다(하한).
    total_devices = db.query(func.count(UsageDevice.device_id)).scalar() or 0
    install_rate = round(pwa["total"] / total_devices * 100, 1) if total_devices else 0.0

    def _agg(kind: str) -> list[dict]:
        rows = (db.query(
                    UsageDaily.key,
                    func.sum(UsageDaily.count).filter(UsageDaily.day == today),
                    func.sum(UsageDaily.count))
                .filter(UsageDaily.kind == kind, UsageDaily.day >= week_ago)
                .group_by(UsageDaily.key).all())
        out = [{"key": k, "today": int(t or 0), "week": int(w or 0)} for k, t, w in rows]
        out.sort(key=lambda r: (-r["week"], r["key"]))
        return out

    # ── 메뉴별 '세부 기능 실사용' — DB 실측(운영자 지시: 껍데기 클릭이 아니라 실제 사용 여부) ──
    from sqlalchemy import and_

    from backend.app.repositories.auth_models import CreditTransaction, Payment, Review, User as _User
    from backend.app.repositories.consultation_models import ConsultationSession
    from backend.app.repositories.models import (
        ChatMessage, ChatSession, SajuVideoJob, TarotSession, ToolSession,
    )
    from backend.app.repositories.models import CompatibilitySession as CompatSession
    from sqlalchemy import text as _text

    t0 = datetime.combine(today, datetime.min.time())
    w0 = datetime.combine(week_ago, datetime.min.time())

    def cnt(model, created_col, *filters) -> dict:
        def q(*extra):
            x = db.query(func.count()).select_from(model)
            for f in filters + extra:
                x = x.filter(f)
            return int(x.scalar() or 0)
        return {"today": q(created_col >= t0), "week": q(created_col >= w0), "total": q()}

    def feat_counter(key: str) -> dict:
        rows = (db.query(UsageDaily.day, UsageDaily.count)
                .filter(UsageDaily.kind == "feat", UsageDaily.key == key).all())
        return {
            "today": sum(c for d, c in rows if d == today),
            "week": sum(c for d, c in rows if d >= week_ago),
            "total": sum(c for _, c in rows),
        }

    def tool_cnt(**kw) -> dict:
        f = []
        if "tool" in kw:
            f.append(ToolSession.tool == kw["tool"])
        if "kind" in kw:
            f.append(ToolSession.kind == kw["kind"])
        return cnt(ToolSession, ToolSession.created_at, *f)

    def credit_cnt(reason: str) -> dict:
        return cnt(CreditTransaction, CreditTransaction.created_at,
                   CreditTransaction.reason == reason, CreditTransaction.delta < 0)

    def _invite_cnt() -> dict:
        # compat_invites 모델은 api 모듈 내 정의 — 테이블 부재 환경(테스트 sqlite)에서도 안전하게
        try:
            return {
                "today": int(db.execute(_text("SELECT COUNT(*) FROM compat_invites WHERE created_at >= :t"), {"t": t0}).scalar() or 0),
                "week": int(db.execute(_text("SELECT COUNT(*) FROM compat_invites WHERE created_at >= :t"), {"t": w0}).scalar() or 0),
                "total": int(db.execute(_text("SELECT COUNT(*) FROM compat_invites")).scalar() or 0),
            }
        except Exception:  # noqa: BLE001
            db.rollback()
            return {"today": 0, "week": 0, "total": 0}

    remember_total = int(db.query(func.count()).select_from(_User)
                         .filter(_User.saju_profile.isnot(None)).scalar() or 0)

    features = [
        {"menu": "상담(사주)", "feature": "상담 시작(명식 생성)", **cnt(ChatSession, ChatSession.created_at)},
        {"menu": "상담(사주)", "feature": "질문(첫 질문+추가)", **cnt(ChatMessage, ChatMessage.created_at, ChatMessage.role == "user")},
        {"menu": "상담(사주)", "feature": "추가 질문 과금", **credit_cnt("question")},
        {"menu": "상담(사주)", "feature": "미리보기 전체 열람(과금)", **credit_cnt("preview_reveal")},
        {"menu": "상담(사주)", "feature": "AI 영상 생성 시작", **cnt(SajuVideoJob, SajuVideoJob.created_at)},
        {"menu": "상담(사주)", "feature": "AI 영상 완성", **cnt(SajuVideoJob, SajuVideoJob.created_at, SajuVideoJob.status == "done")},
        {"menu": "궁합", "feature": "궁합 분석 실행", **cnt(CompatSession, CompatSession.created_at)},
        {"menu": "궁합", "feature": "상대 초대 링크 생성", **_invite_cnt()},
        {"menu": "오늘의 운세", "feature": "운세 조회", **tool_cnt(tool="today")},
        {"menu": "운세 캘린더", "feature": "캘린더 조회", **tool_cnt(tool="calendar")},
        {"menu": "신년운세", "feature": "신년 리포트 생성", **tool_cnt(tool="sinnyeon")},
        {"menu": "택일", "feature": "길일 찾기 실행", **tool_cnt(tool="taekil")},
        {"menu": "작명", "feature": "이름 추천 생성", **tool_cnt(tool="naming", kind="jakmyeong")},
        {"menu": "개명", "feature": "개명 진단 생성", **tool_cnt(tool="naming", kind="gaemyeong")},
        {"menu": "아호", "feature": "아호 추천 생성", **tool_cnt(tool="naming", kind="aho")},
        {"menu": "타로", "feature": "타로 리딩 실행", **cnt(TarotSession, TarotSession.created_at)},
        {"menu": "부적", "feature": "부적 발행", **tool_cnt(tool="amulet")},
        {"menu": "꿈해몽", "feature": "해몽 실행", **tool_cnt(tool="dream")},
        {"menu": "1:1 상담", "feature": "상담 세션", **cnt(ConsultationSession, ConsultationSession.requested_at)},
        {"menu": "1:1 상담", "feature": "예약(홀드 과금)", **credit_cnt("consultation_reserve")},
        {"menu": "공통 기능", "feature": "상담서 PDF 생성", **feat_counter("pdf")},
        {"menu": "공통 기능", "feature": "종합 감정서 생성", **feat_counter("report")},
        {"menu": "공통 기능", "feature": "공유 확정", **feat_counter("share")},
        {"menu": "공통 기능", "feature": "내 사주정보 기억(저장 보유 회원)",
         "today": 0, "week": 0, "total": remember_total},
        {"menu": "충전", "feature": "결제 승인", **cnt(Payment, Payment.created_at, Payment.status == "approved")},
        {"menu": "이용 후기", "feature": "후기 작성", **cnt(Review, Review.created_at)},
    ]

    return {
        "online_now": int(online_now),
        "today_visitors": int(today_visitors),
        "pwa": pwa,
        "total_devices": int(total_devices),
        "install_rate": install_rate,
        "menus": _agg("page"),
        "clicks": _agg("click"),
        "features": features,
        "as_of": now.isoformat(timespec="seconds"),
    }
