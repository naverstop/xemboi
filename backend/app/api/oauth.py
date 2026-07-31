"""소셜 OAuth (카카오 / 구글).

설계:
- /api/auth/oauth/{provider}/start  → 로그인 URL 반환 (provider별 authorize URL + redirect_uri)
- /api/auth/oauth/{provider}/callback ?code=...  → 토큰 교환 + 사용자 정보 조회 + DB upsert + 자체 JWT 발급
- 더미 모드(client_id에 "DUMMY" 포함): 토큰교환을 mock 처리하고 가짜 profile 생성 → 회원 upsert
  → 키 입력 전 개발/QA에서 전체 흐름 검증 가능.
- callback은 프론트로 302 redirect (해시 토큰: #token=... ) — 프론트 OAuthSuccessPage 가 파싱.
"""
from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.db import get_db
from backend.app.core.security import create_access_token, issue_refresh_token
from backend.app.services import auth_service as svc

router = APIRouter(prefix="/api/auth/oauth", tags=["oauth"])


def _is_dummy(v: str) -> bool:
    return (not v) or ("DUMMY" in v)


# -------- Provider 설정 --------

def _provider_cfg(provider: str) -> dict[str, Any]:
    s = get_settings()
    if provider == "kakao":
        return {
            "authorize_url": "https://kauth.kakao.com/oauth/authorize",
            "token_url": "https://kauth.kakao.com/oauth/token",
            "userinfo_url": "https://kapi.kakao.com/v2/user/me",
            "client_id": s.kakao_client_id,
            "client_secret": s.kakao_client_secret,
            "redirect_uri": s.kakao_redirect_uri,
            "scope": "account_email profile_nickname",
        }
    if provider == "google":
        return {
            "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "redirect_uri": s.google_redirect_uri,
            "scope": "openid email profile",
        }
    raise HTTPException(status_code=404, detail=f"unknown provider: {provider}")


@router.get("/{provider}/start")
def oauth_start(provider: str) -> dict[str, Any]:
    cfg = _provider_cfg(provider)
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "response_type": "code",
        "scope": cfg["scope"],
        "state": state,
    }
    if provider == "google":
        params["access_type"] = "online"
        params["prompt"] = "select_account"
    url = f"{cfg['authorize_url']}?{urlencode(params)}"
    return {
        "provider": provider,
        "authorize_url": url,
        "state": state,
        "mock": _is_dummy(cfg["client_id"]),
        "redirect_uri": cfg["redirect_uri"],
    }


_http_client: "httpx.Client | None" = None


def _http() -> httpx.Client:
    """모듈 공유 httpx 클라이언트 — IdP 호출 시 커넥션/TLS 재사용."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=httpx.Timeout(10.0))
    return _http_client


def _exchange_token(provider: str, code: str) -> dict[str, Any]:
    cfg = _provider_cfg(provider)
    if _is_dummy(cfg["client_id"]):
        # 더미 토큰 (실제 호출 안 함)
        return {"access_token": f"mock_{provider}_{secrets.token_hex(8)}", "mock": True}
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "redirect_uri": cfg["redirect_uri"],
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    r = _http().post(cfg["token_url"], data=data, headers=headers, timeout=10.0)
    if r.status_code >= 400:
        # IdP 원문(redirect_uri·client_id 힌트 등)은 서버 로그로만, 클라엔 일반 메시지.
        import logging
        logging.getLogger("saju.oauth").warning(
            "%s token exchange failed: %s %s", provider, r.status_code, r.text[:300])
        raise HTTPException(status_code=502, detail=f"{provider} 로그인에 실패했어요. 잠시 후 다시 시도해 주세요.")
    return r.json()


def _fetch_profile(provider: str, access_token: str, code_hint: str) -> dict[str, Any]:
    """provider 별 표준 프로필 dict 반환: {oauth_id, email, nickname}."""
    cfg = _provider_cfg(provider)
    if _is_dummy(cfg["client_id"]):
        # 더미 모드: code 해시로 안정적 식별자 생성
        oid = f"mock_{provider}_{abs(hash(code_hint)) % 10**10}"
        email = f"{oid}@mock.{provider}.local"
        nickname = f"{provider}_user_{oid[-6:]}"
        return {"oauth_id": oid, "email": email, "nickname": nickname}
    headers = {"Authorization": f"Bearer {access_token}"}
    r = _http().get(cfg["userinfo_url"], headers=headers, timeout=10.0)
    if r.status_code >= 400:
        import logging
        logging.getLogger("saju.oauth").warning(
            "%s userinfo failed: %s %s", provider, r.status_code, r.text[:300])
        raise HTTPException(status_code=502, detail=f"{provider} 로그인에 실패했어요. 잠시 후 다시 시도해 주세요.")
    data = r.json()
    if provider == "kakao":
        oid = str(data.get("id"))
        kacc = (data.get("kakao_account") or {})
        email = (kacc.get("email") or f"kakao_{oid}@nomail.local")
        nickname = ((kacc.get("profile") or {}).get("nickname") or f"kakao_{oid[-6:]}")
    else:  # google
        oid = str(data.get("sub") or data.get("id"))
        email = data.get("email") or f"google_{oid}@nomail.local"
        nickname = data.get("name") or data.get("given_name") or f"google_{oid[-6:]}"
    return {"oauth_id": oid, "email": email.lower(), "nickname": nickname}


def _upsert_user(db: Session, provider: str, profile: dict[str, Any]):
    s = get_settings()
    # 1) provider+oauth_id 매칭
    from sqlalchemy import select
    from backend.app.repositories.auth_models import User
    user = db.execute(
        select(User).where(
            User.oauth_provider == provider, User.oauth_id == profile["oauth_id"]
        )
    ).scalar_one_or_none()
    if user is None:
        # 2) 동일 이메일 회원이 이미 있으면 OAuth 정보 부착
        existing = svc.get_user_by_email(db, profile["email"])
        if existing is not None:
            existing.oauth_provider = provider
            existing.oauth_id = profile["oauth_id"]
            user = existing
            db.flush()
        else:
            user = svc.create_user(
                db,
                email=profile["email"],
                password=None,  # OAuth만으로 가입 시 패스워드 없음
                nickname=profile["nickname"],
                oauth_provider=provider,
                oauth_id=profile["oauth_id"],
            )
            # 가입 보너스
            svc.adjust_credit(db, user.id, s.signup_bonus_credits, reason="signup_bonus")
    from datetime import datetime as _dt
    user.last_login_at = _dt.utcnow()
    db.flush()
    return user


@router.get("/{provider}/callback")
def oauth_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(""),
    db: Session = Depends(get_db),
):
    """provider OAuth 콜백 → 자체 JWT 발급 → 프론트로 redirect (해시에 토큰)."""
    s = get_settings()
    tok = _exchange_token(provider, code)
    profile = _fetch_profile(provider, tok.get("access_token", ""), code_hint=code)
    user = _upsert_user(db, provider, profile)
    db.commit()
    jwt_tok = create_access_token(str(user.id), extra={"role": user.role})
    refresh_tok = issue_refresh_token(user.id)  # 무음 갱신용 — 이메일 로그인과 동일하게 발급
    # 프론트로 fragment 전달 (서버 로그/Referer 노출 최소화)
    target = (
        f"{s.oauth_success_redirect}"
        f"#token={jwt_tok}&refresh={refresh_tok}&role={user.role}&provider={provider}"
    )
    return RedirectResponse(url=target, status_code=302)


# 테스트용 직접 콜백 호출(브라우저 없이 흐름 검증 — 더미 모드 전용 보호장치 없음, 실키여도 502일 뿐)
@router.post("/{provider}/test-login")
def oauth_test_login(provider: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """더미 모드 한정 신뢰 가능. 실키 모드에선 거부."""
    cfg = _provider_cfg(provider)
    if not _is_dummy(cfg["client_id"]):
        raise HTTPException(status_code=400, detail="test-login is dummy-mode only")
    code = secrets.token_urlsafe(8)
    profile = _fetch_profile(provider, "mock", code_hint=code)
    user = _upsert_user(db, provider, profile)
    db.commit()
    jwt_tok = create_access_token(str(user.id), extra={"role": user.role})
    return {
        "access_token": jwt_tok,
        "refresh_token": issue_refresh_token(user.id),
        "token_type": "bearer",
        "role": user.role,
        "email": user.email,
        "provider": provider,
        "mock": True,
    }
