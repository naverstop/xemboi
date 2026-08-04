# -*- coding: utf-8 -*-
"""세운/대운 오라벨 + 신분(학교급) 추정 환각 방지 (2026-07-12, 여정 2006-08-10 실측).

실측 환각 2건:
  ① 내년 세운 정미(丁未)를 '내년 대운 (2027년 정미 대운)'으로 오라벨(세운·대운 혼동, 반복 지적).
     프롬프트는 '정미=세운, 내년 대운=갑오(전환 없음)'을 정확히 줬는데도 약한 모델이 혼동,
     _verify_daewoon이 잡아도 재생성이 못 고침 → 결정적 relabel로 마감.
  ② 2006-08-10생(2026년 만19)을 '고등학생으로 추정'. 원인 _life_stage_ko(19)='고등학생'(경계 오류)
     + 사주로 신분을 단정. → 라벨을 신분 비단정으로 교정 + '○○로 추정' 결정적 제거.
"""
from __future__ import annotations

from datetime import date

from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType, Gender
from backend.app.services import chat_service as C


def _yeojeong_cj():
    ch = build_chart(BirthInput(birth_date=date(2006, 8, 10), calendar=CalendarType.SOLAR,
                                gender=Gender.FEMALE))
    cj = ch.model_dump()
    cj.setdefault("input", {})["birth_date"] = "2006-08-10"
    return cj


# ── 문제 1: 나이 라벨·신분 추정 ──
def test_life_stage_no_highschool_for_19():
    """만 19세(2006생, 곧 20세)를 '고등학생'으로 라벨하지 않는다(진학·취업 함께 커버)."""
    assert "고등학생" not in C._life_stage_ko(19)
    assert "고등학생" not in C._life_stage_ko(20)
    label = C._life_stage_ko(19)
    assert "진학" in label and "취업" in label  # 학교 vs 취업 질문을 한쪽으로 편향하지 않음


def test_life_stage_labels_assert_no_identity():
    """어떤 나이대도 특정 학교급/직업 신분을 단정하지 않는다."""
    for a in range(6, 90, 3):
        lab = C._life_stage_ko(a)
        assert "고등학생" not in lab and "대학생" not in lab and "직장인" not in lab


def test_scrub_status_presumption_removes_guess():
    """'현재 나이가 고등학생으로 추정되므로'류 신분 추정 표현을 결정적으로 제거."""
    s = "2027년 정미년의 운기를 살펴보면, 현재 나이가 고등학생으로 추정되므로 학업과 진로를 봅니다."
    out = C._scrub_status_presumption(s)
    assert "추정" not in out and "고등학생" not in out
    assert "학업과 진로를 봅니다" in out  # 나머지 문장 보존


def test_scrub_status_keeps_nonpresumption():
    """추정이 아닌 단순 신분 언급/일반어는 건드리지 않는다."""
    assert C._scrub_status_presumption("대학생 시절의 인연을 봅니다.") == "대학생 시절의 인연을 봅니다."
    assert C._scrub_status_presumption("성격이 활동적입니다.") == "성격이 활동적입니다."


# ── 문제 2: 세운을 대운으로 오라벨 ──
def test_sewoon_mislabeled_as_daewoon_fixed():
    """내년 세운(정미)을 '대운'이라 부른 것을 '세운'으로 결정적 교정(헤더·인라인 모두)."""
    cj = _yeojeong_cj()
    s = "내년 대운 (2027년 정미 대운): 정미 대운은 화와 금의 조화를 이룹니다."
    out = C._fix_sewoon_daewoon_label(s, cj)
    assert "정미 대운" not in out
    assert "정미 세운" in out and "세운 (2027년 정미 세운)" in out


def test_real_daewoon_preserved():
    """실제 대운(갑오)은 '대운'으로 그대로 보존(오탐 0)."""
    cj = _yeojeong_cj()
    s = "현재 대운은 갑오(甲午)이고 21세부터 계사 대운입니다."
    out = C._fix_sewoon_daewoon_label(s, cj)
    assert "갑오(甲午)" in out and "계사 대운" in out
    assert "갑오 세운" not in out and "계사 세운" not in out


def test_ganji_that_is_both_not_touched():
    """세운 간지가 그 사람 대운 목록에도 있으면 모호 → 건드리지 않는다."""
    cj = _yeojeong_cj()
    # 갑오는 여정의 대운(11세~)이자 과거 세운일 수도 → 대운 목록에 있으므로 relabel 제외
    s = "갑오 대운은 활동적입니다."
    assert C._fix_sewoon_daewoon_label(s, cj) == s


def test_verify_daewoon_flags_sewoon_label():
    """검증기는 '정미 대운'을 여전히 불일치로 검출(교정기와 정합)."""
    cj = _yeojeong_cj()
    assert C._verify_daewoon("내년 정미 대운은 좋습니다.", cj)  # 정미 ∉ 대운목록 → 플래그
