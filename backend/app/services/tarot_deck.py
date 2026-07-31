"""타로 덱(78장) 정적 데이터 + 스프레드 정의 — 서버 결정 렌더의 단일 소스.

- 카드 데이터: backend/app/data/tarot_deck_kr.json (원본: tarot/assets/tarot_deck_kr.json 복사본).
  {id, code, file, name_en, name_kr, arcana, suit, rank, keywords_up, keywords_rev}
- 카드명·방향·포지션은 서버가 결정해 응답에 포함하고, LLM은 해석 본문만 생성한다(창작 금지).
"""
from __future__ import annotations

import json
import os
import threading
from typing import Any

DECK_SIZE = 78

# 이미지 정적 경로(프론트 dist 에 복사되는 위치) — 응답 image_url 프리픽스
CARD_IMAGE_PREFIX = "/tarot/cards/"

# ── 스프레드 정의(포지션명은 서버가 결정, 응답에 포함) ──
SPREAD_POSITIONS: dict[str, list[str]] = {
    "horseshoe7": ["과거", "현재", "숨은 영향", "장애물", "주변 환경", "조언", "결과"],
    "celtic11": [
        "현재", "장애물", "목표(의식)", "기반(무의식)", "최근 과거", "가까운 미래",
        "나 자신", "주변 환경", "희망과 두려움", "최종 결과", "종합 조언",
    ],
}

SPREAD_LABELS: dict[str, str] = {
    "horseshoe7": "말굽 스프레드(7장)",
    "celtic11": "켈틱 크로스 확장(11장)",
}

# ── 섹션 → 스프레드 매핑(확정 사양) ──
SECTION_SPREAD: dict[str, str] = {
    "love": "horseshoe7",
    "money": "horseshoe7",
    "career": "horseshoe7",
    "study": "horseshoe7",
    "choice": "horseshoe7",
    "life": "celtic11",
}

SECTION_LABELS: dict[str, str] = {
    "love": "연애·재회",
    "money": "금전·재물",
    "career": "직업·사업",
    "study": "학업·시험",
    "choice": "선택의 기로",
    "life": "인생 종합·심층",
}

_DECK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tarot_deck_kr.json"
)

_cards: list[dict[str, Any]] | None = None
_by_id: dict[int, dict[str, Any]] = {}
_by_code: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

# 관리자 편집 오버레이(code -> {keywords_up, keywords_rev, interp_up, interp_rev}).
# tarot_content.refresh_cache 가 DB에서 읽어 set_overrides 로 주입. 비어 있으면 JSON 시드 그대로.
_overrides: dict[str, dict[str, Any]] = {}


def set_overrides(ov: dict[str, dict[str, Any]] | None) -> None:
    """관리자 오버레이 캐시 교체(딕셔너리 참조를 원자적으로 교체 — 스레드 안전)."""
    global _overrides
    _overrides = ov or {}


def _ensure_loaded() -> None:
    global _cards
    if _cards is not None:
        return
    with _lock:
        if _cards is not None:
            return
        with open(_DECK_PATH, encoding="utf-8") as f:
            data = json.load(f)
        cards = data.get("cards") or []
        if len(cards) != DECK_SIZE:
            raise RuntimeError(f"tarot deck must have {DECK_SIZE} cards, got {len(cards)}")
        by_id: dict[int, dict[str, Any]] = {}
        for c in cards:
            by_id[int(c["id"])] = c
        if len(by_id) != DECK_SIZE:
            raise RuntimeError("tarot deck card ids are not unique")
        _by_id.clear()
        _by_id.update(by_id)
        _by_code.clear()
        _by_code.update({str(c["code"]): c for c in cards})
        _cards = cards


def all_cards() -> list[dict[str, Any]]:
    _ensure_loaded()
    return list(_cards or [])


def get_card(card_id: int) -> dict[str, Any]:
    _ensure_loaded()
    return _by_id[int(card_id)]


def card_by_code(code: str) -> dict[str, Any] | None:
    """code(예: major-00)로 기본 카드 조회. 없으면 None."""
    _ensure_loaded()
    return _by_code.get(str(code))


def effective_keywords(code: str, is_reversed: bool) -> list[str]:
    """관리자 오버레이 우선, 없으면 JSON 시드의 방향별 키워드."""
    _ensure_loaded()
    key = "keywords_rev" if is_reversed else "keywords_up"
    o = _overrides.get(str(code))
    if o and o.get(key):
        return [str(k) for k in o[key]]
    c = _by_code.get(str(code))
    return [str(k) for k in (c.get(key) or [])] if c else []


def interp_for(code: str, is_reversed: bool) -> str:
    """카드 code + 방향 → 정통(RWS) 해석 서술. 관리자 오버레이 우선, 없으면 JSON 시드. 없으면 ''.

    _render_spread_for_llm 이 code 로 조회 — 신규 드로우는 물론, 뽑힌 구세션의 cards_json 도
    방향별 해석을 얻는다(덱은 단일 소스이므로 항상 최신·오버레이 반영).
    """
    _ensure_loaded()
    key = "interp_rev" if is_reversed else "interp_up"
    o = _overrides.get(str(code))
    if o and o.get(key):
        return str(o[key])
    c = _by_code.get(str(code))
    return str(c.get(key) or "") if c else ""


def spread_for_section(section: str) -> tuple[str, list[str]]:
    """섹션 → (spread_type, positions). 미지원 섹션이면 ValueError."""
    st = SECTION_SPREAD.get(section)
    if st is None:
        raise ValueError(f"invalid section: {section}")
    return st, list(SPREAD_POSITIONS[st])


def card_payload(position_index: int, position_name: str, card_id: int, is_reversed: bool) -> dict[str, Any]:
    """확정 카드 1장의 응답 페이로드(서버 결정 데이터 — 프론트가 그대로 렌더).

    keywords 는 관리자 오버레이 반영값(신규 드로우 시점 스냅샷). interp 는 저장하지 않고
    _render_spread_for_llm 이 code 로 항상 최신본을 조회한다.
    """
    c = get_card(card_id)
    return {
        "position_index": position_index,
        "position_name": position_name,
        "code": c["code"],
        "name_kr": c["name_kr"],
        "name_en": c["name_en"],
        "orientation": "reversed" if is_reversed else "upright",
        "image_url": f"{CARD_IMAGE_PREFIX}{c['file']}",
        "keywords": effective_keywords(c["code"], is_reversed),
    }
