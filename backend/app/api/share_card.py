"""B-6 공유 카드 API — 무과금·비로그인 허용(바이럴 V1·V5). PDF 토큰 서빙 패턴 미러."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.app.saju.types import BirthInput
from backend.app.services import share_card_service as svc

router = APIRouter(prefix="/api/share-card", tags=["share-card"])


class ShareCardReq(BaseModel):
    kind: str = Field("today", pattern="^(today)$")
    birth_date: str
    birth_time: Optional[str] = None
    calendar: str = Field("solar", pattern="^(solar|lunar)$")
    is_leap_month: bool = False
    gender: str = Field("male", pattern="^(male|female)$")
    apply_true_solar_time: bool = True
    birth_longitude: Optional[float] = None
    apply_equation_of_time: bool = False
    night_zi_mode: Optional[str] = None


@router.post("", status_code=201)
def create_card(req: ShareCardReq) -> dict[str, Any]:
    try:
        bi = BirthInput(
            birth_date=req.birth_date, birth_time=req.birth_time, calendar=req.calendar,
            is_leap_month=req.is_leap_month, gender=req.gender,
            apply_true_solar_time=req.apply_true_solar_time, birth_longitude=req.birth_longitude,
            apply_equation_of_time=req.apply_equation_of_time, night_zi_mode=req.night_zi_mode or "yaja",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    png, meta = svc.render_today_card(bi)
    out = svc.store_card(png, f"오늘의운세_{date.today():%Y%m%d}")
    out["meta"] = meta
    return out


@router.get("/{token}")
def get_card(token: str, download: int = Query(0)) -> FileResponse:
    try:
        path, name = svc.card_path(token)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if download:
        return FileResponse(path, media_type="image/png",
                            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})
    return FileResponse(path, media_type="image/png")
