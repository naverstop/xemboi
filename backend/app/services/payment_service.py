"""토스페이먼츠 결제 서비스.

흐름:
1. 회원이 패키지 선택 → create_order: pending 상태 Payment row 생성, order_id 반환
2. 프론트 토스 위젯 결제 완료 → success_url 로 paymentKey/orderId/amount 콜백
3. 프론트가 POST /api/payments/confirm 호출 → confirm_payment 가 토스 API 호출 + 크레딧 충전 + ads_hidden=True
4. (옵션) 토스 웹훅 → handle_webhook 으로 status 동기화

토스 키 미설정(test_sk_DUMMY_*) 시 confirm_payment 가 mock 승인 (개발용).
"""
from __future__ import annotations

import base64
import secrets
from datetime import datetime
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.repositories.auth_models import Payment, User
from backend.app.services import auth_service


def _vat(base: int) -> tuple[int, int, int]:
    """공급가(base) → (공급가, 부가세, 결제총액). 결제금액엔 부가세 포함(예: 10,000 → 1,000 → 11,000)."""
    s = get_settings()
    supply = int(base)
    vat = round(supply * max(0, int(s.vat_pct)) / 100)
    return supply, vat, supply + vat


def list_packages() -> list[dict[str, Any]]:
    """패키지 목록 — 표시용으로 부가세 포함 결제총액(total)·부가세(vat)를 함께 내려준다.
    amount=공급가(=적립 P), total=실제 결제금액(부가세 포함)."""
    s = get_settings()
    out: list[dict[str, Any]] = []
    for p in s.payment_packages:
        supply, vat, total = _vat(int(p["amount"]))
        out.append({**p, "supply_amount": supply, "vat_amount": vat, "total_amount": total, "vat_pct": int(s.vat_pct)})
    return out


def get_package(amount: int) -> Optional[dict[str, Any]]:
    """공급가(amount, 프론트가 보내는 패키지 식별값)로 패키지 조회."""
    for p in list_packages():
        if int(p["amount"]) == amount:
            return p
    return None


def _new_order_id() -> str:
    return f"ord_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(4)}"


def create_order(db: Session, user: User, amount: int) -> dict[str, Any]:
    """패키지 결제 주문 생성. pending 상태로 Payment row 만들고 order_id 반환."""
    pkg = get_package(amount)
    if pkg is None:
        raise ValueError(f"invalid amount: {amount}")
    s = get_settings()
    order_id = _new_order_id()
    supply, vat, total = _vat(int(pkg["amount"]))
    p = Payment(
        user_id=user.id,
        order_id=order_id,
        amount=total,                      # 실제 결제금액(부가세 포함)
        credit_granted=int(pkg["credits"]),  # 적립 포인트(공급가 기준)
        status="pending",
        raw_payload={"package": pkg, "supply_amount": supply, "vat_amount": vat, "vat_pct": int(s.vat_pct)},
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return {
        "order_id": order_id,
        "amount": p.amount,            # 결제금액(부가세 포함)
        "supply_amount": supply,       # 공급가
        "vat_amount": vat,             # 부가세
        "vat_pct": int(s.vat_pct),
        "credits": p.credit_granted,   # 적립 포인트
        "client_key": s.toss_client_key,
        "success_url": s.payment_success_url,
        "fail_url": s.payment_fail_url,
        "order_name": f"사주 에이전트 {pkg['label']} 충전(부가세 포함)",
        "customer_email": user.email,
        "customer_name": user.nickname or user.email.split("@")[0],
    }


def _is_dummy_key(key: str) -> bool:
    return "DUMMY" in key or not key


_http_client: "httpx.Client | None" = None


def _http() -> httpx.Client:
    """모듈 공유 httpx 클라이언트 — 호출당 신규 소켓/TLS 핸드셰이크 대신 커넥션 재사용."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=httpx.Timeout(15.0))
    return _http_client


def _call_toss_confirm(payment_key: str, order_id: str, amount: int) -> dict[str, Any]:
    s = get_settings()
    auth = base64.b64encode(f"{s.toss_secret_key}:".encode()).decode()
    r = _http().post(
        f"{s.toss_api_base}/v1/payments/confirm",
        json={"paymentKey": payment_key, "orderId": order_id, "amount": amount},
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        timeout=15.0,
    )
    data = r.json()
    if r.status_code >= 400:
        # 토스 원문(내부 코드·필드)은 서버 로그로만, 클라엔 일반 메시지(정찰 차단).
        import logging
        logging.getLogger("saju.payment").warning("toss confirm failed: %s %s", r.status_code, data)
        raise RuntimeError("결제 승인에 실패했어요. 잠시 후 다시 시도하거나 고객센터로 문의해 주세요.")
    return data


def confirm_payment(
    db: Session,
    user: User,
    payment_key: str,
    order_id: str,
    amount: int,
) -> dict[str, Any]:
    """결제 승인. 멱등 처리: 이미 approved 면 그대로 반환."""
    s = get_settings()
    # 이중적립(TOCTOU) 차단: 결제행을 FOR UPDATE 로 잠가 동일 order_id 동시 confirm 을 직렬화.
    # 먼저 들어온 요청이 승인·적립·커밋할 때까지 두 번째 요청은 대기 후 'approved' 를 보고 멱등 반환.
    p = db.execute(
        select(Payment).where(Payment.order_id == order_id).with_for_update()
    ).scalar_one_or_none()
    if p is None:
        raise LookupError(f"order not found: {order_id}")
    if p.user_id != user.id:
        raise PermissionError("order owner mismatch")
    if p.amount != amount:
        raise ValueError(f"amount mismatch: order={p.amount}, request={amount}")
    if p.status == "approved":
        # 이미 처리됨 (멱등)
        return {
            "status": "approved",
            "order_id": order_id,
            "amount": p.amount,
            "credits_granted": p.credit_granted,
            "balance": auth_service.get_balance(db, user.id),
            "already": True,
        }
    if p.status in ("failed", "cancelled", "refunded"):
        raise ValueError(f"order not approvable: status={p.status}")

    # 토스 호출 (또는 더미 mock). fail-closed: 더미/빈 키면 명시적 allow_mock_payment 가 켜졌을 때만
    # mock 승인. 미설정(기본) 시 무결제 크레딧 발행을 차단 — 외부 공개 인스턴스(APP_ENV 무관) 보호.
    if _is_dummy_key(s.toss_secret_key):
        if not getattr(s, "allow_mock_payment", False):
            raise RuntimeError(
                "payment not configured: 실 토스 시크릿 키 미설정 — 결제 승인 불가"
                "(테스트 mock 은 ALLOW_MOCK_PAYMENT=true 에서만)."
            )
        toss_data: dict[str, Any] = {
            "mock": True,
            "paymentKey": payment_key,
            "orderId": order_id,
            "totalAmount": amount,
            "approvedAt": datetime.utcnow().isoformat() + "Z",
        }
    else:
        toss_data = _call_toss_confirm(payment_key, order_id, amount)

    # 크레딧 충전
    new_balance = auth_service.adjust_credit(
        db, user.id, p.credit_granted, reason="purchase", ref_id=order_id
    )
    # 유료결제 → 회원등급 승급(계획 5.1: 연간/우수)
    pkg = (p.raw_payload or {}).get("package")
    auth_service.apply_payment_grade(db, user, pkg)
    # Payment row 업데이트
    p.toss_payment_key = payment_key
    p.status = "approved"
    p.approved_at = datetime.utcnow()
    existing = p.raw_payload or {}
    existing["confirm"] = toss_data
    p.raw_payload = existing
    # 광고 숨김은 잔액(>0) 또는 관리자 강제(User.ads_hidden=True) 기반으로 동적 판정
    db.commit()
    return {
        "status": "approved",
        "order_id": order_id,
        "amount": p.amount,
        "credits_granted": p.credit_granted,
        "balance": new_balance,
        "already": False,
        "mock": _is_dummy_key(s.toss_secret_key),
    }


def _call_toss_cancel(payment_key: str, reason: str, cancel_amount: int | None = None) -> dict[str, Any]:
    s = get_settings()
    auth = base64.b64encode(f"{s.toss_secret_key}:".encode()).decode()
    body: dict[str, Any] = {"cancelReason": reason}
    if cancel_amount is not None:
        body["cancelAmount"] = int(cancel_amount)  # 부분취소(미지정 시 전체취소)
    r = _http().post(
        f"{s.toss_api_base}/v1/payments/{payment_key}/cancel",
        json=body,
        headers={"Authorization": f"Basic {auth}", "Content-Type": "application/json"},
        timeout=15.0,
    )
    data = r.json()
    if r.status_code >= 400:
        raise RuntimeError(f"toss cancel failed: {r.status_code} {data}")
    return data


def refund_payment(
    db: Session, order_id: str, reason: str = "admin refund"
) -> dict[str, Any]:
    """관리자 환불(계획 7-E.3).

    환불 대상 = **미사용 '결제' 크레딧** 만 = min(현재 잔액, 그 결제로 지급한 크레딧).
      - 기본제공(무료) 포인트는 환불 대상이 아니다(결제크레딧 상한으로 자동 제외).
      - 이미 사용한 분은 환불 대상이 아니다(잔액 상한으로 자동 제외).
    → 잔액 전체를 환불하면 무료/사용분까지 현금 환불돼 손해이므로 절대 그렇게 하지 않는다.
    토스는 그 금액만큼 부분취소(전액과 같으면 전체취소). 1 크레딧 = 1원.
    """
    s = get_settings()
    p = db.execute(select(Payment).where(Payment.order_id == order_id)).scalar_one_or_none()
    if p is None:
        raise LookupError(f"order not found: {order_id}")
    if p.status == "refunded":
        return {"status": "refunded", "order_id": order_id, "already": True}
    if p.status != "approved":
        raise ValueError(f"order not refundable: status={p.status}")

    # 환불 대상 크레딧: 미사용 결제 크레딧만. 기본제공·사용분 제외.
    bal = auth_service.get_balance(db, p.user_id)
    refundable = min(max(bal, 0), int(p.credit_granted))
    if refundable <= 0:
        raise ValueError(
            "환불 가능 금액이 없습니다 — 결제 크레딧을 모두 사용했거나 잔액이 없습니다. "
            "(기본제공 포인트·사용분은 환불 대상이 아닙니다.)"
        )
    # 현금 환불액(원)은 결제금액(p.amount, VAT 포함) 기준. 크레딧(credit_granted)은 공급가(VAT 제외)라
    # 환불 크레딧을 그대로 취소액으로 쓰면 VAT만큼 덜 돌려준다 → 비례 결제금액으로 환산.
    #   · 미사용 전액환불(refundable==credit_granted): 결제 전액(VAT 포함) 전체취소
    #   · 부분환불: 결제금액 × (환불크레딧/지급크레딧) 비례 부분취소(VAT 포함분 반영)
    granted = max(int(p.credit_granted), 1)
    full = refundable >= int(p.credit_granted)
    cancel_krw = int(p.amount) if full else round(int(p.amount) * refundable / granted)

    if _is_dummy_key(s.toss_secret_key) or not p.toss_payment_key:
        cancel_data: dict[str, Any] = {
            "mock": True, "canceledAt": datetime.utcnow().isoformat() + "Z",
            "cancelAmount": cancel_krw, "partial": not full,
        }
    else:
        cancel_data = _call_toss_cancel(p.toss_payment_key, reason, None if full else cancel_krw)

    # 크레딧 회수 = 미사용 결제 크레딧(공급가 기준). 현금 환불액(cancel_krw)은 VAT 포함이라 별개.
    auth_service.adjust_credit(db, p.user_id, -refundable, reason="refund", ref_id=order_id)
    p.status = "refunded"
    existing = p.raw_payload or {}
    existing["refund"] = {
        "reason": reason, "data": cancel_data,
        "recovered": refundable, "refunded_krw": cancel_krw, "partial": not full,
    }
    p.raw_payload = existing
    db.commit()
    return {
        "status": "refunded",
        "order_id": order_id,
        "recovered_credits": refundable,
        "refunded_krw": cancel_krw,
        "partial": not full,
        "already": False,
        "mock": _is_dummy_key(s.toss_secret_key),
    }


def list_my_payments(db: Session, user: User, limit: int = 30) -> list[dict[str, Any]]:
    rows = db.execute(
        select(Payment)
        .where(Payment.user_id == user.id)
        .order_by(Payment.id.desc())
        .limit(limit)
    ).scalars().all()
    return [
        {
            "id": p.id,
            "order_id": p.order_id,
            "amount": p.amount,
            "credit_granted": p.credit_granted,
            "status": p.status,
            "created_at": p.created_at.isoformat(),
            "approved_at": p.approved_at.isoformat() if p.approved_at else None,
        }
        for p in rows
    ]


def handle_webhook(db: Session, body: dict[str, Any]) -> dict[str, Any]:
    """토스 웹훅. PAYMENT_STATUS_CHANGED 등을 받아 status 동기화.

    토스 v2 웹훅 페이로드 예: {"eventType":"PAYMENT_STATUS_CHANGED","data":{"orderId":"...","status":"DONE"|"CANCELED"...,"paymentKey":"..."}}
    """
    data = body.get("data") or {}
    order_id = data.get("orderId")
    if not order_id:
        return {"ignored": True, "reason": "no orderId"}
    # 멱등·동시성: 결제행을 잠가 중복 웹훅의 이중 회수·경쟁을 차단.
    p = db.execute(
        select(Payment).where(Payment.order_id == order_id).with_for_update()
    ).scalar_one_or_none()
    if p is None:
        return {"ignored": True, "reason": "order not found"}
    toss_status = (data.get("status") or "").upper()
    mapping = {
        "DONE": "approved",
        "CANCELED": "cancelled",
        "PARTIAL_CANCELED": "cancelled",
        "ABORTED": "failed",
        "EXPIRED": "failed",
    }
    new_status = mapping.get(toss_status)
    if new_status and p.status != new_status:
        # 토스/카드사 직접취소(CANCELED)로 현금 환불됐는데 발급 크레딧이 남으면 손해 →
        # approved 였던 결제분 크레딧을 잔액 한도 내에서 회수하고 refunded 로 마킹(멱등).
        if new_status == "cancelled" and p.status == "approved" and int(p.credit_granted or 0) > 0:
            recover = min(auth_service.get_balance(db, p.user_id), int(p.credit_granted or 0))
            if recover > 0:
                try:
                    auth_service.adjust_credit(
                        db, p.user_id, -recover, reason="webhook_cancel", ref_id=order_id
                    )
                except ValueError:
                    pass  # 회수 가능한 만큼만(잔액이 이미 소진된 경우)
            new_status = "refunded"
        p.status = new_status
        existing = p.raw_payload or {}
        existing.setdefault("webhooks", []).append({
            "ts": datetime.utcnow().isoformat() + "Z",
            "event": body.get("eventType"),
            "status": toss_status,
        })
        p.raw_payload = existing
        db.commit()
    return {"ok": True, "order_id": order_id, "status": p.status}
