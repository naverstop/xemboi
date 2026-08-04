# -*- coding: utf-8 -*-
"""운(세운·월운·일진) ↔ 명식 관계 결정적 계산 — 해설 근거 풍부화 공용 모듈 (2026-07-16).

원칙(할루시 검증방): 풍부화 = 'LLM에게 길게 써라'가 아니라 결정적 재료를 더 계산해 주는 것.
기본 관계(육합·충·형·파)는 감수된 관법 엔진 gwanbeop._pair_relations 를 재사용하고,
확장 관계(반합·원진·해)는 여기서만 추가한다 — gwanbeop 룰 매칭(감수 완료)은 건드리지 않는다.

신년운세(tool_service, 커밋 61a1f3a1)에서 검증된 로직을 라벨 파라미터화해 일반화:
'월' 스코프면 '월운 천간/월운 지지', '오늘' 스코프면 '오늘 천간/오늘 지지'로 표기.
⚠️'월간/월지'로 되돌리지 말 것 — 명식의 월지·월간과 표기가 겹쳐 검증기가 월운 서술을
  명식 오류로 오탐한다(전건 재생성 유발 실측 2026-07-21).
"""
from __future__ import annotations

from backend.app.saju.constants import (
    BRANCH_HARM,
    BRANCH_TRIPLE_COMBINATIONS,
    BRANCH_WONJIN,
    HIDDEN_STEMS,
    branch_korean,
    compute_ten_god,
    stem_korean,
)
from backend.app.saju.gwanbeop import _pair_relations

# 궁위(宮位) 라벨 — 관계가 건드리는 삶의 영역(결정적 상수)
PALACE_KO = {"year": "년지(초년·조상궁)", "month": "월지(사회·직장궁)",
             "day": "일지(배우자·가정궁)", "hour": "시지(자녀·말년궁)"}

STAR_KO = {"比肩": "비견", "劫財": "겁재", "食神": "식신", "傷官": "상관", "偏財": "편재",
           "正財": "정재", "偏官": "편관", "正官": "정관", "偏印": "편인", "正印": "정인"}


def branch_ten_god(day_stem: str, branch: str) -> str:
    """지지의 십성 — 지장간 정기(마지막) 기준(관법 엔진과 동일 용법). 실패 시 ''."""
    try:
        return compute_ten_god(day_stem, HIDDEN_STEMS[branch][-1])
    except Exception:  # noqa: BLE001
        return ""


def ten_god_ko(tg: str) -> str:
    """십성 한자 → '비견(比肩)' 병기. 미지 값은 그대로."""
    return f"{STAR_KO[tg]}({tg})" if tg in STAR_KO else tg


def pair_branch_relations_ext(a: str, b: str) -> set[str]:
    """두 지지의 관계(확장): 육합·충·형·파(감수 엔진) + 반합·원진·해.

    반합은 len==2 가드 필수 — 같은 글자는 1원소 집합이라 삼합 부분집합 검사에 항상 걸림
    (궁합 '삼합 78점' 오판과 동일 결함 계열, 커밋 f125ce85)."""
    rels, _ = _pair_relations(a, "branch", b, "branch")
    out = set(rels)
    pair = frozenset({a, b})
    if len(pair) == 2:
        if any(pair < t for t in BRANCH_TRIPLE_COMBINATIONS):
            out.add("반합")
        if pair in BRANCH_WONJIN:
            out.add("원진")
        if pair in BRANCH_HARM:
            out.add("해")
    return out


def _pillars_from(chart_like) -> list[tuple[str, str, str]]:
    """SajuChart 또는 chart_json(dict) → [(궁위key, 천간, 지지)]. 시주 없으면 제외."""
    out: list[tuple[str, str, str]] = []
    if chart_like is None:
        return out
    if isinstance(chart_like, dict):
        pil = chart_like.get("pillars") or {}
        for k in ("year", "month", "day", "hour"):
            p = pil.get(k) or {}
            st, br = p.get("stem"), p.get("branch")
            if st and br:
                out.append((k, st, br))
    else:  # SajuChart
        pil = chart_like.pillars
        for k in ("year", "month", "day", "hour"):
            p = getattr(pil, k, None)
            if p is not None:
                out.append((k, p.stem, p.branch))
    return out


def luck_natal_relations(chart_like, l_stem: str, l_branch: str, *,
                         scope: str = "월", extended: bool = True) -> list[str]:
    """운(l_stem·l_branch) ↔ 내 4주의 관계 목록(궁위 라벨 포함, 전부 결정적).

    scope: 표기 접두('월'→'월운 천간/월운 지지', '오늘'→'오늘 천간/오늘 지지', '세운'→'세운 천간/세운 지지').
    extended=True면 반합·원진·해 포함(기본). 관계 없으면 빈 리스트(무난 — 창작 금지 근거).
    [라벨 주의 2026-07-21] 한 글자 scope에 '월지/월간'을 쓰면 명식의 월지와 표기가 충돌해
    검증기(_verify_branches)가 월운 서술을 명식 오류로 오탐한다(전건 재생성 유발 실측) —
    '월운 지지'처럼 '월지' 부분문자열을 포함하지 않는 라벨을 유지할 것.
    """
    out: list[str] = []
    pillars = _pillars_from(chart_like)
    if not pillars or not l_stem or not l_branch:
        return out
    b_label = f"{scope}운 지지" if len(scope) == 1 else f"{scope} 지지"
    s_label = f"{scope}운 천간" if len(scope) == 1 else f"{scope} 천간"
    day_stem = next((st for k, st, _br in pillars if k == "day"), None)
    try:
        for key, _st, br in pillars:
            rels = (pair_branch_relations_ext(l_branch, br) if extended
                    else _pair_relations(l_branch, "branch", br, "branch")[0])
            for r in sorted(rels):
                out.append(f"{b_label} {branch_korean(l_branch)}({l_branch})↔내 {PALACE_KO[key]} "
                           f"{branch_korean(br)}({br}) {r}")
        # 운 천간 ↔ 내 일간(본인)만 — 궁위 노이즈 방지, 본인에게 오는 기운만
        if day_stem:
            rels, _ = _pair_relations(l_stem, "stem", day_stem, "stem")
            for r in sorted(rels):
                out.append(f"{s_label} {stem_korean(l_stem)}({l_stem})↔내 일간 "
                           f"{stem_korean(day_stem)}({day_stem}) {r}")
    except Exception:  # noqa: BLE001 — 관계 주입은 부가 기능: 실패해도 기본 흐름 유지
        return []
    return out
