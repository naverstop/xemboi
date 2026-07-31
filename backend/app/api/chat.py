"""채팅 API — 세션 생성 / 메시지 / 이력 / 미리보기 reveal."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.deps import get_current_user, get_locale, get_optional_user
from backend.app.domain.chat_dto import (
    CreateSessionRequest,
    CreateSessionResponse,
    PostMessageRequest,
    PostMessageResponse,
    SessionHistoryResponse,
)
from backend.app.repositories import chat_repo
from backend.app.repositories.auth_models import User
from backend.app.services import chat_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/sessions", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    req: CreateSessionRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
    locale: str = Depends(get_locale),
) -> CreateSessionResponse:
    try:
        sid, summary, chart = chat_service.create_session(db, req.birth, req.top_k, user=user, locale=locale)
    except chat_service.SessionLimitError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    # 명식 요약 원문(오행분포·억부·조후용신·대운·계산기준 등 내부 프롬프트용 텍스트)은
    # 영업비밀/내부데이터 → 관리자에게만 반환. 일반 사용자는 시각적 명식표(saju_chart)만 본다.
    return CreateSessionResponse(
        session_id=sid,
        saju_summary=summary if chat_service._is_admin(user) else None,
        saju_chart=chart.model_dump(mode="json") if chart else None,
    )


@router.post("/sessions/{session_id}/messages", response_model=PostMessageResponse)
def post_message(
    session_id: str,
    req: PostMessageRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> PostMessageResponse:
    try:
        result = chat_service.post_message(db, session_id, req.message, req.top_k, user=user, depth=req.depth, explain_level=req.explain_level)
    except KeyError:
        raise HTTPException(status_code=404, detail="session not found")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except chat_service.ServiceUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        msg = str(e)
        if (
            msg.startswith("insufficient_credits")
            or msg.startswith("quota_exceeded")
            or msg.startswith("membership_quota_exhausted")
        ):
            raise HTTPException(status_code=402, detail=msg)
        raise HTTPException(status_code=400, detail=msg)

    msgs = chat_service.list_messages(db, session_id, user)
    return PostMessageResponse(
        session_id=session_id,
        answer=result["answer"],
        sources=result["sources"],
        total_messages=len(msgs),
        assistant_message_id=result["assistant_message_id"],
        is_preview=result["is_preview"],
        preview_revealed=result["preview_revealed"],
        full_length=result["full_length"],
        preview_length=result["preview_length"],
        credits_charged=result["credits_charged"],
        reveal_cost=result.get("reveal_cost", 0),
        balance_after=result["balance_after"],
        billing_mode=result["billing_mode"],
    )


class RevealResponse(BaseModel):
    message_id: int
    content: str
    preview_revealed: bool
    credits_charged: int
    balance_after: int


@router.post("/sessions/{session_id}/messages/{message_id}/reveal", response_model=RevealResponse)
def reveal_message(
    session_id: str,
    message_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RevealResponse:
    try:
        out = chat_service.reveal_message(db, session_id, message_id, user)
    except KeyError:
        raise HTTPException(status_code=404, detail="not found")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        msg = str(e)
        if "insufficient_credits" in msg or "quota_exceeded" in msg:
            raise HTTPException(status_code=402, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    return RevealResponse(
        message_id=message_id,
        content=out["content"],
        preview_revealed=out["preview_revealed"],
        credits_charged=out["credits_charged"],
        balance_after=out["balance_after"],
    )


@router.get("/sessions/{session_id}", response_model=SessionHistoryResponse)
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> SessionHistoryResponse:
    row = chat_service.get_session_row(db, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if row.user_id is not None and (user is None or user.id != row.user_id):
        raise HTTPException(status_code=403, detail="not your session")
    msgs = chat_service.list_messages(db, session_id, user)
    return SessionHistoryResponse(
        session_id=session_id,
        messages=msgs,
        has_saju=row.chart_json is not None,
    )


class MySessionItem(BaseModel):
    session_id: str
    title: str
    created_at: str
    birth_date: str
    gender: str
    message_count: int


class MySessionsResp(BaseModel):
    items: list[MySessionItem]
    total: int
    max_sessions: int = 30


@router.get("/sessions", response_model=MySessionsResp)
def my_sessions(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MySessionsResp:
    rows = chat_repo.list_user_sessions(db, user.id, limit=limit, offset=offset)
    items: list[MySessionItem] = []
    for r in rows:
        first = chat_repo.first_user_message(db, r.session_id)
        title = (first.content[:30] if first else "(빈 세션)").strip()
        if first and len(first.content) > 30:
            title += "…"
        items.append(MySessionItem(
            session_id=r.session_id,
            title=title or "(빈 세션)",
            created_at=r.created_at.isoformat(),
            birth_date=r.birth_date.isoformat(),
            gender=r.gender,
            message_count=chat_repo.count_messages(db, r.session_id),
        ))
    return MySessionsResp(items=items, total=chat_repo.count_user_sessions(db, user.id), max_sessions=chat_service.get_settings().max_sessions_per_user)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    try:
        ok = chat_repo.delete_session(db, session_id, user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not ok:
        raise HTTPException(status_code=404, detail="session not found")


class SuggestionsResp(BaseModel):
    suggestions: list[str]


@router.get("/sessions/{session_id}/suggestions", response_model=SuggestionsResp)
def get_suggestions(
    session_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> SuggestionsResp:
    """최근 질문+답변 맥락 기반 후속 추천질문(로컬 LLM 생성, 실패 시 정적 폴백).

    프론트가 매 답변 아래에 칩으로 표시해 이어지는 질문을 유도한다.
    """
    try:
        qs = chat_service.generate_followup_questions(db, session_id, n=6)
    except Exception:  # noqa: BLE001
        qs = []
    return SuggestionsResp(suggestions=qs)


@router.post("/sessions/{session_id}/messages/stream")
def stream_message(
    session_id: str,
    req: PostMessageRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """SSE 진짜 스트리밍 채팅 — Ollama 토큰을 실시간으로 흘려보낸다.

    이벤트:
      meta   — 빌링 모드/RAG 출처. 1회.
      chunk  — 토큰 조각. full 모드는 다회, preview 모드는 1회(컷된 본문).
      done   — 메시지 id/잔액/길이.
      error  — 도중 실패 시 (HTTP 200 + SSE error 이벤트).
    """
    import json

    # 사전 검증 (예외는 HTTP 응답으로 매핑) — 스트림 시작 전에 일으켜야 클라가 HTTP 상태로 받음
    row = chat_service.get_session_row(db, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if row.user_id is not None and (user is None or user.id != row.user_id):
        raise HTTPException(status_code=403, detail="not your session")
    # 무료한도/잔액 사전 검증 — quota_exceeded 면 402 + 코드 반환(결제 유도 트리거)
    if user is not None:
        try:
            chat_service._decide_billing(db, user, req.depth)
        except ValueError as e:
            msg = str(e)
            if (
                msg.startswith("quota_exceeded")
                or msg.startswith("insufficient_credits")
                or msg.startswith("membership_quota_exhausted")
            ):
                raise HTTPException(status_code=402, detail=msg)
            raise HTTPException(status_code=400, detail=msg)

    def gen():
        try:
            for event, data in chat_service.post_message_stream(
                db, session_id, req.message, req.top_k, user=user, depth=req.depth, explain_level=req.explain_level
            ):
                if event == "ping":
                    # SSE 주석(하트비트) — 무음 구간 방지, 클라는 무시
                    yield ": ping\n\n"
                    continue
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except chat_service.ServiceUnavailableError as e:
            # 외부 서비스(Qdrant/Ollama) 다운 — 친절 메시지 + 코드(클라가 503처럼 처리)
            yield f"event: error\ndata: {json.dumps({'detail': str(e), 'code': 'service_unavailable'}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"event: error\ndata: {json.dumps({'detail': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
