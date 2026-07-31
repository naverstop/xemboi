"""상담 전용 프로세스 — 상담 라우터(REST+WS)만 담은 독립 uvicorn(구조 C).

메인 앱(--reload)과 격리해 편집/재시작이 진행 중인 실시간 채팅을 끊지 않게 한다. in-memory
연결풀(Redis 불필요). 메인 앱이 startup 에서 CREATE_NO_WINDOW(콘솔창 없이)로 이 프로세스를
기동하고 /api/consultation/* 를 이 포트로 리버스 프록시한다(consultation_proxy).

DB/스키마는 메인 앱이 관리(create_all)하므로 여기선 라우터만 올린다.
실행: python -m backend.app.consultation_server  (포트=SAJU_CONSULTATION_PORT, 기본 8010)
설계: [[consultation-1on1-plan]].
"""
from __future__ import annotations

import os

from fastapi import FastAPI

from backend.app.api import consultation
from backend.app.repositories import consultation_models  # noqa: F401  (모델 메타데이터 등록)


def create_consultation_app() -> FastAPI:
    app = FastAPI(title="Saju Consultation Service", version="0.1.0")

    @app.get("/_health")
    def _health() -> dict[str, str]:
        return {"status": "ok", "service": "consultation"}

    # 사용자 상담 라우터(REST 세션 lifecycle + WebSocket). 관리자 라우터는 메인 앱에 둔다(순수 DB).
    app.include_router(consultation.router)
    return app


app = create_consultation_app()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("SAJU_CONSULTATION_PORT", "8010"))
    # app 객체 직접 전달 → --reload 없음(단일 프로세스). WebSocket 은 uvicorn[standard] 가 처리.
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
