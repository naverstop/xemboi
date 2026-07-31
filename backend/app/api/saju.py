"""사주명식 API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.core.deps import get_locale
from backend.app.domain.chat_dto import BirthDTO
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, SajuChart

router = APIRouter(prefix="/api/saju", tags=["saju"])


@router.post("/chart", response_model=SajuChart)
def post_chart(birth: BirthDTO, locale: str = Depends(get_locale)) -> SajuChart:
    """생년월일/시/성별 → 사주 8자 + 오행 + 십성 + 대운.

    locale(요청 로케일 X-Locale→user→Accept-Language→default)이 역법/경도를 결정한다:
    vi 면 105°E·hongoc_duc, ko 면 서울·sxtwl. birth_longitude/균시차/자시관법도 함께 전달.
    """
    try:
        bi = BirthInput(
            birth_date=birth.birth_date,
            birth_time=birth.birth_time,
            calendar=birth.calendar,
            is_leap_month=birth.is_leap_month,
            gender=birth.gender,
            apply_true_solar_time=birth.apply_true_solar_time,
            birth_longitude=birth.birth_longitude,
            apply_equation_of_time=birth.apply_equation_of_time,
            night_zi_mode=birth.night_zi_mode,
            locale=locale,
        )
    except ValueError as e:  # 없는 윤달 입력 등 → 깔끔한 400(R1 메시지 전달)
        raise HTTPException(status_code=400, detail=str(e))
    return build_chart(bi)
