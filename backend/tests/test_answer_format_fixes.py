# -*- coding: utf-8 -*-
"""답변 서식·간지 표기 결함 회귀 (2026-07-28 실측 스크린샷).

① '####9월'처럼 # 뒤 공백 없는 헤딩이 날것 노출 → _tidy_markdown 공백 보장(+ 프론트 HEADER_RE).
② 간지 한자 노출 '庚子月' → '경자월'.
을해버그: 대운 '‘乙亥’(음해)' — 乙(을)을 '음'으로 환각. 닫는 따옴표가 껴 기존 교정기가 미스했다.
③ 월별만 나열하고 마무리 없이 끊김 → CONSULTANT_STYLE_RULE 마무리 문단 강제.

⚠️ 년/월 간지는 절대 틀리면 안 되는 기본 정보(운영자 강조) — 오출력 결정적 교정 + 정상 표기 오탐0.
"""
from __future__ import annotations

from backend.app.saju.constants import fix_term_hanja
from backend.app.services.chat_service import CONSULTANT_STYLE_RULE, _tidy_markdown


# ---- 을해버그: 간지 한자(오독한글) → 정독. 닫는 따옴표 변형 전부 ----
def test_ganji_reading_hallucination_fixed_all_quote_styles():
    assert fix_term_hanja("乙亥(음해)") == "乙亥(을해)"
    assert fix_term_hanja("'乙亥'(음해)") == "'乙亥'(을해)"          # 직선 따옴표
    assert fix_term_hanja("‘乙亥’(음해)") == "‘乙亥’(을해)"          # 곡선 따옴표(실제 DB #1057)
    assert fix_term_hanja("대운 “乙亥”(음해)에 들어") == "대운 “乙亥”(을해)에 들어"


def test_ganji_reading_other_stems():
    # 乙→을(음 아님), 癸→계(귀 아님) 등 결정적 정독 강제
    assert fix_term_hanja("癸巳(귀사)") == "癸巳(계사)"
    assert fix_term_hanja("‘甲子’(갑자)") == "‘甲子’(갑자)"          # 정확하면 불개입


# ---- ② 순수 한자 간지+단위 → 한글 ----
def test_bare_ganji_unit_to_korean():
    assert fix_term_hanja("12월 (庚子月)") == "12월 (경자월)"
    assert fix_term_hanja("庚子月") == "경자월"
    assert fix_term_hanja("乙亥년") == "을해년"
    assert fix_term_hanja("丁酉日") == "정유일"


# ---- 오탐 금지: 명식표('한글(한자)')·이름·오행·정상 표기 보존 ----
def test_ganji_fix_no_false_positive():
    assert fix_term_hanja("년주 을해(乙亥)") == "년주 을해(乙亥)"      # 명식표 보존
    assert fix_term_hanja("일간 갑(甲)") == "일간 갑(甲)"
    assert fix_term_hanja("이름은 乙未(을미)라 좋다") == "이름은 乙未(을미)라 좋다"
    assert fix_term_hanja("정유월 무술월 기해월") == "정유월 무술월 기해월"  # 이미 한글
    assert fix_term_hanja("金水가 부족") == "金水가 부족"             # 오행 병렬(간지 아님)


# ---- ① 헤딩 '#' 뒤 공백 보장(무손실, 레벨 보존) ----
def test_tidy_markdown_ensures_heading_space():
    assert _tidy_markdown("####9월(정유월):") == "#### 9월(정유월):"
    assert _tidy_markdown("#머리말") == "# 머리말"
    assert _tidy_markdown("### 8월 정상") == "### 8월 정상"          # 이미 공백 → 불변
    assert _tidy_markdown("## 이미 공백") == "## 이미 공백"


def test_tidy_markdown_lossless_content():
    # 내용(글자)은 절대 지우지 않는다 — 공백만 삽입
    src = "####12월(庚子月):\n· 사회적으로 인정받는 시기입니다."
    out = _tidy_markdown(src)
    assert "12월" in out and "사회적으로 인정받는 시기입니다." in out
    assert out.startswith("#### 12월")


# ---- ③ 마무리 강제 규칙 ----
def test_consultant_rule_requires_closing():
    assert "마무리" in CONSULTANT_STYLE_RULE
    assert "끝내면 안" in CONSULTANT_STYLE_RULE or "끝내지 말고" in CONSULTANT_STYLE_RULE


# ---- '내일 운세 풀이 시작' 필러 헤더 제거 (연운에 '내일' 오출력, 실측 신년운세 #327·#329) ----
def test_strip_reading_start_filler():
    assert fix_term_hanja("### 내일 운세 풀이 시작\n\n올해 세운 병오는").lstrip() == "올해 세운 병오는"
    assert fix_term_hanja("## 오늘의 운세 풀이를 시작합니다\n본문입니다").lstrip() == "본문입니다"
    assert "내일" not in fix_term_hanja("### 내일 운세 풀이 시작  \n내 일간 을(乙)은 목").split("\n")[0]


def test_reading_filler_no_false_positive():
    # '운세를 풀이하면…'·'운세 풀이하면…' 정상 서술은 보존(시작/들어가 뒤에만 발동)
    assert fix_term_hanja("올해 운세를 풀이하면 재물운이 좋습니다") == "올해 운세를 풀이하면 재물운이 좋습니다"
    assert fix_term_hanja("이 운세는 시작이 좋습니다") == "이 운세는 시작이 좋습니다"
