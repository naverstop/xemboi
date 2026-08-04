# -*- coding: utf-8 -*-
"""동문서답(질문 주제 이탈) 출력측 백스톱 회귀 — _verify_nonresponsive.

실측(2026-07-25): 후속질문 '남자 술주정있을까요'에 '남자친구·연애운' 답변(동문서답).
route_topics()=[] 로 결정적 주제앵커가 없고, 이력(연애 발췌 ~157:1)+QUESTION_FOCUS_RULE 연애
예시가 약한 1차모델을 연애로 끌었다. 입력측(키워드·프롬프트)은 원리상 불완전 → 출력측에서
'질문 핵심어가 답에 전무한가'로 최종 방어한다.

⚠️ 오탐이 정답을 재생성으로 파괴하므로(P2 교훈), ①진성 동문서답은 잡고 ②정상 답변은 절대
안 잡는지를 함께 고정한다. 정상 오분류(false positive)가 진양성만큼 위험하다.
"""
from __future__ import annotations

from backend.app.services.chat_service import (
    _answer_dominant_offtopic,
    _question_salient_terms,
    _strip_q_tail,
    _term_variants,
    _verify_nonresponsive,
)

# 실측 재현: '남자 술주정' 질문에 연애로 흐른 답변(동문서답)
ROMANCE = (
    "이 남자분과의 인연을 보면 남자친구나 연애 운이 생길 수 있는 시기와 가능성이 보입니다. "
    "남자친구와의 인연은 앞으로 더 깊어질 수 있으며, 연애와 결혼운이 함께 흐르는 시기입니다. "
    "인연의 흐름을 보면 좋은 만남이 이어질 수 있습니다. 이성과의 관계에서 설렘이 커지는 시기입니다."
)
# 정상: 술주정을 정면으로 다룬 답변
ADDRESSED = (
    "이 사람은 술을 마시면 주정을 부리는 기질이 있습니다. 편관이 강해 취기가 오르면 다혈질로 "
    "변할 수 있어 음주 자리에서 조심해야 합니다. 술버릇을 스스로 다스리는 노력이 필요합니다."
)
# 정상: 핵심어 대신 동의어(음주·취기·다혈질)로 같은 주제를 다룸
SYN_ONLY = (
    "취기가 오르면 감정 조절이 어려워지는 편입니다. 편관의 기운으로 다혈질 성향이 있어 "
    "음주 자리에서 언성이 높아질 수 있습니다. 절제가 필요하며 관성으로 다스릴 수 있습니다."
)


# ---- 어간 추출 ----
def test_strip_q_tail():
    assert _strip_q_tail("술주정있을까요") == "술주정"
    assert _strip_q_tail("바람기") == "바람기"
    assert _strip_q_tail("주사가") == "주사"


def test_salient_terms_drop_generic_person():
    # '남자'(관계 지시어)는 변별어 아님 → '술주정'만 남아야 그 부재로 동문서답을 잡는다
    assert _question_salient_terms("남자 술주정있을까요") == ["술주정"]
    assert "남자" not in _question_salient_terms("남자 술주정있을까요")


# ---- 진성 동문서답: 반드시 잡는다 ----
def test_flags_romance_drift_for_drinking_question():
    assert _verify_nonresponsive(ROMANCE, "남자 술주정있을까요")


def test_flags_romance_drift_for_violence_question():
    assert _verify_nonresponsive(ROMANCE, "이 사람 바람기 있나요")


# ---- 정상 답변: 절대 안 잡는다(오탐 금지) ----
def test_no_flag_when_addressed():
    assert not _verify_nonresponsive(ADDRESSED, "남자 술주정있을까요")


def test_no_flag_when_synonym_only():
    # 답이 핵심어 대신 동의어로 주제를 다루면 정상 — 넉넉한 변형 매칭으로 오탐 방지
    assert not _verify_nonresponsive(SYN_ONLY, "남자 술주정있을까요")


def test_no_flag_short_answer():
    # 짧은 답/명료화(<80자)는 면제 — 재생성 헛돎 방지
    assert not _verify_nonresponsive("네, 조금 있을 수 있으니 조심하세요.", "남자 술주정있을까요")


def test_flags_three_sentence_drift_over_80_chars():
    # 임계 경계(≈115자) — 3문장급 연애 드리프트도 잡는다(종전 120자 임계에선 놓쳤음)
    drift = ("이 남자분과의 인연을 보면 남자친구나 연애 운이 생길 수 있는 시기입니다. 남자친구와의 "
             "인연은 앞으로 깊어질 수 있고 연애와 결혼운이 함께 흐릅니다. 좋은 만남이 이어질 수 있습니다.")
    assert 80 <= len(drift) < 130
    assert _verify_nonresponsive(drift, "남자 술주정있을까요")


def test_no_flag_comprehensive_request():
    # '전체/종합' 요청이면 집중 대상 아님 → 면제
    assert not _verify_nonresponsive(ROMANCE, "전체적으로 술주정 포함 다 풀어주세요")


def test_no_flag_normal_personality_answer():
    ans = ("성향을 보면 고집이 있고 기질이 강합니다. 대인관계에서 리더십이 있으나 예민한 면도 "
           "있습니다. 성정이 곧아 신뢰를 얻습니다. 십성으로 보면 비겁이 강한 구조입니다.")
    assert not _verify_nonresponsive(ans, "이 사람 성격 어때요")


def test_no_flag_when_no_salient_term():
    # 변별 핵심어를 못 뽑으면(의문사·조사뿐) 검출 자체를 건너뜀(안전)
    assert not _verify_nonresponsive(ROMANCE, "어때요")


def test_no_flag_when_topic_matches_asked():
    # 연애를 실제로 물었으면 연애 답변은 동문서답 아님(질문 주제=답변 주제)
    assert not _verify_nonresponsive(ROMANCE, "남자친구 언제 생겨요")


# ---- 이중 게이트: 핵심어 부재 + 다른 주제 지배가 함께여야 플래그 ----
def test_double_gate_requires_offtopic_domination():
    # 핵심어는 없지만 특정 라우팅 주제로 지배되지도 않은 밋밋한 답 → 플래그 안 함(오탐 방지)
    bland = ("타고난 기운의 균형을 보면 무난한 흐름입니다. 큰 굴곡 없이 안정적으로 지내실 수 "
             "있으며, 주변과의 관계도 원만하게 유지되는 편입니다. 꾸준함이 강점입니다.")
    assert not _answer_dominant_offtopic(bland, "남자 술주정있을까요")
    assert not _verify_nonresponsive(bland, "남자 술주정있을까요")


def test_term_variants_generous():
    v = _term_variants("술주정")
    assert "음주" in v and "주사" in v and "술주" in v  # 동의어 + 2자 어간
