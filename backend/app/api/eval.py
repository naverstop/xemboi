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
def list_runs(limit: int = 200) -> dict:
    rows, skipped = _read_runs(limit)
    return {"runs": rows, "count": len(rows), "skipped_malformed": skipped}


@router.get("/status")
def eval_status(admin: User = Depends(require_admin)) -> dict:
    with _state_lock:
        return dict(_eval_state)


class RunEvalReq(BaseModel):
    tag: str | None = None
    top_k: int = 8


def _run_eval_bg(tag: str, top_k: int, qdrant_url: str, collection: str) -> None:
    """별도 스레드에서 RAG retrieval 평가 1회 실행 후 runs.jsonl 에 append."""
    error: str | None = None
    summary: dict | None = None
    try:
        from ml.eval.eval_retrieval import DEFAULT_DATASET, append_run, eval_lock, evaluate

        # 교차 가드 락: 스케줄러 서브프로세스 평가가 이 락(PID 파일)을 보고 그날 실행을
        # 미루도록 한다(웹서버 ↔ 배치 프로세스 동시 평가 방지).
        with eval_lock():
            result = evaluate(
                DEFAULT_DATASET, top_k=top_k, qdrant_url=qdrant_url, collection=collection
            )
            append_run(result, tag)
            summary = result["summary"]
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
        "message": "RAG 평가를 시작했습니다 (백그라운드). 49개 질문 검색에 보통 10~60초 걸립니다.",
    }
