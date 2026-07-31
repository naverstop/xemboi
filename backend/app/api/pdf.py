"""상담서 PDF 생성·다운로드 API — 6개 메뉴 공통.

POST /api/pdf/consultation : 메뉴/상담내용을 받아 상장풍 PDF(관인 날인)를 생성하고
                             data/pdf/{token}.pdf 로 저장 → 토큰 URL 반환.
GET  /api/pdf/{token}       : 저장된 PDF 반환. 기본 인라인(공유 미리보기),
                             ?download=1 이면 첨부(한글 파일명).

PDF 자체는 services.pdf_service.generate_consultation_pdf 가 만든다(상장 양식+관인).
실제 SNS 전송은 프론트가 이 토큰 URL 을 카카오/메일/Web Share 로 전달해 수행한다.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.db import get_db
from backend.app.core.deps import get_locale, get_optional_user
from backend.app.repositories.auth_models import User
from backend.app.services.pdf_service import generate_consultation_pdf

router = APIRouter(prefix="/api/pdf", tags=["pdf"])

# data/pdf 아래에 토큰별 파일 저장. (backend/app/api/pdf.py → parents[3] = 프로젝트 루트)
_PDF_DIR = Path(__file__).resolve().parents[3] / "data" / "pdf"
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


class ConsultationPdfReq(BaseModel):
    doc_title: str = Field(..., max_length=160)       # 메뉴별 제목(예: "홍길동 님의 사주")
    person_line: str = Field("", max_length=160)      # 대상자 표기(예: "홍 길 동 님")
    item: str = Field("상담", max_length=160)          # 상담 항목
    content: str = Field(..., min_length=1, max_length=80_000)  # 상담 내용
    when: Optional[str] = None                         # YYYY-MM-DD, 없으면 오늘
    session_id: Optional[str] = Field(None, max_length=64)  # 사주 세션 — 있으면 명식 패널 포함


class ConsultationPdfResp(BaseModel):
    token: str
    url: str           # 인라인 보기/공유용
    download_url: str  # 첨부 다운로드용
    filename: str


def _safe_filename(title: str) -> str:
    """한글/영숫자/공백/괄호/._- 만 남긴 안전한 .pdf 파일명(궁합 제목의 괄호 보존)."""
    base = re.sub(r"[^\w가-힣 ()._-]", "", title or "").strip() or "상담서"
    return f"{base[:80]}.pdf"


def _store_pdf(pdf: bytes, title: str) -> ConsultationPdfResp:
    """PDF 바이트를 토큰 파일로 저장하고 응답(토큰 URL) 생성. 두 엔드포인트 공용."""
    _PDF_DIR.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    (_PDF_DIR / f"{token}.pdf").write_bytes(pdf)
    try:
        (_PDF_DIR / f"{token}.name").write_text(_safe_filename(title), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    return ConsultationPdfResp(
        token=token,
        url=f"/api/pdf/{token}",
        download_url=f"/api/pdf/{token}?download=1",
        filename=_safe_filename(title),
    )


def _parse_when(when: Optional[str]) -> "date | None":
    if when:
        try:
            return datetime.strptime(when.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _session_chart(db: Session, session_id: Optional[str],
                   user: Optional[User]) -> tuple[dict | None, str]:
    """세션의 명식(chart_json)과 캡션(생년월일시) — 명식 패널용.

    소유권은 chat API와 동일 규칙(회원 세션은 본인만). 불일치/부재 시 (None, "")로
    조용히 생략 — PDF 생성 자체는 계속(명식만 빠짐).
    """
    if not session_id:
        return None, ""
    try:
        from backend.app.repositories import chat_repo
        row = chat_repo.get_session(db, session_id.strip())
        if row is None or not getattr(row, "chart_json", None):
            return None, ""
        if row.user_id is not None and (user is None or user.id != row.user_id):
            return None, ""
        cap = f"{row.birth_date:%Y년 %m월 %d일}"
        if getattr(row, "birth_time", None):
            cap += f" {row.birth_time:%H:%M}"
        cap += " 생 · " + ("곤명(坤命)" if "female" in str(row.gender).lower() else "건명(乾命)")
        return row.chart_json, cap
    except Exception:  # noqa: BLE001
        return None, ""


@router.post("/consultation", response_model=ConsultationPdfResp)
def create_consultation_pdf(
    req: ConsultationPdfReq,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> ConsultationPdfResp:
    chart, caption = _session_chart(db, req.session_id, user)
    try:
        pdf = generate_consultation_pdf(
            doc_title=req.doc_title, person_line=req.person_line,
            item=req.item, content=req.content, when=_parse_when(req.when),
            saju_chart=chart, saju_caption=caption,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"pdf_generation_failed: {e}")
    return _store_pdf(pdf, req.doc_title)


class ConsultationReportReq(BaseModel):
    doc_title: str = Field(..., max_length=160)       # 예: "홍길동 님 사주 종합 감정서"
    person_line: str = Field("", max_length=160)
    item: str = Field("종합 감정", max_length=160)
    conversation: list[dict] = Field(..., min_length=1)  # [{role, content}] 상담 전체
    topic: str = Field("사주 상담", max_length=40)
    when: Optional[str] = None
    session_id: Optional[str] = Field(None, max_length=64)  # 사주 세션 — 있으면 명식 패널 포함
    # 내부 호출(consultation.session_report)은 세션 로케일을 여기로 전달. 없으면 요청 헤더(get_locale).
    locale: Optional[str] = Field(None, max_length=2)


@router.post("/consultation-report", response_model=ConsultationPdfResp)
def create_consultation_report(
    req: ConsultationReportReq,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
    locale: str = Depends(get_locale),
) -> ConsultationPdfResp:
    """여러 질문·답변(상담 전체)을 로컬 LLM으로 하나의 '종합 감정서'로 재구성→상장양식 PDF."""
    from backend.app.services import chat_service
    loc = (req.locale or locale or "ko").strip().lower()[:2]
    if loc not in ("ko", "vi"):
        loc = "ko"
    convo = [
        {"role": ("user" if (m or {}).get("role") == "user" else "assistant"),
         "content": str((m or {}).get("content") or "")[:8000]}
        for m in req.conversation[:40]
    ]
    body = chat_service.synthesize_consultation(convo, topic=req.topic, locale=loc)
    if not body.strip():
        detail = "Không có nội dung tư vấn để tóm tắt." if loc == "vi" else "요약할 상담 내용이 없습니다."
        raise HTTPException(status_code=400, detail=detail)
    chart, caption = _session_chart(db, req.session_id, user)
    try:
        pdf = generate_consultation_pdf(
            doc_title=req.doc_title, person_line=req.person_line,
            item=req.item, content=body, when=_parse_when(req.when),
            saju_chart=chart, saju_caption=caption,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"pdf_generation_failed: {e}")
    return _store_pdf(pdf, req.doc_title)


@router.get("/{token}")
def get_pdf(
    token: str, download: int = Query(0), locale: str = Depends(get_locale)
) -> FileResponse:
    if not _TOKEN_RE.match(token):
        raise HTTPException(status_code=404, detail="not found")
    path = _PDF_DIR / f"{token}.pdf"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    name_path = _PDF_DIR / f"{token}.name"
    # 저장된 .name(제목 기반)이 우선. 없을 때만 로케일 기본 파일명 폴백.
    filename = "Bản tư vấn.pdf" if locale == "vi" else "상담서.pdf"
    if name_path.is_file():
        try:
            filename = name_path.read_text(encoding="utf-8").strip() or filename
        except Exception:  # noqa: BLE001
            pass
    disposition = "attachment" if download else "inline"
    # RFC 5987: 한글 파일명 안전 인코딩
    headers = {"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(filename)}"}
    return FileResponse(str(path), media_type="application/pdf", headers=headers)
