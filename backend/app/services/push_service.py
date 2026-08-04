"""Web Push 발송 서비스 (PWA, 계획 2.7.6).

- pywebpush 로 VAPID 서명 발송. 미설치/키 미설정 시 graceful no-op.
- 오늘의 운세 데일리 푸시(7-D.2)·재방문 유도에서 사용.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.repositories.auth_models import PushSubscription

log = logging.getLogger("saju.push")

try:  # pywebpush 는 선택적 의존성
    from pywebpush import WebPushException, webpush  # type: ignore

    _HAS_WEBPUSH = True
except Exception:  # noqa: BLE001
    webpush = None  # type: ignore
    WebPushException = Exception  # type: ignore
    _HAS_WEBPUSH = False


def is_enabled() -> bool:
    s = get_settings()
    return bool(_HAS_WEBPUSH and s.vapid_public_key and s.vapid_private_key)


def save_subscription(
    db: Session, user_id: Optional[int], endpoint: str, p256dh: str, auth: str
) -> PushSubscription:
    """동일 endpoint 면 갱신(upsert), 아니면 신규 저장."""
    existing = db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == endpoint)
    ).scalar_one_or_none()
    if existing:
        existing.user_id = user_id
        existing.p256dh = p256dh
        existing.auth = auth
        db.commit()
        db.refresh(existing)
        return existing
    sub = PushSubscription(
        user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def remove_subscription(db: Session, endpoint: str) -> None:
    db.execute(delete(PushSubscription).where(PushSubscription.endpoint == endpoint))
    db.commit()


def _send_one(sub: PushSubscription, payload: dict[str, Any]) -> bool:
    s = get_settings()
    try:
        webpush(  # type: ignore[misc]
            subscription_info={
                "endpoint": sub.endpoint,
                "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=s.vapid_private_key,
            vapid_claims={"sub": s.vapid_subject},
        )
        return True
    except WebPushException as e:  # type: ignore[misc]
        # 410 Gone / 404 → 만료 구독으로 간주 (호출측에서 정리)
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in (404, 410):
            return False
        log.warning("webpush send failed: %s", e)
        return False
    except Exception as e:  # noqa: BLE001
        log.warning("webpush error: %s", e)
        return False


def send_to_user(
    db: Session, user_id: int, title: str, body: str, url: str = "/chat",
    tag: str | None = None,
) -> int:
    """특정 사용자의 모든 구독에 발송. 발송 성공 개수 반환.
    tag를 주면 SW가 같은 태그 알림을 갱신(renotify) — 반복 알림이 쌓이지 않으면서 매번 소리/진동."""
    if not is_enabled():
        return 0
    subs = db.execute(
        select(PushSubscription).where(PushSubscription.user_id == user_id)
    ).scalars().all()
    payload = {"title": title, "body": body, "url": url}
    if tag:
        payload["tag"] = tag
    sent = 0
    stale: list[str] = []
    for sub in subs:
        ok = _send_one(sub, payload)
        if ok:
            sub.last_sent_at = datetime.utcnow()
            sent += 1
        else:
            stale.append(sub.endpoint)
    for ep in stale:
        remove_subscription(db, ep)
    if sent:
        db.commit()
    return sent


def _deliver(db: Session, subs: list[PushSubscription], title: str, body: str, url: str = "/chat") -> int:
    """주어진 구독 목록에 발송(공용 루프). 만료 구독 정리 포함. 발송 성공 개수 반환."""
    if not is_enabled() or not subs:
        return 0
    payload = {"title": title, "body": body, "url": url}
    sent = 0
    stale: list[str] = []
    for sub in subs:
        ok = _send_one(sub, payload)
        if ok:
            sub.last_sent_at = datetime.utcnow()
            sent += 1
        else:
            stale.append(sub.endpoint)
    for ep in stale:
        remove_subscription(db, ep)
    if sent:
        db.commit()
    return sent


def broadcast(db: Session, title: str, body: str, url: str = "/chat") -> int:
    """전체 구독에 발송. 발송 성공 개수 반환.

    ※ 광고성(영리목적) 데일리 푸시는 broadcast 가 아니라 marketing_subscriptions()
      로 '마케팅 수신 동의' 회원만 대상으로 발송해야 한다(정보통신망법 §50). broadcast 는
      서비스 공지 등 비광고성 전체발송 용도로만 사용할 것.
    """
    if not is_enabled():
        return 0
    subs = db.execute(select(PushSubscription)).scalars().all()
    return _deliver(db, list(subs), title, body, url)


def marketing_subscriptions(db: Session) -> list[PushSubscription]:
    """마케팅 수신 동의(marketing_opt_in=True) 회원의 구독만 반환.

    '오늘의 운세/일진' 등 영리목적 광고성 데일리 푸시(정보통신망법 §50)의 발송 대상.
    비로그인(user_id=None) 구독은 동의 근거가 없어 제외한다.
    """
    from backend.app.repositories.auth_models import User

    rows = db.execute(
        select(PushSubscription)
        .join(User, User.id == PushSubscription.user_id)
        .where(User.marketing_opt_in.is_(True))
    ).scalars().all()
    return list(rows)


# -------- 오늘의 운세 데일리 푸시(계획 7-D.2) --------

_FORTUNE_LINES = [
    "오늘은 귀인을 만날 운이 좋은 날이에요. 먼저 인사를 건네보세요.",
    "재물의 기운이 들어옵니다. 작은 기회를 흘리지 마세요.",
    "마음이 분주한 날, 깊게 호흡하고 한 가지에 집중하면 길합니다.",
    "인연이 닿는 하루입니다. 오래 미룬 연락을 해보세요.",
    "건강을 챙기면 만사가 순조롭습니다. 가벼운 산책이 약이 됩니다.",
    "결단의 기운이 강한 날, 미뤄둔 선택을 마무리하기 좋습니다.",
    "주변의 도움이 들어옵니다. 혼자 끙끙대지 말고 청해보세요.",
]


def daily_fortune_message(today: Optional[Any] = None) -> str:
    """날짜 기반 결정적(deterministic) 한 줄 운세."""
    from datetime import date as _date

    d = today or _date.today()
    idx = (d.toordinal()) % len(_FORTUNE_LINES)
    return _FORTUNE_LINES[idx]


def send_daily_fortune(db: Session) -> int:
    """마케팅 수신 동의 구독자에게 오늘의 운세 1줄 발송(정보통신망법 §50). 설정/키 미충족 시 0 반환."""
    s = get_settings()
    if not s.daily_fortune_enabled or not is_enabled():
        return 0
    return _deliver(db, marketing_subscriptions(db), "오늘의 운세 🔮", daily_fortune_message(), url="/today")


# -------- 개인화 일진 데일리 푸시(#4) --------
# 십성(十星) 본질 의미 기반의 정직한 한 줄. '오늘 ~일이 생긴다'식 단정/허구는 배제.
_ILJIN_LINES: dict[str, str] = {
    "比肩": "경쟁·자립의 기운. 동료와 협력은 득, 무리한 지출은 절제하세요.",
    "劫財": "추진·경쟁의 기운. 과감하되 금전 다툼·충동 지출은 주의하세요.",
    "食神": "여유·표현·먹복의 기운. 즐기며 꾸준히 하기 좋은 날입니다.",
    "傷官": "재능·말의 기운. 창의적 표현엔 길하나 구설·말실수는 주의하세요.",
    "偏財": "활동·기회·재물의 기운. 적극적 활동은 길, 충동 투자는 주의하세요.",
    "正財": "성실·실리의 기운. 꾸준함이 결실로 이어지는 날입니다.",
    "偏官": "결단·도전의 기운. 과감하되 무리·다툼은 삼가세요.",
    "正官": "책임·명예·질서의 기운. 공적인 일·약속에 길한 날입니다.",
    "偏印": "직관·학습·변화의 기운. 새 지식·아이디어를 살리기 좋습니다.",
    "正印": "귀인·문서·안정의 기운. 공부·계약·도움에 길한 날입니다.",
}

# saju_profile(저장된 본인 사주) 에서 BirthInput 으로 넘길 수 있는 키만 추림.
_BIRTH_KEYS = (
    "birth_date", "birth_time", "calendar", "is_leap_month", "gender",
    "apply_true_solar_time", "birth_longitude", "apply_equation_of_time", "night_zi_mode",
)


def build_personal_iljin(profile: dict[str, Any], today: Optional[Any] = None) -> Optional[tuple[str, str]]:
    """저장된 본인 사주(profile)와 오늘 날짜로 개인화 일진 메시지(제목, 본문)를 만든다.

    - 일진 간지: 오늘(양력) 일주(엔진 산출).
    - 십성: 본인 일간 기준 오늘 일간의 십성(엔진 산출).
    - 충/합: 본인 일지와 오늘 일지의 지지충/육합(엔진 상수).
    파싱/계산 실패 시 None.
    """
    from datetime import date as _date
    from backend.app.saju.pillars import compute_pillars
    from backend.app.saju.types import BirthInput
    from backend.app.saju.constants import (
        compute_ten_god, TEN_GODS_KO, stem_korean, branch_korean,
        BRANCH_CONFLICTS, BRANCH_SIX_COMBINATIONS,
    )
    try:
        d = today or _date.today()
        kw = {k: profile[k] for k in _BIRTH_KEYS if profile.get(k) is not None}
        user_birth = BirthInput(**kw)
        user_fp, *_ = compute_pillars(user_birth)
        today_fp, *_ = compute_pillars(BirthInput(birth_date=d))
        u_stem = user_fp.day.stem
        u_branch = user_fp.day.branch
        t_stem = today_fp.day.stem
        t_branch = today_fp.day.branch
        tg = compute_ten_god(u_stem, t_stem)             # 본인 일간 기준 오늘 일간의 십성
        tg_ko = TEN_GODS_KO.get(tg, tg)
        line = _ILJIN_LINES.get(tg, "")
        # 충/합 부가 노트(본인 일지 ↔ 오늘 일지)
        pair = frozenset({u_branch, t_branch})
        note = ""
        if u_branch != t_branch and pair in BRANCH_CONFLICTS:
            note = " ※ 오늘 일지가 본인 일지를 충(沖) — 변동·이동수, 신중히."
        elif u_branch != t_branch and pair in BRANCH_SIX_COMBINATIONS:
            note = " ※ 오늘 일지가 본인 일지와 합(合) — 인연·협조의 기운."
        today_gz = f"{stem_korean(t_stem)}{branch_korean(t_branch)}({t_stem}{t_branch})"
        title = "오늘의 일진 🗓"
        body = (
            f"{d.isoformat()} 일진 {today_gz}. "
            f"본인 일간 {stem_korean(u_stem)}({u_stem}) 기준 오늘은 '{tg_ko}'의 기운 — {line}{note}"
        )
        return title, body
    except Exception as e:  # noqa: BLE001
        log.warning("build_personal_iljin failed: %s", e)
        return None


def send_daily_iljin(db: Session) -> int:
    """마케팅 수신 동의 구독자별 발송: saju_profile 보유자는 개인화 일진, 미보유자는 일반 운세.

    광고성 데일리 푸시라 marketing_opt_in=True 회원만 대상(정보통신망법 §50).
    구독은 user_id 로 묶이며, 동일 사용자의 여러 기기에 모두 발송.
    설정(daily_iljin_enabled)·키 미충족 시 0 반환(일반 운세는 호출측에서 처리).
    """
    import json as _json
    s = get_settings()
    if not s.daily_iljin_enabled or not is_enabled():
        return 0
    from backend.app.repositories.auth_models import User

    # 광고성 데일리 푸시 → 마케팅 수신 동의 회원만(정보통신망법 §50)
    subs = marketing_subscriptions(db)
    if not subs:
        return 0
    # user_id → saju_profile(dict|None) 캐시
    prof_cache: dict[int, Optional[dict]] = {}

    def _profile_for(uid: Optional[int]) -> Optional[dict]:
        if uid is None:
            return None
        if uid in prof_cache:
            return prof_cache[uid]
        u = db.get(User, uid)
        raw = getattr(u, "saju_profile", None) if u else None
        parsed = None
        if raw:
            try:
                parsed = _json.loads(raw)
            except Exception:  # noqa: BLE001
                parsed = None
        prof_cache[uid] = parsed
        return parsed

    generic_title, generic_body = "오늘의 운세 🔮", daily_fortune_message()
    sent = 0
    stale: list[str] = []
    # user_id별 일진 메시지 캐시(동일 사용자 다기기 중복 계산 방지)
    msg_cache: dict[int, tuple[str, str]] = {}
    for sub in subs:
        prof = _profile_for(sub.user_id)
        if prof and sub.user_id is not None:
            if sub.user_id in msg_cache:
                title, body = msg_cache[sub.user_id]
            else:
                built = build_personal_iljin(prof)
                title, body = built or (generic_title, generic_body)
                msg_cache[sub.user_id] = (title, body)
        else:
            title, body = generic_title, generic_body
        ok = _send_one(sub, {"title": title, "body": body, "url": "/today"})  # B-2 오늘의 운세 페이지 랜딩
        if ok:
            sub.last_sent_at = datetime.utcnow()
            sent += 1
        else:
            stale.append(sub.endpoint)
    for ep in stale:
        remove_subscription(db, ep)
    if sent:
        db.commit()
    return sent
