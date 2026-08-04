"""고객센터(CONTACT US) — 문의 게시판 + 관리자 메일 알림(SMTP).

- 문의 접수는 항상 DB에 저장된다(게시판). 메일 발송 실패는 접수 자체를 막지 않는다.
- SMTP 미설정(mock) 시 실제 발송 대신 로그만 남긴다 — 결제(토스)·소셜 로그인과 동일한 mock 정책.
- 알림 수신 메일은 SupportRecipient 테이블로 관리자 CRUD.
"""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, formatdate, parseaddr
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


def send_pdf_email(
    smtp: dict[str, Any],
    to_email: str,
    subject: str,
    body: str,
    pdf_bytes: bytes,
    filename: str,
    reply_to: str | None = None,
    sender_name: str | None = None,
) -> bool:
    """상담서 PDF를 **첨부**해 1명에게 발송(사용자 공유용). 성공 True / 미설정·실패 False.

    smtp = settings_service.get_smtp_config(db)(관리자 설정 우선·.env 폴백)와 동일 shape.
    고객센터 알림(send_ticket_notification)과 같은 SMTP 접속 규칙(STARTTLS 587 / 비TLS)을 사용한다.

    보내는 사람(From): 주소는 SMTP 인증계정으로 **고정**(Gmail 등은 소유하지 않은 주소로 발신 시
    SPF/DKIM/DMARC 위반→스팸/차단). 대신 sender_name(공유한 회원 표시명)을 From '표시이름'에 넣고,
    reply_to(회원 실제 이메일)로 답장이 회원에게 가게 한다 — 스팸 없이 '회원이 보낸 것처럼' 보이는 표준 방식.
    """
    if not (smtp.get("enabled") and smtp.get("host") and to_email):
        return False
    sender = smtp.get("from") or smtp.get("user") or "no-reply@localhost"
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        if sender_name:
            _, addr = parseaddr(sender)   # "이름 <addr>"/"addr" → 순수 주소 추출
            msg["From"] = formataddr((sender_name, addr or sender))
        else:
            msg["From"] = sender
        msg["To"] = to_email
        if reply_to:
            msg["Reply-To"] = reply_to
        msg["Date"] = formatdate(localtime=True)
        msg.set_content(body)
        msg.add_attachment(
            pdf_bytes, maintype="application", subtype="pdf",
            filename=filename or "상담서.pdf",
        )
        host, port = smtp["host"], int(smtp["port"])
        if smtp.get("use_tls"):
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.starttls()
                if smtp.get("user"):
                    server.login(smtp["user"], smtp.get("password") or "")
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                if smtp.get("user"):
                    server.login(smtp["user"], smtp.get("password") or "")
                server.send_message(msg)
        log.info("pdf email sent to %s (%s, %d bytes)", to_email, filename, len(pdf_bytes))
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("pdf email send failed to %s: %s", to_email, e)
        return False


def send_test_email(smtp: dict[str, Any], to_email: str) -> tuple[bool, str]:
    """SMTP 설정 검증용 테스트 메일. 반환 (성공여부, 상세). 실패 사유(인증/연결/TLS 등)를
    그대로 돌려 관리자가 설정을 디버깅할 수 있게 한다."""
    if not smtp.get("enabled"):
        return False, "SMTP가 비활성 상태입니다. '메일 발송 사용'을 켜고 저장 후 다시 시도하세요."
    if not smtp.get("host"):
        return False, "SMTP 호스트가 비어 있습니다."
    if not (to_email or "").strip():
        return False, "받는 사람 이메일이 없습니다."
    sender = smtp.get("from") or smtp.get("user") or "no-reply@localhost"
    try:
        msg = EmailMessage()
        msg["Subject"] = "[인생상담 친구] SMTP 테스트 메일"
        msg["From"] = sender
        msg["To"] = to_email
        msg["Date"] = formatdate(localtime=True)
        msg.set_content(
            "이 메일이 도착했다면 SMTP 설정이 정상입니다.\n"
            "상담서 PDF 첨부 발송 및 고객센터 알림이 활성화됩니다.\n\n— 인생상담 친구 관리자 테스트"
        )
        host, port = smtp["host"], int(smtp["port"])
        if smtp.get("use_tls"):
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.starttls()
                if smtp.get("user"):
                    server.login(smtp["user"], smtp.get("password") or "")
                server.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                if smtp.get("user"):
                    server.login(smtp["user"], smtp.get("password") or "")
                server.send_message(msg)
        log.info("SMTP test mail sent to %s", to_email)
        return True, f"{to_email} 로 테스트 메일을 보냈습니다. 받은편지함(스팸함 포함)을 확인하세요."
    except Exception as e:  # noqa: BLE001
        log.warning("SMTP test mail failed to %s: %s", to_email, e)
        return False, f"발송 실패 — {type(e).__name__}: {e}"
