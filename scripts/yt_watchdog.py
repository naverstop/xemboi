"""YouTube 차단 회복 감시자 → 회복되면 자동으로 youtube_full_pipeline 실행.

- 일정 간격(--interval-min)으로 probe (단일 자막 호출)
- 200 OK 떨어지면 youtube_full_pipeline 을 subprocess 로 1회 실행
- 파이프라인 종료(혹은 lock 충돌) 후 다시 polling
- Ctrl+C 까지 무한 루프

사용:
  python scripts\yt_watchdog.py                    # 30분 간격
  python scripts\yt_watchdog.py --interval-min 15
  python scripts\yt_watchdog.py --max-runs 1       # 1회 회복 후 종료
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def probe_caption(video_id: str = "KJmV_cWCgLs", timeout: int = 30) -> tuple[bool, str]:
    """단일 자막 호출. (recovered, msg)."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    with tempfile.TemporaryDirectory() as tmp:
        opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["ko", "ko-KR", "en"],
            "subtitlesformat": "vtt/json3/best",
            "outtmpl": os.path.join(tmp, "%(id)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "socket_timeout": timeout,
            # probe 는 yt-dlp 기본 player_client (web+ios+android) 그대로 사용.
            # tv 단일은 일부 영상에서 DRM 표시됨 → 팔시 양성 가능성 있음.
        }
        try:
            with YoutubeDL(opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
            files = list(Path(tmp).iterdir())
            return True, f"OK files={len(files)}"
        except DownloadError as e:
            msg = str(e)
            if "429" in msg or "too many requests" in msg.lower():
                return False, "429 RATE-LIMITED"
            return False, f"ERR {msg[:200]}"
        except Exception as e:
            return False, f"EXC {type(e).__name__}: {e}"


def ping_youtube() -> bool:
    try:
        req = urllib.request.Request(
            "https://www.youtube.com/robots.txt",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except Exception:
        return False


def run_pipeline(batch_size: int = 10, batch_sleep_min: int = 10, proxy: str | None = None) -> int:
    """youtube_full_pipeline 한 번 실행. exit code 반환."""
    log_path = LOG_DIR / f"yt_pipeline_{datetime.now():%Y%m%d_%H%M%S}.log"
    err_path = log_path.with_suffix(".log.err")
    cmd = [
        sys.executable,
        "-u",
        "-m",
        "scripts.youtube_full_pipeline",
        "--cooldown-min", "720",
        "--max-caption-passes", "24",
        # (목록 갱신 ON: 새로 올라온 영상까지 발견 — 정기 수집용)
        # 차단 방지: 신규 N개 수집마다 휴식 (기본 10개/10분)
        "--batch-size", str(batch_size),
        "--batch-sleep-min", str(batch_sleep_min),
        "--whisper-model", "large-v3",
        "--whisper-device", "cpu",          # GPU0(영상생성) 경합 차단 — CPU STT
        "--whisper-compute-type", "int8",
        # 수집/STT 후 자동 재색인 (point 4)
        "--auto-reindex",
    ]
    if proxy:
        cmd += ["--proxy", proxy]
    print(f"[{ts()}] [run] {' '.join(cmd)}")
    print(f"[{ts()}] [log] {log_path}")
    with log_path.open("w", encoding="utf-8") as fout, err_path.open("w", encoding="utf-8") as ferr:
        proc = subprocess.Popen(cmd, stdout=fout, stderr=ferr, cwd=str(PROJECT_ROOT))
        rc = proc.wait()
    print(f"[{ts()}] [end] rc={rc}")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval-min", type=int, default=30, help="probe 간격(분)")
    ap.add_argument("--video", default="KJmV_cWCgLs", help="probe 대상 video_id")
    ap.add_argument("--max-runs", type=int, default=0, help="파이프라인 실행 최대 횟수 (0=무한)")
    ap.add_argument("--immediate", action="store_true", help="시작 시 probe 없이 바로 1회 실행")
    ap.add_argument("--batch-size", type=int, default=10, help="신규 N개 수집마다 휴식(차단방지, 기본 10)")
    ap.add_argument("--batch-sleep-min", type=int, default=10, help="배치 사이 휴식(분, 기본 10)")
    ap.add_argument("--proxy", default=None, help="IP 우회 프록시 (예: socks5://127.0.0.1:1080)")
    ap.add_argument("--initial-wait-days", type=float, default=0.0, help="시작 전 초기 대기(일). 차단 IP 회복 대기용")
    ap.add_argument("--initial-wait-hours", type=float, default=0.0, help="시작 전 초기 대기(시간). days와 합산")
    ap.add_argument("--escalate-weeks", default="1,2,4",
                    help="차단 지속 시 재시도 간격(주, escalating). 마지막 값 반복. 기본 1,2,4")
    ap.add_argument("--monthly-days", type=float, default=30.0,
                    help="수집 완료 후 정기 재수집 간격(일). 신규 영상 반영. 기본 30")
    args = ap.parse_args()

    # 단일 인스턴스 가드 (예약작업이 로그온마다 떠도 중복 방지)
    lock = LOG_DIR.parent / "raw" / "youtube" / ".watchdog.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        try:
            old_pid = int(lock.read_text().strip() or "0")
        except Exception:
            old_pid = 0
        alive = False
        if old_pid > 0:
            try:
                import ctypes
                h = ctypes.windll.kernel32.OpenProcess(0x1000, False, old_pid)
                if h:
                    ctypes.windll.kernel32.CloseHandle(h)
                    alive = True
            except Exception:
                alive = False
        if alive:
            print(f"[{ts()}] [lock] 이미 와치독 실행 중(PID {old_pid}) → 중복 기동 종료")
            return 0
    lock.write_text(str(os.getpid()), encoding="utf-8")
    import atexit
    atexit.register(lambda: lock.exists() and lock.unlink())

    # 초기 대기: 차단된 IP가 자연 회복되도록 일정 기간 probe/수집을 미룸 (예: 1주일)
    init_wait = args.initial_wait_days * 86400 + args.initial_wait_hours * 3600
    if init_wait > 0:
        from datetime import datetime as _dt, timedelta as _td
        resume_at = _dt.now() + _td(seconds=init_wait)
        print(f"[{ts()}] [초기대기] {args.initial_wait_days}일 {args.initial_wait_hours}시간 후 시작 "
              f"→ {resume_at:%Y-%m-%d %H:%M} 부터 probe 시작 (차단 IP 회복 대기)")
        time.sleep(init_wait)
        print(f"[{ts()}] [초기대기 종료] 와치독 probe 시작")

    # escalating 재시도 간격(주) 파싱
    try:
        escalate_weeks = [float(x) for x in str(args.escalate_weeks).split(",") if x.strip()]
    except ValueError:
        escalate_weeks = [1.0, 2.0, 4.0]
    if not escalate_weeks:
        escalate_weeks = [1.0, 2.0, 4.0]

    def probe_ok() -> bool:
        if not ping_youtube():
            print(f"[{ts()}] [probe] robots.txt 실패(네트워크 점검 필요)")
            return False
        ok, msg = probe_caption(args.video)
        print(f"[{ts()}] [probe] caption {'OK' if ok else 'BLOCK'} : {msg}")
        return ok

    def wait_until_recovered() -> None:
        """차단 회복까지 escalating 백오프(예: 1→2→4주, 마지막값 반복)로 대기."""
        attempt = 0
        while not probe_ok():
            wk = escalate_weeks[min(attempt, len(escalate_weeks) - 1)]
            secs = int(wk * 7 * 86400)
            resume = datetime.now() + timedelta(seconds=secs)
            print(f"[{ts()}] [차단지속#{attempt+1}] {wk}주 후 재시도 → {resume:%Y-%m-%d %H:%M}")
            time.sleep(secs)
            attempt += 1

    print(f"[{ts()}] [watchdog 시작] escalating={escalate_weeks}주, 정기수집={args.monthly_days}일")

    def _run() -> None:
        run_pipeline(args.batch_size, args.batch_sleep_min, args.proxy)

    # 1) 차단 회복 대기(escalating) → 첫 수집 + 자동 재색인
    if args.immediate:
        _run()
    else:
        print(f"[{ts()}] [phase1] 차단 회복 대기 시작")
        wait_until_recovered()
        print(f"[{ts()}] [recover] 회복 감지 → 첫 수집/재색인 실행")
        _run()

    # 2) 월 1회 정기 수집(신규 영상 반영) — 영상이 계속 올라오므로 지속 (point 1·3)
    monthly_secs = int(args.monthly_days * 86400)
    while True:
        nxt = datetime.now() + timedelta(seconds=monthly_secs)
        print(f"[{ts()}] [monthly] 다음 정기 수집 → {nxt:%Y-%m-%d %H:%M} ({args.monthly_days}일 후)")
        time.sleep(monthly_secs)
        wait_until_recovered()  # 정기 수집 직전 차단이면 회복까지 escalating 대기
        print(f"[{ts()}] [monthly] 정기 수집/재색인 실행")
        _run()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[watchdog] 사용자 종료")
        sys.exit(0)
