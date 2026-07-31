"""MP4 업로드 자막 추출 워커.

`status=approved` 이면서 `file_kind=mp4` 인 업로드를 찾아
1) ffmpeg 로 오디오 추출 (.wav 16k mono)
2) faster-whisper 로 한국어 자막 추출
3) data/processed/uploads/u<id>_<title>.txt 로 저장
4) 단일 파일 색인 → status=indexed 마킹

사용:
    python -m scripts.process_mp4_uploads
    python -m scripts.process_mp4_uploads --model medium --device cuda
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# 업로드 STT(whisper) + 색인(bge-m3)은 CPU 전용 — 영상생성(GPU0) 등과의 경합 차단.
# torch/faster-whisper import 이전에 GPU 를 숨겨, 직접 실행 시에도 GPU 를 잡지 않는다.
# "-1" 사용: 빈 문자열("")은 torch 에서 GPU 를 숨기지 못함(실측). "-1" 이라야 차단됨.
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.db import get_session_factory  # noqa: E402
from backend.app.repositories import upload_repo  # noqa: E402
from backend.app.services.upload_service import (  # noqa: E402
    APPROVED_DIR,
    _index_single_file,
)


def _safe_title(s: str) -> str:
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in s).strip() or "untitled"


def _ffmpeg_to_wav(src: Path, dst: Path) -> None:
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(src),
        "-vn", "-ac", "1", "-ar", "16000",
        "-f", "wav",
        str(dst),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr.strip()[:200]}")


def process_pending_mp4(model_name: str, device: str, compute_type: str, limit: int) -> int:
    """음성/영상 업로드(file_kind=mp4) STT+색인. 처리 건수 반환.

    자동 처리(승인 불필요): status가 pending 또는 approved 인 항목을 모두 처리한다.
    (indexed/rejected/failed 는 제외)
    """
    from ml.data_pipeline.whisper_transcribe import transcribe_file

    sf = get_session_factory()
    processed = 0
    APPROVED_DIR.mkdir(parents=True, exist_ok=True)

    with sf() as db:
        rows = upload_repo.list_uploads(db, status=None, limit=500)
        targets = [
            r for r in rows
            if r.file_kind == "mp4" and r.status in ("pending", "approved")
        ][:limit]
        if not targets:
            print("[done] 처리할 음성/영상 업로드 없음(pending/approved)")
            return 0
        print(f"[start] 음성/영상 STT 대상 {len(targets)}건")

        for row in targets:
            t0 = time.time()
            src = PROJECT_ROOT / row.stored_path
            if not src.exists():
                print(f"  [u{row.id}] 원본 누락: {src}")
                row.status = "failed"
                row.review_comment = (row.review_comment or "") + "\n[mp4 worker] source missing"
                db.commit()
                continue

            print(f"  [u{row.id}] {row.title}  ({src.stat().st_size/1024/1024:.1f} MB)")
            wav = src.with_suffix(".wav")
            try:
                _ffmpeg_to_wav(src, wav)
                text = transcribe_file(wav, model_name, device, compute_type).strip()
            except Exception as e:
                print(f"     ERR: {e}")
                row.status = "failed"
                row.review_comment = (row.review_comment or "") + f"\n[mp4 worker] {e}"[:500]
                db.commit()
                if wav.exists():
                    wav.unlink()
                continue
            finally:
                if wav.exists():
                    try:
                        wav.unlink()
                    except Exception:
                        pass

            if not text or len(text) < 30:
                row.status = "failed"
                row.review_comment = "[mp4 worker] empty transcript"
                db.commit()
                print("     ERR: 빈 자막")
                continue

            safe = _safe_title(row.title)
            out_txt = APPROVED_DIR / f"u{row.id:05d}_{safe[:60]}.txt"
            out_txt.write_text(text, encoding="utf-8")

            chunks = _index_single_file(
                out_txt, source_id=f"upload/{row.id}_{safe[:60]}", category=row.category
            )
            upload_repo.mark_indexed(
                db, row, source=f"upload/{row.id}_{safe[:60]}", chunks=chunks
            )
            processed += 1
            print(f"     OK chunks={chunks}, {time.time()-t0:.1f}s, chars={len(text)}")

    print(f"\n[done] {processed} 건 색인 완료")
    return processed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="small", help="faster-whisper 모델 (small/medium/large-v3)")
    # 기본 CPU — 업로드 STT 는 CPU 전용 정책(모듈 상단 CUDA 차단과 일관)
    ap.add_argument("--device", default="cpu", choices=["auto", "cpu", "cuda"])
    ap.add_argument("--compute-type", default="int8", help="int8/int8_float16/float16")
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        print("[ERR] ffmpeg 필요. 시스템 PATH 확인.", file=sys.stderr)
        return 2

    device = args.device
    if device == "auto":
        try:
            import torch  # noqa: F401
            device = "cuda" if __import__("torch").cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"

    n = process_pending_mp4(args.model, device, args.compute_type, args.limit)
    return 0 if n >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
