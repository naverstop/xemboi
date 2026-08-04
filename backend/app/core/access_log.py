"""개인정보 접속기록·감사 로그 미들웨어 (H2/H3).

관리자·상담사(개인정보취급자)의 회원 PII 접근과 인증 이벤트를 access_logs 에 기록한다.
- PIPA 안전성 확보조치 기준 제8조(접속기록 보관·점검) 이행의 기반.
- 쿠팡형 내부자 오남용 대비: '누가 언제 어느 경로(대상 회원 id 포함)에 접근했는가' 추적 가능.
- H3 이상탐지: 단시간 대량 회원 PII 조회 시 보안 경고 로그(모니터링 훅).

스트리밍(SSE) 응답을 깨지 않도록 순수 ASGI 미들웨어로 구현(응답 본문 미버퍼링, 완료 후 기록).
"""
from __future__ import annotations

import logging
import time

from starlette.concurrency import run_in_threadpool

_log = logging.getLogger("saju.access")

# 감사 대상 — 개인정보취급자(관리자/상담사) 접근 + 인증 이벤트. 일반 사용자 폴링은 제외(잡음/부하 최소).
_AUDIT_PREFIXES = ("/api/admin", "/api/consultation/consultant", "/api/consultation/admin")
_AUDIT_EXACT = {"/api/auth/login", "/api/auth/register", "/api/auth/change-password", "/api/auth/logout"}

# H3 대량조회 경보 임계 — 관리자 계정이 5분 내 이 횟수를 넘겨 /api/admin 을 호출하면 경고.
_BULK_WINDOW_SEC = 300
_BULK_THRESHOLD = 100


def _should_audit(path: str) -> bool:
    return path.startswith(_AUDIT_PREFIXES) or path in _AUDIT_EXACT


def _uid_from_scope(scope) -> int | None:
    for k, v in scope.get("headers", []) or []:
        if k == b"authorization":
            try:
                from backend.app.core.security import decode_token
                token = v.decode("latin-1").split(" ", 1)[-1].strip()
                return int(decode_token(token).get("sub"))
            except Exception:  # noqa: BLE001
                return None
    return None


def _ip_from_scope(scope) -> str | None:
    """감사 IP — X-Forwarded-For 는 클라이언트 위조 가능(스푸핑). rate_limit._client_ip 와 동일하게
    trusted_proxy_count=0 이면 XFF 무시하고 TCP peer IP 사용, >0 이면 오른쪽에서 n번째(신뢰 프록시 삽입) 엔트리."""
    client = scope.get("client")
    peer = (client[0][:64] if client and client[0] else None)
    try:
        from backend.app.core.config import get_settings
        n = int(getattr(get_settings(), "trusted_proxy_count", 0) or 0)
    except Exception:  # noqa: BLE001
        n = 0
    if n > 0:
        for k, v in scope.get("headers", []) or []:
            if k == b"x-forwarded-for":
                parts = [p.strip() for p in v.decode("latin-1").split(",") if p.strip()]
                if parts:
                    return parts[max(0, len(parts) - n)][:64]
    return peer


def _write(uid: int | None, path: str, method: str, status: int, ip: str | None, latency: int) -> None:
    try:
        from backend.app.core.db import get_session_factory
        from backend.app.repositories.auth_models import AccessLog

        sf = get_session_factory()
        with sf() as db:
            db.add(AccessLog(
                user_id=uid, path=path[:255], method=(method or "GET")[:8],
                status=int(status or 0), latency_ms=int(latency or 0), ip=ip,
            ))
            db.commit()
            # H3 이상탐지 — 관리자/스태프의 대량 회원 PII 조회 경보(모니터링 훅)
            if uid is not None and path.startswith("/api/admin"):
                from datetime import datetime, timedelta
                from sqlalchemy import func, select
                since = datetime.utcnow() - timedelta(seconds=_BULK_WINDOW_SEC)
                cnt = db.execute(
                    select(func.count(AccessLog.id)).where(
                        AccessLog.user_id == uid,
                        AccessLog.path.like("/api/admin%"),
                        AccessLog.created_at >= since,
                    )
                ).scalar() or 0
                if cnt >= _BULK_THRESHOLD:
                    _log.warning(
                        "SECURITY: 대량 관리자 PII 조회 의심 — uid=%s 최근 %ds간 %d회(임계 %d). 오남용/유출 점검 필요.",
                        uid, _BULK_WINDOW_SEC, cnt, _BULK_THRESHOLD,
                    )
    except Exception:  # noqa: BLE001 — 감사기록 실패가 요청을 막지 않음
        pass


class AccessLogMiddleware:
    """개인정보취급자 접근·인증 이벤트를 access_logs 에 적재하는 순수 ASGI 미들웨어."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "") or ""
        if not _should_audit(path):
            return await self.app(scope, receive, send)

        status_holder = {"code": 0}

        async def send_wrapper(message) -> None:
            if message.get("type") == "http.response.start":
                status_holder["code"] = message.get("status", 0)
            await send(message)

        start = time.monotonic()
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # 응답은 이미 클라이언트로 전송됨 — 여기서의 DB 기록은 응답 지연에 영향 없음.
            latency = int((time.monotonic() - start) * 1000)
            uid = _uid_from_scope(scope)
            ip = _ip_from_scope(scope)
            method = scope.get("method", "GET")
            try:
                await run_in_threadpool(_write, uid, path, method, status_holder["code"], ip, latency)
            except Exception:  # noqa: BLE001
                pass
