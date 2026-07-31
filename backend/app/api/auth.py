"""인증/회원 API."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.crypto import encrypt_str
from backend.app.core.db import get_db
from backend.app.core.deps import get_current_user
from backend.app.core.security import create_access_token, issue_refresh_token, logout_refresh_token, rotate_refresh_token
from backend.app.repositories import chat_repo
from backend.app.repositories.auth_models import User
from backend.app.services import auth_service as svc

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 면책고지 버전(문구 변경 시 올리면 재동의 요구 가능). 현재 문구 기준.
DISCLAIMER_VERSION = "2026-06"


class RegisterReq(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    nickname: Optional[str] = None
    birth_date: date  # 19세 검증 위해 필수
    marketing_opt_in: bool = False
    answer_dialect: str = "standard"
    # 약관 동의 (필수). 프론트는 settings의 현재 버전 문자열을 그대로 전달.
    agree_terms: bool
    agree_privacy: bool
    agree_refund: bool
    agree_disclaimer: bool = False  # 면책고지 확인(필수) — 가입 시 동시 고지·기록


class LoginReq(BaseModel):
    email: EmailStr
    password: str


class ChangePwReq(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class RefreshReq(BaseModel):
    refresh_token: str


class TokenResp(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    must_change_password: bool = False
    role: str = "user"


class MeResp(BaseModel):
    id: int
    email: str
    nickname: Optional[str]
    role: str
    balance: int
    must_change_password: bool
    daily_free_available: bool
    ads_hidden: bool
    level: int
    answer_dialect: str = "standard"
    free_used_count: int = 0
    free_quota_count: int = 3
    free_remaining: int = 0
    # 과금 안내용 (질문당 크레딧 비용 / 연간회원 정보)
    credit_cost_basic: int = 0
    credit_cost_deep: int = 0
    preview_reveal_cost: int = 0
    video_gen_cost: int = 0          # 사주 영상 생성 차감 P(관리자 설정값 — 프론트 안내문구 동기화용)
    # 프리미엄 5개 메뉴 입장료(메뉴별 실가격=할인 반영) / 공통 할인% / 이 사용자 무료 여부
    premium_entry_costs: dict[str, int] = {}
    premium_entry_discount_pct: int = 0
    premium_entry_free: bool = False
    is_member: bool = False          # 연간회원(Level2) 유효기간 내
    membership_remaining: int = 0    # 연간회원 무과금 잔여 횟수
    membership_quota: int = 0        # 연간회원 연 한도
    saju_profile: Optional[dict] = None   # 저장된 본인 사주 프로필(자동 채움)
    disclaimer_agreed: bool = False       # 면책고지 동의(최초 1회) 완료 여부
    terms_agreed: bool = False            # 약관 3종(이용약관·개인정보·환불) 동의 완료 여부(SNS 가입자 게이트용)


class LegalVersionsResp(BaseModel):
    terms: str
    privacy: str
    refund: str
    min_age_years: int
    service_name: str = ""
    business: dict = {}   # 사업자 정보(공개) — 관리자 입력값
    bodies: dict = {}     # 약관 본문 덮어쓰기(Markdown). 비면 프론트 기본 문안


def _token_for(user: User, with_refresh: bool = True) -> TokenResp:
    token = create_access_token(str(user.id), extra={"role": user.role})
    refresh = issue_refresh_token(user.id) if with_refresh else None
    return TokenResp(
        access_token=token,
        refresh_token=refresh,
        must_change_password=user.must_change_password,
        role=user.role,
    )


def _calc_age(birth: date, today: date | None = None) -> int:
    today = today or date.today()
    years = today.year - birth.year
    if (today.month, today.day) < (birth.month, birth.day):
        years -= 1
    return years


@router.get("/legal", response_model=LegalVersionsResp)
def legal_versions(db: Session = Depends(get_db)) -> LegalVersionsResp:
    from backend.app.services import settings_service as ss

    s = get_settings()
    site = ss.get_public_site(db)

    def pick(key: str, fb: str) -> str:
        v = (site.get(key) or "").strip()
        return v if v else fb

    try:
        min_age = int((site.get("min_age_years") or "").strip())
    except (ValueError, TypeError):
        min_age = s.min_age_years

    return LegalVersionsResp(
        terms=pick("terms_version", s.terms_version),
        privacy=pick("privacy_version", s.privacy_version),
        refund=pick("refund_version", s.refund_version),
        min_age_years=min_age,
        service_name=pick("service_name", ""),
        business={
            "name": site.get("biz_name", ""),
            "ceo": site.get("biz_ceo", ""),
            "reg_no": site.get("biz_reg_no", ""),
            "mailorder_no": site.get("biz_mailorder_no", ""),
            "address": site.get("biz_address", ""),
            "tel": site.get("biz_tel", ""),
            "hours": site.get("biz_hours", ""),
            "email": site.get("biz_email", ""),
            "privacy_officer": site.get("biz_privacy_officer", ""),
            "hosting": site.get("biz_hosting", ""),
        },
        bodies={
            "terms": site.get("legal_body_terms", ""),
            "privacy": site.get("legal_body_privacy", ""),
            "refund": site.get("legal_body_refund", ""),
            "disclaimer": site.get("legal_body_disclaimer", ""),
        },
    )


@router.post("/register", response_model=TokenResp)
def register(body: RegisterReq, db: Session = Depends(get_db)) -> TokenResp:
    s = get_settings()
    # 약관 동의 강제
    if not (body.agree_terms and body.agree_privacy and body.agree_refund):
        raise HTTPException(status_code=400, detail="이용약관·개인정보·환불정책에 모두 동의해 주세요.")
    # 19세 미만 차단
    age = _calc_age(body.birth_date)
    if age < s.min_age_years:
        raise HTTPException(status_code=400, detail=f"만 {s.min_age_years}세 이상만 가입할 수 있어요.")
    if svc.get_user_by_email(db, body.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 가입된 이메일이에요. 로그인해 주세요.")
    user = svc.create_user(
        db,
        email=body.email,
        password=body.password,
        nickname=body.nickname,
        role="user",
    )
    user.birth_date = body.birth_date
    user.birth_date_enc = encrypt_str(body.birth_date.isoformat())
    user.marketing_opt_in = body.marketing_opt_in
    if body.answer_dialect in {"standard", "gyeongsang", "jeolla", "gangwon", "jeju"}:
        user.answer_dialect = body.answer_dialect
    user.terms_agreed_version = s.terms_version
    user.privacy_agreed_version = s.privacy_version
    user.refund_agreed_version = s.refund_version
    user.terms_agreed_at = datetime.utcnow()
    # 면책고지도 가입 폼에서 함께 확인 → 동의 기록(가입자는 로그인 후 별도 면책 게이트 불필요)
    if body.agree_disclaimer:
        user.disclaimer_agreed_at = datetime.utcnow()
        user.disclaimer_agreed_version = DISCLAIMER_VERSION
    db.flush()
    # 가입 보너스
    svc.adjust_credit(db, user.id, s.signup_bonus_credits, reason="signup_bonus")
    db.commit()
    return _token_for(user)


@router.post("/login", response_model=TokenResp)
def login(body: LoginReq, db: Session = Depends(get_db)) -> TokenResp:
    user = svc.authenticate(db, body.email, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다. 다시 확인해 주세요.",
        )
    db.commit()
    return _token_for(user)


@router.post("/refresh", response_model=TokenResp)
def refresh(body: RefreshReq, db: Session = Depends(get_db)) -> TokenResp:
    new = rotate_refresh_token(body.refresh_token)
    if new is None:
        raise HTTPException(status_code=401, detail="로그인이 만료되었어요. 다시 로그인해 주세요.")
    user_id, new_refresh = new
    user = svc.get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="계정을 찾을 수 없어요. 다시 로그인해 주세요.")
    token = create_access_token(str(user.id), extra={"role": user.role})
    return TokenResp(
        access_token=token,
        refresh_token=new_refresh,
        must_change_password=user.must_change_password,
        role=user.role,
    )


@router.post("/logout", status_code=204)
def logout(body: RefreshReq, db: Session = Depends(get_db)) -> None:
    # refresh 토큰 무효화 + 소유 회원의 빈 세션(메시지 0개) 정리.
    uid = logout_refresh_token(body.refresh_token)
    if uid is not None:
        try:
            chat_repo.delete_empty_sessions(db, uid)
        except Exception:
            # 빈 세션 정리는 부가 작업 — 실패해도 로그아웃 자체는 성공시킨다.
            db.rollback()


@router.post("/change-password", response_model=MeResp)
def change_password(
    body: ChangePwReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MeResp:
    from backend.app.core.security import verify_password

    if not user.password_hash or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="현재 비밀번호가 올바르지 않습니다."
        )
    svc.change_password(db, user, body.new_password)
    db.commit()
    return _me_payload(db, user)


@router.get("/me", response_model=MeResp)
def me(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MeResp:
    return _me_payload(db, user)


class SajuProfileReq(BaseModel):
    profile: Optional[dict] = None   # None이면 저장 해제(삭제)


@router.put("/me/saju", response_model=MeResp)
def save_saju_profile(
    body: SajuProfileReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MeResp:
    """본인 사주 기본 프로필 저장(자동 채움용). profile=None이면 해제."""
    import json as _json
    user.saju_profile = _json.dumps(body.profile, ensure_ascii=False) if body.profile else None
    db.add(user)
    db.commit()
    db.refresh(user)
    return _me_payload(db, user)


@router.post("/me/agree-disclaimer", response_model=MeResp)
def agree_disclaimer(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MeResp:
    """면책고지 동의 기록(최초 1회, 법적효력). 동의 시각·버전 저장."""
    if not user.disclaimer_agreed_at:
        user.disclaimer_agreed_at = datetime.utcnow()
        user.disclaimer_agreed_version = DISCLAIMER_VERSION
        db.add(user)
        db.commit()
        db.refresh(user)
    return _me_payload(db, user)


class AgreeTermsReq(BaseModel):
    agree_terms: bool
    agree_privacy: bool
    agree_refund: bool
    marketing_opt_in: Optional[bool] = None


@router.post("/me/agree-terms", response_model=MeResp)
def agree_terms(
    body: AgreeTermsReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MeResp:
    """약관 3종(이용약관·개인정보·환불) 동의 기록 — SNS 가입자 등 미동의 사용자 게이트용.
    회원가입 폼을 거치지 않은 SNS 신규 가입자에게 로그인 직후 필수 동의를 받는다(법적효력)."""
    if not (body.agree_terms and body.agree_privacy and body.agree_refund):
        raise HTTPException(status_code=400, detail="이용약관·개인정보·환불정책에 모두 동의해 주세요.")
    s = get_settings()
    if not user.terms_agreed_at:
        user.terms_agreed_version = s.terms_version
        user.privacy_agreed_version = s.privacy_version
        user.refund_agreed_version = s.refund_version
        user.terms_agreed_at = datetime.utcnow()
        if body.marketing_opt_in is not None:
            user.marketing_opt_in = bool(body.marketing_opt_in)
        db.add(user)
        db.commit()
        db.refresh(user)
    return _me_payload(db, user)


class ProfileUpdateReq(BaseModel):
    nickname: Optional[str] = None
    answer_dialect: Optional[str] = None


_VALID_DIALECTS = {"standard", "gyeongsang", "jeolla", "gangwon", "jeju"}


@router.patch("/me", response_model=MeResp)
def update_me(
    body: ProfileUpdateReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MeResp:
    if body.nickname is not None:
        user.nickname = body.nickname[:64]
    if body.answer_dialect is not None:
        if body.answer_dialect not in _VALID_DIALECTS:
            raise HTTPException(status_code=400, detail="invalid dialect")
        user.answer_dialect = body.answer_dialect
    db.commit()
    return _me_payload(db, user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """회원 탈퇴: 모든 채팅 세션/메시지 삭제 + User 삭제.

    User 삭제 시 ondelete=CASCADE 로 credits / credit_transactions / payments 자동 정리,
    access_logs.user_id 는 SET NULL.
    """
    from backend.app.repositories import chat_repo
    chat_repo.delete_all_user_sessions(db, user.id)
    db.delete(user)
    db.commit()


def _me_payload(db: Session, user: User) -> MeResp:
    today = date.today()
    from backend.app.services import settings_service
    level = svc.effective_level(user)
    free_quota = settings_service.get_int(db, "free_quota_count")
    used = user.free_used_count or 0
    free_remaining = max(0, free_quota - used) if level >= 3 else free_quota
    from datetime import datetime as _dt
    from backend.app.core.config import get_settings as _gs
    _s = _gs()
    is_member = bool(
        level == 2 and user.membership_expires_at and user.membership_expires_at > _dt.utcnow()
    )
    membership_quota = _s.membership_annual_quota
    membership_remaining = max(0, membership_quota - (user.membership_used_count or 0)) if is_member else 0
    # 프리미엄 메뉴 입장료(할인 반영) + 이 사용자 무료 여부(멤버십만)
    _disc = max(0, min(100, settings_service.get_int(db, "premium_entry_discount_pct", 0)))
    premium_entry_costs = {
        m: max(0, round(settings_service.get_int(db, f"entry_cost_{m}", 10000) * (100 - _disc) / 100))
        for m in ("compat", "taekil", "jakmyeong", "gaemyeong", "aho", "tarot")
    }
    # 관리자도 일반회원과 동일하게 정가 표시·차감(운영자 요청) — 무료는 유효 멤버십만.
    # (서버 실제 차감은 _decide_entry_billing 과 일치)
    premium_entry_free = is_member
    saju_profile = None
    if getattr(user, "saju_profile", None):
        try:
            import json as _json
            saju_profile = _json.loads(user.saju_profile)
        except Exception:  # noqa: BLE001
            saju_profile = None
    return MeResp(
        id=user.id,
        email=user.email,
        nickname=user.nickname,
        role=user.role,
        balance=svc.get_balance(db, user.id),
        must_change_password=user.must_change_password,
        daily_free_available=(user.daily_free_used_at != today),
        ads_hidden=svc.is_ads_hidden(db, user),
        level=level,
        answer_dialect=user.answer_dialect or "standard",
        free_used_count=used,
        free_quota_count=free_quota,
        free_remaining=free_remaining,
        credit_cost_basic=settings_service.get_int(db, "credit_cost_basic"),
        credit_cost_deep=settings_service.get_int(db, "credit_cost_deep"),
        preview_reveal_cost=settings_service.get_int(db, "preview_reveal_cost"),
        video_gen_cost=settings_service.get_int(db, "video_gen_cost"),
        premium_entry_costs=premium_entry_costs,
        premium_entry_discount_pct=_disc,
        premium_entry_free=premium_entry_free,
        is_member=is_member,
        membership_remaining=membership_remaining,
        membership_quota=membership_quota,
        saju_profile=saju_profile,
        disclaimer_agreed=bool(getattr(user, "disclaimer_agreed_at", None)),
        terms_agreed=bool(getattr(user, "terms_agreed_at", None)),
    )
