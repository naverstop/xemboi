"""B-11 무료 스낵 테스트 API — 무과금·비로그인·무저장(바이럴 V3)."""
from __future__ import annotations

from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.app.saju.types import BirthInput
from backend.app.services import snack_service as svc

router = APIRouter(prefix="/api/snack", tags=["snack"])


class SnackReq(BaseModel):
    birth_date: str
    birth_time: Optional[str] = None
    calendar: str = Field("solar", pattern="^(solar|lunar)$")
    is_leap_month: bool = False
    gender: str = Field("male", pattern="^(male|female)$")
    apply_true_solar_time: bool = True
    birth_longitude: Optional[float] = None
    night_zi_mode: Optional[str] = None
    make_card: bool = False   # True면 결과 공유 카드도 함께 생성


def _birth(req: SnackReq) -> BirthInput:
    return BirthInput(
        birth_date=req.birth_date, birth_time=req.birth_time, calendar=req.calendar,
        is_leap_month=req.is_leap_month, gender=req.gender,
        apply_true_solar_time=req.apply_true_solar_time, birth_longitude=req.birth_longitude,
        night_zi_mode=req.night_zi_mode or "yaja",
    )


@router.get("")
def list_tests() -> dict[str, Any]:
    # icon: 허브 카드용 FLUX 엠블럼(이모지 대체). 파일이 없으면 프론트가 emoji 로 폴백.
    return {"tests": [{"test_id": t, **svc.TEST_META[t], "icon": f"/snack/hub_{t}.webp"} for t in svc.TEST_IDS]}


@router.post("/{test_id}")
def run_snack(test_id: str, req: SnackReq) -> dict[str, Any]:
    try:
        result = svc.run_test(test_id, _birth(req))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if req.make_card:
        try:
            png = svc.render_result_card(test_id, result)
            result["card"] = svc.store_card(png, test_id)
        except Exception:  # noqa: BLE001 — 카드 실패해도 결과는 반환
            result["card"] = None
    return result


# 카드 서빙은 별도 prefix(정적 이미지) — /api/snack-card/{token}
card_router = APIRouter(prefix="/api/snack-card", tags=["snack"])


@card_router.get("/{token}")
def get_card(token: str, download: int = Query(0)) -> FileResponse:
    try:
        path = svc.card_path(token)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if download:
        return FileResponse(path, media_type="image/png",
                            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote('snack.png')}"})
    return FileResponse(path, media_type="image/png")
