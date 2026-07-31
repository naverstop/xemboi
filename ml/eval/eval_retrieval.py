"""RAG retrieval 평가.

평가셋 JSONL의 각 질문에 대해 SajuRetriever 로 top-k 청크를 가져와,
expected_keywords 가 청크 본문에 얼마나 포함되는지로 정확도를 측정한다.

메트릭:
- keyword_hit_rate@k : 한 질문의 키워드 중 top-k 청크 전체 텍스트에서 발견된 비율
- top1_score / topk_mean_score : Qdrant cosine 유사도 평균
- latency_ms : 1쿼리당 검색 소요(ms)
- pass_at_60 : 질문 단위로 keyword_hit_rate >= 0.6 이면 통과로 보고, 그 비율

사용:
  python -m ml.eval.eval_retrieval                 # 기본 top_k=8, 모든 질문
  python -m ml.eval.eval_retrieval --top-k 5
  python -m ml.eval.eval_retrieval --tag after_youtube  # 결과 누적시 라벨
  python -m ml.eval.eval_retrieval --no-append          # runs.jsonl 에 안 쓰고 출력만

결과:
  - 콘솔 표
  - data/eval/runs.jsonl 에 한 줄 append (라운드별 추이 그래프 재료)
"""
from __future__ import annotations

import argparse
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Iterable

from ml.inference.retriever import RetrievedChunk, SajuRetriever

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = PROJECT_ROOT / "ml" / "eval" / "datasets" / "rag_qa.jsonl"
RUNS_PATH = PROJECT_ROOT / "data" / "eval" / "runs.jsonl"
# 단일 인스턴스 락: 웹서버 수동실행(/api/eval/run)과 스케줄러 서브프로세스가
# 같은 collection 을 동시에 평가/append 하지 않도록 교차 가드한다(파일에 PID 기록).
RAG_EVAL_LOCK = PROJECT_ROOT / "data" / "eval" / "rag_eval.lock"


@contextmanager
def eval_lock():
    """평가 실행 구간을 표시하는 PID 락. 종료 시 항상 제거."""
    RAG_EVAL_LOCK.parent.mkdir(parents=True, exist_ok=True)
    RAG_EVAL_LOCK.write_text(str(os.getpid()), encoding="utf-8")
    try:
        yield
    finally:
        try:
            RAG_EVAL_LOCK.unlink()
        except FileNotFoundError:
            pass


def load_dataset(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def _keyword_hits(hits: Iterable[RetrievedChunk], keywords: list[str]) -> tuple[int, list[str]]:
    """top-k 청크 전체 텍스트에 키워드가 등장한 개수."""
    blob = "\n".join(h.text for h in hits)
    found = [kw for kw in keywords if kw in blob]
    return len(found), found


def evaluate(
    dataset_path: Path,
    top_k: int,
    qdrant_url: str,
    collection: str,
    pass_threshold: float = 0.6,
) -> dict:
    retriever = SajuRetriever(url=qdrant_url, collection=collection)
    rows = load_dataset(dataset_path)

    per_q: list[dict] = []
    total_lat = 0.0
    total_pass = 0
    hit_rates: list[float] = []
    top1_scores: list[float] = []
    topk_mean_scores: list[float] = []

    print(f"\n=== RAG Retrieval Eval (top_k={top_k}, n={len(rows)}) ===")
    print(f"{'id':<6} {'hit/total':<10} {'rate':<6} {'top1':<7} {'topkAvg':<8} {'ms':<6}  question")

    for r in rows:
        kws: list[str] = r["expected_keywords"]
        t0 = time.perf_counter()
        hits = retriever.search(r["question"], top_k=top_k)
        lat = (time.perf_counter() - t0) * 1000

        found_n, found = _keyword_hits(hits, kws)
        rate = found_n / max(len(kws), 1)
        top1 = hits[0].score if hits else 0.0
        topk_mean = mean(h.score for h in hits) if hits else 0.0
        passed = rate >= pass_threshold

        per_q.append({
            "id": r["id"],
            "question": r["question"],
            "keywords": kws,
            "keywords_found": found,
            "hit_rate": round(rate, 3),
            "top1_score": round(top1, 4),
            "topk_mean_score": round(topk_mean, 4),
            "latency_ms": round(lat, 1),
            "passed": passed,
        })
        hit_rates.append(rate)
        top1_scores.append(top1)
        topk_mean_scores.append(topk_mean)
        total_lat += lat
        total_pass += int(passed)

        mark = "✅" if passed else "❌"
        print(f"{r['id']:<6} {found_n:>2}/{len(kws):<6} {rate:<6.2f} {top1:<7.4f} "
              f"{topk_mean:<8.4f} {lat:<6.0f} {mark} {r['question'][:50]}")

    try:
        ds_label = str(dataset_path.relative_to(PROJECT_ROOT))
    except ValueError:
        # PROJECT_ROOT 밖이거나 상대경로로 받은 경우(수동 CLI) — 전체 경로로 폴백.
        ds_label = str(dataset_path)
    summary = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "dataset": ds_label,
        "n_questions": len(rows),
        "top_k": top_k,
        "collection": collection,
        "keyword_hit_rate_mean": round(mean(hit_rates), 4) if hit_rates else 0.0,
        "top1_score_mean": round(mean(top1_scores), 4) if top1_scores else 0.0,
        "topk_mean_score_mean": round(mean(topk_mean_scores), 4) if topk_mean_scores else 0.0,
        f"pass_at_{int(pass_threshold*100)}": round(total_pass / max(len(rows), 1), 4),
        "latency_ms_mean": round(total_lat / max(len(rows), 1), 1),
    }
    print("\n" + "-" * 80)
    print("[요약]")
    for k, v in summary.items():
        print(f"  {k:<30} {v}")

    return {"summary": summary, "per_question": per_q}


def append_run(result: dict, tag: str | None) -> Path:
    RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = dict(result["summary"])
    if tag:
        record["tag"] = tag
    with RUNS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return RUNS_PATH


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(DEFAULT_DATASET))
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    ap.add_argument("--collection", default="saju_corpus")
    ap.add_argument("--pass-threshold", type=float, default=0.6,
                    help="질문 통과 기준: keyword_hit_rate >= threshold (기본 0.6)")
    ap.add_argument("--tag", help="run 라벨 (예: baseline, after_youtube)")
    ap.add_argument("--no-append", action="store_true", help="runs.jsonl에 기록하지 않음")
    ap.add_argument("--detail-json", help="질문별 상세 결과 JSON으로 저장")
    args = ap.parse_args()

    with eval_lock():  # 수동/스케줄 평가 동시 실행 방지(교차 가드)
        result = evaluate(
            Path(args.dataset),
            args.top_k,
            args.qdrant_url,
            args.collection,
            args.pass_threshold,
        )
        if not args.no_append:
            path = append_run(result, args.tag)
            print(f"\n[append] {path.relative_to(PROJECT_ROOT)}")
    if args.detail_json:
        out = Path(args.detail_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[detail] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
