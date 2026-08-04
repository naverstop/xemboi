"""인증/회원/크레딧 서비스."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.security import hash_password, verify_password
from backend.app.repositories.auth_models import (
    Credit,
    CreditTransaction,
    User,
)


# -------- 회원 --------

def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.execute(select(User).where(User.email == email.lower())).scalar_one_or_none()


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    return db.get(User, user_id)


def create_user(
    db: Session,
    *,
    email: str,
    password: Optional[str],
    nickname: Optional[str] = None,
    role: str = "user",
    must_change_password: bool = False,
    oauth_provider: Optional[str] = None,
    oauth_id: Optional[str] = None,
) -> User:
    user = User(
        email=email.lower(),
        password_hash=hash_password(password) if password else None,
        nickname=nickname or email.split("@")[0],
        role=role,
        must_change_password=must_change_password,
        oauth_provider=oauth_provider,
        oauth_id=oauth_id,
    )
    db.add(user)
    db.flush()  # id 확보
    # 크레딧 row 생성
    db.add(Credit(user_id=user.id, balance=0))
    db.flush()
    return user


def authenticate(db: Session, email: str, password: str) -> Optional[User]:
    user = get_user_by_email(db, email)
    if not user or not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    user.last_login_at = datetime.utcnow()
    db.flush()
    return user


def change_password(db: Session, user: User, new_password: str) -> None:
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    db.flush()


# -------- 크레딧 --------

def get_balance(db: Session, user_id: int) -> int:
    c = db.get(Credit, user_id)
    return c.balance if c else 0


def adjust_credit(
    db: Session,
    user_id: int,
    delta: int,
    reason: str,
    ref_id: Optional[str] = None,
    idem_key: Optional[str] = None,
) -> int:
    """잔액 조정(원자적). delta는 +충전/-차감. 부족 시 ValueError.

    동시 차감/적립 lost-update·이중차감·음수잔액 방지: read-modify-write 대신 단일
    UPDATE ... WHERE balance+delta>=0 + rowcount 검사. PostgreSQL이 행잠금+EvalPlanQual로
    최신 잔액에 WHERE를 재평가하므로, 동시 요청이 같은 잔액을 두 번 쓰는 일이 없다.

    idem_key 지정 시 멱등: 같은 키의 거래가 이미 있으면 재적용하지 않고 현재 잔액을 그대로 반환한다.
    idem 거래행을 SAVEPOINT 안에서 먼저 선점(부분 UNIQUE 인덱스 ux_credit_tx_idem)하므로, 리컨실 재실행·
    재시도·동시요청이 이중차감/이중환불로 번지지 않는다. (idem_key=None 이면 기존 비멱등 경로 그대로 — 회귀 없음)
    """
    from sqlalchemy import select as _sel, update as _upd
    c = db.get(Credit, user_id)
    if c is None:
        c = Credit(user_id=user_id, balance=0)
        db.add(c)
        db.flush()

    if idem_key is not None:
        from sqlalchemy.exc import IntegrityError
        # 게이트+잔액반영을 하나의 SAVEPOINT 로 원자화 — 유니크 위반=이미 수행됨(no-op),
        #   잔액부족이면 게이트행까지 원복(향후 같은 키 재시도가 유령 no-op 되는 오염 방지).
        sp = db.begin_nested()
        txn = CreditTransaction(
            user_id=user_id, delta=delta, reason=reason, ref_id=ref_id,
            idem_key=idem_key, balance_after=0,   # 게이트 통과 후 실제 잔액으로 갱신
        )
        try:
            db.add(txn)
            db.flush()                    # 중복 idem_key → IntegrityError
        except IntegrityError:
            sp.rollback()
            return db.execute(_sel(Credit.balance).where(Credit.user_id == user_id)).scalar() or 0
        res = db.execute(
            _upd(Credit)
            .where(Credit.user_id == user_id, Credit.balance + delta >= 0)
            .values(balance=Credit.balance + delta, updated_at=datetime.utcnow())
        )
        if res.rowcount == 0:
            sp.rollback()                 # 잔액부족 → 게이트행 원복 후 실패
            cur = db.execute(_sel(Credit.balance).where(Credit.user_id == user_id)).scalar() or 0
            raise ValueError(f"insufficient credits: balance={cur}, delta={delta}")
        db.expire(c)
        new_balance = c.balance
        txn.balance_after = new_balance
        db.flush()
        sp.commit()                       # 게이트행+잔액변경 함께 확정(SAVEPOINT 릴리스)
        return new_balance

    res = db.execute(
        _upd(Credit)
        .where(Credit.user_id == user_id, Credit.balance + delta >= 0)
        .values(balance=Credit.balance + delta, updated_at=datetime.utcnow())
    )
    if res.rowcount == 0:
        # WHERE 불충족 = (차감 시) 잔액 부족 → 음수/이중차감 차단
        cur = db.execute(_sel(Credit.balance).where(Credit.user_id == user_id)).scalar() or 0
        raise ValueError(f"insufficient credits: balance={cur}, delta={delta}")
    db.expire(c)              # 코어 UPDATE는 ORM 캐시 우회 → 무효화해 최신값 재로드
    new_balance = c.balance
    db.add(
        CreditTransaction(
            user_id=user_id,
            delta=delta,
            reason=reason,
            ref_id=ref_id,
            balance_after=new_balance,
        )
    )
    db.flush()
    return new_balance


# -------- 무료질문 정책 --------

def claim_daily_free(db: Session, user: User, today: Optional[date] = None) -> bool:
    """1일 1건 무료 질문을 원자적으로 선점. 성공 True / 이미 소진 False.

    동시요청 lost-update 차단: read-check-set 대신 단일 UPDATE ... WHERE(오늘 미사용).
    PostgreSQL 행잠금으로 동시 두 요청 중 하나만 rowcount==1."""
    from sqlalchemy import update as _upd
    today = today or date.today()
    res = db.execute(
        _upd(User)
        .where(
            User.id == user.id,
            (User.daily_free_used_at.is_(None)) | (User.daily_free_used_at != today),
        )
        .values(daily_free_used_at=today)
    )
    db.expire(user, ["daily_free_used_at"])
    return res.rowcount > 0


def claim_free_quota(db: Session, user: User, quota: int) -> bool:
    """무료 질문 슬롯 1개를 원자적으로 선점(free_used_count+1, used<quota 일 때만).
    동시요청이 같은 used 를 읽어 모두 무료가 되는 lost-update(무료 N회 치팅)를 차단.
    성공 True / 한도 소진 False(→ 호출부는 유료 경로로 폴백)."""
    from sqlalchemy import func as _f, update as _upd
    res = db.execute(
        _upd(User)
        .where(User.id == user.id, _f.coalesce(User.free_used_count, 0) < quota)
        .values(free_used_count=_f.coalesce(User.free_used_count, 0) + 1)
    )
    db.expire(user, ["free_used_count"])
    return res.rowcount > 0


def reset_monthly_free_if_needed(db: Session, user: User) -> None:
    """free_quota_reset='monthly' 전용 — 월이 바뀌면 free_used_count 를 원자적으로 0 리셋(daily 패턴 미러).

    저장된 free_quota_period('YYYY-MM')가 현재 월과 다르면(또는 NULL) 리셋+기간 갱신. 동시요청이 있어도
    단일 UPDATE ... WHERE period<>cur 라 하나만 리셋(rowcount1)하고 나머지는 no-op → lost-update 안전.
    이후 claim_free_quota 가 원자적으로 재선점하므로 '매월 N회' 가 정확히 재부여된다."""
    from datetime import date as _date
    from sqlalchemy import update as _upd, or_ as _or
    cur = _date.today().strftime("%Y-%m")
    db.execute(
        _upd(User)
        .where(User.id == user.id, _or(User.free_quota_period.is_(None), User.free_quota_period != cur))
        .values(free_used_count=0, free_quota_period=cur)
    )
    # rowcount 무관하게 항상 만료 후 재조회 — 동시요청에서 '다른 요청이 이미 리셋'(rowcount0)한 경우에도
    #   세션 캐시가 지난달 stale 값을 들고 있으면 무료가 잘못 차단(402)되므로, 커밋된 최신값을 다시 읽게 한다.
    db.expire(user, ["free_used_count", "free_quota_period"])


def claim_membership_quota(db: Session, user: User, quota: int) -> bool:
    """멤버십(연간) 무과금 슬롯 1개를 원자적으로 선점(membership_used_count+1, used<quota).
    성공 True / 한도 소진 False(→ 호출부는 갱신 유도/차단)."""
    from sqlalchemy import func as _f, update as _upd
    res = db.execute(
        _upd(User)
        .where(User.id == user.id, _f.coalesce(User.membership_used_count, 0) < quota)
        .values(membership_used_count=_f.coalesce(User.membership_used_count, 0) + 1)
    )
    db.expire(user, ["membership_used_count"])
    return res.rowcount > 0


def effective_level(user: Optional[User]) -> int:
    """유저의 유효 회원등급(0~5) 판정(계획 5.1).

    - 비로그인 → 5 (기본/미리보기)
    - user.level 명시값이 있으면 우선
    - admin role → 시드 첫 이메일은 0(시스템관리자), 그 외 admin은 1
    - 그 외 로그인 회원 → 4 (일반회원)
    """
    if user is None:
        return 5
    if user.level is not None:
        return user.level
    if user.role == "admin":
        s = get_settings()
        first_admin = s.admin_emails[0] if s.admin_emails else None
        if first_admin and user.email == first_admin:
            return 0
        return 1
    return 4


def apply_payment_grade(db: Session, user: User, package: Optional[dict]) -> None:
    """유료결제 성공 시 회원등급 승급(계획 5.1).

    - 관리자(role=admin): 등급 변경 없음(결제이력만 기록)
    - 연간 상품(grade=annual): Level2 + 멤버십 만료일 갱신(1년+1개월)
    - 그 외 유료결제: 우수회원(Level3) 승급 + is_premium
    """
    from datetime import timedelta

    now = datetime.utcnow()
    if user.first_paid_at is None:
        user.first_paid_at = now
    if user.role == "admin":
        db.flush()
        return
    s = get_settings()
    grade = (package or {}).get("grade")
    if grade == "annual":
        user.level = 2
        base = (
            user.membership_expires_at
            if (user.membership_expires_at and user.membership_expires_at > now)
            else now
        )
        user.membership_expires_at = base + timedelta(days=s.membership_year_days)
        user.is_premium = True
        # 연간회원 갱신/신규 → 무과금 사용횟수 카운터 리셋(연 1,000회 재부여)
        user.membership_used_count = 0
    else:
        user.is_premium = True
        if user.level is None or user.level > 3:
            user.level = 3
    db.flush()


# -------- 광고 숨김 판정 --------
def is_ads_hidden(db: Session, user: Optional[User]) -> bool:
    """광고 숨김 정책.
    - 비로그인: 노출
    - admin: 숨김
    - 관리자가 User.ads_hidden=True 로 강제 설정: 숨김 (override)
    - 일반 회원 + 잔액 > 0 (유료 포인트 보유): 숨김
    - 그 외: 노출
    """
    if user is None:
        return False
    if user.role == "admin":
        return True
    if bool(user.ads_hidden):
        return True
    # 유료 상위 등급(Level 0~3)은 무광고(계획 N)
    if effective_level(user) <= 3:
        return True
    if get_balance(db, user.id) > 0:
        return True
    # B-7 월 패스(라이트/플러스) 이용 중: 무광고
    try:
        from backend.app.services import pass_service
        if pass_service.get_pass(db, user.id) is not None:
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


# -------- 관리자 시드 --------

def seed_admins(db: Session) -> int:
    """설정 admin_emails 에 대해 신규면 생성, 모두 admin 권한 + 시드 크레딧 보장."""
    s = get_settings()
    created = 0
    if not s.admin_emails:
        import logging
        logging.getLogger("saju.auth").info(
            "admin seeding skipped: ADMIN_EMAILS 미설정(.env 확인)"
        )
        return 0
    for email in s.admin_emails:
        user = get_user_by_email(db, email)
        if user is None:
            if not s.admin_initial_password:
                import logging
                logging.getLogger("saju.auth").warning(
                    "admin %s 생성 건너뜀: ADMIN_INITIAL_PASSWORD 미설정(.env 확인)", email
                )
                continue
            user = create_user(
                db,
                email=email,
                password=s.admin_initial_password,
                role="admin",
                must_change_password=True,
                nickname=email.split("@")[0],
            )
            created += 1
        else:
            if user.role != "admin":
                user.role = "admin"
                db.flush()
        # 잔액이 시드 미만이면 보충
        bal = get_balance(db, user.id)
        if bal < s.admin_seed_credits:
            adjust_credit(
                db,
                user.id,
                s.admin_seed_credits - bal,
                reason="admin_seed",
            )
    # ※ H1 자동강등(허용목록 밖 admin→user)은 제거됨 — 운영자가 관리자 계정을 직접 고정 관리(id 1·2·28·41).
    #   seed_admins 는 '승격/시드'만 하고 기존 role 을 강등하지 않는다(운영자 복원본을 재기동 시 되돌리지 않도록).
    db.commit()
    return created
