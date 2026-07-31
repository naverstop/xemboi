"""타로 카드 해석/키워드 관리자 편집 서비스 — 정적 덱(JSON) 위 DB 오버레이 + 라이브 캐시.

- 저장소: tarot_card_overrides (code 별 편집분). row 없으면 tarot_deck_kr.json 시드 그대로.
- 라이브 반영: 저장/리셋 시 refresh_cache 로 tarot_deck 오버레이 캐시를 갱신 → 재시작 없이 즉시
  다음 드로우·해석에 반영. 앱 시작 시 main.py 가 refresh_cache 로 프리로드.
- 편집 대상은 keywords_up/rev(정/역)·interp_up/rev(정/역)뿐. 카드명·방향·이미지 등 구조 필드는
  JSON 이 단일 소스(편집 불가).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.repositories.models import TarotCardOverride
from backend.app.services import tarot_deck

# 편집 가드(입력 검증)
_MAX_KW = 12          # 방향별 키워드 최대 개수
_MAX_KW_LEN = 40      # 키워드 1개 최대 길이
_MAX_INTERP = 2000    # 해석 서술 최대 길이


def refresh_cache(db: Session) -> None:
    """DB 오버레이 전체를 읽어 tarot_deck 캐시에 주입. 테이블 부재/실패 시 빈 캐시(=JSON 시드)."""
    ov: dict[str, dict[str, Any]] = {}
    try:
        for r in db.execute(select(TarotCardOverride)).scalars().all():
            ov[r.code] = {
                "keywords_up": list(r.keywords_up) if r.keywords_up else None,
                "keywords_rev": list(r.keywords_rev) if r.keywords_rev else None,
                "interp_up": r.interp_up or None,
                "interp_rev": r.interp_rev or None,
            }
    except Exception:  # noqa: BLE001 — 마이그레이션 전(테이블 부재) 등: 시드로 graceful degrade
        ov = {}
    tarot_deck.set_overrides(ov)


def _clean_keywords(v: Any, field: str) -> list[str]:
    if not isinstance(v, list):
        raise ValueError(f"{field}는 목록이어야 합니다")
    out: list[str] = []
    for k in v:
        s = str(k).strip()
        if not s:
            continue
        if len(s) > _MAX_KW_LEN:
            raise ValueError(f"{field} 항목은 {_MAX_KW_LEN}자 이내여야 합니다: '{s[:12]}…'")
        if s not in out:
            out.append(s)
    if not out:
        raise ValueError(f"{field}는 최소 1개 이상이어야 합니다")
    if len(out) > _MAX_KW:
        raise ValueError(f"{field}는 최대 {_MAX_KW}개까지입니다")
    return out


def _clean_interp(v: Any, field: str) -> str:
    s = str(v or "").strip()
    if not s:
        raise ValueError(f"{field}는 비울 수 없습니다")
    if len(s) > _MAX_INTERP:
        raise ValueError(f"{field}는 {_MAX_INTERP}자 이내여야 합니다")
    return s


def _effective_card(base: dict[str, Any], row: TarotCardOverride | None) -> dict[str, Any]:
    code = base["code"]
    return {
        "id": base["id"],
        "code": code,
        "name_kr": base["name_kr"],
        "name_en": base["name_en"],
        "arcana": base["arcana"],
        "suit": base.get("suit"),
        "image_url": f"{tarot_deck.CARD_IMAGE_PREFIX}{base['file']}",
        # 시드 기본값(되돌리기 프리뷰·비교용)
        "seed_keywords_up": [str(k) for k in (base.get("keywords_up") or [])],
        "seed_keywords_rev": [str(k) for k in (base.get("keywords_rev") or [])],
        "seed_interp_up": str(base.get("interp_up") or ""),
        "seed_interp_rev": str(base.get("interp_rev") or ""),
        # 현재 유효값(오버레이 반영)
        "keywords_up": tarot_deck.effective_keywords(code, False),
        "keywords_rev": tarot_deck.effective_keywords(code, True),
        "interp_up": tarot_deck.interp_for(code, False),
        "interp_rev": tarot_deck.interp_for(code, True),
        "overridden": row is not None,
        "updated_at": row.updated_at.isoformat() if (row and row.updated_at) else None,
        "updated_by": row.updated_by if row else None,
    }


def list_cards(db: Session) -> list[dict[str, Any]]:
    """78장 유효 카드(시드+오버레이 병합) — 관리자 편집 화면용. 조회 시 캐시도 최신화."""
    refresh_cache(db)
    rows = {r.code: r for r in db.execute(select(TarotCardOverride)).scalars().all()}
    return [_effective_card(c, rows.get(c["code"])) for c in tarot_deck.all_cards()]


def get_card(db: Session, code: str) -> dict[str, Any]:
    base = tarot_deck.card_by_code(code)
    if base is None:
        raise LookupError(f"unknown card code: {code}")
    row = db.get(TarotCardOverride, code)
    return _effective_card(base, row)


def update_card(
    db: Session, code: str, *,
    keywords_up: Any, keywords_rev: Any, interp_up: Any, interp_rev: Any,
    admin_id: int | None = None,
) -> dict[str, Any]:
    """카드 1장의 키워드(정/역)·해석(정/역) 편집분을 upsert 하고 캐시를 즉시 갱신."""
    base = tarot_deck.card_by_code(code)
    if base is None:
        raise LookupError(f"unknown card code: {code}")
    ku = _clean_keywords(keywords_up, "정방향 키워드")
    kr = _clean_keywords(keywords_rev, "역방향 키워드")
    iu = _clean_interp(interp_up, "정방향 해석")
    ir = _clean_interp(interp_rev, "역방향 해석")

    row = db.get(TarotCardOverride, code)
    if row is None:
        row = TarotCardOverride(code=code)
        db.add(row)
    row.keywords_up = ku
    row.keywords_rev = kr
    row.interp_up = iu
    row.interp_rev = ir
    row.updated_at = datetime.utcnow()
    row.updated_by = admin_id
    db.commit()
    refresh_cache(db)  # 라이브 반영(재시작 불필요)
    return get_card(db, code)


def reset_card(db: Session, code: str) -> dict[str, Any]:
    """카드 편집분 삭제 → JSON 시드(초안)로 되돌림. 캐시 즉시 갱신."""
    base = tarot_deck.card_by_code(code)
    if base is None:
        raise LookupError(f"unknown card code: {code}")
    row = db.get(TarotCardOverride, code)
    if row is not None:
        db.delete(row)
        db.commit()
    refresh_cache(db)
    return get_card(db, code)
