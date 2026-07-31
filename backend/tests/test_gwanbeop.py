# -*- coding: utf-8 -*-
"""관법(觀法) 룰 엔진 — 선생님 공식의 결정적 적용 (할루시 검증 케이스 #4).

테스트 명식은 선생님 자료의 실제 예제를 그대로 사용:
- 회사승진_사례: 己巳년 丙寅월 甲寅일 庚午시, 세운 辛丑 → 승진 명단 포함(관·식상 합 + 재 온전)
- 세운분석보연3: 壬戌년 癸卯월 丙戌일 丙申시, 세운 丁酉 → 卯酉冲으로 인수·재 깨짐(계약 안 된다)
"""
from __future__ import annotations

from backend.app.saju.gwanbeop import (
    build_facts,
    gwanbeop_block,
    load_rules,
    match_rules,
    route_topics,
)


def _chart(y, m, d, h=None):
    def _p(gz):
        return {"stem": gz[0], "branch": gz[1]} if gz else None
    return {"pillars": {"year": _p(y), "month": _p(m), "day": _p(d), "hour": _p(h)}}


# 회사승진_사례 EX 명식 (일간 甲)
PROMO_CHART = _chart("己巳", "丙寅", "甲寅", "庚午")
# 세운분석보연3 첫 명식 (일간 丙)
CONTRACT_CHART = _chart("壬戌", "癸卯", "丙戌", "丙申")


def test_route_topics():
    assert "promotion" in route_topics("올해 승진 될까요?")
    assert "contract" in route_topics("집을 내놨는데 매매 계약 언제 될까요?")
    assert route_topics("오늘 기분이 그냥 그래요") == []


def test_promotion_case_from_teacher_example():
    # 세운 辛丑: 辛(정관)이 丙(식신)과 丙辛합, 丑(정재)은 원국 지지와 충·형·파 없음
    f = build_facts(PROMO_CHART, "辛", "丑")
    assert "관" in f.in_seun and "재" in f.in_seun
    assert frozenset({"관", "식상"}) in f.hap_pairs      # 丙辛합
    assert "재" not in f.broken                            # 丑 온전
    matched = match_rules(["promotion"], f, include_unreviewed=True)
    assert any(r["id"] == "promo-04" for r in matched)     # 승진 명단 포함 조건 성립
    # 시험 룰(관·식상 합)도 같은 관계로 성립
    matched_exam = match_rules(["exam"], f, include_unreviewed=True)
    assert any(r["id"] == "exam-01" for r in matched_exam)


def test_contract_broken_case_from_teacher_example():
    # 세운 丁酉: 卯酉冲 — 卯(인수)·酉(재) 모두 깨짐 → '계약 안 된다·제값 못 받는다'
    f = build_facts(CONTRACT_CHART, "丁", "酉")
    assert "인수" in f.broken and "재" in f.broken
    matched = match_rules(["contract"], f, include_unreviewed=True)
    ids = {r["id"] for r in matched}
    assert "contract-02" in ids and "contract-03" in ids
    assert "contract-04" not in ids                        # '둘 다 온전' 룰은 성립 안 함


def test_reviewed_gate_blocks_unreviewed():
    # 감수(reviewed=False) 룰은 운영 주입 없음 — 전문가 감수 게이트(합성 룰로 검증)
    f = build_facts(CONTRACT_CHART, "丁", "酉")   # 인수 broken 상태
    synthetic = [{"id": "x", "topics": ["contract"], "when": [{"star": "인수", "state": "broken"}],
                  "then": "테스트", "source": "t", "reviewed": False}]
    assert match_rules(["contract"], f, rules=synthetic) == []
    assert len(match_rules(["contract"], f, rules=synthetic, include_unreviewed=True)) == 1


def test_activated_rules_inject_in_production_path():
    # 2026-07-08 운영자 승인으로 전건 활성화 — include_unreviewed 없이도 주입된다
    b = gwanbeop_block("매매 계약 될까요?", CONTRACT_CHART, seun_stem="丁", seun_branch="酉")
    assert b and "[선생님 관법" in b


def test_block_render_and_fallbacks():
    b = gwanbeop_block("매매 계약 될까요?", CONTRACT_CHART,
                       seun_stem="丁", seun_branch="酉", include_unreviewed=True)
    assert b and "[선생님 관법" in b and "계약" in b
    # 주제 미매칭 → None (기존 흐름 폴백)
    assert gwanbeop_block("성격이 어떤가요?", CONTRACT_CHART,
                          seun_stem="丁", seun_branch="酉", include_unreviewed=True) is None
    # 명식 없음 → None
    assert gwanbeop_block("매매 될까요?", None, seun_stem="丁", seun_branch="酉",
                          include_unreviewed=True) is None


def test_gender_gate():
    # love-01은 남성 전용 — 성별 미상/여성에겐 주입 안 됨
    f = build_facts(CONTRACT_CHART, "丁", "酉")   # 재 broken
    male = match_rules(["love"], f, is_male=True, include_unreviewed=True)
    unknown = match_rules(["love"], f, is_male=None, include_unreviewed=True)
    assert any(r["id"] == "love-01" for r in male)
    assert not any(r["id"] == "love-01" for r in unknown)


def test_wolun_contract_negative_from_teacher_example():
    # 카톡정리 사례 9(여): 壬子년 丁未월 丁未일 癸卯시, 월운 戊子 — 아파트 매매 계약 여부.
    # 戊癸합은 '식상-관성' 합이라 계약 공식(재성/식상×인성 합)에 해당 없음 → 성사 룰 미발화.
    # 子卯형으로 卯(인수) 깨짐 → '계약 안 된다' 방향(contract-02)만 성립. 선생님 결론과 일치.
    chart = _chart("壬子", "丁未", "丁未", "癸卯")
    f = build_facts(chart, "戊", "子")
    assert frozenset({"식상", "관"}) in f.hap_pairs          # 戊癸합
    ids = {r["id"] for r in match_rules(["contract"], f, include_unreviewed=True)}
    assert "contract-02" in ids                               # 인수(卯) 子卯형 — 계약 불리
    assert not ids & {"contract-01", "contract-04", "contract-05"}   # 성사 룰은 미발화


def test_block_scope_labels():
    # 세운·월운 두 스코프 계산 — 성립 스코프 라벨이 붙는다(일시적 사안=월운 원칙)
    chart = _chart("壬子", "丁未", "丁未", "癸卯")
    b = gwanbeop_block("아파트 매매 계약 될까요?", chart, seun_stem="庚", seun_branch="子",
                       wolun_stem="戊", wolun_branch="子", include_unreviewed=True)
    assert b and "월운" in b


def test_rules_file_valid():
    rules = load_rules()
    assert len(rules) >= 20
    for r in rules:
        assert r["id"] and r["topics"] and r["when"] and r["then"] and r["source"]
        assert isinstance(r["reviewed"], bool)
