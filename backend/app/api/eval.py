"""RAG 평가 결과 조회 + 수동 실행 엔드포인트.

- GET  /api/eval/runs    : 누적된 평가 결과(runs.jsonl) 조회 (공개)
- GET  /api/eval/status  : 수동 평가 실행 상태 (관리자)
- POST /api/eval/run     : 평가를 지금 1회 실행(백그라운드, 관리자)

평가 자체의 의미/메트릭 정의는 ml/eval/eval_retrieval.py 참조.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.app.core.config import get_settings
from backend.app.core.deps import require_admin
from backend.app.repositories.auth_models import User

log = logging.getLogger("saju.eval")

router = APIRouter(prefix="/api/eval", tags=["eval"])

PROJECT_ROOT = Path(__file__).resolve().parents[3]
RUNS_PATH = PROJECT_ROOT / "data" / "eval" / "runs.jsonl"

# --- 수동 평가 실행 상태(단일 프로세스·단일 인스턴스) ---
_state_lock = threading.Lock()
_eval_state: dict = {
    "running": False,
    "started_at": None,    # ISO8601
    "finished_at": None,   # ISO8601
    "last_tag": None,
    "last_error": None,    # 실패 사유(문자열) — 성공 시 None
    "last_summary": None,  # 마지막 성공 run 요약
}


def _read_runs(limit: int = 200) -> tuple[list[dict], int]:
    """runs.jsonl 을 읽어 (행 목록, 손상으로 건너뛴 줄 수) 반환.

    손상 줄은 조용히 버리지 않고 경고 로그를 남기고 카운트해, 추세에서 결과가
    소리없이 사라지는 일(관측 사각지대)을 방지한다.
    """
    if not RUNS_PATH.exists():
        return [], 0
    rows: list[dict] = []
    skipped = 0
    with RUNS_PATH.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                skipped += 1
                log.warning("runs.jsonl 손상 줄 %d 건너뜀: %s", lineno, e)
                continue
    if limit > 0:
        rows = rows[-limit:]
    return rows, skipped


@router.get("/runs")
def list_runs(limit: int = 200, admin: User = Depends(require_admin)) -> dict:
    # 관리자 전용 — 내부 데이터셋 경로·RAG 품질지표 노출 방지(/status·/run 과 통일).
    rows, skipped = _read_runs(limit)
    return {"runs": rows, "count": len(rows), "skipped_malformed": skipped}


@router.get("/status")
def eval_status(admin: User = Depends(require_admin)) -> dict:
    with _state_lock:
        return dict(_eval_state)


class RunEvalReq(BaseModel):
    tag: str | None = None
    # 0 = 운영 설정(rag_top_k_default)을 따른다. 예전 기본 8은 운영(4)의 두 배였다(P3-D2).
    top_k: int = 0


def _run_eval_bg(tag: str, top_k: int, qdrant_url: str, collection: str) -> None:
    """RAG retrieval 평가 1회를 **별도 프로세스**로 돌리고 runs.jsonl 에 append.

    [P3-D7 2026-07-22] 예전에는 이 함수가 인프로세스에서 evaluate() 를 직접 호출했다.
    그런데 eval 쪽 SajuRetriever 는 device 미지정 → torch 기본 'cuda' 를 잡고, 백엔드는
    saju_start.bat 에서 CUDA_VISIBLE_DEVICES=1 로 뜨므로 그 'cuda' 가 곧 **ollama·리랭커가
    쓰는 GPU1**이었다. 실측 GPU1 여유 1,129MiB / BGE-m3 약 2.3GB → 관리자가 '지금 평가 실행'을
    누르면 CUDA OOM 이 나거나 VRAM 을 영구 점유한다. 게다가 _load_embedder 는 device 가 캐시
    키인 lru_cache(maxsize=1) 이라 운영용 CPU 임베더가 캐시에서 축출된다.
    → 야간 배치(scheduler._run_rag_eval_batch)와 똑같이 CUDA_VISIBLE_DEVICES=-1 서브프로세스로 뺀다.
    """
    import os
    import subprocess
    import sys

    error: str | None = None
    summary: dict | None = None
    try:
        from ml.eval.eval_retrieval import eval_lock   # PROJECT_ROOT·RUNS_PATH 는 이 모듈 것 사용

        # 교차 가드 락: 스케줄러 서브프로세스 평가가 이 락(PID 파일)을 보고 그날 실행을
        # 미루도록 한다(웹서버 ↔ 배치 프로세스 동시 평가 방지).
        with eval_lock():
            cmd = [sys.executable, "-u", "-m", "ml.eval.eval_retrieval",
                   "--tag", tag, "--qdrant-url", qdrant_url, "--collection", collection]
            if top_k:
                cmd += ["--top-k", str(top_k)]
            env = dict(os.environ)
            env.setdefault("PYTHONPATH", str(PROJECT_ROOT))
            env["CUDA_VISIBLE_DEVICES"] = "-1"   # CPU 강제("" 는 torch 에서 무효)
            before = RUNS_PATH.stat().st_size if RUNS_PATH.exists() else 0
            proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env,
                                  capture_output=True, text=True, timeout=1800)
            if proc.returncode != 0:
                tail = (proc.stdout or "")[-400:] + (proc.stderr or "")[-400:]
                raise RuntimeError(f"eval exited {proc.returncode}: {tail.strip()[:600]}")
            # 서브프로세스가 직접 append 하므로 마지막 줄을 되읽어 요약을 얻는다.
            if RUNS_PATH.exists() and RUNS_PATH.stat().st_size > before:
                lines = [ln for ln in RUNS_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]
                if lines:
                    summary = json.loads(lines[-1])
    except Exception as e:  # noqa: BLE001  — 실패 사유를 상태로 노출
        error = f"{type(e).__name__}: {e}"
    finally:
        with _state_lock:
            _eval_state["running"] = False
            _eval_state["finished_at"] = datetime.now(timezone.utc).isoformat()
            _eval_state["last_error"] = error
            if summary is not None:
                _eval_state["last_summary"] = summary


@router.post("/run")
def run_eval(req: RunEvalReq, admin: User = Depends(require_admin)) -> dict:
    """RAG 검색 품질 평가를 지금 1회 실행한다(백그라운드).

    BGE-m3 임베더 + Qdrant 가 떠 있어야 한다(채팅과 동일 검색기). 보통 10~60초.
    중복 기동은 409 로 막는다."""
    settings = get_settings()
    # 스케줄러가 띄운 별도 프로세스 평가(03:30 배치)도 같은 PID 락을 남기므로,
    # 그 경우에도 중복 기동을 막는다(인프로세스 플래그만으론 프로세스 경계를 못 봄).
    from backend.app.services import scheduler
    with _state_lock:
        if _eval_state["running"] or scheduler.is_eval_running():
            raise HTTPException(
                status_code=409,
                detail="이미 평가가 실행 중입니다. 완료 후 다시 시도해 주세요.",
            )
        tag = (req.tag or "").strip() or f"manual_{datetime.now().strftime('%m%d_%H%M')}"
        _eval_state.update(
            {
                "running": True,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
                "last_tag": tag,
                "last_error": None,
            }
        )

    t = threading.Thread(
        target=_run_eval_bg,
        args=(tag, req.top_k, settings.qdrant_url, settings.qdrant_collection),
        name="saju-rag-eval",
        daemon=True,
    )
    t.start()
    return {
        "status": "started",
        "tag": tag,
        # 문항 수를 하드코딩하지 않는다 — 실제로는 50문항인데 49로 적혀 있었다(파일 끝 개행 누락
        # 때문에 wc -l 이 49로 나온 것을 그대로 옮긴 오류). 골든셋이 바뀌면 또 어긋난다.
        "message": ("RAG 평가를 시작했습니다 (백그라운드). 별도 프로세스·CPU로 돌며 보통 1~3분 걸립니다. "
                    "운영과 동일한 게이트(리랭커·임계·top_k)로 재므로 예전 런보다 점수가 낮게 나옵니다."),
    }
