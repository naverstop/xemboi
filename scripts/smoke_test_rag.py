"""RAG + Ollama 파이프라인 스모크 테스트.

1. Qdrant 검색이 의미있는 결과를 반환하는지
2. Ollama 호출이 가능한지
3. 사주 엔진이 연동되는지
"""
from __future__ import annotations

import sys
import time
from datetime import date, time as dtime

import httpx

from backend.app.saju.constants import STEM_IS_YANG, STEM_TO_WUXING
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, Gender
from ml.inference.retriever import SajuRetriever


def main() -> int:
    print("=" * 70)
    print("[1] 사주 엔진")
    print("=" * 70)
    birth = BirthInput(
        birth_date=date(1990, 3, 15),
        birth_time=dtime(14, 30),
        gender=Gender.MALE,
    )
    chart = build_chart(birth)
    fp = chart.pillars
    print(f"  년주 {fp.year.gz}  월주 {fp.month.gz}  일주 {fp.day.gz}  시주 {fp.hour.gz}")
    print(f"  일간 {fp.day.stem} ({STEM_TO_WUXING[fp.day.stem]}), 강약 {chart.day_master_strength}")
    print(f"  오행: {chart.wuxing.as_dict_ko()}")
    print(f"  대운: {chart.daewoon.direction} {chart.daewoon.start_age:.1f}세 시작")

    print("\n" + "=" * 70)
    print("[2] Qdrant 검색 (BGE-m3)")
    print("=" * 70)
    t0 = time.time()
    retriever = SajuRetriever()
    print(f"  retriever 로드: {time.time()-t0:.1f}s")

    queries = [
        "정관과 편관의 차이는 무엇인가",
        "신약한 사주에서 용신을 정하는 방법",
        "비견과 겁재가 많을 때 일어나는 현상",
    ]
    for q in queries:
        t0 = time.time()
        hits = retriever.search(q, top_k=3)
        dt = time.time() - t0
        print(f"\n  Q: {q}  ({dt*1000:.0f}ms)")
        for h in hits:
            preview = h.text[:80].replace("\n", " ")
            print(f"    [{h.score:.3f}] {h.source}#chunk{h.chunk_id}: {preview}...")

    print("\n" + "=" * 70)
    print("[3] Ollama 호출")
    print("=" * 70)
    t0 = time.time()
    r = httpx.post(
        "http://127.0.0.1:11434/api/generate",
        json={
            "model": "qwen2.5:7b-instruct-q4_K_M",
            "prompt": "한국 명리학에서 '용신'이라는 용어를 한 문장으로 정의하라.",
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 100},
        },
        timeout=120.0,
    )
    r.raise_for_status()
    out = r.json()
    print(f"  응답 ({time.time()-t0:.1f}s):")
    print(f"  > {out['response'].strip()}")

    print("\n" + "=" * 70)
    print("[OK] 모든 컴포넌트 정상")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
