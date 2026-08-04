# -*- coding: utf-8 -*-
"""관법(觀法) 룰 엔진 — 선생님 공식('인수가 재와 합되면 계약된다')의 결정적 적용.

설계: docs/gwanbeop_rule_engine.md (할루시 검증 케이스 #4 파생).
문제: 매매·취업·승진 질문에 선생님 관법이 적용되지 않음 — 공식은 '조건(십성 관계)→해석'의
결정적 룰인데 적용을 약한 1차 LLM의 추론에 맡기고 있었다.
해법: 질문 주제 라우팅 → 명식×세운의 십성 관계(합·충·형·파·극)를 코드로 계산 →
      실제 성립한 룰만 프롬프트에 주입("이 공식을 뼈대로") → LLM은 해석 서술만.

룰 파일: data/rag/gwanbeop_rules.json — reviewed(전문가 감수 완료)된 룰만 운영 주입.
감수 시트: docs/gwanbeop_rules_review.md (뽀 선생님 검토용).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from backend.app.saju.constants import (
    BRANCH_BREAK,
    BRANCH_CONFLICTS,
    BRANCH_PUNISH,
    BRANCH_SELF_PUNISH,
    BRANCH_SIX_COMBINATIONS,
    HIDDEN_STEMS,
    STEM_COMBINATIONS,
    STEM_CONFLICTS,
    STEM_TO_WUXING,
    WUXING_OVERCOMES,
    compute_ten_god,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RULES_PATH = PROJECT_ROOT / "data" / "rag" / "gwanbeop_rules.json"

# 십성(한자) → 관법 그룹 5분류(선생님 자료의 어휘: 인수·재·관·식상·비겁)
STAR_GROUP: dict[str, str] = {
    "比肩": "비겁", "劫財": "비겁",
    "食神": "식상", "傷官": "식상",
    "偏財": "재", "正財": "재",
    "偏官": "관", "正官": "관",
    "偏印": "인수", "正印": "인수",
}

# 질문 → 주제 라우팅(결정적 키워드). 주제가 안 잡히면 룰 주입 없음(기존 흐름 폴백 — 안전).
TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "contract": ("계약", "매매", "문서운", "부동산", "집 팔", "집팔", "전세", "월세", "분양", "잔금", "등기"),
    "career": ("취업", "이직", "입사", "직장", "퇴사", "퇴직", "인사이동", "발령", "회사"),
    "promotion": ("승진", "진급"),
    "exam": ("시험", "합격", "고시", "자격증", "수능", "면접"),
    "business": ("사업", "장사", "가게", "창업", "개업", "폐업", "확장"),
    "invest": ("투자", "주식", "코인"),
    "love": ("남자친구", "여자친구", "연애", "애인", "이성운", "결혼운", "결혼"),
    "money": ("돈", "재물", "금전", "빚", "대출", "동업"),
}


def route_topics(question: str) -> list[str]:
    q = question or ""
    return [t for t, kws in TOPIC_KEYWORDS.items() if any(k in q for k in kws)]


@lru_cache(maxsize=1)
def load_rules() -> list[dict]:
    try:
        return json.loads(RULES_PATH.read_text(encoding="utf-8")).get("rules", [])
    except Exception:  # noqa: BLE001 — 룰 파일 없거나 깨져도 엔진은 무해하게 무동작
        return []


class GwanbeopFacts:
    """명식(원국)×세운의 십성 관계 사실 집합 — 룰 조건 판정의 근거(전부 결정적 계산).

    선생님 어법 반영: 충·형·파는 양쪽 글자를 모두 '깨진' 것으로, 극은 맞은 쪽만 깨진 것으로
    본다(세운3: '卯酉冲 묘(인수)계약 유(돈) 극 맞았으니'). 합은 양쪽 모두 '합에 참여'."""

    def __init__(self) -> None:
        self.present: set[str] = set()          # 원국+세운에 존재하는 십성 그룹
        self.in_seun: set[str] = set()          # 세운(천간·지지)으로 들어온 그룹
        self.broken: set[str] = set()           # 세운과의 충·형·파·극으로 깨진 그룹
        self.in_hap: set[str] = set()           # 세운과 합에 참여한 그룹
        self.hap_pairs: set[frozenset[str]] = set()      # 합을 이룬 그룹 쌍
        self.geuk_pairs: set[tuple[str, str]] = set()    # (극하는 그룹, 극받는 그룹)


def _star(day_stem: str, char: str, kind: str) -> str | None:
    """글자의 십성 그룹. 지지는 정기(지장간 마지막) 기준 — 선생님 자료의 통상 용법."""
    try:
        stem = char if kind == "stem" else HIDDEN_STEMS[char][-1]
        return STAR_GROUP.get(compute_ten_god(day_stem, stem))
    except Exception:  # noqa: BLE001
        return None


def _natal_chars(chart_json: dict | None) -> tuple[str | None, list[tuple[str, str]]]:
    """(일간, [(글자, stem|branch)]) — 일간 자신은 십성 판정 대상에서 제외."""
    pil = (chart_json or {}).get("pillars") or {}
    day_stem = (pil.get("day") or {}).get("stem")
    chars: list[tuple[str, str]] = []
    for k in ("year", "month", "day", "hour"):
        p = pil.get(k) or {}
        st, br = p.get("stem"), p.get("branch")
        if st and k != "day":
            chars.append((st, "stem"))
        if br:
            chars.append((br, "branch"))
    return day_stem, chars


def _pair_relations(a: str, ka: str, b: str, kb: str) -> tuple[set[str], list[tuple[str, str]]]:
    """두 글자의 관계: ({합,충,형,파}, [(극하는글자, 극받는글자)]). 천간↔지지 간엔 관계 없음."""
    rels: set[str] = set()
    geuk: list[tuple[str, str]] = []
    if ka == "stem" and kb == "stem":
        fs = frozenset({a, b})
        if fs in STEM_COMBINATIONS:
            rels.add("합")
        if fs in STEM_CONFLICTS:
            rels.add("충")
        ea, eb = STEM_TO_WUXING[a], STEM_TO_WUXING[b]
        if WUXING_OVERCOMES.get(ea) == eb:
            geuk.append((a, b))
        if WUXING_OVERCOMES.get(eb) == ea:
            geuk.append((b, a))
    elif ka == "branch" and kb == "branch":
        fs = frozenset({a, b})
        if fs in BRANCH_SIX_COMBINATIONS:
            rels.add("합")
        if fs in BRANCH_CONFLICTS:
            rels.add("충")
        if fs in BRANCH_PUNISH or (a == b and a in BRANCH_SELF_PUNISH):
            rels.add("형")
        if fs in BRANCH_BREAK:
            rels.add("파")
    return rels, geuk


def build_facts(chart_json: dict | None, seun_stem: str, seun_branch: str) -> GwanbeopFacts | None:
    """원국×세운의 십성 관계 사실 계산. 명식이 없으면 None(주입 안 함)."""
    day_stem, natal = _natal_chars(chart_json)
    if not day_stem or not natal:
        return None
    f = GwanbeopFacts()
    seun = [(seun_stem, "stem"), (seun_branch, "branch")]
    star_of: dict[tuple[str, str], str | None] = {}
    for ch, kind in natal + seun:
        g = _star(day_stem, ch, kind)
        star_of[(ch, kind)] = g
        if g:
            f.present.add(g)
    for ch, kind in seun:
        g = star_of[(ch, kind)]
        if g:
            f.in_seun.add(g)
    # 세운 글자 ↔ 원국 글자 사이의 관계만 본다(B1 스코프 — 선생님 세운분석의 기본형)
    for s_ch, s_kind in seun:
        s_star = star_of[(s_ch, s_kind)]
        for n_ch, n_kind in natal:
            n_star = star_of[(n_ch, n_kind)]
            rels, geuk = _pair_relations(s_ch, s_kind, n_ch, n_kind)
            if "합" in rels:
                if s_star:
                    f.in_hap.add(s_star)
                if n_star:
                    f.in_hap.add(n_star)
                if s_star and n_star:
                    f.hap_pairs.add(frozenset({s_star, n_star}))
            if rels & {"충", "형", "파"}:   # 충·형·파는 양쪽 모두 깨짐
                for g in (s_star, n_star):
                    if g:
                        f.broken.add(g)
            for atk, dfd in geuk:           # 극은 맞은 쪽만 깨짐
                atk_star = star_of[(atk, s_kind if atk == s_ch else n_kind)]
                dfd_star = star_of[(dfd, s_kind if dfd == s_ch else n_kind)]
                if dfd_star:
                    f.broken.add(dfd_star)
                if atk_star and dfd_star:
                    f.geuk_pairs.add((atk_star, dfd_star))
    return f


def _atom_ok(atom: dict, f: GwanbeopFacts) -> bool:
    if "pair" in atom:
        a, b = atom["pair"]
        if atom.get("rel") == "합":
            return frozenset({a, b}) in f.hap_pairs
        if atom.get("rel") == "극":
            return (a, b) in f.geuk_pairs
        return False
    star, state = atom.get("star"), atom.get("state")
    if not star:
        return False
    if state == "intact":
        return star in f.present and star not in f.broken
    if state == "broken":
        return star in f.broken
    if state == "in_seun":
        return star in f.in_seun
    if state == "합":
        return star in f.in_hap
    return False


def match_rules(topics: list[str], f: GwanbeopFacts, *, is_male: bool | None = None,
                rules: list[dict] | None = None, include_unreviewed: bool = False) -> list[dict]:
    """주제가 맞고 조건(when 전체 AND)이 성립한 룰만. 운영은 reviewed(감수 완료)만 주입."""
    out: list[dict] = []
    for r in (rules if rules is not None else load_rules()):
        if not include_unreviewed and not r.get("reviewed"):
            continue
        if not set(r.get("topics", [])) & set(topics):
            continue
        g = r.get("gender")
        if g and (is_male is None or g != ("male" if is_male else "female")):
            continue
        if all(_atom_ok(a, f) for a in r.get("when", [])):
            out.append(r)
    return out


def gwanbeop_block(question: str, chart_json: dict | None, *, seun_stem: str,
                   seun_branch: str, wolun_stem: str | None = None,
                   wolun_branch: str | None = None, is_male: bool | None = None,
                   include_unreviewed: bool = False,
                   seun_label: str = "올해 세운",
                   wolun_label: str = "이번 달 월운") -> str | None:
    """성립한 관법 룰 프롬프트 블록. 주제 미매칭·명식 없음·성립 룰 없음이면 None(기존 흐름).

    선생님 원칙(카톡정리): 지속적인 사안은 '세운' 기준, 매매·취업처럼 일시적(단발) 사안은
    세운을 무시하고 '월운'을 원국에 바로 대입한다 → 두 스코프를 모두 계산해 각 룰이 어느
    시점 기준으로 성립했는지 라벨로 밝힌다(판단은 결정적, 서술만 LLM).

    seun_label/wolun_label: 스코프 표기 — 실측(전수감사): '내년/2023년' 질문에도 '올해 세운'
    라벨로 2026년 공식을 주입해 자기모순 프롬프트가 됐다. 호출부가 질문 대상 연도의 세운을
    넣을 때 라벨도 그 해로 밝힌다(공식 자체는 세운 일반 룰이라 대입 연도만 달라짐)."""
    topics = route_topics(question)
    if not topics:
        return None
    scopes: list[tuple[str, str, str]] = [(seun_label, seun_stem, seun_branch)]
    if wolun_stem and wolun_branch:
        scopes.append((wolun_label, wolun_stem, wolun_branch))
    hits: dict[str, tuple[dict, list[str]]] = {}
    for label, st, br in scopes:
        f = build_facts(chart_json, st, br)
        if f is None:
            return None
        for r in match_rules(topics, f, is_male=is_male, include_unreviewed=include_unreviewed):
            hits.setdefault(r["id"], (r, []))[1].append(label)
    if not hits:
        return None
    lines = ["[선생님 관법 — 이 명식에 실제로 성립한 공식만 추린 것]"]
    lines += [f"· [{'·'.join(labels)}] {r['then']}" for r, labels in hits.values()]
    lines.append(
        "→ 위 공식을 이 질문 풀이의 뼈대로 삼으세요. 여기 없는 공식이나 성립하지 않은 "
        "십성 관계(합·충·형·파·극)를 지어내지 말고, 공식의 결론 방향과 모순되게 풀지 마세요. "
        "지속적인 사안(사업·직장 전반)은 세운 기준, 단발 사안(매매·취업·시험 시기)은 월운 기준 "
        "공식을 우선 참고하세요. (용어: 재=돈·적응, 관=직장·인사이동, 인수=문서·계약, 식상=하는 일)"
    )
    return "\n".join(lines)
