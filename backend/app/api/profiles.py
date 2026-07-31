"""다중 사주 프로필 API (계획 7-D.2).

본인 외 가족·지인 사주를 저장/전환. 프로필로 채팅 세션을 시작할 수 있다.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.db import get_db
from backend.app.core.deps import get_current_user
from backend.app.repositories.auth_models import SajuProfile, User

router = APIRouter(prefix="/api/profiles", tags=["profiles"])

_CALENDARS = {"solar", "lunar"}
_GENDERS = {"male", "female"}


class ProfileReq(BaseModel):
    label: str = Field(..., min_length=1, max_length=64)
    birth_date: date
    birth_time: Optional[str] = Field(default=None, max_length=8)
    calendar: str = "solar"
    is_leap_month: bool = False
    gender: str = "male"
    apply_true_solar_time: bool = False
    birth_longitude: Optional[float] = None
    apply_equation_of_time: bool = False
    night_zi_mode: Optional[str] = Field(default=None, max_length=8)
    is_default: bool = False


class ProfilePatchReq(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=64)
    birth_date: Optional[date] = None
    birth_time: Optional[str] = Field(default=None, max_length=8)
    calendar: Optional[str] = None
    is_leap_month: Optional[bool] = None
    gender: Optional[str] = None
    apply_true_solar_time: Optional[bool] = None
    birth_longitude: Optional[float] = None
    apply_equation_of_time: Optional[bool] = None
    night_zi_mode: Optional[str] = Field(default=None, max_length=8)
    is_default: Optional[bool] = None


def _to_dict(p: SajuProfile) -> dict[str, Any]:
    return {
        "id": p.id,
        "label": p.label,
        "birth_date": p.birth_date.isoformat(),
        "birth_time": p.birth_time,
        "calendar": p.calendar,
        "is_leap_month": p.is_leap_month,
        "gender": p.gender,
        "apply_true_solar_time": p.apply_true_solar_time,
        "birth_longitude": p.birth_longitude,
        "apply_equation_of_time": p.apply_equation_of_time,
        "night_zi_mode": p.night_zi_mode,
        "is_default": p.is_default,
        "created_at": p.created_at.isoformat(),
    }


def _validate(calendar: str | None, gender: str | None) -> None:
    if calendar is not None and calendar not in _CALENDARS:
        raise HTTPException(status_code=400, detail="invalid calendar")
    if gender is not None and gender not in _GENDERS:
        raise HTTPException(status_code=400, detail="invalid gender")


def _clear_default(db: Session, user_id: int, keep_id: int | None) -> None:
    rows = db.execute(
        select(SajuProfile).where(SajuProfile.user_id == user_id, SajuProfile.is_default.is_(True))
    ).scalars().all()
    for r in rows:
        if r.id != keep_id:
            r.is_default = False


@router.get("")
def list_profiles(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    rows = db.execute(
        select(SajuProfile)
        .where(SajuProfile.user_id == user.id)
        .order_by(SajuProfile.is_default.desc(), SajuProfile.id)
    ).scalars().all()
    return {"items": [_to_dict(p) for p in rows]}


@router.post("", status_code=201)
def create_profile(
    req: ProfileReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    s = get_settings()
    _validate(req.calendar, req.gender)
    cnt = db.execute(
        select(SajuProfile).where(SajuProfile.user_id == user.id)
    ).scalars().all()
    if len(cnt) >= s.max_profiles_per_user:
        raise HTTPException(status_code=409, detail="profile_limit_reached")
    p = SajuProfile(
        user_id=user.id,
        label=req.label,
        birth_date=req.birth_date,
        birth_time=req.birth_time,
        calendar=req.calendar,
        is_leap_month=req.is_leap_month,
        gender=req.gender,
        apply_true_solar_time=req.apply_true_solar_time,
        birth_longitude=req.birth_longitude,
        apply_equation_of_time=req.apply_equation_of_time,
        night_zi_mode=req.night_zi_mode,
        is_default=req.is_default or len(cnt) == 0,
    )
    db.add(p)
    db.flush()
    if p.is_default:
        _clear_default(db, user.id, p.id)
    db.commit()
    db.refresh(p)
    return _to_dict(p)


def _get_owned(db: Session, user_id: int, profile_id: int) -> SajuProfile:
    p = db.get(SajuProfile, profile_id)
    if p is None or p.user_id != user_id:
        raise HTTPException(status_code=404, detail="profile not found")
    return p


@router.patch("/{profile_id}")
def update_profile(
    profile_id: int,
    req: ProfilePatchReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    _validate(req.calendar, req.gender)
    p = _get_owned(db, user.id, profile_id)
    data = req.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(p, k, v)
    db.flush()
    if data.get("is_default"):
        _clear_default(db, user.id, p.id)
    db.commit()
    db.refresh(p)
    return _to_dict(p)


@router.delete("/{profile_id}", status_code=204)
def delete_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    p = _get_owned(db, user.id, profile_id)
    db.delete(p)
    db.commit()
