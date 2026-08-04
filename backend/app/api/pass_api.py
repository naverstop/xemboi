"""B-7 월 패스 API — 조회/구독/해지. 포인트 차감형(빌링키 불필요)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.deps import get_current_user, get_optional_user
from backend.app.repositories.auth_models import User
from backend.app.services import pass_service as svc
from backend.app.services import settings_service, share_service

router = APIRouter(prefix="/api/pass", tags=["pass"])


@router.get("")
def my_pass(db: Session = Depends(get_db), user: User | None = Depends(get_optional_user)) -> dict[str, Any]:
    """패스 상품 정보(가격·혜택) + 내 패스 상태(로그인 시)."""
    # [운영자 지적 2026-07-22] 혜택 표기가 부실했다 — 공유 쿼터는 '기본 몇 회 대비 얼마'인지 없어
    #   가치가 안 읽혔고, 무료 기본질문/할인도 실제 절약액이 안 보였다. 전부 설정값에서 산출해
    #   관리자가 값만 바꾸면 표시·과금이 함께 따라가게 한다(하드코딩 금지).
    # 공유 관련 값은 share_service 에서만 읽는다 — 표시와 실제 판정이 갈라지지 않게(과거 pdf.py 사례).
    base_share = share_service.base_limit()                  # 비패스 기본 공유 횟수(현재 5)
    pass_share = settings_service.get_int(db, "pass_share_quota", 20)
    disc = settings_service.get_int(db, "pass_followup_discount_pct", 30)
    free_basic = settings_service.get_int(db, "pass_free_basic_monthly", 5)
    free_amulet = settings_service.get_int(db, "pass_amulet_monthly", 1)
    basic_cost = settings_service.get_int(db, "credit_cost_basic", 1900)
    amulet_cost = settings_service.get_int(db, "amulet_cost_p", 3900)   # 부적 실제 차감 키(amulet_service 와 동일)
    plus_price = svc.price_p(db, "plus")

    lite_price = svc.price_p(db, "lite")
    if pass_share > base_share:
        mult = pass_share / max(1, base_share)
        share_line = (f"공유 월 {pass_share}회 (기본 {base_share}회 → {mult:.0f}배)" if mult >= 2
                      else f"공유 월 {pass_share}회 (기본 {base_share}회)")
    else:
        share_line = f"공유 월 {pass_share}회"
    lite_benefits = ["광고 제거", share_line]

    # 라이트도 '얼마나 이득인지' 한 줄로(운영자 지적) — 단 광고 제거·공유 확대는 개별 판매가가 없어
    # 플러스처럼 P 상당액을 매기면 근거 없는 숫자가 된다. 그래서 실제로 계산 가능한 값만 쓴다:
    #   ① 하루 환산가(가격 ÷ 기간) ② 공유 추가 횟수(패스 쿼터 − 기본 쿼터).
    lite_daily = round(lite_price / max(1, svc.PERIOD_DAYS))
    lite_extra_share = max(0, pass_share - base_share)
    lite_note = f"하루 {lite_daily:,}P — 광고 없이, 공유 월 {lite_extra_share}회 추가" \
        if lite_extra_share else f"하루 {lite_daily:,}P — 광고 없이"

    # [운영자 지적 2026-07-23] "라이트 혜택 전체" 한 줄로 뭉뚱그리니 9,900P 를 내는 사람이
    #   자기가 공유 확대를 받는지 몰랐다. 백엔드는 tier 구분 없이 이미 주고 있으므로(share_service.limit)
    #   표시에서도 핵심 혜택은 중복해서 명시한다.
    plus_benefits = ["라이트 혜택 전체 (광고 제거)", share_line]
    if free_basic > 0:
        plus_benefits.append(f"월 {free_basic}회 기본질문 무료 ({basic_cost:,}P × {free_basic} = {basic_cost*free_basic:,}P)")
    if disc > 0:
        plus_benefits.append(f"추가질문 {disc}% 할인 (기본질문 {basic_cost:,}P → {round(basic_cost*(100-disc)/100):,}P)")
    if free_amulet > 0:
        plus_benefits.append(f"월 {free_amulet}회 부적 발행 무료 ({amulet_cost:,}P)")

    # 월 절약액(무료 기본질문 + 무료 부적) — 패스가가 그보다 싸면 '남는 장사'를 한 줄로 보여준다.
    plus_worth = basic_cost * max(0, free_basic) + amulet_cost * max(0, free_amulet)
    plus_note = (f"이 혜택만 {plus_worth:,}P 상당 — 패스는 {plus_price:,}P"
                 if plus_worth > plus_price else None)

    products = {
        "lite": {
            "label": "라이트 패스", "price_p": lite_price, "period_days": svc.PERIOD_DAYS,
            "benefits": lite_benefits, "worth_note": lite_note,
        },
        "plus": {
            "label": "플러스 패스", "price_p": plus_price, "period_days": svc.PERIOD_DAYS,
            "benefits": plus_benefits, "worth_note": plus_note,
        },
    }
    mine = svc.to_dict(db, svc.get_pass(db, user.id)) if user else None
    return {"products": products, "mine": mine}


class SubscribeReq(BaseModel):
    tier: str = Field(pattern="^(lite|plus)$")


@router.post("/subscribe", status_code=201)
def subscribe(req: SubscribeReq, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        row = svc.subscribe(db, user, req.tier)
    except ValueError as e:
        if "insufficient" in str(e):
            raise HTTPException(status_code=402, detail="포인트가 부족해요. 충전 후 구독해 주세요.")
        raise HTTPException(status_code=400, detail=str(e))
    return {"mine": svc.to_dict(db, row)}


@router.post("/cancel")
def cancel(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        row = svc.cancel(db, user)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"mine": svc.to_dict(db, row)}
