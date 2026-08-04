# -*- coding: utf-8 -*-
"""출처 인용 앵무새 차단 + 영어 드리프트 가드 (운영자 지적 2026-08-03).

- RAG 컨텍스트가 모델에 출처명(명리전 2권 p.358)을 주면 약모델이 '자료1·명리전2권 p.358 등을
  종합하면'처럼 그대로 뱉는다 → 컨텍스트에서 출처 제거 + 출력 스크러버 보강.
- 언어 가드(_looks_korean_clean)가 중국어만 잡고 영어 code-switch를 놓쳐 한/영 혼합 답변이
  '심화 보강됨'으로 나갔다 → 영어 문장 덩어리 감지 추가.
"""
from __future__ import annotations

from backend.app.services.chat_service import (
    _looks_korean_clean,
    _scrub_source_refs,
    rag_context_block,
)


class _Chunk:
    def __init__(self, text, source, score=0.5):
        self.text = text
        self.source = source
        self.score = score


# ── 출처 인용 스크럽 ──────────────────────────────────────────────
def test_scrub_numbered_source_and_page_citation():
    s = ("자료1 및 명리전2권 p. 358 등 여러 자료들을 종합하면, "
         "당신은 매우 계획적이고 현실주의적인 사고방식을 갖고 있습니다.")
    out = _scrub_source_refs(s)
    assert out.startswith("당신은 매우 계획적")
    for bad in ("자료1", "명리전2권", "p. 358", "여러 자료", "종합하면"):
        assert bad not in out, f"출처 인용 잔존: {bad}"


def test_scrub_example_prompt_leak():
    out = _scrub_source_refs("예시처럼 '己丑'와 같은 특성이 있듯이, 내심은 단단합니다.")
    assert "예시처럼" not in out and "단단합니다" in out


def test_scrub_preserves_normal_text():
    # 출처 언급이 없는 정상 문장은 그대로.
    s = "당신은 인내심이 강하고 꾸준합니다. 올해는 재물 관리가 중요합니다."
    assert _scrub_source_refs(s) == s


def test_rag_block_hides_source_from_model():
    block = rag_context_block([_Chunk("성격은 안정적이고 꾸준하다.", "명리전 2권 p.358")])
    assert block is not None
    assert "명리전" not in block and "출처" not in block
    assert "성격은 안정적" in block   # 본문은 유지


# ── 영어 드리프트 가드 ────────────────────────────────────────────
def test_english_drift_rejected():
    en = ("따라서 지금은 새로운 일들—특히 이사나 회사를 바꾸기 같은 결정적인 행동—"
          "are not recommended at all for you right now. Instead of chasing after new "
          "opportunities or changes in your life during this period, it would be better to focus.")
    assert _looks_korean_clean(en) is False


def test_korean_with_few_english_words_ok():
    ko = ("올해는 재물운이 대체로 안정적입니다. " * 4
          + "가끔 OK 사인을 주고받는 정도의 가벼운 교류는 무방합니다. "
          + "꾸준함이 강점이니 계획을 세워 차근차근 실행하시길 권합니다.")
    assert _looks_korean_clean(ko) is True


# ── 십성 '뜻' 병기 한자혼입 교정 (동僚·競争 → 동료·경쟁) ──
def test_corrupted_star_gloss_to_korean():
    from backend.app.saju.constants import fix_term_hanja as ft
    out = ft("월간 식신(표현·여유), 월지 비견(동僚·競争)이라는 조합")
    assert "비견(동료·경쟁)" in out and "競争" not in out and "僚" not in out
    assert "식신(표현·여유)" in out   # 이미 정상 한글 뜻은 보존


def test_proper_sipsin_hanja_preserved():
    from backend.app.saju.constants import fix_term_hanja as ft
    # 올바른 십성 한자 병기(比肩/正官)는 뜻으로 바꾸지 않고 보존.
    out = ft("비견(比肩)이 강하고 정관(正官)도 뚜렷하다")
    assert "비견(比肩)" in out and "정관(正官)" in out
