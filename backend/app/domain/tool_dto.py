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
    # 작명 옵션 — 이름 글자 수(2=두 자 이름 구○○, 1=외자 이름 구본式)
    name_len: int = Field(default=2, ge=1, le=2)
    # 돌림자(항렬자) 고정 — 한자 1자 + 위치("front"=성 다음 앞자리, "back"=끝자리). name_len==2에서만 적용.
    dollimja: Optional[str] = Field(default=None, max_length=1)
    dollimja_pos: Literal["front", "back"] = "back"


class TaekilRequest(BaseModel):
    birth: BirthDTO
    birth2: Optional[BirthDTO] = None   # 선택 — 출산택일=두 번째 부모 / 결혼택일=상대(배우자) 명식(③a 커플 정밀)
    purpose: Literal[
        "wedding", "birth", "moving", "opening", "contract",
        "ceremony", "surgery", "travel", "general",
    ] = "general"
    start_date: date
    days: int = Field(default=60, ge=7, le=120)


class SinnyeonRequest(BaseModel):
    """B-1 신년운세 — 대상 연도(비우면 올해)."""
    birth: BirthDTO
    year: Optional[int] = Field(default=None, ge=1950, le=2100)


class ToolMessageRequest(BaseModel):
    message: str = ""
    depth: Literal["basic", "deep"] = "deep"
    explain_level: Literal["normal", "easy", "brief"] = "normal"
