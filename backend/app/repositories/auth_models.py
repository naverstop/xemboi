"""회원/크레딧/결제/배너 ORM.

기존 `models.Base` 메타데이터에 등록되어 `create_all` 시 자동 생성됨.
"""
from __future__ import annotations

from datetime import date as date_t, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.repositories.models import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)  # OAuth-only면 NULL
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="user")  # user | admin
    nickname: Mapped[str | None] = mapped_column(String(64), nullable=True)
    oauth_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)  # kakao | google
    oauth_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    birth_date: Mapped[date_t | None] = mapped_column(Date, nullable=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    daily_free_used_at: Mapped[date_t | None] = mapped_column(Date, nullable=True)
    ads_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # ---- P3/P4 신규 ----
    # 회원등급(계획 5.x): 0 시스템관리자 ~ 5 비로그인. NULL이면 role 기반 폴백.
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 무료 질문 누적 사용 횟수(계획 4.2 H)
    free_used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 답변 말투/방언(계획 P): standard | gyeongsang | jeolla | gangwon | jeju
    answer_dialect: Mapped[str] = mapped_column(String(16), nullable=False, default="standard")
    # 로케일(ko|vi) — 언어·역법·독음 축. 기존 회원은 'ko'. answer_dialect(방언)는 ko 전용.
    locale: Mapped[str] = mapped_column(String(2), nullable=False, default="ko", server_default="ko")
    # 유료/멤버십 캐시(계획 5.2)
    membership_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 연간회원 무과금 사용 누적 횟수(계획 5.1). 한도 settings.membership_annual_quota, 갱신 시 0으로 리셋.
    membership_used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 답변 공유 누적 사용 횟수(계획 7.2 K) — 한도는 settings.share_quota_default
    share_used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 약관 동의 (가입 시 필수)
    terms_agreed_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    privacy_agreed_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    refund_agreed_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    terms_agreed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 생년월일 암호화 본문 (AES-256-GCM nonce|ct base64). birth_date 평문은 호환을 위해 유지하다 추후 마이그레이션.
    birth_date_enc: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 본인 사주 기본 프로필(JSON): 재방문 시 자동 채움. {birth_date,birth_time,calendar,gender,is_leap_month,...}
    saju_profile: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 면책고지 동의(최초 1회, 법적효력). 동의 시각·버전 기록.
    disclaimer_agreed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    disclaimer_agreed_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    credit: Mapped["Credit"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Credit(Base):
    __tablename__ = "credits"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="credit")


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)  # +충전 / -차감
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    # reason: signup_bonus | admin_seed | purchase | question | preview_reveal | refund | admin_grant
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    toss_payment_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # 원
    credit_granted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # status: pending | approved | failed | cancelled | refunded
    # MutableDict: in-place 변경(confirm/refund/webhook 페이로드 갱신)을 SQLAlchemy가 감지해
    # commit 시 영속화하도록 한다(순수 JSON 컬럼이면 같은 dict 재할당이 변경으로 인식 안 돼 유실됨).
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSON), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("order_id", name="uq_payments_order_id"),)


class Banner(Base):
    __tablename__ = "banners"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slot: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # slot: top | chat_top_1 | chat_top_2 | side_1 | side_2 | answer_bottom
    image_url: Mapped[str] = mapped_column(String(512), nullable=False)
    link_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class AccessLog(Base):
    __tablename__ = "access_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    path: Mapped[str] = mapped_column(String(255), nullable=False)
    method: Mapped[str] = mapped_column(String(8), nullable=False, default="GET")
    status: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False, index=True
    )


class PushSubscription(Base):
    """Web Push 구독 정보 (PWA 푸시, 계획 2.7.6)."""

    __tablename__ = "push_subscriptions"
    __table_args__ = (UniqueConstraint("endpoint", name="uq_push_endpoint"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(255), nullable=False)
    auth: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AppSetting(Base):
    """관리자 편집형 key-value 설정(계획 4.2/4.3). 운영 중 변경 즉시 반영."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class AnswerTemplate(Base):
    """답변 표준양식/로직(계획 L). 활성 버전의 body가 SYSTEM_PROMPT로 주입됨."""

    __tablename__ = "answer_templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)  # 시스템 프롬프트 본문
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class MessageFeedback(Base):
    """답변 피드백 👍👎 (계획 7-D).

    message_id 는 chat_messages / tool_messages / compat_messages 각각의 id 인데
    세 테이블이 별도 시퀀스라 값이 겹친다. 어느 메뉴의 메시지인지 source 로 구분하고
    유니크 제약도 (message_id, source, user_id) 로 둬 메뉴 간 피드백 충돌을 막는다.
    """

    __tablename__ = "message_feedback"
    __table_args__ = (
        UniqueConstraint("message_id", "source", "user_id", name="uq_feedback_msg_src_user"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="chat", server_default="chat", index=True
    )  # chat | tool | compat
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # +1=👍 / -1=👎
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 피드백 리워드(답변당 1회 적립한 포인트). 0=미적립. 중복적립 방지·투명성.
    reward_granted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # 피드백 학습 폐루프 처리 완료 여부(👍=검증지식 색인 / 👎=개선큐 적재). 중복 학습 방지.
    learned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SupportTicket(Base):
    """고객센터(CONTACT US) 문의 — 결제·환불 등 요청 게시판.

    접수 시 활성 SupportRecipient 들에게 메일 알림이 발송되고, 관리자 화면에서
    상태(received→in_progress→resolved/rejected)와 처리 메모를 관리한다.
    """

    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 작성 회원(비로그인 문의 허용 → nullable). 회원 탈퇴 시 문의는 보존하되 연결 해제.
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(16), nullable=False, default="refund")
    # category: refund(환불) | payment(결제오류) | account(계정) | etc(기타)
    contact_email: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)   # 결제 주문번호(환불 대상)
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)        # 결제(환불) 금액(원)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="received", index=True)
    # status: received(접수) | in_progress(처리중) | resolved(완료) | rejected(반려)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class SupportRecipient(Base):
    """고객센터 문의 접수 알림을 받을 관리자 메일 — 관리자 화면에서 CRUD."""

    __tablename__ = "support_recipients"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class SajuProfile(Base):
    """다중 사주 프로필(계획 7-D.2) — 본인 외 가족·지인 사주 저장."""

    __tablename__ = "saju_profiles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(64), nullable=False)  # 예: 본인/배우자/자녀
    birth_date: Mapped[date_t] = mapped_column(Date, nullable=False)
    birth_time: Mapped[str | None] = mapped_column(String(8), nullable=True)  # HH:MM
    calendar: Mapped[str] = mapped_column(String(8), nullable=False, default="solar")
    is_leap_month: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gender: Mapped[str] = mapped_column(String(8), nullable=False, default="male")
    apply_true_solar_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 진태양시 정밀화 — 출생지 경도(시·군·구) + 균시차 + 자시 관법 영구저장(자동채움용)
    birth_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    apply_equation_of_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    night_zi_mode: Mapped[str | None] = mapped_column(String(8), nullable=True)  # yaja/jeongja
    # 로케일(ko|vi) — 이 프로필의 역법/독음(vi=베트남 음력·한월음)
    locale: Mapped[str] = mapped_column(String(2), nullable=False, default="ko", server_default="ko")
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
