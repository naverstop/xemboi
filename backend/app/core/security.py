"""비밀번호 해시 + JWT 발급/검증 + Refresh token (Redis 화이트리스트)."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt

from backend.app.core.config import get_settings


def _to_bytes(pw: str) -> bytes:
    # bcrypt는 72바이트 한계가 있어 안전 컷
    b = pw.encode("utf-8")
    return b[:72]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_to_bytes(plain), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bytes(plain), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=s.jwt_access_minutes)).timestamp()),
        "typ": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except JWTError as e:
        raise ValueError(f"invalid token: {e}") from e


# ---- Refresh token: 불투명 토큰 + Redis 화이트리스트 (fallback: in-memory) ----

_mem_store: dict[str, dict[str, Any]] = {}


_redis_client = None
_redis_unavailable = False


def _redis():
    global _redis_client, _redis_unavailable
    s = get_settings()
    # Redis 미사용(기본) → in-memory 화이트리스트 사용. 죽은 Redis 접속 시도 없음.
    if not s.redis_enabled or _redis_unavailable:
        return None
    if _redis_client is not None:
        return _redis_client
    try:
        import redis  # type: ignore

        client = redis.Redis.from_url(
            s.redis_url, decode_responses=True, socket_timeout=0.3, socket_connect_timeout=0.3
        )
        client.ping()  # 실제 연결 가능 여부 1회 검증(미가동이면 즉시 in-memory 폴백)
        _redis_client = client
        return _redis_client
    except Exception:
        _redis_unavailable = True
        return None


def _refresh_key(token: str) -> str:
    return f"refresh:{token}"


def issue_refresh_token(user_id: int) -> str:
    s = get_settings()
    tok = secrets.token_urlsafe(s.refresh_token_bytes)
    ttl = s.jwt_refresh_days * 86400
    r = _redis()
    if r is not None:
        try:
            r.setex(_refresh_key(tok), ttl, str(user_id))
            return tok
        except Exception:
            pass
    now = datetime.utcnow()
    # lazy 만료 스윕: 재방문 없는 만료 토큰 누적 방지(redis 미사용 폴백 한정). 일정 크기 넘을 때만 스캔.
    if len(_mem_store) > 64:
        for k in [k for k, v in _mem_store.items() if v.get("exp", now) < now]:
            _mem_store.pop(k, None)
    _mem_store[tok] = {
        "user_id": user_id,
        "exp": now + timedelta(seconds=ttl),
    }
    return tok


def _consume_refresh(token: str) -> Optional[int]:
    r = _redis()
    if r is not None:
        try:
            uid = r.get(_refresh_key(token))
            if uid is None:
                return None
            r.delete(_refresh_key(token))
            return int(uid)
        except Exception:
            pass
    row = _mem_store.pop(token, None)
    if row is None:
        return None
    if row["exp"] < datetime.utcnow():
        return None
    return int(row["user_id"])


def rotate_refresh_token(token: str) -> Optional[tuple[int, str]]:
    """기존 refresh 무효화 + 신규 발급. 유효하면 (user_id, new_token), 아니면 None."""
    uid = _consume_refresh(token)
    if uid is None:
        return None
    return uid, issue_refresh_token(uid)


def revoke_refresh_token(token: str) -> bool:
    return _consume_refresh(token) is not None


def logout_refresh_token(token: str) -> Optional[int]:
    """로그아웃: refresh 토큰을 무효화하고 소유 user_id를 반환(없으면 None).

    revoke_refresh_token과 동일하게 토큰을 소비하되, 후처리(빈 세션 정리 등)를
    위해 소유자 id를 함께 돌려준다.
    """
    return _consume_refresh(token)

