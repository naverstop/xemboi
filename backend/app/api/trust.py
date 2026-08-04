"""B-5 신뢰 지표 공개 API — 누적 상담수·실측 만족도(피드백 데이터). 비인증.

과장 금지 원칙: 전부 DB 실측값이며, 표본이 작으면(콜드스타트) 프론트가 해당 항목을 숨긴다.
COUNT 집계는 프로세스 캐시 10분 — 랜딩 트래픽이 DB를 두드리지 않게.
"""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.repositories.auth_models import MessageFeedback, Review
from backend.app.repositories.models import ChatSession, CompatibilitySession, TarotSession, ToolSession

router = APIRouter(prefix="/api/trust-stats", tags=["trust"])

_TTL_SEC = 600
_cache: dict[str, Any] = {"ts": 0.0, "data": None}


@router.get("")
def trust_stats(db: Session = Depends(get_db)) -> dict[str, Any]:
    now = time.time()
    if _cache["data"] is not None and now - _cache["ts"] < _TTL_SEC:
        return _cache["data"]

    def _count(model) -> int:
        return int(db.execute(select(func.count()).select_from(model)).scalar_one())

    consultations = (
        _count(ChatSession) + _count(CompatibilitySession) + _count(ToolSession) + _count(TarotSession)
    )
    fb_total = _count(MessageFeedback)
    fb_up = int(db.execute(
        select(func.count()).select_from(MessageFeedback).where(MessageFeedback.rating == 1)
    ).scalar_one())
    reviews = int(db.execute(
        select(func.count()).select_from(Review).where(Review.status == "approved")
    ).scalar_one())

    data = {
        "consultations": consultations,                 # 누적 상담(사주·궁합·택일작명·타로 세션 합)
        "feedback_votes": fb_total,                     # 만족도 표본 수
        "satisfaction_pct": round(fb_up / fb_total * 100) if fb_total else None,
        "reviews": reviews,                             # 승인 게시 후기 수
    }
    _cache.update(ts=now, data=data)
    return data
