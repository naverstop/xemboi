"""마케팅 가격 에이전트 서비스 — 결정적 권장가 산출 + 승인 게이트 적용.

설계: docs/마케팅_가격에이전트_추진계획서.md. 운영자 확정(2026-07-13):
- 권장가 = 경쟁사 최저 × (1-언더컷%) → 하한/상한 클램프 → 1회 최대변동 제한 → 심리가 반올림. **결정적**(LLM/GPU 없음).
- 가격 변경은 **관리자 [적용] 클릭** 으로만(apply_recommendation → settings_service.set_many). 자동 적용 없음.
- 3소스 동기화(DB app_settings / DEFAULTS / entryFee.ts FALLBACK) 중 런타임은 DB만 반영 — 코드 폴백은 배포 diff 로 안내.
"""
from __future__ import annotations

import statistics
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.services import settings_service

# 에이전트가 관리하는 가격 키 전체(= app_settings 정수 키 중 '가격'). 상담단가 포함.
PRICING_KEYS: tuple[str, ...] = (
    "entry_cost_compat", "entry_cost_taekil", "entry_cost_jakmyeong", "entry_cost_gaemyeong",
    "entry_cost_aho", "entry_cost_tarot", "entry_cost_sinnyeon",
    "credit_cost_basic", "credit_cost_deep",
    "preview_reveal_cost", "amulet_cost_p", "video_gen_cost",
    "consultation_default_price_p",
)

KEY_LABEL: dict[str, str] = {
    "entry_cost_compat": "궁합 입장료", "entry_cost_taekil": "택일 입장료",
    "entry_cost_jakmyeong": "작명 입장료", "entry_cost_gaemyeong": "개명 입장료",
    "entry_cost_aho": "아호 입장료", "entry_cost_tarot": "타로 입장료",
    "entry_cost_sinnyeon": "신년운세 입장료", "credit_cost_basic": "기본 질문",
    "credit_cost_deep": "심화 질문", "preview_reveal_cost": "전체보기",
    "amulet_cost_p": "부적 발행", "video_gen_cost": "영상 생성",
    "consultation_default_price_p": "1:1 상담 기본단가",
}

DOC_STALE_DAYS = 14   # 경쟁사 시트가 이 일수 초과 미갱신이면 '낡음' 경고

# 가드레일 시드 기본안(운영자 확정 2026-07-13) — (floor, ceiling, max_change%, undercut%, round_unit, round_tail)
# round_unit=1000·round_tail=900 → 끝자리 900 앵커(…4900,5900,9900). 상담은 unit=1000·tail=0(천원 단위).
# max_change=25%: …900 앵커 간격(1000)을 한 스텝 넘을 수 있게(작은 가격도 이동 가능). 상담(큰 가격)은 20%.
_GUARDRAIL_SEED: dict[str, tuple[int, int, int, int, int, int]] = {
    "entry_cost_tarot":     (3900, 19900, 25, 5, 1000, 900),
    "entry_cost_compat":    (3900, 19900, 25, 5, 1000, 900),
    "entry_cost_aho":       (3900, 19900, 25, 5, 1000, 900),
    "entry_cost_jakmyeong": (4900, 29900, 25, 5, 1000, 900),
    "entry_cost_gaemyeong": (4900, 29900, 25, 5, 1000, 900),
    "entry_cost_taekil":    (4900, 29900, 25, 5, 1000, 900),
    "entry_cost_sinnyeon":  (4900, 29900, 25, 5, 1000, 900),
    "credit_cost_basic":    (900, 9900, 25, 10, 1000, 900),
    "credit_cost_deep":     (900, 9900, 25, 10, 1000, 900),
    "amulet_cost_p":        (900, 9900, 30, 5, 1000, 900),
    "video_gen_cost":       (900, 9900, 30, 5, 1000, 900),
    "preview_reveal_cost":  (900, 9900, 30, 5, 1000, 900),
    "consultation_default_price_p": (30000, 120000, 20, 3, 1000, 0),
}


# ─────────────────────────── 가드레일 ───────────────────────────

def seed_guardrails(db: Session) -> int:
    """없는 메뉴 키만 기본안으로 시드(멱등). 반환=신규 삽입 건수."""
    from backend.app.repositories.pricing_models import PricingGuardrail

    have = {g.menu_key for g in db.execute(select(PricingGuardrail)).scalars().all()}
    n = 0
    for key, (fl, ce, mc, uc, ru, rt) in _GUARDRAIL_SEED.items():
        if key in have:
            continue
        db.add(PricingGuardrail(menu_key=key, floor_p=fl, ceiling_p=ce, max_change_pct=mc,
                                undercut_pct=uc, round_unit=ru, round_tail=rt, enabled=True))
        n += 1
    if n:
        db.commit()
    return n


def guardrail_dict(g: "PricingGuardrail") -> dict[str, Any]:  # noqa: F821
    return {
        "menu_key": g.menu_key, "label": KEY_LABEL.get(g.menu_key, g.menu_key),
        "floor_p": g.floor_p, "ceiling_p": g.ceiling_p, "max_change_pct": g.max_change_pct,
        "undercut_pct": g.undercut_pct, "round_unit": g.round_unit, "round_tail": g.round_tail,
        "enabled": g.enabled,
    }


def list_guardrails(db: Session) -> list[dict[str, Any]]:
    from backend.app.repositories.pricing_models import PricingGuardrail
    seed_guardrails(db)
    rows = db.execute(select(PricingGuardrail)).scalars().all()
    order = {k: i for i, k in enumerate(PRICING_KEYS)}
    rows.sort(key=lambda g: order.get(g.menu_key, 999))
    return [guardrail_dict(g) for g in rows]


def update_guardrail(db: Session, menu_key: str, patch: dict[str, Any]) -> dict[str, Any]:
    from backend.app.repositories.pricing_models import PricingGuardrail
    if menu_key not in PRICING_KEYS:
        raise ValueError("알 수 없는 가격 항목이에요.")
    g = db.get(PricingGuardrail, menu_key)
    if g is None:
        seed = _GUARDRAIL_SEED.get(menu_key, (0, 1_000_000, 20, 5, 100, 900))
        g = PricingGuardrail(menu_key=menu_key, floor_p=seed[0], ceiling_p=seed[1],
                             max_change_pct=seed[2], undercut_pct=seed[3],
                             round_unit=seed[4], round_tail=seed[5])
        db.add(g)
    for f in ("floor_p", "ceiling_p", "max_change_pct", "undercut_pct", "round_unit", "round_tail", "enabled"):
        if f in patch and patch[f] is not None:
            setattr(g, f, patch[f])
    if g.floor_p > g.ceiling_p:
        raise ValueError("하한이 상한보다 클 수 없어요.")
    g.updated_at = datetime.utcnow()
    db.commit()
    return guardrail_dict(g)


# ─────────────────────────── 경쟁사 시트 ───────────────────────────

def competitor_dict(c: "CompetitorPrice") -> dict[str, Any]:  # noqa: F821
    stale = (datetime.utcnow() - c.verified_at) > timedelta(days=DOC_STALE_DAYS) if c.verified_at else True
    return {
        "id": c.id, "competitor_name": c.competitor_name, "menu_key": c.menu_key,
        "label": KEY_LABEL.get(c.menu_key, c.menu_key), "price_krw": c.price_krw, "note": c.note,
        "verified_at": c.verified_at.isoformat() if c.verified_at else None, "stale": stale,
    }


def list_competitors(db: Session) -> list[dict[str, Any]]:
    from backend.app.repositories.pricing_models import CompetitorPrice
    rows = db.execute(select(CompetitorPrice).order_by(CompetitorPrice.menu_key, CompetitorPrice.competitor_name)).scalars().all()
    return [competitor_dict(c) for c in rows]


def upsert_competitor(db: Session, *, id: Optional[int], competitor_name: str, menu_key: str,
                      price_krw: int, note: Optional[str], updated_by: Optional[str]) -> dict[str, Any]:
    from backend.app.repositories.pricing_models import CompetitorPrice
    if menu_key not in PRICING_KEYS:
        raise ValueError("알 수 없는 가격 항목이에요.")
    if not (competitor_name or "").strip():
        raise ValueError("경쟁사 이름을 입력해 주세요.")
    if price_krw < 0:
        raise ValueError("가격은 0 이상이어야 해요.")
    c = db.get(CompetitorPrice, id) if id else None
    if c is None:
        c = CompetitorPrice(competitor_name=competitor_name.strip()[:80], menu_key=menu_key, price_krw=price_krw)
        db.add(c)
    else:
        c.competitor_name = competitor_name.strip()[:80]
        c.menu_key = menu_key
        c.price_krw = price_krw
    c.note = (note or "").strip()[:200] or None
    c.updated_by = (updated_by or "")[:255] or None
    c.verified_at = datetime.utcnow()
    db.commit()
    db.refresh(c)
    return competitor_dict(c)


def delete_competitor(db: Session, id: int) -> None:
    from backend.app.repositories.pricing_models import CompetitorPrice
    c = db.get(CompetitorPrice, id)
    if c is not None:
        db.delete(c)
        db.commit()


# ─────────────────────────── 권장가 산출(결정적) ───────────────────────────

def _nearest_anchor(value: float, unit: int, tail: int, lo: int, hi: int) -> int:
    """[lo,hi] 범위 안에서 value 에 가장 가까운 심리가 앵커.

    tail>0: k·unit+tail(…900 앵커) 중 [lo,hi] 내 최근접. tail=0: unit 배수 중 최근접.
    범위 안에 앵커가 하나도 없으면 value 를 [lo,hi]로 클램프한 정수 반환(앵커 불가 시 범위 우선).
    """
    unit = max(1, unit)
    lo = int(lo); hi = int(hi)
    if lo > hi:
        lo = hi
    cands: list[int] = []
    if tail <= 0:
        k0 = (lo + unit - 1) // unit           # ceil(lo/unit)
        k1 = hi // unit                         # floor(hi/unit)
        cands = [k * unit for k in range(k0, k1 + 1)]
    else:
        # k·unit+tail 가 [lo,hi] 에 드는 k 범위
        import math
        k0 = math.ceil((lo - tail) / unit)
        k1 = math.floor((hi - tail) / unit)
        cands = [k * unit + tail for k in range(k0, k1 + 1) if k * unit + tail >= 0]
    if not cands:
        return int(min(max(round(value), lo), hi))
    return min(cands, key=lambda c: abs(c - value))


def compute_recommendation(current: int, competitor_prices: list[int], g: dict[str, Any]) -> dict[str, Any]:
    """단일 메뉴 권장가 산출(순수 함수). 반환: recommended, competitor_min/median, rationale, changed.

    유효 구간 [lo,hi]를 먼저 확정(하한/상한 ∩ 1회 최대변동 밴드 ∩ 언더컷 상한) 후 그 안의 최근접
    심리가 앵커를 고른다 — 반올림이 경쟁사 최저·최대변동·상하한을 넘는 결함을 원천 차단.
    """
    if not competitor_prices:
        return {"recommended": current, "competitor_min": None, "competitor_median": None,
                "changed": False, "rationale": "경쟁사 데이터 없음 — 현재가 유지."}
    cmin = min(competitor_prices)
    cmed = int(statistics.median(competitor_prices))
    undercut = max(0, min(100, g["undercut_pct"]))
    floor, ceiling = int(g["floor_p"]), int(g["ceiling_p"])
    target = cmin * (100 - undercut) / 100.0                      # ① 항상 언더컷(목표)

    # ② 유효 구간: 하한/상한 ∩ 1회 최대변동 밴드. current==0 은 퍼센트 캡 무의미 → 하한/상한만.
    lo, hi = floor, ceiling
    if current > 0:
        md = current * max(0, g["max_change_pct"]) / 100.0       # max_change=0 → md=0 → lo=hi=current(동결)
        lo = max(lo, int(round(current - md)))
        hi = min(hi, int(round(current + md)))
    # ③ 언더컷 불변식: 목표가 경쟁사 최저 이하이고 밴드 안에서 도달 가능하면 상한을 경쟁사 최저로
    #    (반올림이 경쟁사 최저 위로 튀는 것 차단). 밴드가 그만큼 못 내려가면(1회 변동 제한) 이 제약은 포기.
    if undercut > 0 and cmin >= lo:
        hi = min(hi, cmin)
    if lo > hi:
        lo = hi
    target = min(max(target, lo), hi)
    rec = _nearest_anchor(target, g["round_unit"], g["round_tail"], lo, hi)  # ④ 범위 내 심리가 반올림

    changed = rec != current
    rationale = (
        f"경쟁사 최저 {cmin:,}원 대비 {undercut}% 우위 목표 → "
        f"가드레일(하한 {floor:,}/상한 {ceiling:,}/최대변동 {g['max_change_pct']}%) 적용 → "
        f"권장 {rec:,}P (현재 {current:,}P)"
    )
    return {"recommended": rec, "competitor_min": cmin, "competitor_median": cmed,
            "changed": changed, "rationale": rationale}


def run_survey(db: Session) -> dict[str, Any]:
    """시장 조사 회차 실행 — 경쟁사 시트+가드레일로 전 메뉴 권장가 산출 후 pending 적재.

    ⛔ 가격을 변경하지 않는다(권장만 생성). 변경은 apply_recommendation(관리자 클릭)만.
    기존 pending 은 새 회차로 대체(dismiss)해 중복 방지.
    """
    from backend.app.repositories.pricing_models import (
        CompetitorPrice, PricingGuardrail, PricingRecommendation,
    )
    seed_guardrails(db)
    # 이전 pending 은 무시 처리(최신 회차만 유효)
    for r in db.execute(select(PricingRecommendation).where(PricingRecommendation.status == "pending")).scalars().all():
        r.status = "dismissed"
        r.decided_at = datetime.utcnow()
        r.decided_by = "system:new_survey"

    comps: dict[str, list[int]] = {}
    for c in db.execute(select(CompetitorPrice)).scalars().all():
        comps.setdefault(c.menu_key, []).append(c.price_krw)
    guards = {g.menu_key: g for g in db.execute(select(PricingGuardrail)).scalars().all()}

    batch_id = uuid.uuid4().hex[:16]
    made = {"batch_id": batch_id, "pending": 0, "skipped": 0, "items": []}
    for key in PRICING_KEYS:
        current = settings_service.get_int(db, key)
        g = guards.get(key)
        if g is None or not g.enabled:
            continue
        out = compute_recommendation(current, comps.get(key, []), guardrail_dict(g))
        status = "pending" if out["changed"] else "skipped"
        rec = PricingRecommendation(
            batch_id=batch_id, menu_key=key, current_price=current,
            competitor_min=out["competitor_min"], competitor_median=out["competitor_median"],
            recommended_price=out["recommended"], rationale=out["rationale"], status=status,
        )
        db.add(rec)
        made["pending" if status == "pending" else "skipped"] += 1
    db.commit()
    return made


# ─────────────────────────── 승인 게이트: 적용/무시/롤백 ───────────────────────────

def recommendation_dict(r: "PricingRecommendation") -> dict[str, Any]:  # noqa: F821
    return {
        "id": r.id, "batch_id": r.batch_id, "menu_key": r.menu_key,
        "label": KEY_LABEL.get(r.menu_key, r.menu_key), "current_price": r.current_price,
        "competitor_min": r.competitor_min, "competitor_median": r.competitor_median,
        "recommended_price": r.recommended_price, "rationale": r.rationale, "status": r.status,
        "applied_from": r.applied_from,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None, "decided_by": r.decided_by,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def list_recommendations(db: Session, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
    from backend.app.repositories.pricing_models import PricingRecommendation
    stmt = select(PricingRecommendation).order_by(PricingRecommendation.id.desc()).limit(limit)
    if status:
        stmt = select(PricingRecommendation).where(PricingRecommendation.status == status).order_by(PricingRecommendation.id.desc()).limit(limit)
    return [recommendation_dict(r) for r in db.execute(stmt).scalars().all()]


def apply_recommendation(db: Session, rec_id: int, admin_email: Optional[str]) -> dict[str, Any]:
    """관리자 [적용] — 유일한 가격변경 경로. set_many 로 라이브 반영 + 롤백용 직전값 기록.

    ⚠️ DB app_settings 만 즉시 반영(20초 TTL). 코드 폴백(DEFAULTS/entryFee.ts)은 배포 diff 로 별도 안내.
    """
    from backend.app.repositories.pricing_models import PricingRecommendation
    r = db.get(PricingRecommendation, rec_id)
    if r is None:
        raise LookupError("권장 항목을 찾을 수 없어요.")
    if r.status != "pending":
        raise ValueError("이미 처리된 항목이에요.")
    prev = settings_service.get_int(db, r.menu_key)       # 롤백 대비 직전 실제값
    settings_service.set_many(db, {r.menu_key: r.recommended_price})   # ← 라이브 반영(승인된 값만)
    r.status = "applied"
    r.applied_from = prev
    r.decided_at = datetime.utcnow()
    r.decided_by = (admin_email or "admin")[:255]
    db.commit()
    return recommendation_dict(r)


def dismiss_recommendation(db: Session, rec_id: int, admin_email: Optional[str]) -> dict[str, Any]:
    from backend.app.repositories.pricing_models import PricingRecommendation
    r = db.get(PricingRecommendation, rec_id)
    if r is None:
        raise LookupError("권장 항목을 찾을 수 없어요.")
    if r.status != "pending":
        raise ValueError("이미 처리된 항목이에요.")
    r.status = "dismissed"
    r.decided_at = datetime.utcnow()
    r.decided_by = (admin_email or "admin")[:255]
    db.commit()
    return recommendation_dict(r)


def rollback_recommendation(db: Session, rec_id: int, admin_email: Optional[str]) -> dict[str, Any]:
    """적용된 항목의 직전값(applied_from) 복원 — 잘못 적용 시 되돌리기."""
    from backend.app.repositories.pricing_models import PricingRecommendation
    r = db.get(PricingRecommendation, rec_id)
    if r is None:
        raise LookupError("권장 항목을 찾을 수 없어요.")
    if r.status != "applied" or r.applied_from is None:
        raise ValueError("적용된 항목만 되돌릴 수 있어요.")
    # 정합성: 이 적용이 아직 '최신'일 때만 롤백 허용 — 이후 다른 변경이 적용됐으면(라이브값이
    # 이 권장가와 다르면) 옛 값으로 최신 라이브를 덮어쓰는 사고를 차단.
    live = settings_service.get_int(db, r.menu_key)
    if live != r.recommended_price:
        raise ValueError(f"이미 다른 변경이 적용됐어요(현재 {live:,}P). 최신 이력에서 되돌려 주세요.")
    settings_service.set_many(db, {r.menu_key: r.applied_from})
    r.status = "dismissed"
    r.decided_at = datetime.utcnow()
    r.decided_by = f"rollback:{(admin_email or 'admin')[:240]}"
    db.commit()
    return recommendation_dict(r)


def sync_diff(db: Session) -> list[dict[str, Any]]:
    """3소스 동기화 상태 — 현재 라이브(DB) 값과 코드 폴백(DEFAULTS)의 차이. 배포 시 맞출 대상 안내.

    entryFee.ts FALLBACK 은 프론트라 여기선 DEFAULTS 만 대조(입장료 7키). 값 다르면 배포 diff 필요.
    """
    out = []
    for key in PRICING_KEYS:
        live = settings_service.get_int(db, key)
        default = int(settings_service.DEFAULTS.get(key, "0") or 0)
        if live != default:
            out.append({"menu_key": key, "label": KEY_LABEL.get(key, key),
                        "live": live, "code_default": default})
    return out
