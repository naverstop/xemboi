"""채팅 세션/메시지 리포지토리."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.repositories.models import ChatMessage, ChatSession


def create_session(
    db: Session,
    *,
    session_id: str,
    top_k: int,
    birth_dict: dict[str, Any],
    saju_summary: str | None,
    chart_json: dict | None,
    user_id: int | None = None,
) -> ChatSession:
    row = ChatSession(
        session_id=session_id,
        top_k=top_k,
        user_id=user_id,
        birth_date=birth_dict["birth_date"],
        birth_time=birth_dict.get("birth_time"),
        calendar=birth_dict.get("calendar", "solar"),
        is_leap_month=bool(birth_dict.get("is_leap_month", False)),
        gender=birth_dict.get("gender", "male"),
        apply_true_solar_time=bool(birth_dict.get("apply_true_solar_time", False)),
        saju_summary=saju_summary,
        chart_json=chart_json,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_session(db: Session, session_id: str) -> ChatSession | None:
    stmt = (
        select(ChatSession)
        .options(selectinload(ChatSession.messages))
        .where(ChatSession.session_id == session_id)
    )
    return db.execute(stmt).scalar_one_or_none()


def list_messages(db: Session, session_id: str) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id)
    )
    return list(db.execute(stmt).scalars().all())


def append_messages(
    db: Session,
    session_id: str,
    rows: list[dict[str, Any]],
) -> list[ChatMessage]:
    """rows: [{role, content, created_at, sources_json, ...}, ...]. 삽입된 ChatMessage 객체 리스트 반환."""
    out: list[ChatMessage] = []
    for r in rows:
        m = ChatMessage(session_id=session_id, **r)
        db.add(m)
        out.append(m)
    db.commit()
    for m in out:
        db.refresh(m)
    return out


def get_message(db: Session, message_id: int) -> ChatMessage | None:
    return db.get(ChatMessage, message_id)


def list_user_sessions(
    db: Session, user_id: int, limit: int = 50, offset: int = 0
) -> list[ChatSession]:
    """회원 본인 세션 목록 (최신순)."""
    stmt = (
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.execute(stmt).scalars().all())


def count_messages(db: Session, session_id: str) -> int:
    from sqlalchemy import func
    stmt = select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id)
    return int(db.execute(stmt).scalar_one() or 0)


def count_user_sessions(db: Session, user_id: int) -> int:
    """회원 본인 채팅 세션 개수(계획 5.6 R). 한도 산정 기준.

    '상담 시작'은 질문 전에도 세션 행을 즉시 만들어 빈 세션(메시지 0개)이 쌓인다.
    한도는 '실제 상담'만 세야 하므로 메시지가 1건 이상인 세션만 카운트한다.
    """
    from sqlalchemy import exists, func
    msg_exists = exists().where(ChatMessage.session_id == ChatSession.session_id)
    stmt = select(func.count(ChatSession.session_id)).where(
        ChatSession.user_id == user_id, msg_exists
    )
    return int(db.execute(stmt).scalar_one() or 0)


def delete_empty_sessions(db: Session, user_id: int) -> int:
    """회원의 빈 세션(메시지 0개)을 일괄 삭제하고 삭제 개수를 반환. 커밋 포함.

    '상담 시작'을 누르면 질문 전에도 세션이 즉시 생성되므로, 반복 클릭/이탈 시
    빈 세션이 영구히 쌓여 한도(max_sessions_per_user)를 소진한다. 실제 질문이
    1건도 없는 세션은 가치가 없으므로 자동 정리한다(세션 생성 직전·로그아웃 시 호출).
    """
    from sqlalchemy import exists
    msg_exists = exists().where(ChatMessage.session_id == ChatSession.session_id)
    rows = list(
        db.execute(
            select(ChatSession).where(
                ChatSession.user_id == user_id, ~msg_exists
            )
        ).scalars()
    )
    if not rows:
        return 0
    for s in rows:
        db.delete(s)
    db.commit()
    return len(rows)


def first_user_message(db: Session, session_id: str) -> ChatMessage | None:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id, ChatMessage.role == "user")
        .order_by(ChatMessage.id)
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def delete_session(db: Session, session_id: str, user_id: int | None) -> bool:
    """본인 세션 삭제. 익명 세션(user_id IS NULL)은 user_id 무관 삭제 가능 안 함."""
    row = get_session(db, session_id)
    if row is None:
        return False
    if row.user_id != user_id:
        raise PermissionError("not your session")
    db.delete(row)
    db.commit()
    return True


def delete_all_user_sessions(db: Session, user_id: int) -> int:
    """탈퇴 시 회원의 모든 채팅 세션(메시지 cascade) 삭제. 커밋은 호출자가."""
    sessions = list(
        db.execute(select(ChatSession).where(ChatSession.user_id == user_id)).scalars()
    )
    n = 0
    for s in sessions:
        db.delete(s)
        n += 1
    db.flush()
    return n
