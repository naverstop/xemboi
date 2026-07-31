"""고객센터(CONTACT US) — 문의 게시판 + 관리자 메일 알림(SMTP).

- 문의 접수는 항상 DB에 저장된다(게시판). 메일 발송 실패는 접수 자체를 막지 않는다.
- SMTP 미설정(mock) 시 실제 발송 대신 로그만 남긴다 — 결제(토스)·소셜 로그인과 동일한 mock 정책.
- 알림 수신 메일은 SupportRecipient 테이블로 관리자 CRUD.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formatdate
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.repositories.auth_models import SupportRecipient, SupportTicket

log = logging.getLogger("saju.support")

CATEGORY_LABELS: dict[str, str] = {
    "refund": "환불 요청",
    "payment": "결제 오류",
    "account": "계정 문의",
    "etc": "기타 문의",
}
STATUS_LABELS: dict[str, str] = {
    "received": "접수",
    "in_progress": "처리중",
    "resolved": "처리완료",
    "rejected": "반려",
}
_VALID_CATEGORY = set(CATEGORY_LABELS)
_VALID_STATUS = set(STATUS_LABELS)


# ───────────────────────── 직렬화 ─────────────────────────
def to_dict(t: SupportTicket) -> dict[str, Any]:
    return {
        "id": t.id,
        "user_id": t.user_id,
        "category": t.category,
        "category_label": CATEGORY_LABELS.get(t.category, t.category),
        "contact_email": t.contact_email,
        "contact_name": t.contact_name,
        "order_id": t.order_id,
        "amount": t.amount,
        "title": t.title,
        "message": t.message,
        "status": t.status,
        "status_label": STATUS_LABELS.get(t.status, t.status),
        "admin_note": t.admin_note,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


# ───────────────────────── 문의(티켓) ─────────────────────────
def create_ticket(
    db: Session,
    *,
    user_id: int | None,
    category: str,
    contact_email: str,
    contact_name: str | None,
    order_id: str | None,
    amount: int | None,
    title: str,
    message: str,
) -> SupportTicket:
    cat = category if category in _VALID_CATEGORY else "etc"
    t = SupportTicket(
        user_id=user_id,
        category=cat,
        contact_email=contact_email.strip(),
        contact_name=(contact_name or None),
        order_id=(order_id or None),
        amount=amount,
        title=title.strip()[:200],
        message=message.strip(),
        status="received",
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def list_tickets(
    db: Session, *, status: str | None = None, limit: int = 50, offset: int = 0
) -> tuple[list[dict[str, Any]], int]:
    """관리자 — 전체 문의 목록(최신순)."""
    base = select(SupportTicket)
    cnt = select(func.count(SupportTicket.id))
    if status and status in _VALID_STATUS:
        base = base.where(SupportTicket.status == status)
        cnt = cnt.where(SupportTicket.status == status)
    total = db.execute(cnt).scalar_one()
    rows = (
        db.execute(base.order_by(SupportTicket.id.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return [to_dict(t) for t in rows], int(total)


def list_user_tickets(db: Session, user_id: int, limit: int = 50) -> list[dict[str, Any]]:
    """회원 본인 문의 내역(게시판)."""
    rows = (
        db.execute(
            select(SupportTicket)
            .where(SupportTicket.user_id == user_id)
            .order_by(SupportTicket.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [to_dict(t) for t in rows]


def get_ticket(db: Session, ticket_id: int) -> SupportTicket | None:
    return db.get(SupportTicket, ticket_id)


def update_ticket(
    db: Session, ticket_id: int, *, status: str | None = None, admin_note: str | None = None
) -> dict[str, Any]:
    t = db.get(SupportTicket, ticket_id)
    if t is None:
        raise LookupError("문의를 찾을 수 없어요.")
    if status is not None:
        if status not in _VALID_STATUS:
            raise ValueError("invalid status")
        t.status = status
    if admin_note is not None:
        t.admin_note = admin_note
    db.commit()
    db.refresh(t)
    return to_dict(t)


# ───────────────────────── 알림 수신자(CRUD) ─────────────────────────
def list_recipients(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(select(SupportRecipient).order_by(SupportRecipient.id)).scalars().all()
    return [{"id": r.id, "email": r.email, "active": r.active} for r in rows]


def add_recipient(db: Session, email: str) -> dict[str, Any]:
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError("올바른 이메일을 입력해 주세요.")
    exists = db.execute(select(SupportRecipient).where(SupportRecipient.email == email)).scalar_one_or_none()
    if exists is not None:
        raise ValueError("이미 등록된 메일이에요.")
    r = SupportRecipient(email=email, active=True)
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "email": r.email, "active": r.active}


def set_recipient_active(db: Session, recipient_id: int, active: bool) -> dict[str, Any]:
    r = db.get(SupportRecipient, recipient_id)
    if r is None:
        raise LookupError("수신자를 찾을 수 없어요.")
    r.active = active
    db.commit()
    db.refresh(r)
    return {"id": r.id, "email": r.email, "active": r.active}


def delete_recipient(db: Session, recipient_id: int) -> None:
    r = db.get(SupportRecipient, recipient_id)
    if r is None:
        raise LookupError("수신자를 찾을 수 없어요.")
    db.delete(r)
    db.commit()


def active_recipient_emails(db: Session) -> list[str]:
    rows = (
        db.execute(select(SupportRecipient.email).where(SupportRecipient.active.is_(True)))
        .scalars()
        .all()
    )
    return [e for e in rows if e]


def seed_default_recipients(db: Session) -> None:
    """수신자 테이블이 비어 있으면 config 기본값으로 1회 시드(멱등)."""
    have = db.execute(select(func.count(SupportRecipient.id))).scalar_one()
    if have and int(have) > 0:
        return
    s = get_settings()
    seen: set[str] = set()
    for raw in s.support_default_recipients:
        email = (raw or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        db.add(SupportRecipient(email=email, active=True))
    if seen:
        db.commit()


# ───────────────────────── 메일 발송 ─────────────────────────
def _build_message(ticket: dict[str, Any], recipients: list[str], sender: str) -> EmailMessage:
    cat = ticket.get("category_label") or ticket.get("category")
    amount = ticket.get("amount")
    amount_str = f"{int(amount):,}원" if isinstance(amount, int) else "-"
    body = (
        f"[고객센터 문의 접수 #{ticket['id']}]\n\n"
        f"분류    : {cat}\n"
        f"제목    : {ticket['title']}\n"
        f"이름    : {ticket.get('contact_name') or '-'}\n"
        f"이메일  : {ticket['contact_email']}\n"
        f"회원ID  : {ticket.get('user_id') if ticket.get('user_id') is not None else '비로그인'}\n"
        f"주문번호: {ticket.get('order_id') or '-'}\n"
        f"금액    : {amount_str}\n"
        f"접수시각: {ticket.get('created_at') or '-'}\n"
        f"\n----- 문의 내용 -----\n{ticket['message']}\n"
        f"\n관리자 화면에서 처리 상태를 변경할 수 있습니다.\n"
    )
    msg = EmailMessage()
    msg["Subject"] = f"[고객센터/{cat}] {ticket['title']} (#{ticket['id']})"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    if ticket.get("contact_email"):
        msg["Reply-To"] = ticket["contact_email"]
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)
    return msg


def send_ticket_notification(
    ticket: dict[str, Any], recipients: list[str], smtp: dict[str, Any] | None = None
) -> bool:
    """접수 알림 메일 발송. SMTP 미설정 시 로그만 남기고 True 반환(mock).

    smtp: settings_service.get_smtp_config(db) 결과(관리자 설정 우선). None이면 config(.env) 폴백.
    BackgroundTask 로 호출되므로 예외를 삼키고 로그만 남긴다(요청 처리에 영향 없음).
    """
    recipients = [e for e in (recipients or []) if e]
    if not recipients:
        log.info("support: no active recipients — skip notification (ticket #%s)", ticket.get("id"))
        return False
    if smtp is None:
        s = get_settings()
        smtp = {
            "enabled": s.smtp_enabled, "host": s.smtp_host, "port": s.smtp_port,
            "user": s.smtp_user, "password": s.smtp_password, "from": s.smtp_from,
            "use_tls": s.smtp_use_tls,
        }
    sender = smtp.get("from") or smtp.get("user") or "no-reply@localhost"

    if not (smtp.get("enabled") and smtp.get("host")):
        # mock 모드: 실제 발송 대신 기록만. 운영 시 관리자 화면 또는 SMTP_* 주입하면 활성화.
        log.info(
            "support[mock-email] would notify %s about ticket #%s (%s)",
            recipients, ticket.get("id"), ticket.get("title"),
        )
        return True

    try:
        msg = _build_message(ticket, recipients, sender)
        if smtp.get("use_tls"):
            with smtplib.SMTP(smtp["host"], int(smtp["port"]), timeout=15) as server:
                server.starttls()
                if smtp.get("user"):
                    server.login(smtp["user"], smtp.get("password") or "")
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp["host"], int(smtp["port"]), timeout=15) as server:
                if smtp.get("user"):
                    server.login(smtp["user"], smtp.get("password") or "")
                server.send_message(msg)
        log.info("support: notification sent to %s (ticket #%s)", recipients, ticket.get("id"))
        return True
    except Exception as e:  # noqa: BLE001 — 알림 실패가 접수를 막지 않게
        log.warning("support: email send failed (ticket #%s): %s", ticket.get("id"), e)
        return False
