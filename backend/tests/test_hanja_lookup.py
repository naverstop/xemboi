# -*- coding: utf-8 -*-
"""개명 한자 조회 — 24개 절단으로 '내 이름 한자가 목록에 없다' (2026-07-10 전문가 지적).

실측: /api/tools/hanja 가 lookup_by_reading 기본 limit=24 로 호출돼, 사전에 107자(구)·105자(기)·
88자(수)가 있어도 24자만 노출됐다. 120개 음절이 24 초과 → 본인 한자를 못 골라 개명 진행 불가.
"""
from __future__ import annotations

from backend.app.saju import naming as N


def test_truncation_was_real():
    """24 절단이 실제로 다수 음절에서 발생했음(회귀 근거)."""
    over = [r for r in ("구", "기", "수", "정", "전", "조", "주") if len(N.lookup_by_reading(r, limit=500)) > 24]
    assert len(over) >= 5, "절단 대상 음절 표본 부족"


def test_lookup_returns_all_when_limit_raised():
    """limit 을 올리면 사전 보유량 전부 반환되어야 한다(본인 한자 선택 가능)."""
    for r in ("구", "기", "수", "정"):
        few = N.lookup_by_reading(r, limit=24)
        many = N.lookup_by_reading(r, limit=200)
        assert len(few) == 24
        assert len(many) > 24, f"{r}: limit 상향이 반영되지 않음"


def test_api_default_limit_is_generous():
    """API 기본 limit 이 24 로 되돌아가면(회귀) 여기서 깨진다."""
    import inspect

    from backend.app.api import tools as tools_api
    sig = inspect.signature(tools_api.hanja_lookup)
    assert sig.parameters["limit"].default >= 100


def test_pure_korean_syllables_have_no_hanja():
    """순우리말 음절(늘·봄·솜·샘·빛·든)은 한자가 없다 — 한글 이름 개명 미지원의 근거."""
    for s in ("늘", "봄", "솜", "샘", "빛", "든"):
        assert N.lookup_by_reading(s, limit=200) == [], f"{s}: 한자가 생겼다면 정책 재검토"
