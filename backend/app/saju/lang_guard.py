"""로케일별 언어 충실도 가드 + 응답언어 지시 — 순수 모듈(무거운 의존 0, 단위검증 가능).

Qwen 계열(중국권 모델)은 한자 많은 컨텍스트에서 간체/번체로 드리프트한다. chat_service 는
로컬 LLM 출력이 '목표 언어인지' 검증해 통과 시에만 채택한다. 로케일별로 판정을 달리한다:
  - ko: 한글 본문 + 한자 술어 병기 허용(한자 ≤ 한글×0.5). 기존 _looks_korean_clean 동치.
  - vi: 라틴(성조부호) 본문. 한자(Hán tự) 1자라도 있으면 폐기(중국어 드리프트). 순 ASCII도 폐기.
"""
from __future__ import annotations

import re
from typing import Callable

_HANGUL_RE = re.compile(r"[가-힣]")
_HANJA_RE = re.compile(r"[一-鿿]")


def _has_replacement_or_surrogate(text: str) -> bool:
    if "�" in text:
        return True
    return any(0xDC80 <= ord(c) <= 0xDCFF for c in text)


def looks_korean_clean(text: str) -> bool:
    """ko: 깨지지 않은 한국어 본문인지. chat_service._looks_korean_clean 과 동일 규칙."""
    if not text or not text.strip():
        return False
    if _has_replacement_or_surrogate(text):
        return False
    hangul = len(_HANGUL_RE.findall(text))
    hanja = len(_HANJA_RE.findall(text))
    if hangul < 20:
        return False
    if hanja > hangul * 0.5:   # 한자 과다 = 중국어 드리프트
        return False
    return True


def _is_viet_diacritic(c: str) -> bool:
    """베트남어 성조/모음 부호(Latin-1 Supplement · Extended-A/B · Extended Additional)."""
    o = ord(c)
    if o in (0x00D7, 0x00F7):   # × ÷ 제외
        return False
    return (0x00C0 <= o <= 0x024F) or (0x1E00 <= o <= 0x1EFF)


def looks_vietnamese_clean(text: str) -> bool:
    """vi: 라틴(성조부호) 본문인지. 한자 드리프트·순ASCII·깨짐을 폐기."""
    if not text or not text.strip():
        return False
    if _has_replacement_or_surrogate(text):
        return False
    # vi 는 라틴 전용 — 한자(Hán tự)가 하나라도 있으면 중국어 드리프트로 폐기(ko 보다 엄격)
    if _HANJA_RE.search(text):
        return False
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    if latin < 20:
        return False
    # 성조부호가 거의 없으면 순 ASCII(영어/병음) 드리프트로 간주해 폐기
    diacritics = sum(1 for c in text if _is_viet_diacritic(c))
    if diacritics < 3:
        return False
    return True


def clean_guard(locale: str) -> Callable[[str], bool]:
    """로케일별 언어 충실도 판정 함수 반환."""
    return looks_vietnamese_clean if locale == "vi" else looks_korean_clean


# 산재하던 14곳의 '한국어로만/중국어 금지' 지시를 로케일 단일 규칙으로 대체.
RESPONSE_LANGUAGE_RULE: dict[str, str] = {
    "ko": (
        "한국어로만 작성하세요. 한자 술어는 한글(한자) 병기만 허용합니다(예: 정관(正官), 비견(比肩)). "
        "중국어(간체/번체) 문장·단어를 절대 쓰지 마세요."
    ),
    "vi": (
        "Chỉ viết bằng tiếng Việt (chữ Quốc ngữ có dấu thanh). Dùng Hán-Việt Latinh cho thuật ngữ "
        "(Giáp Tý, Chính quan, Ngũ hành, Đại vận), TUYỆT ĐỐI không dùng chữ Hán / tiếng Trung."
    ),
}


def response_language_rule(locale: str) -> str:
    return RESPONSE_LANGUAGE_RULE.get(locale, RESPONSE_LANGUAGE_RULE["ko"])
