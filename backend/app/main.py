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

from backend.app.api import admin, banners, chat, eval as eval_api, health, oauth, payments, push, saju, uploads, auth, templates, feedback, share, profiles, compatibility, tools, pdf, support, video, tarot, consultation
from backend.app.core.config import get_settings
from backend.app.core.db import get_engine, get_session_factory
from backend.app.core.rate_limit import RateLimitMiddleware
from backend.app.repositories.models import Base
# upload_models/auth_models 도 import 해야 metadata에 등록되어 create_all 시 테이블 생성됨
from backend.app.repositories import upload_models  # noqa: F401
from backend.app.repositories import auth_models  # noqa: F401
from backend.app.repositories import consultation_models  # noqa: F401
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
    app.include_router(support.admin_router)
    app.include_router(video.router)
    # 1:1 인적 상담(입점업체). 관리자 라우터(순수 DB)는 항상 메인.
    # 사용자 라우터(REST 세션 lifecycle + WebSocket)는 구조 C: 상담 전용 프로세스로 분리하고
    # 여기서 /api/consultation/* 를 리버스 프록시(기본). SAJU_CONSULTATION_WORKER=0 이면 메인에서 직접 서빙(dev).
    app.include_router(consultation.admin_router)
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
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS disclaimer_agreed_at TIMESTAMP"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS disclaimer_agreed_version VARCHAR(32)"))
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
                # 1:1 상담 만족도 평점 — 멱등 보강(consultation_sessions 는 create_all 로 생성되지만 기존 DB엔 신규 컬럼 없음)
                conn.execute(text("ALTER TABLE consultation_sessions ADD COLUMN IF NOT EXISTS rating INTEGER"))
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

        # LLM·RAG 모델 워밍업 — 첫 질문 지연 제거(임베더/리랭커 선(先)로드 + exaone/qwen 상주).
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
