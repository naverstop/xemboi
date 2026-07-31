"""사주명식 API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.domain.chat_dto import BirthDTO
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, SajuChart

router = APIRouter(prefix="/api/saju", tags=["saju"])


@router.post("/chart", response_model=SajuChart)
def post_chart(birth: BirthDTO) -> SajuChart:
    """생년월일/시/성별 → 사주 8자 + 오행 + 십성 + 대운."""
    try:
        bi = BirthInput(
            birth_date=birth.birth_date,
            birth_time=birth.birth_time,
            calendar=birth.calendar,
            is_leap_month=birth.is_leap_month,
            gender=birth.gender,
            apply_true_solar_time=birth.apply_true_solar_time,
        )
    except ValueError as e:  # 없는 윤달 입력 등 → 깔끔한 400(R1 메시지 전달)
        raise HTTPException(status_code=400, detail=str(e))
    return build_chart(bi)
