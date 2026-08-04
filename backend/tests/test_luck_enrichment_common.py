# -*- coding: utf-8 -*-
"""Phase 2 공용 풍부화 회귀 고정 — 상담·전 tool 추가질문의 월별 십성·합충 관계 병기.

한 곳(_current_luck_block)의 확장이 상담 본해설·추가질문 + 전 tool 메뉴 추가질문
(_aux_ganji_blocks 경유)을 전부 커버한다. 신년운세(61a1f3a1)와 동일 원칙·동일 공용 모듈
(saju/relations.py — 육합·충·형·파는 감수된 gwanbeop 재사용, 반합·원진·해는 확장).
관법 시기 스코프(내년·회고 질문에 올해 공식 주입되던 자기모순)도 함께 고정.
"""
from __future__ import annotations

from datetime import date

from backend.app.saju import relations as R
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType, Gender
from backend.app.services import chat_service as C


def _cj():
    ch = build_chart(BirthInput(birth_date=date(2006, 8, 10), calendar=CalendarType.SOLAR,
                                gender=Gender.FEMALE))  # 지지: 戌申未, 일간 辛
    return ch.model_dump(mode="json")


# ── 공용 관계 모듈 ──
def test_extended_pair_relations():
    """확장 관계: 원진·해·반합 검출 + 같은 글자 반합 가드(궁합 오판 계열 재발 방지)."""
    assert {"원진", "해"} <= R.pair_branch_relations_ext("子", "未")
    assert "반합" in R.pair_branch_relations_ext("寅", "午")      # 인오술 중 2자
    assert "반합" not in R.pair_branch_relations_ext("午", "午")  # 같은 글자 가드
    assert "충" in R.pair_branch_relations_ext("子", "午")        # 기본 관계 유지(감수 엔진)


def test_scope_label_parameterized():
    """라벨 파라미터화 — '오늘' 스코프의 운(運) 쪽 표기가 '월간/월지'로 오라벨되지 않는다.

    (내 명식 궁위 라벨 '내 월지(사회·직장궁)'는 정당 — 검사 대상은 각 행의 운 쪽 접두뿐.)"""
    cj = _cj()
    rels = R.luck_natal_relations(cj, "辛", "卯", scope="오늘")
    assert rels
    assert all(r.startswith("오늘 ") for r in rels)            # 운 쪽 접두 = '오늘 지지/오늘 천간'
    assert not any(r.startswith(("월지 ", "월간 ")) for r in rels)


def test_relations_accept_dict_and_chart():
    """chart_json(dict)과 SajuChart 양쪽 입력 지원(상담=dict, 신년운세=SajuChart)."""
    ch = build_chart(BirthInput(birth_date=date(2006, 8, 10), calendar=CalendarType.SOLAR,
                                gender=Gender.FEMALE))
    a = R.luck_natal_relations(ch, "乙", "未", scope="월")
    b = R.luck_natal_relations(ch.model_dump(mode="json"), "乙", "未", scope="월")
    assert a == b and a


# ── 상담 월별 표 풍부화 ──
def test_chat_month_table_enriched_with_chart():
    """명식이 있으면 월별 표에 십성·관계·궁위가 병기된다(상담+전 tool 추가질문 공용)."""
    blk = C._current_luck_block(question="올해 운세 월별로", chart_json=_cj())
    assert "십성" in blk and "관계:" in blk
    # [2026-07-22 운영자 "쉽게"] 궁위 라벨을 쉬운 말로 바꿨다 — '월지(사회·직장궁)' → '사회·직장 자리'
    assert "자리" in blk
    assert "관계: 없음" in blk or "관계:" in blk
    assert "지어내지 마세요" in blk          # 환각 금지 지시 유지


def test_chat_month_table_plain_without_chart():
    """명식이 없으면 종전 간지 표 그대로(무회귀 — 비로그인/레거시 세션)."""
    blk = C._current_luck_block(question="올해 운세 월별로")
    assert "[월별 간지(달력" in blk and "십성" not in blk


def test_mixed_scope_includes_both_years():
    """'올해 말과 내년 초' 혼합 질문 — 올해 잔여 달과 내년 12개월이 함께 주입(근거 소실 방지)."""
    td = date.today()
    blk = C._current_luck_block(question="올해 말과 내년 초 이사운을 월별로", chart_json=_cj())
    assert f"{td.year}년 12월" in blk and f"{td.year + 1}년 1월" in blk


# ── 관법 시기 스코프 ──
def test_gwanbeop_retro_scope_label():
    """회고 질문(2023년)엔 그 해 세운으로 성립판정 + '2023년 세운' 라벨(올해 공식 주입 금지)."""
    g = C._gwanbeop_block_for("2023년 사업운은 어땠을까요", _cj(), False)
    if g:  # 룰 성립 시(sparse — 이 명식은 성립 확인됨)
        assert "2023년 세운" in g and "올해 세운" not in g


def test_gwanbeop_current_scope_unchanged():
    """올해 질문은 종전대로 올해 세운+이번 달 월운 스코프(무회귀)."""
    g = C._gwanbeop_block_for("올해 사업운 어때요", _cj(), False)
    if g:
        assert "2023년" not in g and "2027년" not in g
