"""1:1 인적 상담(입점업체 상담사 ↔ 사용자 실시간 채팅) ORM.

입점업체(상담사)·상담 세션·메시지·정산 원장. 기존 `models.Base` 메타데이터에 등록되어
`create_all` 로 생성되고 Alembic(20260704_0013)으로도 멱등 관리된다.

설계·의사결정: [[consultation-1on1-plan]]. Phase 1 은 스키마 + 관리자 등록 + 리스트까지.
실시간 WebSocket(presence/타이머)·과금·요약 PDF·정산은 Phase 2~4 에서 채운다.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
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

    # sqlite(테스트) autoincrement 호환 — PG는 기존 BIGSERIAL 그대로
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
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
    # #키워드(전문영역) — JSON 배열 문자열(예: ["연애","취업","재물"]). 정규화는 consultation_service.
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 요일별 상시 영업시간표(KST) — JSON: {"0":{"open":"10:00","close":"19:00"}, ... "6":null}(0=월~6=일, null=휴무).
    # 안내 표시 + 예약 슬롯 가능 범위 제한용. 즉시 '상담가능'은 실제 토글/접속(presence)이 결정(무관).
    business_hours: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 개별 단가/시간/수수료 — NULL 이면 전역 기본값(settings_service) 폴백
    rate_p: Mapped[int | None] = mapped_column(Integer, nullable=True)          # 회당 포인트(P)
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)    # 상담 시간(분·블록)
    commission_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 플랫폼 수수료(%)
    # 요금 단위(상담사 자율) — session(회당 rate_p) | minute(분당 per_min_p) | hour(시간당 per_hour_p).
    # 실제 차감은 블록제 유지: 1회(=duration_min분) 블록가로 환산(effective). 표시만 분/시간 단위.
    price_unit: Mapped[str] = mapped_column(
        String(8), nullable=False, default="session", server_default="session"
    )
    per_min_p: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 분당 P(price_unit='minute')
    per_hour_p: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 시간당 P(price_unit='hour')
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 노출 상태(관리·상담사) — active(정상) | coming_soon(입점예정·오버레이·신청불가) | hidden(숨김).
    # is_active(마스터 스위치)·presence(런타임 온라인)와 별개인 편집 상태.
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="active", server_default="active"
    )
    # 상담사 셀프 편집 허용 여부(관리자가 잠글 수 있음). False 면 셀프 설정 화면이 읽기전용.
    self_managed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
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
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="requested", index=True
    )
    price_p: Mapped[int] = mapped_column(Integer, nullable=False, default=0)       # 차감(예정) 포인트
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 구매 블록(분)
    extended_min: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 연장 누계(분)
    # 정산 수수료 스냅샷(요청 시 고정) — 진행 중 관리자 수수료 변경이 in-flight 세션 정산에 영향 없도록.
    # NULL(구버전 세션)이면 정산 시 effective()로 폴백.
    commission_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # A-1 상담 컨텍스트 자동 전달 — 접수 시 서버가 소스(사주 채팅 세션/타로 세션)에서 스냅샷을 떠서 저장.
    # 상담사가 채팅방에서 명식표/카드 스프레드를 바로 봄(중복 질문 제거). PII 포함 → 7일 파기 시 함께 마스킹.
    source_kind: Mapped[str | None] = mapped_column(String(8), nullable=True)   # saju | tarot
    source_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)    # {chart,...} | {cards,...}
    # A-2 예약 상담 — 예약 슬롯에서 전환된 세션이면 슬롯 id. 예약은 선결제(홀드)라 수락 시 재차감 금지,
    # 미수락/거절/노쇼 시 전액 환불. 미수락 유예도 즉시 상담(120초)과 달리 consultation_reserve_grace_min 적용.
    reservation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
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


class ConsultationSlot(Base):
    """A-2 예약 상담 슬롯 — 상담사가 등록한 예약 가능 시간.

    수명주기: open(등록) → booked(사용자 예약·선결제 홀드) → converted(시각 도래, 세션 자동 생성)
              / cancelled(상담사 삭제·사용자 취소 — 정책 환불) / done(정리용)
    선결제(charged_p)는 취소 정책에 따라 환불: 시작 N시간 전 100%, 이후 M%(관리자 설정),
    상담사 측 취소·노쇼는 항상 100%.
    """

    __tablename__ = "consultation_slots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # uuid4().hex
    consultant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("consultants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)  # UTC
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # ── 예약(booked) 시 채워짐 ──
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    booked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    price_p: Mapped[int] = mapped_column(Integer, nullable=False, default=0)        # 예약 시점 단가 스냅샷
    commission_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)      # 예약 시점 수수료 스냅샷
    charged_p: Mapped[int] = mapped_column(Integer, nullable=False, default=0)      # 선결제(홀드) 금액
    refunded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    refund_p: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    # ── 전환(converted) 시 채워짐 ──
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


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


class ConsultantApplication(Base):
    """입점 신청서(운영자 지시 2026-07-11) — 신청·심사 이력 + 클릭랩 동의 증빙 스냅샷.

    법적 증빙을 위해 동의한 약관 '전문'을 통째로 스냅샷 보관한다(버전·해시·시각·IP 포함).
    승인 시 consultants 행이 생성되고(login_email 매핑 → 가입 계정 자동 연결), 본 행은
    승인 후에도 계약 증빙으로 영구 보존한다(탈퇴 시에도 정산·분쟁 대응 위해 유지 — 약관 고지).
    """

    __tablename__ = "consultant_applications"

    # sqlite(테스트)는 INTEGER PK만 autoincrement — PG는 BIGSERIAL(마이그레이션) 그대로
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    # 신청자 — 메일 ID가 권한 키(운영자 지시). 로그인 필수라 둘 다 채워짐.
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    # 신청 내용
    specialty: Mapped[str] = mapped_column(String(8), nullable=False, default="saju")  # saju|tarot|both
    business_name: Mapped[str] = mapped_column(String(120), nullable=False)
    contact: Mapped[str | None] = mapped_column(String(64), nullable=True)   # 연락처(선택)
    intro: Mapped[str | None] = mapped_column(Text, nullable=True)           # 자기소개/경력
    # 클릭랩 동의 증빙(전자문서법 §4 + 약관규제법 §3 명시·설명의무 충족 설계)
    terms_version: Mapped[str] = mapped_column(String(16), nullable=False)
    terms_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    terms_text: Mapped[str] = mapped_column(Text, nullable=False)            # 동의 시점 약관 전문 스냅샷
    agreed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    agreed_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 첨부 서류(사업자등록증·입점 증빙) — [{id, kind, name, path, size}] JSON. 파일명은 uuid(경로순회 방지).
    docs_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 심사 상태
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending", index=True)  # pending|approved|rejected
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    consultant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # 승인 시 생성된 입점 행
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class PartnerInquiry(Base):
    """입점 문의(운영자 확정 2026-07-12) — 신청서 작성 전 게이트.

    프로세스: 푸터 '입점 문의' → (회원가입) → 메일 ID로 문의 접수 → 관리자가 확인 후
    [신청 허용] → 그때부터 입점 신청서(서류·약관) 작성 가능. 일반 회원의 무단 신청 차단.
    """

    __tablename__ = "partner_inquiries"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)   # 권한 키 = 메일 ID
    note: Mapped[str | None] = mapped_column(Text, nullable=True)                 # 남긴 말(선택)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending", index=True)  # pending|allowed|dismissed
    decide_note: Mapped[str | None] = mapped_column(String(300), nullable=True)   # 기각 사유 등(선택)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
