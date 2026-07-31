"""RAG 청크 신뢰성 태깅 — 출처 신뢰등급 / 예시명식 / 저품질(OCR 깨짐) 판정.

색인(ingest_rag)과 재태깅(retag_corpus) 양쪽에서 공용으로 쓰여, 검색 단계에서
저신뢰·예시·깨진 청크를 걸러내거나 감점하기 위한 payload 메타를 만든다.

- trust_tier: 1(고전·이론서) / 2(일반·스캔본 기본) / 3(유튜브·카톡 등 비공식)
- is_example: 교재의 '예시 명식'(타인 사주) 청크 → 사주상담 검색 오염 방지용 제외 대상
- low_quality: 한글+한자 비율이 낮은(OCR 깨짐) 청크 → 검색 제외 대상

신뢰등급 규칙은 data/rag/source_tiers.json 으로 조정 가능(하드코딩 최소화).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RULES_PATH = PROJECT_ROOT / "data" / "rag" / "source_tiers.json"

# 출처명(파일 stem) 부분일치 규칙. tier3 우선 적용 후 tier1, 나머지는 default.
_DEFAULT_RULES = {
    # 고전·이론서(권위 높음) — 명리 원전/정통 이론 정리물
    "tier1_patterns": [
        "명리전", "적천수", "자평진전", "자평", "연해자평", "궁통보감", "삼명통회",
        "천간론", "지지론", "월령론", "일주론", "간지총론", "체용", "형상격국",
        "격국", "신살", "용신", "육친", "십성", "조후", "정신",
    ],
    # 비공식·요약(권위 낮음) — 대화/메모/요약
    "tier3_patterns": ["카톡", "대화", "채팅", "메모", "잡담", "톡정리", "요약정리"],
    # tier3 패턴에 걸려도 tier1으로 승격하는 예외 — '카톡정리'는 선생님(현명역학원) 강의
    # 대화 원본으로 매매·취업·승진 관법의 1차 출처(실측: tier3 강등 탓에 관법이 검색에서 밀림).
    "tier1_override_patterns": ["카톡정리"],
    "default_tier": 2,
    "low_quality_threshold": 0.5,  # 한글+한자 비율 미만이면 OCR 깨짐으로 간주
}


@lru_cache(maxsize=1)
def load_tier_rules() -> dict:
    rules = dict(_DEFAULT_RULES)
    if _RULES_PATH.exists():
        try:
            rules.update(json.loads(_RULES_PATH.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 — 규칙 파일 깨져도 기본값으로 동작
            pass
    return rules


def classify_trust_tier(source: str, category: str | None, rules: dict | None = None) -> int:
    """출처 신뢰등급 1/2/3. youtube=3, tier1승격예외 → tier3 패턴=3 → tier1 패턴=1 → 기본(2)."""
    r = rules or load_tier_rules()
    if (category or "") == "youtube":
        return 3
    s = source or ""
    if any(p in s for p in r.get("tier1_override_patterns", [])):
        return 1
    if any(p in s for p in r.get("tier3_patterns", [])):
        return 3
    if any(p in s for p in r.get("tier1_patterns", [])):
        return 1
    return int(r.get("default_tier", 2))


# 예시 명식(타인 사주 사례) 탐지 — 사주상담 검색 오염 방지
_EX_MARKERS = (
    "님 사주", "씨 사주", "예시 사주", "다음 사주", "아래 사주", "사주 예",
    "예를 들", "다음과 같은 사주", "사주를 보면", "사주를 살펴", "위 사주", "사례",
)
_GANJI = set("甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥")


def is_example_chunk(text: str) -> bool:
    """교재의 '예시 명식'(특정 타인 사주를 펼친 사례) 청크면 True.

    예시 마커 + (4주 표기 또는 간지 한자 밀집)일 때만 → 일반 이론 청크 오탐 최소화.
    """
    t = text or ""
    if not any(m in t for m in _EX_MARKERS):
        return False
    has_pillars = ("년주" in t and "월주" in t and "일주" in t)
    hanja = sum(1 for ch in t if ch in _GANJI)
    return has_pillars or hanja >= 8


def korean_ratio(text: str) -> float:
    """한글+한자 문자 비율(0~1). 낮을수록 OCR 깨짐/노이즈."""
    t = text or ""
    n = len(t) or 1
    return len(re.findall(r"[가-힣一-龥]", t)) / n


# 판독불가 OCR 신호(2026-07 전수진단 실측): 손글씨 오인식은 라틴 난수열('PPpopeerpopop…')·
# 기호 연속('++++$++')로, 스캔 인쇄물 오인식(PaddleOCR)은 '단어 파편'(줄당 평균 3~5자,
# '司人가⏎오면⏎촛水로')으로 나타난다. 종전 한글비율 기준만으론 '오인식된 한글'이 통과했다.
_LATIN_RUN_RE = re.compile(r"[A-Za-z]{18,}")
_LATIN_RUN10_RE = re.compile(r"[A-Za-z]{10,}")
_SYMBOL_RUN_RE = re.compile(r"[+$%=~^_]{6,}")


def is_low_quality(text: str, threshold: float | None = None) -> bool:
    """OCR 깨짐 등 저품질 청크면 True(검색 제외 대상)."""
    t = (text or "").strip()
    if len(t) < 50:
        return True
    thr = threshold if threshold is not None else load_tier_rules().get("low_quality_threshold", 0.5)
    if korean_ratio(t) < thr:
        return True
    # 라틴 난수열·기호 연속 — 판독불가 손글씨 OCR (영단어 1개 오탐 방지: 초장문 1회 또는 3회 이상)
    if _LATIN_RUN_RE.search(t) or len(_LATIN_RUN10_RE.findall(t)) >= 3 or _SYMBOL_RUN_RE.search(t):
        return True
    # 단어 파편 — 줄당 평균 글자수가 극단적으로 짧으면 스캔 오인식과 동행(실측 A급 평균 3~5자).
    # 정상 텍스트·유튜브 자막·비전 전사는 줄당 8자 이상이라 걸리지 않는다.
    lines = [ln for ln in t.splitlines() if ln.strip()]
    if len(lines) >= 8 and sum(len(ln) for ln in lines) / len(lines) < 6:
        return True
    return False


def tag_chunk(source: str, category: str | None, text: str, rules: dict | None = None) -> dict:
    """청크 1개의 신뢰성 메타(payload에 병합용)."""
    return {
        "trust_tier": classify_trust_tier(source, category, rules),
        "is_example": is_example_chunk(text),
        "low_quality": is_low_quality(text),
    }
