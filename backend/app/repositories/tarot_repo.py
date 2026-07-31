"""타로 세션 이력 리포지토리 — chat_repo 미러(세션 목록/카운트/삭제 + 1주 TTL 정리).

타로는 채팅과 달리 '빈 세션(메시지 0개, 카드만 뽑음)'도 입장료를 낸 자산이므로
count_user_sessions 는 메시지 유무와 무관하게 회원의 모든 세션을 카운트한다
(chat_repo 처럼 '메시지 1건 이상'만 세지 않는다). 따라서 delete_empty_sessions 도 없다.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.repositories.models import TarotMessage, TarotSession


def list_user_sessions(
    db: Session, user_id: int, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    """회원 본인 타로 세션 목록(최신순).

    각 항목: {tarot_id, question, section, spread_type, created_at,
             message_count, has_reading(assistant 메시지 유무)}.
    빈 세션(카드만 뽑고 해석 전)도 입장료 낸 자산이라 그대로 노출한다.
    """
    stmt = (
        select(TarotSession)
        .where(TarotSession.user_id == user_id)
        .order_by(TarotSession.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = list(db.execute(stmt).scalars().all())
    out: list[dict[str, Any]] = []
    for r in rows:
        cnt = int(
            db.execute(
                select(func.count(TarotMessage.id)).where(
                    TarotMessage.tarot_id == r.tarot_id
                )
            ).scalar_one()
            or 0
        )
        has_reading = bool(
            db.execute(
                select(func.count(TarotMessage.id)).where(
                    TarotMessage.tarot_id == r.tarot_id,
                    TarotMessage.role == "assistant",
                )
            ).scalar_one()
            or 0
        )
        out.append(
            {
                "tarot_id": r.tarot_id,
                "question": r.question or "",
                "section": r.section,
                "spread_type": r.spread_type,
                "created_at": r.created_at,
                "message_count": cnt,
                "has_reading": has_reading,
            }
        )
    return out


def count_user_sessions(db: Session, user_id: int) -> int:
    """회원 본인 타로 세션 개수 — 한도 산정 기준.

    ⚠️ 채팅과 다르게 '메시지 1건 이상'만 세지 않는다. 타로는 세션 생성 시 입장료를
    차감하고 카드를 뽑으므로, 해석/추가질문 없이 카드만 뽑은 빈 세션도 이미 대가를
    치른 자산이다. 따라서 user_id 가 일치하는 모든 TarotSession 을 카운트한다.
    """
    stmt = select(func.count(TarotSession.tarot_id)).where(
        TarotSession.user_id == user_id
    )
    return int(db.execute(stmt).scalar_one() or 0)


def delete_session(db: Session, tarot_id: str, user_id: int) -> bool:
    """본인 타로 세션 삭제(메시지 CASCADE). 소유자 검증.

    - 세션 없음 → KeyError
    - 타인 세션 → PermissionError
    - 성공 → True (커밋 포함)
    """
    row = db.get(TarotSession, tarot_id)
    if row is None:
        raise KeyError(tarot_id)
    if row.user_id != user_id:
        raise PermissionError("not your tarot session")
    db.delete(row)
    db.commit()
    return True


def purge_expired(db: Session, days: int = 7) -> int:
    """created_at 이 days(기본 7일)를 초과한 타로 세션 삭제(메시지 CASCADE). 삭제 건수 반환.

    created_at 은 UTC(datetime.utcnow) 로 저장되므로 cutoff 도 utcnow 기준으로 계산한다.
    비로그인 세션(user_id NULL) 포함 전체가 대상이다(보관 정책은 1주).
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = list(
        db.execute(
            select(TarotSession).where(TarotSession.created_at < cutoff)
        ).scalars()
    )
    if not rows:
        return 0
    for s in rows:
        db.delete(s)
    db.commit()
    return len(rows)
