"""YouTube 자막이 없는 영상 → faster-whisper STT.

흐름:
  1) data/raw/youtube/<channel>/transcribe_queue.txt 의 video_id 읽기
     (이미 자막/STT 결과가 존재하면 skip)
  2) yt-dlp로 m4a/opus 오디오만 임시 다운로드
  3) faster-whisper로 한국어 STT → 텍스트
  4) data/processed/youtube/<channel>/<vid>.txt 로 저장 (헤더 포함)
  5) data/raw/youtube/<channel>/captions/<vid>.txt 에도 평문 백업
  6) 처리 끝난 vid는 queue에서 제거

사용:
  python -m ml.data_pipeline.whisper_transcribe                # 모든 채널 큐
  python -m ml.data_pipeline.whisper_transcribe --channel cheonsewon
  python -m ml.data_pipeline.whisper_transcribe --model medium --device cuda
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

# YouTube STT 도 CPU 전용으로 강제 — 영상생성(GPU0) 등과의 경합 차단(한시적 수집 작업).
# torch/faster-whisper import 이전에 GPU 숨김. "-1" 사용("" 은 torch 에서 무효, 실측).
os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CHANNELS = ["cheonsewon", "hyunmyung", "haengun"]
CHANNEL_NAME_KO = {
    "cheonsewon": "천세원 명리교실",
    "hyunmyung": "행운사주철학관",
    "haengun": "현명역술원",
}


def load_index(channel: str) -> dict[str, dict]:
    """index.jsonl → {video_id: meta}."""
    p = PROJECT_ROOT / "data" / "raw" / "youtube" / channel / "index.jsonl"
    out: dict[str, dict] = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            j = json.loads(line)
            if j.get("video_id"):
                out[j["video_id"]] = j
        except Exception:
            pass
    return out


def load_queue(channel: str) -> list[tuple[str, str]]:
    """transcribe_queue.txt → [(vid, title), ...]."""
    p = PROJECT_ROOT / "data" / "raw" / "youtube" / channel / "transcribe_queue.txt"
    out: list[tuple[str, str]] = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.rstrip()
        if not line:
            continue
        if "\t" in line:
            vid, title = line.split("\t", 1)
        else:
            vid, title = line, ""
        out.append((vid, title))
    return out


def save_queue(channel: str, remaining: list[tuple[str, str]]) -> None:
    p = PROJECT_ROOT / "data" / "raw" / "youtube" / channel / "transcribe_queue.txt"
    if remaining:
        p.write_text("\n".join(f"{v}\t{t}" for v, t in remaining), encoding="utf-8")
    else:
        if p.exists():
            p.unlink()


def download_audio(video_id: str, out_dir: Path) -> Path | None:
    """yt-dlp로 오디오만 다운로드. 반환: 생성된 파일 경로."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    url = f"https://www.youtube.com/watch?v={video_id}"
    out_tpl = str(out_dir / "%(id)s.%(ext)s")
    opts = {
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": out_tpl,
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "retries": 5,
        "fragment_retries": 5,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "m4a",
                "preferredquality": "0",
            }
        ],
        "extractor_args": {"youtube": {"player_client": ["web", "tv", "android_vr"]}},
    }
    try:
        with YoutubeDL(opts) as ydl:
            ydl.download([url])
    except DownloadError as e:
        print(f"  [audio 실패] {video_id}: {str(e)[:120]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [audio 예외] {video_id}: {e}", file=sys.stderr)
        return None

    # 확장자 다양 → 가장 큰 파일 1개 선택
    cands = sorted(out_dir.glob(f"{video_id}.*"), key=lambda p: p.stat().st_size, reverse=True)
    return cands[0] if cands else None


_WHISPER_MODEL = None


def get_whisper(model: str, device: str, compute_type: str):
    global _WHISPER_MODEL
    if _WHISPER_MODEL is None:
        from faster_whisper import WhisperModel

        print(f"[whisper] 모델 로드 model={model} device={device} compute={compute_type}")
        t0 = time.time()
        _WHISPER_MODEL = WhisperModel(model, device=device, compute_type=compute_type)
        print(f"[whisper] 로드 완료 ({time.time()-t0:.1f}s)")
    return _WHISPER_MODEL


def transcribe_file(audio: Path, model_name: str, device: str, compute_type: str, lang: str = "ko") -> str:
    model = get_whisper(model_name, device, compute_type)
    segments, info = model.transcribe(
        str(audio),
        language=lang,
        vad_filter=True,
        beam_size=1,
        condition_on_previous_text=False,
    )
    parts: list[str] = []
    for s in segments:
        t = (s.text or "").strip()
        if t:
            parts.append(t)
    return " ".join(parts)


def process_channel(
    channel: str,
    model_name: str,
    device: str,
    compute_type: str,
    limit: int | None,
) -> dict:
    name_ko = CHANNEL_NAME_KO.get(channel, channel)
    queue = load_queue(channel)
    if not queue:
        print(f"\n=== [{channel}] 큐 비어있음 — skip ===")
        return {"processed": 0, "failed": 0, "skipped": 0}

    proc_dir = PROJECT_ROOT / "data" / "processed" / "youtube" / channel
    cap_dir = PROJECT_ROOT / "data" / "raw" / "youtube" / channel / "captions"
    proc_dir.mkdir(parents=True, exist_ok=True)
    cap_dir.mkdir(parents=True, exist_ok=True)
    index = load_index(channel)

    print(f"\n=== [{channel}] {name_ko}  큐 {len(queue)}개 STT 시작 ===")
    stats = {"processed": 0, "failed": 0, "skipped": 0}
    remaining: list[tuple[str, str]] = []

    for i, (vid, title) in enumerate(queue, 1):
        if limit and stats["processed"] >= limit:
            remaining.append((vid, title))
            continue

        proc_file = proc_dir / f"{vid}.txt"
        if proc_file.exists():
            stats["skipped"] += 1
            continue

        meta = index.get(vid, {})
        real_title = title or meta.get("title", "")
        print(f"  [{i:4d}/{len(queue)}] {vid}  {real_title[:60]}")

        with tempfile.TemporaryDirectory(prefix="ytwh_") as tmp:
            tmp_dir = Path(tmp)
            t0 = time.time()
            audio = download_audio(vid, tmp_dir)
            if not audio:
                stats["failed"] += 1
                remaining.append((vid, title))
                continue
            dur_dl = time.time() - t0

            try:
                t1 = time.time()
                text = transcribe_file(audio, model_name, device, compute_type)
                dur_stt = time.time() - t1
            except Exception as e:
                print(f"    [stt 실패] {vid}: {e}", file=sys.stderr)
                stats["failed"] += 1
                remaining.append((vid, title))
                continue

        text = text.strip()
        if not text:
            print(f"    [stt 결과 비어있음] {vid}")
            stats["failed"] += 1
            remaining.append((vid, title))
            continue

        header = (
            f"# {real_title}\n"
            f"# 출처: {name_ko} | https://www.youtube.com/watch?v={vid}\n"
            f"# 자막 언어: ko (Whisper STT)\n\n"
        )
        proc_file.write_text(header + text, encoding="utf-8")
        (cap_dir / f"{vid}.txt").write_text(text, encoding="utf-8")
        stats["processed"] += 1
        print(f"    OK  {len(text):,}자  (dl={dur_dl:.1f}s stt={dur_stt:.1f}s)")

    # queue 갱신 (성공한 것 빠짐)
    save_queue(channel, remaining)
    print(f"[{channel}] 처리 {stats['processed']} / 실패 {stats['failed']} / 스킵 {stats['skipped']} / 남은 큐 {len(remaining)}")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", help="특정 채널만 (cheonsewon/hyunmyung/haengun)")
    ap.add_argument("--model", default="medium", help="faster-whisper 모델 (tiny/base/small/medium/large-v3)")
    ap.add_argument("--device", default="cpu", help="cpu(기본, GPU경합차단) or cuda")
    ap.add_argument("--compute-type", default="int8", help="int8(CPU 기본)/float16/int8_float16 등")
    ap.add_argument("--limit", type=int, default=None, help="채널당 최대 N개")
    args = ap.parse_args()

    channels = [args.channel] if args.channel else CHANNELS
    grand = {"processed": 0, "failed": 0, "skipped": 0}
    for ch in channels:
        try:
            s = process_channel(ch, args.model, args.device, args.compute_type, args.limit)
            for k, v in s.items():
                grand[k] += v
        except KeyboardInterrupt:
            print("\n[중단됨]")
            return 130
        except Exception as e:
            print(f"[ERR] {ch}: {e}", file=sys.stderr)
            grand["failed"] += 1

    print("\n" + "=" * 60)
    print(f"[STT TOTAL] 처리 {grand['processed']} / 실패 {grand['failed']} / 스킵 {grand['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
