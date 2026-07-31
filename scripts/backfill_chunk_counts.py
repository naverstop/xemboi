# -*- coding: utf-8 -*-
"""기존 indexed 업로드의 chunks_count 소급 보정(backfill).

배경: 과거 색인분(특히 업로드 화면/zip 경유)은 chunks_count 가 0 으로 기록됐다.
실제 색인 청크는 Qdrant 코퍼스에 source 단위로 들어가 있으므로, source 별 포인트
수를 세어 Upload.chunks_count 를 채운다. 이후 '학습 성과 → 일별 추세(청크 수)'에
과거분도 실제 청크로 반영된다.

source 키 규칙(색인 시점 기준):
  - pdf/이미지 업로드 : 학습자료_new 파일명 stem = "u{id:05d}_{safe_title[:60]}"
  - txt 업로드        : "upload/{id}_{safe_title[:60]}"
  - 직접 투입분        : 원본 stem (이미 실제값이 들어가 있어 보정 대상 아님)

실행:  .venv\\Scripts\\python.exe -m scripts.backfill_chunk_counts [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass


def _source_keys(u) -> list[str]:
    from backend.app.services.upload_service import _safe_title
    st = _safe_title(u.title)[:60]
    if u.file_kind in ("pdf", "image"):
        # 업로드/zip 경유분(u-프리픽스) + 혹시 모를 직접분(raw stem) 둘 다 시도
        return [f"u{u.id:05d}_{st}", st]
    if u.file_kind == "txt":
        return [f"upload/{u.id}_{st}"]
    return []


def _count_source(client, collection: str, key: str) -> int:
    from qdrant_client.http import models as qm
    r = client.count(
        collection_name=collection,
        count_filter=qm.Filter(must=[qm.FieldCondition(key="source", match=qm.MatchValue(value=key))]),
        exact=True,
    )
    return int(r.count)


def main() -> int:
    ap = argparse.ArgumentParser(description="indexed 업로드 chunks_count 소급 보정")
    ap.add_argument("--dry-run", action="store_true", help="DB 변경 없이 보정 예정만 출력")
    args = ap.parse_args()

    from qdrant_client import QdrantClient
    from backend.app.core.config import get_settings
    from backend.app.core.db import get_session_factory
    from backend.app.repositories import upload_repo

    s = get_settings()
    collection = s.qdrant_collection
    client = QdrantClient(url=s.qdrant_url, timeout=60.0)
    if not client.collection_exists(collection):
        print(f"[!] Qdrant 컬렉션 없음: {collection}")
        return 1

    sf = get_session_factory()
    scanned = updated = filled = 0
    samples: list[str] = []
    with sf() as db:
        rows = upload_repo.list_uploads(db, status="indexed", limit=100000)
        for u in rows:
            scanned += 1
            if u.chunks_count and u.chunks_count > 0:
                continue  # 이미 실제값 존재 → 건너뜀
            best = 0
            for key in _source_keys(u):
                try:
                    c = _count_source(client, collection, key)
                except Exception as e:  # noqa: BLE001
                    print(f"  [warn] count 실패 id={u.id} key={key}: {e}")
                    c = 0
                best = max(best, c)
            if best > 0:
                filled += 1
                if len(samples) < 8:
                    samples.append(f"id={u.id} '{u.title[:24]}' → {best}청크")
                if not args.dry_run:
                    u.chunks_count = best
                    updated += 1
        if not args.dry_run:
            db.commit()

    print(f"[backfill] indexed 스캔 {scanned}건 / 보정대상(0·null) 중 청크 확인 {filled}건"
          + (f" / DB 반영 {updated}건" if not args.dry_run else " / (dry-run, 미반영)"))
    for ex in samples:
        print("   - " + ex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
