"""듀얼 LLM(로컬) 검증: exaone 초안 → qwen 보강 → (필요시 Claude 폴백).

특히 qwen 한글 출력 품질(중국어 드리프트/서로게이트 깨짐) 을 _looks_korean_clean
가드로 반복 검증한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services import chat_service as cs

QUESTIONS = [
    "사주로 시험 합격 여부를 보는 방법을 알려줘.",
    "재물복이 있는 사주의 조건을 열매나무 비유로 설명해줘.",
    "비견과 겁재가 많은 사주는 어떤 특징이 있나요?",
]


def main() -> int:
    ok = True
    for q in QUESTIONS:
        print("=" * 78)
        print("질문:", q)
        chunks = cs._search_corpus(q, 6)
        new_n = sum(1 for c in chunks if c.source.startswith("S25C"))
        print(f"[RAG] {len(chunks)}건(신규 S25C {new_n}건)")

        # 1차: exaone 초안
        prompt = cs._build_user_prompt(q, chunks, None)
        msgs = [
            {"role": "system", "content": cs.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        draft = cs._call_ollama(msgs)  # exaone
        print(f"[1차 exaone] {len(draft.strip())}자  clean={cs._looks_korean_clean(draft)}")

        # 2차: qwen 보강(한글 가드 포함)
        rag_context = "\n\n".join(
            f"[자료{i}] (출처:{c.source}) {c.text}" for i, c in enumerate(chunks, 1)
        )
        qwen_out = cs._refine_with_qwen(
            question=q, draft=draft, saju_summary=None,
            evidence=None, rag_context=rag_context, dialect_instruction=None,
        )
        if qwen_out:
            print(f"[2차 qwen ] {len(qwen_out)}자  clean=True  head={qwen_out[:60]!r}")
        else:
            print("[2차 qwen ] 가드 탈락(중국어 드리프트/깨짐) → 폐기")

        # 통합 해석(qwen 우선 → claude 폴백)
        refined, eng = cs._deep_refine(
            question=q, draft=draft, saju_summary=None,
            evidence=None, rag_context=rag_context, dialect_instruction=None,
        )
        print(f"[_deep_refine] engine={eng}  최종 {len(refined) if refined else 0}자")
        if refined and not cs._looks_korean_clean(refined):
            print("  !! 최종 보강본 한글 가드 실패")
            ok = False
        print()

    print("=" * 78)
    print("[OK] 듀얼 엔진 검증 완료" if ok else "[FAIL] 일부 보강본 한글 깨짐")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
