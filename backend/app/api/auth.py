"""인증/회원 API."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

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


def _check_password(pw: str) -> None:
    """비밀번호 규칙(숫자+문자, 8자 이상). 실패 시 한글 400.

    [운영자 지적 2026-07-27] Field(min_length=8)는 Pydantic 영문 422('String should have at least
    8 characters')를 냈다. 길이 검증을 Field 에서 빼고 여기서 해 한글 메시지를 준다(조합 규칙도 함께).
    """
    if len(pw or "") < 8 or not re.search(r"[A-Za-z]", pw or "") or not re.search(r"\d", pw or ""):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="비밀번호는 숫자·문자를 포함한 8자 이상을 입력해 주세요.")


class RegisterReq(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)
    nickname: Optional[str] = None
    birth_date: date  # 19세 검증 위해 필수
    marketing_opt_in: bool = False
    # 국외이전 별도 동의(선택, 제28조의8) — 외부 AI 심화 보강에 질문·사주맥락을 국외(미국 등)로 전송하는 것에 동의.
    agree_overseas: bool = False
    # 민감정보 처리 별도 동의(선택, 제23조) — 상담/채팅에 건강·신념 등 민감정보가 포함될 수 있음에 동의.
    agree_sensitive: bool = False
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
    new_password: str = Field(max_length=128)


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
    overseas_transfer_opt_in: bool = False  # 국외이전 별도 동의(H4) 상태
    birth_verified: bool = False  # 생년월일(연령) 검증 여부 — SNS 가입자 게이트용(M8)
    free_used_count: int = 0
    free_quota_count: int = 3
    free_remaining: int = 0
    # 과금 안내용 (질문당 크레딧 비용 / 연간회원 정보)
    credit_cost_basic: int = 0
    credit_cost_deep: int = 0
    preview_reveal_cost: int = 0
    video_gen_cost: int = 0          # 사주 영상 생성 차감 P(관리자 설정값 — 프론트 안내문구 동기화용)
    amulet_cost_p: int = 0           # B-4 부적 발행 차감 P(관리자 설정값)
    # 프리미엄 5개 메뉴 입장료(메뉴별 실가격=할인 반영) / 공통 할인% / 이 사용자 무료 여부
    premium_entry_costs: dict[str, int] = {}
    premium_entry_discount_pct: int = 0
    premium_entry_free: bool = False
    is_member: bool = False          # 연간회원(Level2) 유효기간 내
    membership_remaining: int = 0    # 연간회원 무과금 잔여 횟수
    membership_quota: int = 0        # 연간회원 연 한도
    saju_profile: Optional[dict] = None   # 저장된 본인 사주 프로필(자동 채움)
    active_pass: Optional[dict] = None    # B-7 월 패스 상태(없으면 None)
    # 플러스 패스 추가질문 할인% — 화면이 '실제 차감액'을 계산해 안내하려면 필요하다.
    # 없을 때 프론트는 정가(1,900P)만 보여줬는데 플러스는 실제로 1,330P 가 빠졌다(표시≠실제).
    pass_followup_discount_pct: int = 0
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
    _check_password(body.password)   # 숫자·문자 포함 8자 이상(한글 메시지)
    # 약관 동의 강제
    if not (body.agree_terms and body.agree_privacy and body.agree_refund):
        raise HTTPException(status_code=400, detail="이용약관·개인정보·환불정책에 모두 동의해 주세요.")
    # 19세 미만 차단
    age = _calc_age(body.birth_date)
    if age < s.min_age_years:
        raise HTTPException(status_code=400, detail=f"만 {s.min_age_years}세 이상만 가입할 수 있어요.")
    if svc.get_user_by_email(db, body.email):
        # 계정 열거 완화(L16) — 존재 여부를 단정하지 않는 일반 메시지(+가입 rate-limit 10/분). 완전 차단은 이메일 인증 흐름 필요.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="입력하신 정보로는 가입할 수 없어요. 이미 가입된 계정이면 로그인해 주세요.")
    user = svc.create_user(
        db,
        email=body.email,
        password=body.password,
        nickname=body.nickname,
        role="user",
    )
    # 생년월일은 암호문(birth_date_enc)만 저장 — 평문 컬럼 병존은 암호화 실효화(M1). 연령검증은 위 _calc_age(요청값)로 수행.
    user.birth_date_enc = encrypt_str(body.birth_date.isoformat())
    user.marketing_opt_in = body.marketing_opt_in
    user.overseas_transfer_opt_in = body.agree_overseas  # 국외이전 별도 동의(제28조의8) 기록
    user.sensitive_consent = body.agree_sensitive  # 민감정보 처리 별도 동의(제23조) 기록
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
    _check_password(body.new_password)   # 숫자·문자 포함 8자 이상(한글 메시지)
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
    overseas_transfer_opt_in: Optional[bool] = None  # 국외이전 별도 동의(H4) 토글 — 기존 회원용
    birth_date: Optional[date] = None  # SNS 가입자 연령검증용(M8) — 만19세 검증 후 암호문 저장


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
    if body.overseas_transfer_opt_in is not None:
        user.overseas_transfer_opt_in = bool(body.overseas_transfer_opt_in)
    if body.birth_date is not None:
        # SNS 가입 등 생년월일 미보유 회원의 연령검증(M8) — 만 N세 미만 차단, 암호문만 저장.
        if _calc_age(body.birth_date) < get_settings().min_age_years:
            raise HTTPException(status_code=400, detail=f"만 {get_settings().min_age_years}세 이상만 이용할 수 있어요.")
        user.birth_date_enc = encrypt_str(body.birth_date.isoformat())
    db.commit()
    return _me_payload(db, user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """회원 탈퇴: 회원의 전 서비스 개인정보를 파기(제21조) + User 삭제.

    User 삭제 시 ondelete=CASCADE 로 credits / credit_transactions / payments 자동 정리,
    access_logs.user_id 는 SET NULL. 그 외 CASCADE 되지 않는 궁합/타로/작명·택일/영상/프로필/검색로그를
    명시 삭제하고, 고객센터 문의는 회계 목적상 레코드는 남기되 연락처·본문(PII)만 마스킹한다(M12/L14).
    """
    from sqlalchemy import text as _text
    from backend.app.repositories import chat_repo

    uid = user.id
    # 검색로그(retrieval_logs)의 질문 원문(PII) — 채팅뿐 아니라 궁합(compat_id)·도구(tool_id) 메뉴 추가질문도
    # 여기 적재됨(N3). 세션 삭제 전에 세 메뉴의 세션 id 로 연결된 로그를 모두 즉시 파기.
    db.execute(_text(
        "DELETE FROM retrieval_logs WHERE session_id IN ("
        " SELECT session_id FROM chat_sessions WHERE user_id=:u"
        " UNION SELECT compat_id FROM compat_sessions WHERE user_id=:u"
        " UNION SELECT tool_id FROM tool_sessions WHERE user_id=:u)"
    ), {"u": uid})
    # 피드백 코멘트(사용자 작성 원문, PII) 즉시 파기 — rating 은 익명 집계용 보존(user_id 는 SET NULL)(N4).
    db.execute(_text("UPDATE message_feedback SET comment=NULL WHERE user_id=:u"), {"u": uid})
    # 사주 영상 파일(.mp4) 고아 방지(#2 순서수정) — saju_video_jobs.session_id FK 가 chat_sessions CASCADE 라
    # chat 세션 삭제(delete_all_user_sessions) 시 영상잡 행이 함께 사라진다. 반드시 그 '전에' 파일을 unlink.
    # (#2a) 본인 소유 잡(user_id) + '본인 세션에 찍힌' 잡을 모두 커버 — 관리자가 타인 메시지로 생성한 잡은
    #   user_id 가 관리자라 user_id 조건만으론 놓치지만 session_id 가 본인 세션이면 CASCADE 로 행이 지워져 파일이 고아가 된다.
    try:
        from backend.app.services.video import service as _vsvc
        for _mp, _dp in db.execute(_text(
            "SELECT master_path, delivery_path FROM saju_video_jobs "
            "WHERE user_id=:u OR session_id IN (SELECT session_id FROM chat_sessions WHERE user_id=:u)"
        ), {"u": uid}).fetchall():
            for _rel in (_mp, _dp):
                _p = _vsvc._abs(_rel)
                try:
                    if _p and _p.is_file():
                        _p.unlink()
                except OSError:
                    pass
    except Exception:  # noqa: BLE001 — 파일 정리 실패가 탈퇴를 막지 않음
        pass
    chat_repo.delete_all_user_sessions(db, uid)
    # 1:1 상담 PII 즉시 파기(D1) — 대화·명식/타로 스냅샷·요약PDF. 세션·정산 메타는 상담사 정산 보존.
    from backend.app.services import consultation_session_service as _csess
    _csess.purge_user_consultation_pii(db, uid)
    # 업로드(회원 제출) 파일·제출자 이메일(PII) 파기(#6) — 파일 unlink 후 레코드 삭제.
    # (회귀가드) 관리자/코퍼스 예약 카테고리는 파기 제외 — 이메일이 같아도(관리자 자기탈퇴) 코퍼스 원본을 보호.
    #   회원은 제출 경로에서 예약 카테고리를 사칭할 수 없으므로(upload_service 강제치환), 회원 본인 제출은 전부 파기되어 개인정보가 완전 삭제된다.
    from backend.app.services.upload_service import RESERVED_UPLOAD_CATEGORIES as _RESV_CATS, PROJECT_ROOT as _PROOT
    _resv = {f"rc{_i}": _c for _i, _c in enumerate(_RESV_CATS)}
    _resv_ph = ",".join(f":{_k}" for _k in _resv) or "''"   # NOT IN (:rc0,:rc1)
    try:
        for (_sp,) in db.execute(
            _text(f"SELECT stored_path FROM uploads WHERE submitter=:e AND category NOT IN ({_resv_ph})"),
            {"e": user.email, **_resv},
        ).fetchall():
            try:
                # stored_path 는 PROJECT_ROOT 상대경로로 저장됨 — CWD 무관하게 루트 기준으로 resolve(_PROOT/_sp;
                # _sp 가 절대경로면 pathlib 이 그대로 사용). CWD 의존 os.remove 로 조용히 고아가 되는 것을 방지.
                _ap = (_PROOT / _sp) if _sp else None
                if _ap and _ap.is_file():
                    _ap.unlink()
            except OSError:
                pass
    except Exception:  # noqa: BLE001
        pass
    db.execute(
        _text(f"DELETE FROM uploads WHERE submitter=:e AND category NOT IN ({_resv_ph})"),
        {"e": user.email, **_resv},
    )
    for tbl in ("compat_sessions", "tarot_sessions", "tool_sessions", "saju_video_jobs", "saju_profiles"):
        db.execute(_text(f"DELETE FROM {tbl} WHERE user_id=:u"), {"u": uid})
    # 입점 문의(신청 전 게이트) — 계약 전 단계 PII(email·note)라 전량 파기.
    # 이메일 기준도 함께 지워 동일 메일 재가입 계정이 이전 문의·'신청 허용' 자격을 승계하는 것 차단.
    # (입점 '신청서'는 계약 증빙이라 보존 — consultant_applications 모델 주석 참조)
    db.execute(_text("DELETE FROM partner_inquiries WHERE user_id=:u OR lower(email)=lower(:e)"), {"u": uid, "e": user.email})
    # 고객센터 문의 — 레코드 보존, PII만 파기.
    db.execute(_text(
        "UPDATE support_tickets SET contact_email='(파기됨)', contact_name=NULL, message='(회원 탈퇴로 파기됨)' WHERE user_id=:u"
    ), {"u": uid})
    db.delete(user)
    db.commit()


@router.get("/me/export")
def export_my_data(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """정보주체 권리 — 개인정보 이동권/통합 열람(제35조·이동권). 본인 데이터를 기계판독(JSON)으로 반환.

    복호화된 평문으로 제공(본인 데이터). 대화 본문은 용량상 건수만 제공하고, 상세는 각 메뉴 화면에서 열람."""
    from sqlalchemy import select as _sel, text as _text
    from backend.app.repositories.auth_models import SajuProfile as _SP
    import json as _json

    def _cnt(table: str) -> int:
        try:
            return int(db.execute(_text(f"SELECT count(*) FROM {table} WHERE user_id=:u"), {"u": user.id}).scalar() or 0)
        except Exception:  # noqa: BLE001
            return 0

    profiles = [
        {"label": p.label, "birth_date": p.birth_date.isoformat(), "birth_time": p.birth_time,
         "calendar": p.calendar, "gender": p.gender, "birth_longitude": p.birth_longitude}
        for p in db.execute(_sel(_SP).where(_SP.user_id == user.id)).scalars().all()
    ]
    try:
        saju_profile = _json.loads(user.saju_profile) if user.saju_profile else None
    except Exception:  # noqa: BLE001
        saju_profile = None
    return {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "account": {
            "email": user.email, "nickname": user.nickname, "role": user.role,
            "oauth_provider": user.oauth_provider,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        },
        "consents": {
            "terms_version": user.terms_agreed_version, "privacy_version": user.privacy_agreed_version,
            "marketing_opt_in": user.marketing_opt_in,
            "overseas_transfer_opt_in": bool(getattr(user, "overseas_transfer_opt_in", False)),
            "sensitive_consent": bool(getattr(user, "sensitive_consent", False)),
        },
        "balance": svc.get_balance(db, user.id),
        "saju_profiles": profiles,
        "default_saju_profile": saju_profile,
        "activity_counts": {
            "chat_sessions": _cnt("chat_sessions"), "tarot_sessions": _cnt("tarot_sessions"),
            "tool_sessions": _cnt("tool_sessions"), "compat_sessions": _cnt("compat_sessions"),
            "consultation_sessions": _cnt("consultation_sessions"), "payments": _cnt("payments"),
        },
    }


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
        for m in ("compat", "taekil", "jakmyeong", "gaemyeong", "aho", "tarot", "sinnyeon")
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
        overseas_transfer_opt_in=bool(getattr(user, "overseas_transfer_opt_in", False)),
        birth_verified=bool(getattr(user, "birth_date_enc", None)),
        free_used_count=used,
        free_quota_count=free_quota,
        free_remaining=free_remaining,
        credit_cost_basic=settings_service.get_int(db, "credit_cost_basic"),
        credit_cost_deep=settings_service.get_int(db, "credit_cost_deep"),
        preview_reveal_cost=settings_service.get_int(db, "preview_reveal_cost"),
        video_gen_cost=settings_service.get_int(db, "video_gen_cost"),
        amulet_cost_p=settings_service.get_int(db, "amulet_cost_p", 3900),  # DEFAULTS(3900)와 일치 — 3000 은 표시/차감 동시 오류였다
        premium_entry_costs=premium_entry_costs,
        premium_entry_discount_pct=_disc,
        premium_entry_free=premium_entry_free,
        is_member=is_member,
        membership_remaining=membership_remaining,
        membership_quota=membership_quota,
        saju_profile=saju_profile,
        disclaimer_agreed=bool(getattr(user, "disclaimer_agreed_at", None)),
        terms_agreed=bool(getattr(user, "terms_agreed_at", None)),
        active_pass=_active_pass(db, user),
        pass_followup_discount_pct=settings_service.get_int(db, "pass_followup_discount_pct", 30),
    )


def _active_pass(db: Session, user: User) -> "Optional[dict]":
    """B-7 월 패스 상태(지연 갱신 포함) — 실패해도 me 응답을 막지 않음."""
    try:
        from backend.app.services import pass_service
        return pass_service.to_dict(db, pass_service.get_pass(db, user.id))
    except Exception:  # noqa: BLE001
        return None
