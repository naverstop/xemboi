"""사용 현황(현재 통계) 모델 — 운영자 지시 2026-07-11.

관리자 '현재 통계' 탭용 경량 수집:
- UsageDevice: 익명 기기 1행(uuid) — 현재 접속(최근 heartbeat)·오늘 방문자·PWA 설치(플랫폼별).
  개인정보 없음(랜덤 uuid + 플랫폼 구분만). 로그인 여부와 무관하게 기기 단위.
- UsageDaily: 일자×종류(page/click)×키 집계 카운터 — 메뉴별 사용도·버튼 클릭 현황.
  원시 이벤트를 쌓지 않고 카운터 증분만(저장량·프라이버시 최소화).
"""
from __future__ import annotations

from datetime import date as date_t, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.repositories.models import Base


class UsageDevice(Base):
    __tablename__ = "usage_devices"

    device_id: Mapped[str] = mapped_column(String(36), primary_key=True)   # 클라 생성 uuid
    platform: Mapped[str] = mapped_column(String(16), nullable=False, default="other")  # ios/android/desktop/other
    is_pwa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 한 번이라도 standalone 실행
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False, index=True)


class UsageDaily(Base):
    __tablename__ = "usage_daily"
    __table_args__ = (UniqueConstraint("day", "kind", "key", name="uq_usage_daily"),)

    # sqlite(테스트)는 INTEGER PK만 autoincrement — PG는 BIGSERIAL(마이그레이션) 그대로
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"),
                                    primary_key=True, autoincrement=True)
    day: Mapped[date_t] = mapped_column(Date, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)    # page | click
    key: Mapped[str] = mapped_column(String(64), nullable=False)    # 메뉴 키 / 버튼 키
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
