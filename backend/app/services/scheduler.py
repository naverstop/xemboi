"""경량 백그라운드 스케줄러 (계획 7-D.2 오늘의 운세 데일리 푸시).

의존성 없이 daemon 스레드로 매분 시각을 확인해 지정 시각에 1회 발송한다.
설정(daily_fortune_enabled) 미충족 시 아무 것도 하지 않는다.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

from backend.app.core.config import get_settings
from backend.app.core.db import get_session_factory
from backend.app.services import push_service

log = logging.getLogger("saju.scheduler")

# 학습/인사이트 배치는 uvicorn 의 '자식'으로 떠서, --reload(DEV_RELOAD=1) 재시작 시 부모가 보내는
# CTRL 시그널을 같이 받아 KeyboardInterrupt 로 중도 사망하는 문제가 있었다(메모리: 백엔드 reload가 배치
# 죽임). 콘솔 없는 독립 프로세스로 띄워 시그널을 안 받게 한다:
#   CREATE_NO_WINDOW(0x08000000): 창/콘솔 없이 백그라운드 → 부모 콘솔의 CTRL_BREAK 미수신.
#   CREATE_NEW_PROCESS_GROUP(0x200): 부모 CTRL_C 그룹과 분리. (비-Windows는 0=무시.)
_DETACH_FLAGS = (0x08000000 | 0x00000200) if os.name == "nt" else 0

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_NIGHTLY_LOCK = _PROJECT_ROOT / "data" / "logs" / "nightly_learning.lock"
# 유튜브 파이프라인의 코퍼스 재색인(--recreate, 컬렉션 delete→재생성) 진행 표시.
_REINDEX_LOCK = _PROJECT_ROOT / "data" / "logs" / "reindex.lock"
# RAG 평가(수동/스케줄) 진행 표시 — 교차 가드.
_RAG_EVAL_LOCK = _PROJECT_ROOT / "data" / "eval" / "rag_eval.lock"

_started = False
_last_fortune_date: date | None = None
_last_nightly_date: date | None = None
_last_insight_date: date | None = None
_last_rag_eval_date: date | None = None
_last_tarot_purge_date: date | None = None
_last_consultation_purge_date: date | None = None


def _pid_alive(pid: int) -> bool:
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        return False
    except Exception:  # noqa: BLE001
        return False


def _lock_pid_alive(lock_path: Path) -> bool:
    """PID 락 파일이 가리키는 프로세스가 살아있는지."""
    if not lock_path.exists():
        return False
    try:
        pid = int(lock_path.read_text(encoding="utf-8").strip() or "0")
    except Exception:  # noqa: BLE001
        return False
    return bool(pid and _pid_alive(pid))


def is_nightly_running() -> bool:
    """야간 학습 배치가 현재 실행 중인지(단일 인스턴스 락의 PID 생존 여부)."""
    return _lock_pid_alive(_NIGHTLY_LOCK)


def is_reindex_running() -> bool:
    """유튜브 파이프라인의 코퍼스 재색인(--recreate)이 진행 중인지."""
    return _lock_pid_alive(_REINDEX_LOCK)


def is_eval_running() -> bool:
    """RAG 평가(수동 또는 스케줄)가 진행 중인지."""
    return _lock_pid_alive(_RAG_EVAL_LOCK)


def run_nightly_learning_now() -> dict:
    """관리자 수동 트리거 — 야간 배치와 동일 로직을 즉시 1회 실행(CPU 백그라운드).

    이미 실행 중이면 중복 기동하지 않는다(배치 자체 단일 인스턴스 락과 이중 안전).
    """
    if is_nightly_running():
        return {"started": False, "running": True}
    _run_nightly_learning_batch()
    return {"started": True, "running": True}


def _run_nightly_learning_batch() -> None:
    """통합 야간 학습 배치(OCR→증분색인→STT→아카이브)를 별도 프로세스로 1회 실행.

    전 과정 CPU 전용(CUDA_VISIBLE_DEVICES="-1") — 사주 GPU 자원(GPU1: LLM·영상·임베딩)과의
    경합을 원천 차단. 무거운 모델 로딩을 웹서버와 분리하려 subprocess 로 띄운다.
    대상(학습자료_new PDF / 승인 업로드)이 없으면 배치가 스스로 각 단계를 생략한다.
    """
    log_dir = _PROJECT_ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"nightly_learning_{datetime.now():%Y%m%d_%H%M%S}.log"
    cmd = [sys.executable, "-u", "-m", "scripts.nightly_learning"]
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", str(_PROJECT_ROOT))
    env["CUDA_VISIBLE_DEVICES"] = "-1"  # CPU 강제("" 는 torch 에서 무효)
    log.info("nightly learning batch start: %s (log=%s)", " ".join(cmd), log_path)
    try:
        with log_path.open("w", encoding="utf-8") as fout:
            subprocess.Popen(cmd, stdout=fout, stderr=subprocess.STDOUT,
                             cwd=str(_PROJECT_ROOT), env=env, creationflags=_DETACH_FLAGS)
    except OSError as e:
        # python exe 부재·권한 등으로 spawn 실패해도 스케줄러 루프는 죽지 않도록 로깅만.
        log.error("batch process spawn failed: %s (%s)", e, " ".join(cmd))


def _run_daily_insight_batch() -> None:
    """일일 질문 인사이트 배치를 별도 프로세스로 1회 실행.

    CUDA_VISIBLE_DEVICES="-1" 로 CPU 전용 강제 — GPU 서비스/학습 로드에 영향 없음.
    """
    log_dir = _PROJECT_ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"question_insight_{datetime.now():%Y%m%d_%H%M%S}.log"
    cmd = [sys.executable, "-u", "-m", "scripts.daily_question_insight"]
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", str(_PROJECT_ROOT))
    env["CUDA_VISIBLE_DEVICES"] = "-1"  # CPU 강제("" 는 torch 에서 무효)
    log.info("daily question insight batch start: %s (log=%s)", " ".join(cmd), log_path)
    try:
        with log_path.open("w", encoding="utf-8") as fout:
            subprocess.Popen(cmd, stdout=fout, stderr=subprocess.STDOUT,
                             cwd=str(_PROJECT_ROOT), env=env, creationflags=_DETACH_FLAGS)
    except OSError as e:
        # python exe 부재·권한 등으로 spawn 실패해도 스케줄러 루프는 죽지 않도록 로깅만.
        log.error("batch process spawn failed: %s (%s)", e, " ".join(cmd))


def _run_feedback_learning_batch() -> None:
    """피드백 학습 폐루프(👍 검증지식 색인 / 👎 개선큐 적재)를 별도 프로세스로 1회 실행.

    Claude API(외부)로 일반화 + CPU 임베딩 색인 — GPU 경합 없음. 일일 인사이트 직후 실행해
    그날 모인 피드백을 학습/개선에 반영한다(폐루프).
    """
    log_dir = _PROJECT_ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"feedback_learning_{datetime.now():%Y%m%d_%H%M%S}.log"
    cmd = [sys.executable, "-u", "-m", "scripts.feedback_learning"]
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", str(_PROJECT_ROOT))
    env["CUDA_VISIBLE_DEVICES"] = "-1"  # CPU 강제(임베딩) — GPU 경합 차단. Claude는 외부 API.
    log.info("feedback learning batch start: %s (log=%s)", " ".join(cmd), log_path)
    try:
        with log_path.open("w", encoding="utf-8") as fout:
            subprocess.Popen(cmd, stdout=fout, stderr=subprocess.STDOUT,
                             cwd=str(_PROJECT_ROOT), env=env, creationflags=_DETACH_FLAGS)
    except OSError as e:
        # python exe 부재·권한 등으로 spawn 실패해도 스케줄러 루프는 죽지 않도록 로깅만.
        log.error("batch process spawn failed: %s (%s)", e, " ".join(cmd))


def run_feedback_learning_now() -> dict:
    """관리자 수동 — 피드백 학습 폐루프 즉시 1회 실행."""
    _run_feedback_learning_batch()
    return {"started": True}


def _run_rag_eval_batch() -> None:
    """RAG 검색 품질 평가를 별도 프로세스로 1회 실행 → data/eval/runs.jsonl 에 append.

    야간 학습이 코퍼스를 다시 쌓은 뒤 시각(03:30)에 돌려, 그날 추가된 자료의 검색
    품질 효과를 추세로 누적한다. CUDA_VISIBLE_DEVICES="-1" 로 CPU 전용 강제(GPU 경합
    차단). Ollama 등 LLM 호출 없음 — BGE-m3 임베더 + Qdrant 검색만 수행.
    Qdrant 미가동 등 실패는 이 프로세스 로그에만 남고 웹서버/스케줄러엔 영향 없다.
    """
    s = get_settings()
    log_dir = _PROJECT_ROOT / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"rag_eval_{datetime.now():%Y%m%d_%H%M%S}.log"
    tag = f"nightly_{datetime.now():%Y%m%d}"
    cmd = [
        sys.executable, "-u", "-m", "ml.eval.eval_retrieval",
        "--tag", tag,
        "--qdrant-url", s.qdrant_url,
        "--collection", s.qdrant_collection,
    ]
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", str(_PROJECT_ROOT))
    env["CUDA_VISIBLE_DEVICES"] = "-1"  # CPU 강제("" 는 torch 에서 무효)
    log.info("rag eval batch start: %s (log=%s)", " ".join(cmd), log_path)
    try:
        with log_path.open("w", encoding="utf-8") as fout:
            subprocess.Popen(cmd, stdout=fout, stderr=subprocess.STDOUT,
                             cwd=str(_PROJECT_ROOT), env=env, creationflags=_DETACH_FLAGS)
    except OSError as e:
        # python exe 부재·권한 등으로 spawn 실패해도 스케줄러 루프는 죽지 않도록 로깅만.
        log.error("batch process spawn failed: %s (%s)", e, " ".join(cmd))


def _run_tarot_purge_expired() -> None:
    """만료(1주 초과) 타로 세션 정리 — factory 세션으로 1회 실행. 실패는 로깅만(루프 유지)."""
    factory = get_session_factory()
    db = factory()
    try:
        from backend.app.repositories import tarot_repo
        n = tarot_repo.purge_expired(db)
        if n:
            log.info("tarot expired sessions purged: %d", n)
    except Exception:  # noqa: BLE001
        log.exception("tarot purge_expired failed")
    finally:
        db.close()


def _run_consultation_purge() -> None:
    """보관기간(7일) 지난 1:1 상담 대화·요약 PDF 완전 파기(개인정보 준수). 실패는 로깅만(루프 유지).

    입장 전 동의 게이트에서 고지한 '대화는 7일 후 자동·완전 파기'를 실제로 이행. 순수 DB+파일(LLM/GPU 없음).
    """
    factory = get_session_factory()
    db = factory()
    try:
        from backend.app.services import consultation_session_service as csess
        r = csess.purge_expired(db)
        if r["sessions"]:
            log.info(
                "consultation purged: sessions=%d messages=%d pdfs=%d",
                r["sessions"], r["messages"], r["pdfs"],
            )
    except Exception:  # noqa: BLE001
        log.exception("consultation purge failed")
    finally:
        db.close()


def _loop() -> None:
    global _last_fortune_date, _last_nightly_date, _last_insight_date, _last_rag_eval_date
    global _last_tarot_purge_date, _last_consultation_purge_date
    while True:
        try:
            s = get_settings()
            now = datetime.now()
            # 타로 세션 1주 TTL 정리 (하루 1회, 04:10). created_at UTC 초과분 삭제(메시지 CASCADE).
            if now.hour == 4 and now.minute == 10 and _last_tarot_purge_date != date.today():
                _last_tarot_purge_date = date.today()
                _run_tarot_purge_expired()
            # 1:1 상담 대화·요약 PDF 7일 파기 (하루 1회, 04:20). 동의 게이트 고지 이행(개인정보).
            if now.hour == 4 and now.minute == 20 and _last_consultation_purge_date != date.today():
                _last_consultation_purge_date = date.today()
                _run_consultation_purge()
            # 데일리 푸시: iljin(개인화) 우선, 아니면 일반 운세. 슬롯 시각은 daily_fortune_hour/minute 공용.
            if s.daily_iljin_enabled or s.daily_fortune_enabled:
                if (
                    now.hour == s.daily_fortune_hour
                    and now.minute == s.daily_fortune_minute
                    and _last_fortune_date != date.today()
                ):
                    factory = get_session_factory()
                    db = factory()
                    try:
                        if s.daily_iljin_enabled:
                            # 프로필 보유자 개인화 일진 + 미보유자 일반 운세를 한 번에 처리
                            sent = push_service.send_daily_iljin(db)
                            log.info("daily iljin push sent: %d", sent)
                        else:
                            sent = push_service.send_daily_fortune(db)
                            log.info("daily fortune push sent: %d", sent)
                        _last_fortune_date = date.today()
                    finally:
                        db.close()
            # 통합 야간 학습 배치 (00:30, CPU 전용, 하루 1회): OCR→색인→STT→아카이브
            if s.nightly_learning_enabled:
                if (
                    now.hour == s.nightly_learning_hour
                    and now.minute == s.nightly_learning_minute
                    and _last_nightly_date != date.today()
                ):
                    _last_nightly_date = date.today()
                    _run_nightly_learning_batch()
            # 일일 질문 인사이트 배치 (04:30, CPU 전용, 하루 1회)
            if s.daily_insight_enabled:
                if (
                    now.hour == s.daily_insight_hour
                    and now.minute == s.daily_insight_minute
                    and _last_insight_date != date.today()
                ):
                    _last_insight_date = date.today()
                    _run_daily_insight_batch()
                    _run_feedback_learning_batch()  # 인사이트 직후 피드백 폐루프(👍 검증색인/👎 큐)
            # RAG 검색 품질 평가 배치 (CPU 전용, 하루 1회).
            # 야간 학습(00:30)이 코퍼스를 재색인한 뒤 측정하도록 03:30 시작.
            # 학습/유튜브 재색인/다른 평가가 진행 중이면 코퍼스가 갱신 중이거나 CPU 가
            # 경합하므로 미루고, 다음 틱에 재시도한다(예약시각~+3시간 윈도우). 그 안에
            # 한 번도 한가하지 못하면 그날은 건너뛴다(다음 날 측정).
            if s.rag_eval_enabled and _last_rag_eval_date != date.today():
                start_min = s.rag_eval_hour * 60 + s.rag_eval_minute
                now_min = now.hour * 60 + now.minute
                if start_min <= now_min < start_min + 180:
                    if is_nightly_running() or is_reindex_running() or is_eval_running():
                        log.info("rag eval deferred: corpus batch/eval in progress")
                    else:
                        _last_rag_eval_date = date.today()
                        _run_rag_eval_batch()
        except Exception:  # noqa: BLE001
            log.exception("scheduler loop error")
        time.sleep(30)


def start() -> None:
    """앱 기동 시 1회 호출. 중복 기동 방지."""
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_loop, name="saju-scheduler", daemon=True)
    t.start()
    log.info("background scheduler started")
