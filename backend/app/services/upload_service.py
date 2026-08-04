"""업로드 자료 검수/색인 서비스.

업로드 파일은 즉시 색인되지 않고, 관리자 검수 후 승인 시점에
텍스트 추출(.pdf) → 청킹 → 임베딩 → Qdrant upsert 한다.
승인 직후 RAG 평가는 별도 트리거(예: 일정 배치 후) 가 권장.
"""
from __future__ import annotations

import hashlib
import io
import shutil
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.repositories import upload_repo
from backend.app.repositories.upload_models import Upload

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INBOX_DIR = PROJECT_ROOT / "data" / "inbox"
APPROVED_DIR = PROJECT_ROOT / "data" / "processed" / "uploads"
LEARN_NEW_DIR = PROJECT_ROOT / "학습자료_new"   # 야간 학습 배치의 PDF OCR 대상 적재소

# 관리자/코퍼스 전용 예약 카테고리 — 회원 제출(공개 엔드포인트)로는 사칭할 수 없어야 한다.
#   회원이 자신의 업로드를 예약 카테고리로 라벨링해 탈퇴 시 파기(제21조)를 우회하는 것을 차단하기 위해,
#   회원 제출 경로에서 이 값들을 user_upload 로 강제 치환한다(단일 진실원). zip_import=관리자 zip 일괄,
#   admin_direct=야간 학습 배치 적재본.
RESERVED_UPLOAD_CATEGORIES = ("zip_import", "admin_direct")


def _safe_title(s: str) -> str:
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in s).strip() or "untitled"


def _unique_dest(path: Path) -> Path:
    """동명 파일이 있으면 -1, -2 … 접미사로 회피한 목적지 경로 반환."""
    if not path.exists():
        return path
    i = 1
    while True:
        cand = path.with_name(f"{path.stem}-{i}{path.suffix}")
        if not cand.exists():
            return cand
        i += 1

ALLOWED_KINDS = {"txt", "pdf", "mp4", "image"}
MAX_BYTES = 200 * 1024 * 1024  # 200MB
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff"}


def _ext_to_kind(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in {"txt", "md"}:
        return "txt"
    if ext == "pdf":
        return "pdf"
    # 스캔 이미지(강의자료 사진·캡처) → OCR 대상. pdf 와 동일하게 야간 OCR→색인.
    if ext in IMAGE_EXTS:
        return "image"
    # 영상/음성(강의·상담 녹음) → STT 대상. file_kind="mp4" 워커가 ffmpeg→whisper 처리.
    if ext in {"mp4", "m4a", "mov", "webm", "mp3", "wav", "aac", "flac", "ogg", "opus"}:
        return "mp4"
    raise ValueError(f"unsupported file type: .{ext}")


def _sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def submit_upload(
    db: Session,
    *,
    filename: str,
    content: bytes,
    title: str | None,
    category: str | None,
    note: str | None,
    submitter: str | None,
) -> Upload:
    if len(content) == 0:
        raise ValueError("empty file")
    if len(content) > MAX_BYTES:
        raise ValueError(f"file too large (>{MAX_BYTES // (1024 * 1024)}MB)")
    kind = _ext_to_kind(filename)
    sha = _sha256_of(content)

    dup = upload_repo.find_by_sha(db, sha)
    if dup is not None:
        raise FileExistsError(f"duplicate (sha256={sha[:12]}..., upload_id={dup.id}, status={dup.status})")

    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    sub_id = uuid.uuid4().hex[:12]
    safe_name = filename.replace("/", "_").replace("\\", "_")
    stored = INBOX_DIR / f"{sub_id}__{safe_name}"
    stored.write_bytes(content)

    row = upload_repo.create_upload(
        db,
        title=title or Path(filename).stem,
        category=category or "user_upload",
        note=note,
        submitter=submitter,
        file_kind=kind,
        original_name=filename,
        stored_path=str(stored.relative_to(PROJECT_ROOT)),
        size_bytes=len(content),
        sha256=sha,
        status="pending",
    )
    return row


def list_uploads(db: Session, status: str | None = None, limit: int = 50) -> list[Upload]:
    return upload_repo.list_uploads(db, status=status, limit=limit)


def corpus_chunk_count() -> int | None:
    """Qdrant 코퍼스(saju_corpus) 색인 청크(포인트) 수. 실패/미가동 시 None."""
    s = get_settings()
    try:
        import httpx
        r = httpx.get(f"{s.qdrant_url}/collections/{s.qdrant_collection}", timeout=3.0)
        if r.status_code == 200:
            res = r.json().get("result", {}) or {}
            val = res.get("points_count")
            if val is None:
                val = res.get("vectors_count")
            return int(val) if val is not None else None
    except Exception:  # noqa: BLE001
        return None
    return None


CORPUS_SNAP_PATH = PROJECT_ROOT / "data" / "logs" / "corpus_snapshots.json"


def _load_snapshots() -> list[dict]:
    import json
    try:
        return json.loads(CORPUS_SNAP_PATH.read_text(encoding="utf-8")) or []
    except Exception:  # noqa: BLE001
        return []


def record_corpus_snapshot(chunks: int | None = None) -> None:
    """현재(또는 주어진) 코퍼스 청크 수를 '이번 달' 스냅샷으로 upsert(월별 증가량 그래프용).

    매월 1행. 같은 달이면 최신 값으로 덮어쓴다. 야간 배치 종료 시 + 통계 조회 시 호출.
    """
    import json
    from datetime import date as _date, datetime as _dt

    if chunks is None:
        chunks = corpus_chunk_count()
    if chunks is None:
        return
    month = _date.today().strftime("%Y-%m")
    snaps = _load_snapshots()
    for row in snaps:
        if row.get("month") == month:
            row["chunks"] = int(chunks)
            row["updated_at"] = _dt.utcnow().isoformat()
            break
    else:
        snaps.append({"month": month, "chunks": int(chunks), "updated_at": _dt.utcnow().isoformat()})
    snaps.sort(key=lambda x: x.get("month", ""))
    try:
        CORPUS_SNAP_PATH.parent.mkdir(parents=True, exist_ok=True)
        CORPUS_SNAP_PATH.write_text(json.dumps(snaps, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def monthly_chunks() -> list[dict]:
    """월별 코퍼스 청크(스냅샷) + 전월 대비 증가량(delta)."""
    out: list[dict] = []
    prev: int | None = None
    for row in _load_snapshots():
        c = int(row.get("chunks", 0))
        out.append({"month": row.get("month"), "chunks": c,
                    "delta": (c - prev) if prev is not None else None})
        prev = c
    return out


def stats(db: Session) -> dict:
    """업로드/학습 성과 집계 — 상태별·종류별 분포, 총 청크, 코퍼스 청크, 14일 색인 추세, 월별 청크."""
    from datetime import date as _date, timedelta
    from sqlalchemy import func, select

    by_status = {
        str(k): int(v)
        for k, v in db.execute(
            select(Upload.status, func.count(Upload.id)).group_by(Upload.status)
        ).all()
    }
    by_kind = {
        str(k): int(v)
        for k, v in db.execute(
            select(Upload.file_kind, func.count(Upload.id)).group_by(Upload.file_kind)
        ).all()
    }
    total = sum(by_status.values())
    total_size = int(
        db.execute(select(func.coalesce(func.sum(Upload.size_bytes), 0))).scalar_one() or 0
    )
    sum_chunks = int(
        db.execute(select(func.coalesce(func.sum(Upload.chunks_count), 0))).scalar_one() or 0
    )

    # 최근 14일 일별 색인 추세 — 파일 건수 + 청크 수(자료별 청크 산출량 추적)
    today = _date.today()
    since = today - timedelta(days=13)
    rows = db.execute(
        select(
            func.date(Upload.indexed_at),
            func.count(Upload.id),
            func.coalesce(func.sum(Upload.chunks_count), 0),
        )
        .where(Upload.indexed_at.isnot(None))
        .group_by(func.date(Upload.indexed_at))
    ).all()
    files_map: dict[str, int] = {}
    chunks_map: dict[str, int] = {}
    for d, c, ch in rows:
        if d is None:
            continue
        ds = d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]
        files_map[ds] = files_map.get(ds, 0) + int(c or 0)
        chunks_map[ds] = chunks_map.get(ds, 0) + int(ch or 0)
    trend = [
        {"date": (since + timedelta(days=i)).isoformat(),
         "indexed": files_map.get((since + timedelta(days=i)).isoformat(), 0),
         "chunks": chunks_map.get((since + timedelta(days=i)).isoformat(), 0)}
        for i in range(14)
    ]

    corpus = corpus_chunk_count()
    record_corpus_snapshot(corpus)   # 이번 달 스냅샷 최신화(월별 증가량 그래프용)

    return {
        "total": total,
        "by_status": by_status,
        "by_kind": by_kind,
        "total_size_bytes": total_size,
        "sum_chunks": sum_chunks,
        "indexed_count": by_status.get("indexed", 0),
        "corpus_chunks": corpus,
        "trend": trend,
        "monthly_chunks": monthly_chunks(),
    }


def reject_upload(
    db: Session, upload_id: int, *, reviewer: str | None, comment: str | None
) -> Upload:
    row = upload_repo.get_upload(db, upload_id)
    if row is None:
        raise KeyError(upload_id)
    if row.status != "pending":
        raise ValueError(f"upload {upload_id} not pending (status={row.status})")
    return upload_repo.update_review(db, row, status="rejected", reviewer=reviewer, comment=comment)


# ---------- 텍스트 추출 ----------

def _extract_text_from_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts = [(p.extract_text() or "") for p in reader.pages]
    return "\n\n".join(parts).strip()


def _extract_text(path: Path, kind: str) -> str:
    if kind == "txt":
        return path.read_text(encoding="utf-8", errors="ignore").strip()
    if kind == "pdf":
        return _extract_text_from_pdf(path)
    raise ValueError(f"text extraction not supported for kind={kind}")


# ---------- 승인 + 색인 ----------

def approve_and_index(
    db: Session,
    upload_id: int,
    *,
    reviewer: str | None,
    comment: str | None,
) -> Upload:
    """승인 = 야간 학습 예약. 즉시 색인하지 않는다(GPU 경합·서비스 지연 회피).

    실제 OCR/STT/색인은 자정 이후 야간 학습 배치(scripts/nightly_learning.py)가
    전 과정 CPU 로 일괄 수행한다. 본 함수는 대상만 적재하고 status=approved 로 둔다.
      - pdf/image : 원본을 학습자료_new 로 복사 → 야간 CPU OCR→색인
      - txt       : 텍스트만 추출해 data/processed/uploads 에 저장 → 야간 CPU 색인
      - mp4       : 마킹만 → 야간 CPU STT→색인
    배치가 색인을 마치면 status 를 indexed 로 전이시킨다.
    """
    row = upload_repo.get_upload(db, upload_id)
    if row is None:
        raise KeyError(upload_id)
    if row.status != "pending":
        raise ValueError(f"upload {upload_id} not pending (status={row.status})")

    if row.file_kind == "mp4":
        # 마킹만 — 야간 배치(process_mp4_uploads)가 STT+색인
        upload_repo.update_review(db, row, status="approved", reviewer=reviewer, comment=comment)
        return row

    src_path = PROJECT_ROOT / row.stored_path
    if not src_path.exists():
        raise FileNotFoundError(str(src_path))

    safe_title = _safe_title(row.title)[:60]

    if row.file_kind in ("pdf", "image"):
        # 원본 PDF/이미지를 학습자료_new 로 복사(업로드ID 프리픽스로 야간 배치가 추적).
        # 확장자는 원본 유지 → 야간 OCR 이 PDF/이미지를 구분 처리.
        ext = Path(row.original_name).suffix.lower() or (".pdf" if row.file_kind == "pdf" else ".jpg")
        LEARN_NEW_DIR.mkdir(parents=True, exist_ok=True)
        dst = _unique_dest(LEARN_NEW_DIR / f"u{row.id:05d}_{safe_title}{ext}")
        shutil.copy2(src_path, dst)
        upload_repo.update_review(db, row, status="approved", reviewer=reviewer, comment=comment)
        return row

    # txt: 텍스트 추출(가벼움, GPU 무관)만 지금 수행 → 야간 색인
    text = _extract_text(src_path, row.file_kind)
    if not text or len(text) < 30:
        upload_repo.update_review(db, row, status="rejected",
                                  reviewer=reviewer, comment="텍스트 추출 실패 또는 너무 짧음")
        raise ValueError("extracted text too short / empty")
    APPROVED_DIR.mkdir(parents=True, exist_ok=True)
    out_txt = APPROVED_DIR / f"u{row.id:05d}_{safe_title}.txt"
    out_txt.write_text(text, encoding="utf-8")
    upload_repo.update_review(db, row, status="approved", reviewer=reviewer, comment=comment)
    return row


# ---------- ZIP 일괄 등록 ----------
# 전문가에게 zip 으로 받은 자료를 그대로 올리면 서버가 풀어 기존 업로드 파이프라인에
# 투입한다(파일마다 submit_upload + approve_and_index). pdf/이미지는 학습자료_new 로,
# txt 는 추출본으로 적재되어, 이후 학습 배치가 OCR→색인까지 처리한다.
ZIP_MAX_FILES = 1000                          # zip 폭탄 방지(파일 수 상한)
ZIP_MAX_TOTAL_BYTES = 500 * 1024 * 1024       # zip 폭탄 방지(압축 해제 후 총량 상한)
ZIP_TEXT_EXTS = {"txt", "md"}
ZIP_ALLOWED_EXTS = ZIP_TEXT_EXTS | {"pdf"} | IMAGE_EXTS


def _zip_member_name(info: zipfile.ZipInfo) -> str:
    """zip 멤버명을 안전한 파일명으로 정규화.

    - 경로 구분자를 제거해 basename 만 사용 → 절대경로/'..'(zip-slip) 무력화.
    - UTF-8 플래그가 없으면 zipfile 이 cp437 로 디코딩해 한글이 깨지므로 cp949 로 복원 시도.
    """
    name = info.filename
    if not (info.flag_bits & 0x800):  # 0x800 = UTF-8 파일명 플래그
        try:
            name = name.encode("cp437").decode("cp949")
        except Exception:  # noqa: BLE001
            pass
    return name.replace("\\", "/").split("/")[-1].strip()


def ingest_zip(db: Session, *, content: bytes, submitter: str | None) -> dict:
    """zip 을 풀어 허용 자료(pdf/이미지/txt)를 업로드 파이프라인에 일괄 투입.

    각 파일을 submit_upload(중복 sha 차단) + approve_and_index(학습자료_new/추출본 적재)로
    처리한다. 색인(OCR/임베딩)은 호출부가 트리거하는 학습 배치가 수행한다.
    반환: {extracted, duplicates, skipped, rejected, total_in_zip} (각 파일명 리스트).
    """
    summary: dict = {"extracted": [], "duplicates": [], "skipped": [], "rejected": [], "total_in_zip": 0}
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise ValueError("올바른 zip 파일이 아니에요.")
    infos = [i for i in zf.infolist() if not i.is_dir()]
    summary["total_in_zip"] = len(infos)
    if len(infos) > ZIP_MAX_FILES:
        raise ValueError(f"zip 안의 파일이 너무 많아요(>{ZIP_MAX_FILES}개). 나눠서 올려 주세요.")

    running_total = 0
    for info in infos:
        name = _zip_member_name(info)
        if not name:
            continue
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in ZIP_ALLOWED_EXTS:
            summary["skipped"].append(name)
            continue
        running_total += info.file_size
        if running_total > ZIP_MAX_TOTAL_BYTES:
            raise ValueError(f"압축 해제 용량이 너무 커요(>{ZIP_MAX_TOTAL_BYTES // (1024 * 1024)}MB). 나눠서 올려 주세요.")
        try:
            data = zf.read(info)
        except Exception:  # noqa: BLE001  (암호 zip·손상 멤버)
            summary["skipped"].append(name)
            continue
        try:
            row = submit_upload(
                db, filename=name, content=data, title=None,
                category="zip_import", note="zip 일괄 등록", submitter=submitter,
            )
            approve_and_index(db, row.id, reviewer=submitter or "zip", comment="zip 일괄 등록")
            summary["extracted"].append(name)
        except FileExistsError:
            summary["duplicates"].append(name)        # 이미 등록된 동일 자료(sha 중복)
        except ValueError:
            summary["rejected"].append(name)          # 빈 파일/너무 짧음/추출 실패 등
        except Exception:  # noqa: BLE001
            summary["skipped"].append(name)
    return summary


def _index_single_file(path: Path, *, source_id: str, category: str) -> int:
    """ingest_rag 의 내부 구성요소를 재사용해 단일 파일을 즉시 색인."""
    # 지연 import (모델 로딩 무거움)
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qm
    from sentence_transformers import SentenceTransformer
    import torch

    from ml.data_pipeline.chunker import chunk_file
    from ml.data_pipeline.ingest_rag import (
        COLLECTION,
        EMB_DIM,
        MODEL_NAME,
        stable_point_id,
    )

    s = get_settings()
    chunks = chunk_file(path, source=source_id, target_size=700, max_size=1000, overlap_size=120)
    if not chunks:
        return 0

    # 사주 자원 정책: GPU1 우선(GPU0은 타 서비스). 단일 GPU 환경이면 cuda:0 폴백.
    device = "cpu"
    if torch.cuda.is_available():
        device = "cuda:1" if torch.cuda.device_count() > 1 else "cuda:0"
    model = SentenceTransformer(MODEL_NAME, device=device)

    client = QdrantClient(url=s.qdrant_url, timeout=60.0)
    if not client.collection_exists(COLLECTION):
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=qm.VectorParams(size=EMB_DIM, distance=qm.Distance.COSINE),
        )
        client.create_payload_index(COLLECTION, "source", qm.PayloadSchemaType.KEYWORD)
        client.create_payload_index(COLLECTION, "category", qm.PayloadSchemaType.KEYWORD)

    texts = [c.text for c in chunks]
    vecs = model.encode(texts, batch_size=32, normalize_embeddings=True,
                        show_progress_bar=False, convert_to_numpy=True)
    points = [
        qm.PointStruct(
            id=stable_point_id(c.source, c.chunk_id),
            vector=v.tolist(),
            payload={
                "source": c.source,
                "category": category,
                "chunk_id": c.chunk_id,
                "text": c.text,
                "char_len": c.char_len,
            },
        )
        for c, v in zip(chunks, vecs)
    ]
    client.upsert(collection_name=COLLECTION, points=points, wait=True)
    return len(points)
