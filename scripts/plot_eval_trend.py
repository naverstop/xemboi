"""
RAG 평가 추이 시각화.

`data/eval/runs.jsonl` 에 누적된 평가 결과를 읽어
- 콘솔 표 (항상)
- PNG 그래프 (matplotlib 있을 때만, --png 옵션)
로 출력한다.

사용:
    python scripts/plot_eval_trend.py
    python scripts/plot_eval_trend.py --png data/eval/trend.png
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS = PROJECT_ROOT / "data" / "eval" / "runs.jsonl"


def load_runs(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def print_table(rows: list[dict]) -> None:
    if not rows:
        print("[no runs] data/eval/runs.jsonl 가 비어있습니다.")
        return
    header = f"{'#':>3}  {'ts':<20}  {'tag':<28}  {'N':>3}  {'hit':>6}  {'top1':>6}  {'topk':>6}  {'p@60':>6}  {'lat(ms)':>8}"
    print(header)
    print("-" * len(header))
    for i, r in enumerate(rows, 1):
        print(
            f"{i:>3}  {r.get('ts',''):<20}  {(r.get('tag') or '-'):<28}  "
            f"{r.get('n_questions', 0):>3}  "
            f"{r.get('keyword_hit_rate_mean', 0):>6.3f}  "
            f"{r.get('top1_score_mean', 0):>6.3f}  "
            f"{r.get('topk_mean_score_mean', 0):>6.3f}  "
            f"{r.get('pass_at_60', 0):>6.3f}  "
            f"{r.get('latency_ms_mean', 0):>8.1f}"
        )
    if len(rows) >= 2:
        first, last = rows[0], rows[-1]
        d_hit = last.get("keyword_hit_rate_mean", 0) - first.get("keyword_hit_rate_mean", 0)
        d_pass = last.get("pass_at_60", 0) - first.get("pass_at_60", 0)
        print()
        print(f"[변화 {first.get('tag','-')} → {last.get('tag','-')}]  "
              f"hit_rate Δ={d_hit:+.3f}   pass@60 Δ={d_pass:+.3f}")


def save_png(rows: list[dict], out: Path) -> bool:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("[skip png] matplotlib 미설치. `pip install matplotlib` 후 재시도.")
        return False
    if not rows:
        print("[skip png] 데이터 없음")
        return False
    xs = list(range(1, len(rows) + 1))
    labels = [r.get("tag") or r.get("ts", "")[:10] for r in rows]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(xs, [r.get("keyword_hit_rate_mean", 0) for r in rows], "o-", label="hit_rate")
    ax.plot(xs, [r.get("pass_at_60", 0) for r in rows], "s-", label="pass@60")
    ax.plot(xs, [r.get("top1_score_mean", 0) for r in rows], "^-", label="top1_score")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
    ax.set_ylim(0, 1)
    ax.set_ylabel("score (0-1)")
    ax.set_title("RAG retrieval trend")
    ax.grid(alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=120)
    try:
        rel = out.resolve().relative_to(PROJECT_ROOT)
        print(f"[png] {rel}")
    except ValueError:
        print(f"[png] {out}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=str(DEFAULT_RUNS), help="runs.jsonl 경로")
    ap.add_argument("--png", default=None, help="PNG 저장 경로 (선택)")
    args = ap.parse_args()

    rows = load_runs(Path(args.runs))
    print_table(rows)
    if args.png:
        save_png(rows, Path(args.png))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
