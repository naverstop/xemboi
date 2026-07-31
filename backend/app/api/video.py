"""사주 답변 → 1분 쇼츠 영상 API(부록 C-2). chat(사주) 전용.

POST /jobs(즉시 20000P 차감·402 PAYWALL) / GET /jobs/{token}(폴링) /
GET /jobs/{token}/download(인증+소유 검증·410 만료) / GET /jobs(내 목록).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.deps import get_current_user
from backend.app.repositories.auth_models import User
from backend.app.repositories.models import SajuVideoJob
from backend.app.services import chat_service
from backend.app.services.video import service as vsvc

router = APIRouter(prefix="/api/video", tags=["video"])


class CreateVideoJobRequest(BaseModel):
    message_id: int
    session_id: str | None = None  # 일관성 체크용(옵션)


def _is_admin(user: User) -> bool:
    try:
        return chat_service._is_admin(user)
    except Exception:
        return False


def _owned(job: SajuVideoJob | None, user: User) -> bool:
    return bool(job and (job.user_id == user.id or _is_admin(user)))


def _job_view(job: SajuVideoJob) -> dict:
    out = {
        "job_token": job.job_token, "status": job.status, "stage": job.stage,
        "progress_pct": job.progress_pct, "detail": job.detail, "aspect": job.aspect,
        "title": (job.scenario_json or {}).get("title") if job.scenario_json else None,
    }
    if job.status == "done":
        out["download_url"] = f"/api/video/jobs/{job.job_token}/download"
        out["expires_at"] = job.expires_at.isoformat() if job.expires_at else None
    return out


@router.post("/jobs", status_code=status.HTTP_201_CREATED)
def create_job(req: CreateVideoJobRequest, response: Response, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    try:
        job = vsvc.create_job(db, req.message_id, requester=user, is_admin=_is_admin(user))
    except vsvc.PaywallError:
        # 클라이언트는 status===402로 감지 → openCharge
        raise HTTPException(status_code=402, detail="포인트가 부족합니다. 충전하면 영상 생성이 바로 시작돼요.")
    except vsvc.JobConflict as e:
        # 이미 생성 중인 같은 답변 → 기존 작업에 재첨부(중복 차감 없이 진행상황 반환, 200)
        existing = db.query(SajuVideoJob).filter(SajuVideoJob.job_token == str(e)).first()
        if existing is not None and _owned(existing, user):   # 소유자/운영자만 재첨부
            response.status_code = status.HTTP_200_OK
            return _job_view(existing)
        raise HTTPException(status_code=409, detail="이미 영상을 만들고 있어요.")
    except Exception as e:  # VideoSourceError 등
        code = getattr(e, "code", "")
        if code == "forbidden":
            raise HTTPException(status_code=403, detail="권한이 없습니다")
        if code == "not_assistant":
            raise HTTPException(status_code=400, detail="답변 메시지만 영상화할 수 있습니다")
        if code == "not_found":
            raise HTTPException(status_code=404, detail="대상을 찾을 수 없습니다")
        raise
    return _job_view(job)


@router.get("/jobs/{job_token}")
def get_job(job_token: str, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)) -> dict:
    job = db.query(SajuVideoJob).filter(SajuVideoJob.job_token == job_token).first()
    if not _owned(job, user):
        raise HTTPException(status_code=404, detail="not found")  # 존재 은닉
    return _job_view(job)


@router.get("/jobs/{job_token}/download")
def download(job_token: str, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)) -> FileResponse:
    job = db.query(SajuVideoJob).filter(SajuVideoJob.job_token == job_token).first()
    if not _owned(job, user):
        raise HTTPException(status_code=404, detail="not found")
    if job.status == "expired" or (job.expires_at and job.expires_at < datetime.utcnow()):
        raise HTTPException(status_code=410, detail="보관 기간이 만료되어 삭제되었습니다")
    if job.status != "done" or not job.delivery_path:
        raise HTTPException(status_code=409, detail="아직 준비되지 않았습니다")
    path = vsvc._abs(job.delivery_path)
    if not path or not path.exists():
        raise HTTPException(status_code=410, detail="파일이 더 이상 존재하지 않습니다")
    title = (job.scenario_json or {}).get("title") if job.scenario_json else None
    fname = f"{title}.mp4" if title else f"saju_video_{job_token[:8]}.mp4"
    return FileResponse(str(path), media_type="video/mp4", filename=fname)


@router.get("/jobs")
def my_jobs(active: int = Query(0), limit: int = Query(20, le=100),
            db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    q = db.query(SajuVideoJob).filter(SajuVideoJob.user_id == user.id)
    if active:
        q = q.filter(SajuVideoJob.status.in_(("queued", "running", "done")))
    total = q.count()
    rows = q.order_by(SajuVideoJob.id.desc()).limit(limit).all()
    return {"items": [_job_view(j) for j in rows], "total": total}
