"""신규 학습자료(학습자료_new)가 채팅 답변에 실제로 반영되는지 end-to-end 검증.

backend chat_service 의 deep 모드 경로를 그대로 사용:
  _search_corpus(RAG) -> _build_user_prompt -> _call_ollama(exaone3.5)

신규 자료에서만 답할 수 있는 질문을 던져, 검색 출처에 S25C(신규)가 잡히고
LLM 답변이 생성되는지까지 확인한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.services import chat_service as cs

SYS = cs.SYSTEM_PROMPT + "\n\n" + cs.PILLAR_NOTATION_RULE

QUESTIONS = [
    "사주로 시험 합격 여부를 보는 방법을 알려줘.",
    "재물복이 있는 사주의 조건을 열매나무 비유로 설명해줘.",
]


def main() -> int:
    for q in QUESTIONS:
        print("=" * 78)
        print("질문:", q)
        chunks = cs._search_corpus(q, 6)
        new_hits = [c for c in chunks if c.source.startswith("S25C")]
        print(f"[RAG] 검색 {len(chunks)}건, 신규(S25C) {len(new_hits)}건")
        for c in chunks:
            tag = "★NEW" if c.source.startswith("S25C") else "    "
            print(f"   {tag} [{c.score:.3f}] {c.source}#c{c.chunk_id}")
        prompt = cs._build_user_prompt(q, chunks, None)
        msgs = [
            {"role": "system", "content": SYS},
            {"role": "user", "content": prompt},
        ]
        print("[LLM] exaone3.5 답변 생성 중...", flush=True)
        ans = cs._call_ollama(msgs)
        print(f"[답변] ({len(ans)}자)\n{ans}\n")
    print("=" * 78)
    print("[OK] 신규 자료 RAG 검색 + LLM 답변 생성 정상")
    return 0


if __name__ == "__main__":
    sys.exit(main())
