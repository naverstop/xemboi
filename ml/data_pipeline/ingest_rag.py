"""학습자료 텍스트 → BGE-m3 임베딩 → Qdrant 색인.

사용:
  python -m ml.data_pipeline.ingest_rag
  python -m ml.data_pipeline.ingest_rag --recreate   # 컬렉션 재생성
  python -m ml.data_pipeline.ingest_rag --file "명리전 1 최종"

전제:
  - Qdrant: 127.0.0.1:6333 (docker compose up)
  - 모델: BAAI/bge-m3 (1024-d, dense), 첫 실행시 자동 다운로드 ~2.3GB
  - 입력: data/processed/*.txt + data/ocr/*.txt
"""
from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from ml.data_pipeline.chunker import Chunk, chunk_file
from ml.data_pipeline.tagging import tag_chunk

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COLLECTION = "saju_corpus"
EMB_DIM = 1024  # BGE-m3 dense
MODEL_NAME = "BAAI/bge-m3"


def gather_sources(only: str | None) -> list[Path]:
    """수집 대상 .txt 목록.

    - data/ocr/*.txt        (PDF OCR 결과, 우선)
    - data/processed/*.txt  (PDF PyMuPDF 추출, OCR 본 있으면 스킵)
    - data/processed/youtube/<channel>/*.txt  (YouTube 자막)
    """
    candidates: list[Path] = []
    ocr_dir = PROJECT_ROOT / "data" / "ocr"
    processed_dir = PROJECT_ROOT / "data" / "processed"
    ocr_stems = {p.stem for p in ocr_dir.glob("*.txt")}
    candidates.extend(sorted(ocr_dir.glob("*.txt")))
    for p in sorted(processed_dir.glob("*.txt")):
        if p.stem in ocr_stems:
            continue
        candidates.append(p)
    # YouTube 채널별 하위 폴더 재귀 수집
    yt_root = processed_dir / "youtube"
    if yt_root.exists():
        candidates.extend(sorted(yt_root.glob("*/*.txt")))
    if only:
        candidates = [p for p in candidates if p.stem == only or only in str(p)]
    return candidates


def source_meta(path: Path) -> dict:
    """파일 경로에서 source/category/channel 메타 도출."""
    rel = path.relative_to(PROJECT_ROOT)
    parts = rel.parts
    if len(parts) >= 4 and parts[0] == "data" and parts[1] == "processed" and parts[2] == "youtube":
        # data/processed/youtube/<channel>/<video_id>.txt
        return {
            "source": f"youtube/{parts[3]}/{path.stem}",
            "category": "youtube",
            "channel": parts[3],
            "video_id": path.stem,
        }
    return {"source": path.stem, "category": "pdf"}


def stable_point_id(source: str, chunk_id: int) -> int:
    h = hashlib.blake2b(f"{source}#{chunk_id}".encode("utf-8"), digest_size=8).hexdigest()
    return int(h, 16)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qdrant-url", default="http://127.0.0.1:6333")
    ap.add_argument("--recreate", action="store_true", help="컬렉션 삭제 후 재생성")
    ap.add_argument("--file", default=None, help="특정 파일 stem만 처리")
    ap.add_argument("--batch", type=int, default=32, help="임베딩 배치 크기")
    ap.add_argument("--target", type=int, default=700)
    ap.add_argument("--max", type=int, default=1000)
    ap.add_argument("--overlap", type=int, default=120)
    ap.add_argument("--eval", action="store_true",
                    help="색인 완료 후 RAG retrieval 평가를 자동 실행하고 결과를 runs.jsonl 에 append")
    ap.add_argument("--eval-tag", default=None,
                    help="--eval 시 기록될 태그 (예: after_youtube)")
    args = ap.parse_args()

    sources = gather_sources(args.file)
    if not sources:
        print("[ERR] 처리할 파일이 없습니다.", file=sys.stderr)
        return 2

    print(f"[1/5] 소스 파일 {len(sources)}개:")
    for p in sources:
        print(f"   - {p.relative_to(PROJECT_ROOT)}  ({p.stat().st_size/1024:.1f} KB)")

    # 청킹 + 메타 보존
    print(f"\n[2/5] 청킹 (target={args.target}, max={args.max}, overlap={args.overlap})")
    all_chunks: list[Chunk] = []
    chunk_meta: dict[str, dict] = {}  # source -> meta
    for p in sources:
        meta = source_meta(p)
        src = meta["source"]
        chunk_meta[src] = meta
        cs = chunk_file(
            p,
            source=src,
            target_size=args.target,
            max_size=args.max,
            overlap_size=args.overlap,
        )
        cat = meta.get("category", "?")
        print(f"   [{cat}] {src}: {len(cs)} chunks ({sum(c.char_len for c in cs):,} chars)")
        all_chunks.extend(cs)
    print(f"   TOTAL: {len(all_chunks)} chunks")

    # 입력 품질 게이트: 저품질(OCR 깨짐)·예시명식 청크는 메인 코퍼스에서 보류(검역) → 검색 노이즈/환각 차단
    from ml.data_pipeline.quarantine import partition, record as record_quarantine
    accepted_pairs, quarantined = partition(
        all_chunks, lambda c: chunk_meta.get(c.source, {}).get("category", "pdf"))
    accepted_chunks = [c for c, _t in accepted_pairs]
    if quarantined:
        src_stats: dict = {}
        for c in all_chunks:
            src_stats.setdefault(c.source, {"total": 0, "quarantined": 0})["total"] += 1
        for c, _t, _r in quarantined:
            src_stats[c.source]["quarantined"] += 1
        reocr = record_quarantine(f"ingest_{int(time.time())}", quarantined, src_stats)
        print(f"   [검역] 보류 {len(quarantined)} 청크(저품질/예시) → 메인 색인 제외 (data/rag/quarantine 기록)")
        if reocr:
            print(f"   [재OCR 권고] 저품질 비율>30% 소스 {len(reocr)}개: {reocr[:5]}")
    print(f"   색인 대상(accepted): {len(accepted_chunks)} chunks")

    # 모델 로드 (느린 import)
    print(f"\n[3/5] 임베딩 모델 로드: {MODEL_NAME}")
    t0 = time.time()
    from sentence_transformers import SentenceTransformer
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"   device={device}, torch.cuda.is_available={torch.cuda.is_available()}")
    model = SentenceTransformer(MODEL_NAME, device=device)
    print(f"   model loaded in {time.time()-t0:.1f}s")

    # Qdrant
    print(f"\n[4/5] Qdrant 컬렉션 준비: {COLLECTION} @ {args.qdrant_url}")
    client = QdrantClient(url=args.qdrant_url, timeout=60.0)
    exists = client.collection_exists(COLLECTION)
    if exists and args.recreate:
        client.delete_collection(COLLECTION)
        exists = False
    if not exists:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=qm.VectorParams(size=EMB_DIM, distance=qm.Distance.COSINE),
        )
        client.create_payload_index(COLLECTION, "source", qm.PayloadSchemaType.KEYWORD)
        client.create_payload_index(COLLECTION, "category", qm.PayloadSchemaType.KEYWORD)
        client.create_payload_index(COLLECTION, "channel", qm.PayloadSchemaType.KEYWORD)
        # 신뢰성 게이트용 인덱스(검색기 필터/재랭킹)
        client.create_payload_index(COLLECTION, "trust_tier", qm.PayloadSchemaType.INTEGER)
        client.create_payload_index(COLLECTION, "low_quality", qm.PayloadSchemaType.BOOL)
        client.create_payload_index(COLLECTION, "is_example", qm.PayloadSchemaType.BOOL)
        print(f"   created collection (dim={EMB_DIM}, cosine)")
    else:
        info = client.get_collection(COLLECTION)
        print(f"   existing collection: points={info.points_count}")

    # 임베딩 + upsert (배치)
    print(f"\n[5/5] 임베딩 + upsert (batch={args.batch})")
    t0 = time.time()
    for start in range(0, len(accepted_chunks), args.batch):
        batch = accepted_chunks[start : start + args.batch]
        texts = [c.text for c in batch]
        vecs = model.encode(
            texts,
            batch_size=len(batch),
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        points = []
        for c, v in zip(batch, vecs):
            meta = chunk_meta.get(c.source, {"source": c.source, "category": "pdf"})
            points.append(qm.PointStruct(
                id=stable_point_id(c.source, c.chunk_id),
                vector=v.tolist(),
                payload={
                    **meta,
                    "chunk_id": c.chunk_id,
                    "text": c.text,
                    "char_len": c.char_len,
                    # 신뢰성 태그(검색 게이트용): trust_tier / is_example / low_quality
                    **tag_chunk(c.source, meta.get("category"), c.text),
                },
            ))
        client.upsert(collection_name=COLLECTION, points=points, wait=False)
        done = start + len(batch)
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        eta = (len(accepted_chunks) - done) / rate if rate > 0 else 0
        print(
            f"   [{done:5d}/{len(accepted_chunks)}]  {rate:5.1f} chunks/s  ETA {eta:5.0f}s",
            flush=True,
        )

    info = client.get_collection(COLLECTION)
    print(f"\n[OK] upsert 완료. 컬렉션 points={info.points_count}, 소요 {time.time()-t0:.1f}s")
    if args.eval:
        print("\n" + "=" * 60)
        print("[후처리] RAG retrieval 평가 자동 실행")
        print("=" * 60)
        from ml.eval.eval_retrieval import DEFAULT_DATASET, append_run, evaluate
        result = evaluate(DEFAULT_DATASET, top_k=8,
                          qdrant_url=args.qdrant_url, collection=COLLECTION)
        tag = args.eval_tag or f"ingest_{int(time.time())}"
        path = append_run(result, tag)
        print(f"\n[append] {path.relative_to(PROJECT_ROOT)}  (tag={tag})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
