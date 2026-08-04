# -*- coding: utf-8 -*-
"""꿈해몽 상징 사전 회귀 테스트.

배경: 이 메뉴는 결정적 엔진도 없고 코퍼스도 실질 0건인데 DREAM_SYSTEM 은
"전통 해몽에서 그 상징을 어떻게 보는지 설명하라"고 요구했다 — 근거를 하나도 주지 않으면서.
저장본 50건 중 존재하지 않는 문헌 인용이 2건 나왔다.
"""
from __future__ import annotations

import pytest

from backend.app.services import dream_symbols as D


# ── 매칭 정확도 — 1음절 키의 파생어 오매칭이 이 프로젝트의 반복 사고다 ──────
@pytest.mark.parametrize("text,expect", [
    ("돼지가 집으로 들어오는 꿈을 꿨어요", "돼지"),
    ("바다에서 큰 물고기를 잡는 꿈", "물고기"),
    ("용이 승천하는 꿈", "용"),
    ("이가 빠지는 꿈을 꿨어요", "이가 빠지는"),
    ("커다란 구렁이가 몸을 감는 꿈", "뱀"),
    ("호랑이가 방으로 들어왔어요", "호랑이"),
])
def test_matches_expected_symbol(text, expect):
    assert expect in [s["key"] for s in D.match(text)]


@pytest.mark.parametrize("text", [
    "회사에서 사용하는 프로그램이 나오는 꿈",     # '사용' 의 용
    "용기를 내는 꿈을 꿨어요",                  # '용기' 의 용
    "용서를 구하는 꿈",                        # '용서'
    "말씀을 나누는 꿈",                        # '말씀'
])
def test_no_false_match_on_derived_words(text):
    """'형성합니다'→'형성관계니다', '수호(守護)'→'수호(秀浩)' 같은 사고가 반복됐다.
    낱말 경계로 막는다 — 앞은 한글이 아니어야 하고 뒤는 조사 하나까지만 허용한다."""
    assert D.match(text) == [], f"파생어에 오매칭: {text}"


def test_match_is_capped():
    """전량 주입 금지 — 타로도 78장 중 뽑힌 카드만 넣는다(프롬프트 예산)."""
    text = "용과 호랑이와 돼지와 뱀과 물고기와 말과 토끼가 나오고 이가 빠지는 꿈"
    assert len(D.match(text)) <= D.MAX_SYMBOLS


# ── 데이터 무결성 ────────────────────────────────────────────────────
def test_every_symbol_has_source_and_tier():
    """근거 없는 상징 해석이 유료 답변에 확정 사실로 나간 전례가 있다."""
    cats = set(D._data()["meta"]["categories"])
    for s in D.symbols():
        assert s.get("source"), f"출처 없음: {s.get('code')}"
        assert s.get("tier") in (1, 2), f"티어 없음/잘못됨: {s.get('code')}"
        assert s.get("category") in cats, f"공식 8분류 밖: {s.get('category')}"
        assert s.get("polarity") in ("길", "흉", "중립", "맥락의존")
        assert len(s.get("interp") or "") <= 400


def test_no_single_gender_field():
    """태몽 성별을 단일 값으로 저장하면 LLM 이 반드시 그걸 단정한다.

    백과사전이 지역·기준 충돌을 **결함이 아니라 특징으로** 기술하므로 1:1 매핑 자체가
    전통 왜곡이다(애호박=형태는 아들·색은 딸)."""
    for s in D.symbols():
        assert "gender" not in s, f"단일 성별 필드가 생겼다: {s['code']}"
    gl = D.gender_lore()
    assert gl.get("conflict_examples"), "충돌 사례가 없으면 '두 갈래' 서술을 못 한다"
    assert "의학적 근거" in (gl.get("disclaimer") or "")


# ── 프롬프트 블록 ────────────────────────────────────────────────────
def test_context_block_none_when_nothing_matches():
    """None 이어야 has_sources=False 로 이어져 '자료가 없습니다' 쪽 문구가 붙는다.
    빈 문자열을 돌려주면 '없는 자료를 따르라'는 유령 지시가 된다."""
    assert D.context_block("아무 상관 없는 이야기입니다") is None


def test_context_block_restricts_to_dictionary():
    b = D.context_block("돼지가 들어오는 꿈")
    assert b and "여기 없는 것을" in b and "말하지 마세요" in b


def test_taemong_block_forbids_gender_assertion():
    b = D.context_block("용이 승천하는 태몽을 꿨어요. 아들일까요?")
    assert b
    assert "단정하지 말고" in b
    assert "의학적 근거는 없습니다" in b
    assert "두 갈래" in b


def test_tier2_marked_in_block():
    """같은 국가 사전 안에도 '민속 채록'과 '현대 해몽서 재정리'가 섞여 있다 — 층을 표시한다."""
    b = D.context_block("뱀이 나오는 꿈")
    assert b and "현대 해몽서" in b


def test_block_size_bounded():
    """브리핑 비대로 답변이 잘린 전례가 있다(프롬프트 예산)."""
    text = "용과 호랑이와 돼지와 뱀이 나오는 태몽을 꿨어요"
    assert len(D.context_block(text) or "") < 2500


# ── 성별 단정 검증기 ─────────────────────────────────────────────────
@pytest.mark.parametrize("bad", [
    "이 꿈은 아들일 것입니다.",
    "성별은 아들입니다.",
    "딸을 낳으시겠어요.",
    "여아일 가능성이 매우 높습니다.",
])
def test_gender_assertion_detected(bad):
    assert D.verify_no_gender_claim(bad)


@pytest.mark.parametrize("ok", [
    "전통에서는 아들로도 딸로도 풀었습니다. 어느 쪽으로도 단정할 수 없어요.",
    "전통에서는 아들 쪽으로 보기도 했지만 의학적 근거는 없습니다.",
    "기준에 따라 두 갈래로 갈립니다.",
    "돼지꿈은 재물이 들어온다고 봅니다.",
])
def test_gender_hedged_or_irrelevant_passes(ok):
    """'전통에서는 아들로 보았지만 단정할 수 없다'는 정상 서술이다 — 오탐하면 안 된다."""
    assert D.verify_no_gender_claim(ok) == []


# ── 배선 ─────────────────────────────────────────────────────────────
def test_wired_into_both_dream_paths():
    """첫 풀이와 후속질문이 같은 자료를 받아야 한다 — 한쪽만 주면 그쪽에서만 지어낸다."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    assert "dream_symbols.context_block(" in (root / "backend/app/api/dream.py").read_text(encoding="utf-8")
    assert "_ds.context_block(" in (root / "backend/app/services/tool_service.py").read_text(encoding="utf-8")


def test_dream_system_has_sensitive_guards():
    """타로에는 있는 의료·민감 주제 가드가 DREAM_SYSTEM 에는 없었다.
    꿈 상징 사전은 죽음·임신·병 항목을 담게 되므로 공백이 곧바로 노출된다."""
    from backend.app.services.tool_service import DREAM_SYSTEM as S

    assert "병명" in S and "진단" in S
    assert "성별을" in S and "단정하지 마세요" in S
    assert "현대적 부가 해석" in S, "사주-꿈 연결이 전통인 것처럼 서술되면 안 된다"


# ── 감수 재확인 (2026-07-22) ─────────────────────────────────────────
def test_tiger_two_separate_conditions():
    """원문은 별개 조항 둘이다 — ①마구 날뛰면 불미스러운 일 ②크게 두려웠으면 대개 흉몽.
    1차 작성에서 '마구 날뛰어 크게 두려웠다면'으로 **결합 조건**처럼 좁혀 적었다."""
    t = next(s for s in D.symbols() if s["code"] == "animal-tiger")["interp"]
    assert "마구 날뛰는 꿈은" in t
    assert "크게 두려움을 느꼈다면" in t


@pytest.mark.parametrize("code", ["animal-rabbit", "animal-horse"])
def test_tier2_symbols_have_real_interpretation(code):
    """'표제어가 실려 있습니다'만 적혀 서비스에서 죽은 항목이었다 — 실제 해석을 담아야 한다."""
    s = next(x for x in D.symbols() if x["code"] == code)
    assert "표제어가" not in s["interp"], "메타 설명이 아니라 해석을 넣어야 한다"
    assert len(s["interp"]) >= 80


def test_official_categories_are_covered():
    """파일 스스로 8분류를 공식 체계로 선언해 놓고 5개 분류가 비어 있었다."""
    cats = {s["category"] for s in D.symbols()}
    for c in ("인체", "인사", "자연물", "가옥", "기물", "동물", "식물"):
        assert c in cats, f"'{c}' 분류에 항목이 하나도 없다"


@pytest.mark.parametrize("text,expect", [
    ("불이 났어요", "불"),
    ("돌아가신 할머니가 상을 차려주는 꿈", "조상"),
    ("거울이 깨졌습니다", "거울"),
    ("큰 나무에 올라가는 꿈", "나무"),
    ("상여를 봤어요", "상여"),
    ("똥을 뒤집어쓰는 꿈", "똥"),
    ("물이 넘치는 꿈", "물"),
])
def test_new_symbols_match(text, expect):
    assert expect in [s["key"] for s in D.match(text)]


@pytest.mark.parametrize("text", [
    "불편했어요", "물건을 샀어요", "나무라는 소리", "상여금을 받았어요",
    "나는 학생입니다", "말씀을 나누는 꿈",
])
def test_new_symbols_no_false_match(text):
    """상징을 늘리면 오매칭 위험도 같이 는다 — 낱말 경계가 여전히 지켜져야 한다."""
    assert D.match(text) == [], f"오매칭: {text}"


@pytest.mark.parametrize("text", [
    "하늘을 나는 꿈", "하늘로 날아오르는 꿈", "하늘에 올라가는 꿈", "이빨이 빠졌어요",
])
def test_stem_aliases_match_conjugations(text):
    """별칭이 용언 어간이면 뒤에 어미가 자유롭게 붙는다('하늘로 오르'+'아오르는').
    조사 하나로 묶으면 활용형을 통째로 놓친다."""
    assert D.match(text), f"활용형을 놓쳤다: {text}"
