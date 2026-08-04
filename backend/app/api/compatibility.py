"""궁합(宮合) API — 생성 / 조회 / 전체 평균(펜타곤 오버레이)."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.deps import get_current_user, get_optional_user
from backend.app.domain.compat_dto import CreateCompatRequest
from backend.app.repositories.auth_models import User
from backend.app.services import chat_service, compat_service
from backend.app.services.chat_service import ServiceUnavailableError

router = APIRouter(prefix="/api/compatibility", tags=["compatibility"])


class CompatMessageRequest(BaseModel):
    message: str = ""
    depth: Literal["basic", "deep"] = "deep"
    explain_level: Literal["normal", "easy"] = "normal"


@router.post("")
def create_compatibility(
    req: CreateCompatRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> dict[str, Any]:
    try:
        return compat_service.create_compatibility(
            db, req.person_a, req.person_b, user=user,
            depth=req.depth, explain_level=req.explain_level,
        )
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ServiceUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        msg = str(e)
        if (
            msg.startswith("quota_exceeded")
            or msg.startswith("insufficient_credits")
            or msg.startswith("membership_quota_exhausted")
        ):
            raise HTTPException(status_code=402, detail=msg)
        raise HTTPException(status_code=400, detail=msg)


@router.post("/{compat_id}/messages/stream")
def stream_compat_message(
    compat_id: str,
    req: CompatMessageRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """SSE 스트리밍 — 첫 호출은 궁합 해설, 이후는 추가질문(상담쿼터 과금)."""
    import json

    # 사전 검증 (스트림 시작 전 HTTP 상태로 매핑)
    sess = db.get(compat_service.CompatibilitySession, compat_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="compatibility not found")
    if sess.user_id is not None and (user is None or user.id != sess.user_id):
        raise HTTPException(status_code=403, detail="not your compatibility session")
    # 추가질문(이미 해설 있음)일 때만 사전 빌링 검증 → 402 매핑
    has_assistant = any(m.role == "assistant" for m in sess.messages)
    if has_assistant and user is not None and req.message.strip():
        try:
            chat_service._decide_billing(db, user, req.depth, allow_free_quota=False)
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
            for event, data in compat_service.stream_message(
                db, compat_id, req.message, user=user, depth=req.depth, explain_level=req.explain_level
            ):
                if event == "ping":
                    yield ": ping\n\n"
                    continue
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except ServiceUnavailableError as e:
            yield f"event: error\ndata: {json.dumps({'detail': str(e), 'code': 'service_unavailable'}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"event: error\ndata: {json.dumps({'detail': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


@router.get("/{compat_id}/suggestions")
def compat_suggestions(
    compat_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> dict[str, Any]:
    """궁합 해설 맥락 기반 후속 추천질문(로컬 LLM, 무과금)."""
    try:
        qs = compat_service.generate_compat_suggestions(db, compat_id, n=6)
    except Exception:  # noqa: BLE001
        qs = []
    return {"suggestions": qs}


@router.get("/average")
def compatibility_average(db: Session = Depends(get_db)) -> dict[str, Any]:
    """궁합 본 사람들의 평균(요소점수·관법총점) — 펜타곤 '전체 평균' 오버레이용."""
    return compat_service.get_average(db)


@router.get("")
def my_compat(
    limit: int = 30,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """회원 본인 궁합 세션 목록(최신순) — '지난 결과' 무차감 재열람용. 비로그인 401.

    경로는 정확히 GET /api/compatibility(빈 path) — /average·/{compat_id}와 별개(FastAPI 정확 매칭).
    """
    rows = compat_service.list_user_compat(db, user.id, limit=limit, offset=offset)
    items = [{
        "compat_id": r["compat_id"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else "",
        "a_label": r["a_label"], "b_label": r["b_label"],
        "a_birth_date": r["a_birth_date"], "b_birth_date": r["b_birth_date"],
    } for r in rows]
    return {"items": items, "total": len(items)}


@router.get("/{compat_id}")
def get_compatibility(
    compat_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> dict[str, Any]:
    try:
        out = compat_service.get_compatibility(db, compat_id, user)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if out is None:
        raise HTTPException(status_code=404, detail="compatibility not found")
    return out
