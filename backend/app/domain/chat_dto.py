"""채팅 도메인 스키마 (요청/응답)."""
from __future__ import annotations

from datetime import date, datetime, time as dtime
from typing import Literal

from pydantic import BaseModel, Field

from backend.app.saju.types import CalendarType, Gender


class BirthDTO(BaseModel):
    """채팅 시작 전 필수로 받는 생년월일/시 정보.

    - birth_time 은 사용자가 모를 수 있어 선택(None=시미상).
    - 음력 입력 시 calendar='lunar' + 필요 시 is_leap_month=True.
    """
    birth_date: date
    birth_time: dtime | None = None
    calendar: CalendarType = CalendarType.SOLAR
    is_leap_month: bool = False
    gender: Gender = Gender.MALE
    apply_true_solar_time: bool = True                   # 제품 기본 ON(전문 만세력 관행)
    birth_longitude: float | None = None                 # 출생지 경도(°E); None이면 서울
    apply_equation_of_time: bool = False                 # 균시차 반영
    night_zi_mode: Literal["yaja", "jeongja"] = "yaja"   # 자시 관법(야자시/정자시)
    locale: Literal["ko", "vi"] = "ko"                    # ko=한국 역법/KST, vi=베트남 역법/ICT


class ChatSourceDTO(BaseModel):
    source: str
    chunk_id: int
    score: float
    text_preview: str


class ChatMessageDTO(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime
    sources: list[ChatSourceDTO] = Field(default_factory=list)
    id: int | None = None
    is_preview: bool = False
    preview_revealed: bool = False
    credits_charged: int = 0
    reveal_credits_charged: int = 0
    reveal_cost: int = 0  # 전체보기 시 차감될 이연 금액(회원 미리보기)


class CreateSessionRequest(BaseModel):
    birth: BirthDTO
    top_k: int | None = None


class CreateSessionResponse(BaseModel):
    session_id: str
    saju_summary: str | None = None
    saju_chart: dict | None = None


class PostMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    top_k: int | None = None
    depth: Literal["basic", "deep"] = "basic"  # 기본 / 심화(듀얼 LLM 보강)
    explain_level: Literal["normal", "easy", "brief"] = "normal"  # 전문 / 쉽게 / 핵심만(100단어)


class PostMessageResponse(BaseModel):
    session_id: str
    answer: str
    sources: list[ChatSourceDTO]
    total_messages: int
    assistant_message_id: int | None = None
    is_preview: bool = False
    preview_revealed: bool = False
    full_length: int = 0
    preview_length: int = 0
    credits_charged: int = 0
    reveal_cost: int = 0  # 전체보기 시 차감될 이연 금액(회원 미리보기)
    balance_after: int | None = None
    billing_mode: Literal["anonymous_preview", "daily_free_preview", "free_quota", "membership_full", "paid_full", "paid_preview", "admin_full"] = "paid_full"


class SessionHistoryResponse(BaseModel):
    session_id: str
    messages: list[ChatMessageDTO]
    has_saju: bool
