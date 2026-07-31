# -*- coding: utf-8 -*-
"""기존 Qdrant 코퍼스에 신뢰성 메타(trust_tier·is_example·low_quality) 재태깅.

ingest 당시엔 없던 신뢰성 태그를 모든 기존 포인트에 소급 부여한다(멱등 — 재실행 안전).
검색기는 이 태그로 저신뢰·예시·깨진 청크를 걸러내고 신뢰등급으로 재랭킹한다.

실행:
  python -m scripts.retag_corpus            # 전체 재태깅 + 분포 출력
  python -m scripts.retag_corpus --dry-run  # 변경 없이 분포만
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from ml.data_pipeline.tagging import tag_chunk

COLLECTION = "saju_corpus"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--batch", type=int, default=256)
    args = ap.parse_args()

    c = QdrantClient(url=args.qdrant_url, timeout=60.0)
    if not c.collection_exists(COLLECTION):
        print(f"[ERR] 컬렉션 {COLLECTION} 없음", file=sys.stderr)
        return 2

    # 필터용 payload 인덱스(없으면 생성) — 재실행 안전
    if not args.dry_run:
        for field in ("trust_tier", "low_quality", "is_example"):
            try:
                schema = qm.PayloadSchemaType.INTEGER if field == "trust_tier" else qm.PayloadSchemaType.BOOL
                c.create_payload_index(COLLECTION, field, schema)
            except Exception:  # noqa: BLE001 — 이미 있으면 무시
                pass

    tier = Counter(); ex = 0; lq = 0; tot = 0
    off = None
    # 태그 조합(3×2×2=12종)별로 포인트 id를 모아 그룹당 1회 set_payload → 11k 개별호출 회피
    groups: dict[tuple, list] = {}

    while True:
        pts, off = c.scroll(
            COLLECTION, limit=args.batch, offset=off,
            with_payload=["source", "category", "text"], with_vectors=False,
        )
        if not pts:
            break
        for p in pts:
            pl = p.payload or {}
            t = tag_chunk(pl.get("source", ""), pl.get("category"), pl.get("text", ""))
            tier[t["trust_tier"]] += 1
            ex += int(t["is_example"]); lq += int(t["low_quality"]); tot += 1
            key = (t["trust_tier"], t["is_example"], t["low_quality"])
            groups.setdefault(key, []).append(p.id)
        print(f"  ...{tot} 스캔", end="\r", flush=True)
        if off is None:
            break

    if not args.dry_run:
        print()
        for (ti, exf, lqf), ids in groups.items():
            payload = {"trust_tier": ti, "is_example": exf, "low_quality": lqf}
            for i in range(0, len(ids), 1000):  # set_payload 1회당 최대 1000 id
                c.set_payload(COLLECTION, payload=payload, points=ids[i:i + 1000], wait=True)
            print(f"  set {payload} → {len(ids)} 포인트")

    print(f"\n총 {tot} 청크 {'(dry-run, 미변경)' if args.dry_run else '재태깅 완료'}")
    print(f"  신뢰등급: tier1={tier[1]}  tier2={tier[2]}  tier3={tier[3]}")
    print(f"  예시명식 제외대상: {ex} ({100*ex/max(tot,1):.1f}%)")
    print(f"  저품질 제외대상: {lq} ({100*lq/max(tot,1):.1f}%)")
    if not args.dry_run:
        info = c.get_collection(COLLECTION)
        print(f"  컬렉션 points={info.points_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
