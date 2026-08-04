"""타로 카드 해석/키워드 관리자 편집 서비스 — 정적 덱(JSON) 위 DB 오버레이 + 라이브 캐시.

- 저장소: tarot_card_overrides (code 별 편집분). row 없으면 tarot_deck_kr.json 시드 그대로.
- 라이브 반영: 저장/리셋 시 refresh_cache 로 tarot_deck 오버레이 캐시를 갱신 → 재시작 없이 즉시
  다음 드로우·해석에 반영. 앱 시작 시 main.py 가 refresh_cache 로 프리로드.
- 편집 대상은 keywords_up/rev(정/역)·interp_up/rev(정/역)뿐. 카드명·방향·이미지 등 구조 필드는
  JSON 이 단일 소스(편집 불가).
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.repositories.auth_models import AppSetting
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


# ============================================================
# 재학습(운영자 요구, 2026-07-11) — 유효 덱 '확정 스냅샷' 버전화
#
# 타로는 RAG/임베딩 색인이 없어 편집분이 프롬프트에 즉시 주입되지만, 운영자는 편집 누적분을
# 명시적 '학습' 단위로 확정·추적하길 원한다. 재학습 = ①라이브 캐시 전체 재적재(refresh_cache)
# ②유효 덱(시드+오버레이 병합 78장×정/역) 스냅샷을 버전 파일로 영구 보존(=백업)
# ③버전·학습일시·내용해시 기록. 야간 배치는 해시 패리티가 어긋나면(편집 발생) 자동 수행한다.
# ============================================================
_LEARN_VERSION_KEY = "tarot_deck_learn_version"
_LEARN_AT_KEY = "tarot_deck_learned_at"
_LEARN_HASH_KEY = "tarot_deck_learn_hash"
_LEARN_MANUAL_DATE_KEY = "tarot_deck_manual_learn_date"   # 수동 1일 1회 가드
_LEARN_SNAP_DIR = Path(__file__).resolve().parents[1] / "data" / "backups"


def _effective_content(db: Session) -> dict[str, dict[str, Any]]:
    """유효 덱 내용(시드+오버레이 병합) — 재적재 후 78장×정/역 키워드·해석."""
    refresh_cache(db)
    out: dict[str, dict[str, Any]] = {}
    for c in tarot_deck.all_cards():
        code = c["code"]
        out[code] = {
            "name_kr": c["name_kr"],
            "keywords_up": tarot_deck.effective_keywords(code, False),
            "keywords_rev": tarot_deck.effective_keywords(code, True),
            "interp_up": tarot_deck.interp_for(code, False),
            "interp_rev": tarot_deck.interp_for(code, True),
        }
    return out


def _content_hash(content: dict[str, Any]) -> str:
    blob = json.dumps(content, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _get_meta(db: Session, key: str, default: str = "") -> str:
    row = db.get(AppSetting, key)
    return row.value if (row is not None and row.value is not None) else default


def _set_meta(db: Session, items: dict[str, str]) -> None:
    from backend.app.services import settings_service
    for key, val in items.items():
        row = db.get(AppSetting, key)
        if row is None:
            db.add(AppSetting(key=key, value=val))
        else:
            row.value = val
    db.commit()
    settings_service.invalidate()  # app_settings 전량 캐시와 정합 유지


def learn_status(db: Session) -> dict[str, Any]:
    """최종 학습일자·버전·패리티(현재 내용 해시 vs 학습본 해시) — 관리자 표시/야간 배치 공용."""
    cur = _content_hash(_effective_content(db))
    learned_hash = _get_meta(db, _LEARN_HASH_KEY) or None
    try:
        version = int(_get_meta(db, _LEARN_VERSION_KEY, "0") or 0)
    except ValueError:
        version = 0
    return {
        "version": version,
        "learned_at": _get_meta(db, _LEARN_AT_KEY) or None,
        "changed": learned_hash != cur,     # 패리티 체크: 학습 이후 편집 발생 여부
        "current_hash": cur,
        "learned_hash": learned_hash,
        "manual_done_today": _get_meta(db, _LEARN_MANUAL_DATE_KEY) == date.today().isoformat(),
    }


# 재학습 직렬화 — 동시 클릭/야간 배치 경합으로 같은 내용이 두 번 학습(버전 중복)되는 것 방지.
# 관리자 API·스케줄러 모두 :8008 단일 프로세스에서 돌므로 프로세스 내 락으로 충분하다.
_RELEARN_LOCK = threading.Lock()


def relearn(db: Session, *, mode: str = "manual", admin_id: int | None = None) -> dict[str, Any]:
    """재학습 실행 — 캐시 재적재 + 확정 스냅샷 저장 + 버전/일시/해시 기록.

    중복학습 원천 차단(운영자 지시 2026-07-11):
    - 변경분(패리티 불일치)이 있을 때만 학습한다. 없으면 manual=예외(버튼도 비활성),
      auto=skipped 반환 — 같은 내용을 두 번 스냅샷/버전업하지 않는다.
    - '1일 1회'는 변경분 게이트로 대체: 수정·저장이 발생하면 같은 날에도 다시 학습 가능
      (버튼 재활성), 변경이 없으면 그날 몇 번을 눌러도 학습되지 않는다.
    - 프로세스 내 락으로 동시 실행(더블클릭·04:15 배치 경합)을 직렬화한다.
    """
    with _RELEARN_LOCK:
        content = _effective_content(db)        # refresh_cache 포함 — 라이브 재적재
        h = _content_hash(content)
        learned_hash = _get_meta(db, _LEARN_HASH_KEY) or None
        if h == learned_hash:
            if mode == "manual":
                raise ValueError("변경분이 없어 재학습할 내용이 없습니다. 카드 수정·저장 후 버튼이 다시 활성화됩니다.")
            st = learn_status(db)
            st["skipped"] = True                # 야간 배치: 변경 없음 → 학습 생략(중복 방지)
            st["mode"] = mode
            return st

        try:
            version = int(_get_meta(db, _LEARN_VERSION_KEY, "0") or 0) + 1
        except ValueError:
            version = 1
        now = datetime.now()

        _LEARN_SNAP_DIR.mkdir(parents=True, exist_ok=True)
        snap = _LEARN_SNAP_DIR / f"tarot_deck_learned_v{version}_{now:%Y%m%d_%H%M%S}.json"
        snap.write_text(json.dumps({
            "version": version,
            "learned_at": now.isoformat(timespec="seconds"),
            "mode": mode,
            "admin_id": admin_id,
            "hash": h,
            "cards": content,
        }, ensure_ascii=False, indent=1), encoding="utf-8")

        items = {
            _LEARN_VERSION_KEY: str(version),
            _LEARN_AT_KEY: now.isoformat(timespec="seconds"),
            _LEARN_HASH_KEY: h,
        }
        if mode == "manual":
            items[_LEARN_MANUAL_DATE_KEY] = date.today().isoformat()  # 표시/이력용(차단 용도 아님)
        _set_meta(db, items)

        st = learn_status(db)
        st["skipped"] = False
        st["snapshot"] = snap.name
        st["mode"] = mode
        return st
