"""B-4 부적 발행 API — 회원 전용, 생성 시 amulet_cost_p 차감(실패 시 무과금).

POST /api/amulet          : 생년월일+목적 → 결정적 룰 발행 + PNG 각인 → 토큰 URL
GET  /api/amulet/{token}  : PNG 반환(기본 인라인, ?download=1 첨부) — PDF 토큰 패턴 미러
"""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.deps import get_current_user
from backend.app.repositories.auth_models import User
from backend.app.saju.types import BirthInput
from backend.app.services import amulet_service as svc

router = APIRouter(prefix="/api/amulet", tags=["amulet"])


class AmuletReq(BaseModel):
    birth_date: str
    birth_time: Optional[str] = None
    calendar: str = Field("solar", pattern="^(solar|lunar)$")
    is_leap_month: bool = False
    gender: str = Field("male", pattern="^(male|female)$")
    apply_true_solar_time: bool = True
    birth_longitude: Optional[float] = None
    apply_equation_of_time: bool = False
    night_zi_mode: Optional[str] = None
    purpose: str = Field(pattern="^(wealth|love|exam|health|protect|biz)$")


@router.post("", status_code=201)
def issue(req: AmuletReq, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict[str, Any]:
    try:
        bi = BirthInput(
            birth_date=req.birth_date,
            birth_time=req.birth_time,
            calendar=req.calendar,
            is_leap_month=req.is_leap_month,
            gender=req.gender,
            apply_true_solar_time=req.apply_true_solar_time,
            birth_longitude=req.birth_longitude,
            apply_equation_of_time=req.apply_equation_of_time,
            night_zi_mode=req.night_zi_mode or "yaja",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        result = svc.issue_amulet(db, user, bi, req.purpose)
    except ValueError as e:
        # 잔액 부족(adjust_credit) → 402 결제 유도
        if "insufficient" in str(e):
            raise HTTPException(status_code=402, detail="포인트가 부족해요. 충전 후 이용해 주세요.")
        raise HTTPException(status_code=400, detail=str(e))
    # 해설·추가질문(공용 tools 스트림)용 세션 — 발행 근거를 컨텍스트로. 실패해도 발행 자체는 유지.
    try:
        from backend.app.saju.engine import build_chart
        from backend.app.services import tool_service
        chart = build_chart(bi, with_daewoon=False)
        result["tool_id"] = tool_service.persist_free_session(
            db, "amulet", req.purpose, birth_date=bi.birth_date, birth_time=bi.birth_time,
            calendar=req.calendar, is_leap_month=req.is_leap_month, gender=req.gender,
            apply_true_solar_time=req.apply_true_solar_time,
            chart_json=chart.model_dump(mode="json"),
            input_json={"purpose": req.purpose},
            # token·url 도 저장 — '지난 결과' 재열람(getTool) 시 부적 이미지 URL 복원용(무차감)
            result_json={
                "amulet": result.get("amulet"),
                "token": result.get("token"),
                "url": result.get("url"),
                "download_url": result.get("download_url"),
            }, user=user,
        )
    except Exception:  # noqa: BLE001
        pass
    return result


@router.get("/{token}")
def get_amulet(token: str, download: int = Query(0)) -> FileResponse:
    try:
        path, name = svc.amulet_path(token)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if download:
        return FileResponse(
            path, media_type="image/png",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"},
        )
    return FileResponse(path, media_type="image/png")
