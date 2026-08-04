"""꿈해몽 상징 사전 — 결정적 매칭 + 프롬프트 블록 생성.

[P4-꿈해몽 2026-07-22] 이 메뉴는 결정적 엔진이 없고 코퍼스도 실질 0건이라 LLM 단독으로
답해 왔다. 그런데 DREAM_SYSTEM 은 "전통 해몽에서 그 상징을 어떻게 보는지 설명하라"고
요구한다 — **근거 데이터를 하나도 주지 않으면서**. 그 결과 저장본 50건 중 존재하지 않는
문헌을 인용한 것이 2건 나왔다("'꿈 해석 사전'에 따르면…" — 그런 자료는 어디에도 없다).
→ 타로 78장 덱과 같은 방식으로 정적 사전을 두고, **매칭된 항목만** 주입한다.

⛔⛔ 승인 없이 수정 금지 ⛔⛔
  · 엔진이 길흉을 **종합 판정하지 않는다** — 전통이 '반대해석'과 '해몽자 재해석'을 축으로
    삼으므로(같은 돼지꿈이 재수·푼돈·낭패로 갈린다) 엔진이 최종 길흉을 계산하면 전통 왜곡이다.
    엔진은 '이 항목이 걸렸다'까지, 해석은 LLM 이 그 자료 안에서 한다.
  · 사전 **전량 주입 금지**. 매칭된 것만, 상한 4개. 타로도 78장 중 뽑힌 카드만 넣는다.
  · 성별을 **단일 값으로 저장하지 않는다**. 태몽 성별은 지역·기준마다 충돌하는 것이 특징이라
    (애호박=형태는 아들·색은 딸) 1:1 매핑 자체가 전통 왜곡이다.
  관련: docs/rag_hallucination_audit_2026-07-22.md
"""
from __future__ import annotations

import json
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "dream_symbols.json"
_lock = threading.Lock()

# 주입 상한 — 프롬프트 예산. 브리핑 비대로 답변이 잘린 전례가 있어 항목 수와 길이를 모두 묶는다.
MAX_SYMBOLS = 4
MAX_INTERP_CHARS = 220


@lru_cache(maxsize=1)
def _data() -> dict[str, Any]:
    try:
        return json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 데이터 부재 시 호출부가 '자료 없음'으로 폴백
        return {}


def symbols() -> list[dict]:
    return _data().get("symbols") or []


def meta_rules() -> list[dict]:
    return _data().get("meta_rules") or []


def gender_lore() -> dict:
    return _data().get("gender_lore") or {}


def reload_cache() -> None:
    """운영 중 사전을 고쳤을 때 재기동 없이 반영(관리자 편집 경로 대비)."""
    with _lock:
        _data.cache_clear()
        _alias_res.cache_clear()


# ── 매칭 ────────────────────────────────────────────────────────────
# 1음절 키(용·말·뱀)가 파생어에 걸리는 사고가 이 프로젝트에서 반복됐다:
#   '형성합니다'→'형성관계니다'(거짓합 중화기), '수호(守護)'→'수호(秀浩)'(작명 교정기).
# 그때 사고를 끝낸 것이 **낱말 경계**였다. 여기서도 같은 방식을 쓴다 —
# 앞은 한글이 아니어야 하고, 뒤는 조사 하나까지만 허용한 뒤 한글이 아니어야 한다.
# 그래서 '사용·활용·용기·용접'은 안 걸리고 '용이·용을·용꿈'은 걸린다.
_PARTICLES = "이|가|을|를|은|는|와|과|의|에|도|만|에게|에서|처럼|같은|꿈"
# 별칭이 **용언 어간**(공백을 품고 '오르'·'빠'처럼 끝나는 것)이면 뒤에 어미가 자유롭게 붙는다
# ('하늘로 오르' + '아오르는'). 이런 별칭까지 조사 하나로 묶으면 활용형을 통째로 놓친다.
# 어간형은 이미 두 어절 이상이라 파생어 오매칭 위험이 낮으므로 뒤 제약만 푼다
# (앞 경계는 그대로 — '나는 학생입니다' 같은 오탐은 앞 경계가 막는다).
_STEM_ALIAS_RE = re.compile(r"\s")


@lru_cache(maxsize=1)
def _alias_res() -> list[tuple[str, re.Pattern]]:
    out: list[tuple[str, re.Pattern]] = []
    for s in symbols():
        raw = [a for a in ([s.get("key")] + list(s.get("aliases") or [])) if a]
        if not raw:
            continue
        strict = [re.escape(a) for a in raw if not _STEM_ALIAS_RE.search(a)]
        stems = [re.escape(a) for a in raw if _STEM_ALIAS_RE.search(a)]
        parts = []
        if strict:
            parts.append(r"(?<![가-힣])(?:" + "|".join(sorted(strict, key=len, reverse=True))
                         + r")(?:" + _PARTICLES + r")?(?![가-힣])")
        if stems:
            parts.append(r"(?<![가-힣])(?:" + "|".join(sorted(stems, key=len, reverse=True)) + r")")
        out.append((s["code"], re.compile("|".join(parts))))
    return out


_TAEMONG_RE = re.compile(r"태몽|임신|임산부|아기를\s*가|배가\s*불러")
_GENDER_ASK_RE = re.compile(r"성별|아들|딸|남아|여아|사내|계집")


def match(text: str, *, limit: int = MAX_SYMBOLS) -> list[dict]:
    """꿈 이야기에서 사전 상징을 찾는다. 판정은 하지 않고 '걸린 항목'만 돌려준다."""
    t = text or ""
    if not t:
        return []
    by_code = {s["code"]: s for s in symbols()}
    hits: list[tuple[int, dict]] = []
    for code, pat in _alias_res():
        m = pat.search(t)
        if m:
            hits.append((m.start(), by_code[code]))
    hits.sort(key=lambda x: x[0])          # 꿈 이야기에 나온 순서대로
    return [s for _pos, s in hits[:limit]]


def is_taemong_context(text: str) -> bool:
    return bool(_TAEMONG_RE.search(text or ""))


def asks_gender(text: str) -> bool:
    return bool(_GENDER_ASK_RE.search(text or ""))


# ── 프롬프트 블록 ────────────────────────────────────────────────────
def context_block(text: str) -> str | None:
    """꿈 이야기에 맞는 [전통 해몽 자료] 블록. 걸린 게 없으면 None(=자료 없음).

    None 을 돌려주는 것이 중요하다 — 호출부가 has_sources 로 쓰고, 자료가 없으면
    '참고자료가 없습니다' 쪽 문구가 붙는다(없는 자료를 따르라는 유령 지시 방지)."""
    hits = match(text)
    taemong = is_taemong_context(text)
    if not hits and not taemong:
        return None

    lines: list[str] = ["[전통 해몽 자료 — 아래 내용만 근거로 쓰고, 여기 없는 것을 "
                        "'전통 해몽에서는'이라고 말하지 마세요]"]
    for s in hits:
        tier_note = "" if s.get("tier") == 1 else " (근거: 현대 해몽서 정리본 — 단정하지 마세요)"
        lines.append(f"· {s['key']} [{s.get('category','')}]{tier_note}")
        lines.append(f"  {(s.get('interp') or '')[:MAX_INTERP_CHARS]}")
        if s.get("caution"):
            lines.append(f"  ※ {s['caution']}")
        if s.get("conflict_note"):
            lines.append(f"  ※ {s['conflict_note']}")
        if taemong and s.get("taemong_note"):
            lines.append(f"  ※ {s['taemong_note']}")

    # 메타 규칙은 '반대해석'과 '꿈보다 해몽'만 — 전량 주입하면 예산을 먹고 본문이 밀린다.
    for r in meta_rules():
        if r["code"] in ("opposite", "haemong_over_dream"):
            lines.append(f"· [{r['title']}] {r['text']}")

    if taemong:
        gl = gender_lore()
        lines.append("· [태몽] " + (next((r["text"] for r in meta_rules()
                                          if r["code"] == "taemong_relation"), "")))
        if gl:
            lines.append("· [태몽과 성별] 전통에서 성별을 가리던 방식: "
                         + " / ".join(p["text"] for p in (gl.get("principles") or [])))
            for ex in (gl.get("conflict_examples") or [])[:2]:
                lines.append(f"  ※ {ex}")
            lines.append("  ★ 위 예처럼 같은 상징도 기준에 따라 아들로도 딸로도 풀렸습니다. "
                         "**절대 한쪽으로 단정하지 말고**, 전통에서 두 갈래로 풀었다는 사실만 "
                         "전하세요. '아들입니다'·'딸입니다' 같은 표현을 쓰면 안 됩니다.")
            lines.append(f"  ★ 반드시 덧붙일 것: {gl.get('disclaimer','')}")
    return "\n".join(lines)


# ── 출력 검증 ────────────────────────────────────────────────────────
# 태몽 성별 단정은 ①경험적 근거 없음 ②확률 50% 오답 ③임신·출산이라는 최고 민감 주제
# ④'예언이 틀렸다' 클레임이 가장 명확히 성립하는 형태 — 프롬프트 지시만으로 두지 않는다.
_GENDER_ASSERT_RE = re.compile(
    r"(아들|딸|남아|여아|사내아이|여자아이)(?:일\s*것|입니다|이에요|예요|이겠|일\s*가능성이\s*(?:매우\s*)?(?:높|큽))"
    r"|(?:아들|딸)(?:을|를)\s*(?:낳|가지)"
    r"|성별은\s*(?:아들|딸|남아|여아)")
_GENDER_HEDGE_RE = re.compile(r"단정할\s*수\s*없|두\s*갈래|양쪽|의학적\s*근거|가리기\s*어렵|갈립니다|전통에서는")


def verify_no_gender_claim(answer: str) -> list[tuple[str, str, str]]:
    """답변이 태아 성별을 단정하면 불일치로 보고한다. 빈 결과 = 문제 없음.

    같은 문장 안에 '단정할 수 없다'류 완충 표현이 있으면 통과시킨다 —
    '전통에서는 아들로 보았지만 단정할 수 없습니다'는 정상 서술이다."""
    if not answer:
        return []
    for m in _GENDER_ASSERT_RE.finditer(answer):
        s0 = max((answer.rfind(c, 0, m.start()) for c in ".!?。\n"), default=-1) + 1
        e0 = next((k for k in range(m.end(), min(len(answer), m.end() + 60))
                   if answer[k] in ".!?。\n"), min(len(answer), m.end() + 60))
        if _GENDER_HEDGE_RE.search(answer[s0:e0]):
            continue
        return [("태몽 성별 단정", m.group(0), "전통 해석이며 의학적 근거가 없다는 점을 함께 밝힐 것")]
    return []
