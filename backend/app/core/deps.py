"""FastAPI 인증 Depends."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.db import get_db
from backend.app.core.security import decode_token
from backend.app.repositories.auth_models import User
from backend.app.services.auth_service import get_user_by_id


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1]
    return None


def get_optional_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """토큰이 없거나 잘못되어도 None 반환 (익명 허용 경로용)."""
    token = _extract_token(authorization)
    if not token:
        return None
    try:
        payload = decode_token(token)
    except Exception:
        return None
    uid = payload.get("sub")
    if uid is None:
        return None
    try:
        user_id = int(uid)
    except (TypeError, ValueError):
        return None
    return get_user_by_id(db, user_id)


_SUPPORTED_LOCALES = ("ko", "vi")


def _first_lang(accept_language: Optional[str]) -> Optional[str]:
    """Accept-Language 첫 언어 서브태그 2글자(예: 'vi-VN,vi;q=0.9' → 'vi')."""
    if not accept_language:
        return None
    head = accept_language.split(",")[0].strip()      # 'vi-VN;q=0.9' → 'vi-VN;q=0.9'
    return head.split(";")[0].strip()[:2].lower() or None


def get_locale(
    x_locale: Optional[str] = Header(default=None, alias="X-Locale"),
    accept_language: Optional[str] = Header(default=None, alias="Accept-Language"),
    user: Optional[User] = Depends(get_optional_user),
) -> str:
    """요청 로케일 해석. 우선순위: X-Locale(명시) → user.locale(로그인 선호) → Accept-Language → 'ko'.
    지원 로케일(ko|vi) 밖은 무시하고 다음 후보로. 기본 'ko'(한국 서비스 불변)."""
    for cand in (x_locale, getattr(user, "locale", None), _first_lang(accept_language)):
        c = (cand or "").strip().lower()[:2]
        if c in _SUPPORTED_LOCALES:
            return c
    dl = get_settings().default_locale     # 인스턴스 기본(ko=한국 / vi=VN)
    return dl if dl in _SUPPORTED_LOCALES else "ko"


def get_current_user(
    user: Optional[User] = Depends(get_optional_user),
) -> User:
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="로그인이 필요해요. 먼저 로그인해 주세요.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="관리자 전용 기능이에요.")
    return user


def require_level(min_level: int):
    """회원등급 게이트(계획 5.3). level 값이 작을수록 상위 권한.

    예: require_level(1) → Level 0·1(관리자)만 통과.
    """
    from backend.app.services.auth_service import effective_level

    def _dep(user: User = Depends(get_current_user)) -> User:
        if effective_level(user) > min_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="이 기능을 이용할 권한이 없어요.",
            )
        return user

    return _dep
