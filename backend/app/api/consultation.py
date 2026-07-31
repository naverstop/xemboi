"""1:1 인적 상담 API — 사용자 상담사 리스트 + 관리자 입점업체 관리.

support.py 와 동일하게 `router`(사용자) + `admin_router`(관리자, /api/admin/consultants)로 분리.
상담 도메인을 한 모듈로 응집해 두어, Phase 2 에서 실시간(WebSocket)까지 포함해 별도 프로세스(구조 C)로
떼어내기 쉽게 한다. 지금은 메인 앱에 마운트. 설계: [[consultation-1on1-plan]].
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.db import get_db, get_session_factory
from backend.app.core.deps import get_current_user, get_optional_user, require_admin
from backend.app.repositories.auth_models import User
from backend.app.repositories.consultation_models import Consultant, ConsultationSession
from backend.app.services import consultation_service as svc
from backend.app.services import consultation_session_service as sess
from backend.app.services import settings_service
from backend.app.services.consultation_rt import manager

router = APIRouter(prefix="/api/consultation", tags=["consultation"])


def require_consultant(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> Consultant:
    """입점 상담사(활성) 전용 게이트 — 로그인 사용자의 이메일/계정에 연결된 Consultant 반환."""
    c = svc.get_consultant_by_user(db, user.id) or svc.link_user(db, user)
    if c is None or not c.is_active:
        raise HTTPException(status_code=403, detail="입점 상담사 전용 기능이에요.")
    return c
admin_router = APIRouter(
    prefix="/api/admin/consultants", tags=["admin-consultation"], dependencies=[Depends(require_admin)]
)

# 관리자 편집 대상 전역 상담 설정 키
_SETTING_KEYS = (
    "consultation_default_price_p",
    "consultation_default_duration_min",
    "consultation_commission_pct",
    "consultation_tax_pct",
    "consultation_no_show_timeout_sec",
    "consultation_extend_warn_sec",
    "consultation_retention_days",
)


# ───────────────────────── 사용자 ─────────────────────────

@router.get("/consultants")
def list_consultants(
    specialty: Optional[str] = Query(None, pattern="^(saju|tarot)$"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """상담 화면 상담사 카드 리스트 — 활성 상담사만, 분야 필터(saju|tarot, 'both' 포함)."""
    return {"items": svc.list_public(db, specialty=specialty)}


@router.get("/config")
def consultation_config(db: Session = Depends(get_db)) -> dict[str, Any]:
    """사용자 화면용 공개 설정 — 보관/파기 고지, 블록·연장 정책 등(단가는 상담사별)."""
    return {
        "retention_days": settings_service.get_int(db, "consultation_retention_days", 7),
        "no_show_timeout_sec": settings_service.get_int(db, "consultation_no_show_timeout_sec", 120),
        "extend_warn_sec": settings_service.get_int(db, "consultation_extend_warn_sec", 120),
        "default_price_p": settings_service.get_int(db, "consultation_default_price_p", 50000),
        "default_duration_min": settings_service.get_int(db, "consultation_default_duration_min", 30),
    }


@router.get("/consultant/me")
def my_consultant_profile(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> dict[str, Any]:
    """현재 로그인 사용자가 입점업체(상담사)면 프로필 반환 — 상담사 콘솔 진입점 판단용(Phase 2)."""
    if user is None:
        return {"consultant": None}
    c = svc.get_consultant_by_user(db, user.id)
    if c is None:
        # 아직 미연결(가입 후 첫 접근)일 수 있으니 이메일로 연결 시도
        c = svc.link_user(db, user)
    return {"consultant": svc.admin_dict(db, c) if c is not None else None}


@router.get("/signboards/{name}")
def serve_signboard(name: str) -> FileResponse:
    """간판 이미지 서빙 — 안전한 파일명만(경로순회 차단)."""
    path = svc.signboard_path(name)
    if path is None:
        raise HTTPException(status_code=404, detail="이미지를 찾을 수 없어요.")
    return FileResponse(path)


# ───────────────────────── 세션 수명주기 ─────────────────────────

class SessionRequestReq(BaseModel):
    consultant_id: int
    consent: bool = False  # 대화 저장·7일 후 파기 고지 동의(입장 전)


@router.post("/sessions", status_code=201)
def create_session(
    req: SessionRequestReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """사용자 상담 요청 — 잔액·상담사 확인 후 requested 생성 + 상담사 접수 알림(Web Push, 요건 ⑩)."""
    try:
        s = sess.request_session(db, user, req.consultant_id, consent=req.consent)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # 상담사에게 접수 알림 — 콘솔 WS 즉시 반영(온라인 시) + Web Push(오프라인 폴백, 요건 ⑩).
    detail = sess.session_dict(db, s)
    manager.notify_console_threadsafe(req.consultant_id, {"type": "new_request", "session": detail})
    c = svc.get_consultant(db, req.consultant_id)
    if c and c.user_id:
        try:
            from backend.app.services import push_service
            who = user.nickname or "회원"
            push_service.send_to_user(
                db, c.user_id, "새 1:1 상담 요청",
                f"{who}님이 상담을 신청했어요. 접수해 주세요.", url="/consultation/console",
            )
        except Exception:  # noqa: BLE001
            pass
    return detail


@router.get("/sessions/mine")
def my_sessions(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return {"items": sess.list_user_sessions(db, user, 30)}


@router.get("/sessions/{session_id}")
def get_session_detail(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict[str, Any]:
    s = sess.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없어요.")
    if not sess.is_participant(db, s, user):
        raise HTTPException(status_code=403, detail="본인 상담만 볼 수 있어요.")
    return sess.session_dict(db, s)


@router.get("/sessions/{session_id}/messages")
def get_session_messages(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """대화 이력(재접속 복원용). 참여자만."""
    s = sess.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없어요.")
    if not sess.is_participant(db, s, user):
        raise HTTPException(status_code=403, detail="본인 상담만 볼 수 있어요.")
    return {"items": sess.list_messages(db, session_id)}


@router.post("/sessions/{session_id}/accept")
def accept_session_ep(
    session_id: str, db: Session = Depends(get_db), consultant: Consultant = Depends(require_consultant)
) -> dict[str, Any]:
    try:
        s = sess.accept_session(db, session_id, consultant)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return sess.session_dict(db, s)


@router.post("/sessions/{session_id}/decline")
def decline_session_ep(
    session_id: str, db: Session = Depends(get_db), consultant: Consultant = Depends(require_consultant)
) -> dict[str, Any]:
    try:
        s = sess.decline_session(db, session_id, consultant)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return sess.session_dict(db, s)


@router.post("/sessions/{session_id}/end")
def end_session_ep(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """상담 종료 — 참여자(사용자/상담사) 누구나. 정산 산출 + 파기예정 설정."""
    s = sess.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없어요.")
    if not sess.is_participant(db, s, user):
        raise HTTPException(status_code=403, detail="본인 상담만 종료할 수 있어요.")
    s = sess.end_session(db, session_id, reason="manual_end")
    return sess.session_dict(db, s)


@router.post("/sessions/{session_id}/extend")
def extend_session_ep(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict[str, Any]:
    try:
        s = sess.extend_session(db, session_id, user)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return sess.session_dict(db, s)


@router.post("/sessions/{session_id}/cancel")
def cancel_session_ep(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """사용자가 대기 중(requested) 요청 취소."""
    s = sess.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없어요.")
    if s.user_id != user.id:
        raise HTTPException(status_code=403, detail="본인 상담만 취소할 수 있어요.")
    s = sess.cancel_requested(db, session_id)
    return sess.session_dict(db, s)


@router.post("/sessions/{session_id}/report")
def session_report(
    session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """상담 종료 후 대화 요약 → 상장양식 상담서 PDF(요건 ⑧). 참여자만, 동의 후 프론트가 호출.

    consultation_messages → transcript → 기존 synthesize_consultation + generate_consultation_pdf 재사용.
    """
    s = sess.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없어요.")
    if not sess.is_participant(db, s, user):
        raise HTTPException(status_code=403, detail="본인 상담만 발급할 수 있어요.")
    convo = sess.transcript_for_summary(db, session_id)
    if not convo:
        raise HTTPException(status_code=400, detail="요약할 대화 내용이 없어요.")
    from backend.app.api.pdf import ConsultationReportReq, create_consultation_report
    c = svc.get_consultant(db, s.consultant_id)
    person = f"{user.nickname} 님" if user.nickname else ""
    req = ConsultationReportReq(
        doc_title=f"{(c.business_name + ' ') if c else ''}1:1 상담서",
        person_line=person, item="1:1 상담", conversation=convo, topic="1:1 상담",
    )
    resp = create_consultation_report(req, db=db, user=user)
    s.pdf_token = resp.token  # 세션에 귀속(재다운로드·7일 파기 연동)
    db.commit()
    return resp.model_dump()


class RatingReq(BaseModel):
    rating: int = Field(..., ge=1, le=5)


@router.post("/sessions/{session_id}/rating")
def rate_session(
    session_id: str, req: RatingReq, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """종료된 상담 만족도(1~5) 제출 — 간판 만족도 집계에 반영."""
    try:
        s = sess.submit_rating(db, session_id, user, req.rating)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return sess.session_dict(db, s)


@router.get("/consultant/requests")
def consultant_requests(
    db: Session = Depends(get_db), consultant: Consultant = Depends(require_consultant)
) -> dict[str, Any]:
    """상담사 접수함 — 대기/진행 세션 목록(요건 ⑩)."""
    return {"items": sess.consultant_pending(db, consultant)}


class AvailabilityReq(BaseModel):
    online: bool


@router.post("/consultant/availability")
def set_availability_ep(
    req: AvailabilityReq,
    db: Session = Depends(get_db),
    consultant: Consultant = Depends(require_consultant),
) -> dict[str, Any]:
    """상담사 본인 영업 on/off — 사용자 리스트 상태 배지에 반영(상담 중이면 세션 우선)."""
    c = svc.set_availability(db, consultant, req.online)
    return svc.admin_dict(db, c)


# ───────────────────────── WebSocket 실시간 (2a-2) ─────────────────────────
# 구조 C: 아래 WS/드라이버는 상담 전용 프로세스에서 동작(in-memory manager). sync SQLAlchemy는
# asyncio.to_thread 로 감싸 이벤트 루프 비차단. 서버 권위 카운트다운·no-show 타임아웃은 드라이버가 소유.


def _ws_uid(token: Optional[str]) -> Optional[int]:
    """WS 쿼리파라미터 토큰 → user_id (브라우저 WS 는 Authorization 헤더 불가)."""
    if not token:
        return None
    from backend.app.core.security import decode_token
    try:
        payload = decode_token(token)
        return int(payload.get("sub"))
    except Exception:  # noqa: BLE001
        return None


def _participant_role(session_id: str, uid: int) -> Optional[str]:
    sf = get_session_factory()
    with sf() as db:
        s = db.get(ConsultationSession, session_id)
        if s is None:
            return None
        if s.user_id == uid:
            return "user"
        c = db.get(Consultant, s.consultant_id)
        if c is not None and c.user_id == uid:
            return "consultant"
        return None


def _consultant_id_for_uid(uid: int) -> Optional[int]:
    sf = get_session_factory()
    with sf() as db:
        c = svc.get_consultant_by_user(db, uid)
        return c.id if (c is not None and c.is_active) else None


def _persist_message(session_id: str, sender: str, content: str) -> None:
    sf = get_session_factory()
    with sf() as db:
        sess.add_message(db, session_id, sender, content)


def _end_db(session_id: str, reason: str) -> None:
    sf = get_session_factory()
    with sf() as db:
        sess.end_session(db, session_id, reason=reason)


def _cancel_no_show_db(session_id: str) -> None:
    sf = get_session_factory()
    with sf() as db:
        sess.cancel_requested(db, session_id, no_show=True)


def _set_presence_if_free(consultant_id: int, presence: str) -> None:
    sf = get_session_factory()
    with sf() as db:
        c = db.get(Consultant, consultant_id)
        if c is not None and c.presence != "busy":
            c.presence = presence
            c.last_seen_at = datetime.utcnow()
            db.commit()


async def _session_driver(session_id: str) -> None:
    """세션 진행감시(서버 권위) — no-show 자동취소 + 카운트다운(2분전 연장경고·만료 자동종료).

    소켓이 연결된 동안만 3초 주기로 DB 상태를 재평가(재접속·연장 자동 반영). 상태는 전부 DB.
    """
    sf = get_session_factory()

    def _cfg() -> tuple[int, int]:
        with sf() as db:
            return (
                settings_service.get_int(db, "consultation_no_show_timeout_sec", 120),
                settings_service.get_int(db, "consultation_extend_warn_sec", 120),
            )

    no_show_sec, warn_sec = await asyncio.to_thread(_cfg)
    warned = False
    try:
        while manager.session_count(session_id) > 0:
            def _read() -> Optional[dict[str, Any]]:
                with sf() as db:
                    s = sess.get_session(db, session_id)
                    if s is None:
                        return None
                    return {
                        "status": s.status,
                        "started_at": s.started_at,
                        "requested_at": s.requested_at,
                        "total_sec": (s.duration_min + (s.extended_min or 0)) * 60,
                    }

            st = await asyncio.to_thread(_read)
            if st is None or st["status"] in sess._TERMINAL:
                await manager.broadcast_session(
                    session_id, {"type": "ended", "status": st["status"] if st else "gone"}
                )
                return
            now = datetime.utcnow()
            if st["status"] == "requested":
                if (now - st["requested_at"]).total_seconds() >= no_show_sec:
                    await asyncio.to_thread(_cancel_no_show_db, session_id)
                    await manager.broadcast_session(session_id, {"type": "no_show"})
                    return
            elif st["status"] == "active" and st["started_at"]:
                remaining = int(st["total_sec"] - (now - st["started_at"]).total_seconds())
                await manager.broadcast_session(
                    session_id, {"type": "tick", "remaining_sec": max(0, remaining)}
                )
                if remaining > warn_sec:
                    warned = False  # 연장으로 시간이 늘면 다음 블록 경고 재무장
                elif not warned:
                    warned = True
                    await manager.broadcast_session(
                        session_id, {"type": "warn_extend", "remaining_sec": max(0, remaining)}
                    )
                if remaining <= 0:
                    await asyncio.to_thread(_end_db, session_id, "expired")
                    await manager.broadcast_session(
                        session_id, {"type": "ended", "status": "completed", "reason": "expired"}
                    )
                    return
            await asyncio.sleep(3)
    finally:
        manager.clear_driver(session_id)


@router.websocket("/ws")
async def session_ws(ws: WebSocket) -> None:
    """세션 채팅 WS — 사용자↔상담사 릴레이 + 서버 카운트다운 push. 인증=쿼리 token."""
    manager.capture_loop()
    token = ws.query_params.get("token")
    session_id = ws.query_params.get("session_id")
    uid = _ws_uid(token)
    if uid is None or not session_id:
        await ws.close(code=4401)
        return
    role = await asyncio.to_thread(_participant_role, session_id, uid)
    if role is None:
        await ws.close(code=4403)
        return
    await ws.accept()
    await manager.join_session(session_id, ws)
    if not manager.driver_running(session_id):
        manager.set_driver(session_id, asyncio.create_task(_session_driver(session_id)))

    def _initial() -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
        with get_session_factory()() as db:
            s = sess.get_session(db, session_id)
            return (sess.session_dict(db, s) if s else None), sess.list_messages(db, session_id)

    state, history = await asyncio.to_thread(_initial)
    await ws.send_json({"type": "state", "role": role, "session": state, "history": history})
    try:
        while True:
            data = await ws.receive_json()
            typ = data.get("type")
            if typ == "message":
                content = (data.get("content") or "").strip()[:4000]
                if content:
                    await asyncio.to_thread(_persist_message, session_id, role, content)
                    await manager.broadcast_session(
                        session_id, {"type": "message", "sender": role, "content": content}
                    )
            elif typ == "end":
                await asyncio.to_thread(_end_db, session_id, f"{role}_end")
                await manager.broadcast_session(session_id, {"type": "ended", "status": "completed"})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        await manager.leave_session(session_id, ws)


@router.websocket("/consultant/ws")
async def consultant_console_ws(ws: WebSocket) -> None:
    """상담사 콘솔 WS — presence(대기중) 유지 + 접수 실시간 알림 + 하트비트. 인증=쿼리 token."""
    manager.capture_loop()
    token = ws.query_params.get("token")
    uid = _ws_uid(token)
    if uid is None:
        await ws.close(code=4401)
        return
    cid = await asyncio.to_thread(_consultant_id_for_uid, uid)
    if cid is None:
        await ws.close(code=4403)
        return
    await ws.accept()
    await manager.join_console(cid, ws)
    await asyncio.to_thread(_set_presence_if_free, cid, "online")

    def _pending() -> list[dict[str, Any]]:
        with get_session_factory()() as db:
            c = db.get(Consultant, cid)
            return sess.consultant_pending(db, c) if c else []

    await ws.send_json({"type": "requests", "items": await asyncio.to_thread(_pending)})
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "ping":
                await ws.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        await manager.leave_console(cid, ws)
        if not manager.console_online(cid):
            await asyncio.to_thread(_set_presence_if_free, cid, "offline")


# ───────────────────────── 관리자: 입점업체 ─────────────────────────

class ConsultantCreateReq(BaseModel):
    login_email: str = Field(..., max_length=255, description="입점 ID(=로그인 이메일)")
    business_name: str = Field(..., min_length=1, max_length=120)
    specialty: str = Field("saju", pattern="^(saju|tarot|both)$")
    intro: Optional[str] = Field(None, max_length=2000)
    rate_p: Optional[int] = Field(None, ge=0, description="회당 단가(P) — 비우면 전역 기본값")
    duration_min: Optional[int] = Field(None, ge=1, le=600, description="상담 시간(분) — 비우면 전역")
    commission_pct: Optional[int] = Field(None, ge=0, le=100, description="수수료% — 비우면 전역")
    is_active: bool = True
    sort_order: int = Field(100, ge=0, le=100000)


class ConsultantUpdateReq(BaseModel):
    business_name: Optional[str] = Field(None, min_length=1, max_length=120)
    specialty: Optional[str] = Field(None, pattern="^(saju|tarot|both)$")
    intro: Optional[str] = Field(None, max_length=2000)
    rate_p: Optional[int] = Field(None, ge=0)
    duration_min: Optional[int] = Field(None, ge=1, le=600)
    commission_pct: Optional[int] = Field(None, ge=0, le=100)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = Field(None, ge=0, le=100000)


@admin_router.get("")
def admin_list_consultants(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"items": svc.admin_list(db)}


@admin_router.post("", status_code=201)
def admin_create_consultant(req: ConsultantCreateReq, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        c = svc.create_consultant(db, **req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.admin_dict(db, c)


class DesignateReq(BaseModel):
    user_id: int
    specialty: str = Field("saju", pattern="^(saju|tarot|both)$")


@admin_router.post("/from-user", status_code=201)
def admin_designate_consultant(req: DesignateReq, db: Session = Depends(get_db)) -> dict[str, Any]:
    """회원관리에서 상담사 지정 — 회원을 입점업체로 생성/연결 + 분야(사주/타로/둘다) 지정."""
    try:
        c = svc.create_consultant_from_user(db, req.user_id, specialty=req.specialty)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.admin_dict(db, c)


@admin_router.patch("/{consultant_id}")
def admin_update_consultant(
    consultant_id: int, req: ConsultantUpdateReq, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        c = svc.update_consultant(db, consultant_id, **req.model_dump(exclude_unset=True))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return svc.admin_dict(db, c)


@admin_router.delete("/{consultant_id}", status_code=204)
def admin_delete_consultant(consultant_id: int, db: Session = Depends(get_db)) -> None:
    try:
        svc.delete_consultant(db, consultant_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@admin_router.post("/{consultant_id}/signboard")
async def admin_upload_signboard(
    consultant_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """간판 이미지 업로드 → 저장 후 상담사 레코드에 URL 반영."""
    if svc.get_consultant(db, consultant_id) is None:
        raise HTTPException(status_code=404, detail="상담사를 찾을 수 없어요.")
    content = await file.read()
    try:
        url = svc.save_signboard(consultant_id, file.filename or "image", content)
        c = svc.update_consultant(db, consultant_id, signboard_image_url=url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return svc.admin_dict(db, c)


# ───────────────────────── 관리자: 전역 설정 ─────────────────────────

class ConsultationSettingsPatchReq(BaseModel):
    consultation_default_price_p: Optional[int] = Field(None, ge=0)
    consultation_default_duration_min: Optional[int] = Field(None, ge=1, le=600)
    consultation_commission_pct: Optional[int] = Field(None, ge=0, le=100)
    consultation_tax_pct: Optional[float] = Field(None, ge=0, le=100)
    consultation_no_show_timeout_sec: Optional[int] = Field(None, ge=10, le=3600)
    consultation_extend_warn_sec: Optional[int] = Field(None, ge=10, le=3600)
    consultation_retention_days: Optional[int] = Field(None, ge=1, le=365)


def _settings_subset(db: Session) -> dict[str, Any]:
    allv = settings_service.get_all(db)
    return {k: allv.get(k) for k in _SETTING_KEYS}


@admin_router.get("/settings")
def admin_get_settings(db: Session = Depends(get_db)) -> dict[str, Any]:
    return {"settings": _settings_subset(db)}


@admin_router.patch("/settings")
def admin_patch_settings(
    req: ConsultationSettingsPatchReq, db: Session = Depends(get_db)
) -> dict[str, Any]:
    items: dict[str, Any] = {}
    for k, v in req.model_dump(exclude_unset=True).items():
        if v is None:
            continue
        items[k] = v
    if items:
        settings_service.set_many(db, items)
    return {"settings": _settings_subset(db)}


# ───────────────────────── 관리자: 정산 실지급 뷰 ─────────────────────────

@admin_router.get("/settlements")
def admin_list_settlements(
    consultant_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, pattern="^(pending|settled)$"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """정산 명세(세션별) + 전체 합계. 금액은 원(1P=1원)."""
    return {
        "items": svc.list_settlements(db, consultant_id=consultant_id, status=status),
        "totals": svc.settlement_totals(db),
    }


@admin_router.post("/settlements/{settlement_id}/settle")
def admin_settle_settlement(settlement_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """실지급 처리 — pending → settled."""
    try:
        return svc.settlement_dict(svc.set_settlement_status(db, settlement_id, True))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@admin_router.post("/settlements/{settlement_id}/unsettle")
def admin_unsettle_settlement(settlement_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """실지급 취소 — settled → pending."""
    try:
        return svc.settlement_dict(svc.set_settlement_status(db, settlement_id, False))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@admin_router.post("/{consultant_id}/settle-all")
def admin_settle_all(consultant_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """상담사 정산대기 전체 일괄 실지급 처리."""
    return svc.settle_all_for_consultant(db, consultant_id)
