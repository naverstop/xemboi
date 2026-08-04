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
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.db import get_db, get_session_factory
from backend.app.core.deps import get_current_user, get_locale, get_optional_user, require_admin
from backend.app.repositories.auth_models import User
from backend.app.repositories.consultation_models import Consultant, ConsultationSession
from backend.app.services import consultation_reservation_service as rsvc
from backend.app.services import consultation_service as svc
from backend.app.services import consultation_session_service as sess
from backend.app.services import settings_service
from backend.app.services.consultation_rt import manager

router = APIRouter(prefix="/api/consultation", tags=["consultation"])


def require_consultant(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    locale: str = Depends(get_locale),
) -> Consultant:
    """입점 상담사(활성) 전용 게이트 — 로그인 사용자의 이메일/계정에 연결된 Consultant 반환."""
    c = svc.get_consultant_by_user(db, user.id) or svc.link_user(db, user)
    if c is None or not c.is_active:
        raise HTTPException(status_code=403, detail=sess.msg("consultant_only", locale))
    return c
admin_router = APIRouter(
    prefix="/api/admin/consultants", tags=["admin-consultation"], dependencies=[Depends(require_admin)]
)

# 관리자 편집 대상 전역 상담 설정 키
_SETTING_KEYS = (
    "consultation_default_price_p",
    "consultation_default_duration_min",
    "consultation_min_price_p",
    "consultation_commission_pct",
    "consultation_tax_pct",
    "consultation_no_show_timeout_sec",
    "consultation_extend_warn_sec",
    "consultation_retention_days",
    "consultation_reserve_full_refund_hours",
    "consultation_reserve_late_refund_pct",
    "consultation_reserve_grace_min",
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
    pol = rsvc.reserve_policy(db)
    return {
        "retention_days": settings_service.get_int(db, "consultation_retention_days", 7),
        "no_show_timeout_sec": settings_service.get_int(db, "consultation_no_show_timeout_sec", 120),
        "extend_warn_sec": settings_service.get_int(db, "consultation_extend_warn_sec", 120),
        "default_price_p": settings_service.get_int(db, "consultation_default_price_p", 59000),
        "default_duration_min": settings_service.get_int(db, "consultation_default_duration_min", 30),
        # A-2 예약 정책(사용자 고지용)
        "reserve_full_refund_hours": pol["full_refund_hours"],
        "reserve_late_refund_pct": pol["late_refund_pct"],
        "reserve_grace_min": pol["grace_min"],
    }


@router.get("/consultant/me")
def my_consultant_profile(
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> dict[str, Any]:
    """현재 로그인 사용자가 입점업체(상담사)면 본인 프로필(셀프 편집 뷰) 반환 — 콘솔·상담사 설정 진입점."""
    if user is None:
        return {"consultant": None}
    c = svc.get_consultant_by_user(db, user.id)
    if c is None:
        # 아직 미연결(가입 후 첫 접근)일 수 있으니 이메일로 연결 시도
        c = svc.link_user(db, user)
    return {"consultant": svc.self_dict(db, c) if c is not None else None}


class ConsultantSelfUpdateReq(BaseModel):
    """상담사 본인 셀프 편집 — 상호(business_name)는 본인 입력. 분야·수수료·노출순서·활성은 관리자 전용."""
    business_name: Optional[str] = Field(None, min_length=1, max_length=120, description="상호(카드 표시명)")
    intro: Optional[str] = Field(None, max_length=2000)
    keywords: Optional[list[str]] = Field(None, description="#전문영역 키워드(최대 8개)")
    price_unit: Optional[str] = Field(None, pattern="^(session|minute|hour)$")
    rate_p: Optional[int] = Field(None, ge=0, description="회당(세션) 요금 P")
    per_min_p: Optional[int] = Field(None, ge=0, description="분당 요금 P")
    per_hour_p: Optional[int] = Field(None, ge=0, description="시간당 요금 P")
    status: Optional[str] = Field(None, pattern="^(active|coming_soon)$")
    business_hours: Optional[dict[str, Any]] = Field(None, description="요일별 영업시간 {'0':{'open','close'}, ...}")


@router.patch("/consultant/me")
def update_my_consultant(
    req: ConsultantSelfUpdateReq,
    db: Session = Depends(get_db),
    consultant: Consultant = Depends(require_consultant),
) -> dict[str, Any]:
    """상담사 본인 프로필(소개·#키워드·요금·상태) 수정 — 즉시 반영(진행 중 세션은 스냅샷이라 무관)."""
    try:
        c = svc.update_self(db, consultant, **req.model_dump(exclude_unset=True))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"consultant": svc.self_dict(db, c)}


@router.post("/consultant/me/signboard")
async def upload_my_signboard(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    consultant: Consultant = Depends(require_consultant),
) -> dict[str, Any]:
    """상담사 본인 간판/사진 업로드 → 저장 후 본인 레코드에 URL 반영(셀프)."""
    if not bool(getattr(consultant, "self_managed", True)):
        raise HTTPException(status_code=403, detail="관리자가 설정을 잠갔어요. 문의해 주세요.")
    content = await file.read()
    try:
        url = svc.save_signboard(consultant.id, file.filename or "image", content)
        c = svc.update_consultant(db, consultant.id, signboard_image_url=url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"consultant": svc.self_dict(db, c)}


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
    # A-1 상담 컨텍스트 — 사주 채팅 세션/타로 세션 참조. 서버가 소유 검증 후 스냅샷을 떠서 저장.
    source_kind: str | None = None    # "saju" | "tarot" | "birth"(출산 택일 — 양 부모 명식)
    source_ref_id: str | None = None  # chat session_id | tarot_id | taekil tool_id


def _profile_source_context(user: User) -> dict[str, Any] | None:
    """직접 신청(사주챗/타로 경유 아님) fallback — 신청자의 저장된 본인 사주 프로필로 명식 스냅샷 생성.

    saju 소스(_resolve_source_context)와 동일한 dict 구조({chart, birth_date, birth_time, calendar, gender})로
    반환해 상담사 접수목록·채팅방 명식 패널이 코드 수정 없이 그대로 렌더된다.
    프로필이 없거나 파싱/명식 실패 시 None → 명식 없이 진행(기존과 동일)."""
    raw = getattr(user, "saju_profile", None)
    if not raw:
        return None
    try:
        import json as _json
        prof = _json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(prof, dict) or not prof.get("birth_date"):
            return None
        from backend.app.saju.engine import build_chart
        from backend.app.saju.types import BirthInput
        # 저장 프로필에서 BirthInput 이 받는 키만 추림(push_service._BIRTH_KEYS 와 동일 규약).
        _keys = ("birth_date", "birth_time", "calendar", "is_leap_month", "gender",
                 "apply_true_solar_time", "birth_longitude", "apply_equation_of_time", "night_zi_mode")
        kw = {k: prof[k] for k in _keys if prof.get(k) is not None}
        chart = build_chart(BirthInput(**kw)).model_dump(mode="json")
        return {
            "chart": chart,
            "birth_date": prof.get("birth_date"),
            "birth_time": prof.get("birth_time"),
            "calendar": prof.get("calendar") or "solar",
            "gender": prof.get("gender"),
        }
    except Exception:  # noqa: BLE001 — 프로필 파싱/명식 산출 실패 시 명식 없이 진행
        return None


def _profile_tarot_context(db: Session, user: User) -> dict[str, Any] | None:
    """직접 신청(타로 상담사) fallback — 신청자의 최근 '카드를 뽑은' 타로 세션을 상담사에게 연결.

    타로 상담엔 사주 명식이 아니라 타로 카드가 붙어야 한다(타로 소스 _resolve_source_context 와 동일
    dict 구조 {question, spread_type, cards}). 뽑은 카드가 있는 최근 세션만 대상. 없으면 None(카드 없이 진행)."""
    try:
        from backend.app.repositories.models import TarotSession
        from backend.app.services import tarot_service
        row = (
            db.query(TarotSession)
            .filter(TarotSession.user_id == user.id, TarotSession.cards_json.isnot(None))
            .order_by(TarotSession.created_at.desc())
            .first()
        )
        if row is None:
            return None
        t = tarot_service.get_tarot(db, row.tarot_id, user)
        if not t or not t.get("cards"):
            return None
        return {"question": t.get("question"), "spread_type": t.get("spread_type"), "cards": t.get("cards")}
    except Exception:  # noqa: BLE001 — 조회/파싱 실패 시 카드 없이 진행
        return None


def _resolve_source_context(db: Session, user: User, kind: str, ref_id: str) -> dict[str, Any]:
    """A-1: 소스 세션에서 상담사 전달용 스냅샷 생성 — 반드시 서버측 로드(클라이언트 위변조 차단)."""
    if kind == "saju":
        from backend.app.services import chat_service
        row = chat_service.get_session_row(db, ref_id)
        # 익명 세션(user_id 없음)은 전달 불가 — 본인 소유 세션만
        if row is None or row.user_id != user.id or not row.chart_json:
            raise HTTPException(status_code=404, detail="전달할 사주 명식을 찾을 수 없어요.")
        return {
            "chart": row.chart_json,
            "birth_date": row.birth_date.isoformat() if row.birth_date else None,
            "birth_time": row.birth_time.isoformat(timespec="minutes") if row.birth_time else None,
            "calendar": row.calendar,
            "gender": row.gender,
        }
    if kind == "birth":
        # 출산 택일(taekil birth) → 양 부모 명식 전달(뽀 지시 2026-08-03: 출산일은 상담으로 —
        # 아빠/엄마 사주를 상담사에게). 부모①=세션 컬럼, 부모②=result_json["parent2"](있을 때만).
        from backend.app.repositories.models import ToolSession
        row = db.get(ToolSession, (ref_id or "").strip())
        if (row is None or row.user_id != user.id or row.tool != "taekil"
                or row.kind != "birth" or not row.chart_json):
            raise HTTPException(status_code=404, detail="전달할 출산 택일 명식을 찾을 수 없어요.")
        ctx: dict[str, Any] = {
            "chart": row.chart_json,
            "birth_date": row.birth_date.isoformat() if row.birth_date else None,
            "birth_time": row.birth_time.isoformat(timespec="minutes") if row.birth_time else None,
            "calendar": row.calendar,
            "gender": row.gender,
        }
        p2 = (row.result_json or {}).get("parent2")
        if isinstance(p2, dict) and p2.get("chart"):
            ctx["parent2"] = p2
        return ctx
    if kind == "tarot":
        from backend.app.services import tarot_service
        try:
            t = tarot_service.get_tarot(db, ref_id, user)
        except PermissionError:
            raise HTTPException(status_code=403, detail="본인 타로 세션만 전달할 수 있어요.")
        if not t or not t.get("cards"):
            raise HTTPException(status_code=404, detail="전달할 타로 카드를 찾을 수 없어요.")
        return {
            "question": t.get("question"),
            "spread_type": t.get("spread_type"),
            "cards": t.get("cards"),
        }
    raise HTTPException(status_code=400, detail="전달할 수 없는 상담 정보 종류예요.")


@router.post("/sessions", status_code=201)
def create_session(
    req: SessionRequestReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    locale: str = Depends(get_locale),
) -> dict[str, Any]:
    """사용자 상담 요청 — 잔액·상담사 확인 후 requested 생성 + 상담사 접수 알림(Web Push, 요건 ⑩).

    source_kind/source_ref_id 가 오면 명식/타로 스냅샷을 세션에 저장해 상담사에게 자동 전달(A-1).
    요청 로케일(locale)을 세션에 영속 → 요약 상담서 언어·모델 선택 근거(ko 기본 불변)."""
    source_kind: str | None = None
    source_context: dict[str, Any] | None = None
    if req.source_kind and req.source_ref_id:
        source_context = _resolve_source_context(db, user, req.source_kind, req.source_ref_id)
        source_kind = req.source_kind
    else:
        # 직접 신청(상담사 목록/간판에서 바로) — 상담사 '분야'에 맞춰 컨텍스트 자동 첨부.
        #  · 사주/둘다: 저장된 본인 명식(_profile_source_context)
        #  · 타로 전용: 명식 대신 최근 뽑은 타로 카드(_profile_tarot_context) — 타로 상담에 명식은 부적합.
        _c = svc.get_consultant(db, req.consultant_id)
        if (getattr(_c, "specialty", None) or "saju") == "tarot":
            fb = _profile_tarot_context(db, user)
            if fb is not None:
                source_kind, source_context = "tarot", fb
        else:
            fb = _profile_source_context(user)
            if fb is not None:
                source_kind, source_context = "saju", fb
    try:
        s = sess.request_session(
            db, user, req.consultant_id, consent=req.consent,
            source_kind=source_kind, source_context=source_context, locale=locale,
        )
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


# ───────────────────────── A-2 예약 상담 ─────────────────────────

class SlotCreateReq(BaseModel):
    start_at: datetime  # ISO(UTC 권장) — 서버가 UTC naive 로 정규화


class ReserveReq(BaseModel):
    slot_id: str
    consent: bool = False  # 대화 저장·7일 파기 + 선결제·취소정책 고지 동의


@router.post("/consultant/slots", status_code=201)
def add_consultant_slot(
    req: SlotCreateReq,
    db: Session = Depends(get_db),
    consultant: Consultant = Depends(require_consultant),
) -> dict[str, Any]:
    """상담사 — 예약 가능 시간 등록(본인 블록 시간 기준 겹침 방지)."""
    try:
        s = rsvc.add_slot(db, consultant, req.start_at)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return rsvc.slot_dict(db, s, include_user=True)


@router.get("/consultant/slots")
def list_my_slots(
    db: Session = Depends(get_db),
    consultant: Consultant = Depends(require_consultant),
) -> dict[str, Any]:
    return {"items": [rsvc.slot_dict(db, s, include_user=True) for s in rsvc.list_consultant_slots(db, consultant)]}


@router.delete("/consultant/slots/{slot_id}")
def remove_consultant_slot(
    slot_id: str,
    db: Session = Depends(get_db),
    consultant: Consultant = Depends(require_consultant),
) -> dict[str, Any]:
    """상담사 — 슬롯 삭제/예약 취소. booked 였다면 사용자에게 100% 환불 + 알림."""
    try:
        s, refund = rsvc.remove_slot(db, consultant, slot_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if refund > 0 and s.user_id:
        try:
            from backend.app.services import push_service
            push_service.send_to_user(
                db, s.user_id, "예약 상담이 취소되었어요",
                f"상담사 사정으로 예약이 취소되어 {refund:,}P가 전액 환불되었어요.", url="/",
            )
        except Exception:  # noqa: BLE001
            pass
    return rsvc.slot_dict(db, s, include_user=True)


@router.get("/consultants/{consultant_id}/slots")
def list_consultant_open_slots(
    consultant_id: int, db: Session = Depends(get_db)
) -> dict[str, Any]:
    """사용자 — 특정 상담사의 예약 가능(open·미래) 슬롯."""
    return {"items": [rsvc.slot_dict(db, s) for s in rsvc.list_open_slots(db, consultant_id)]}


@router.post("/reservations", status_code=201)
def reserve_slot(
    req: ReserveReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """사용자 — 예약 확정(선결제 홀드). 상담사에게 예약 접수 푸시."""
    try:
        s = rsvc.reserve(db, user, req.slot_id, consent=req.consent)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    c = svc.get_consultant(db, s.consultant_id)
    if c and c.user_id:
        try:
            from backend.app.services import push_service
            from datetime import timedelta as _td9
            when = (s.start_at + _td9(hours=9)).strftime("%m/%d %H:%M")
            push_service.send_to_user(
                db, c.user_id, "새 예약이 잡혔어요",
                f"{when}(한국시간) 예약 상담이 접수되었어요. 콘솔에서 확인하세요.", url="/consultation/console",
            )
        except Exception:  # noqa: BLE001
            pass
    return rsvc.slot_dict(db, s)


@router.get("/reservations/mine")
def my_reservations(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> dict[str, Any]:
    out = []
    for s in rsvc.my_reservations(db, user):
        d = rsvc.slot_dict(db, s)
        c = svc.get_consultant(db, s.consultant_id)
        d["consultant_name"] = c.business_name if c else None
        out.append(d)
    return {"items": out}


@router.delete("/reservations/{slot_id}")
def cancel_reservation(
    slot_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """사용자 — 예약 취소. 시작 N시간 전 100%, 이내 M% 환불(관리자 설정)."""
    try:
        s, refund = rsvc.cancel_by_user(db, user, slot_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    c = svc.get_consultant(db, s.consultant_id)
    if c and c.user_id:
        try:
            from backend.app.services import push_service
            push_service.send_to_user(
                db, c.user_id, "예약이 취소되었어요",
                f"{(s.start_at + __import__('datetime').timedelta(hours=9)).strftime('%m/%d %H:%M')}(한국시간) 예약을 사용자가 취소했어요.", url="/consultation/console",
            )
        except Exception:  # noqa: BLE001
            pass
    return {**rsvc.slot_dict(db, s), "refund_p": refund}


async def _reservation_driver() -> None:
    """A-2 예약 드라이버 — 30초 주기: ①시작 10분 전 리마인더 푸시 ②시각 도래 시 세션 자동 생성
    +양측 알림. 상담사 미수락 노쇼는 _session_driver(예약 유예)가, WS 미접속 잔류 세션은
    다음 전환 주기에서 requested_at+유예 초과분을 정리한다."""
    sf = get_session_factory()
    while True:
        try:
            def _tick() -> tuple[list, list, list]:
                with sf() as db:
                    reminders = [
                        (s.user_id, s.consultant_id, s.start_at) for s in rsvc.due_reminders(db)
                    ]
                    converted = []
                    for slot, srow in rsvc.convert_due(db):
                        converted.append((slot.user_id, slot.consultant_id, srow.id, sess.session_dict(db, srow)))
                    # WS 드라이버가 안 도는(아무도 접속 안 한) 잔류 세션의 노쇼 정리.
                    #  · 예약 전환 세션: reserve_grace_min(분) 유예
                    #  · 즉시 상담 세션: no_show_timeout_sec(초) 유예 — 세션 WS 미접속(브라우저 종료/네트워크
                    #    단절 등) 시 _session_driver 가 안 돌아 무기한 requested 잔류 + 사용자 신규요청 차단(deadlock)을
                    #    막기 위한 안전망(WS 접속 시엔 _session_driver 가 정확히 처리).
                    from datetime import timedelta as _td
                    from sqlalchemy import and_, or_, select as _sel
                    now_ = datetime.utcnow()
                    grace_min = settings_service.get_int(db, "consultation_reserve_grace_min", 10)
                    no_show_sec = settings_service.get_int(db, "consultation_no_show_timeout_sec", 120)
                    rsv_cutoff = now_ - _td(minutes=grace_min)
                    imm_cutoff = now_ - _td(seconds=no_show_sec)
                    stale = db.execute(
                        _sel(ConsultationSession).where(
                            ConsultationSession.status == "requested",
                            or_(
                                and_(
                                    ConsultationSession.reservation_id.isnot(None),
                                    ConsultationSession.requested_at < rsv_cutoff,
                                ),
                                and_(
                                    ConsultationSession.reservation_id.is_(None),
                                    ConsultationSession.requested_at < imm_cutoff,
                                ),
                            ),
                        )
                    ).scalars().all()
                    expired = []
                    for st_row in stale:
                        refunded = bool(st_row.credits_charged)  # 예약(선결제)만 환불, 즉시상담은 무차감
                        sess.cancel_requested(db, st_row.id, no_show=True)  # 선결제 있으면 전액 환불(멱등)
                        expired.append((st_row.user_id, st_row.id, refunded))
                    # 진행 중(active) 세션 리퍼 — 양측 소켓이 모두 끊겨 _session_driver(session_count>0 동안만 동작)가
                    #   멈춘 세션이 무기한 active 로 남아, 상담사 busy 고정(신규 수락 차단) + 사용자 진행중 세션 차단(신규 신청
                    #   차단)으로 양측 계정이 deadlock 되던 것을 방지. 블록시간(+연장)+유예 초과분을 소켓 유무와 무관하게
                    #   서버 권위로 종료(end_session=참여검증→정산 or 무응답 전액환불). end_session 은 멱등이라 _session_driver 와 겹쳐도 안전.
                    reap_grace_sec = settings_service.get_int(db, "consultation_active_reap_grace_sec", 120)
                    active_rows = db.execute(
                        _sel(ConsultationSession).where(
                            ConsultationSession.status == "active",
                            ConsultationSession.started_at.isnot(None),
                        )
                    ).scalars().all()
                    reaped = []
                    for a_row in active_rows:
                        total_sec = (a_row.duration_min + (a_row.extended_min or 0)) * 60
                        uid_, cid_, sid_ = a_row.user_id, a_row.consultant_id, a_row.id
                        if (now_ - a_row.started_at).total_seconds() < total_sec + reap_grace_sec:
                            continue
                        try:
                            _es = sess.end_session(db, sid_, reason="reaper")
                            reaped.append((uid_, cid_, sid_, _es.status if _es else None))
                        except Exception:  # noqa: BLE001
                            continue
                    return reminders, converted, expired, reaped

            reminders, converted, expired, reaped = await asyncio.to_thread(_tick)

            def _notify() -> None:
                with sf() as db:
                    from backend.app.services import push_service
                    for uid, cid, start_at in reminders:
                        when = (start_at + __import__("datetime").timedelta(hours=9)).strftime("%H:%M")
                        c = svc.get_consultant(db, cid)
                        if uid:
                            push_service.send_to_user(db, uid, "예약 상담 10분 전", "곧 예약하신 1:1 상담이 시작돼요. 접속해 주세요.", url="/")
                        if c and c.user_id:
                            push_service.send_to_user(db, c.user_id, "예약 상담 10분 전", f"{when}(한국시간) 예약 상담이 곧 시작돼요.", url="/consultation/console")
                    for uid, cid, sid_, detail in converted:
                        manager.notify_console_threadsafe(cid, {"type": "new_request", "session": detail})
                        c = svc.get_consultant(db, cid)
                        if uid:
                            push_service.send_to_user(db, uid, "예약 상담 시간이에요", "지금 접속하면 상담사와 연결돼요.", url="/")
                        if c and c.user_id:
                            push_service.send_to_user(db, c.user_id, "예약 상담 시간이에요", "예약 상담을 수락해 주세요.", url="/consultation/console")
                    for uid, sid_, refunded in expired:
                        if uid:
                            msg = (
                                "상담사가 응답하지 않아 전액 환불되었어요."
                                if refunded
                                else "상담사가 응답하지 않아 상담 요청이 자동 취소되었어요."
                            )
                            push_service.send_to_user(db, uid, "상담이 진행되지 못했어요", msg, url="/")
                    # active 리퍼로 정리된 세션 — 양측 push + 콘솔에 종료 통지(접수함/재입장 카드 정리)
                    for uid, cid, sid_, end_status in reaped:
                        c = svc.get_consultant(db, cid)
                        umsg = (
                            "상담사가 응답하지 않아 상담이 종료되고 전액 환불되었어요."
                            if end_status == "no_show"
                            else "상담 시간이 종료되어 상담이 마무리되었어요."
                        )
                        if uid:
                            push_service.send_to_user(db, uid, "상담이 종료되었어요", umsg, url="/")
                        if c and c.user_id:
                            push_service.send_to_user(db, c.user_id, "상담이 종료되었어요", "진행 중이던 상담이 시간 종료로 정리되었어요.", url="/consultation/console")
                        manager.notify_console_threadsafe(cid, {"type": "session_ended", "session_id": sid_})

            if reminders or converted or expired or reaped:
                await asyncio.to_thread(_notify)
        except Exception:  # noqa: BLE001 — 드라이버는 죽지 않는다
            import logging
            logging.getLogger("consultation").exception("reservation driver tick failed")
        await asyncio.sleep(30)


@router.on_event("startup")
async def _start_reservation_driver() -> None:
    asyncio.create_task(_reservation_driver())


@router.get("/sessions/{session_id}")
def get_session_detail(
    session_id: str, db: Session = Depends(get_db),
    user: User = Depends(get_current_user), locale: str = Depends(get_locale),
) -> dict[str, Any]:
    s = sess.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail=sess.msg("session_not_found", locale))
    if not sess.is_participant(db, s, user):
        raise HTTPException(status_code=403, detail=sess.msg("view_only_own", locale))
    return sess.session_dict(db, s)


@router.get("/sessions/{session_id}/messages")
def get_session_messages(
    session_id: str, db: Session = Depends(get_db),
    user: User = Depends(get_current_user), locale: str = Depends(get_locale),
) -> dict[str, Any]:
    """대화 이력(재접속 복원용). 참여자만."""
    s = sess.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail=sess.msg("session_not_found", locale))
    if not sess.is_participant(db, s, user):
        raise HTTPException(status_code=403, detail=sess.msg("view_only_own", locale))
    return {"items": sess.list_messages(db, session_id)}


@router.post("/sessions/{session_id}/accept")
def accept_session_ep(
    session_id: str, db: Session = Depends(get_db),
    consultant: Consultant = Depends(require_consultant), locale: str = Depends(get_locale),
) -> dict[str, Any]:
    try:
        s = sess.accept_session(db, session_id, consultant, locale=locale)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return sess.session_dict(db, s)


@router.post("/sessions/{session_id}/decline")
def decline_session_ep(
    session_id: str, db: Session = Depends(get_db),
    consultant: Consultant = Depends(require_consultant), locale: str = Depends(get_locale),
) -> dict[str, Any]:
    try:
        s = sess.decline_session(db, session_id, consultant, locale=locale)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    return sess.session_dict(db, s)


@router.post("/sessions/{session_id}/end")
def end_session_ep(
    session_id: str, db: Session = Depends(get_db),
    user: User = Depends(get_current_user), locale: str = Depends(get_locale),
) -> dict[str, Any]:
    """상담 종료 — 참여자(사용자/상담사) 누구나. 정산 산출 + 파기예정 설정."""
    s = sess.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail=sess.msg("session_not_found", locale))
    if not sess.is_participant(db, s, user):
        raise HTTPException(status_code=403, detail=sess.msg("end_only_own", locale))
    # 미수락 예약세션을 상담사가 종료하면 사실상 거절 → 100% 환불(사용자에 late-refund 페널티 전가 금지).
    by_consultant = s.user_id != user.id
    s = sess.end_session(db, session_id, reason="manual_end", by_consultant=by_consultant, locale=locale)
    return sess.session_dict(db, s)


@router.post("/sessions/{session_id}/extend")
def extend_session_ep(
    session_id: str, db: Session = Depends(get_db),
    user: User = Depends(get_current_user), locale: str = Depends(get_locale),
) -> dict[str, Any]:
    try:
        s = sess.extend_session(db, session_id, user, locale=locale)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return sess.session_dict(db, s)


@router.post("/sessions/{session_id}/cancel")
def cancel_session_ep(
    session_id: str, db: Session = Depends(get_db),
    user: User = Depends(get_current_user), locale: str = Depends(get_locale),
) -> dict[str, Any]:
    """사용자가 대기 중(requested) 요청 취소."""
    s = sess.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail=sess.msg("session_not_found", locale))
    if s.user_id != user.id:
        raise HTTPException(status_code=403, detail=sess.msg("cancel_only_own", locale))
    s = sess.cancel_requested(db, session_id)
    return sess.session_dict(db, s)


def _existing_report_resp(token: str, loc: str = "ko") -> dict[str, Any]:
    """저장된 상담서 토큰 → 응답(재사용). ConsultationPdfResp 와 동일 키 구조."""
    from backend.app.api.pdf import _PDF_DIR as _PDFD
    _name = "Bản tư vấn.pdf" if loc == "vi" else "상담서.pdf"
    _np = _PDFD / f"{token}.name"
    if _np.is_file():
        try:
            _name = _np.read_text(encoding="utf-8").strip() or _name
        except Exception:  # noqa: BLE001
            pass
    return {"token": token, "url": f"/api/pdf/{token}",
            "download_url": f"/api/pdf/{token}?download=1", "filename": _name}


def _discard_report_pdf(token: str) -> None:
    """동시발급 레이스에서 '진' 쪽의 고아 PDF(+사이드카) 파기 — 세션 미참조 PII 잔존 방지."""
    from backend.app.api.pdf import _PDF_DIR as _PDFD
    for _suf in (".pdf", ".name"):
        try:
            (_PDFD / f"{token}{_suf}").unlink(missing_ok=True)
        except OSError:
            pass


@router.post("/sessions/{session_id}/report")
def session_report(
    session_id: str, db: Session = Depends(get_db),
    user: User = Depends(get_current_user), locale: str = Depends(get_locale),
) -> dict[str, Any]:
    """상담 종료 후 대화 요약 → 상장양식 상담서 PDF(요건 ⑧). 참여자만, 동의 후 프론트가 호출.

    consultation_messages → transcript → 기존 synthesize_consultation + generate_consultation_pdf 재사용.
    문서 제목·대상자·항목·주제와 요약 언어는 세션 로케일(s.locale) 기준(ko 기본 불변).
    """
    from backend.app.api.pdf import _PDF_DIR as _PDFD
    s = sess.get_session(db, session_id)
    if s is None:
        raise HTTPException(status_code=404, detail=sess.msg("session_not_found", locale))
    if not sess.is_participant(db, s, user):
        raise HTTPException(status_code=403, detail=sess.msg("report_only_own", locale))
    loc = (getattr(s, "locale", None) or locale or "ko")
    if loc not in ("ko", "vi"):
        loc = "ko"
    # (B) 이미 발급된 요약서가 있으면 재사용(순차 클릭) — 누가 눌러도 같은 상담서 공유.
    if s.pdf_token and (_PDFD / f"{s.pdf_token}.pdf").is_file():
        return _existing_report_resp(s.pdf_token, loc)
    convo = sess.transcript_for_summary(db, session_id)
    if not convo:
        raise HTTPException(status_code=400, detail=sess.msg("no_convo", loc))
    from backend.app.api.pdf import ConsultationReportReq, create_consultation_report
    c = svc.get_consultant(db, s.consultant_id)
    # (B) 상담서 수신자명은 '누가 발급하든' 상담받은 신청자 기준(상담사가 먼저 눌러도 신청자 이름으로).
    applicant = db.get(User, s.user_id) if s.user_id else None
    biz = (c.business_name + " ") if c else ""
    if loc == "vi":
        doc_title = f"{biz}Bản tư vấn 1:1"
        person = (applicant.nickname if applicant and applicant.nickname else "")
        item = tpc = "Tư vấn 1:1"
    else:
        doc_title = f"{biz}1:1 상담서"
        person = f"{applicant.nickname} 님" if (applicant and applicant.nickname) else ""
        item = tpc = "1:1 상담"
    req = ConsultationReportReq(
        doc_title=doc_title, person_line=person, item=item,
        conversation=convo, topic=tpc, locale=loc,
    )
    old_token = s.pdf_token               # 재생성 시작 시점 스냅샷(create 내부 commit 의 expire 대비)
    resp = create_consultation_report(req, db=db, user=user, locale=loc)
    # (A) 동시 발급 레이스 방지 — CAS(compare-and-swap): '내가 본 상태에서 안 바뀐' 경우에만 내 토큰 확정.
    #   create_consultation_report 가 내부 commit 을 하므로 행잠금(FOR UPDATE)은 조기 해제돼 부적합.
    #   재사용 가드가 '파일이 없으면(파기됨) 재생성'을 허용하므로 IS NULL 조건만으론 파일 없는 stale 토큰을
    #   못 덮어써 깨진 링크가 된다 → old_token 기준 비교(NULL 이면 IS NULL, 아니면 ==old)로 재생성도 이기게 한다.
    from sqlalchemy import update as _update
    from backend.app.repositories.consultation_models import ConsultationSession as _CS
    _cond = _CS.pdf_token.is_(None) if old_token is None else (_CS.pdf_token == old_token)
    r = db.execute(_update(_CS).where(_CS.id == session_id, _cond).values(pdf_token=resp.token))
    db.commit()
    if r.rowcount == 1:
        return resp.model_dump()          # 선착 — 내 토큰이 세션에 귀속(재다운로드·7일 파기 연동)
    # 다른 참여자가 먼저 확정 → 확정본 파일이 유효하면 내 PDF(고아) 파기 후 그 '같은' 상담서 재사용.
    db.refresh(s)
    if s.pdf_token and (_PDFD / f"{s.pdf_token}.pdf").is_file():
        _discard_report_pdf(resp.token)
        return _existing_report_resp(s.pdf_token, loc)
    # 확정본도 파일 부재(초극단) — 깨진 링크 방지 위해 내 결과(파일 존재)를 강제 확정하고 반환.
    db.execute(_update(_CS).where(_CS.id == session_id).values(pdf_token=resp.token))
    db.commit()
    return resp.model_dump()


class RatingReq(BaseModel):
    rating: int = Field(..., ge=1, le=5)


@router.post("/sessions/{session_id}/rating")
def rate_session(
    session_id: str, req: RatingReq, db: Session = Depends(get_db),
    user: User = Depends(get_current_user), locale: str = Depends(get_locale),
) -> dict[str, Any]:
    """종료된 상담 만족도(1~5) 제출 — 간판 만족도 집계에 반영."""
    try:
        s = sess.submit_rating(db, session_id, user, req.rating, locale=locale)
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


@router.get("/consultant/earnings")
def consultant_earnings_ep(
    db: Session = Depends(get_db), consultant: Consultant = Depends(require_consultant)
) -> dict[str, Any]:
    """상담사 본인 수익 요약 — 오늘/이번달/올해/전체 상담건수·수익금액 + 지급대기/완료(KST 기준).
    상담사 콘솔 '내 수익' 뷰용. 자기 정산만 집계(require_consultant 게이트)."""
    return svc.consultant_earnings(db, consultant.id)


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
    return svc.self_dict(db, c)


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


def _persist_message(session_id: str, sender: str, content: str) -> bool:
    """진행 중(active) 세션에만 저장. 종료·취소·만료된 세션이면 저장하지 않고 False 반환
    (종료 세션에서의 무제한·무과금 채팅 차단).

    세션 행을 FOR UPDATE 로 잠가 상태검사~저장을 원자화 — end_session 도 같은 행을 잠그므로
    '종료 커밋 순간의 인플라이트 메시지 1건' 저장 레이스를 차단한다."""
    from sqlalchemy import select as _sel
    sf = get_session_factory()
    with sf() as db:
        s = db.execute(
            _sel(ConsultationSession).where(ConsultationSession.id == session_id).with_for_update()
        ).scalars().first()
        if s is None or s.status != "active":
            return False
        sess.add_message(db, session_id, sender, content)  # 커밋 → 잠금 해제
        return True


def _end_db(session_id: str, reason: str, *, by_consultant: bool = False) -> Optional[str]:
    sf = get_session_factory()
    with sf() as db:
        # by_consultant: 미수락 예약세션을 상담사가 종료 = 사실상 거절 → 100% 환불(사용자에 페널티 전가 금지)
        s = sess.end_session(db, session_id, reason=reason, by_consultant=by_consultant)
        return s.status if s else None  # 참여검증 결과(completed | no_show)를 브로드캐스트에 반영


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


def _touch_last_seen_db(consultant_id: int) -> None:
    """콘솔 하트비트 → last_seen_at 갱신(살아있음 표시). presence 미변경(busy 유지)."""
    sf = get_session_factory()
    with sf() as db:
        svc.touch_last_seen(db, consultant_id)


async def _session_driver(session_id: str) -> None:
    """세션 진행감시(서버 권위) — no-show 자동취소 + 카운트다운(2분전 연장경고·만료 자동종료).

    소켓이 연결된 동안만 3초 주기로 DB 상태를 재평가(재접속·연장 자동 반영). 상태는 전부 DB.
    """
    sf = get_session_factory()

    def _cfg() -> tuple[int, int, int]:
        with sf() as db:
            return (
                settings_service.get_int(db, "consultation_no_show_timeout_sec", 120),
                settings_service.get_int(db, "consultation_extend_warn_sec", 120),
                # A-2 예약 전환 세션은 미수락 유예가 김(분 단위) — 즉시 상담 120초와 구분
                settings_service.get_int(db, "consultation_reserve_grace_min", 10) * 60,
            )

    no_show_sec, warn_sec, reserve_grace_sec = await asyncio.to_thread(_cfg)
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
                        "reserved": bool(s.reservation_id),  # A-2 예약 전환 세션
                    }

            st = await asyncio.to_thread(_read)
            if st is None or st["status"] in sess._TERMINAL:
                await manager.broadcast_session(
                    session_id, {"type": "ended", "status": st["status"] if st else "gone"}
                )
                return
            now = datetime.utcnow()
            if st["status"] == "requested":
                limit_sec = reserve_grace_sec if st.get("reserved") else no_show_sec
                if (now - st["requested_at"]).total_seconds() >= limit_sec:
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
                    st_end = await asyncio.to_thread(_end_db, session_id, "expired")
                    if st_end == "no_show":  # 상담사 무응답 종료 → 전액 환불 안내 화면
                        await manager.broadcast_session(session_id, {"type": "no_show"})
                    else:
                        await manager.broadcast_session(
                            session_id, {"type": "ended", "status": st_end or "completed", "reason": "expired"}
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
                    persisted = await asyncio.to_thread(_persist_message, session_id, role, content)
                    if persisted:
                        await manager.broadcast_session(
                            session_id, {"type": "message", "sender": role, "content": content}
                        )
                    else:
                        # 종료된 상담 — 저장·릴레이하지 않고 발신자에게만 안내
                        await ws.send_json({"type": "ended", "status": "completed", "reason": "closed"})
            elif typ == "end":
                st_end = await asyncio.to_thread(
                    _end_db, session_id, f"{role}_end", by_consultant=(role == "consultant")
                )
                if st_end == "no_show":  # 상담사 무응답 종료 → 전액 환불 안내 화면
                    await manager.broadcast_session(session_id, {"type": "no_show"})
                else:
                    await manager.broadcast_session(session_id, {"type": "ended", "status": st_end or "completed"})
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
                await asyncio.to_thread(_touch_last_seen_db, cid)  # 하트비트 → last_seen 갱신(살아있음)
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
    keywords: Optional[list[str]] = Field(None, description="#전문영역 키워드(최대 8개)")
    rate_p: Optional[int] = Field(None, ge=0, description="회당 단가(P) — 비우면 전역 기본값")
    duration_min: Optional[int] = Field(None, ge=1, le=600, description="상담 시간(분) — 비우면 전역")
    commission_pct: Optional[int] = Field(None, ge=0, le=100, description="수수료% — 비우면 전역")
    price_unit: str = Field("session", pattern="^(session|minute|hour)$")
    per_min_p: Optional[int] = Field(None, ge=0, description="분당 요금 P")
    per_hour_p: Optional[int] = Field(None, ge=0, description="시간당 요금 P")
    is_active: bool = True
    status: str = Field("active", pattern="^(active|coming_soon|hidden)$")
    sort_order: int = Field(100, ge=0, le=100000)


class ConsultantUpdateReq(BaseModel):
    business_name: Optional[str] = Field(None, min_length=1, max_length=120)
    specialty: Optional[str] = Field(None, pattern="^(saju|tarot|both)$")
    intro: Optional[str] = Field(None, max_length=2000)
    keywords: Optional[list[str]] = Field(None)
    rate_p: Optional[int] = Field(None, ge=0)
    duration_min: Optional[int] = Field(None, ge=1, le=600)
    commission_pct: Optional[int] = Field(None, ge=0, le=100)
    price_unit: Optional[str] = Field(None, pattern="^(session|minute|hour)$")
    per_min_p: Optional[int] = Field(None, ge=0)
    per_hour_p: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    status: Optional[str] = Field(None, pattern="^(active|coming_soon|hidden)$")
    self_managed: Optional[bool] = None
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


@admin_router.patch("/{consultant_id:int}")
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


@admin_router.delete("/{consultant_id:int}", status_code=204)
def admin_delete_consultant(consultant_id: int, db: Session = Depends(get_db)) -> None:
    try:
        svc.delete_consultant(db, consultant_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@admin_router.post("/{consultant_id:int}/signboard")
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
    consultation_min_price_p: Optional[int] = Field(None, ge=0)  # 상담사 자율요금 하한(0=없음)
    consultation_commission_pct: Optional[int] = Field(None, ge=0, le=100)
    consultation_tax_pct: Optional[float] = Field(None, ge=0, le=100)
    consultation_no_show_timeout_sec: Optional[int] = Field(None, ge=10, le=3600)
    consultation_extend_warn_sec: Optional[int] = Field(None, ge=10, le=3600)
    consultation_retention_days: Optional[int] = Field(None, ge=1, le=365)
    # A-2 예약 취소/환불/유예 정책(N2) — GET 에는 노출되나 그동안 PATCH 스키마에 없어 설정 불가였음.
    consultation_reserve_full_refund_hours: Optional[int] = Field(None, ge=0, le=720)
    consultation_reserve_late_refund_pct: Optional[int] = Field(None, ge=0, le=100)
    consultation_reserve_grace_min: Optional[int] = Field(None, ge=1, le=1440)


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
    cycle: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """정산 명세(세션별) + 합계. cycle('YYYY-MM')=정산월(전월26~당월25 실적) 필터.
    payout_date=해당 정산월 지급예정일(당월 마지막 영업일 — 자동이체 아님, 운영자 수동 송금 기준)."""
    from backend.app.services.settlement_cycle import cycle_of, payout_date
    from datetime import datetime as _dt
    cur = cycle_of(_dt.now())
    out: dict[str, Any] = {
        "items": svc.list_settlements(db, consultant_id=consultant_id, status=status, cycle=cycle),
        "totals": svc.settlement_totals(db, cycle=cycle),
        "current_cycle": cur,
    }
    if cycle:
        out["cycle"] = cycle
        out["payout_date"] = payout_date(cycle).isoformat()
    return out


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


@admin_router.post("/{consultant_id:int}/settle-all")
def admin_settle_all(consultant_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """상담사 정산대기 전체 일괄 실지급 처리."""
    return svc.settle_all_for_consultant(db, consultant_id)


# ───────────────────────── 입점 신청(운영자 지시 2026-07-11) ─────────────────────────
# ⚠️ /api/consultation/* 는 상담 워커(:8010) 리버스 프록시 경로 — 신청은 실시간 채팅과 무관하므로
# 메인 앱이 직접 서빙하는 별도 prefix(/api/partner)를 쓴다(워커 재기동 없이 즉시 반영, main.py include).
partner_router = APIRouter(prefix="/api/partner", tags=["partner"])




@partner_router.get("/terms")
def get_partner_terms() -> dict[str, Any]:
    """입점 약관 전문(단일 소스) — 신청 화면이 이걸 표시(클라 위조 방지)."""
    from backend.app.services import partner_terms as pt
    return {"version": pt.TERMS_VERSION, "effective_date": pt.EFFECTIVE_DATE,
            "text": pt.PARTNER_TERMS, "sha256": pt.terms_sha256(), "key_points": pt.KEY_POINTS}


async def _read_doc(f: UploadFile, label: str) -> bytes:
    """업로드를 1MB 청크로 읽고 10MB 초과 시 즉시 중단 — read() 전량 RAM 적재(DoS) 방지."""
    buf = bytearray()
    while chunk := await f.read(1024 * 1024):
        buf += chunk
        if len(buf) > svc._DOC_MAX:
            raise HTTPException(status_code=400, detail=f"{label} 파일이 너무 커요 — 파일당 10MB 이하로 첨부해 주세요.")
    return bytes(buf)


@partner_router.post("/apply", status_code=201)
async def partner_apply(
    request: Request,
    specialty: str = Form("saju"),
    business_name: str = Form(...),
    contact: Optional[str] = Form(None),
    intro: Optional[str] = Form(None),
    terms_version: str = Form(...),
    agree_key_points: bool = Form(...),
    biz_license: UploadFile = File(...),                       # 사업자등록증(필수 — 운영자 지시)
    bank_book: UploadFile = File(...),                         # 통장사본(필수 — 정산 대금 지급 계좌 확인)
    extra_docs: list[UploadFile] = File(default=[]),           # 온라인 입점 증빙(플랫폼 프로필·자격 등, 선택 다중)
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """입점 신청(multipart) — [입점 신청하기] 클릭 = 약관 동의(클릭랩) + 서류 첨부.
    사업자등록증·통장사본(정산 계좌 확인) 필수, 추가 증빙(타 플랫폼 입점 이력·자격증 등) 선택. jpg/png/webp/pdf · 10MB/파일."""
    from backend.app.services import partner_terms as pt
    if specialty not in ("saju", "tarot", "both"):
        raise HTTPException(status_code=400, detail="분야를 선택해 주세요.")
    if terms_version != pt.TERMS_VERSION:
        raise HTTPException(status_code=409, detail="약관이 갱신됐어요. 화면을 새로고침해 최신 약관에 동의해 주세요.")
    if not agree_key_points:
        raise HTTPException(status_code=400, detail="핵심 조항(수수료·정산·해지) 확인에 체크해 주세요.")
    # 게이트(운영자 확정 2026-07-12): 관리자가 입점 문의를 허용한 계정만 신청서 작성 가능
    if not svc.can_apply(db, user):
        raise HTTPException(status_code=403, detail="관리자 확인 후 신청서를 작성할 수 있어요. 먼저 '입점 문의'를 남겨 주세요.")
    ip = (request.headers.get("cf-connecting-ip")
          or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
          or (request.client.host if request.client else None))
    docs: list[tuple[str, str, bytes]] = []
    lic = await _read_doc(biz_license, "사업자등록증")
    if not lic:
        raise HTTPException(status_code=400, detail="사업자등록증 파일을 첨부해 주세요.")
    docs.append(("biz_license", biz_license.filename or "사업자등록증", lic))
    bank = await _read_doc(bank_book, "통장사본")
    if not bank:
        raise HTTPException(status_code=400, detail="통장사본 파일을 첨부해 주세요.")
    docs.append(("bank_book", bank_book.filename or "통장사본", bank))
    for f in (extra_docs or [])[:5]:                            # 추가 증빙 최대 5개
        data = await _read_doc(f, "증빙")
        if data:
            docs.append(("evidence", f.filename or "증빙서류", data))
    try:
        a = svc.create_application(
            db, user, specialty=specialty, business_name=business_name,
            contact=contact, intro=intro, ip=ip, docs=docs,
        )
    except svc.DocValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))   # 중복 신청·기입점
    return svc.application_dict(a)


@partner_router.get("/apply/mine")
def partner_apply_mine(
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """내 입점 진행 상태 — 신청서 + 문의 + 작성 자격(프론트 상태머신·사이드바 노출 판정 소스)."""
    q = svc.my_inquiry(db, user)
    return {
        "application": svc.my_application(db, user),
        "inquiry": svc.inquiry_dict(q) if q else None,
        "can_apply": svc.can_apply(db, user),
    }


class InquiryReq(BaseModel):
    note: str = Field("", max_length=2000)   # 남긴 말(선택 — 경력·플랫폼 링크 등)


@partner_router.post("/inquiry", status_code=201)
def partner_inquiry(
    req: InquiryReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """입점 문의 접수 — 로그인 계정 메일 ID 기준. 관리자 [신청 허용] 후 신청서 작성 가능."""
    try:
        q = svc.create_inquiry(db, user, note=req.note)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return svc.inquiry_dict(q)


@admin_router.get("/applications")
def admin_list_applications(
    status: Optional[str] = Query(None, pattern="^(pending|approved|rejected)$"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    return {"items": svc.list_applications(db, status=status)}


class RejectReq(BaseModel):
    reason: str = Field("", max_length=300)


@admin_router.get("/inquiries")
def admin_list_inquiries(
    status: Optional[str] = Query(None, pattern="^(pending|allowed|dismissed)$"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """입점 문의 목록 — 메일 ID 확인 후 [신청 허용]/[기각] 처리."""
    return {"items": svc.list_inquiries(db, status=status)}


@admin_router.post("/inquiries/{inquiry_id:int}/allow")
def admin_allow_inquiry(inquiry_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """[신청 허용] — 해당 메일 ID 계정에 입점 신청서 작성 자격 부여(웹푸시 안내)."""
    try:
        return svc.allow_inquiry(db, inquiry_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@admin_router.post("/inquiries/{inquiry_id:int}/dismiss")
def admin_dismiss_inquiry(
    inquiry_id: int, req: RejectReq, db: Session = Depends(get_db),
) -> dict[str, Any]:
    try:
        return svc.dismiss_inquiry(db, inquiry_id, reason=req.reason)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@admin_router.post("/applications/{app_id:int}/approve")
def admin_approve_application(app_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return svc.approve_application(db, app_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@admin_router.get("/applications/{app_id:int}/docs/{doc_id}")
def admin_application_doc(app_id: int, doc_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """신청 서류 열람(관리자 전용) — docs_json 검증 경유(임의 경로 접근 차단)."""
    from backend.app.repositories.consultation_models import ConsultantApplication
    a = db.get(ConsultantApplication, app_id)
    if a is None:
        raise HTTPException(status_code=404, detail="신청서를 찾을 수 없어요.")
    try:
        path, name = svc.application_doc_path(a, doc_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    media = "application/pdf" if path.suffix.lower() == ".pdf" else f"image/{path.suffix.lstrip('.').lower().replace('jpg','jpeg')}"
    return FileResponse(path, media_type=media, filename=name)


@admin_router.post("/applications/{app_id:int}/reject")
def admin_reject_application(app_id: int, req: RejectReq, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return svc.reject_application(db, app_id, reason=req.reason)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
