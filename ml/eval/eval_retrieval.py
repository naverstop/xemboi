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


# ── 운영 파이프라인 정렬 (P3-D2) ────────────────────────────────────────
# [전수감사 2026-07-22] 이 평가는 **운영 검색을 재지 않았다**. SajuRetriever(url, collection)
# 만 넘겨 리랭커 None·min_score 0·게이트 3종 off·tier_boosts 없음이었고 top_k 도 8(운영 4).
# 후보 풀이 17,746 vs 9,441 로 1.88배, k 도 2배라 한 방향으로만 과대평가됐다.
# 그 결과 리랭커 분기의 min_score·tier_boosts 무효 버그가 33일간(c694728e→a49a825d) 살아
# 있는 동안에도 pass@60 은 0.84~0.90 으로 정상 표시됐다 — 평가가 그 코드 경로를 한 번도
# 안 탔기 때문이다. 이제 운영 설정을 그대로 읽어 같은 파이프라인을 잰다.
#
# ⛔⛔ 승인 없이 되돌리지 마세요 — "점수가 떨어졌으니 롤백"이 가장 위험한 반응입니다 ⛔⛔
#   정렬 직후 점수는 **크게 떨어지는 것이 정상**이고, 그 떨어진 값이 진짜 현재 운영 품질이다.
#   옛 값(0.84~0.90)은 게이트 없이 후보 풀 1.88배·k 2배로 잰 수치라 운영을 1비트도 재지 않았다.
#   runs.jsonl 의 eval_mode='aligned'·gate 필드와 /trend 의 '운영정렬/옛측정' 배지·'조건변경'
#   표시를 지우지 마세요 — 지우면 정렬 전후를 섞어 보고 잘못된 롤백이 일어난다.
#   옛 방식으로 재보고 싶으면 되돌리지 말고 `--legacy` 플래그를 쓸 것.
#   관련: docs/rag_hallucination_audit_2026-07-22.md 4장
#   테스트: backend/tests/test_p3_rag_coverage.py::test_eval_reads_ops_settings
def _ops_settings() -> dict:
    """운영(backend) 설정을 읽어 평가 파라미터로. 백엔드 임포트 실패 시 안전 기본값."""
    try:
        from backend.app.core.config import get_settings
        s = get_settings()
        return {
            "top_k": max(1, min(s.rag_top_k_default, s.rag_max_top_k)),
            "min_score": s.rag_min_score,
            "exclude_low_quality": s.rag_exclude_low_quality,
            "exclude_youtube": s.rag_exclude_youtube,
            "tier_boosts": {1: s.rag_tier1_boost, 2: s.rag_tier2_boost, 3: 0.0},
            "rerank": s.rag_reranker_enabled,
            "rerank_top_n": s.rag_rerank_top_n,
            "rerank_min_score": s.rag_reranker_min_score,
            "reranker_model": (s.rag_reranker_model if s.rag_reranker_enabled else None),
            "embed_device": s.rag_embed_device,
            "pdf_boost": s.rag_pdf_boost,
            "over_fetch": s.rag_over_fetch,
        }
    except Exception:  # noqa: BLE001
        return {}


def evaluate(
    dataset_path: Path,
    top_k: int,
    qdrant_url: str,
    collection: str,
    pass_threshold: float = 0.6,
    *,
    align_ops: bool = True,
) -> dict:
    ops = _ops_settings() if align_ops else {}
    # 평가는 CPU 강제 — 운영 리랭커가 GPU1(ollama와 공유, 여유 ~1GB)을 쓰고 있어
    # 여기서 cuda 를 잡으면 OOM 또는 VRAM 영구 점유가 난다(D-7).
    dev = "cpu"
    if ops:
        top_k = ops["top_k"]
        retriever = SajuRetriever(
            url=qdrant_url, collection=collection, device=dev,
            pdf_boost=ops["pdf_boost"], over_fetch=ops["over_fetch"],
            reranker_model=ops["reranker_model"], reranker_device=dev,
        )
        gate = dict(
            min_score=ops["min_score"], exclude_low_quality=ops["exclude_low_quality"],
            exclude_examples=True,          # chat_service._search_corpus 와 동일(하드코딩)
            exclude_youtube=ops["exclude_youtube"], tier_boosts=ops["tier_boosts"],
            rerank=ops["rerank"], rerank_top_n=ops["rerank_top_n"],
            rerank_min_score=ops["rerank_min_score"],
        )
    else:
        retriever = SajuRetriever(url=qdrant_url, collection=collection, device=dev)
        gate = {}
    rows = load_dataset(dataset_path)

    per_q: list[dict] = []
    total_lat = 0.0
    total_pass = 0
    hit_rates: list[float] = []
    top1_scores: list[float] = []
    topk_mean_scores: list[float] = []
    chunk_counts: list[int] = []
    zero_hits = 0

    print(f"\n=== RAG Retrieval Eval (top_k={top_k}, n={len(rows)}) ===")
    print(f"{'id':<6} {'hit/total':<10} {'rate':<6} {'top1':<7} {'topkAvg':<8} {'ms':<6}  question")

    for r in rows:
        kws: list[str] = r["expected_keywords"]
        t0 = time.perf_counter()
        hits = retriever.search(r["question"], top_k=top_k, **gate)
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
        chunk_counts.append(len(hits))
        zero_hits += int(not hits)
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
        # [P3-D2/D6] 운영 정렬 여부와 게이트 값 — /trend 가 이 값이 바뀐 지점에 추세 단절선을
        # 긋는다. 이걸 안 남기면 정렬 전후 점수를 섞어 보고 "품질 급락"으로 오독한다.
        "eval_mode": "aligned" if gate else "legacy",
        "gate": {k: v for k, v in gate.items() if k != "tier_boosts"} or None,
        # 0건은 운영에서 실제로 일어나는 최악 케이스인데 legacy 평가는 게이트가 없어
        # 구조적으로 0건이 나올 수 없었다 → 이제 지표로 남긴다.
        "zero_hit_rate": round(zero_hits / max(len(rows), 1), 4),
        "mean_chunks_returned": round(mean(chunk_counts), 2) if chunk_counts else 0.0,
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
    # 기본값 0 = 운영 설정(rag_top_k_default)을 따른다. 예전 기본 8은 운영(4)의 두 배라
    # 회수 기회를 두 배로 주는 셈이었다 — 지표 과대평가의 절반이 여기서 나왔다.
    ap.add_argument("--top-k", type=int, default=0)
    ap.add_argument("--legacy", action="store_true",
                    help="운영 게이트 없이 예전 방식으로 측정(과거 런과 비교용)")
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
            args.top_k or 8,          # align_ops=True 면 evaluate 안에서 운영 top_k로 덮어씀
            args.qdrant_url,
            args.collection,
            args.pass_threshold,
            align_ops=not args.legacy,
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
