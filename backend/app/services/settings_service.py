"""관리자 편집형 설정(app_settings) 서비스 — 운영 중 변경 즉시 반영(계획 4.2/4.3).

key-value 를 DB에 저장하고, 프로세스 메모리에 캐시한다. set 시 캐시 무효화.
조회 시 DB에 없으면 DEFAULTS 폴백(+ 일부는 config 값으로 폴백).
"""
from __future__ import annotations

import threading
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.repositories.auth_models import AppSetting

# 설정 키 기본값(문자열로 저장). config 폴백이 있는 키는 _config_fallback 참조.
DEFAULTS: dict[str, str] = {
    "free_quota_count": "3",          # 일반회원(Level4) 무료 질문 횟수
    "free_quota_reset": "none",       # none | daily | monthly
    "credit_cost_basic": "1900",      # 기본 답변 1건 차감 크레딧(시장조사 반영 2026-07-12)
    "credit_cost_deep": "3900",       # 심화(듀얼 LLM) 1건 차감 크레딧
    "preview_reveal_cost": "900",     # 미리보기 전체보기 차감
    "preview_max_chars": "1000",      # 미리보기 표시 글자수(무료/맛보기 분량) — 성격 한 단락이 안 끊기게
    "feedback_reward_pct": "3",       # 피드백(👍/👎) 시 결제액 대비 리워드 적립 비율(%)
    "feedback_reward_daily_cap": "3000",  # 1일 1인 피드백 리워드 상한(P)
    "review_reward_p": "500",         # B-3 후기 승인 시 1회 리워드(P). 0=지급 없음
    "amulet_cost_p": "3900",          # B-4 부적 발행 1회 차감(P). 실패 시 무과금
    # ── B-7 월 패스(포인트 자동차감형, 30일 주기) ──
    "pass_lite_price_p": "3900",      # 라이트: 광고 제거 + 공유쿼터 확대
    "pass_plus_price_p": "9900",      # 플러스: 라이트 전체 + 할인/월 무료질문/월 무료부적
    "pass_share_quota": "20",         # 패스 공유 쿼터(기본 5 → 20)
    # [운영자 결정 2026-07-22 '2안 균형'] 10%·월1회는 체감이 없었다(할인 190P, 혜택가치 5,800P).
    #   30%·월5회로 상향 → 혜택가치 13,400P(패스 9,900P 대비 1.4배). 1안(월10회=22,900P)은 역마진
    #   13,000P라 기각. 값은 관리자 화면에서 즉시 조정 가능(표시 문구도 pass_api 가 함께 따라감).
    "pass_followup_discount_pct": "30",  # 플러스 추가질문 할인 %
    "pass_free_basic_monthly": "5",   # 플러스 월 무료 기본질문 횟수(기본질문 depth=basic 한정)
    "pass_amulet_monthly": "1",       # 플러스 월 무료 부적 횟수
    # ── 마케팅 가격 에이전트(2026-07-13) — 조사 토글. 자동적용은 미구현(승인게이트 필수) ──
    "pricing_survey_enabled": "false",     # 주단위 시장조사·권장가 산출 자동 실행
    "pricing_auto_apply_enabled": "false", # (자리표시자) 완전자동 — 본 차수 미사용, 어떤 코드도 자동적용 안 함
    "external_llm_enabled": "true",   # 듀얼 LLM 2차 보강 사용 여부
    # 로컬 엔진 전체 다운 시 외부(미국) LLM 자동 폴백 — 국외이전 미동의 전송이라 기본 OFF(H4).
    "overseas_llm_fallback_enabled": "false",
    # 영상 내레이션 OpenAI TTS(미국) 허용 여부(⑱). 끄면 edgetts→heami 로컬 폴백으로 국외전송 제거.
    "overseas_tts_allowed": "true",
    # 보관기간 파기(M6/제21조) — 경과 세션·검색로그 자동 삭제(일 단위).
    "session_retention_days": "365",
    "retrieval_log_retention_days": "90",
    "access_log_retention_days": "365",  # 접속기록 IP 보관상한(D9)
    # ── 프리미엄 5개 메뉴 입장료(생성=입장 시 1회 차감). 메뉴별 관리자 설정 → 코드 수정 불필요 ──
    # 시장조사(2026-07-12) 반영 — 커머디티(타로·궁합)는 앱수준↓, 전문(작명·개명)은 가치↑
    "entry_cost_compat": "5900",      # 궁합 입장료
    "entry_cost_taekil": "9900",      # 택일 입장료
    "entry_cost_jakmyeong": "12900",  # 작명 입장료
    "entry_cost_gaemyeong": "12900",  # 개명 입장료
    "entry_cost_aho": "6900",         # 아호 입장료
    "entry_cost_tarot": "4900",       # 타로 입장료
    "entry_cost_sinnyeon": "9900",    # B-1 신년운세 입장료
    "premium_entry_discount_pct": "0",  # 5개 메뉴 공통 행사 할인 %(0~100). 50 입력 시 반값
    # ── 사주 답변 → 1분 쇼츠 영상(부록 C). 전부 관리자 즉시 조정 ──
    "video_gen_cost": "2900",         # '영상으로 보기' 클릭 즉시 차감 P
    "shorts_video_seconds": "90",     # 출력 길이(품질>시간, 60~120 허용)
    "shorts_video_seconds_max": "120", # 상한
    "shorts_aspect": "9x16",          # 9x16 | 16x9
    "shorts_encoder_mode": "cpu",     # cpu(libx264) | nvenc | auto(VRAM 게이팅)
    "shorts_gpu_index": "1",          # 사주 자원 GPU = GPU1(+CPU). GPU0은 타 서비스 전용(충돌 방지)
    "shorts_nvenc_vram_gate_mb": "3000",  # auto/nvenc 시 GPU{shorts_gpu_index} free 임계
    "shorts_max_concurrency": "1",    # 동시 렌더(증설 시 ↑, RAM 상한 3)
    "shorts_master_cq": "20",         # 4K hevc 마스터 품질(낮을수록 고품질)
    "shorts_tts_engine": "openai",    # openai(gpt-4o-mini-tts·자연/감정·기본) | edgetts | heami(로컬폴백)
    "shorts_retention_hours": "48",   # 보관 시간(이후 실삭제)
    "shorts_renderer": "talk",        # talk(말하는 flap·기본) | code(코드그래픽) | flux(스틸)
    "shorts_bgm": "none",             # none(무음·현행) | auto(분위기 자동매칭) | 파일명(assets/bgm/)
    "shorts_credit": "orion0321@gmail.com",  # 음원·영상 출처(메타데이터 artist/copyright)
    # ── 1:1 인적 상담(입점업체) 전역 기본값 — 상담사별 미설정 시 폴백. [[consultation-1on1-plan]] ──
    "consultation_default_price_p": "59000",     # 회당 기본 단가(P) — 시장 진입가 30분 60,000 정렬
    "consultation_default_duration_min": "30",   # 기본 상담 시간(분)
    "consultation_min_price_p": "0",             # 상담사 자율요금 하한(1회 블록 환산가 기준). 0=제한 없음
    "consultation_commission_pct": "20",         # 플랫폼 수수료(%) — 정산 산출
    "consultation_tax_pct": "3.3",               # 프리랜서 원천징수(%) — 정산 산출
    "consultation_no_show_timeout_sec": "120",   # 상담사 미수락 시 자동취소·전액환불(초)
    "consultation_extend_warn_sec": "120",       # 블록 종료 N초 전 연장 경고
    "consultation_retention_days": "7",          # 대화/요약PDF 보관 후 완전파기(일)
    # A-2 예약 상담 — 선결제(홀드) 취소·노쇼 정책
    "consultation_reserve_full_refund_hours": "24",  # 시작 N시간 전 취소 = 100% 환불
    "consultation_reserve_late_refund_pct": "50",    # N시간 이내 취소 = M% 환불
    "consultation_reserve_grace_min": "10",          # 전환 후 상담사 미수락 유예(분) — 초과 시 노쇼·전액환불
    # ── 사업자(통신판매업자) 정보 — 전자상거래법 §13. 관리자 입력 → 약관/푸터에 노출 ──
    "service_name": "",          # 서비스명(비우면 프론트 기본 '인생상담 친구')
    "biz_name": "",              # 상호
    "biz_ceo": "",               # 대표자
    "biz_reg_no": "",            # 사업자등록번호
    "biz_mailorder_no": "",      # 통신판매업 신고번호
    "biz_address": "",           # 사업장 소재지
    "biz_tel": "",               # 고객센터 전화
    "biz_hours": "",             # 고객센터 운영시간
    "biz_email": "",             # 고객문의·개인정보 이메일
    "biz_privacy_officer": "",   # 개인정보 보호책임자
    "biz_hosting": "",           # 호스팅 제공자
    # ── 약관 버전·연령(비우면 config 폴백) ──
    "terms_version": "",
    "privacy_version": "",
    "refund_version": "",
    "min_age_years": "",
    # ── 약관 본문 덮어쓰기(Markdown). 비우면 기본 구조화 문안 사용 ──
    "legal_body_terms": "",
    "legal_body_privacy": "",
    "legal_body_refund": "",
    "legal_body_disclaimer": "",
    # ── 고객센터 알림 메일(SMTP). 비우면 config(.env) 값 폴백 ──
    "smtp_enabled": "",          # "true"/"false" (비우면 config)
    "smtp_host": "",
    "smtp_port": "",
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from": "",
    "smtp_use_tls": "",          # "true"/"false" (비우면 config)
}

# 공개(비관리자)로 노출해도 되는 키 — SMTP/비밀번호는 절대 제외.
PUBLIC_SITE_KEYS = (
    "service_name", "biz_name", "biz_ceo", "biz_reg_no", "biz_mailorder_no",
    "biz_address", "biz_tel", "biz_hours", "biz_email", "biz_privacy_officer", "biz_hosting",
    "terms_version", "privacy_version", "refund_version", "min_age_years",
    "legal_body_terms", "legal_body_privacy", "legal_body_refund", "legal_body_disclaimer",
)
# 관리자 운영설정 화면에서 편집 가능한 전체 키(SMTP 포함)
SITE_SETTING_KEYS = PUBLIC_SITE_KEYS + (
    "smtp_enabled", "smtp_host", "smtp_port", "smtp_user", "smtp_password",
    "smtp_from", "smtp_use_tls",
)

# 조회 응답에서 평문 노출 금지(마스킹) 대상 시크릿 키. 실제 값은 get_smtp_config 가 캐시/DB 에서
# 직접 읽으므로 발송 동작에는 영향 없음. 저장(set_many) 시 MASKED_VALUE 는 무시해 원값을 보존한다.
_SECRET_KEYS = frozenset({"smtp_password"})
MASKED_VALUE = "********"


def mask_secrets(d: dict[str, Any]) -> dict[str, Any]:
    """설정 dict 사본에서 시크릿 키의 '설정된' 값을 마스킹(빈 값은 빈 값 유지)."""
    out = dict(d)
    for k in _SECRET_KEYS:
        if out.get(k):
            out[k] = MASKED_VALUE
    return out

# 정수형 키(get_int 캐스팅 대상)
_INT_KEYS = {
    "free_quota_count", "credit_cost_basic", "credit_cost_deep", "preview_reveal_cost",
    "preview_max_chars", "feedback_reward_pct", "feedback_reward_daily_cap", "review_reward_p", "amulet_cost_p",
    "pass_lite_price_p", "pass_plus_price_p", "pass_share_quota", "pass_followup_discount_pct",
    "pass_free_basic_monthly", "pass_amulet_monthly",
    "entry_cost_compat", "entry_cost_taekil", "entry_cost_jakmyeong",
    "entry_cost_gaemyeong", "entry_cost_aho", "entry_cost_tarot", "entry_cost_sinnyeon", "premium_entry_discount_pct",
    "video_gen_cost", "shorts_video_seconds", "shorts_video_seconds_max",
    "shorts_nvenc_vram_gate_mb", "shorts_max_concurrency", "shorts_master_cq",
    "shorts_retention_hours", "shorts_gpu_index",
    "consultation_default_price_p", "consultation_default_duration_min",
    "consultation_min_price_p",
    "consultation_commission_pct", "consultation_no_show_timeout_sec",
    "consultation_extend_warn_sec", "consultation_retention_days",
    "consultation_reserve_full_refund_hours", "consultation_reserve_late_refund_pct",
    "consultation_reserve_grace_min",
    "session_retention_days", "retrieval_log_retention_days", "access_log_retention_days",
}
# 실수형 키(get_float 캐스팅 대상) — 세율 등 소수점 필요
_FLOAT_KEYS = {"consultation_tax_pct"}
_BOOL_KEYS = {"external_llm_enabled", "overseas_llm_fallback_enabled", "overseas_tts_allowed",
              "pricing_survey_enabled", "pricing_auto_apply_enabled"}

_cache: dict[str, str] = {}
_cache_loaded = False
_cache_at = 0.0
_lock = threading.Lock()
# 캐시 TTL — 각 프로세스가 최대 이 초 후 DB를 재조회한다. 같은 프로세스 내 set_many→invalidate()는
# 즉시 무효화하지만, 다른 프로세스(:8010 상담 워커·영상 워커)는 자기 캐시를 모르므로 TTL로 전파한다.
# (예: 관리자 상담설정 변경이 상담 워커에 최대 _CACHE_TTL 초 안에 반영됨 — 재시작 불필요.)
_CACHE_TTL = 20.0


def _load(db: Session) -> None:
    global _cache_loaded, _cache_at
    rows = db.execute(select(AppSetting)).scalars().all()
    _cache.clear()
    for r in rows:
        _cache[r.key] = r.value
    _cache_loaded = True
    _cache_at = time.monotonic()


def _fresh() -> bool:
    return _cache_loaded and (time.monotonic() - _cache_at) <= _CACHE_TTL


def _ensure_loaded(db: Session) -> None:
    if _fresh():
        return
    with _lock:
        if _fresh():
            return
        _load(db)


def invalidate() -> None:
    global _cache_loaded
    with _lock:
        _cache.clear()
        _cache_loaded = False


def get(db: Session, key: str, default: str | None = None) -> str:
    _ensure_loaded(db)
    if key in _cache:
        return _cache[key]
    if default is not None:
        return default
    return DEFAULTS.get(key, "")


def get_int(db: Session, key: str, default: int | None = None) -> int:
    raw = get(db, key, None if default is None else str(default))
    try:
        return int(str(raw).strip())
    except (ValueError, TypeError):
        if default is not None:
            return default
        return int(DEFAULTS.get(key, "0") or 0)


def get_float(db: Session, key: str, default: float | None = None) -> float:
    raw = get(db, key, None if default is None else str(default))
    try:
        return float(str(raw).strip())
    except (ValueError, TypeError):
        if default is not None:
            return default
        try:
            return float(DEFAULTS.get(key, "0") or 0)
        except (ValueError, TypeError):
            return 0.0


def get_cached_int(key: str, default: int) -> int:
    """db 없이 캐시에서 정수 설정 읽기 — 요청 흐름상 캐시는 이미 로드됨(_decide_billing 등이 선조회).
    미로드/미설정이면 default(주로 config 값). _make_preview 등 db 없는 함수용."""
    raw = _cache.get(key)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except (ValueError, TypeError):
        return default


def get_bool(db: Session, key: str, default: bool = False) -> bool:
    raw = get(db, key, str(default).lower())
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def get_cached_bool(key: str, default: bool) -> bool:
    """db 없이 캐시에서 bool 설정 읽기(요청 흐름상 캐시 선로드됨). 미로드/미설정이면 default."""
    raw = _cache.get(key)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def get_all(db: Session) -> dict[str, Any]:
    """현재 유효 설정(기본값 병합) 반환 — 관리자 화면용."""
    _ensure_loaded(db)
    out: dict[str, Any] = dict(DEFAULTS)
    out.update(_cache)
    # 정수형은 int 로 캐스팅해 반환
    for k in _INT_KEYS:
        if k in out:
            try:
                out[k] = int(str(out[k]).strip())
            except (ValueError, TypeError):
                pass
    # 실수형은 float 로 캐스팅해 반환
    for k in _FLOAT_KEYS:
        if k in out:
            try:
                out[k] = float(str(out[k]).strip())
            except (ValueError, TypeError):
                pass
    # 불리언형은 bool 로 캐스팅해 반환
    for k in _BOOL_KEYS:
        if k in out:
            out[k] = str(out[k]).strip().lower() in ("true", "1", "yes", "on")
    return out


def get_site_settings(db: Session) -> dict[str, str]:
    """관리자 운영설정 화면용 — 사업자/약관/SMTP 키 현재값(문자열)."""
    _ensure_loaded(db)
    return {k: _cache.get(k, DEFAULTS.get(k, "")) for k in SITE_SETTING_KEYS}


def get_public_site(db: Session) -> dict[str, str]:
    """공개(약관 페이지/푸터) 노출용 — SMTP·비밀번호 제외."""
    _ensure_loaded(db)
    return {k: _cache.get(k, DEFAULTS.get(k, "")) for k in PUBLIC_SITE_KEYS}


def get_smtp_config(db: Session) -> dict[str, Any]:
    """SMTP 설정 — DB(app_settings) 값 우선, 비어 있으면 config(.env) 폴백."""
    from backend.app.core.config import get_settings as _gs
    s = _gs()

    def _s(key: str, fb: str) -> str:
        v = get(db, key, "")
        return v if (v is not None and str(v).strip() != "") else fb

    def _b(key: str, fb: bool) -> bool:
        v = get(db, key, "")
        if v is None or str(v).strip() == "":
            return fb
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    def _i(key: str, fb: int) -> int:
        v = get(db, key, "")
        try:
            return int(str(v).strip())
        except (ValueError, TypeError):
            return fb

    return {
        "enabled": _b("smtp_enabled", s.smtp_enabled),
        "host": _s("smtp_host", s.smtp_host),
        "port": _i("smtp_port", s.smtp_port),
        "user": _s("smtp_user", s.smtp_user),
        "password": _s("smtp_password", s.smtp_password),
        "from": _s("smtp_from", s.smtp_from),
        "use_tls": _b("smtp_use_tls", s.smtp_use_tls),
    }


def set_many(db: Session, items: dict[str, Any]) -> dict[str, Any]:
    """여러 설정 upsert. 알 수 없는 키는 무시. 변경 후 캐시 무효화."""
    for key, value in items.items():
        if value is None:
            continue
        if key not in DEFAULTS:
            continue
        # 마스킹된 시크릿(변경 안 함)은 저장하지 않음 — 폼을 그대로 저장해도 원 비밀번호가 덮이지 않게.
        if key in _SECRET_KEYS and str(value) == MASKED_VALUE:
            continue
        sval = str(value)
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=sval))
        else:
            row.value = sval
    db.commit()
    invalidate()
    return get_all(db)


def seed_defaults(db: Session) -> None:
    """없는 키만 기본값으로 1회 시드(멱등)."""
    have = {r.key for r in db.execute(select(AppSetting)).scalars().all()}
    changed = False
    for key, val in DEFAULTS.items():
        if key not in have:
            db.add(AppSetting(key=key, value=val))
            changed = True
    if changed:
        db.commit()
        invalidate()
