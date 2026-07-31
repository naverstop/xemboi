"""간지→오행 속성 주장 검증 — _verify_ganji_element (전문가 지적 케이스 #3, 2026-07-05).

실측: '화기(火氣)가 강한 월지 갑자(甲子)' — 甲子는 목·수(지장간 壬·癸도 수)로 화기가 없다.
간지의 오행은 결정적(표면+지장간)이라 명식 없이 자기모순을 판정하고, 불일치 시 기존
교정 루프(_correct_branches)가 깨끗한 컨텍스트로 재생성한다. 오탐 0 지향(좁은 앵커).
"""
from __future__ import annotations

from backend.app.services.chat_service import _verify_ganji_element


def test_flags_real_case_forward():
    # 실측 문장 그대로 — 甲子에 화기 없음
    bad = _verify_ganji_element("하지만 화기(火氣)가 강한 월지 갑자(甲子)와의 조화로 인해")
    assert len(bad) == 1
    assert bad[0][1] == "화기"
    assert "甲子" in bad[0][0] and "목·수" in bad[0][0]


def test_flags_reverse_pattern():
    bad = _verify_ganji_element("갑자(甲子) 월주는 화기(火氣)가 강한 편입니다.")
    assert len(bad) == 1 and bad[0][1] == "화기"


def test_passes_surface_element():
    # 癸巳=수·화(표면), 庚午=금·화 — 정상 주장은 불개입
    assert _verify_ganji_element("수기(水氣)가 강한 년지 계사(癸巳)의 영향") == []
    assert _verify_ganji_element("화기(火氣)가 강한 시주 경오(庚午)") == []


def test_passes_hidden_stem_element():
    # 甲戌 지장간 辛·丁·戊 — '화기'는 지장간 丁 근거라 정상 해석으로 통과
    assert _verify_ganji_element("갑술(甲戌) 일주는 화기(火氣)가 강한 면도 있습니다") == []


def test_whole_chart_claim_untouched():
    # '사주 전체'에 대한 서술은 간지 직결이 아니므로 불개입(갭 규칙)
    assert _verify_ganji_element("화기(火氣)가 강한 사주라 갑자(甲子) 대운에는 유의하세요") == []


def test_collective_influence_untouched():
    # 여러 간지·기운을 묶어 말하는 문장(강조어 없음)은 보수적으로 불개입
    assert _verify_ganji_element(
        "갑자(甲子)와 계사(癸巳)는 화기(火氣)와 수기(水氣)의 영향으로 감정이 풍부합니다"
    ) == []


def test_empty_safe():
    assert _verify_ganji_element("") == []
