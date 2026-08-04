"""Rate limit middleware — Redis sliding window (fallback: in-memory).

규칙:
- /api/auth/*       : auth limit
- /api/chat/*       : chat limit
- 그 외 /api/*      : default
키: (route_class, ip)  +  (route_class, user_id) [Bearer 있을 때]
"""
from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from backend.app.core.config import get_settings
from backend.app.core.security import decode_token


_mem: dict[str, deque[float]] = {}
_mem_lock = Lock()
_mem_sweep_counter = 0  # 주기적 스윕 카운터(무한증가 방지 — redis 미사용 폴백 한정)


# 비밀번호 무차별 대입·계정 스팸 방어가 필요한 민감 인증 엔드포인트만 strict(분당 rate_limit_auth_per_min).
# /me·/oauth·/refresh·/legal·/logout 등은 빈번하거나 무차별 대입이 불가하므로 default 한도를 따른다
# (특히 /api/auth/me 는 프론트가 화면마다 호출 → 과거 전체 /api/auth strict 적용 시 정상 사용자도 차단됨).
_AUTH_STRICT_PREFIXES = (
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/change-password",
)


def _classify(path: str, method: str = "GET") -> str:
    if any(path.startswith(p) for p in _AUTH_STRICT_PREFIXES):
        return "auth"
    # 관리자 회원 PII 조회 — 대량조회 남용 억제(저한도). 목록/검색·거래·결제 조회 계열.
    if path.startswith("/api/admin/users") or path.startswith("/api/admin/payments"):
        return "admin"
    if path.startswith("/api/chat"):
        return "chat"
    # PDF '생성'(POST)만 별도 강한 한도 — 미로그인도 생성 가능해 반복 호출로 디스크를
    # 채우는 남용(DoS) 벡터였음. 열람(GET /api/pdf/{token}, 공유 수신자)은 default 유지.
    if method == "POST" and path.startswith("/api/pdf"):
        return "pdf"
    return "default"


def _limit_for(klass: str) -> int:
    s = get_settings()
    if klass == "auth":
        return s.rate_limit_auth_per_min
    if klass == "chat":
        return s.rate_limit_chat_per_min
    if klass == "pdf":
        return s.rate_limit_pdf_per_min
    if klass == "admin":
        return s.rate_limit_admin_per_min
    return s.rate_limit_default_per_min


def _client_ip(request: Request) -> str:
    """레이트리밋 키용 클라이언트 IP.

    X-Forwarded-For 는 클라이언트가 자유롭게 위조할 수 있어, 첫 엔트리를 무조건 신뢰하면
    헤더 스푸핑으로 IP 단위 레이트리밋을 무력화(Sybil 증폭)할 수 있다. 신뢰 프록시 홉 수
    (trusted_proxy_count)만큼 '오른쪽에서' 떨어진 엔트리(=신뢰 프록시가 덧붙인, 위조 불가
    위치)만 신뢰하고, 0이면 XFF 를 무시하고 TCP peer IP 를 쓴다."""
    peer = (request.client.host if request.client else "0.0.0.0") or "0.0.0.0"
    try:
        from backend.app.core.config import get_settings
        n = int(getattr(get_settings(), "trusted_proxy_count", 0) or 0)
    except Exception:  # noqa: BLE001
        n = 0
    if n > 0:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            parts = [p.strip() for p in fwd.split(",") if p.strip()]
            if parts:
                # 신뢰 프록시 n개가 오른쪽에 덧붙임 → 그만큼 안쪽이 실제 클라이언트.
                return parts[max(0, len(parts) - n)]
    return peer


def _user_id_from_auth(request: Request) -> Optional[int]:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    try:
        payload = decode_token(auth.split(" ", 1)[1].strip())
        sub = payload.get("sub")
        return int(sub) if sub is not None else None
    except Exception:
        return None


_redis_client = None
_redis_unavailable = False


def _redis():
    global _redis_client, _redis_unavailable
    # Redis 미사용(기본) → 즉시 in-memory 사용. 죽은 Redis 접속 시도 없음.
    if not get_settings().redis_enabled:
        return None
    # Redis 가 한 번 사용 불가로 확인되면 매 요청마다 연결 타임아웃을
    # 반복 지불하지 않도록 즉시 in-memory 폴백을 사용한다.
    if _redis_unavailable:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis  # type: ignore

        client = redis.Redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            # 닫힌 포트 접속이 느린 환경 대비 짧게(최대 ~0.3s/시도). 실패 시 in-memory.
            socket_timeout=0.3,
            socket_connect_timeout=0.3,
        )
        # from_url 은 지연 연결이므로 실제 연결 가능 여부를 ping 으로 1회 검증한다.
        client.ping()
        _redis_client = client
        return _redis_client
    except Exception:
        _redis_unavailable = True
        return None


def _allow_redis(key: str, limit: int, window_sec: int = 60) -> tuple[bool, int]:
    r = _redis()
    if r is None:
        return _allow_mem(key, limit, window_sec)
    try:
        now_ms = int(time.time() * 1000)
        cutoff = now_ms - window_sec * 1000
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zadd(key, {f"{now_ms}-{secrets_token()}": now_ms})
        pipe.zcard(key)
        pipe.expire(key, window_sec + 5)
        _, _, count, _ = pipe.execute()
        return (int(count) <= limit, int(count))
    except Exception:
        return _allow_mem(key, limit, window_sec)


def secrets_token() -> str:
    import secrets

    return secrets.token_hex(4)


def _allow_mem(key: str, limit: int, window_sec: int = 60) -> tuple[bool, int]:
    global _mem_sweep_counter
    now = time.time()
    cutoff = now - window_sec
    with _mem_lock:
        dq = _mem.setdefault(key, deque())
        while dq and dq[0] < cutoff:
            dq.popleft()
        dq.append(now)
        count = len(dq)
        # 주기적 스윕: 오래(>window) 안 쓰인 키(전부 만료) 제거 — 고유 (route,ip) 키 무한증가 방지.
        _mem_sweep_counter += 1
        if _mem_sweep_counter >= 2000:
            _mem_sweep_counter = 0
            stale = [k for k, d in _mem.items() if k != key and (not d or d[-1] < cutoff)]
            for k in stale:
                del _mem[k]
    return (count <= limit, count)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        s = get_settings()
        path = request.url.path
        if not s.rate_limit_enabled or not path.startswith("/api/"):
            return await call_next(request)
        # 헬스/정적은 제외
        if path.startswith("/api/health"):
            return await call_next(request)

        klass = _classify(path, request.method)
        limit = _limit_for(klass)
        ip = _client_ip(request)
        uid = _user_id_from_auth(request)
        keys = [f"rl:{klass}:ip:{ip}"]
        if uid is not None:
            keys.append(f"rl:{klass}:uid:{uid}")
        for key in keys:
            ok, count = _allow_redis(key, limit)
            if not ok:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "rate_limit_exceeded",
                        "class": klass,
                        "limit_per_min": limit,
                        "count": count,
                    },
                    headers={"Retry-After": "30"},
                )
        return await call_next(request)
