"""업로드 자료 검수 API."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.deps import get_current_user, require_admin
from backend.app.repositories.auth_models import User
from backend.app.repositories.upload_models import Upload
from backend.app.services import upload_service

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


class UploadDTO(BaseModel):
    id: int
    title: str
    category: str
    file_kind: str
    original_name: str
    size_bytes: int
    status: str
    submitter: str | None = None
    note: str | None = None
    submitted_at: str
    reviewed_at: str | None = None
    reviewer: str | None = None
    review_comment: str | None = None
    indexed_at: str | None = None
    indexed_source: str | None = None
    chunks_count: int | None = None

    @classmethod
    def from_row(cls, r: Upload) -> "UploadDTO":
        return cls(
            id=r.id,
            title=r.title,
            category=r.category,
            file_kind=r.file_kind,
            original_name=r.original_name,
            size_bytes=r.size_bytes,
            status=r.status,
            submitter=r.submitter,
            note=r.note,
            submitted_at=r.submitted_at.isoformat(),
            reviewed_at=r.reviewed_at.isoformat() if r.reviewed_at else None,
            reviewer=r.reviewer,
            review_comment=r.review_comment,
            indexed_at=r.indexed_at.isoformat() if r.indexed_at else None,
            indexed_source=r.indexed_source,
            chunks_count=r.chunks_count,
        )


class ReviewRequest(BaseModel):
    reviewer: str | None = None
    comment: str | None = None


@router.post("", response_model=UploadDTO, status_code=status.HTTP_201_CREATED)
async def submit(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    category: str | None = Form(None),
    note: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),   # 무인증 제출 차단(검수큐 오염·스토리지 소진·RAG 오염)
) -> UploadDTO:
    content = await file.read()
    # 회원 제출은 관리자/코퍼스 예약 카테고리를 사칭할 수 없다(파기 우회 방지, 제21조) — user_upload 로 강제.
    _cat = (category or "").strip() or "user_upload"
    if _cat in upload_service.RESERVED_UPLOAD_CATEGORIES:
        _cat = "user_upload"
    try:
        row = upload_service.submit_upload(
            db,
            filename=file.filename or "untitled",
            content=content,
            title=title,
            category=_cat,
            note=note,
            # submitter 는 로그인 계정으로 강제 — 클라이언트가 보낸 값을 신뢰하면 탈퇴 파기(제21조) 우회 가능(위조).
            submitter=user.email,
        )
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return UploadDTO.from_row(row)


class ZipImportResp(BaseModel):
    extracted: int
    duplicates: int
    skipped: int
    rejected: int
    total_in_zip: int
    learning_started: bool
    message: str


@router.post("/zip", response_model=ZipImportResp)
async def submit_zip(
    file: UploadFile = File(...),
    submitter: str | None = Form(None),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ZipImportResp:
    """zip 일괄 업로드(관리자) — 서버가 풀어 pdf/이미지/txt 를 학습 파이프라인에 투입하고
    바로 학습 배치를 시작한다(전문가 zip → 업로드 → 즉시 학습). OCR/STT 대상은 CPU 배치 처리."""
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="zip 파일만 업로드할 수 있어요.")
    content = await file.read()
    try:
        s = upload_service.ingest_zip(db, content=content, submitter=submitter or admin.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    n = len(s["extracted"])
    learning_started = False
    if n > 0:
        from backend.app.services import scheduler
        r = scheduler.run_nightly_learning_now()
        learning_started = bool(r.get("started"))

    parts: list[str] = []
    if n:
        parts.append(f"{n}개 자료를 등록했어요")
    else:
        parts.append("등록된 자료가 없어요")
    if s["duplicates"]:
        parts.append(f"중복 {len(s['duplicates'])}건 제외")
    if s["skipped"]:
        parts.append(f"미지원 {len(s['skipped'])}건 제외")
    if s["rejected"]:
        parts.append(f"품질미달 {len(s['rejected'])}건 제외")
    if learning_started:
        parts.append("학습을 시작했어요(CPU·백그라운드)")
    elif n:
        parts.append("학습 대기 중 — 이미 실행 중인 배치가 끝나면 반영돼요")

    return ZipImportResp(
        extracted=n,
        duplicates=len(s["duplicates"]),
        skipped=len(s["skipped"]),
        rejected=len(s["rejected"]),
        total_in_zip=s["total_in_zip"],
        learning_started=learning_started,
        message=" · ".join(parts),
    )


@router.get("", response_model=list[UploadDTO])
def list_(
    status_filter: Literal["pending", "approved", "rejected", "indexed", "failed", None] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),   # 무인증 시 reviewer(관리자 이메일) 등 메타 노출 → 관리자 전용
) -> list[UploadDTO]:
    rows = upload_service.list_uploads(db, status=status_filter, limit=limit)
    return [UploadDTO.from_row(r) for r in rows]


@router.get("/stats")
def stats(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> dict:
    """업로드/학습 성과 집계(상태분포·총청크·코퍼스 청크·14일 색인추세)."""
    return upload_service.stats(db)


@router.post("/{upload_id}/approve", response_model=UploadDTO)
def approve(
    upload_id: int,
    req: ReviewRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UploadDTO:
    try:
        row = upload_service.approve_and_index(
            db, upload_id, reviewer=req.reviewer or admin.email, comment=req.comment
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="upload not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return UploadDTO.from_row(row)


@router.post("/{upload_id}/reject", response_model=UploadDTO)
def reject(
    upload_id: int,
    req: ReviewRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UploadDTO:
    try:
        row = upload_service.reject_upload(
            db, upload_id, reviewer=req.reviewer or admin.email, comment=req.comment
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="upload not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return UploadDTO.from_row(row)


@router.post("/run-learning")
def run_learning(admin: User = Depends(require_admin)) -> dict:
    """관리자 수동 학습 실행 — 학습자료_new 폴더의 PDF/이미지 + 승인된 업로드를
    야간 배치를 기다리지 않고 즉시 CPU 배치로 학습(OCR→증분색인→아카이브).
    이미 실행 중이면 409. 단일 인스턴스 락으로 중복 기동을 막는다."""
    from backend.app.services import scheduler
    r = scheduler.run_nightly_learning_now()
    if not r["started"]:
        raise HTTPException(status_code=409, detail="이미 학습 배치가 실행 중입니다. 완료 후 다시 시도해 주세요.")
    return {"status": "started",
            "message": "학습 배치를 시작했습니다 (CPU·백그라운드). 자료량에 따라 수 분~수십 분 걸립니다."}


@router.post("/run-feedback-learning")
def run_feedback_learning(admin: User = Depends(require_admin)) -> dict:
    """관리자 수동 — 피드백 학습 폐루프 즉시 실행.
    👍(고평점) 답변 → 일반 명리 지식으로 환원(개인정보 제거) → 검증 코퍼스 색인,
    👎(+코멘트) → 개선 큐 적재. 일일 자동(인사이트 직후) 외에 수동으로도 돌릴 수 있다."""
    from backend.app.services import scheduler
    scheduler.run_feedback_learning_now()
    return {"status": "started",
            "message": "피드백 학습 폐루프를 시작했습니다 (👍 검증지식 색인 / 👎 개선큐, 백그라운드)."}


@router.get("/learning-status")
def learning_status(admin: User = Depends(require_admin)) -> dict:
    """야간/수동 학습 배치 실행 여부 + 진행상황(단계·진척·청크)."""
    from backend.app.services import scheduler, upload_service
    running = scheduler.is_nightly_running()
    progress = None
    try:
        import json
        p = upload_service.PROJECT_ROOT / "data" / "logs" / "learning_progress.json"
        if p.exists():
            progress = json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        progress = None
    return {"running": running, "progress": progress}
