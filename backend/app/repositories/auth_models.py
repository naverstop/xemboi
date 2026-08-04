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
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.enc_types import EncryptedDate, EncryptedFloat, EncryptedString

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
    # 국외이전 별도 동의(개인정보보호법 제28조의8) — 외부 AI(미국 등) 심화 보강에 질문·사주맥락 전송 동의.
    # 기본 False(미동의) → 미동의 회원은 외부 전송(심화·폴백) 미적용(H4).
    overseas_transfer_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 민감정보 처리 별도 동의(제23조) — 상담/채팅에 건강·신념 등 민감정보가 포함될 수 있음에 대한 동의(선택).
    sensitive_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # ---- P3/P4 신규 ----
    # 회원등급(계획 5.x): 0 시스템관리자 ~ 5 비로그인. NULL이면 role 기반 폴백.
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 무료 질문 누적 사용 횟수(계획 4.2 H)
    free_used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # free_quota_reset='monthly' 일 때 free_used_count 가 속한 기간('YYYY-MM'). 월이 바뀌면 원자적 0 리셋.
    free_quota_period: Mapped[str | None] = mapped_column(String(7), nullable=True)
    # 답변 말투/방언(계획 P): standard | gyeongsang | jeolla | gangwon | jeju
    answer_dialect: Mapped[str] = mapped_column(String(16), nullable=False, default="standard")
    # 유료/멤버십 캐시(계획 5.2)
    membership_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    first_paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 연간회원 무과금 사용 누적 횟수(계획 5.1). 한도 settings.membership_annual_quota, 갱신 시 0으로 리셋.
    membership_used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 답변 공유 사용 횟수 — '이번 주기' 사용분. 한도는 share_service.limit(비패스 5 / 패스 20).
    # ⚠️ 2026-07-23 이전엔 리셋이 없어 사실상 평생 누적이었다(화면은 "월 20회"라고 안내). 아래
    #    share_period_start 앵커 + share_service.roll_period 지연 평가로 30일마다 0으로 돌아간다.
    share_used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 공유 주기 앵커(UTC naive). NULL=아직 미설정 → 첫 접근 시 현재시각으로 심는다.
    share_period_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 약관 동의 (가입 시 필수)
    terms_agreed_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    privacy_agreed_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    refund_agreed_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    terms_agreed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 생년월일 암호화 본문 (AES-256-GCM nonce|ct base64). birth_date 평문은 호환을 위해 유지하다 추후 마이그레이션.
    birth_date_enc: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 본인 사주 기본 프로필(JSON): 재방문 시 자동 채움. {birth_date,birth_time,calendar,gender,is_leap_month,...}
    # 생년월일 등 개인정보 포함 → 컬럼 투명 암호화(M2/②). 저장은 암호문, 앱은 평문 JSON 문자열로 취급.
    saju_profile: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)
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
    # 멱등키(선택) — 지정 시 같은 키의 거래는 1회만 반영. ref_id 는 세션단위로 재사용되므로(세션당 다건)
    #   멱등 대상이 될 수 없어 별도 컬럼을 둔다. 리컨실 재실행·재시도가 이중차감/이중환불로 번지지 않게
    #   부분 UNIQUE 인덱스(idem_key IS NOT NULL)로 DB 레벨 dedup. adjust_credit(idem_key=…)이 SAVEPOINT 게이트로 사용.
    idem_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index(
            "ux_credit_tx_idem", "idem_key", unique=True,
            postgresql_where=text("idem_key IS NOT NULL"),
            sqlite_where=text("idem_key IS NOT NULL"),
        ),
    )


class AnswerReceipt(Base):
    """유료 추가질문의 '선차감 → 완결(EOF)' 영수증 — 크래시 orphan(차감 O·답변 X) 결정적 탐지·복구 앵커.

    precharge_followup 이 차감과 '같은 트랜잭션'으로 pending 생성 → 각 메뉴 'done'(EOF) 에서 complete,
    오류/환불(refund_followup) 경로에서 refunded 로 전이. pending 으로 N분 넘게 남은 영수증 =
    '차감됐으나 완결 못 함(크래시)' orphan → 스케줄러가 멱등 환불(adjust_credit idem_key). 현재는 실현금
    (charged>0) 추가질문만 대상(무료슬롯 orphan 은 비현금·저심각 → 후속). 상세 [[stream-billing-freeride]] 6차.
    """
    __tablename__ = "answer_receipts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    menu: Mapped[str] = mapped_column(String(24), nullable=False)   # question|tool_q|compatibility_q|tarot_q|dream
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)   # 세션 id(dream 은 생성 후 finalize 시 주입)
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 선차감 크레딧(현금, 양수). 무료슬롯=0
    # 선점 종류 — 리컨실이 복구 방식을 정한다: cash=포인트 환불, 그 외=슬롯 카운터 복원.
    slot_kind: Mapped[str] = mapped_column(String(12), nullable=False, default="cash", server_default="cash")
    # pass 슬롯 복원용 월패스 id(slot_kind='pass' 일 때만).
    pass_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")  # pending|complete|refunded
    message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_answer_receipts_sweep", "status", "created_at"),
    )


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


class UserPass(Base):
    """B-7 월 패스 — 포인트 자동차감형(빌링키·PG 구독계약 불필요).

    회원당 1행(재구독 시 재활성). 갱신은 '지연 평가'(lazy) — 조회 시점에 next_renewal_at 경과면
    차감 시도, 잔액 부족이면 비활성+충전 유도 푸시. 별도 스케줄러 없이 재기동에도 안전.
    """

    __tablename__ = "user_passes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    tier: Mapped[str] = mapped_column(String(8), nullable=False)  # lite | plus
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    auto_renew: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    current_start: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    next_renewal_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    price_p: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # 최근 차감액(표기용)
    # 이번 주기 사용량(플러스 혜택) — 갱신 시 리셋
    free_basic_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    amulet_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Review(Base):
    """B-3 이용 후기 — 답변 👍 직후 수집한 한 줄 후기. 관리자 승인 후에만 공개 노출.

    display_name 은 작성 시점에 서버가 마스킹해 스냅샷(탈퇴/개명에도 표기 유지, 원본 미노출).
    리워드는 승인 시점 1회 지급(파밍 방지) — reward_granted 로 멱등.
    """

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(
        String(16), nullable=False, default="chat", server_default="chat", index=True
    )  # chat | compat | tarot | tool | sinnyeon | consultation
    content: Mapped[str] = mapped_column(Text, nullable=False)   # 한 줄 후기(최대 200자, API 검증)
    rating: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")  # 별점 1~5
    display_name: Mapped[str] = mapped_column(String(32), nullable=False, default="익명", server_default="익명")
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="pending", server_default="pending", index=True
    )  # pending | approved | rejected
    reward_granted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
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
    # 생년월일·출생시각은 개인정보 → 컬럼 투명 암호화(M2/②). 저장은 암호문(Text), 앱은 date/str 로 취급.
    birth_date: Mapped[date_t] = mapped_column(EncryptedDate, nullable=False)
    birth_time: Mapped[str | None] = mapped_column(EncryptedString, nullable=True)  # HH:MM
    calendar: Mapped[str] = mapped_column(String(8), nullable=False, default="solar")
    is_leap_month: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gender: Mapped[str] = mapped_column(String(8), nullable=False, default="male")
    apply_true_solar_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 진태양시 정밀화 — 출생지 경도(시·군·구) + 균시차 + 자시 관법 영구저장(자동채움용)
    # 출생지 경도는 위치 유추 민감정보 → 투명 암호화(M2/②).
    birth_longitude: Mapped[float | None] = mapped_column(EncryptedFloat, nullable=True)
    apply_equation_of_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    night_zi_mode: Mapped[str | None] = mapped_column(String(8), nullable=True)  # yaja/jeongja
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
