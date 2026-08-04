"""마케팅 가격 에이전트 — 결정적 권장가 산출 + 승인 게이트(운영자 확정 2026-07-13)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.repositories.models import Base
from backend.app.repositories import auth_models  # noqa: F401
from backend.app.repositories import pricing_models  # noqa: F401
from backend.app.services import pricing_agent_service as P
from backend.app.services import settings_service


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = SessionLocal()
    settings_service.invalidate()   # 캐시 격리(다른 테스트 DB 잔재 방지)
    try:
        yield s
    finally:
        s.close(); engine.dispose(); settings_service.invalidate()


# ── 순수 산출 함수(결정적) ──

def _g(**kw):
    base = {"floor_p": 0, "ceiling_p": 1_000_000, "max_change_pct": 100,
            "undercut_pct": 5, "round_unit": 1000, "round_tail": 900}
    base.update(kw)
    return base


def test_undercut_and_round():
    # 경쟁사 최저 10,000 · 5% 언더컷 = 9,500 → …900 반올림 = 9,900? 가장 가까운 …900은 9,900
    out = P.compute_recommendation(12000, [10000, 11000], _g(undercut_pct=5))
    assert out["competitor_min"] == 10000
    assert out["recommended"] == 9900       # 9,500 → 가장 가까운 …900 = 9,900
    assert out["changed"] is True


def test_floor_clamp():
    # 언더컷 결과가 하한 미만이면 하한으로
    out = P.compute_recommendation(5000, [2000], _g(floor_p=3900, undercut_pct=10))
    assert out["recommended"] == 3900


def test_ceiling_clamp():
    out = P.compute_recommendation(5000, [999999], _g(ceiling_p=19900, max_change_pct=100, undercut_pct=0))
    assert out["recommended"] <= 19900


def test_max_change_limits_swing():
    # 현재 10,000, 경쟁사 2,000 → 1회 최대변동 20% 밴드 [8,000, 12,000] 안의 …900 앵커 = 8,900
    # (구버전은 7,900으로 밴드를 100P 넘겨 위반 → 수정: 밴드 내 앵커만 선택)
    out = P.compute_recommendation(10000, [2000], _g(max_change_pct=20, undercut_pct=5, floor_p=0))
    assert out["recommended"] == 8900
    assert 8000 <= out["recommended"] <= 12000   # 밴드 준수


def test_no_competitor_keeps_current():
    out = P.compute_recommendation(9900, [], _g())
    assert out["recommended"] == 9900 and out["changed"] is False


def test_max_change_zero_freezes_price():
    # 최대변동 0% = 동결(무제한 아님) — 감사 결함 수정 검증
    out = P.compute_recommendation(10000, [2000], _g(max_change_pct=0, undercut_pct=5, floor_p=0))
    assert out["recommended"] == 10000 and out["changed"] is False


def test_rounding_never_exceeds_competitor_min():
    # 언더컷>0이면 반올림이 경쟁사 최저 위로 튀지 않음 — 감사 결함 수정 검증
    out = P.compute_recommendation(7900, [6800], _g(undercut_pct=5, floor_p=3900, ceiling_p=19900))
    assert out["recommended"] <= 6800          # 경쟁사 최저 이하 보장
    assert out["recommended"] % 1000 == 900    # …900 앵커 유지


def test_rounding_never_exceeds_max_change_band():
    # 반올림이 1회 최대변동 밴드를 넘지 않음(현재 4900, 20% → 하락 상한 980) — 감사 결함 수정 검증
    out = P.compute_recommendation(4900, [0], _g(undercut_pct=5, floor_p=0, ceiling_p=19900, max_change_pct=20))
    assert out["recommended"] >= 4900 - int(4900 * 0.20)   # 3920 이상(밴드 준수)


def test_round_tail_zero_uses_unit_multiple():
    # 상담단가: tail=0, unit=1000 → 1000 배수
    out = P.compute_recommendation(50000, [60000], _g(undercut_pct=3, round_unit=1000, round_tail=0, ceiling_p=120000))
    assert out["recommended"] % 1000 == 0


# ── 승인 게이트(라이브 세션) ──

def test_survey_creates_pending_but_never_changes_price(db):
    settings_service.set_many(db, {"entry_cost_compat": 5900})
    P.seed_guardrails(db)
    P.upsert_competitor(db, id=None, competitor_name="포스텔러", menu_key="entry_cost_compat",
                        price_krw=8000, note=None, updated_by="t@t")
    before = settings_service.get_int(db, "entry_cost_compat")
    r = P.run_survey(db)
    after = settings_service.get_int(db, "entry_cost_compat")
    assert before == after == 5900          # ⛔ 조사는 가격을 바꾸지 않는다
    pend = P.list_recommendations(db, status="pending")
    assert any(x["menu_key"] == "entry_cost_compat" for x in pend)


def test_apply_is_only_price_change_path(db):
    settings_service.set_many(db, {"consultation_default_price_p": 59000})
    P.seed_guardrails(db)
    P.upsert_competitor(db, id=None, competitor_name="점신", menu_key="consultation_default_price_p",
                        price_krw=50000, note=None, updated_by="t@t")
    P.run_survey(db)
    rec = next(x for x in P.list_recommendations(db, status="pending") if x["menu_key"] == "consultation_default_price_p")
    out = P.apply_recommendation(db, rec["id"], "admin@t")
    assert out["status"] == "applied"
    assert settings_service.get_int(db, "consultation_default_price_p") == out["recommended_price"]   # 실제 반영
    assert out["applied_from"] == 59000                                                               # 롤백값 보존
    # 이미 처리된 항목 재적용 차단
    with pytest.raises(ValueError):
        P.apply_recommendation(db, rec["id"], "admin@t")


def test_rollback_restores_previous(db):
    settings_service.set_many(db, {"consultation_default_price_p": 59000})
    P.seed_guardrails(db)
    P.upsert_competitor(db, id=None, competitor_name="헬로우봇", menu_key="consultation_default_price_p",
                        price_krw=48000, note=None, updated_by="t@t")
    P.run_survey(db)
    rec = next(x for x in P.list_recommendations(db, status="pending") if x["menu_key"] == "consultation_default_price_p")
    P.apply_recommendation(db, rec["id"], "admin@t")
    changed = settings_service.get_int(db, "consultation_default_price_p")
    assert changed != 59000
    P.rollback_recommendation(db, rec["id"], "admin@t")
    assert settings_service.get_int(db, "consultation_default_price_p") == 59000   # 직전값 복원


def test_rollback_blocked_when_superseded(db):
    """멀티-적용 후 옛 적용건 롤백 차단 — 최신 라이브를 stale값으로 덮는 사고 방지(감사 수정)."""
    KEY = "consultation_default_price_p"
    settings_service.set_many(db, {KEY: 59000})
    P.seed_guardrails(db)
    # R1: 경쟁사 낮게 → 적용
    c1 = P.upsert_competitor(db, id=None, competitor_name="A", menu_key=KEY, price_krw=52000, note=None, updated_by="t")
    P.run_survey(db)
    r1 = next(x for x in P.list_recommendations(db, status="pending") if x["menu_key"] == KEY)
    P.apply_recommendation(db, r1["id"], "admin")
    live1 = settings_service.get_int(db, KEY)
    # R2: 더 낮게 → 재조사·적용
    P.upsert_competitor(db, id=c1["id"], competitor_name="A", menu_key=KEY, price_krw=44000, note=None, updated_by="t")
    P.run_survey(db)
    r2 = next(x for x in P.list_recommendations(db, status="pending") if x["menu_key"] == KEY)
    P.apply_recommendation(db, r2["id"], "admin")
    live2 = settings_service.get_int(db, KEY)
    assert live2 != live1
    # 옛 R1 롤백 시도 → 최신이 아니므로 차단
    with pytest.raises(ValueError):
        P.rollback_recommendation(db, r1["id"], "admin")
    assert settings_service.get_int(db, KEY) == live2   # 최신값 보존
    # 최신 R2 롤백은 정상
    P.rollback_recommendation(db, r2["id"], "admin")
    assert settings_service.get_int(db, KEY) == live1


def test_disabled_guardrail_skipped(db):
    settings_service.set_many(db, {"entry_cost_aho": 6900})
    P.seed_guardrails(db)
    P.update_guardrail(db, "entry_cost_aho", {"enabled": False})
    P.upsert_competitor(db, id=None, competitor_name="X", menu_key="entry_cost_aho",
                        price_krw=3000, note=None, updated_by="t@t")
    P.run_survey(db)
    assert not any(x["menu_key"] == "entry_cost_aho" for x in P.list_recommendations(db, status="pending"))
