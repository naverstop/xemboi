"""명리 도구(작명/개명/아호/택일) 요청 스키마."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

from backend.app.domain.chat_dto import BirthDTO


class NamingRequest(BaseModel):
    kind: Literal["jakmyeong", "gaemyeong", "aho"]
    birth: BirthDTO
    surname: Optional[str] = Field(default=None, max_length=4)       # 한자 성 (작명)
    current_name: Optional[str] = Field(default=None, max_length=10) # 한자 현재이름 (개명: 성+이름)
    reading: Optional[str] = Field(default=None, max_length=10)      # 사용자 입력 한글 음 (개명: 다음 한자 표시 정정)


class TaekilRequest(BaseModel):
    birth: BirthDTO
    birth2: Optional[BirthDTO] = None   # 출산택일: 두 번째 부모(선택)
    purpose: Literal[
        "wedding", "birth", "moving", "opening", "contract",
        "ceremony", "surgery", "travel", "general",
    ] = "general"
    start_date: date
    days: int = Field(default=60, ge=7, le=120)


class ToolMessageRequest(BaseModel):
    message: str = ""
    depth: Literal["basic", "deep"] = "deep"
    explain_level: Literal["normal", "easy", "brief"] = "normal"
