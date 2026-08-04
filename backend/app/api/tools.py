"""명리 도구 API — 작명/개명/아호/택일 생성 · 스트리밍 해설 · 조회."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.deps import get_current_user, get_locale, get_optional_user
from backend.app.domain.tool_dto import NamingRequest, SinnyeonRequest, TaekilRequest, ToolMessageRequest
from backend.app.repositories.auth_models import User
from backend.app.repositories.models import ToolSession
from backend.app.services import chat_service, tool_service
from backend.app.services.chat_service import ServiceUnavailableError

router = APIRouter(prefix="/api/tools", tags=["tools"])


def _quota_402(e: ValueError):
    msg = str(e)
    if (msg.startswith("quota_exceeded") or msg.startswith("insufficient_credits")
            or msg.startswith("membership_quota_exhausted")):
        raise HTTPException(status_code=402, detail=msg)
    raise HTTPException(status_code=400, detail=msg)


@router.post("/naming")
def create_naming(
    req: NamingRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
    locale: str = Depends(get_locale),
) -> dict[str, Any]:
    try:
        return tool_service.create_naming(
            db, req.kind, req.birth, req.surname, req.current_name, user=user, reading=req.reading,
            name_len=req.name_len, dollimja=req.dollimja, dollimja_pos=req.dollimja_pos,
            locale=locale,
        )
    except ValueError as e:
        _quota_402(e)


@router.post("/taekil")
def create_taekil(
    req: TaekilRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
    locale: str = Depends(get_locale),
) -> dict[str, Any]:
    try:
        return tool_service.create_taekil(
            db, req.birth, req.purpose, req.start_date, req.days, user=user, birth2=req.birth2,
            locale=locale,
        )
    except ValueError as e:
        _quota_402(e)


@router.post("/sinnyeon")
def create_sinnyeon(
    req: SinnyeonRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> dict[str, Any]:
    """B-1 신년운세 — 세운·영역점수·월별 간지/십성 리포트(입장료형, 해설·추가질문은 공용 스트림)."""
    try:
        return tool_service.create_sinnyeon(db, req.birth, req.year, user=user)
    except ValueError as e:
        _quota_402(e)


@router.post("/{tool_id}/messages/stream")
def stream_tool_message(
    tool_id: str,
    req: ToolMessageRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    import json

    row = db.get(ToolSession, tool_id)
    if row is None:
        raise HTTPException(status_code=404, detail="tool session not found")
    if row.user_id is not None and (user is None or user.id != row.user_id):
        raise HTTPException(status_code=403, detail="not your session")
    has_assistant = any(m.role == "assistant" for m in row.messages)
    if has_assistant and user is not None and req.message.strip():
        try:
            chat_service._decide_billing(db, user, req.depth, allow_free_quota=False)
        except ValueError as e:
            _quota_402(e)

    def gen():
        try:
            for event, data in tool_service.stream_message(
                db, tool_id, req.message, user=user, depth=req.depth, explain_level=req.explain_level
            ):
                if event == "ping":
                    yield ": ping\n\n"; continue
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except ServiceUnavailableError as e:
            yield f"event: error\ndata: {json.dumps({'detail': str(e), 'code': 'service_unavailable'}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"event: error\ndata: {json.dumps({'detail': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@router.get("/{tool_id}/suggestions")
def tool_suggestions(
    tool_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> dict[str, Any]:
    """택일/작명/개명/아호 해설 맥락 기반 후속 추천질문(로컬 LLM, 무과금)."""
    try:
        qs = tool_service.generate_tool_suggestions(db, tool_id, n=6)
    except Exception:  # noqa: BLE001
        qs = []
    return {"suggestions": qs}


@router.get("/hanja")
def hanja_lookup(reading: str, limit: int = 200, db: Session = Depends(get_db)) -> dict[str, Any]:
    """한글 음 → 한자 후보(일반, 이름용).

    limit 기본 200: 종전 24로 잘려 '개명에 내 이름 한자가 목록에 없다'는 실측(전문가 지적).
    독음당 사전 보유량이 최대 107자(구)·105자(기)라 24는 절단이 심했다(120개 음절이 24 초과).
    """
    from backend.app.saju import naming as naming_engine
    items = naming_engine.lookup_by_reading(reading, limit=max(1, min(limit, 500)))
    return {"reading": reading, "items": items, "total": len(items)}


@router.get("/surname")
def surname_lookup(reading: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """한글 성씨 → 한자(단성·복성). 김→金, 금→琴, 사공→司空."""
    from backend.app.saju import naming as naming_engine
    return {"reading": reading, "items": naming_engine.lookup_surname(reading)}


@router.get("")
def my_tools(
    tools: Optional[str] = None,
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """회원 본인 도구 세션 목록(최신순) — '지난 결과' 무차감 재열람용. 비로그인 401.

    tools=쉼표구분 필터(예: sinnyeon / naming / taekil / amulet). 경로는 정확히 GET /api/tools(빈 path)로
    스냅샷 GET /api/tools/{tool_id}(dynamic)과 별개(FastAPI 정확 매칭).
    """
    tool_filter = [t.strip() for t in tools.split(",") if t.strip()] if tools else None
    rows = tool_service.list_user_tools(db, user.id, tools=tool_filter, limit=limit, offset=offset)
    items = [{
        "tool_id": r["tool_id"], "tool": r["tool"], "kind": r["kind"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else "",
        "input": r["input"], "birth_date": r["birth_date"], "is_preview": r["is_preview"],
    } for r in rows]
    return {"items": items, "total": len(items)}


@router.get("/{tool_id}")
def get_tool(
    tool_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> dict[str, Any]:
    try:
        out = tool_service.get_tool(db, tool_id, user)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if out is None:
        raise HTTPException(status_code=404, detail="tool session not found")
    return out
