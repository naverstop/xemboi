"""입력 품질 게이트 — 색인 단계에서 저품질·예시 청크를 메인 코퍼스에서 보류(검역).

검색 단계 제외(P0)와 별개로, 애초에 깨진/예시 청크를 코퍼스에 넣지 않는다.
보류분은 data/rag/quarantine/ 에 기록해 관리자가 재OCR·검수할 수 있게 한다.

- partition(chunks, get_category): (accepted, quarantined)로 분리. low_quality 또는 is_example=보류.
- record(run_tag, quarantined, source_stats): 보류 청크 JSONL + 요약(재OCR 소스) 기록.
"""
from __future__ import annotations

import json
from pathlib import Path

from ml.data_pipeline.tagging import tag_chunk

PROJECT_ROOT = Path(__file__).resolve().parents[2]
QUARANTINE_DIR = PROJECT_ROOT / "data" / "rag" / "quarantine"


def partition(chunks, get_category, rules: dict | None = None):
    """청크 리스트를 (accepted, quarantined)로 분리.

    get_category: callable(chunk)->category 또는 category 문자열.
    accepted   : list[(chunk, tags)]          — 메인 코퍼스 색인 대상(tags 그대로 payload 사용)
    quarantined: list[(chunk, tags, reason)]  — 보류(low_quality / is_example / 둘다)
    """
    catf = get_category if callable(get_category) else (lambda _c: get_category)
    accepted: list = []
    quarantined: list = []
    for c in chunks:
        tags = tag_chunk(c.source, catf(c), c.text, rules)
        reason = "+".join(k for k in ("low_quality", "is_example") if tags[k])
        if reason:
            quarantined.append((c, tags, reason))
        else:
            accepted.append((c, tags))
    return accepted, quarantined


def record(run_tag: str, quarantined: list, source_stats: dict, *, reocr_ratio: float = 0.3) -> list[str]:
    """보류 청크를 기록하고, 저품질 비율이 높은 소스를 '재OCR 필요'로 반환.

    quarantined: partition()의 보류 리스트.
    source_stats: {source: {"total": n, "quarantined": q}} — 파일 단위 재OCR 판정용.
    반환: 재OCR 권고 소스 리스트.
    """
    QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
    if quarantined:
        with (QUARANTINE_DIR / f"{run_tag}.jsonl").open("a", encoding="utf-8") as f:
            for c, tags, reason in quarantined:
                f.write(json.dumps({
                    "source": c.source, "chunk_id": c.chunk_id, "reason": reason,
                    "trust_tier": tags.get("trust_tier"), "preview": (c.text or "")[:100],
                }, ensure_ascii=False) + "\n")
    reocr = sorted(
        s for s, st in source_stats.items()
        if st.get("total") and st["quarantined"] / st["total"] > reocr_ratio
    )
    summary = {
        "run": run_tag,
        "quarantined_chunks": len(quarantined),
        "reocr_sources": reocr,  # 저품질 비율 > reocr_ratio → OCR 실패 의심, 재처리 권고
        "by_source": {s: st for s, st in sorted(source_stats.items()) if st["quarantined"]},
    }
    (QUARANTINE_DIR / f"{run_tag}.summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return reocr
