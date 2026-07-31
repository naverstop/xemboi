"""YouTube 전체 자막+STT+검증 오케스트레이터 (무인 운영용).

흐름:
  PHASE 1) 자막 우선 수집
    - youtube_fetch 1패스 실행
    - 신규 자막 0건이고 큐도 비어있으면 PHASE 2로 진행
    - 신규 자막이 있었으면 continue (또 받을 게 남았을 수 있음)
    - 429/네트워크 차단 등으로 멈췄으면 cooldown 후 재시도
    - 최대 시도 횟수 (--max-caption-passes) 도달 시 PHASE 2로 강제 진행

  PHASE 2) Whisper STT
    - transcribe_queue.txt 남은 영상 전량 STT
    - 실패한 영상은 큐에 남음 → 다음 실행 때 재시도

  PHASE 3) 검증 및 리포트
    - 채널별: 영상수 / 자막수집 / STT처리 / 미처리
    - data/processed/youtube/*.txt 총 글자수
    - 미처리 vid 리스트 출력

사용:
  python -m scripts.youtube_full_pipeline                          # 기본 (1시간 쿨다운, 무한 재시도)
  python -m scripts.youtube_full_pipeline --cooldown-min 60 --max-caption-passes 48
  python -m scripts.youtube_full_pipeline --skip-stt                # STT 안 함
  python -m scripts.youtube_full_pipeline --skip-captions           # 자막 패스 스킵, STT만
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ml.data_pipeline import youtube_fetch as yf  # noqa: E402
# whisper_transcribe(faster-whisper)는 STT 단계에서만 필요 → 지연 import.
# 자막(텍스트)만 수집할 때는 faster-whisper 미설치여도 동작하도록 함.

LOCK_PATH = PROJECT_ROOT / "data" / "raw" / "youtube" / ".pipeline.lock"


def acquire_lock() -> None:
    """단일 인스턴스 가드. 동일 IP에서 병렬 실행 시 YouTube 429 증폭 방지."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOCK_PATH.exists():
        try:
            data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
            pid = int(data.get("pid", 0))
        except Exception:
            pid = 0
        if pid > 0 and _pid_alive(pid):
            print(f"[LOCK] 이미 PID {pid} 에서 실행 중 → 중복 실행 거부", file=sys.stderr)
            raise SystemExit(2)
        # stale lock
        try:
            LOCK_PATH.unlink()
        except OSError:
            pass
    LOCK_PATH.write_text(
        json.dumps({"pid": os.getpid(), "started_at": ts()}, ensure_ascii=False),
        encoding="utf-8",
    )
    atexit.register(_release_lock)


def _release_lock() -> None:
    try:
        if LOCK_PATH.exists():
            data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
            if int(data.get("pid", 0)) == os.getpid():
                LOCK_PATH.unlink()
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    try:
        if sys.platform == "win32":
            import ctypes
            PROCESS_QUERY = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY, False, pid)
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def count_status() -> dict:
    """채널별 현황 집계."""
    out = {}
    for ch in yf.CHANNELS:
        label = ch["label"]
        raw_dir = PROJECT_ROOT / "data" / "raw" / "youtube" / label
        proc_dir = PROJECT_ROOT / "data" / "processed" / "youtube" / label
        index_path = raw_dir / "index.jsonl"
        queue_path = raw_dir / "transcribe_queue.txt"

        total = 0
        if index_path.exists():
            total = sum(1 for line in index_path.read_text(encoding="utf-8").splitlines() if line.strip())

        captioned = 0
        char_sum = 0
        if proc_dir.exists():
            for p in proc_dir.glob("*.txt"):
                captioned += 1
                try:
                    char_sum += len(p.read_text(encoding="utf-8"))
                except Exception:
                    pass

        queue_remaining = 0
        if queue_path.exists():
            queue_remaining = sum(1 for line in queue_path.read_text(encoding="utf-8").splitlines() if line.strip())

        out[label] = {
            "name_ko": ch["name_ko"],
            "total": total,
            "captioned_files": captioned,
            "chars": char_sum,
            "queue_remaining": queue_remaining,
        }
    return out


def print_status(title: str) -> dict:
    s = count_status()
    print(f"\n----- 현황 ({title}) {ts()} -----")
    print(f"{'채널':<14}{'영상':>6}{'수집':>6}{'STT대기':>10}{'문자수':>12}")
    for k, v in s.items():
        print(f"{k:<14}{v['total']:>6}{v['captioned_files']:>6}{v['queue_remaining']:>10}{v['chars']:>12,}")
    tot = {
        "total": sum(v["total"] for v in s.values()),
        "captioned": sum(v["captioned_files"] for v in s.values()),
        "queue": sum(v["queue_remaining"] for v in s.values()),
        "chars": sum(v["chars"] for v in s.values()),
    }
    print(f"{'TOTAL':<14}{tot['total']:>6}{tot['captioned']:>6}{tot['queue']:>10}{tot['chars']:>12,}")
    return tot


def caption_pass(force: bool = False, batch_size: int = 10, batch_sleep_sec: int = 600) -> dict:
    """youtube_fetch 1패스. 반환: 합산 stats + rate_limited 플래그.

    batch_size/batch_sleep_sec: 신규 N개 수집마다 휴식(차단 방지). 기본 10개/10분.
    """
    grand = {"total": 0, "captioned": 0, "queued": 0, "skipped": 0, "failed": 0, "rate_limited": False}
    for ch in yf.CHANNELS:
        try:
            s = yf.collect_channel(
                ch, limit=None, list_only=False, force=force,
                batch_size=batch_size, batch_sleep_sec=batch_sleep_sec,
            )
            for k in ("total", "captioned", "queued", "skipped", "failed"):
                grand[k] += s.get(k, 0)
            if s.get("rate_limited"):
                grand["rate_limited"] = True
        except Exception as e:
            print(f"[ERR] {ch['label']}: {e}", file=sys.stderr)
            grand["failed"] += 1
    return grand


def _last_success_ts() -> float | None:
    """data/processed/youtube/**/*.txt 중 가장 최근 mtime. 없으면 None."""
    base = PROJECT_ROOT / "data" / "processed" / "youtube"
    if not base.exists():
        return None
    latest = None
    for p in base.rglob("*.txt"):
        try:
            m = p.stat().st_mtime
            if latest is None or m > latest:
                latest = m
        except OSError:
            pass
    return latest


def phase_captions(cooldown_sec: int, max_passes: int, batch_size: int = 10, batch_sleep_sec: int = 600) -> None:
    print(f"\n========== PHASE 1: 자막 수집 (최대 {max_passes}패스, 배치 {batch_size}개/{batch_sleep_sec//60}분) ==========")
    print(f"[policy] 마지막 성공 시각 + {cooldown_sec//3600}h 후 재시도")
    yf.set_impersonate("chrome")
    print("[impersonate] chrome")

    # 차단 감지 시 exponential backoff (연속 차단일수록 12h → 24h → 48h → 96h, 최대 96h)
    block_streak = 0
    base_block_h = max(12, cooldown_sec // 3600)

    for pass_no in range(1, max_passes + 1):
        last_ok = _last_success_ts()
        if last_ok is not None:
            next_attempt = last_ok + cooldown_sec
            now = time.time()
            wait = next_attempt - now
            if wait > 0:
                from datetime import datetime as _dt
                print(
                    f"[wait] 마지막 성공 {_dt.fromtimestamp(last_ok).strftime('%Y-%m-%d %H:%M')} "
                    f"+ {cooldown_sec//3600}h → {_dt.fromtimestamp(next_attempt).strftime('%Y-%m-%d %H:%M')} "
                    f"({wait/3600:.2f}h 대기)"
                )
                time.sleep(wait)

        print(f"\n***** PASS {pass_no}/{max_passes}  ({ts()}) *****")
        t0 = time.time()
        s = caption_pass(force=False, batch_size=batch_size, batch_sleep_sec=batch_sleep_sec)
        elapsed = time.time() - t0
        print(
            f"\n[PASS {pass_no}] captioned={s['captioned']} queued={s['queued']} "
            f"skipped={s['skipped']} failed={s['failed']} rate_limited={s['rate_limited']}  "
            f"({elapsed/60:.1f}분)"
        )
        status = count_status()
        unresolved = sum(
            max(0, v["total"] - v["captioned_files"]) for v in status.values()
        )
        print(f"[누적] 미해결(자막없음+큐) {unresolved}개")

        if unresolved == 0:
            print("[PHASE 1 완료] 전체 영상 자막 확보")
            return

        if s["captioned"] == 0 and not s["rate_limited"]:
            print("[PHASE 1 종료] 신규 자막 0 + 차단 아님 → 남은 건 자막 미존재 영상 (STT 대상)")
            return

        # 성공한 경우: _last_success_ts 가 갱신됨 → 다음 루프에서 +cooldown 자동 대기
        # 차단된 경우: exponential backoff 적용
        if s["captioned"] > 0:
            block_streak = 0
        else:
            block_streak += 1
            backoff_h = min(96, base_block_h * (2 ** (block_streak - 1)))
            print(f"[block#{block_streak}] 신규 0건 → {backoff_h}h 대기 (exponential backoff)")
            time.sleep(backoff_h * 3600)

    print(f"[PHASE 1 종료] 최대 패스({max_passes}) 도달")

    print(f"[PHASE 1 종료] 최대 패스({max_passes}) 도달")


def phase_stt(model: str, device: str, compute_type: str) -> None:
    print(f"\n========== PHASE 2: Whisper STT (model={model}, device={device}) ==========")
    status = count_status()
    total_queue = sum(v["queue_remaining"] for v in status.values())
    if total_queue == 0:
        print("[PHASE 2 skip] STT 대기 큐 비어있음")
        return
    try:
        from ml.data_pipeline import whisper_transcribe as wt
    except Exception as e:  # faster-whisper 미설치 등
        print(f"[PHASE 2 skip] whisper_transcribe 로드 실패({e}) → STT 건너뜀. "
              f"자막 없는 영상 {total_queue}개는 faster-whisper 설치 후 처리하세요.", file=sys.stderr)
        return
    print(f"[PHASE 2] 총 STT 대상 {total_queue}개")
    grand = {"processed": 0, "failed": 0, "skipped": 0}
    for ch in yf.CHANNELS:
        try:
            s = wt.process_channel(ch["label"], model, device, compute_type, limit=None)
            for k in grand:
                grand[k] += s.get(k, 0)
        except Exception as e:
            print(f"[ERR] STT {ch['label']}: {e}", file=sys.stderr)
            grand["failed"] += 1
    print(
        f"\n[PHASE 2 종료] STT 처리 {grand['processed']} / 실패 {grand['failed']} / 스킵 {grand['skipped']}"
    )


def phase_validate() -> int:
    print("\n========== PHASE 3: 검증 ==========")
    tot = print_status("최종")
    status = count_status()

    incomplete = []
    for label, v in status.items():
        missing = v["total"] - v["captioned_files"]
        if missing > 0:
            incomplete.append((label, missing, v["queue_remaining"]))

    print("\n----- 채널별 결과 -----")
    for label, v in status.items():
        ratio = (v["captioned_files"] / v["total"] * 100) if v["total"] else 0
        print(f"  {label:<12} {v['captioned_files']:>4}/{v['total']:<4} ({ratio:5.1f}%)  남은큐 {v['queue_remaining']}")

    if incomplete:
        print("\n[UNRESOLVED] 다음 채널에 미해결 영상 있음:")
        for label, missing, queue in incomplete:
            print(f"  - {label}: 미수집 {missing}개 (큐 {queue}개)")
        return 1
    print("\n[OK] 전체 영상 텍스트 확보 완료")
    return 0


def phase_reindex() -> None:
    """수집/STT로 갱신된 코퍼스를 Qdrant에 재색인(ingest_rag --recreate). 별도 프로세스.

    --recreate 는 saju_corpus 컬렉션을 delete 후 재생성하므로, 이 구간에 RAG 평가가
    검색을 돌리면 빈/반쪽 컬렉션을 읽어 추세가 오염된다. 재색인 동안 reindex.lock 을
    남겨 스케줄러의 03:30 평가가 이 구간을 피하도록(가드) 한다.
    """
    print("\n========== PHASE 4: 자동 재색인 (ingest_rag --recreate) ==========")
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", str(PROJECT_ROOT))
    env.setdefault("HF_HOME", str(PROJECT_ROOT / "infra" / "hf_cache"))
    env["CUDA_VISIBLE_DEVICES"] = "-1"  # CPU 강제 — 영상생성(GPU0) 경합 차단(YouTube 한시적)
    cmd = [sys.executable, "-u", "-m", "ml.data_pipeline.ingest_rag", "--recreate"]
    print(f"[reindex] {' '.join(cmd)}")
    reindex_lock = PROJECT_ROOT / "data" / "logs" / "reindex.lock"
    reindex_lock.parent.mkdir(parents=True, exist_ok=True)
    reindex_lock.write_text(str(os.getpid()), encoding="utf-8")
    try:
        rc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env).returncode
    finally:
        try:
            reindex_lock.unlink()
        except FileNotFoundError:
            pass
    print(f"[reindex] 종료 rc={rc}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cooldown-min", type=int, default=60, help="자막 패스 사이 쿨다운(분, 기본 60)")
    ap.add_argument("--max-caption-passes", type=int, default=48, help="자막 최대 패스 수 (기본 48 = 약 2일)")
    ap.add_argument("--skip-captions", action="store_true")
    ap.add_argument("--skip-stt", action="store_true")
    ap.add_argument("--skip-list-refresh", action="store_true", help="시작 시 채널 영상 목록 갱신 안 함")
    ap.add_argument("--batch-size", type=int, default=10, help="신규 N개 수집마다 휴식(차단방지, 기본 10)")
    ap.add_argument("--batch-sleep-min", type=int, default=10, help="배치 사이 휴식(분, 기본 10)")
    ap.add_argument("--proxy", default=None, help="IP 우회 프록시 (예: socks5://127.0.0.1:1080)")
    ap.add_argument("--whisper-model", default="medium")
    # 기본 CPU — YouTube STT 도 GPU 경합 차단(한시적 수집). GPU 강제 시 --whisper-device cuda
    ap.add_argument("--whisper-device", default="cpu")
    ap.add_argument("--whisper-compute-type", default="int8")
    ap.add_argument("--auto-reindex", action="store_true", help="수집/STT 후 Qdrant 자동 재색인")
    args = ap.parse_args()
    if args.proxy:
        yf.set_proxy(args.proxy)
        print(f"[proxy] {args.proxy}")

    acquire_lock()
    print(f"========== YouTube 전체 파이프라인 시작 {ts()} ==========")
    print(f"[lock] {LOCK_PATH} (PID={os.getpid()})")

    # 0) 영상 목록 최신화 (한 번)
    if not args.skip_list_refresh:
        print("\n[0] 채널 영상 목록 갱신")
        yf.set_impersonate("chrome")
        for ch in yf.CHANNELS:
            try:
                yf.collect_channel(ch, limit=None, list_only=True, force=False)
            except Exception as e:
                print(f"[ERR list] {ch['label']}: {e}", file=sys.stderr)

    print_status("시작")

    if not args.skip_captions:
        phase_captions(
            args.cooldown_min * 60, args.max_caption_passes,
            batch_size=args.batch_size, batch_sleep_sec=args.batch_sleep_min * 60,
        )
        print_status("자막 단계 완료")

    if not args.skip_stt:
        phase_stt(args.whisper_model, args.whisper_device, args.whisper_compute_type)

    if args.auto_reindex:
        phase_reindex()

    return phase_validate()


if __name__ == "__main__":
    raise SystemExit(main())
