"""타로 도메인 스키마 (요청/응답)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class CreateTarotRequest(BaseModel):
    section: str = Field(min_length=1, max_length=32)   # love|money|career|study|choice|life
    question: str = Field(default="", max_length=500)


class TarotPicksRequest(BaseModel):
    """부채꼴에서 고른 카드 인덱스(0~77, 스프레드 장수만큼, 중복 불가)."""
    indices: list[int] = Field(min_length=1, max_length=11)


class TarotMessageRequest(BaseModel):
    message: str = ""                                   # ""=최초 해석(입장료 포함 무과금)
    depth: Literal["basic", "deep"] = "deep"
