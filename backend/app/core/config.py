"""앱 설정 — .env에서 읽음."""
from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 일반
    app_name: str = "Saju Agent API"
    app_env: str = "dev"
    # 인스턴스 기본 로케일. ko=한국(사주1, saju.songstock.art) / vi=베트남(xemboi.io).
    # VN 배포는 DEFAULT_LOCALE=vi 로 설정. per-request locale 미지정 시 폴백이며,
    # DB/컬렉션 '물리적 완전분리' 가드(main.py)의 기준이 된다(vi 인스턴스는 saju_db 접근 금지).
    default_locale: str = Field(
        default="ko",
        validation_alias=AliasChoices("default_locale", "DEFAULT_LOCALE", "SAJU_LOCALE"),
    )
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"])
    # 클라이언트 IP 산정 시 신뢰할 역방향 프록시 홉 수. 0(기본)=X-Forwarded-For 무시하고 TCP peer
    # IP 사용(헤더 스푸핑으로 레이트리밋 우회 차단). 프록시(Caddy/nginx/CF) 뒤라면 그 개수만큼
    # 설정 → XFF 오른쪽에서 N번째(프록시가 덧붙인, 스푸핑 불가) 엔트리를 실제 클라이언트로 사용.
    trusted_proxy_count: int = 0

    # DB
    database_url: str = "postgresql+psycopg://saju:saju_dev_2026@127.0.0.1:5432/saju_db"

    # Redis (선택). 단일 서버에선 미사용(in-memory)으로 충분 → 기본 OFF.
    # redis_enabled=False 면 rate-limit/리프레시토큰이 in-memory 로 동작하며
    # 죽은 Redis 에 접속 시도하지 않아 지연이 없다.
    # 다중 인스턴스로 확장 + Redis 가동 시 REDIS_ENABLED=true 로 켜세요.
    redis_enabled: bool = False
    redis_url: str = "redis://127.0.0.1:6379/0"

    # Qdrant
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "saju_corpus"

    # 임베딩
    embed_model: str = "BAAI/bge-m3"

    # Ollama
    ollama_url: str = Field(
        default="http://127.0.0.1:11434",
        validation_alias=AliasChoices("ollama_url", "OLLAMA_URL", "OLLAMA_BASE_URL"),
    )
    ollama_model: str = "exaone3.5:7.8b"
    # 심화(deep) 2차 보강용 로컬 엔진(듀얼 LLM 로컬화). exaone 초안 → qwen 보강.
    ollama_refine_model: str = Field(
        default="qwen2.5:7b-instruct-q4_K_M",
        validation_alias=AliasChoices("ollama_refine_model", "OLLAMA_REFINE_MODEL"),
    )
    # ── 베트남 로케일(vi) 로컬 모델 — Qwen3(다국어). 공용 Ollama(GPU1)에 이미 로드된 qwen3:14b 재사용.
    #   ko=exaone 초안→qwen2.5 보강, vi=qwen3 단일(초안=보강). locale 별로 _call_ollama 가 선택.
    #   EXAONE(한국어 특화)은 vi 에 부적합 → vi 는 초안·보강 모두 Qwen3.
    ollama_model_vi: str = Field(
        default="qwen3:14b",
        validation_alias=AliasChoices("ollama_model_vi", "OLLAMA_MODEL_VI"),
    )
    ollama_refine_model_vi: str = Field(
        default="qwen3:14b",
        validation_alias=AliasChoices("ollama_refine_model_vi", "OLLAMA_REFINE_MODEL_VI"),
    )
    # 심화 모드에서 로컬 qwen 2차 보강 사용 여부(끄면 exaone 단독). Claude는 로컬 실패 시 폴백.
    deep_local_refine_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("deep_local_refine_enabled", "DEEP_LOCAL_REFINE_ENABLED"),
    )
    ollama_temperature: float = 0.4
    # 컨텍스트 길이. 16GB GPU + flash attn/KV q8 전제로 8192(기본 4096은 시스템규칙+명식+RAG6청크
    # +히스토리 초과 시 잘려 명식 환각 유발). VRAM 여유에 따라 16384까지. 8GB 시절엔 OOM이라 미설정이었음.
    ollama_num_ctx: int = Field(
        default=16384,  # 종합 풀이(성격·육친·건강 + 올해/월별 발생할 일 6개월) 길이 여유(16GB·KV q8)
        validation_alias=AliasChoices("ollama_num_ctx", "OLLAMA_NUM_CTX"),
    )
    # 최대 생성 토큰. 미설정 시 모델/엔진 기본값에 의존해 종합 풀이(성격·육친·건강 + 올해/월별 발생할 일
    # 6개월)가 길어질 때 대비. 명시적으로 넉넉히 잡아 잘림 차단. (num_ctx 안에서만 유효)
    ollama_num_predict: int = Field(
        default=3072,
        validation_alias=AliasChoices("ollama_num_predict", "OLLAMA_NUM_PREDICT"),
    )
    ollama_timeout_sec: float = 180.0
    # 모델 상시 예열 (콜드로드 방지). -1=영구 상주, "30m" 등도 가능
    ollama_keep_alive: str = Field(
        default="-1",
        validation_alias=AliasChoices("ollama_keep_alive", "OLLAMA_KEEP_ALIVE"),
    )

    # SSE / 미리보기 스트리밍 (524 대책)
    sse_heartbeat_sec: float = 12.0   # 무음 구간 방지용 : ping 주기
    preview_max_chars: int = 660       # 미리보기 실시간 컷 기준(절대 문자수). 220→660(약 3배, 무료도 성의있게)

    # Web Push (PWA, VAPID)
    vapid_public_key: str = Field(
        default="",
        validation_alias=AliasChoices("vapid_public_key", "VAPID_PUBLIC_KEY"),
    )
    vapid_private_key: str = Field(
        default="",
        validation_alias=AliasChoices("vapid_private_key", "VAPID_PRIVATE_KEY"),
    )
    vapid_subject: str = Field(
        default="mailto:admin@example.com",
        validation_alias=AliasChoices("vapid_subject", "VAPID_SUBJECT"),
    )

    # 외부 LLM (듀얼 LLM 2차 보강, 계획 F)
    external_llm_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("external_llm_enabled", "EXTERNAL_LLM_ENABLED"),
    )
    # 프로바이더 선택: "claude"(기본) | "gemini"(레거시) | "off"
    external_llm_provider: str = Field(
        default="claude",
        validation_alias=AliasChoices("external_llm_provider", "EXTERNAL_LLM_PROVIDER"),
    )

    # --- Claude (Anthropic) ---
    anthropic_api_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "anthropic_api_key", "ANTHROPIC_API_KEY", "claude_api_key", "CLAUDE_API_KEY"
        ),
    )
    # 모델은 버전 고정 대신 '항상 최신'을 지향.
    #  - "auto"          : models.list로 최신 Opus를 동적 조회(실패 시 claude-opus-4-8 폴백)
    #  - "claude-opus-4-8": 고정 핀(비용 절감하려면 "claude-sonnet-4-6"도 가능)
    claude_model: str = Field(
        default="auto",
        validation_alias=AliasChoices("claude_model", "CLAUDE_MODEL"),
    )

    # --- Google Gemini (레거시) ---
    google_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("google_api_key", "GOOGLE_API_KEY", "gemini_api_key", "GEMINI_API_KEY"),
    )
    # "gemini-flash-latest"(기본 별칭) | "auto"(list_models 동적조회) | 명시 버전
    gemini_model: str = Field(
        default="gemini-flash-latest",
        validation_alias=AliasChoices("gemini_model", "GEMINI_MODEL"),
    )
    external_llm_timeout_sec: float = 25.0

    # RAG
    rag_top_k_default: int = 6
    rag_max_top_k: int = 12
    # 출처 우선순위: 스캔본 책(pdf) 1순위, 유튜브 자막 2순위.
    #  - 후보를 top_k*over_fetch 만큼 가져와, pdf 카테고리에 점수 보너스를 주고 재정렬.
    #  - 코사인 점수대(~0.45~0.70) 기준 boost 0.12면 책이 사실상 항상 앞서되,
    #    유튜브가 boost 이상으로 더 적합하면 그때만 위로 올라옴(관련성 보존).
    #  - 엄격한 2단 분리를 원하면 boost를 크게(예: 1.0) 설정.
    rag_pdf_boost: float = Field(
        default=0.12,
        validation_alias=AliasChoices("rag_pdf_boost", "RAG_PDF_BOOST"),
    )
    rag_over_fetch: int = Field(
        default=4,
        validation_alias=AliasChoices("rag_over_fetch", "RAG_OVER_FETCH"),
    )
    # 관련성 게이트: 코사인 점수가 이 값 미만인 청크는 버린다(저관련 노이즈 주입 차단).
    #  - 0건이면 [참고자료] 없이 LLM 단독 답변(근거 없는 자료로 인한 환각 방지).
    #  - 실측 분포(top1~0.59, topk~0.57) 기준 0.45면 명백한 저관련만 제거.
    rag_min_score: float = Field(
        default=0.45,
        validation_alias=AliasChoices("rag_min_score", "RAG_MIN_SCORE"),
    )
    # 출처 신뢰등급 재랭킹 가산(코사인 점수에 더함). tier1(고전·이론서)>tier2(스캔본 기본)>tier3(유튜브·카톡).
    #  - pdf_boost(책>유튜브)를 3등급으로 일반화. tier3=0(기준). 엄격분리 원하면 tier1을 크게.
    rag_tier1_boost: float = Field(
        default=0.12,
        validation_alias=AliasChoices("rag_tier1_boost", "RAG_TIER1_BOOST"),
    )
    rag_tier2_boost: float = Field(
        default=0.06,
        validation_alias=AliasChoices("rag_tier2_boost", "RAG_TIER2_BOOST"),
    )
    # OCR 깨짐 등 저품질(한글+한자 비율 낮음) 청크를 검색에서 제외.
    rag_exclude_low_quality: bool = Field(
        default=True,
        validation_alias=AliasChoices("rag_exclude_low_quality", "RAG_EXCLUDE_LOW_QUALITY"),
    )
    # 유튜브 자막(잡담·타인 사주 상담)은 키워드로 오검색돼 답변을 오염 → 검색 근거에서 완전 배제(기본 True).
    # 데이터는 Qdrant 에 남으며(되돌리기 가능), 전문가 구조화 PDF 로 대체하는 동안 노이즈만 차단.
    rag_exclude_youtube: bool = Field(
        default=True,
        validation_alias=AliasChoices("rag_exclude_youtube", "RAG_EXCLUDE_YOUTUBE"),
    )
    # ── RAG 리랭커(cross-encoder) ── dense top_n 후보를 (질문,청크) 교차인코더로 재점수→top_k.
    #  - BGE-m3 코사인 압축(관련~0.55 vs 무관련~0.51) 해결: 리랭커는 관련 0.99 vs 무관 0.00 으로 분리.
    #  - 점수=sigmoid(0~1). min_score 0.1이면 명백히 무관/깨짐만 제거(관련은 0.9+). 5060Ti 16GB GPU.
    rag_reranker_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("rag_reranker_enabled", "RAG_RERANKER_ENABLED"),
    )
    rag_reranker_model: str = Field(
        default="BAAI/bge-reranker-v2-m3",
        validation_alias=AliasChoices("rag_reranker_model", "RAG_RERANKER_MODEL"),
    )
    rag_reranker_device: str = Field(
        default="cuda",  # GPU1(LLM 카드). VRAM 빠듯하면 cpu(지연↑).
        validation_alias=AliasChoices("rag_reranker_device", "RAG_RERANKER_DEVICE"),
    )
    rag_rerank_top_n: int = Field(
        default=24,  # dense 후보 수(이 중에서 리랭커가 top_k 선별)
        validation_alias=AliasChoices("rag_rerank_top_n", "RAG_RERANK_TOP_N"),
    )
    rag_reranker_min_score: float = Field(
        default=0.1,  # sigmoid 관련도 임계. 미만=드롭(0건이면 근거없이 LLM 단독)
        validation_alias=AliasChoices("rag_reranker_min_score", "RAG_RERANKER_MIN_SCORE"),
    )
    # 검색 임베딩(BGE-m3 질의 인코딩) 디바이스. 리랭커가 GPU1을 쓰므로 임베딩은 CPU 기본
    #  (질의 1건 인코딩 ~50~100ms로 가볍고, GPU1 VRAM을 ollama+리랭커에 양보). GPU 여유 시 "cuda".
    rag_embed_device: str = Field(
        default="cpu",
        validation_alias=AliasChoices("rag_embed_device", "RAG_EMBED_DEVICE"),
    )

    # 인증/보안
    jwt_secret: str = Field(
        default="change-me-in-prod-saju-2026",
        validation_alias=AliasChoices("jwt_secret", "JWT_SECRET", "SECRET_KEY"),
    )
    jwt_algorithm: str = "HS256"
    jwt_access_minutes: int = 60 * 24  # 1일 (개발 편의)
    jwt_refresh_days: int = 14

    # 관리자 시드 (최초 1회 자동 생성). 실제 값은 .env에서만 주입(코드 하드코딩 금지).
    #   ADMIN_EMAILS 는 JSON 배열로: ADMIN_EMAILS=["a@x.com","b@y.com"]
    admin_emails: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("admin_emails", "ADMIN_EMAILS"),
    )
    admin_initial_password: str = Field(
        default="",
        validation_alias=AliasChoices("admin_initial_password", "ADMIN_INITIAL_PASSWORD"),
    )
    admin_seed_credits: int = 100_000

    # 크레딧/과금 정책 (베트남 시장가, 1P = 1 VND — VN 유사서비스 top5 벤치마크)
    signup_bonus_credits: int = 20_000     # 가입 보너스 ≈ 무료 질문 1회
    question_cost: int = 19_000            # 추가 질문 1건 (시장가 19k~29k)
    preview_reveal_cost: int = 10_000      # 무료 미리보기 → 전체보기 차감
    preview_char_ratio: float = 0.5  # 50% 미리보기
    free_question_per_day: int = 1
    # 피드백 리워드 — 👍/👎 남기면 해당 답변 결제액의 N%를 적립(답변당 1회·일일 상한). 파밍 차단.
    feedback_reward_pct: int = 3            # 결제액 대비 리워드 비율(%)
    feedback_reward_daily_cap: int = 30_000  # 1일 1인 리워드 적립 상한(P, VND)
    # 약관/법적 페이지
    terms_version: str = "2026-06-01"
    privacy_version: str = "2026-06-01"
    refund_version: str = "2026-06-01"
    min_age_years: int = 18   # 베트남 성년(민법)

    # 답변 품질 가드 — 올해·월별 운세 기본 포함 등 충분한 분량 목표(약 1,800자 이상).
    # num_ctx 12288 + 이력 발췌로 출력 여유 확보됨(잘림 방지).
    answer_min_chars: int = 1800
    answer_retry_max: int = 2

    # Rate Limit (Redis sliding window)
    rate_limit_enabled: bool = True
    rate_limit_chat_per_min: int = 20
    rate_limit_auth_per_min: int = 10
    rate_limit_default_per_min: int = 120

    # JWT Refresh
    refresh_token_bytes: int = 48

    # AES-256-GCM (생년월일 암호화 용). 32-byte url-safe base64 권장.
    pii_aes_key_b64: str = Field(
        default="",
        validation_alias=AliasChoices("pii_aes_key_b64", "PII_AES_KEY_B64", "BIRTH_DATA_AES_KEY"),
    )
    # 결제 (1P = 1 VND, 패키지 4종). VN 은 표시가격 올인 → vat_pct=0 (별도 부가세 미부과).
    vat_pct: int = 0  # VN 올인 가격
    toss_client_key: str = "test_ck_DUMMY_REPLACE_ME"
    toss_secret_key: str = "test_sk_DUMMY_REPLACE_ME"
    toss_api_base: str = "https://api.tosspayments.com"
    # mock 결제(더미키 시 가짜 승인)는 명시적으로 켤 때만 허용 — 외부 공개 인스턴스에서 무결제 크레딧
    # 발행을 원천 차단(fail-closed). 로컬 테스트 시에만 ALLOW_MOCK_PAYMENT=true.
    allow_mock_payment: bool = False
    # 충전 패키지 (VND, 1P=1đ). VN 시장가 기준 4종.
    payment_packages: list[dict] = Field(
        default_factory=lambda: [
            {"amount": 50_000, "credits": 50_000, "label": "50.000đ"},
            {"amount": 100_000, "credits": 100_000, "label": "100.000đ"},
            {"amount": 300_000, "credits": 300_000, "label": "300.000đ"},
            {"amount": 500_000, "credits": 500_000, "label": "500.000đ"},
        ]
    )
    payment_success_url: str = "http://127.0.0.1:5173/payments/success"
    payment_fail_url: str = "http://127.0.0.1:5173/payments/fail"

    # 소셜 OAuth (DUMMY 포함 시 mock 모드로 동작 — 실키 입력만으로 활성화)
    kakao_client_id: str = "DUMMY_KAKAO_CLIENT_ID"
    kakao_client_secret: str = ""
    kakao_redirect_uri: str = "http://127.0.0.1:8008/api/auth/oauth/kakao/callback"
    google_client_id: str = "DUMMY_GOOGLE_CLIENT_ID"
    google_client_secret: str = "DUMMY_GOOGLE_CLIENT_SECRET"
    google_redirect_uri: str = "http://127.0.0.1:8008/api/auth/oauth/google/callback"
    oauth_success_redirect: str = "http://127.0.0.1:5173/login/oauth-success"

    # Toss 웹훅 HMAC 서명
    toss_webhook_secret: str = Field(
        default="",
        validation_alias=AliasChoices("toss_webhook_secret", "TOSS_WEBHOOK_SECRET"),
    )

    # ---- P4 신규 ----
    # 사용자별 채팅 세션 최대 개수(계획 5.6 R). 빈 세션은 카운트 제외(실제 상담만).
    max_sessions_per_user: int = 30
    # 유휴 자동 로그아웃(계획 5.5 O) — 프론트에 노출
    idle_timeout_sec: int = 600
    idle_warn_sec: int = 60
    # 답변 공유 무료 횟수(계획 7.2 K) — Level5(비로그인) 제외 전 회원
    share_quota_default: int = 5
    # 다중 사주 프로필 최대 개수(계획 7-D.2)
    max_profiles_per_user: int = 10
    # 연간회원(Level2) 이용기간: 1년 + 1개월 보너스(계획 5.1)
    membership_year_days: int = 395
    # 연간회원 무과금 사용 한도(회). 소진 시 차단 → 갱신(재결제) 유도.
    membership_annual_quota: int = 1000
    # 오늘의 운세 데일리 푸시(계획 7-D.2)
    daily_fortune_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("daily_fortune_enabled", "DAILY_FORTUNE_ENABLED"),
    )
    daily_fortune_hour: int = 8  # 매일 발송 시각(서버 로컬)
    daily_fortune_minute: int = 0
    # 개인화 일진 푸시(#4): saju_profile 보유 구독자에게 본인 일간 기준 일진 발송.
    # ON이면 데일리 슬롯에서 프로필 보유자는 개인화 일진, 미보유자는 일반 운세를 받음.
    daily_iljin_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("daily_iljin_enabled", "DAILY_ILJIN_ENABLED"),
    )

    # 통합 야간 학습 배치 (OCR→증분색인→STT→아카이브). 전 과정 CPU 전용 —
    # 영상생성(GPU0) 등과의 GPU 경합 차단. 관리자 업로드/재학습은 즉시 실행하지 않고
    # 이 배치가 자정 이후 1일 1회 일괄 처리. 대상 없으면 각 단계 자동 생략.
    nightly_learning_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("nightly_learning_enabled", "NIGHTLY_LEARNING_ENABLED"),
    )
    nightly_learning_hour: int = 0        # 매일 00:30 실행(자정 직후)
    nightly_learning_minute: int = 30
    # STT 파라미터(야간 배치의 mp4 처리에 사용). device 는 배치가 CPU 로 강제.
    uploads_stt_model: str = "medium"     # faster-whisper 모델 (small/medium/large-v3)
    uploads_stt_limit: int = 50           # 1회 배치 최대 처리 건수

    # 일일 질문 인사이트 배치 (질문 클러스터링 + 코퍼스 갭 + 만족도 리포트).
    # CPU 전용 실행 — GPU 서비스/학습에 영향 없음. DB 백업(04:00) 직후 시각.
    daily_insight_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("daily_insight_enabled", "DAILY_INSIGHT_ENABLED"),
    )
    daily_insight_hour: int = 4
    daily_insight_minute: int = 30

    # RAG 검색 품질 평가 배치 (야간 학습 색인 후 자동 추세 누적).
    # CPU 전용 — GPU 서비스/학습과 경합 없음. 야간 학습(00:30) 완료 후·인사이트(04:30)
    # 이전인 03:30 에 1일 1회 실행해, 그날 추가된 자료의 검색 품질 효과를 runs.jsonl 에
    # 누적한다(태그 nightly_YYYYMMDD). 학습/유튜브 재색인/다른 평가가 진행 중이면 미뤘다가
    # 다음 틱에 재시도(예약시각~+3시간), 그 안에 못하면 그날은 건너뛴다(다음 날 측정).
    rag_eval_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("rag_eval_enabled", "RAG_EVAL_ENABLED"),
    )
    rag_eval_hour: int = 3
    rag_eval_minute: int = 30

    # ── 고객센터(CONTACT US) 메일 알림 (SMTP) ──
    # 기본은 mock(비활성): SMTP 미설정 시 실제 발송 대신 로그만 남긴다(문의 접수 자체는 항상 저장).
    # 실 운영 시 SMTP_* 를 .env 에 주입(예: Gmail 앱비밀번호 등)하면 즉시 활성화.
    smtp_enabled: bool = Field(default=False, validation_alias=AliasChoices("smtp_enabled", "SMTP_ENABLED"))
    smtp_host: str = Field(default="", validation_alias=AliasChoices("smtp_host", "SMTP_HOST"))
    smtp_port: int = Field(default=587, validation_alias=AliasChoices("smtp_port", "SMTP_PORT"))
    smtp_user: str = Field(default="", validation_alias=AliasChoices("smtp_user", "SMTP_USER"))
    smtp_password: str = Field(default="", validation_alias=AliasChoices("smtp_password", "SMTP_PASSWORD"))
    smtp_from: str = Field(default="", validation_alias=AliasChoices("smtp_from", "SMTP_FROM"))
    smtp_use_tls: bool = Field(default=True, validation_alias=AliasChoices("smtp_use_tls", "SMTP_USE_TLS"))
    # 고객센터 문의 접수 시 알림 받을 기본 관리자 메일(최초 1회 시드). 이후 관리자 화면에서 CRUD.
    support_default_recipients: list[str] = Field(
        default_factory=lambda: ["orion0321@gmail.com", "yeon6787@gmail.com"],
        validation_alias=AliasChoices("support_default_recipients", "SUPPORT_DEFAULT_RECIPIENTS"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
