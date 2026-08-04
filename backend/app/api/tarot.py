"""타로 API — 세션 생성(입장료) / 픽 확정(멱등) / 해석 스트리밍 / 스냅샷. 궁합 라우터 미러링."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.deps import get_current_user, get_locale, get_optional_user
from backend.app.domain.tarot_dto import CreateTarotRequest, TarotMessageRequest, TarotPicksRequest
from backend.app.repositories import tarot_repo
from backend.app.repositories.auth_models import User
from backend.app.services import chat_service, tarot_service
from backend.app.services.chat_service import ServiceUnavailableError
from backend.app.services.tarot_service import TarotSession

router = APIRouter(prefix="/api/tarot", tags=["tarot"])


def _raise_billing_or_400(e: ValueError) -> None:
    msg = str(e)
    if (
        msg.startswith("quota_exceeded")
        or msg.startswith("insufficient_credits")
        or msg.startswith("membership_quota_exhausted")
    ):
        raise HTTPException(status_code=402, detail=msg)
    raise HTTPException(status_code=400, detail=msg)


@router.post("")
def create_tarot(
    req: CreateTarotRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
    locale: str = Depends(get_locale),
) -> dict[str, Any]:
    try:
        return tarot_service.create_tarot(db, req.section, req.question, user=user, locale=locale)
    except chat_service.SessionLimitError as e:
        # 세션 개수 상한 초과 — chat 과 동일 상태코드(409)+detail("session_limit...").
        # 서비스에서 입장료 차감 '전'에 발생 → 초과 시 과금 없음.
        raise HTTPException(status_code=409, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ServiceUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        _raise_billing_or_400(e)


# ============================================================
# 세션 이력 목록 / 삭제 (로그인 필수) — chat.my_sessions/delete_session 미러
# ============================================================
class MyTarotSessionItem(BaseModel):
    tarot_id: str
    title: str
    section: str
    spread_type: str
    created_at: str
    message_count: int
    has_reading: bool


class MyTarotSessionsResp(BaseModel):
    items: list[MyTarotSessionItem]
    total: int
    max_sessions: int = tarot_service.TAROT_MAX_SESSIONS


@router.get("", response_model=MyTarotSessionsResp)
def my_tarot_sessions(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MyTarotSessionsResp:
    """회원 본인 타로 세션 목록(최신순). 비로그인 401. 비로그인 세션(user_id NULL)은 미노출.

    ⚠️ 경로는 정확히 GET /api/tarot(빈 path) — 스냅샷 GET /api/tarot/{tarot_id}(dynamic)과
    별개 경로라 충돌하지 않는다(FastAPI 가 정확 매칭). 제목은 question 30자 절단,
    없으면 "(질문 없음)".
    """
    rows = tarot_repo.list_user_sessions(db, user.id, limit=limit, offset=offset)
    items: list[MyTarotSessionItem] = []
    for r in rows:
        q = (r["question"] or "").strip()
        if q:
            title = q[:30] + ("…" if len(q) > 30 else "")
        else:
            title = "(질문 없음)"
        items.append(
            MyTarotSessionItem(
                tarot_id=r["tarot_id"],
                title=title,
                section=r["section"],
                spread_type=r["spread_type"],
                created_at=r["created_at"].isoformat() if r["created_at"] else "",
                message_count=r["message_count"],
                has_reading=r["has_reading"],
            )
        )
    return MyTarotSessionsResp(
        items=items,
        total=tarot_repo.count_user_sessions(db, user.id),
        max_sessions=tarot_service.TAROT_MAX_SESSIONS,
    )


@router.post("/{tarot_id}/picks")
def submit_picks(
    tarot_id: str,
    req: TarotPicksRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> dict[str, Any]:
    """부채꼴에서 고른 인덱스(0~77) 제출 — 세션당 1회 확정, 재호출은 저장된 동일 결과(멱등)."""
    try:
        return tarot_service.submit_picks(db, tarot_id, req.indices, user=user)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError:
        raise HTTPException(status_code=404, detail="tarot not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{tarot_id}/messages/stream")
def stream_tarot_message(
    tarot_id: str,
    req: TarotMessageRequest,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    """SSE 스트리밍 — 첫 호출은 스프레드 해석(입장료 포함), 이후는 추가질문(depth 과금)."""
    import json

    # 사전 검증 (스트림 시작 전 HTTP 상태로 매핑) — compat 동일
    sess = db.get(TarotSession, tarot_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="tarot not found")
    if sess.user_id is not None and (user is None or user.id != sess.user_id):
        raise HTTPException(status_code=403, detail="not your tarot session")
    if not sess.cards_json:
        raise HTTPException(status_code=400, detail="cards_not_picked")
    # 추가질문(이미 해석 있음)일 때만 사전 빌링 검증 → 402 매핑
    has_assistant = any(m.role == "assistant" for m in sess.messages)
    if has_assistant and user is not None and req.message.strip():
        try:
            chat_service._decide_billing(db, user, req.depth, allow_free_quota=False)
        except ValueError as e:
            _raise_billing_or_400(e)

    def gen():
        try:
            for event, data in tarot_service.stream_message(
                db, tarot_id, req.message, user=user, depth=req.depth
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


@router.get("/{tarot_id}/suggestions")
def tarot_suggestions(
    tarot_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> dict[str, Any]:
    """타로 해석 맥락 기반 후속 추천질문(로컬 LLM, 무과금) — compat 미러."""
    try:
        qs = tarot_service.generate_tarot_suggestions(db, tarot_id, n=6)
    except Exception:  # noqa: BLE001
        qs = []
    return {"suggestions": qs}


@router.get("/{tarot_id}")
def get_tarot(
    tarot_id: str,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> dict[str, Any]:
    """세션 스냅샷(질문/섹션/스프레드/확정 카드/메시지 이력) — 재조회 시 동일 카드 보장."""
    try:
        out = tarot_service.get_tarot(db, tarot_id, user)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if out is None:
        raise HTTPException(status_code=404, detail="tarot not found")
    return out


@router.delete("/{tarot_id}", status_code=204)
def delete_tarot_session(
    tarot_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """본인 타로 세션 삭제(메시지 CASCADE). 비로그인 401, 타인 403, 없음 404. 성공 204."""
    try:
        tarot_repo.delete_session(db, tarot_id, user.id)
    except KeyError:
        raise HTTPException(status_code=404, detail="tarot not found")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


class TarotBulkDeleteReq(BaseModel):
    ids: list[str]


@router.post("/bulk-delete")
def bulk_delete_tarot(
    body: TarotBulkDeleteReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    """체크한 타로 기록 여러 개를 한 번에 삭제(개별 DELETE 반복의 레이트리밋·부분실패 회피).

    본인 소유만 삭제(타인/없음은 조용히 건너뜀). 삭제 성공 건수를 반환.
    """
    deleted = 0
    for tid in body.ids[:500]:
        try:
            if tarot_repo.delete_session(db, tid, user.id):
                deleted += 1
        except (KeyError, PermissionError):
            pass
    return {"deleted": deleted}
