"""1:1 인적 상담(입점업체 상담사 ↔ 사용자 실시간 채팅) ORM.

입점업체(상담사)·상담 세션·메시지·정산 원장. 기존 `models.Base` 메타데이터에 등록되어
`create_all` 로 생성되고 Alembic(20260704_0013)으로도 멱등 관리된다.

설계·의사결정: [[consultation-1on1-plan]]. Phase 1 은 스키마 + 관리자 등록 + 리스트까지.
실시간 WebSocket(presence/타이머)·과금·요약 PDF·정산은 Phase 2~4 에서 채운다.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.repositories.models import Base


class Consultant(Base):
    """입점업체(오프라인 상담사) — 관리자 등록. login_email 로 User 계정과 매핑.

    가입 전 이메일도 등록 가능(user_id NULL) → 해당 이메일로 가입/로그인 시 자동 연결한다.
    개별 단가/시간/수수료가 NULL 이면 전역 기본값(settings_service)으로 폴백한다.
    """

    __tablename__ = "consultants"
    __table_args__ = (UniqueConstraint("login_email", name="uq_consultants_login_email"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 입점 ID = 로그인 이메일(User.email 과 매핑)
    login_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # 매핑된 User.id (가입 전이면 NULL → 가입/로그인 시 연결)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    business_name: Mapped[str] = mapped_column(String(120), nullable=False)  # 업체명(간판)
    specialty: Mapped[str] = mapped_column(
        String(8), nullable=False, default="saju"
    )  # saju | tarot | both
    signboard_image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)  # 간판 이미지
    intro: Mapped[str | None] = mapped_column(Text, nullable=True)  # 소개
    # 개별 단가/시간/수수료 — NULL 이면 전역 기본값(settings_service) 폴백
    rate_p: Mapped[int | None] = mapped_column(Integer, nullable=True)          # 회당 포인트(P)
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)    # 상담 시간(분)
    commission_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 플랫폼 수수료(%)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 실시간 접속상태(런타임 갱신) — offline | online(대기) | busy(상담중). Phase 2 WS presence 가 갱신.
    presence: Mapped[str] = mapped_column(
        String(8), nullable=False, default="offline", server_default="offline"
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)  # 리스트 정렬(작을수록 위)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class ConsultationSession(Base):
    """1:1 상담 세션 — 요청→수락→진행→종료 수명주기(서버 권위). 포인트 블록제.

    상태: requested(요청) | accepted(수락·차감) | active(진행) | completed(정상종료)
          | cancelled(취소) | no_show(미응답 자동취소·환불) | expired(시간만료)
    """

    __tablename__ = "consultation_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # uuid4().hex
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    consultant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("consultants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    specialty: Mapped[str] = mapped_column(String(8), nullable=False, default="saju")
    # 요청 로케일(ko|vi) — 세션 생성 시 get_locale 로 확정. 요약 상담서 언어·모델 선택 근거.
    # 기존 행은 server_default 'ko'(한국 서비스 불변). DB 컬럼은 0015_locale 마이그레이션이 보강.
    locale: Mapped[str] = mapped_column(String(2), nullable=False, default="ko", server_default="ko")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="requested", index=True
    )
    price_p: Mapped[int] = mapped_column(Integer, nullable=False, default=0)       # 차감(예정) 포인트
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 구매 블록(분)
    extended_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 연장 누계(분)
    # 개인정보 처리 동의(입장 전 필수) — 시각 기록. transcript 7일 파기 고지·동의.
    consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    elapsed_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 과금/환불 (Phase 3) — 선차감 후 실패/노쇼 시 멱등 환불
    credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refund_p: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    refunded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # 종료 후 요약 PDF 토큰(pdf_service). transcript 파기 시 함께 삭제.
    pdf_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 사용자 만족도 평점(종료 후, 1~5). NULL=미평가. 간판의 만족도 집계에 사용.
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # transcript/PDF 파기 예정 시각(ended_at + retention). 파기 배치가 이 시각 지난 세션 정리(하드삭제).
    purge_after: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    purged: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    messages: Mapped[list["ConsultationMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ConsultationMessage.id",
    )


class ConsultationMessage(Base):
    """상담 대화 메시지 — 서버 릴레이 시 영속화(요약 PDF·감사용). 7일 후 완전 파기."""

    __tablename__ = "consultation_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("consultation_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender: Mapped[str] = mapped_column(String(12), nullable=False)  # user | consultant | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    session: Mapped[ConsultationSession] = relationship(back_populates="messages")


class ConsultationSettlement(Base):
    """세션별 정산 원장 — 수수료·세금 산출·표시(실지급은 수동/오프라인). MVP=집계/표시.

    payout = revenue×(1−commission_pct/100)×(1−tax_pct/100). 예: 50,000P → 수수료20%=10,000,
    상담사몫 40,000, 원천징수3.3%=1,320 → 실지급 38,680.
    """

    __tablename__ = "consultation_settlements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("consultation_sessions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    consultant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("consultants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    revenue_p: Mapped[int] = mapped_column(Integer, nullable=False, default=0)     # 매출(차감 포인트)
    commission_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    commission_p: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 플랫폼 수수료
    taxable_p: Mapped[int] = mapped_column(Integer, nullable=False, default=0)     # 상담사 몫(과세대상)
    tax_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    tax_p: Mapped[int] = mapped_column(Integer, nullable=False, default=0)         # 원천징수
    payout_p: Mapped[int] = mapped_column(Integer, nullable=False, default=0)      # 실지급
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="pending", index=True
    )  # pending | settled
    settled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
