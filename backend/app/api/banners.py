"""공개 배너 노출 API.

슬롯별 활성 배너 1건(weight desc) 또는 전체 반환. 비로그인/유료/관리자 가시성은
프론트에서 me.ads_hidden 으로 결정한다 (백엔드는 정보만 제공).
"""
from __future__ import annotations

import random
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.repositories.auth_models import Banner
from backend.app.services.admin_service import VALID_SLOTS

router = APIRouter(prefix="/api/banners", tags=["banners"])


def _banner_dict(b: Banner) -> dict[str, Any]:
    return {
        "id": b.id,
        "slot": b.slot,
        "image_url": b.image_url,
        "link_url": b.link_url,
        "title": b.title,
        "weight": b.weight,
    }


@router.get("")
def list_active(
    slot: Optional[str] = Query(None),
    pick_one: bool = Query(False, description="슬롯당 weight 가중 1건만 반환"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if slot and slot not in VALID_SLOTS:
        return {"items": []}
    stmt = select(Banner).where(Banner.active == True)  # noqa: E712
    if slot:
        stmt = stmt.where(Banner.slot == slot)
    rows = list(db.execute(stmt).scalars().all())
    if not pick_one:
        rows.sort(key=lambda b: (b.slot, -b.weight, -b.id))
        return {"items": [_banner_dict(b) for b in rows]}

    # weight 가중 선택, 슬롯별 1건
    by_slot: dict[str, list[Banner]] = {}
    for b in rows:
        by_slot.setdefault(b.slot, []).append(b)
    picked: list[dict[str, Any]] = []
    for s, group in by_slot.items():
        weights = [max(1, b.weight) for b in group]
        chosen = random.choices(group, weights=weights, k=1)[0]
        picked.append(_banner_dict(chosen))
    return {"items": picked}
