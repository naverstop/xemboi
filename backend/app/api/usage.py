"""사용 현황 수집(공개) — 관리자 '현재 통계' 탭 데이터 소스 (운영자 지시 2026-07-11).

POST /api/usage/beat: 기기 heartbeat + 페이지뷰/클릭 이벤트 배치.
- 익명(비로그인 포함) 허용 — device_id는 클라이언트 생성 uuid, 개인정보 없음.
- 원시 이벤트 저장 없이 일별 카운터 증분만(usage_daily) + 기기 1행 갱신(usage_devices).
- 남용 방어: uuid 형식 검증·이벤트 20개 상한·키 화이트리스트 문자만. 전역 rate limit(default) 적용.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.repositories.usage_models import UsageDaily, UsageDevice

router = APIRouter(prefix="/api/usage", tags=["usage"])

_DEVICE_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_KEY_RE = re.compile(r"^[a-z0-9:_-]{1,64}$")
_PLATFORMS = {"ios", "android", "desktop", "other"}


class BeatEvent(BaseModel):
    kind: str = Field(pattern="^(page|click)$")
    key: str = Field(min_length=1, max_length=64)
    n: int = Field(default=1, ge=1, le=50)


class BeatIn(BaseModel):
    device_id: str = Field(min_length=36, max_length=36)
    platform: str = "other"
    standalone: bool = False
    events: list[BeatEvent] = Field(default_factory=list, max_length=20)


from backend.app.services.usage_service import bump_daily as _bump_daily


def _bump(db: Session, day: date, kind: str, key: str, n: int) -> None:
    _bump_daily(db, kind, key, n, day=day)


@router.post("/beat")
def usage_beat(body: BeatIn, db: Session = Depends(get_db)) -> dict:
    if not _DEVICE_RE.match(body.device_id or ""):
        return {"ok": False}                       # 조용히 무시(수집용 — 오류 노이즈 불필요)
    platform = body.platform if body.platform in _PLATFORMS else "other"
    now = datetime.now()

    dev = db.get(UsageDevice, body.device_id)
    if dev is None:
        dev = UsageDevice(device_id=body.device_id, platform=platform,
                          is_pwa=bool(body.standalone), first_seen=now, last_seen=now)
        db.add(dev)
    else:
        dev.last_seen = now
        dev.platform = platform                    # 기기 플랫폼 최신값 유지
        if body.standalone:
            dev.is_pwa = True                      # 한 번이라도 standalone 실행 = 설치됨(래칫)

    today = now.date()
    for ev in body.events[:20]:
        if _KEY_RE.match(ev.key):
            _bump(db, today, ev.kind, ev.key, ev.n)

    db.commit()
    return {"ok": True}
