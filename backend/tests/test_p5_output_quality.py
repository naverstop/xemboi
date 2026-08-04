# -*- coding: utf-8 -*-
"""P5 답변 품질 후처리 회귀 (전수감사 2026-07-29).

- P5-a enforce_easy_gloss: 십성 '나열(2개+ /,、 연결)'에만 생활어 뜻 1회 병기(산문 단독·'·'복합 미개입).
- P5-b _strip_copied_table_lines: '- **십성**: 정관/겁재'처럼 값이 십성명뿐인 근거표 라벨덤프만 제거(문장 보존).
- P5-c _strip_md_rules: 헤딩 '#' 뒤 공백 보장을 공통 체인(fix_term_hanja)에 통합(tool/compat/tarot 저장본까지).

⚠️ 유료 답변이라 '과잉병기·오삭제 0'이 핵심 — 정상 답변을 어수선하게 만들면 안 된다(실측 캘리브레이션 근거).
"""
from __future__ import annotations

from backend.app.saju.constants import (
    enforce_easy_gloss,
    fix_term_hanja,
)


# ---- P5-a: 십성 나열 병기 ----
def test_gloss_applies_to_list():
    assert enforce_easy_gloss("정관, 겁재, 식신이 강합니다") == \
        "정관(직장·책임), 겁재(동업·지출), 식신(표현·여유)이 강합니다"
    # 한자 병기 항목은 이중괄호 없이 안에 삽입
    assert enforce_easy_gloss("정관(正官)/겁재(劫財)") == "정관(正官, 직장·책임)/겁재(劫財, 동업·지출)"


def test_gloss_skips_prose_and_single_and_middot():
    # 산문 중 단독 십성 — 미개입(모델이 곧 풀이)
    assert enforce_easy_gloss("정관이 강해 직장운이 좋습니다") == "정관이 강해 직장운이 좋습니다"
    # '·'(가운뎃점) 복합 지칭 — 미개입(나열 아님)
    assert enforce_easy_gloss("정관·정재 위주의 사주") == "정관·정재 위주의 사주"
    # 십성 없음 — 불변
    assert enforce_easy_gloss("리더십이 있고 재물운이 좋습니다") == "리더십이 있고 재물운이 좋습니다"


def test_gloss_idempotent_and_no_double_gloss():
    once = enforce_easy_gloss("정관, 겁재가 강합니다")
    assert enforce_easy_gloss(once) == once                       # 멱등
    # 이미 뜻 병기가 있는 런은 통째 skip
    assert enforce_easy_gloss("정관(직장·책임), 겁재가 강합니다") == "정관(직장·책임), 겁재가 강합니다"


def test_gloss_hardening_no_double_paren_no_midword_no_nesting():
    # (순환검증 잠복결함 하드닝) — 실 DB 0건이었지만 합성으로 재현되던 3케이스 방어 확인
    # ① 나열 뒤 항목이 이미 뜻 병기 → 통째 skip(이중괄호 '(뜻)(뜻)' 방지)
    assert enforce_easy_gloss("정관, 겁재(동업·지출)가 강함") == "정관, 겁재(동업·지출)가 강함"
    # ② 앞이 한글이면 선두항 mid-word 오병기 방지('부정관…')
    assert enforce_easy_gloss("부정관, 식신이 나타남") == "부정관, 식신이 나타남"
    # ③ 괄호 라벨 안 나열은 미개입(괄호 중첩 방지)
    assert enforce_easy_gloss("자식 (정관, 편관):") == "자식 (정관, 편관):"


# ---- P5-b: 근거표 라벨덤프 제거(문장 보존) ----
def test_strip_tengod_dump_line():
    out = fix_term_hanja("### 3월\n- **십성**: 정관(正官)/겁재(劫財)\n- 흐름: 재물운이 좋습니다")
    assert "십성**: 정관" not in out and "십성: 정관" not in out    # 덤프행 제거
    assert "흐름" in out                                           # 서술은 보존


def test_strip_preserves_prose_label_lines():
    # 값이 문장이면 라벨행이어도 보존(오삭제 방지가 P5-b 핵심)
    assert "재물을 뜻하는" in fix_term_hanja("십성: 재물을 뜻하는 정재가 강합니다")
    assert "안정적 수입" in fix_term_hanja("- **십성**: 정재는 안정적 수입을 뜻합니다")


# ---- P5-c: 헤딩 공백 공통 체인 통합 ----
def test_heading_space_in_common_chain():
    assert fix_term_hanja("####9월(정유월):").startswith("#### 9월")
    assert fix_term_hanja("### 8월 좋습니다") == "### 8월 좋습니다"   # 이미 공백 → 불변


def test_fix_term_hanja_idempotent_full():
    src = "### 3월\n- **십성**: 정관(正官)/겁재(劫財)\n정관, 겁재가 강하고 재물운이 좋습니다\n####4월"
    once = fix_term_hanja(src)
    assert fix_term_hanja(once) == once
