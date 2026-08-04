"""마케팅 가격 에이전트 ORM — 경쟁사 시트·가드레일·권장가 이력.

설계: docs/마케팅_가격에이전트_추진계획서.md. 권장가 산출은 결정적 계산(LLM/GPU 없음).
가격 변경은 **관리자 최종 승인(클릭)** 으로만 일어난다 — 자동 적용 없음(운영자 확정 2026-07-13).

기존 `models.Base` 메타데이터에 등록(create_all + Alembic 20260713_0025 멱등).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.repositories.models import Base


class CompetitorPrice(Base):
    """경쟁사 가격 시트(관리자 수동 관리) — 권장가 산출의 근거 데이터.

    menu_key = 우리 설정 키(entry_cost_compat, credit_cost_basic 등). price_krw = 경쟁사 해당 상품가(원).
    verified_at = 관리자가 마지막으로 확인·갱신한 시각(낡음 경고 기준).
    """

    __tablename__ = "competitor_prices"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    competitor_name: Mapped[str] = mapped_column(String(80), nullable=False)
    menu_key: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    price_krw: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    verified_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)   # 관리자 이메일
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PricingGuardrail(Base):
    """메뉴별 가격 가드레일 — 권장가의 하한/상한/1회 최대변동·언더컷·반올림. 관리자 조정.

    menu_key 를 PK 로 1행/메뉴. enabled=False 면 그 메뉴는 권장 대상에서 제외(현재가 유지).
    """

    __tablename__ = "pricing_guardrails"

    menu_key: Mapped[str] = mapped_column(String(48), primary_key=True)
    floor_p: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ceiling_p: Mapped[int] = mapped_column(Integer, nullable=False, default=1_000_000)
    max_change_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=20)   # 1회 최대 변동%
    undercut_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=5)      # 경쟁사 최저 대비 언더컷%
    round_unit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)      # 반올림 단위
    round_tail: Mapped[int] = mapped_column(Integer, nullable=False, default=900)      # 끝자리 앵커(…900), 0=단위배수
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PricingRecommendation(Base):
    """권장가 산출 결과(주단위/수동) + 승인 이력.

    status: pending(승인대기) | applied(적용됨) | dismissed(무시) | skipped(데이터없음/변동없음).
    가격 변경은 applied 로 전이할 때만 일어난다(관리자 [적용] 클릭 → set_many).
    """

    __tablename__ = "pricing_recommendations"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)   # 한 조사 회차 묶음(uuid hex)
    menu_key: Mapped[str] = mapped_column(String(48), nullable=False, index=True)
    current_price: Mapped[int] = mapped_column(Integer, nullable=False)             # 산출 시점 현재가
    competitor_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    competitor_median: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommended_price: Mapped[int] = mapped_column(Integer, nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending", index=True)
    applied_from: Mapped[int | None] = mapped_column(Integer, nullable=True)        # 적용 직전값(롤백용)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
