# -*- coding: utf-8 -*-
"""택일 뽀 관법 2차(2026-08-03 뽀 확인): 계약=인수(문서) 중심 · 개업=재-식상 합 · 출산=상담 유도.

- 계약: 문서(인수) 깨진 날 하드배제 + 그날 일진이 원국 인수와 합(관/식상/재가 끌어옴)이면 가점.
- 개업: 재 안 깨짐(유지) + '돈이 식상과 합되는 날'만 가점(비겁-재 합=뺏김이라 제외).
- 출산: 엔진 자동추천 유지(무변경) + 부모② 명식 영속(상담사 전달) + 상담 소스(kind=birth).
"""
from __future__ import annotations

import contextlib
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.saju import taekil
from backend.app.saju.engine import build_chart
from backend.app.saju.taekil import _day_combines_star, _score_day, recommend_dates
from backend.app.saju.types import BirthInput, CalendarType, Gender


def _chart(y, m, d, gender, t="12:00"):
    return build_chart(BirthInput(birth_date=date(y, m, d), birth_time=t,
                                  calendar=CalendarType.SOLAR, gender=gender))


@contextlib.contextmanager
def _opts(**over):
    old = dict(taekil.TAEKIL_OPTIONS)
    taekil.TAEKIL_OPTIONS.update(over)
    try:
        yield
    finally:
        taekil.TAEKIL_OPTIONS.clear()
        taekil.TAEKIL_OPTIONS.update(old)


def _scan(user, purpose, days=365):
    with _opts(month_luck_mode="off"):
        return [_score_day(date(2026, 1, 1) + timedelta(days=i), user, purpose) for i in range(days)]


# ── 계약 = 인수(문서) 중심 ────────────────────────────────────────
def test_contract_insu_hard_and_no_jae_check():
    user = _chart(1988, 5, 20, Gender.MALE)
    scored = _scan(user, "contract")
    # 인수(문서) 깨진 날 = 하드배제(score≤44) 실재.
    insu_broken = [s for s in scored if any("인수" in w for w in s.warnings)]
    assert insu_broken, "계약에서 인수 깨짐 판정이 전혀 없음"
    assert all(s.score <= 44 for s in insu_broken), "인수 깨진 날이 하드배제되지 않음"
    # 계약은 이제 재(돈) 보호가 아님 — 재 경고가 나오면 안 된다(뽀: 계약=문서 중심).
    assert not any("재(돈)" in w for s in scored for w in s.warnings), "계약에 구 재(財) 체크 잔존"


def test_contract_insu_hap_bonus():
    user = _chart(1988, 5, 20, Gender.MALE)
    scored = _scan(user, "contract")
    hap = [s for s in scored if "인수(문서) 합" in s.reason]
    assert hap, "계약 인수-합 가점일이 1년 내 없음"
    for s in hap:
        assert not s.reason.startswith("회피")     # 합 가점은 깨짐과 공존 안 함


# ── 개업 = 재-식상 합 ─────────────────────────────────────────────
# ⚠️ 픽스처 주의: 재-식상 합은 명식 구조에 따라 성립 불가할 수 있다(구조상 천간합의 재 파트너는
#   항상 인수/비겁 → 지지육합만 가능). 庚일간 1992-03-15는 寅亥가 합+파 동시라 전부 disq 억제(정상),
#   己일간 1964-07-09는 깨끗한 식상-재 육합이 1년 30건 성립 — 양성 검증용.
def test_opening_siksang_hap_only():
    user = _chart(1964, 7, 9, Gender.FEMALE)
    scored = _scan(user, "opening")
    sik = [s for s in scored if "재(돈)-식상 합" in s.reason]
    assert sik, "개업 재-식상 합 가점일이 1년 내 없음"
    # 구 일반 재-합 문구(비겁·인수가 재와 합해도 가점되던 것)는 개업에서 사라져야 한다.
    assert not any("재(돈) 합(合) — 매우 좋은 날" in s.reason for s in scored), \
        "개업에 구 일반 재-합 가점 잔존(비겁-재 합=뺏김 오판 위험)"


def test_day_combines_star_day_group_filter():
    # day_groups 필터: 필터 없이 합이던 날 중 '식상 합'이 아닌 날은 필터에서 탈락해야 한다.
    user = _chart(1992, 3, 15, Gender.FEMALE)
    any_hap = sik_hap = drop = None
    for i in range(365):
        d = date(2026, 1, 1) + timedelta(days=i)
        ch = build_chart(BirthInput(birth_date=d), with_daewoon=False)
        ds, db = ch.pillars.day.stem, ch.pillars.day.branch
        a = _day_combines_star(ds, db, user, "재")
        s = _day_combines_star(ds, db, user, "재", day_groups=frozenset({"식상"}))
        assert not (s and not a)                   # 필터 결과는 무필터의 부분집합
        any_hap = any_hap or a
        sik_hap = sik_hap or s
        if a and not s:
            drop = d
    assert any_hap and sik_hap, "재 합/식상 합 표본 부재"
    assert drop is not None, "필터가 아무 날도 거르지 않음(무의미)"


# ── 이사·결혼 합 가점은 불변(회귀) ─────────────────────────────────
def test_moving_wedding_hap_unchanged():
    user = _chart(1988, 5, 20, Gender.MALE)
    mv = _scan(user, "moving", days=120)
    assert any("재(돈) 합(合) — 매우 좋은 날" in s.reason for s in mv), "이사 일반 재-합 가점이 사라짐"


# ── 출산: 부모② 명식 영속(상담사 전달) ────────────────────────────
def test_birth_persists_parent2():
    from backend.app.domain.chat_dto import BirthDTO
    from backend.app.services import tool_service

    captured = {}

    def _fake_persist(db, tool, kind, birth, chart, input_json, result_json, user, depth, locale="ko"):
        captured.update(tool=tool, kind=kind, input_json=input_json, result_json=result_json)
        return {"tool_id": "t", "result": result_json}

    orig = tool_service._persist_and_bill
    tool_service._persist_and_bill = _fake_persist
    try:
        tool_service.create_taekil(
            None, BirthDTO(birth_date=date(1990, 3, 15), gender=Gender.MALE),
            "birth", date(2026, 8, 1), 3,
            birth2=BirthDTO(birth_date=date(1992, 7, 20), gender=Gender.FEMALE),
        )
    finally:
        tool_service._persist_and_bill = orig
    p2 = captured["result_json"].get("parent2")
    assert p2 and p2.get("chart"), "출산 부모② 명식 미영속(상담 전달 불가)"
    assert p2["gender"] == "female" and p2["birth_date"] == "1992-07-20"
    # 결혼은 여전히 상대 PII 미영속(기존 정책 유지).
    captured.clear()
    tool_service._persist_and_bill = _fake_persist
    try:
        tool_service.create_taekil(
            None, BirthDTO(birth_date=date(1990, 3, 15), gender=Gender.MALE),
            "wedding", date(2026, 8, 1), 3,
            birth2=BirthDTO(birth_date=date(1992, 7, 20), gender=Gender.FEMALE),
        )
    finally:
        tool_service._persist_and_bill = orig
    assert "parent2" not in captured["result_json"], "결혼에 상대 PII가 영속됨(정책 위반)"


# ── 출산: 상담 소스(kind=birth) 리졸버 — 양 부모 명식 + IDOR ───────
class _FakeDB:
    def __init__(self, row):
        self._row = row

    def get(self, model, key):
        return self._row if key == getattr(self._row, "tool_id", None) else None


def _tool_row(user_id=7, kind="birth", parent2=True):
    ch = _chart(1990, 3, 15, Gender.MALE).model_dump(mode="json")
    p2 = _chart(1992, 7, 20, Gender.FEMALE).model_dump(mode="json")
    from datetime import time as _time
    return SimpleNamespace(
        tool_id="tk-1", tool="taekil", kind=kind, user_id=user_id,
        birth_date=date(1990, 3, 15), birth_time=_time(12, 0), calendar="solar", gender="male",
        chart_json=ch,
        result_json={"parent2": {"chart": p2, "birth_date": "1992-07-20", "birth_time": "12:00",
                                 "calendar": "solar", "gender": "female"}} if parent2 else {},
    )


def test_resolver_birth_returns_both_parents():
    from backend.app.api.consultation import _resolve_source_context
    row = _tool_row()
    ctx = _resolve_source_context(_FakeDB(row), SimpleNamespace(id=7), "birth", "tk-1")
    assert ctx["chart"] and ctx["gender"] == "male"
    assert ctx["parent2"]["chart"] and ctx["parent2"]["gender"] == "female"
    # 부모② 없으면 부모①만(기존과 동일 — 에러 아님).
    ctx1 = _resolve_source_context(_FakeDB(_tool_row(parent2=False)), SimpleNamespace(id=7), "birth", "tk-1")
    assert "parent2" not in ctx1 and ctx1["chart"]


def test_resolver_birth_idor_and_kind_guard():
    from backend.app.api.consultation import _resolve_source_context
    with pytest.raises(HTTPException):            # 비소유
        _resolve_source_context(_FakeDB(_tool_row(user_id=7)), SimpleNamespace(id=99), "birth", "tk-1")
    with pytest.raises(HTTPException):            # 출산이 아닌 택일(결혼) 세션은 전달 불가
        _resolve_source_context(_FakeDB(_tool_row(kind="wedding")), SimpleNamespace(id=7), "birth", "tk-1")
