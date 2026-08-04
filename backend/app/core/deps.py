"""FastAPI 인증 Depends."""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

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
    """토큰이 '없으면' None(익명 허용 경로). 단 토큰이 '실려 왔는데 만료·무효'면 401을 던진다.

    과거엔 만료 토큰의 JWTError까지 삼켜 None(익명)으로 강등 → optional 라우트가 401 대신
    200(익명 미리보기)을 반환했고, 프론트 강제로그아웃(notifySessionExpired)·무음갱신(refresh)은
    모두 401에서만 발동하므로 '로그인 상태(캐시 잔액)인데 미리보기'로 새어나가는 사고가 반복됐다.
    → '토큰 없음(진짜 비로그인)'과 '토큰 만료·무효'를 구분해, 후자는 401로 재로그인/무음갱신을 유도한다."""
    token = _extract_token(authorization)
    if not token:
        return None  # 진짜 비로그인 — 익명 미리보기 허용(정상)
    try:
        payload = decode_token(token)
    except Exception:
        # 토큰이 실려 왔는데 만료·서명오류 → 조용한 익명 금지, 401로 재로그인/무음갱신 유도
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 만료됐어요. 다시 로그인해 주세요.",
        )
    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 만료됐어요. 다시 로그인해 주세요.",
        )
    user = get_user_by_id(db, user_id)
    if user is None:
        # 토큰 서명은 유효한데 사용자가 삭제됨 → 무효 세션
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 만료됐어요. 다시 로그인해 주세요.",
        )
    return user


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
