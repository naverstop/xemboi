"""궁합(宮合) 도메인 스키마 (요청/응답)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from backend.app.domain.chat_dto import BirthDTO


class CompatPersonDTO(BaseModel):
    """궁합 대상 1명. 프로필 선택(profile_id) 또는 즉석입력(birth) 중 하나.

    - profile_id: 로그인 회원의 저장 프로필 사용(소유 검증).
    - birth: 즉석 생년월일 입력.
    둘 다 없으면 오류. 둘 다 있으면 profile_id 우선.
    """
    label: Optional[str] = Field(default=None, max_length=64)
    profile_id: Optional[int] = None
    birth: Optional[BirthDTO] = None


class CreateCompatRequest(BaseModel):
    person_a: CompatPersonDTO
    person_b: CompatPersonDTO
    depth: Literal["basic", "deep"] = "deep"
    explain_level: Literal["normal", "easy"] = "normal"
