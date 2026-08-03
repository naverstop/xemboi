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

# ── 베트남어(vi) 포지션명 — SPREAD_POSITIONS 미러(같은 순서·길이). vi 세션 렌더용 ──
SPREAD_POSITIONS_VI: dict[str, list[str]] = {
    "horseshoe7": [
        "Quá khứ", "Hiện tại", "Ảnh hưởng ẩn", "Trở ngại",
        "Môi trường xung quanh", "Lời khuyên", "Kết quả",
    ],
    "celtic11": [
        "Hiện tại", "Trở ngại", "Mục tiêu (ý thức)", "Nền tảng (tiềm thức)",
        "Quá khứ gần", "Tương lai gần", "Bản thân", "Môi trường xung quanh",
        "Hy vọng và nỗi sợ", "Kết quả cuối cùng", "Lời khuyên tổng hợp",
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

# ── 베트남어(vi) 카드명(code → name_vi) — 78장 전수 ──
# 널리 통용되는 베트남 타로 명칭. 덱 JSON(name_kr/name_en)의 vi 대응(단일 소스).
# 마이너: 슈트 Gậy(완드)·Cốc(컵)·Kiếm(소드)·Tiền(펜타클),
#         궁정 Tiểu Đồng(시종)·Hiệp Sĩ(기사)·Hoàng Hậu(여왕)·Vua(왕).
CARD_NAME_VI: dict[str, str] = {
    # Major Arcana (0–21)
    "major-00": "Chàng Khờ",
    "major-01": "Nhà Ảo Thuật",
    "major-02": "Nữ Tư Tế",
    "major-03": "Nữ Hoàng",
    "major-04": "Hoàng Đế",
    "major-05": "Giáo Hoàng",
    "major-06": "Tình Nhân",
    "major-07": "Cỗ Xe",
    "major-08": "Sức Mạnh",
    "major-09": "Ẩn Sĩ",
    "major-10": "Bánh Xe Số Phận",
    "major-11": "Công Lý",
    "major-12": "Người Treo Ngược",
    "major-13": "Cái Chết",
    "major-14": "Điều Độ",
    "major-15": "Ác Quỷ",
    "major-16": "Tòa Tháp",
    "major-17": "Ngôi Sao",
    "major-18": "Mặt Trăng",
    "major-19": "Mặt Trời",
    "major-20": "Phán Xét",
    "major-21": "Thế Giới",
    # Wands — Gậy
    "wands-01": "Át Gậy",
    "wands-02": "Hai Gậy",
    "wands-03": "Ba Gậy",
    "wands-04": "Bốn Gậy",
    "wands-05": "Năm Gậy",
    "wands-06": "Sáu Gậy",
    "wands-07": "Bảy Gậy",
    "wands-08": "Tám Gậy",
    "wands-09": "Chín Gậy",
    "wands-10": "Mười Gậy",
    "wands-11": "Tiểu Đồng Gậy",
    "wands-12": "Hiệp Sĩ Gậy",
    "wands-13": "Hoàng Hậu Gậy",
    "wands-14": "Vua Gậy",
    # Cups — Cốc
    "cups-01": "Át Cốc",
    "cups-02": "Hai Cốc",
    "cups-03": "Ba Cốc",
    "cups-04": "Bốn Cốc",
    "cups-05": "Năm Cốc",
    "cups-06": "Sáu Cốc",
    "cups-07": "Bảy Cốc",
    "cups-08": "Tám Cốc",
    "cups-09": "Chín Cốc",
    "cups-10": "Mười Cốc",
    "cups-11": "Tiểu Đồng Cốc",
    "cups-12": "Hiệp Sĩ Cốc",
    "cups-13": "Hoàng Hậu Cốc",
    "cups-14": "Vua Cốc",
    # Swords — Kiếm
    "swords-01": "Át Kiếm",
    "swords-02": "Hai Kiếm",
    "swords-03": "Ba Kiếm",
    "swords-04": "Bốn Kiếm",
    "swords-05": "Năm Kiếm",
    "swords-06": "Sáu Kiếm",
    "swords-07": "Bảy Kiếm",
    "swords-08": "Tám Kiếm",
    "swords-09": "Chín Kiếm",
    "swords-10": "Mười Kiếm",
    "swords-11": "Tiểu Đồng Kiếm",
    "swords-12": "Hiệp Sĩ Kiếm",
    "swords-13": "Hoàng Hậu Kiếm",
    "swords-14": "Vua Kiếm",
    # Pentacles — Tiền
    "pentacles-01": "Át Tiền",
    "pentacles-02": "Hai Tiền",
    "pentacles-03": "Ba Tiền",
    "pentacles-04": "Bốn Tiền",
    "pentacles-05": "Năm Tiền",
    "pentacles-06": "Sáu Tiền",
    "pentacles-07": "Bảy Tiền",
    "pentacles-08": "Tám Tiền",
    "pentacles-09": "Chín Tiền",
    "pentacles-10": "Mười Tiền",
    "pentacles-11": "Tiểu Đồng Tiền",
    "pentacles-12": "Hiệp Sĩ Tiền",
    "pentacles-13": "Hoàng Hậu Tiền",
    "pentacles-14": "Vua Tiền",
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


def localized_positions(spread_type: str, locale: str = "ko") -> list[str]:
    """스프레드 포지션명을 로케일별로 반환 — vi 면 vi, 그 외 ko(기본). 응답의 positions 렌더용.

    ko 경로는 기존과 동일(SPREAD_POSITIONS). vi 만 SPREAD_POSITIONS_VI 로 치환한다.
    """
    if locale == "vi" and spread_type in SPREAD_POSITIONS_VI:
        return list(SPREAD_POSITIONS_VI[spread_type])
    return list(SPREAD_POSITIONS.get(spread_type, []))


def card_payload(
    position_index: int,
    position_name: str,
    card_id: int,
    is_reversed: bool,
    position_name_vi: str = "",
) -> dict[str, Any]:
    """확정 카드 1장의 응답 페이로드(서버 결정 데이터 — 프론트가 그대로 렌더).

    keywords 는 관리자 오버레이 반영값(신규 드로우 시점 스냅샷). interp 는 저장하지 않고
    _render_spread_for_llm 이 code 로 항상 최신본을 조회한다.
    name_vi/position_name_vi 는 vi 로케일 렌더용 병기(ko 는 name_kr/position_name 을 그대로 사용).
    """
    c = get_card(card_id)
    return {
        "position_index": position_index,
        "position_name": position_name,
        "position_name_vi": position_name_vi,
        "code": c["code"],
        "name_kr": c["name_kr"],
        "name_en": c["name_en"],
        "name_vi": CARD_NAME_VI.get(str(c["code"]), ""),
        "orientation": "reversed" if is_reversed else "upright",
        "image_url": f"{CARD_IMAGE_PREFIX}{c['file']}",
        "keywords": effective_keywords(c["code"], is_reversed),
    }
