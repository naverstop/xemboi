"""FastAPI 진입점.

실행:
  uvicorn backend.app.main:app --host 127.0.0.1 --port 8008 --reload
"""
from __future__ import annotations

import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.app.api import admin, amulet, banners, chat, compat_invite, dream, pass_api, reviews, share_card, snack, trust, eval as eval_api, health, oauth, payments, push, saju, uploads, auth, templates, feedback, share, profiles, compatibility, tools, pdf, support, video, tarot, consultation
from backend.app.api import usage
from backend.app.core.config import get_settings
from backend.app.core.db import get_engine, get_session_factory
from backend.app.core.rate_limit import RateLimitMiddleware
from backend.app.repositories.models import Base
# upload_models/auth_models 도 import 해야 metadata에 등록되어 create_all 시 테이블 생성됨
from backend.app.repositories import upload_models  # noqa: F401
from backend.app.repositories import auth_models  # noqa: F401
from backend.app.repositories import consultation_models  # noqa: F401
from backend.app.repositories import pricing_models  # noqa: F401
from backend.app.services import auth_service


def _spa_file_within_dist(dist_root_real: str, full_path: str) -> "str | None":
    """경로순회(Path Traversal) 봉쇄 헬퍼.

    full_path 를 dist 루트 기준으로 합친 뒤 realpath 로 정규화한 실제 경로가 dist 안에 있고
    '파일'일 때만 그 경로를 돌려준다. dist 밖(.env·소스 등)으로 탈출하거나 파일이 아니면 None
    → 호출부에서 SPA index 로 폴백. Starlette 가 %2e%2e%2f 같은 인코딩을 이미 ../ 로 디코드해
    핸들러에 넘기므로, 여기서 realpath 로 한 번 더 정규화해 dist 경계 밖 접근을 차단한다."""
    if not full_path:
        return None
    candidate = os.path.realpath(os.path.join(dist_root_real, full_path))
    within = candidate == dist_root_real or candidate.startswith(dist_root_real + os.sep)
    if within and os.path.isfile(candidate):
        return candidate
    return None


def _mount_spa(app: FastAPI, frontend_dist: str) -> None:
    """Vite 빌드 산출물(frontend/dist) 정적 서빙 + SPA 폴백 라우트 등록.

    dist 가 없으면(빌드 전) 아무것도 등록하지 않는다. /assets 는 해시 파일명이라 캐시 가능하므로
    별도 mount, 그 외 경로는 경로순회 봉쇄(_spa_file_within_dist) 후 SPA index 로 폴백."""
    if not os.path.isdir(frontend_dist):
        return
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
    index_html = os.path.join(frontend_dist, "index.html")
    # SPA 진입점은 절대 캐시하지 않는다 — 빌드 시 번들 해시가 바뀌어도 옛 index.html(옛 번들 참조)을
    # 계속 내주면 새 화면이 안 보이는 문제 방지. (assets/* 는 해시 파일명이라 캐시해도 안전 — 별도 mount.)
    _NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}

    def _index() -> FileResponse:
        return FileResponse(index_html, headers=_NO_CACHE)

    @app.get("/", include_in_schema=False)
    def _spa_root():
        return _index()

    dist_root = os.path.realpath(frontend_dist)

    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa_catch(full_path: str):
        # 경로순회 차단: dist 안의 파일일 때만 직접 서빙, 그 외(.env·소스 등)는 SPA index 폴백.
        served = _spa_file_within_dist(dist_root, full_path)
        if served is not None:
            return FileResponse(served)
        return _index()


def _consultation_separate() -> bool:
    """상담 전용 프로세스 분리 여부(기본 ON). 0/false/off 면 메인에서 직접 서빙(dev 폴백)."""
    return os.getenv("SAJU_CONSULTATION_WORKER", "1").lower() not in ("0", "false", "off")


def _consultation_port() -> int:
    try:
        return int(os.getenv("SAJU_CONSULTATION_PORT", "8010"))
    except ValueError:
        return 8010


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title=s.app_name, version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware)
    # 개인정보 접속기록·감사 로그(H2) + 대량조회 이상탐지(H3) — 관리자/상담사 PII 접근·인증 이벤트 기록.
    from backend.app.core.access_log import AccessLogMiddleware
    app.add_middleware(AccessLogMiddleware)
    # 보안 응답 헤더(M3) — HSTS·nosniff·X-Frame-Options·Referrer-Policy.
    from backend.app.core.security_headers import SecurityHeadersMiddleware
    app.add_middleware(SecurityHeadersMiddleware)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(oauth.router)
    app.include_router(admin.router)
    app.include_router(banners.router)
    app.include_router(saju.router)
    app.include_router(chat.router)
    app.include_router(uploads.router)
    app.include_router(eval_api.router)
    app.include_router(payments.router)
    app.include_router(push.router)
    app.include_router(templates.router)
    app.include_router(feedback.router)
    app.include_router(share.router)
    app.include_router(profiles.router)
    app.include_router(compatibility.router)
    app.include_router(tarot.router)
    app.include_router(tools.router)
    app.include_router(pdf.router)
    app.include_router(support.router)
    app.include_router(usage.router)
    app.include_router(support.admin_router)
    app.include_router(reviews.router)
    app.include_router(reviews.admin_router)
    app.include_router(amulet.router)
    app.include_router(trust.router)
    app.include_router(share_card.router)
    app.include_router(pass_api.router)
    app.include_router(dream.router)
    app.include_router(compat_invite.router)
    app.include_router(snack.router)
    app.include_router(snack.card_router)
    app.include_router(video.router)
    # 1:1 인적 상담(입점업체). 관리자 라우터(순수 DB)는 항상 메인.
    # 사용자 라우터(REST 세션 lifecycle + WebSocket)는 구조 C: 상담 전용 프로세스로 분리하고
    # 여기서 /api/consultation/* 를 리버스 프록시(기본). SAJU_CONSULTATION_WORKER=0 이면 메인에서 직접 서빙(dev).
    app.include_router(consultation.admin_router)
    app.include_router(consultation.partner_router)  # 입점 신청 — 워커 프록시 우회(메인 직접)
    if _consultation_separate():
        from backend.app.api.consultation_proxy import mount_consultation_proxy
        mount_consultation_proxy(app, _consultation_port())
    else:
        app.include_router(consultation.router)

    @app.on_event("startup")
    def _bootstrap_db() -> None:
        # ── DB/컬렉션 물리분리 가드 — vi 인스턴스는 한국 saju_db/saju_corpus 접근 금지(fail-closed) ──
        #   VN(DEFAULT_LOCALE=vi)이 한국 리소스를 가리키면 부팅 자체를 거부해 데이터 오염을 원천 차단.
        _s = get_settings()
        if _s.default_locale == "vi":
            _dbname = _s.database_url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]
            if _dbname == "saju_db" or _s.qdrant_collection == "saju_corpus":
                raise RuntimeError(
                    "VN 인스턴스(DEFAULT_LOCALE=vi)가 한국 리소스를 가리킵니다 — 부팅 거부. "
                    f"현재 DB='{_dbname}', collection='{_s.qdrant_collection}'. "
                    "물리 분리 필요: DATABASE_URL=...saju_vn_db · QDRANT_COLLECTION=saju_vn_corpus"
                )
        # 스키마는 Alembic으로 관리: `alembic upgrade head` 가 사전에 실행되어 있어야 함.
        # create_all 은 신규 모델 추가 시 마이그레이션 미작성 케이스를 위한 안전망(기존 테이블은 건드리지 않음).
        engine = get_engine()
        Base.metadata.create_all(bind=engine)
        # 기존 테이블 신규 컬럼 멱등 보강(마이그레이션 미실행 환경 안전망, PG)
        try:
            from sqlalchemy import text
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS saju_profile TEXT"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS free_quota_period VARCHAR(7)"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS disclaimer_agreed_at TIMESTAMP"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS disclaimer_agreed_version VARCHAR(32)"))
                # 공유 쿼터 주기 앵커(2026-07-23) — 이게 없으면 share_used_count 가 리셋되지 않아
                # "공유 월 20회" 안내와 달리 평생 한도가 된다(패스 2개월차 공유 0회 버그).
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS share_period_start TIMESTAMP"))
                conn.execute(text("UPDATE users SET share_period_start = (NOW() AT TIME ZONE 'UTC') "
                                  "WHERE share_period_start IS NULL"))
                # 사주 프로필 출생지(진태양시 정밀화) 컬럼 — 멱등 보강
                conn.execute(text("ALTER TABLE saju_profiles ADD COLUMN IF NOT EXISTS birth_longitude DOUBLE PRECISION"))
                conn.execute(text("ALTER TABLE saju_profiles ADD COLUMN IF NOT EXISTS apply_equation_of_time BOOLEAN NOT NULL DEFAULT FALSE"))
                conn.execute(text("ALTER TABLE saju_profiles ADD COLUMN IF NOT EXISTS night_zi_mode VARCHAR(8)"))
                # 피드백 리워드 적립액 — 멱등 보강
                conn.execute(text("ALTER TABLE message_feedback ADD COLUMN IF NOT EXISTS reward_granted INTEGER NOT NULL DEFAULT 0"))
                # 피드백 학습 폐루프 처리 여부 — 멱등 보강
                conn.execute(text("ALTER TABLE message_feedback ADD COLUMN IF NOT EXISTS learned BOOLEAN NOT NULL DEFAULT FALSE"))
                # 회원 전체보기(reveal) 이연 차감액 — 멱등 보강
                conn.execute(text("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS reveal_cost INTEGER NOT NULL DEFAULT 0"))
                # 크레딧 거래 멱등키(리컨실 재실행·재시도 이중차감/이중환불 차단) — 컬럼 + 부분 UNIQUE 인덱스 멱등 보강
                conn.execute(text("ALTER TABLE credit_transactions ADD COLUMN IF NOT EXISTS idem_key VARCHAR(80)"))
                conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_credit_tx_idem "
                                  "ON credit_transactions (idem_key) WHERE idem_key IS NOT NULL"))
                # 영수증 무료슬롯 orphan 확장(slot_kind/pass_id) — answer_receipts 는 create_all 로 이미 생성됐으므로 컬럼만 멱등 보강.
                conn.execute(text("ALTER TABLE answer_receipts ADD COLUMN IF NOT EXISTS slot_kind VARCHAR(12) NOT NULL DEFAULT 'cash'"))
                conn.execute(text("ALTER TABLE answer_receipts ADD COLUMN IF NOT EXISTS pass_id BIGINT"))
                # 업로드 비전 재OCR 시도 횟수 — 백로그 무한 재시도(색인 불가 페이지 매일 Claude 호출) 방지 상한용.
                conn.execute(text("ALTER TABLE uploads ADD COLUMN IF NOT EXISTS vision_attempts INTEGER NOT NULL DEFAULT 0"))
                # 국외이전 별도 동의(H4, 제28조의8) — 멱등 보강
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS overseas_transfer_opt_in BOOLEAN NOT NULL DEFAULT FALSE"))
                # 민감정보 처리 별도 동의(제23조) — 멱등 보강
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS sensitive_consent BOOLEAN NOT NULL DEFAULT FALSE"))
                # 1:1 상담 만족도 평점 — 멱등 보강(consultation_sessions 는 create_all 로 생성되지만 기존 DB엔 신규 컬럼 없음)
                conn.execute(text("ALTER TABLE consultation_sessions ADD COLUMN IF NOT EXISTS rating INTEGER"))
                # 상담사 자율설정(키워드·분당/시간당 요금·입점예정 상태·셀프편집 잠금) — 멱등 보강
                conn.execute(text("ALTER TABLE consultants ADD COLUMN IF NOT EXISTS keywords TEXT"))
                conn.execute(text("ALTER TABLE consultants ADD COLUMN IF NOT EXISTS price_unit VARCHAR(8) NOT NULL DEFAULT 'session'"))
                conn.execute(text("ALTER TABLE consultants ADD COLUMN IF NOT EXISTS per_min_p INTEGER"))
                conn.execute(text("ALTER TABLE consultants ADD COLUMN IF NOT EXISTS per_hour_p INTEGER"))
                conn.execute(text("ALTER TABLE consultants ADD COLUMN IF NOT EXISTS status VARCHAR(12) NOT NULL DEFAULT 'active'"))
                conn.execute(text("ALTER TABLE consultants ADD COLUMN IF NOT EXISTS self_managed BOOLEAN NOT NULL DEFAULT TRUE"))
                conn.execute(text("ALTER TABLE consultants ADD COLUMN IF NOT EXISTS business_hours TEXT"))  # 요일별 영업시간표(JSON)
                # 세션 정산 수수료 스냅샷(요청 시 고정) — 멱등 보강
                conn.execute(text("ALTER TABLE consultation_sessions ADD COLUMN IF NOT EXISTS commission_pct INTEGER"))
                # A-1 상담 컨텍스트 자동 전달(사주 명식/타로 카드 스냅샷) — 멱등 보강
                conn.execute(text("ALTER TABLE consultation_sessions ADD COLUMN IF NOT EXISTS source_kind VARCHAR(8)"))
                conn.execute(text("ALTER TABLE consultation_sessions ADD COLUMN IF NOT EXISTS source_context JSON"))
                # A-2 예약 상담 — 세션의 예약 출처(슬롯 테이블은 create_all 로 생성) — 멱등 보강
                conn.execute(text("ALTER TABLE consultation_sessions ADD COLUMN IF NOT EXISTS reservation_id VARCHAR(64)"))
                # [P3-D1] RAG 회수 로그의 메뉴 태그 — 멱등 보강
                conn.execute(text("ALTER TABLE retrieval_logs ADD COLUMN IF NOT EXISTS menu VARCHAR(32)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_retrieval_logs_menu ON retrieval_logs (menu)"))
                # 이중 로케일(ko/vi) — 사용자·세션·프로필 locale 멱등 보강(마이그레이션 0015 미실행 환경 안전망). 기존 행은 'ko'.
                for _t in ("users", "chat_sessions", "saju_profiles", "compat_sessions",
                           "tool_sessions", "tarot_sessions", "consultation_sessions"):
                    conn.execute(text(f"ALTER TABLE {_t} ADD COLUMN IF NOT EXISTS locale VARCHAR(2) NOT NULL DEFAULT 'ko'"))
                # 피드백 source 네임스페이스(사주/택일/궁합 메시지 id 충돌 방지) — 멱등 보강
                conn.execute(text("ALTER TABLE message_feedback ADD COLUMN IF NOT EXISTS source VARCHAR(16) NOT NULL DEFAULT 'chat'"))
                conn.execute(text("ALTER TABLE message_feedback DROP CONSTRAINT IF EXISTS uq_feedback_msg_user"))
                conn.execute(text(
                    "DO $$ BEGIN "
                    "IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='uq_feedback_msg_src_user') THEN "
                    "ALTER TABLE message_feedback ADD CONSTRAINT uq_feedback_msg_src_user UNIQUE (message_id, source, user_id); "
                    "END IF; END $$;"
                ))
                # ── 개인정보 컬럼 투명 암호화 마이그레이션(M2/②) — 기존 평문을 1회 암호화. 트랜잭션 원자성 보장(중단 시 롤백). ──
                from backend.app.core.crypto import encrypt_str as _enc, is_enabled as _crypto_on
                _bt = conn.execute(text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name='saju_profiles' AND column_name='birth_date'"
                )).scalar()
                _plaintext_pending = bool(_bt and _bt.lower() == "date")  # date형 = 아직 평문
                # #3 크립토 페일패스트 — 키(PII_AES_KEY_B64) 미설정 상태에서 암호화 경로가 돌면
                #   encrypt_str/decrypt_str 이 조용히 None 을 반환한다: 평문 마이그레이션은 모든 PII 를
                #   NULL 로 덮어써 파괴하고, 이미 암호화된 DB 는 복호화가 전부 None 이 되어 서비스가 조용히 손상된다.
                #   두 경우 모두 치명적이므로 암호화 경로를 실행하지 않고 CRITICAL 로 크게 경고한다(운영자 조치 유도).
                if not _crypto_on():
                    import logging as _lgc
                    _prof_cnt = conn.execute(text("SELECT count(*) FROM saju_profiles")).scalar() or 0
                    _enc_json = conn.execute(text(
                        "SELECT count(*) FROM users WHERE saju_profile IS NOT NULL "
                        "AND left(btrim(saju_profile),1) NOT IN ('{','[')"
                    )).scalar() or 0
                    if _prof_cnt or _enc_json or not _plaintext_pending:
                        _lgc.getLogger("saju.db").critical(
                            "PII 암호화 키(PII_AES_KEY_B64) 미설정 — 프로필 %d행 / 암호화된 saju_profile %d행 존재. "
                            "암호화·복호화가 모두 None 을 반환하므로 암호화 마이그레이션을 건너뜁니다"
                            "(키 없이 진행하면 평문 파괴 또는 복호 실패). .env 의 PII_AES_KEY_B64 설정 후 재기동하세요.",
                            _prof_cnt, _enc_json,
                        )
                else:
                    if _plaintext_pending:  # 아직 평문(date) → TEXT(암호문)로 전환 + 기존값 암호화
                        conn.execute(text("ALTER TABLE saju_profiles ALTER COLUMN birth_date TYPE TEXT USING birth_date::text"))
                        conn.execute(text("ALTER TABLE saju_profiles ALTER COLUMN birth_time TYPE TEXT"))
                        conn.execute(text("ALTER TABLE saju_profiles ALTER COLUMN birth_longitude TYPE TEXT USING birth_longitude::text"))
                        _rows = conn.execute(text("SELECT id, birth_date, birth_time, birth_longitude FROM saju_profiles")).fetchall()
                        for _r in _rows:
                            conn.execute(
                                text("UPDATE saju_profiles SET birth_date=:bd, birth_time=:bt, birth_longitude=:bl WHERE id=:id"),
                                {"id": _r[0],
                                 "bd": _enc(_r[1]) if _r[1] is not None else None,
                                 "bt": _enc(_r[2]) if _r[2] is not None else None,
                                 "bl": _enc(_r[3]) if _r[3] is not None else None},
                            )
                        import logging as _lg
                        _lg.getLogger("saju.db").info("saju_profiles birth columns encrypted: %d rows", len(_rows))
                    # users.saju_profile(JSON): 평문(‘{’/‘[’로 시작)인 값만 암호화(멱등 — 암호문은 스킵).
                    _prows = conn.execute(text("SELECT id, saju_profile FROM users WHERE saju_profile IS NOT NULL")).fetchall()
                    _pn = 0
                    for _r in _prows:
                        _v = _r[1]
                        if _v and _v.lstrip()[:1] in ("{", "["):
                            conn.execute(text("UPDATE users SET saju_profile=:v WHERE id=:id"), {"id": _r[0], "v": _enc(_v)})
                            _pn += 1
                    if _pn:
                        import logging as _lg2
                        _lg2.getLogger("saju.db").info("users.saju_profile encrypted: %d rows", _pn)
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger("saju.db").warning("saju_profile column ensure failed: %s", e)
        # 관리자 시드 (멱등)
        sf = get_session_factory()
        with sf() as db:
            try:
                auth_service.seed_admins(db)
            except Exception as e:  # noqa: BLE001
                import logging
                logging.getLogger("saju.auth").warning("admin seeding failed: %s", e)
            try:
                from backend.app.services import admin_service
                admin_service.seed_default_banners(db)
            except Exception as e:  # noqa: BLE001
                import logging
                logging.getLogger("saju.admin").warning("banner seeding failed: %s", e)
            try:
                from backend.app.services import settings_service
                settings_service.seed_defaults(db)
            except Exception as e:  # noqa: BLE001
                import logging
                logging.getLogger("saju.admin").warning("settings seeding failed: %s", e)
            try:
                from backend.app.services import support_service
                support_service.seed_default_recipients(db)
            except Exception as e:  # noqa: BLE001
                import logging
                logging.getLogger("saju.support").warning("support recipient seeding failed: %s", e)
            try:
                # 타로 카드 해석/키워드 관리자 오버레이 프리로드(이후 편집은 저장 시 즉시 캐시 갱신)
                from backend.app.services import tarot_content
                tarot_content.refresh_cache(db)
            except Exception as e:  # noqa: BLE001
                import logging
                logging.getLogger("saju.admin").warning("tarot overrides preload failed: %s", e)
        # 백그라운드 스케줄러(오늘의 운세 데일리 푸시, 계획 7-D.2)
        try:
            from backend.app.services import scheduler
            scheduler.start()
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger("saju.scheduler").warning("scheduler start failed: %s", e)
        # 사주 영상 렌더 워커(별도 프로세스·detach). 재기동 때마다 새 워커가 pid를 인계(takeover)받고
        # 전임 워커는 현재 작업을 끝낸 뒤 자진 은퇴 → 재시작만으로 '새 코드' 워커로 자동 교체.
        try:
            if os.getenv("SAJU_VIDEO_WORKER", "1").lower() not in ("0", "false", "off"):
                import subprocess
                _root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                _logdir = os.path.join(_root, "logs")
                os.makedirs(_logdir, exist_ok=True)
                # CREATE_NO_WINDOW(0x08000000): 콘솔 창 없이 백그라운드(DETACHED_PROCESS 는 새 콘솔창을
                # 띄움 → 금지). CREATE_NEW_PROCESS_GROUP(0x200): --reload 의 CTRL 시그널과 분리해
                # 합성 중인 워커가 안 죽게(학습배치와 동일). 세대교체는 워커 _take_ownership/_should_retire 가 담당.
                _flags = (0x08000000 | 0x00000200) if os.name == "nt" else 0
                _fout = open(os.path.join(_logdir, "video_worker.log"), "a", encoding="utf-8")
                subprocess.Popen(
                    [sys.executable, "-m", "backend.app.services.video.worker"],
                    cwd=_root, stdout=_fout, stderr=subprocess.STDOUT,
                    creationflags=_flags, close_fds=True,
                )
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger("saju.video").warning("video worker spawn failed: %s", e)

        # 상담 전용 프로세스(구조 C) — 영상 워커와 동일하게 CREATE_NO_WINDOW(콘솔창 없이)로 기동.
        # 이미 떠 있으면(이전 세대·live 채팅 보유) 재기동하지 않아, 메인 앱 --reload/재시작이
        # 진행 중인 채팅을 끊지 않는다. saju_start.bat 실행 시 자동 동반 기동(별도 콘솔창 없음).
        try:
            if _consultation_separate():
                import subprocess
                import urllib.request
                port = _consultation_port()
                alive = False
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/_health", timeout=0.6) as _r:
                        alive = _r.status == 200
                except Exception:  # noqa: BLE001
                    alive = False
                if not alive:
                    _root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                    _logdir = os.path.join(_root, "logs")
                    os.makedirs(_logdir, exist_ok=True)
                    _flags = (0x08000000 | 0x00000200) if os.name == "nt" else 0  # CREATE_NO_WINDOW|NEW_PROCESS_GROUP
                    _fout = open(os.path.join(_logdir, "consultation_server.log"), "a", encoding="utf-8")
                    _env = {**os.environ, "SAJU_CONSULTATION_PORT": str(port)}
                    subprocess.Popen(
                        [sys.executable, "-m", "backend.app.consultation_server"],
                        cwd=_root, stdout=_fout, stderr=subprocess.STDOUT,
                        creationflags=_flags, close_fds=True, env=_env,
                    )
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger("saju.consultation").warning("consultation server spawn failed: %s", e)

        # LLM·RAG 모델 워밍업 — 첫 질문 지연 제거(임베더/리랭커 선(先)로드 + qwen3:14b 상주).
        # 백그라운드 스레드(기동 비차단). 재기동마다 실행돼 첫 사용자 질문이 즉시 응답되게 한다.
        try:
            import threading as _th
            from backend.app.services import chat_service as _cs
            _th.Thread(target=_cs.warmup_models, daemon=True, name="model-warmup").start()
        except Exception as e:  # noqa: BLE001
            import logging
            logging.getLogger("saju.warmup").warning("warmup thread start failed: %s", e)

    # [프론트엔드] Vite 빌드 산출물(frontend/dist) 정적 서빙 — /api 외 모든 경로는 SPA index.html
    # (경로순회 봉쇄 포함). 로직은 모듈 레벨 _mount_spa/_spa_file_within_dist 로 추출 — 회귀 테스트 가능.
    frontend_dist = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
    )
    _mount_spa(app, frontend_dist)

    return app


app = create_app()
