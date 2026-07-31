# -*- coding: utf-8 -*-
"""물상(物象) 조합 사전 주입 — 명리전 1·2권 원문 발췌의 결정적 선별.

관법 룰 엔진(gwanbeop.py)과 동일 철학: 어떤 조합이 이 명식에 존재하는지는 코드가
결정적으로 판정하고, LLM은 선생님 책 원문의 물상 비유를 근거로 서술만 한다.
사전: data/rag/mulsang_pairs.json (scripts/extract_mulsang.py 산출, 지지 144 + 천간 100).

주입 대상: 성격·기질·관계·궁합·육친류 질문. 쌍 우선순위(명리 통례):
일간↔월간(천간) → 일지↔월지 → 일지↔시지 → 일간↔시간 — 최대 max_entries개만
(프롬프트 비대 방지, 항목당 max_chars 문장경계 발췌).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PAIRS_PATH = PROJECT_ROOT / "data" / "rag" / "mulsang_pairs.json"

# 물상 해설이 유효한 질문(성격·기질·관계) — 미매칭이면 주입 없음(기존 흐름 폴백)
_TOPIC_KEYWORDS = (
    "성격", "기질", "성향", "어떤 사람", "어떤사람", "특징", "장점", "단점",
    "궁합", "잘 맞", "어울리", "관계", "부모", "형제", "배우자", "자식", "육친",
    "종합", "전체적", "타고난",
)


def _wants_mulsang(question: str) -> bool:
    q = question or ""
    return any(k in q for k in _TOPIC_KEYWORDS)


@lru_cache(maxsize=1)
def _load_pairs() -> dict[tuple[str, str, str], dict]:
    """(kind, a, b) → entry. 파일 없거나 깨져도 빈 사전(무해)."""
    try:
        d = json.loads(PAIRS_PATH.read_text(encoding="utf-8"))
        return {(e["kind"], e["a"], e["b"]): e for e in d.get("entries", [])}
    except Exception:  # noqa: BLE001
        return {}


def _excerpt(text: str, max_chars: int) -> str:
    """문장 경계('다.') 기준 발췌 — 원문 손상 없이 앞부분만. 경계 못 찾으면 자름."""
    t = re.sub(r"\s*\n\s*", " ", (text or "").strip())
    if len(t) <= max_chars:
        return t
    cut = t[:max_chars]
    m = None
    for m in re.finditer(r"다\.", cut):
        pass
    return cut[: m.end()] if m else cut


def _chart_pair_keys(chart_json: dict | None) -> list[tuple[str, tuple[str, str], str]]:
    """명식에서 우선순위대로 (kind, (a,b), 위치라벨) 후보 나열."""
    pil = (chart_json or {}).get("pillars") or {}

    def _g(k: str, part: str) -> str | None:
        return (pil.get(k) or {}).get(part)

    ds, db = _g("day", "stem"), _g("day", "branch")
    out: list[tuple[str, tuple[str, str], str]] = []
    if ds and _g("month", "stem"):
        out.append(("stem", (ds, _g("month", "stem")), "일간↔월간"))
    if db and _g("month", "branch"):
        out.append(("branch", (db, _g("month", "branch")), "일지↔월지"))
    if db and _g("hour", "branch"):
        out.append(("branch", (db, _g("hour", "branch")), "일지↔시지"))
    if ds and _g("hour", "stem"):
        out.append(("stem", (ds, _g("hour", "stem")), "일간↔시간"))
    return out


def mulsang_block(question: str, chart_json: dict | None, *,
                  max_entries: int = 2, max_chars: int = 420) -> str | None:
    """명식에 실존하는 조합의 명리전 원문 발췌 블록. 대상 아님/사전 없음이면 None."""
    if not _wants_mulsang(question):
        return None
    pairs = _load_pairs()
    if not pairs:
        return None
    lines: list[str] = []
    for kind, (a, b), label in _chart_pair_keys(chart_json):
        e = pairs.get((kind, a, b))
        if not e:
            continue
        lines.append(f"· [{label}] {e['title']} — \"{_excerpt(e['text'], max_chars)}\" ({e['source']})")
        if len(lines) >= max_entries:
            break
    if not lines:
        return None
    return (
        "[명리전 물상 — 이 명식에 실제로 있는 조합의 원문 발췌]\n"
        + "\n".join(lines)
        + "\n→ 성격·기질·관계 풀이에서 물상 비유는 위 원문을 우선 근거로 쓰고, "
          "원문에 없는 물상이나 이 명식에 없는 조합의 이야기를 지어내지 마세요."
    )
