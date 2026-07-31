"""CLI 사주 상담 데모: 사주명식 계산 + RAG + Ollama(Qwen2.5-7B).

사용:
  python -m ml.inference.chat_cli                       # 사주 없이 일반 상담
  python -m ml.inference.chat_cli --birth 1990-03-15 --time 14:30 --gender male

명령:
  /quit        종료
  /reset       대화 초기화
  /sources     마지막 답변 출처 보기
  /k 8         top_k 변경
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, time as dtime

import httpx

from backend.app.saju.constants import STEM_IS_YANG, STEM_TO_WUXING
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, Gender
from ml.inference.retriever import RetrievedChunk, SajuRetriever


OLLAMA_URL = "http://127.0.0.1:11434"
MODEL = "qwen2.5:7b-instruct-q4_K_M"


SYSTEM_PROMPT_BASE = """당신은 한국 명리학(사주팔자) 전문 상담사입니다.

원칙:
1. 답변은 반드시 제공된 [참고자료] 안의 내용에 근거하여 작성하세요. 자료에 없는 내용을 추측하지 마세요.
2. 자료가 부족하면 "제공된 자료에 명확한 답이 없습니다"라고 솔직히 말하세요.
3. 한국어로 답변하고, 한자 술어는 한글(한자) 형식으로 표기하세요. 예: 정관(正官), 비견(比肩).
4. 길흉 단정은 피하고, 가능성과 흐름으로 설명하세요.
5. 응답은 3~7문장으로 간결하게 작성하세요.
"""


@dataclass
class ChatState:
    history: list[dict]  # [{role, content}]
    last_sources: list[RetrievedChunk]
    top_k: int


def build_saju_block(args) -> str | None:
    if not (args.birth and args.time and args.gender):
        return None
    y, m, d = map(int, args.birth.split("-"))
    hh, mm = map(int, args.time.split(":"))
    birth = BirthInput(
        birth_date=date(y, m, d),
        birth_time=dtime(hh, mm),
        gender=Gender(args.gender),
    )
    chart = build_chart(birth)
    fp = chart.pillars
    day_stem = fp.day.stem
    day_yy = "양" if STEM_IS_YANG[day_stem] else "음"
    hour_str = fp.hour.gz if fp.hour else "시미상"
    lines = [
        f"[사주명식] 양력 {args.birth} {args.time} {args.gender}",
        f"  년주 {fp.year.gz}  월주 {fp.month.gz}  일주 {fp.day.gz}  시주 {hour_str}",
        f"  일간(本人): {day_stem} ({STEM_TO_WUXING[day_stem]}), 음양: {day_yy}",
        f"  일간 강약: {chart.day_master_strength}",
        f"  오행 분포: {chart.wuxing.as_dict_ko()}",
    ]
    if chart.daewoon:
        dw = chart.daewoon
        dir_ko = "순행" if dw.direction == "forward" else "역행"
        lines.append(f"  대운 방향: {dir_ko}, 대운수: {dw.start_age:.1f}세")
        if dw.entries:
            first = dw.entries[0]
            lines.append(f"  첫 대운: {first.pillar.gz} ({first.start_age}세~)")
    return "\n".join(lines)


def build_user_prompt(question: str, ctx_chunks: list[RetrievedChunk], saju_block: str | None) -> str:
    parts = []
    if saju_block:
        parts.append(saju_block)
    if ctx_chunks:
        parts.append("[참고자료]")
        for i, c in enumerate(ctx_chunks, 1):
            parts.append(f"--- 자료{i} (출처: {c.source}, score={c.score:.3f}) ---\n{c.text}")
    parts.append(f"[질문]\n{question}")
    return "\n\n".join(parts)


def call_ollama(messages: list[dict]) -> str:
    payload = {"model": MODEL, "messages": messages, "stream": False, "options": {"temperature": 0.4}}
    r = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=180.0)
    r.raise_for_status()
    return r.json()["message"]["content"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--birth", help="YYYY-MM-DD (양력)")
    ap.add_argument("--time", help="HH:MM")
    ap.add_argument("--gender", choices=["male", "female"])
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()

    saju_block = build_saju_block(args)
    if saju_block:
        print("=" * 60)
        print(saju_block)
        print("=" * 60)
    else:
        print("[i] 사주 정보 미입력 — 일반 명리학 Q&A 모드")

    print("[i] 임베딩 + Qdrant 연결 중...")
    retriever = SajuRetriever()
    print(f"[i] Ollama 모델: {MODEL}")
    print("[i] '/quit' 종료, '/reset' 초기화, '/sources' 출처, '/k N' top_k 변경\n")

    state = ChatState(history=[{"role": "system", "content": SYSTEM_PROMPT_BASE}], last_sources=[], top_k=args.top_k)

    while True:
        try:
            q = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q == "/quit":
            break
        if q == "/reset":
            state.history = [{"role": "system", "content": SYSTEM_PROMPT_BASE}]
            state.last_sources = []
            print("[i] 대화 초기화됨")
            continue
        if q == "/sources":
            if not state.last_sources:
                print("[i] 출처 없음")
            for c in state.last_sources:
                print(f"  - {c.source}#chunk{c.chunk_id}  (score={c.score:.3f})")
                print(f"    {c.text[:120].replace(chr(10), ' ')}...")
            continue
        if q.startswith("/k "):
            try:
                state.top_k = int(q.split()[1])
                print(f"[i] top_k = {state.top_k}")
            except (IndexError, ValueError):
                print("[!] 사용법: /k 5")
            continue

        # 검색
        chunks = retriever.search(q, top_k=state.top_k)
        state.last_sources = chunks
        user_msg = build_user_prompt(q, chunks, saju_block)

        # 호출
        state.history.append({"role": "user", "content": user_msg})
        try:
            answer = call_ollama(state.history)
        except httpx.HTTPError as e:
            print(f"[ERR] Ollama 호출 실패: {e}", file=sys.stderr)
            state.history.pop()
            continue
        state.history.append({"role": "assistant", "content": answer})

        print(f"\n{answer}")
        print(f"\n[참고 {len(chunks)}건: {', '.join(c.source for c in chunks)}]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
