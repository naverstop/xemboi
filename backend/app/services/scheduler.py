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
_last_tarot_learn_date: date | None = None
_last_consultation_purge_date: date | None = None
_last_pdf_purge_date: date | None = None
_last_session_purge_date: date | None = None
_last_video_sweep_date: date | None = None
_last_pricing_week: str | None = None   # 가격조사 주단위 중복방지(ISO 연-주차)
_last_receipt_reconcile_key: tuple[int, int] | None = None   # 유료 추가질문 orphan 리컨실 5분버킷 중복방지
_last_receipt_purge_date: date | None = None   # 종결 영수증 일일 purge 중복방지
_last_pending_expire_date: date | None = None   # 미완료 결제 pending 만료 일일 처리 중복방지


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


def _run_pdf_share_purge() -> None:
    """보관기간(config.pdf_share_ttl_days, 기본 30일) 지난 공유 상담서 PDF 정리. 실패는 로깅만.

    POST /api/pdf/consultation(-report)로 만든 토큰 PDF는 DB 추적이 없어(파일만) 이 배치가
    유일한 정리 경로다. 순수 파일 스윕(LLM/GPU/DB 없음)."""
    try:
        from backend.app.api.pdf import purge_expired_pdfs
        n = purge_expired_pdfs()
        if n:
            log.info("shared consultation PDFs purged: %d", n)
    except Exception:  # noqa: BLE001
        log.exception("pdf share purge failed")


def _run_session_retention_purge() -> None:
    """보관기간 경과 세션 파기(M6/제21조) — chat/compat/tool 세션(메시지 CASCADE)과 retrieval_logs(질문 원문).

    탈퇴하지 않은 회원의 오래된 대화·검색로그를 자동 파기. 순수 DB(LLM/GPU 없음). 실패는 로깅만."""
    from datetime import timedelta

    from sqlalchemy import text as _text

    factory = get_session_factory()
    db = factory()
    try:
        from backend.app.services import settings_service
        days = settings_service.get_int(db, "session_retention_days", 365)
        rl_days = settings_service.get_int(db, "retrieval_log_retention_days", 90)
        al_days = settings_service.get_int(db, "access_log_retention_days", 365)
        now = datetime.utcnow()
        cutoff = now - timedelta(days=max(1, days))
        rl_cutoff = now - timedelta(days=max(1, rl_days))
        al_cutoff = now - timedelta(days=max(1, al_days))
        res = {}
        for tbl in ("chat_sessions", "compat_sessions", "tool_sessions"):
            r = db.execute(_text(f"DELETE FROM {tbl} WHERE created_at < :c"), {"c": cutoff})
            res[tbl] = int(r.rowcount or 0)  # 메시지는 FK CASCADE 로 함께 삭제
        r = db.execute(_text("DELETE FROM retrieval_logs WHERE created_at < :c"), {"c": rl_cutoff})
        res["retrieval_logs"] = int(r.rowcount or 0)
        # 접속기록(IP=개인정보) 보관상한 파기(D9) — 무기한 적재 방지.
        r = db.execute(_text("DELETE FROM access_logs WHERE created_at < :c"), {"c": al_cutoff})
        res["access_logs"] = int(r.rowcount or 0)
        # 피드백 코멘트(사용자 원문 PII) 보관상한 마스킹(N4) — 학습 처리 후 장기보관 불필요. rating 은 익명 집계용 보존.
        r = db.execute(_text("UPDATE message_feedback SET comment=NULL WHERE comment IS NOT NULL AND created_at < :c"), {"c": rl_cutoff})
        res["feedback_comments"] = int(r.rowcount or 0)
        db.commit()
        if any(res.values()):
            log.info("session retention purge: %s (retention=%dd, logs=%dd)", res, days, rl_days)
    except Exception:  # noqa: BLE001
        log.exception("session retention purge failed")
        db.rollback()
    finally:
        db.close()


def _run_video_orphan_sweep() -> None:
    """영상 산출물 고아 파일 스윕(#2a/#2b 보정) — DB 잡 행이 없는 master/delivery *.mp4 를 제거.

    탈퇴 CASCADE(관리자가 타인 세션에 찍은 잡)·워커 레이스로 파일만 남는 경우를 주기적으로 청소한다.
    파일명 stem = job_token(uuid hex) 이므로 DB 의 모든 job_token 집합에 없는 파일이 고아.
    생성 중(mtime 24h 이내) 파일은 보호해 진행 중 렌더를 지우지 않는다. 순수 파일 I/O(LLM/GPU 없음)."""
    import time as _time
    from sqlalchemy import text as _text

    factory = get_session_factory()
    db = factory()
    try:
        from backend.app.services.video.service import _VIDEO_BASE
        tokens = {
            str(t) for (t,) in db.execute(
                _text("SELECT job_token FROM saju_video_jobs WHERE job_token IS NOT NULL")
            ).fetchall()
        }
        cutoff = _time.time() - 24 * 3600   # 24h 유예 — 진행 중 산출물 보호
        removed = 0
        for sub in ("master", "delivery"):
            d = _VIDEO_BASE / sub
            if not d.is_dir():
                continue
            for p in d.glob("*.mp4"):
                try:
                    if p.stem in tokens:
                        continue
                    if p.stat().st_mtime >= cutoff:
                        continue
                    p.unlink()
                    removed += 1
                except OSError:
                    pass
        if removed:
            log.info("video orphan sweep: removed %d orphan file(s)", removed)
    except Exception:  # noqa: BLE001
        log.exception("video orphan sweep failed")
    finally:
        db.close()


def _run_receipt_orphan_reconcile() -> None:
    """유료 추가질문 크래시 orphan(차감 O·완결 X) 리컨실 — pending+N분 경과분 멱등 환불.

    정상 답변은 done(EOF)에서 complete, 오류는 refund_followup 에서 refunded 로 마감돼 대상 아님.
    전원차단·강제재기동으로 '차감 커밋 ~ 완결' 사이에 죽어 pending 으로 남은 것만 환불한다(순수 DB·무LLM).
    임계·on/off 는 관리자 설정(receipt_orphan_min 기본20, receipt_reconcile_enabled 기본 on)."""
    factory = get_session_factory()
    db = factory()
    try:
        from backend.app.services import receipt_service, settings_service
        if not settings_service.get_bool(db, "receipt_reconcile_enabled", True):
            return
        # 하한 10분 강제 — 최악 생성시간(외부 폴백 포함 수백초)보다 작게 설정돼 진행 중 생성을 orphan 오판(매출 누수)하지 않게.
        mins = max(10, settings_service.get_int(db, "receipt_orphan_min", 20))
        n = receipt_service.reconcile_orphans(db, older_than_min=mins)
        if n:
            log.info("receipt orphan reconcile: refunded %d crash-orphan charge(s)", n)
    except Exception:  # noqa: BLE001
        log.exception("receipt orphan reconcile failed")
        db.rollback()
    finally:
        db.close()


def _run_pending_order_expire() -> None:
    """미완료(paymentKey 없는) pending 결제주문 만료 처리 — 유령/테스트 주문 누적 정리.

    토스 위젯 세션은 수십 분 내 만료되므로 N시간(기본24) 경과 pending 은 결제될 수 없다.
    approved/refunded 는 불변. 자동 결제 위험 없음(confirm 은 프론트 위젯완료+paymentKey 로만 발동)."""
    factory = get_session_factory()
    db = factory()
    try:
        from backend.app.services import payment_service, settings_service
        hrs = settings_service.get_int(db, "pending_order_expire_hours", 24)
        n = payment_service.expire_pending_orders(db, older_than_hours=hrs)
        if n:
            log.info("pending order expire: %d abandoned order(s) → expired", n)
    except Exception:  # noqa: BLE001
        log.exception("pending order expire failed")
        db.rollback()
    finally:
        db.close()


def _run_receipt_purge() -> None:
    """종결(complete/refunded) 영수증 일일 정리 — pending 은 절대 삭제 안 함(무한증가 방지)."""
    factory = get_session_factory()
    db = factory()
    try:
        from backend.app.services import receipt_service, settings_service
        days = settings_service.get_int(db, "receipt_retention_days", 7)
        n = receipt_service.purge_terminal(db, older_than_days=days)
        if n:
            log.info("receipt purge: removed %d terminal receipt(s)", n)
    except Exception:  # noqa: BLE001
        log.exception("receipt purge failed")
        db.rollback()
    finally:
        db.close()


def _run_tarot_deck_parity_learn() -> None:
    """타로 덱 패리티 체크 → 변경 시 자동 재학습(운영자 요구, 2026-07-11).

    관리자 편집(키워드/해석) 누적분의 내용 해시가 마지막 학습본과 다르면 재학습
    (라이브 캐시 재적재 + 확정 스냅샷 버전 저장). 인프로세스 실행이라 :8008 의
    tarot_deck 캐시에 즉시 반영된다(서브프로세스면 캐시 미반영). 순수 CPU·무LLM."""
    factory = get_session_factory()
    db = factory()
    try:
        from backend.app.services import tarot_content
        st = tarot_content.learn_status(db)
        if st["changed"]:
            out = tarot_content.relearn(db, mode="auto")
            if out.get("skipped"):  # 락 경합 등으로 직전에 이미 학습됨 — 중복 방지 정상 동작
                log.info("tarot deck auto-relearn skipped (already up-to-date, v%s)", out["version"])
            else:
                log.info("tarot deck auto-relearn: v%s (snapshot=%s)", out["version"], out.get("snapshot"))
        else:
            log.info("tarot deck parity ok (v%s) — relearn skipped", st["version"])
    except Exception:  # noqa: BLE001
        log.exception("tarot deck parity learn failed")
    finally:
        db.close()


# 미응답 상담 재푸시 상태 — {session_id: 마지막 푸시 epoch}. 프로세스 재시작 시 리셋(무해: 첫 틱에 재개).
_consult_repush: dict[str, float] = {}


def _run_consult_request_renotify() -> None:
    """미응답 상담 요청 반복 알림(운영자 지시 2026-07-11) — 상담사가 수락/거절할 때까지 계속.

    requested 상태 + 15분 이내 요청에 45초 간격으로 웹푸시 재발송. 수락/거절/취소로
    상태가 바뀌면 자연 중지. 최초 접수 푸시는 API가 이미 보냈으므로 45초 후부터 재푸시.
    콘솔이 열려 있으면 프론트가 자체 소리/음성 반복 알림을 함께 울린다(이중 안전망)."""
    import time as _time
    from datetime import timedelta

    from backend.app.repositories.consultation_models import Consultant, ConsultationSession

    factory = get_session_factory()
    db = factory()
    try:
        now = datetime.utcnow()
        rows = (
            db.query(ConsultationSession)
            .filter(
                ConsultationSession.status == "requested",
                ConsultationSession.requested_at >= now - timedelta(minutes=15),
            )
            .all()
        )
        alive = {r.id for r in rows}
        for k in list(_consult_repush):
            if k not in alive:
                _consult_repush.pop(k, None)     # 응답됨/만료 — 추적 종료
        if not rows:
            return
        from backend.app.services import push_service
        for r in rows:
            ts = _time.time()
            last = _consult_repush.get(r.id)
            if last is None:
                _consult_repush[r.id] = ts       # 최초 발견 — API의 접수 푸시 직후이므로 대기
                continue
            if ts - last < 45:
                continue
            c = db.get(Consultant, r.consultant_id)
            if not c or not c.user_id:
                _consult_repush[r.id] = ts
                continue
            mins = max(1, int((now - r.requested_at).total_seconds() // 60))
            push_service.send_to_user(
                db, c.user_id, "🔔 대기 중인 상담 요청",
                f"아직 응답하지 않은 상담 요청이 있어요 ({mins}분 경과). 콘솔에서 수락 또는 거절해 주세요.",
                url="/consultation/console", tag="consult-request",
            )
            db.commit()
            _consult_repush[r.id] = ts
    except Exception:  # noqa: BLE001
        log.exception("consult request renotify failed")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    finally:
        db.close()



def _run_pricing_survey() -> None:
    """주단위 시장조사 → 권장가 산출(pending 적재). ⛔ 가격을 변경하지 않는다(관리자 승인만 변경).

    경쟁사 수동 시트 + 가드레일로 결정적 계산(LLM/GPU 없음) — 인프로세스 실행. 실패는 로깅만."""
    factory = get_session_factory()
    db = factory()
    try:
        from backend.app.services import pricing_agent_service as p
        r = p.run_survey(db)
        log.info("pricing survey: batch=%s pending=%d skipped=%d",
                 r["batch_id"], r["pending"], r["skipped"])
    except Exception:  # noqa: BLE001
        log.exception("pricing survey failed")
    finally:
        db.close()


def run_pricing_survey_now() -> dict:
    """관리자 수동 — 지금 시장조사 1회(권장만 생성, 가격변경 없음)."""
    _run_pricing_survey()
    return {"started": True}


def _loop() -> None:
    global _last_fortune_date, _last_nightly_date, _last_insight_date, _last_rag_eval_date
    global _last_tarot_purge_date, _last_consultation_purge_date, _last_pdf_purge_date
    global _last_session_purge_date, _last_video_sweep_date, _last_tarot_learn_date
    global _last_pricing_week, _last_receipt_reconcile_key, _last_receipt_purge_date
    global _last_pending_expire_date
    while True:
        try:
            s = get_settings()
            now = datetime.now()
            # 미응답 1:1 상담 재푸시 — 매 틱(30초) 검사, 요청별 45초 간격(응답 시 자연 중지)
            _run_consult_request_renotify()
            # 유료 추가질문 크래시 orphan 리컨실 — 5분마다(pending+N분 경과 = 차감 O·완결 X 멱등 환불)
            _rk = (now.hour, now.minute // 5)
            if _rk != _last_receipt_reconcile_key:
                _last_receipt_reconcile_key = _rk
                _run_receipt_orphan_reconcile()
            # 타로 세션 1주 TTL 정리 (하루 1회, 04:10). created_at UTC 초과분 삭제(메시지 CASCADE).
            if now.hour == 4 and now.minute == 10 and _last_tarot_purge_date != date.today():
                _last_tarot_purge_date = date.today()
                _run_tarot_purge_expired()
            # 타로 덱 패리티 체크→변경 시 자동 재학습 (하루 1회, 04:15). 인프로세스(캐시 즉시 반영)·무LLM.
            if now.hour == 4 and now.minute == 15 and _last_tarot_learn_date != date.today():
                _last_tarot_learn_date = date.today()
                _run_tarot_deck_parity_learn()
            # 1:1 상담 대화·요약 PDF 7일 파기 (하루 1회, 04:20). 동의 게이트 고지 이행(개인정보).
            if now.hour == 4 and now.minute == 20 and _last_consultation_purge_date != date.today():
                _last_consultation_purge_date = date.today()
                _run_consultation_purge()
            # 공유용 상담서 PDF(data/pdf/{token}) TTL 정리 (하루 1회, 04:25). 링크공유 대비 개인정보/용량.
            if now.hour == 4 and now.minute == 25 and _last_pdf_purge_date != date.today():
                _last_pdf_purge_date = date.today()
                _run_pdf_share_purge()
            # 보관기간 경과 세션·검색로그 파기 (하루 1회, 04:35). 제21조 파기(M6).
            if now.hour == 4 and now.minute == 35 and _last_session_purge_date != date.today():
                _last_session_purge_date = date.today()
                _run_session_retention_purge()
            # 영상 고아 파일 스윕 (하루 1회, 04:40) — 탈퇴 CASCADE·워커 레이스로 남은 mp4 청소(#2a/#2b 보정).
            if now.hour == 4 and now.minute == 40 and _last_video_sweep_date != date.today():
                _last_video_sweep_date = date.today()
                _run_video_orphan_sweep()
            # 종결 영수증 일일 purge (하루 1회, 04:45) — pending 은 보존, 무한증가 방지.
            if now.hour == 4 and now.minute == 45 and _last_receipt_purge_date != date.today():
                _last_receipt_purge_date = date.today()
                _run_receipt_purge()
            # 미완료 결제 pending 만료 (하루 1회, 04:50) — paymentKey 없는 유령/테스트 주문 정리(자동결제 위험 없음).
            if now.hour == 4 and now.minute == 50 and _last_pending_expire_date != date.today():
                _last_pending_expire_date = date.today()
                _run_pending_order_expire()
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
            # 마케팅 가격 조사 (주1회, 월요일 05:00). 권장만 생성·⛔자동적용 없음(관리자 승인 필수).
            # 토글은 DB(app_settings)에 있어 세션으로 읽는다. 시각 일치 시에만 세션을 연다.
            if now.weekday() == 0 and now.hour == 5 and now.minute == 0:
                wk = f"{now.isocalendar().year}-W{now.isocalendar().week:02d}"
                if _last_pricing_week != wk:
                    _pf = get_session_factory()
                    _pdb = _pf()
                    try:
                        from backend.app.services import settings_service as _ss
                        if _ss.get_bool(_pdb, "pricing_survey_enabled"):
                            _last_pricing_week = wk
                            _run_pricing_survey()
                    finally:
                        _pdb.close()
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
