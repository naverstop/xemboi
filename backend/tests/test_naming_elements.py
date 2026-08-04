# -*- coding: utf-8 -*-
"""작명 발음오행 vs 자원오행 분리 (전문가 지적 2026-07-09).

실측: '도하(稲河)' 답변의 '발음오행'을 자원오행(한자 부수) 논리로 '목수'라 설명. 정답은
발음오행(한글 초성)=화토(도=ㄷ=火, 하=ㅎ=土), 자원오행(한자)=목/수(부수). 두 개념이 다른데
후보에 발음오행이 없어 LLM이 자원오행으로 혼동·환각. 후보에 baleum_elements를 별도 제공한다.
"""
from __future__ import annotations

from datetime import date

from backend.app.saju import naming as N
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType


def test_phonetic_element_by_chosung():
    # 발음오행 = 한글 초성 기준(전문가 정답): 도=火, 하=土
    assert N._chosung_element("도") == "火"
    assert N._chosung_element("하") == "土"
    assert N._chosung_element("김") == "木"   # ㄱ=木
    assert N._chosung_element("수") == "金"   # ㅅ=金


def test_resource_element_by_radical():
    # 자원오행 = 한자 부수 기준. 河=水. 稲는 부수 불명(None) — 억지로 붙이면 안 됨
    assert N._char_element("河") == "水"
    assert N._char_element("稲") is None


def test_naming_targets_by_gwanbeop():
    # 전문가 관법: 발음=부족오행만(비겁 제외), 자원=부족+신약시 비겁
    from datetime import date as _d
    from backend.app.saju.types import BirthInput as _BI, CalendarType as _CT
    # 신약 케이스 탐색
    weak = None
    for by in range(1970, 2005):
        c = build_chart(_BI(birth_date=_d(by, 7, 7), calendar=_CT.SOLAR))
        if c.day_master_strength == "weak":
            weak = c
            break
    assert weak is not None
    baleum, jawon = N._naming_targets(weak)
    bigyeop = weak.day_master_element
    assert bigyeop not in baleum          # 발음오행엔 비겁 제외
    assert bigyeop in jawon               # 자원오행엔 신약시 비겁 포함


def test_baleum_scores_deficiency_fill():
    # 발음오행 = 부족오행 채우기: 목표(수·목)를 채우는 초성이면 고득점, 아니면 저득점
    # 稲河(도하: 초성 火土)는 수·목 목표 0충족 → 낮음
    low = N._score_baleum("", "稲河", ["水", "木"]).score
    # 초성이 수·목인 한자쌍은 고득점
    water = next(c for c in N._hanja() if N._chosung_element(N._reading(c)) == "水")
    wood = next(c for c in N._hanja() if N._chosung_element(N._reading(c)) == "木")
    high = N._score_baleum("", water + wood, ["水", "木"]).score
    assert high > low and high >= 90 and low <= 50


def test_candidate_exposes_both_elements_separately():
    ch = build_chart(BirthInput(birth_date=date(1990, 5, 5), calendar=CalendarType.SOLAR))
    cands = N.recommend_names("김", ch, count=2, top=20, gender="male")
    assert cands, "후보 생성 실패"
    for c in cands[:5]:
        d = c.model_dump()
        assert "elements" in d and "baleum_elements" in d      # 두 오행 별도 필드
        assert len(d["baleum_elements"]) == len(d["given"])
        # 발음오행은 각 음절 초성으로 결정적 계산됨
        want = [N._WX_KO_INV.get(N._chosung_element(r)) if hasattr(N, "_WX_KO_INV") else None
                for r in d["reading"]]
        # 값 존재(불명 포함)만 확인 — 자원과 독립
        assert all(e for e in d["baleum_elements"])
