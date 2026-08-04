"""사주 영상 렌더 워커(부록 A-2/C-3) — 별도 프로세스 실행 권장.

DB 큐를 FOR UPDATE SKIP LOCKED 로 단일플라이트 클레임 → run_job.
크래시 복구(고아 running 회수) + 주기적 48h 보관 삭제. 실행: python -m backend.app.services.video.worker
편집-reload가 죽이지 않도록 detach 프로세스로 기동([[upload-learning-batch]] 교훈).
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.db import get_session_factory
from backend.app.repositories.models import SajuVideoJob
from backend.app.services.video import service as _svc

_POLL_SEC = 3.0
_STALE_MIN = 30          # running 인데 완료시각 없고 30분 경과 → 고아로 간주
_EXPIRE_EVERY = 100      # 루프 N회마다 보관 삭제
_PIDFILE = Path(__file__).resolve().parents[4] / "data" / "video" / "worker.pid"


def _pid_alive(pid: int) -> bool:
    """PID 생존 확인. Windows 의 os.kill(pid,0)은 프로세스를 '죽이므로'(TerminateProcess) 금지,
    tasklist 로 조회한다. POSIX 는 os.kill(0) 으로 생존 확인."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
                capture_output=True, text=True, timeout=5,
            )
            return f'"{pid}"' in (out.stdout or "")
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _take_ownership() -> None:
    """신규 워커가 pid 소유권을 즉시 인계(takeover)받는다 — 서버 재기동 때 '새 코드' 워커가 확실히 뜨도록.
    전임자를 죽이지 않는다(렌더 중이면 70% 멈춤·커밋 df81516d). 대신 전임자는 _should_retire()로
    현재 작업을 끝낸 뒤 스스로 은퇴하므로, 중단 없이 세대 교체(graceful takeover)가 일어난다."""
    try:
        _PIDFILE.parent.mkdir(parents=True, exist_ok=True)
        _PIDFILE.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass


def _should_retire() -> bool:
    """pid 파일을 '살아있는 다른' 워커가 인계받았으면 True(은퇴). 파일이 나/스테일이면 내가 (재)점유해 유지.
    루프 최상단에서만 호출 → 렌더(run_job) 도중엔 검사하지 않아 작업이 중단되지 않는다."""
    me = os.getpid()
    try:
        cur = int((_PIDFILE.read_text(encoding="utf-8").strip() or "0"))
    except Exception:
        cur = 0
    if cur == me:
        return False
    if cur and _pid_alive(cur):
        return True                       # 신규 워커가 인계받음 → 나는 은퇴(현재 작업까지 마친 상태)
    try:                                  # 파일이 스테일/공백 → 내가 (재)점유하고 계속
        _PIDFILE.write_text(str(me), encoding="utf-8")
    except Exception:
        pass
    return False


def _claim(db: Session) -> SajuVideoJob | None:
    job = db.execute(
        select(SajuVideoJob).where(SajuVideoJob.status == "queued")
        .order_by(SajuVideoJob.id).with_for_update(skip_locked=True).limit(1)
    ).scalar_one_or_none()
    if job is None:
        return None
    job.status = "running"
    db.commit()
    db.refresh(job)
    return job


def _recover(db: Session) -> int:
    """① 멈춘 running(>_STALE_MIN) → failed + 환불.  ② 환불 누락 failed(프로세스 중단) → 환불.
    refund_job은 status='failed' + refunded=false 멱등이라 다중 호출·다중 워커에도 안전."""
    cutoff = datetime.utcnow() - timedelta(minutes=_STALE_MIN)
    stale = db.query(SajuVideoJob).filter(
        SajuVideoJob.status == "running", SajuVideoJob.created_at < cutoff
    ).all()
    from sqlalchemy import update as _update
    for job in stale:
        # 조건부 전이 — 동시 finalize 로 이미 done 이 된 잡을 blind 하게 failed 로 덮어써
        #   완료·납품된 영상을 오환불(수익 누수)하던 문제 차단. running 인 잡만 회수하고 그 경우에만 환불.
        res = db.execute(
            _update(SajuVideoJob)
            .where(SajuVideoJob.id == job.id, SajuVideoJob.status == "running", SajuVideoJob.created_at < cutoff)
            .values(status="failed", detail="지연 작업 회수")
        )
        db.commit()
        if res.rowcount == 1:
            _svc.refund_job(db, job)
    # 환불 누락 고아(실패 확정 후 환불 전 프로세스 사망) 보정
    orphans = db.query(SajuVideoJob).filter(
        SajuVideoJob.status == "failed", SajuVideoJob.refunded.is_(False),
        SajuVideoJob.credits_charged > 0,
    ).all()
    for job in orphans:
        _svc.refund_job(db, job)
    return len(stale) + len(orphans)


def run_forever() -> None:
    _take_ownership()   # 신규 워커가 즉시 pid 인계 → 재기동 시 새 코드 워커가 뜬다(전임자는 아래서 자진 은퇴)
    factory = get_session_factory()
    with factory() as db:
        n = _recover(db)
        if n:
            sys.stderr.write(f"[video-worker] recovered {n} jobs\n")
    i = 0
    sys.stderr.write(f"[video-worker] started pid={os.getpid()}\n")
    sys.stderr.flush()
    while True:
        # 세대 교체: 신규 워커가 인계했으면 현재 인스턴스는 은퇴(렌더 중이 아닌 루프 상단에서만 검사)
        if _should_retire():
            sys.stderr.write(f"[video-worker] 신규 워커 인계 감지 — pid={os.getpid()} 은퇴(graceful)\n")
            sys.stderr.flush()
            return
        i += 1
        try:
            with factory() as db:
                # 유지보수(보관 삭제·고아 회수)는 큐 혼잡과 무관하게 주기 실행
                if i % _EXPIRE_EVERY == 0:
                    _svc.expire_due(db)
                    _recover(db)
                job = _claim(db)
                if job is not None:
                    sys.stderr.write(f"[video-worker] run job={job.job_token}\n")
                    sys.stderr.flush()
                    _svc.run_job(db, job)
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"[video-worker] loop error: {e}\n")
            sys.stderr.flush()
        time.sleep(_POLL_SEC)


if __name__ == "__main__":
    run_forever()
