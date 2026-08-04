"""B-10 궁합 상대 초대(바이럴 V2) — 초대 링크로 상대가 자기 생일만 입력하면 양측에 결과 티저.

과금 원칙(입장료 우회 금지 — [[security-audit-status]] G 게이트 존중):
  수락 시 반환은 '종합 등급 + 한 줄' 티저뿐이다. 펜타곤·축별 점수·해설 등 본 결과는
  기존 궁합 메뉴(입장료)에서만 — 초대는 진입 동선(가입 유도)이다.
개인정보: 초대 조회(GET)에서 초대자 생일은 절대 비노출(표시명 마스킹만). 수락 시 상대 생일은
  결과 계산에만 쓰고 티저와 함께 저장(초대자가 정식 궁합으로 이어갈 때 프리필 — 수락 화면에 고지).
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from backend.app.core.db import get_db
from backend.app.core.deps import get_current_user, get_optional_user
from backend.app.repositories.auth_models import User
from backend.app.repositories.models import Base
from backend.app.services.review_service import mask_display_name

router = APIRouter(prefix="/api/compatibility/invites", tags=["compat-invite"])

_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")
_EXPIRE_DAYS = 7


class CompatInvite(Base):
    """궁합 초대 — 회원(초대자)만 생성, 7일 만료. 결과는 등급 티저만 저장."""

    __tablename__ = "compat_invites"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    inviter_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    inviter_name: Mapped[str] = mapped_column(String(32), nullable=False, default="익명")  # 마스킹 스냅샷
    a_birth_json: Mapped[str] = mapped_column(Text, nullable=False)      # 초대자 생일(비노출)
    b_birth_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # 수락자 생일(수락 후)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending", index=True)
    teaser_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # {grade,total,line}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BirthBody(BaseModel):
    birth_date: str
    birth_time: Optional[str] = None
    calendar: str = Field("solar", pattern="^(solar|lunar)$")
    is_leap_month: bool = False
    gender: str = Field("male", pattern="^(male|female)$")
    apply_true_solar_time: bool = True
    birth_longitude: Optional[float] = None
    night_zi_mode: Optional[str] = None


class InviteCreateReq(BirthBody):
    label: Optional[str] = Field(None, max_length=24)   # 상대 호칭(예: 남자친구)


def _build(birth: BirthBody):
    from backend.app.saju.engine import build_chart
    from backend.app.saju.types import BirthInput
    return build_chart(BirthInput(
        birth_date=birth.birth_date, birth_time=birth.birth_time, calendar=birth.calendar,
        is_leap_month=birth.is_leap_month, gender=birth.gender,
        apply_true_solar_time=birth.apply_true_solar_time, birth_longitude=birth.birth_longitude,
        night_zi_mode=birth.night_zi_mode or "yaja",
    ), with_daewoon=False)


@router.post("", status_code=201)
def create_invite(
    req: InviteCreateReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """초대 생성(회원·무과금) — 내 생일을 담은 7일짜리 링크."""
    try:
        _build(req)   # 생일 유효성 선검증(잘못된 초대 방지)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = uuid.uuid4().hex
    inv = CompatInvite(
        token=token, inviter_user_id=user.id, inviter_name=mask_display_name(user),
        a_birth_json=json.dumps(req.model_dump(exclude={"label"}), ensure_ascii=False),
        status="pending", expires_at=datetime.utcnow() + timedelta(days=_EXPIRE_DAYS),
    )
    db.add(inv)
    db.commit()
    return {"token": token, "url": f"/compat-invite/{token}", "expires_at": inv.expires_at.isoformat()}


def _get(db: Session, token: str) -> CompatInvite:
    if not _TOKEN_RE.match(token or ""):
        raise HTTPException(status_code=404, detail="잘못된 초대예요.")
    inv = db.execute(select(CompatInvite).where(CompatInvite.token == token)).scalar_one_or_none()
    if inv is None:
        raise HTTPException(status_code=404, detail="초대를 찾을 수 없어요.")
    if inv.status == "pending" and inv.expires_at < datetime.utcnow():
        inv.status = "expired"
        db.commit()
    return inv


@router.get("/{token}")
def get_invite(token: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """초대 랜딩(비인증) — 초대자 마스킹 표시명만. 생일 등 개인정보 비노출."""
    inv = _get(db, token)
    out: dict[str, Any] = {
        "status": inv.status,
        "inviter_name": inv.inviter_name,
        "expires_at": inv.expires_at.isoformat(),
    }
    if inv.status == "accepted" and inv.teaser_json:
        out["teaser"] = json.loads(inv.teaser_json)
    return out


@router.post("/{token}/accept")
def accept_invite(token: str, req: BirthBody, db: Session = Depends(get_db)) -> dict[str, Any]:
    """수락(비인증 허용) — 상대 생일 입력 → 종합 등급 티저 계산·저장. 본 결과는 궁합 메뉴로."""
    inv = _get(db, token)
    if inv.status == "expired":
        raise HTTPException(status_code=410, detail="초대가 만료됐어요. 새 초대를 부탁해 보세요.")
    if inv.status == "accepted":
        return {"status": "accepted", "teaser": json.loads(inv.teaser_json or "{}"),
                "note": "이미 수락된 초대예요."}
    from backend.app.saju.compatibility import compute_compatibility
    try:
        a_birth = BirthBody(**json.loads(inv.a_birth_json))
        chart_a = _build(a_birth)
        chart_b = _build(req)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    result = compute_compatibility(chart_a, chart_b)
    # 종합(B 관점 우선) 등급 + 한 줄만 — 입장료 우회 금지(펜타곤·축점수·해설 미제공)
    persp = result.perspectives.get("B") or next(iter(result.perspectives.values()))
    # 5축 점수 동봉 — 티저 그래프(페이드 가림)용. 정확 수치·근거·해설은 유료 화면에서만(운영자 결정).
    axes = [{"key": f.key, "label": f.label, "score": f.score} for f in result.factors.values()]
    teaser = {"grade": persp.grade, "total": persp.total, "line": persp.interpretation, "axes": axes}
    inv.b_birth_json = json.dumps(req.model_dump(), ensure_ascii=False)
    inv.teaser_json = json.dumps(teaser, ensure_ascii=False)
    inv.status = "accepted"
    inv.accepted_at = datetime.utcnow()
    db.commit()
    # 초대자에게 웹푸시(실패 무시)
    try:
        from backend.app.services import push_service
        push_service.send_to_user(
            db, inv.inviter_user_id,
            title="궁합 초대 수락!",
            body=f"상대방이 생일을 입력했어요 — 두 분의 궁합은 「{teaser['grade']}」. 자세한 풀이를 확인해 보세요.",
            url=f"/compatibility?invite={inv.token}",   # 궁합 페이지가 두 생일 자동 채움(prefill 연계)
        )
    except Exception:  # noqa: BLE001
        pass
    return {"status": "accepted", "teaser": teaser}


@router.get("/{token}/prefill")
def invite_prefill(
    token: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """초대자 전용 — 수락된 초대의 두 생일을 정식 궁합 입력으로 프리필(소유 검증)."""
    inv = _get(db, token)
    if inv.inviter_user_id != user.id:
        raise HTTPException(status_code=403, detail="내 초대가 아니에요.")
    if inv.status != "accepted" or not inv.b_birth_json:
        raise HTTPException(status_code=400, detail="아직 상대가 수락하지 않았어요.")
    return {"a": json.loads(inv.a_birth_json), "b": json.loads(inv.b_birth_json)}
