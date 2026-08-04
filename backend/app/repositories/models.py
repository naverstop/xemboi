"""ORM 모델 — 채팅 세션/메시지 영속화."""
from __future__ import annotations

from datetime import date as date_t, datetime, time as time_t
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
    Time,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    # 소유 회원 (익명 세션 허용 → nullable)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # 생년월일 (필수)
    birth_date: Mapped[date_t] = mapped_column(Date, nullable=False)
    birth_time: Mapped[time_t | None] = mapped_column(Time, nullable=True)
    calendar: Mapped[str] = mapped_column(String(16), nullable=False, default="solar")
    is_leap_month: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gender: Mapped[str] = mapped_column(String(8), nullable=False, default="male")
    apply_true_solar_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 산출된 사주 명식
    saju_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    chart_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.id",
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    sources_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    # 미리보기/차감
    preview_revealed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_preview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reveal_credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 전체보기(reveal) 시 차감할 이연 금액(회원=질문단가). 0이면 폴백(preview_reveal_cost).
    reveal_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    session: Mapped[ChatSession] = relationship(back_populates="messages")


class SajuVideoJob(Base):
    """사주 답변 → 1분 쇼츠 영상 생성 작업(부록 C-3).

    chat(사주) 메뉴 전용. chat_messages.content(전체답변) + chat_sessions.chart_json(명식)을
    재활용해 1인칭 스토리 영상을 생성한다. 클릭 즉시 video_gen_cost 차감, 실패 시 멱등 환불.
    """
    __tablename__ = "saju_video_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 외부 노출 식별자(IDOR 표면 축소) — uuid4().hex
    job_token: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    # FK: chat 세션/메시지 (ChatMessage.id 는 Integer 이므로 message_id 도 Integer)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("chat_sessions.session_id", ondelete="CASCADE"), nullable=False, index=True
    )
    message_id: Mapped[int] = mapped_column(Integer, nullable=False)  # 논리참조(피드백 관례)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    # queued | running | done | failed | expired
    stage: Mapped[str | None] = mapped_column(String(24), nullable=True)
    # scenario | tts | compose | encode | finalize
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    aspect: Mapped[str] = mapped_column(String(8), nullable=False, default="9x16")

    scenario_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    master_path: Mapped[str | None] = mapped_column(Text, nullable=True)    # 상대경로(이관 대비)
    delivery_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    encoder_used: Mapped[str | None] = mapped_column(String(16), nullable=True)  # libx264 | hevc_nvenc
    gpu_gate_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 실패 자동환불 멱등 가드(이중환불=무결제 크레딧 발행 차단)
    refunded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class RetrievalLog(Base):
    """RAG 검색 점수 로그 — 일일 질문 인사이트 배치의 갭(미커버 주제) 분석용.

    max_score가 낮은 질문 = 코퍼스에 근거 자료가 부족한 주제.
    """

    __tablename__ = "retrieval_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # [P3-D1] 메뉴 태그('chat'·'compat'·'naming/jakmyeong'·'dream'…). 세션이 지워지면 4개 테이블을
    # 조인해도 메뉴를 알 수 없어 추적이 끊긴다(전기간 orphan 39%) → 로그 자체에 남긴다.
    menu: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    results_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)


class CompatibilitySession(Base):
    """궁합(宮合) 세션 — 두 사람의 사주 + 산출 결과. 상담 쿼터 공유."""

    __tablename__ = "compat_sessions"

    compat_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    # 사람 A (본인 등)
    a_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    a_birth_date: Mapped[date_t] = mapped_column(Date, nullable=False)
    a_birth_time: Mapped[time_t | None] = mapped_column(Time, nullable=True)
    a_calendar: Mapped[str] = mapped_column(String(16), nullable=False, default="solar")
    a_is_leap_month: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    a_gender: Mapped[str] = mapped_column(String(8), nullable=False, default="male")
    a_apply_true_solar_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    a_chart_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # 사람 B (상대)
    b_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    b_birth_date: Mapped[date_t] = mapped_column(Date, nullable=False)
    b_birth_time: Mapped[time_t | None] = mapped_column(Time, nullable=True)
    b_calendar: Mapped[str] = mapped_column(String(16), nullable=False, default="solar")
    b_is_leap_month: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    b_gender: Mapped[str] = mapped_column(String(8), nullable=False, default="male")
    b_apply_true_solar_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    b_chart_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # 산출 결과 (CompatResult 전체)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # 요소별 근거점수 — 평균 집계용(펜타곤 '전체 평균' 오버레이). 관법 중립 0~100.
    f_day_branch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    f_day_stem: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    f_wuxing: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    f_ten_god: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    f_sinsal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 관법별 종합점수(집계용)
    total_a: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_b: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_c: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 빌링(상담 쿼터 공유)
    is_preview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    messages: Mapped[list["CompatibilityMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="CompatibilityMessage.id",
    )


class CompatibilityMessage(Base):
    """궁합 해설/추가질문 메시지 (chat_messages와 동일 구조)."""

    __tablename__ = "compat_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    compat_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("compat_sessions.compat_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    sources_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    preview_revealed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_preview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reveal_credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    session: Mapped[CompatibilitySession] = relationship(back_populates="messages")


class ToolSession(Base):
    """명리 도구 세션 — 작명/개명/아호/택일 공용. 상담 쿼터 공유."""

    __tablename__ = "tool_sessions"

    tool_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tool: Mapped[str] = mapped_column(String(16), nullable=False, index=True)   # naming | taekil
    kind: Mapped[str] = mapped_column(String(24), nullable=False)               # jakmyeong|gaemyeong|aho|wedding|moving|...
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    birth_date: Mapped[date_t] = mapped_column(Date, nullable=False)
    birth_time: Mapped[time_t | None] = mapped_column(Time, nullable=True)
    calendar: Mapped[str] = mapped_column(String(16), nullable=False, default="solar")
    is_leap_month: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    gender: Mapped[str] = mapped_column(String(8), nullable=False, default="male")
    apply_true_solar_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    chart_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    input_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)   # 성/현재이름/용도/기간 등
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    is_preview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    messages: Mapped[list["ToolMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ToolMessage.id",
    )


class ToolMessage(Base):
    """도구 해설/추가질문 메시지."""

    __tablename__ = "tool_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tool_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tool_sessions.tool_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    is_preview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preview_revealed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reveal_credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    session: Mapped[ToolSession] = relationship(back_populates="messages")


class TarotSession(Base):
    """타로 세션 — 섹션/질문 + 서버 확정 드로우(셔플 순서·역방향, 비공개). 궁합과 동일 패턴.

    deck_order_json/reversed_json 은 생성 시 CSPRNG 로 확정된 비공개 값(응답 미노출).
    picks_json/cards_json 은 픽 제출 시 1회 확정(멱등) — 재조회 시 동일 카드 보장.
    """

    __tablename__ = "tarot_sessions"

    tarot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    section: Mapped[str] = mapped_column(String(16), nullable=False)     # love|money|career|study|choice|life
    question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    spread_type: Mapped[str] = mapped_column(String(16), nullable=False)  # horseshoe7 | celtic11

    # 서버 확정 드로우(비공개): 78장 셔플 순서(카드 id) / 카드별 역방향(50%)
    deck_order_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    reversed_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    # 픽 제출(1회 확정): 사용자가 고른 인덱스(0~77) / 확정 카드 배열(응답 페이로드 그대로)
    picks_json: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    cards_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    # 빌링(입장료 — compat 동일)
    is_preview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    messages: Mapped[list["TarotMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="TarotMessage.id",
    )


class TarotMessage(Base):
    """타로 해석/추가질문 메시지 (compat_messages 와 동일 구조)."""

    __tablename__ = "tarot_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tarot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tarot_sessions.tarot_id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    sources_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    preview_revealed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_preview: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reveal_credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    session: Mapped[TarotSession] = relationship(back_populates="messages")


class TarotCardOverride(Base):
    """타로 카드 해석/키워드 관리자 편집 오버레이 — 정적 덱(JSON) 위에 얹는 라이브 수정본.

    code(예: major-00, cups-01) 단위로 편집분만 저장. row 가 없으면 tarot_deck_kr.json 시드
    그대로 사용. 카드명·방향·이미지 등 구조 필드는 JSON 이 단일 소스(편집 불가).
    저장 즉시 tarot_deck 캐시에 반영되어 재시작 없이 라이브 적용된다.
    """

    __tablename__ = "tarot_card_overrides"

    code: Mapped[str] = mapped_column(String(24), primary_key=True)
    keywords_up: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    keywords_rev: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    interp_up: Mapped[str | None] = mapped_column(Text, nullable=True)
    interp_rev: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)  # 편집 관리자 id(감리 이력)
