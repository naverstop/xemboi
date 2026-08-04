# -*- coding: utf-8 -*-
"""P0-1: 엔진이 계산해 둔 십이운성·공망 등을 프롬프트에 주입 (RAG 전수감사 2026-07-22).

engine.build_chart 는 twelve_life·twelve_sinsal·gongmang·napeum·saryeong 을 전부 계산하는데
소비처가 부적 문구와 사후 검증기뿐이라 프롬프트에는 한 줄도 안 들어갔다.
그 결과 3개 명식 전수에서 오답(관대↔장생 뒤바꿈, 공망을 '일주와 시주'로 서술).
'RAG가 명식을 이긴' 게 아니라 결정값이 비어 환각이 빈칸을 메운 유형이다.
"""
from datetime import date

from backend.app.domain.chat_dto import BirthDTO
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput
from backend.app.services.chat_service import _build_saju_summary

CASES = [(date(1986, 3, 5), "10:00"), (date(1990, 3, 21), "09:30")]


def _summary(bd, bt):
    ch = build_chart(BirthInput(birth_date=bd, birth_time=bt))
    s = _build_saju_summary(ch, BirthDTO(birth_date=bd, birth_time=bt, calendar="solar",
                                         gender="male", name="t"))
    return ch, s


def test_twelve_life_and_gongmang_reach_the_prompt():
    for bd, bt in CASES:
        ch, s = _summary(bd, bt)
        assert "십이운성(일간 기준" in s, bd
        # 엔진값이 그대로 실렸는가 — 자리별 배정까지 대조
        for pos, stage in ch.twelve_life.items():
            assert f"{pos}주 {stage}" in s, (bd, pos, stage)
        assert "공망(空亡" in s and "·".join(ch.gongmang) in s, bd
        # 자리로 말하지 말라는 가드(실측 오답: "일주와 시주에 공망이 발생")
        assert "자리로 말하지 말고" in s


def test_other_engine_values_also_injected():
    for bd, bt in CASES:
        ch, s = _summary(bd, bt)
        if ch.twelve_sinsal:
            assert "십이신살(년지 기준" in s
        if ch.napeum:
            assert "납음(納音)" in s
        if ch.saryeong:
            assert "사령(司令)" in s
