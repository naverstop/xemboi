# -*- coding: utf-8 -*-
"""관법 룰 2차(뽀 서면 2026-08-03): 계약 가게/토지·인수운 + 취업 합공식 + 시험 발표일 합공식.

- contract-06 식상-관 합(가게) / contract-07 인수 in_seun / contract-08 土가 인수·재와 합(토지, elem 조건)
- career-06 관 in_seun+관식상 합 / career-07 재·관 모두 합
- exam-05 관-인수 합(합격 신호) / exam-06 관-재 합(취업·자격증)
"""
from __future__ import annotations

from backend.app.saju.gwanbeop import build_facts, load_rules, match_rules


def _pillars(day_stem: str, stems: list[str], branches: list[str]) -> dict:
    """간단 명식 조립 — year/month(+선택 hour)에 stems·branches 배치, 일간=day_stem."""
    keys = ["year", "month", "hour"]
    pil: dict = {"day": {"stem": day_stem, "branch": branches[0] if branches else None}}
    si = bi = 0
    for k in keys:
        p = {}
        if si < len(stems):
            p["stem"] = stems[si]; si += 1
        if bi + 1 < len(branches) + 1 and bi < len(branches) - 1:
            p["branch"] = branches[bi + 1]; bi += 1
        if p:
            pil[k] = p
    return {"pillars": pil}


def _match_ids(chart, seun_stem, seun_branch, topics):
    f = build_facts(chart, seun_stem, seun_branch)
    assert f is not None
    return {r["id"] for r in match_rules(topics, f, rules=load_rules())}


def test_rules_loaded():
    ids = {r["id"] for r in load_rules()}
    for rid in ("contract-06", "contract-07", "contract-08", "career-06", "career-07", "exam-05", "exam-06"):
        assert rid in ids, f"신규 룰 {rid} 미탑재"


def test_contract08_land_elem_hap():
    # 丙일간: 인수=木(卯). 세운 지지 戌(土)이 원국 卯와 육합(卯戌합) → 土가 인수와 합 = 토지계약 유리.
    chart = _pillars("丙", ["甲"], ["子", "卯"])
    ids = _match_ids(chart, "戊", "戌", ["contract"])
    assert "contract-08" in ids
    # 반례: 세운 酉(金)는 卯와 충 — elem_hap 미성립.
    assert "contract-08" not in _match_ids(chart, "戊", "酉", ["contract"])


def test_contract07_insu_in_seun():
    # 丙일간: 세운 천간 甲(편인=인수) 들어옴 → contract-07.
    chart = _pillars("丙", ["庚"], ["子", "午"])
    assert "contract-07" in _match_ids(chart, "甲", "申", ["contract"])


def test_contract06_siksang_gwan_hap():
    # 甲일간: 식상=火(巳), 관=金(申). 세운 지지 申(관)이 원국 巳(식상)와 육합 → 가게 계약 성사.
    chart = _pillars("甲", ["丙"], ["子", "巳"])
    assert "contract-06" in _match_ids(chart, "壬", "申", ["contract"])


def test_career06_gwan_inseun_and_siksang_hap():
    # 甲일간: 세운 庚申(관 in_seun) + 申합巳(관-식상 합) → 취업 성사 방향.
    chart = _pillars("甲", ["丙"], ["子", "巳"])
    ids = _match_ids(chart, "庚", "申", ["career"])
    assert "career-06" in ids


def test_career07_jae_gwan_both_hap():
    # 甲일간: 세운 己(재)합 원국 甲(년간) + 세운 申(관)합 원국 巳(식상) → 재·관 모두 합.
    chart = _pillars("甲", ["甲"], ["子", "巳"])
    ids = _match_ids(chart, "己", "申", ["career"])
    assert "career-07" in ids


def test_exam05_gwan_insu_hap():
    # 壬일간: 관=土(辰), 인수=金(酉). 辰酉 육합 — 세운 酉가 원국 辰과 합 → 합격 신호.
    chart = _pillars("壬", ["甲"], ["子", "辰"])
    assert "exam-05" in _match_ids(chart, "甲", "酉", ["exam"])


def test_exam06_gwan_jae_hap():
    # 甲일간: 관=金(酉), 재=土(辰). 세운 酉(관)합 원국 辰(재) → 발표·결과 좋은 신호.
    chart = _pillars("甲", ["丙"], ["子", "辰"])
    assert "exam-06" in _match_ids(chart, "壬", "酉", ["exam"])
