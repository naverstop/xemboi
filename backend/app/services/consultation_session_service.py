"""1:1 상담 세션 수명주기 — 요청→수락(선차감)→진행→종료(정산). 서버 권위.

포인트 블록제: 수락 시 price_p 선차감(adjust_credit), 노쇼(미수락 타임아웃)·조기취소 시 멱등 환불.
종료 시 정산 원장 산출(수수료·세금, 표시용). 실시간 릴레이/카운트다운은 consultation_rt(WS 계층, 2a-2).
설계: [[consultation-1on1-plan]].
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from backend.app.repositories.auth_models import User
from backend.app.repositories.consultation_models import (
    Consultant,
    ConsultationMessage,
    ConsultationSession,
    ConsultationSettlement,
)
from backend.app.services import auth_service, consultation_service as csvc, settings_service

# 종료로 간주하는 상태(멱등 처리용)
_TERMINAL = {"completed", "cancelled", "no_show", "expired"}


def _now() -> datetime:
    return datetime.utcnow()


# ───────────────────────── 사용자 노출 메시지 로케일 ─────────────────────────
# ko 는 기존 문구를 바이트 동일하게 유지(한국 서비스 불변), vi 만 분기. 금액은 {need}/{have}
# 자리표시자에 로케일 구분자로 조판된 문자열을 넣는다(_grp). 키가 없으면 ko→키 순으로 폴백.
_MSGS: dict[str, dict[str, str]] = {
    "consultant_unavailable": {
        "ko": "상담 가능한 상담사가 아니에요.",
        "vi": "Tư vấn viên hiện không khả dụng.",
    },
    "insufficient_points": {
        "ko": "포인트가 부족해요. (필요 {need}P · 보유 {have}P)",
        "vi": "Không đủ điểm. (Cần {need} điểm · Hiện có {have} điểm)",
    },
    "already_active": {
        "ko": "이미 진행 중이거나 대기 중인 상담이 있어요.",
        "vi": "Bạn đang có một buổi tư vấn đang diễn ra hoặc đang chờ.",
    },
    "request_not_found": {
        "ko": "상담 요청을 찾을 수 없어요.",
        "vi": "Không tìm thấy yêu cầu tư vấn.",
    },
    "accept_not_yours": {
        "ko": "본인에게 요청된 상담만 수락할 수 있어요.",
        "vi": "Bạn chỉ có thể chấp nhận yêu cầu được gửi cho mình.",
    },
    "already_handled": {
        "ko": "이미 처리되었거나 만료된 요청이에요.",
        "vi": "Yêu cầu đã được xử lý hoặc đã hết hạn.",
    },
    "user_insufficient": {
        "ko": "사용자 포인트가 부족해 상담을 시작할 수 없어요.",
        "vi": "Người dùng không đủ điểm nên không thể bắt đầu buổi tư vấn.",
    },
    "process_not_yours": {
        "ko": "본인에게 요청된 상담만 처리할 수 있어요.",
        "vi": "Bạn chỉ có thể xử lý yêu cầu được gửi cho mình.",
    },
    "session_not_found": {
        "ko": "세션을 찾을 수 없어요.",
        "vi": "Không tìm thấy phiên tư vấn.",
    },
    "extend_not_yours": {
        "ko": "본인 상담만 연장할 수 있어요.",
        "vi": "Bạn chỉ có thể gia hạn buổi tư vấn của mình.",
    },
    "extend_only_active": {
        "ko": "진행 중인 상담만 연장할 수 있어요.",
        "vi": "Chỉ có thể gia hạn buổi tư vấn đang diễn ra.",
    },
    "extend_insufficient": {
        "ko": "포인트가 부족해 연장할 수 없어요. (필요 {need}P)",
        "vi": "Không đủ điểm để gia hạn. (Cần {need} điểm)",
    },
    "rating_range": {
        "ko": "평점은 1~5 사이여야 해요.",
        "vi": "Điểm đánh giá phải từ 1 đến 5.",
    },
    "rating_not_yours": {
        "ko": "본인 상담만 평가할 수 있어요.",
        "vi": "Bạn chỉ có thể đánh giá buổi tư vấn của mình.",
    },
    "rating_only_completed": {
        "ko": "종료된 상담만 평가할 수 있어요.",
        "vi": "Chỉ có thể đánh giá buổi tư vấn đã kết thúc.",
    },
    # 엔드포인트 계층에서 직접 raise 하는 참여자/권한 문구(consultation.py 공용).
    "view_only_own": {
        "ko": "본인 상담만 볼 수 있어요.",
        "vi": "Bạn chỉ có thể xem buổi tư vấn của mình.",
    },
    "end_only_own": {
        "ko": "본인 상담만 종료할 수 있어요.",
        "vi": "Bạn chỉ có thể kết thúc buổi tư vấn của mình.",
    },
    "cancel_only_own": {
        "ko": "본인 상담만 취소할 수 있어요.",
        "vi": "Bạn chỉ có thể hủy buổi tư vấn của mình.",
    },
    "report_only_own": {
        "ko": "본인 상담만 발급할 수 있어요.",
        "vi": "Bạn chỉ có thể phát hành bản tư vấn của mình.",
    },
    "no_convo": {
        "ko": "요약할 대화 내용이 없어요.",
        "vi": "Không có nội dung trò chuyện để tóm tắt.",
    },
    "consultant_only": {
        "ko": "입점 상담사 전용 기능이에요.",
        "vi": "Tính năng chỉ dành cho tư vấn viên.",
    },
}


def _grp(n: int, locale: str) -> str:
    """천단위 구분 — ko/기본은 콤마, vi 는 마침표(베트남 관습)."""
    s = f"{int(n):,}"
    return s.replace(",", ".") if locale == "vi" else s


def msg(key: str, locale: str = "ko", **kw: object) -> str:
    """상담 도메인 사용자 노출 문구(로케일). ko 기본·폴백. kw 는 자리표시자 치환값."""
    entry = _MSGS.get(key, {})
    text = entry.get(locale) or entry.get("ko") or key
    return text.format(**kw) if kw else text


# ───────────────────────── 조회/직렬화 ─────────────────────────

def get_session(db: Session, session_id: str) -> Optional[ConsultationSession]:
    return db.get(ConsultationSession, session_id)


def session_dict(db: Session, s: ConsultationSession) -> dict[str, Any]:
    c = db.get(Consultant, s.consultant_id)
    total_min = s.duration_min + (s.extended_min or 0)
    remaining_sec = None
    if s.status == "active" and s.started_at:
        elapsed = int((_now() - s.started_at).total_seconds())
        remaining_sec = max(0, total_min * 60 - elapsed)
    return {
        "id": s.id,
        "status": s.status,
        "specialty": s.specialty,
        "consultant_id": s.consultant_id,
        "consultant_name": c.business_name if c else None,
        "user_id": s.user_id,
        "price_p": s.price_p,
        "duration_min": s.duration_min,
        "extended_min": s.extended_min or 0,
        "total_min": total_min,
        "remaining_sec": remaining_sec,
        "started_at": s.started_at.isoformat() if s.started_at else None,
        "ended_at": s.ended_at.isoformat() if s.ended_at else None,
        "consent_at": s.consent_at.isoformat() if s.consent_at else None,
        "pdf_token": s.pdf_token,
    }


def is_participant(db: Session, s: ConsultationSession, user: User) -> bool:
    """세션의 사용자 본인 또는 담당 상담사인지(권한 게이트)."""
    if s.user_id == user.id:
        return True
    c = db.get(Consultant, s.consultant_id)
    return bool(c and c.user_id == user.id)


# ───────────────────────── 수명주기 ─────────────────────────

def request_session(
    db: Session, user: User, consultant_id: int, *, consent: bool = False, locale: str = "ko"
) -> ConsultationSession:
    """사용자 상담 요청 — 잔액·상담사 확인 후 requested 세션 생성(차감은 수락 시). locale 영속."""
    c = db.get(Consultant, consultant_id)
    if c is None or not c.is_active:
        raise LookupError(msg("consultant_unavailable", locale))
    price, dur, _comm = csvc.effective(db, c)
    bal = auth_service.get_balance(db, user.id)
    if bal < price:
        raise ValueError(msg("insufficient_points", locale, need=_grp(price, locale), have=_grp(bal, locale)))
    # 사용자가 이미 진행/대기 중인 세션이 있으면 중복 방지
    active = db.execute(
        select(ConsultationSession).where(
            ConsultationSession.user_id == user.id,
            ConsultationSession.status.in_(["requested", "accepted", "active"]),
        )
    ).scalars().first()
    if active is not None:
        raise ValueError(msg("already_active", locale))
    s = ConsultationSession(
        id=uuid.uuid4().hex,
        user_id=user.id,
        consultant_id=c.id,
        specialty=c.specialty,
        locale=locale if locale in ("ko", "vi") else "ko",
        status="requested",
        price_p=price,
        duration_min=dur,
        consent_at=_now() if consent else None,
        requested_at=_now(),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def accept_session(
    db: Session, session_id: str, consultant: Consultant, *, locale: str = "ko"
) -> ConsultationSession:
    """상담사 수락 — 담당 확인 → 사용자 포인트 선차감 → active. (요건 ⑪ 수락 시 채팅 가능)"""
    s = db.get(ConsultationSession, session_id, with_for_update=True)  # 세션행 잠금 — 동시 cancel/decline 과 직렬화(status resurrection·이중지출 방지)
    if s is None:
        raise LookupError(msg("request_not_found", locale))
    if s.consultant_id != consultant.id:
        raise PermissionError(msg("accept_not_yours", locale))
    if s.status != "requested":
        raise ValueError(msg("already_handled", locale))
    # 선차감(원자적). 잔액 부족이면 요청 취소 처리.
    try:
        auth_service.adjust_credit(db, s.user_id, -s.price_p, reason="consultation", ref_id=s.id)
    except ValueError:
        s.status = "cancelled"
        db.commit()
        raise ValueError(msg("user_insufficient", locale))
    now = _now()
    s.status = "active"
    s.accepted_at = now
    s.started_at = now
    s.credits_charged = s.price_p
    consultant.presence = "busy"  # 상담 중 — 사용자 리스트에 '상담중' 표기(요건 ⑫)
    db.commit()
    db.refresh(s)
    return s


def decline_session(
    db: Session, session_id: str, consultant: Consultant, *, locale: str = "ko"
) -> ConsultationSession:
    """상담사 거절 — requested 상태에서만. 즉시 상담은 차감 전이라 환불 불필요,
    예약 전환 세션(선결제)은 전액 환불."""
    s = db.get(ConsultationSession, session_id, with_for_update=True)  # 동시 취소/거절 직렬화(이중환불 차단)
    if s is None:
        raise LookupError(msg("request_not_found", locale))
    db.refresh(s)  # 락 후 최신값(preload stale 방지)
    if s.consultant_id != consultant.id:
        raise PermissionError(msg("process_not_yours", locale))
    if s.status == "requested":
        s.status = "cancelled"
        db.commit()
        db.refresh(s)
    return s


def cancel_requested(db: Session, session_id: str, *, no_show: bool = False) -> Optional[ConsultationSession]:
    """미수락 타임아웃/사용자 취소 — requested 상태만.
    즉시 상담은 차감 전이라 환불 없음, 예약 전환 세션(선결제)은 전액 환불."""
    # 행잠금 — session_driver(3s)·reservation_driver(30s) 두 스윕이 같은 grace 임계에서 동시에
    #   cancel_requested 를 호출해 _refund 가 두 번 실행(이중환불)되던 것을 직렬화로 차단.
    s = db.get(ConsultationSession, session_id, with_for_update=True)
    if s is None:
        return s
    db.refresh(s)  # 락 획득 후 최신값 재로드 — 호출부가 preload 한 stale 인스턴스로 이중환불되던 것 차단(accept_session 패턴)
    if s.status != "requested":
        return s
    # 사용자 자발 취소(no_show=False)가 예약전환 세션이면 예약 late-refund 정책 비율 적용
    #   (start_at 후 세션취소로 100% 환불받는 우회 차단). 상담사 미수락 노쇼(no_show=True)는 서비스 미제공이라 100%.
    ratio = 1.0
    if not no_show and getattr(s, "reservation_id", None):
        ratio = _reserve_refund_ratio(db, s.reservation_id)
    _refund(db, s, ratio, reason="consultation_reserve_refund")  # 선결제 없으면 no-op(멱등)
    s.status = "no_show" if no_show else "cancelled"
    db.commit()
    db.refresh(s)
    return s


def _refund(db: Session, s: ConsultationSession, ratio: float, reason: str) -> int:
    """멱등 환불 — 이미 환불했으면 0. ratio(0~1) 비율만큼 환급."""
    if s.refunded or not s.credits_charged:
        return 0
    amount = int(round(s.credits_charged * max(0.0, min(1.0, ratio))))
    if amount > 0:
        auth_service.adjust_credit(db, s.user_id, amount, reason=reason, ref_id=s.id)
    s.refunded = True
    s.refund_p = amount
    return amount


def _reserve_refund_ratio(db: Session, slot_id: str) -> float:
    """예약 슬롯 start_at 기준 사용자취소 환불비율(full/late) — cancel_by_user 와 동일 정책.

    예약전환 세션(start_at 이미 도래)을 사용자가 취소할 때, 예약취소 late-refund(예:50%) 대신
    100% 환불받는 우회를 막기 위해 슬롯 정책 비율을 적용한다. 조회 실패 시 보수적으로 1.0(사용자 불이익 방지)."""
    try:
        from backend.app.repositories.consultation_models import ConsultationSlot
        from backend.app.services import consultation_reservation_service as _rsvc
        slot = db.get(ConsultationSlot, slot_id)
        if slot is None or slot.start_at is None:
            return 1.0
        pol = _rsvc.reserve_policy(db)
        hours_left = (slot.start_at - _now()).total_seconds() / 3600.0
        return 1.0 if hours_left >= pol["full_refund_hours"] else max(0, min(100, pol["late_refund_pct"])) / 100.0
    except Exception:  # noqa: BLE001
        return 1.0


def end_session(
    db: Session, session_id: str, *, reason: str = "user_end", by_consultant: bool = False, locale: str = "ko"
) -> ConsultationSession:
    """상담 종료 — 경과시간 확정 + 정산 산출 + 파기예정 설정. 멱등.

    세션 행을 FOR UPDATE 로 잠가 _persist_message(동일 행 잠금)와 직렬화 — 종료 커밋과
    인플라이트 메시지 저장의 레이스를 차단한다."""
    s = db.execute(
        select(ConsultationSession).where(ConsultationSession.id == session_id).with_for_update()
    ).scalars().first()
    if s is None:
        raise LookupError("세션을 찾을 수 없어요.")
    db.refresh(s)  # 락 후 최신값 재로드 — 라우터가 get_session 으로 preload 한 stale 인스턴스(동시 accept/cancel
    #   반영 전 status='requested')로 활성세션을 취소·이중환불하던 것 차단(accept/cancel/decline 과 동일 패턴).
    if s.status in _TERMINAL:
        return s
    now = _now()
    # 미수락(requested·무선차감) 세션 종료 = 취소로 처리(D4) — 결제가 없었으므로 정산·매출을 만들지 않는다.
    # (선결제 예약 세션은 credits_charged>0 이라 아래 정상 종료 경로로 감. 여기 걸리는 건 즉시상담 미수락뿐.)
    if s.status == "requested":
        # 미수락(아직 accept 전) 세션 종료 = 취소(정산 없음 → 유령정산·상담사 파밍 방지).
        #   · 사용자 자발 종료(예약전환) = late-refund 정책 비율(start_at 후 /end 로 100% 환불받는 우회 차단).
        #   · 상담사 종료 = 사실상 거절/미출석이므로 100% 환불(사용자에게 정책 페널티 전가 금지).
        #   즉시상담은 credits_charged=0 → 어느 쪽이든 no-op.
        if by_consultant or not getattr(s, "reservation_id", None):
            _r = 1.0
        else:
            _r = _reserve_refund_ratio(db, s.reservation_id)
        _refund(db, s, _r, reason="consultation_reserve_refund")
        s.status = "cancelled"
        s.ended_at = now
        db.commit()
        db.refresh(s)
        return s
    s.ended_at = now
    if s.started_at:
        s.elapsed_sec = int((now - s.started_at).total_seconds())
    retention = settings_service.get_int(db, "consultation_retention_days", 7)
    s.purge_after = now + timedelta(days=retention)
    # 상담사 참여 검증(머니세이프티) — 수락(active) 후 상담사가 한 마디도 안 하고 끝났으면 서비스 미제공:
    #   전액 환불 + 정산 미생성 + no_show 처리(매출·상담건수·평점 집계에서 제외). 상담사 잠수 파밍 차단.
    #   (스키마 무변경 — 상담사 발화 메시지 유무로 판정. 정상 종료는 completed+정산 그대로.)
    consultant_spoke = db.execute(
        select(ConsultationMessage.id)
        .where(
            ConsultationMessage.session_id == s.id,
            ConsultationMessage.sender == "consultant",
        )
        .limit(1)
    ).first() is not None
    if not consultant_spoke and (s.credits_charged or 0) > 0:
        _refund(db, s, 1.0, reason="consultation_no_reply_refund")  # 멱등 전액 환불
        s.status = "no_show"
    else:
        s.status = "completed"
        _ensure_settlement(db, s)
    # 상담사 busy 해제 — 콘솔이 연결돼 있으면 online, 아니면 콘솔 disconnect 가 offline 처리.
    c = db.get(Consultant, s.consultant_id)
    if c is not None and c.presence == "busy":
        c.presence = "online"
    db.commit()
    db.refresh(s)
    return s


def _ensure_settlement(db: Session, s: ConsultationSession) -> None:
    """세션 정산 원장 1회 생성(멱등)."""
    exists = db.execute(
        select(ConsultationSettlement).where(ConsultationSettlement.session_id == s.id)
    ).scalars().first()
    if exists is not None:
        return
    revenue = s.credits_charged or s.price_p
    if revenue <= 0:
        return
    c = db.get(Consultant, s.consultant_id)
    _p, _d, comm_pct = csvc.effective(db, c) if c else (0, 0, settings_service.get_int(db, "consultation_commission_pct", 20))
    tax_pct = settings_service.get_float(db, "consultation_tax_pct", 3.3)
    calc = csvc.compute_settlement(revenue, comm_pct, tax_pct)
    db.add(
        ConsultationSettlement(
            session_id=s.id,
            consultant_id=s.consultant_id,
            revenue_p=calc["revenue_p"],
            commission_pct=calc["commission_pct"],
            commission_p=calc["commission_p"],
            taxable_p=calc["taxable_p"],
            tax_pct=calc["tax_pct"],
            tax_p=calc["tax_p"],
            payout_p=calc["payout_p"],
            status="pending",
        )
    )


def extend_session(db: Session, session_id: str, user: User, *, locale: str = "ko") -> ConsultationSession:
    """블록 연장 — 동일 단가 추가 차감 + duration 만큼 시간 연장(active 상태만)."""
    # 행잠금 — 더블클릭/재시도로 동시 연장 시 extended_min read-modify-write lost-update(2P 차감·1블록만 반영) 차단.
    s = db.get(ConsultationSession, session_id, with_for_update=True)
    if s is None:
        raise LookupError(msg("session_not_found", locale))
    db.refresh(s)  # 락 후 최신값(preload stale 방지 — extended_min/credits_charged lost-update 차단)
    if s.user_id != user.id:
        raise PermissionError(msg("extend_not_yours", locale))
    if s.status != "active":
        raise ValueError(msg("extend_only_active", locale))
    try:
        auth_service.adjust_credit(db, user.id, -s.price_p, reason="consultation_extend", ref_id=s.id)
    except ValueError:
        raise ValueError(msg("extend_insufficient", locale, need=_grp(s.price_p, locale)))
    s.extended_min = (s.extended_min or 0) + s.duration_min
    s.credits_charged = (s.credits_charged or 0) + s.price_p
    db.commit()
    db.refresh(s)
    return s


# ───────────────────────── 메시지 ─────────────────────────

def add_message(db: Session, session_id: str, sender: str, content: str) -> ConsultationMessage:
    m = ConsultationMessage(session_id=session_id, sender=sender, content=content)
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def list_messages(db: Session, session_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ConsultationMessage)
        .where(ConsultationMessage.session_id == session_id)
        .order_by(ConsultationMessage.id.asc())
    ).scalars().all()
    return [
        {"id": m.id, "sender": m.sender, "content": m.content, "created_at": m.created_at.isoformat()}
        for m in rows
    ]


def transcript_for_summary(db: Session, session_id: str) -> list[dict[str, str]]:
    """요약 PDF용 — user→'user' / consultant→'assistant' 매핑(system 제외). 요건 ⑧."""
    rows = db.execute(
        select(ConsultationMessage)
        .where(ConsultationMessage.session_id == session_id)
        .order_by(ConsultationMessage.id.asc())
    ).scalars().all()
    out: list[dict[str, str]] = []
    for m in rows:
        if m.sender == "user":
            out.append({"role": "user", "content": m.content})
        elif m.sender == "consultant":
            out.append({"role": "assistant", "content": m.content})
    return out


# ───────────────────────── 상담사 접수함 ─────────────────────────

def consultant_pending(db: Session, consultant: Consultant) -> list[dict[str, Any]]:
    """상담사 접수함 — 대기/진행 중 세션(요건 ⑩ 접수 알람 목록)."""
    rows = db.execute(
        select(ConsultationSession)
        .where(
            ConsultationSession.consultant_id == consultant.id,
            ConsultationSession.status.in_(["requested", "active"]),
        )
        .order_by(ConsultationSession.requested_at.asc())
    ).scalars().all()
    return [session_dict(db, s) for s in rows]


def submit_rating(
    db: Session, session_id: str, user: User, rating: int, *, locale: str = "ko"
) -> ConsultationSession:
    """사용자 만족도 평점(1~5) — 종료된 본인 상담만. 간판 만족도 집계에 반영."""
    if rating < 1 or rating > 5:
        raise ValueError(msg("rating_range", locale))
    s = db.get(ConsultationSession, session_id)
    if s is None:
        raise LookupError(msg("session_not_found", locale))
    if s.user_id != user.id:
        raise PermissionError(msg("rating_not_yours", locale))
    if s.status != "completed":
        raise ValueError(msg("rating_only_completed", locale))
    s.rating = int(rating)
    db.commit()
    db.refresh(s)
    return s


def list_user_sessions(db: Session, user: User, limit: int = 30) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ConsultationSession)
        .where(ConsultationSession.user_id == user.id)
        .order_by(ConsultationSession.requested_at.desc())
        .limit(limit)
    ).scalars().all()
    return [session_dict(db, s) for s in rows]


# ───────────────────────── 7일 파기 배치 (개인정보 준수) ─────────────────────────

# 요약 PDF 저장 경로(pdf.py 와 동일: 저장소 루트/data/pdf)
_PDF_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "pdf"))


def _delete_pdf(token: str) -> int:
    """요약 PDF 파일(+.name) 삭제. 삭제한 pdf 수(0/1) 반환."""
    n = 0
    for ext in (".pdf", ".name"):
        p = os.path.join(_PDF_DIR, f"{token}{ext}")
        try:
            if os.path.isfile(p):
                os.remove(p)
                if ext == ".pdf":
                    n = 1
        except OSError:
            pass
    return n


def purge_expired(db: Session, *, now: Optional[datetime] = None, limit: int = 1000) -> dict[str, int]:
    """보관기간(consultation_retention_days, 기본 7일) 지난 상담의 대화·요약 PDF를 **완전 파기**.

    입장 전 동의 게이트에서 고지한 '대화는 7일 후 자동·완전 파기' 준수(개인정보). 세션 메타(정산·시각)는
    보존하고 PII(대화 메시지 + 요약 PDF 파일)만 하드 삭제 후 purged=True. 종료 세션은 purge_after 기준,
    비정상 잔류(장기 미종료) 세션은 requested_at + retention+1일 안전망으로도 파기한다.

    반환: {sessions, messages, pdfs}. 스케줄러(04:20)·수동 호출 공용. LLM/GPU 없음(순수 DB+파일).
    """
    now = now or datetime.utcnow()
    retention = settings_service.get_int(db, "consultation_retention_days", 7)
    abandoned_cutoff = now - timedelta(days=retention + 1)
    rows = db.execute(
        select(ConsultationSession)
        .where(
            ConsultationSession.purged.is_(False),
            or_(
                and_(
                    ConsultationSession.purge_after.isnot(None),
                    ConsultationSession.purge_after < now,
                ),
                ConsultationSession.requested_at < abandoned_cutoff,
            ),
        )
        .limit(limit)
    ).scalars().all()
    n_sess = n_msg = n_pdf = 0
    for s in rows:
        res = db.execute(delete(ConsultationMessage).where(ConsultationMessage.session_id == s.id))
        n_msg += int(res.rowcount or 0)
        if s.pdf_token:
            n_pdf += _delete_pdf(s.pdf_token)
            s.pdf_token = None
        s.purged = True
        n_sess += 1
    if n_sess:
        db.commit()
    return {"sessions": n_sess, "messages": n_msg, "pdfs": n_pdf}
