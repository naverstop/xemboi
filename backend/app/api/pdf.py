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
from backend.app.core.deps import get_current_user, get_optional_user
from backend.app.repositories.auth_models import User
from backend.app.services.pdf_service import generate_consultation_pdf

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

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
    compat_id: Optional[str] = Field(None, max_length=64)    # 궁합 세션 — 있으면 2인 명식+펜타곤 포함
    # 타로 — 뽑은 카드(이미지 그리드로 PDF에 포함). [{position_name, name_kr, name_en, orientation, image_url}]
    tarot_cards: Optional[list[dict]] = Field(None, max_length=11)


class ConsultationPdfResp(BaseModel):
    token: str
    url: str           # 인라인 보기/공유용
    download_url: str  # 첨부 다운로드용
    filename: str


def _safe_filename(title: str) -> str:
    """한글/영숫자/공백/괄호/._- 만 남긴 안전한 .pdf 파일명(궁합 제목의 괄호 보존)."""
    base = re.sub(r"[^\w가-힣 ()._-]", "", title or "").strip() or "상담서"
    return f"{base[:80]}.pdf"


def purge_expired_pdfs(ttl_days: Optional[int] = None) -> int:
    """보관기간(config.pdf_share_ttl_days) 지난 공유 PDF(data/pdf/{token}.pdf/.name) 삭제.

    이 토큰 PDF들은 어떤 DB에도 추적되지 않으므로 파일 mtime(생성시각) 기준으로 스윕한다.
    링크공유(수신자가 서버 URL 열람) 채택에 따른 개인정보/디스크 보호. 스케줄러 04:25 호출.
    반환: 삭제한 .pdf 개수.
    """
    import time
    if ttl_days is None:
        from backend.app.core.config import get_settings
        ttl_days = get_settings().pdf_share_ttl_days
    if not _PDF_DIR.is_dir() or ttl_days <= 0:
        return 0
    cutoff = time.time() - ttl_days * 86400
    removed = 0
    for pdf_path in _PDF_DIR.glob("*.pdf"):
        try:
            if pdf_path.stat().st_mtime >= cutoff:
                continue
            pdf_path.unlink(missing_ok=True)
            pdf_path.with_suffix(".name").unlink(missing_ok=True)  # 사이드카 파일명도 함께
            pdf_path.with_name(f"{pdf_path.stem}.thumb.png").unlink(missing_ok=True)  # 공유카드 썸네일 캐시
            removed += 1
        except Exception:  # noqa: BLE001
            continue
    return removed


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
                   user: Optional[User]) -> tuple[dict | None, str, "date | None"]:
    """세션의 명식(chart_json)·캡션(생년월일시)·상담일(세션 생성일 KST) — 명식 패널 + 상담일자용.

    소유권은 chat API와 동일 규칙(회원 세션은 본인만). 불일치/부재 시 (None, "", None)로
    조용히 생략 — PDF 생성 자체는 계속(명식만 빠짐).
    상담일: 과거 세션을 나중에 재발급해도 상담일자가 '오늘'로 찍히지 않게 세션 created_at(UTC)→KST 날짜.
    """
    if not session_id:
        return None, "", None
    try:
        from backend.app.repositories import chat_repo
        row = chat_repo.get_session(db, session_id.strip())
        if row is None:
            # 신년운세·택일·작명 등 도구(tool)는 tool_sessions 테이블 — 명식(chart_json)이 여기 있다.
            #   (chat 세션에만 명식 패널을 붙이던 탓에 신년운세 PDF에 명식이 빠지던 결함.)
            from backend.app.repositories.models import ToolSession
            row = db.get(ToolSession, session_id.strip())
        if row is None:
            return None, "", None
        # 명식 패널은 '본인 소유 회원 세션'만 — 익명(게스트) 세션은 소유 바인딩이 없어
        # session_id 를 아는 임의 사용자가 남의 명식(생년월일시)을 PDF로 뽑는 IDOR 이 가능했음.
        # 게스트 본인도 패널만 조용히 생략(상담일은 사용) — PDF 생성 자체는 계속.
        owned = row.user_id is not None and user is not None and user.id == row.user_id
        consult_date = None
        if getattr(row, "created_at", None):
            from datetime import timezone, timedelta
            consult_date = (
                row.created_at.replace(tzinfo=timezone.utc)
                .astimezone(timezone(timedelta(hours=9))).date()
            )
        if not owned or not getattr(row, "chart_json", None):
            return None, "", consult_date  # 미소유/명식 없음 — 상담일만 사용
        cap = f"{row.birth_date:%Y년 %m월 %d일}"
        if getattr(row, "birth_time", None):
            cap += f" {row.birth_time:%H:%M}"
        cap += " 생 · " + ("곤명(坤命)" if "female" in str(row.gender).lower() else "건명(乾命)")
        return row.chart_json, cap, consult_date
    except Exception:  # noqa: BLE001
        return None, "", None


def _compat_data(db: Session, compat_id: Optional[str],
                 user: Optional[User]) -> tuple[dict | None, "date | None"]:
    """궁합 세션의 2인 명식·캡션·5요소 점수·상담일 — PDF 패널용. 반환 (compat_dict|None, 상담일|None).

    소유권은 _session_chart 와 동일 규칙(회원 본인만) + 비프리뷰(입장료 결제분)만. 미소유·프리뷰·부재 시
    compat=None(패널 생략, PDF 생성은 계속). compat_id 만 알면 남의 2인 명식을 뽑는 IDOR 을 차단한다.
    """
    if not compat_id:
        return None, None
    try:
        from backend.app.repositories.models import CompatibilitySession
        row = db.get(CompatibilitySession, compat_id.strip())
        if row is None:
            return None, None
        consult_date = None
        if getattr(row, "created_at", None):
            from datetime import timezone, timedelta
            consult_date = (row.created_at.replace(tzinfo=timezone.utc)
                            .astimezone(timezone(timedelta(hours=9))).date())
        owned = row.user_id is not None and user is not None and user.id == row.user_id
        if not owned or getattr(row, "is_preview", False):
            return None, consult_date  # 미소유/미리보기 — 명식·펜타곤 생략(상담일만 사용)

        # 명식 캡션엔 이름/호칭을 넣지 않는다(개인정보 최소화 — 단독 사주 PDF와 동일 규칙, 운영자 지적).
        #   두 패널은 '첫 번째 분/두 번째 분' 섹션 제목으로 구분한다.
        def _cap(bd, bt, gender) -> str:
            c = f"{bd:%Y년 %m월 %d일}"
            if bt:
                c += f" {bt:%H:%M}"
            return c + " 생 · " + ("곤명(坤命)" if "female" in str(gender).lower() else "건명(乾命)")

        compat = {
            "a_chart": row.a_chart_json,
            "a_cap": _cap(row.a_birth_date, row.a_birth_time, row.a_gender),
            "b_chart": row.b_chart_json,
            "b_cap": _cap(row.b_birth_date, row.b_birth_time, row.b_gender),
            "factors": [("일지", row.f_day_branch), ("일간", row.f_day_stem), ("오행", row.f_wuxing),
                        ("십성", row.f_ten_god), ("신살", row.f_sinsal)],
        }
        return compat, consult_date
    except Exception:  # noqa: BLE001 — 로드 실패해도 PDF 생성은 계속(패널만 생략)
        return None, None


@router.post("/consultation", response_model=ConsultationPdfResp)
def create_consultation_pdf(
    req: ConsultationPdfReq,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> ConsultationPdfResp:
    chart, caption, consult_date = _session_chart(db, req.session_id, user)
    compat, compat_date = _compat_data(db, req.compat_id, user)
    try:
        pdf = generate_consultation_pdf(
            doc_title=req.doc_title, person_line=req.person_line,
            item=req.item, content=req.content,
            when=_parse_when(req.when) or consult_date or compat_date,  # 명시값 → 세션/궁합 상담일 → 오늘
            saju_chart=chart, saju_caption=caption,
            tarot_cards=req.tarot_cards, compat=compat,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"pdf_generation_failed: {e}")
    from backend.app.services.usage_service import bump_daily
    bump_daily(db, "feat", "pdf")          # 실사용 실측(관리자 현재 통계) — 실패해도 본 기능 무영향
    db.commit()
    return _store_pdf(pdf, req.doc_title)


class ConsultationReportReq(BaseModel):
    doc_title: str = Field(..., max_length=160)       # 예: "홍길동 님 사주 종합 감정서"
    person_line: str = Field("", max_length=160)
    item: str = Field("종합 감정", max_length=160)
    conversation: list[dict] = Field(..., min_length=1)  # [{role, content}] 상담 전체
    topic: str = Field("사주 상담", max_length=40)
    when: Optional[str] = None
    session_id: Optional[str] = Field(None, max_length=64)  # 사주 세션 — 있으면 명식 패널 포함


@router.post("/consultation-report", response_model=ConsultationPdfResp)
def create_consultation_report(
    req: ConsultationReportReq,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
) -> ConsultationPdfResp:
    """여러 질문·답변(상담 전체)을 로컬 LLM으로 하나의 '종합 감정서'로 재구성→상장양식 PDF."""
    from backend.app.services import chat_service
    convo = [
        {"role": ("user" if (m or {}).get("role") == "user" else "assistant"),
         "content": str((m or {}).get("content") or "")[:8000]}
        for m in req.conversation[:40]
    ]
    body = chat_service.synthesize_consultation(convo, topic=req.topic)
    if not body.strip():
        raise HTTPException(status_code=400, detail="요약할 상담 내용이 없습니다.")
    chart, caption, consult_date = _session_chart(db, req.session_id, user)
    try:
        pdf = generate_consultation_pdf(
            doc_title=req.doc_title, person_line=req.person_line,
            item=req.item, content=body,
            when=_parse_when(req.when) or consult_date,  # 명시값 우선 → 세션 상담일 → (None이면 오늘)
            saju_chart=chart, saju_caption=caption,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"pdf_generation_failed: {e}")
    from backend.app.services.usage_service import bump_daily
    bump_daily(db, "feat", "report")       # 실사용 실측(관리자 현재 통계)
    db.commit()
    return _store_pdf(pdf, req.doc_title)


class EmailPdfReq(BaseModel):
    token: str = Field(..., max_length=64)
    to: str = Field(..., max_length=254)              # 받는 사람 이메일
    doc_title: str = Field("", max_length=160)         # 제목용(예: "홍길동 님의 사주")
    message: Optional[str] = Field(None, max_length=1000)  # 사용자 메모(선택)


@router.post("/email")
def email_consultation_pdf(
    req: EmailPdfReq,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),   # 스팸 릴레이 방지 — 로그인 필수
) -> dict:
    """생성된 상담서 PDF(token)를 받는 사람 이메일로 **첨부**해 발송(서버 SMTP).

    게이트: 로그인 필수 + 공유 무료 한도(누적) 소비. SMTP 미설정 시 503(프론트가 mailto로 폴백).
    발송 실패 시 소비한 한도를 되돌린다(환원).
    """
    to_email = (req.to or "").strip()
    if not _EMAIL_RE.match(to_email):
        raise HTTPException(status_code=422, detail="invalid email")
    if not _TOKEN_RE.match(req.token):
        raise HTTPException(status_code=404, detail="not found")
    path = _PDF_DIR / f"{req.token}.pdf"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")

    from backend.app.services import settings_service, support_service
    from backend.app.services.auth_service import effective_level

    smtp = settings_service.get_smtp_config(db)
    if not (smtp.get("enabled") and smtp.get("host")):
        # 미설정 → 프론트가 mailto(링크)로 폴백하도록 신호
        raise HTTPException(status_code=503, detail="email_not_configured")

    # 공유 무료 한도 원자적 소비(관리자=무제한).
    # ⚠️ 2026-07-23 이전엔 여기서 get_settings().share_quota_default(=5)를 직접 읽어, 주석의
    #    "record_share 와 동일 규칙"이라는 말과 달리 **월 패스 확대(20회)가 반영되지 않았다**.
    #    패스 구독자가 PDF 메일 공유만 5회에서 막혔다. 이제 share.py 와 같은 함수를 호출한다.
    from backend.app.services import share_service
    lvl = effective_level(user)
    if lvl >= 5:
        raise HTTPException(status_code=403, detail="login required to share")
    consumed = False
    if lvl > 1:
        try:
            share_service.consume(db, user)
        except share_service.QuotaExceeded:
            raise HTTPException(status_code=403, detail="share_quota_exceeded")
        consumed = True

    # 파일명(사이드카) + 본문 구성 후 발송
    filename = "상담서.pdf"
    name_path = _PDF_DIR / f"{req.token}.name"
    if name_path.is_file():
        try:
            filename = name_path.read_text(encoding="utf-8").strip() or filename
        except Exception:  # noqa: BLE001
            pass
    title = (req.doc_title or "").strip() or "상담서"
    memo = (req.message or "").strip()
    # 보낸 사람 표시명 = 공유한 회원(이메일 아이디, 호칭 정책). From 표시이름·본문에 사용.
    #  ⚠️ From '주소'는 SMTP 인증계정 고정(사용자 이메일로 바꾸면 SPF/DKIM/DMARC 위반→스팸/차단).
    #     대신 Reply-To=회원 이메일이라 받는 사람이 답장하면 회원에게 간다.
    sender_id = ((user.email or "").split("@")[0] or "회원").strip()
    body = (
        (memo + "\n\n" if memo else "")
        + f"{sender_id} 님이 '인생상담 친구' 상담서({title})를 보냈습니다. 첨부된 PDF를 확인해 주세요.\n\n"
        + f"문의·답장은 이 메일에 그대로 회신하시면 {sender_id} 님({user.email})에게 전달됩니다.\n"
        + "— 인생상담 친구"
    )
    ok = support_service.send_pdf_email(
        smtp, to_email=to_email, subject=f"[인생상담 친구] {sender_id} 님의 {title}",
        body=body, pdf_bytes=path.read_bytes(), filename=filename,
        reply_to=user.email, sender_name=f"{sender_id} · 인생상담친구",
    )
    if not ok:
        # 발송 실패 → 소비한 한도 되돌림(환원). 소비와 같은 모듈을 써야 규칙이 다시 갈라지지 않는다.
        if consumed:
            share_service.refund(db, user)
        raise HTTPException(status_code=502, detail="email_send_failed")
    return {"ok": True}


@router.get("/{token}")
def get_pdf(token: str, download: int = Query(0)) -> FileResponse:
    if not _TOKEN_RE.match(token):
        raise HTTPException(status_code=404, detail="not found")
    path = _PDF_DIR / f"{token}.pdf"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    name_path = _PDF_DIR / f"{token}.name"
    filename = "상담서.pdf"
    if name_path.is_file():
        try:
            filename = name_path.read_text(encoding="utf-8").strip() or filename
        except Exception:  # noqa: BLE001
            pass
    disposition = "attachment" if download else "inline"
    # RFC 5987: 한글 파일명 안전 인코딩
    headers = {"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(filename)}"}
    return FileResponse(str(path), media_type="application/pdf", headers=headers)


@router.get("/{token}/thumb.png")
def get_pdf_thumb(token: str) -> FileResponse:
    """공유 링크카드용 PDF 첫장 썸네일(PNG). 카카오 등 스크래퍼가 카드 대표이미지로 가져간다.

    [2026-07-28 운영자 지적 #9] 데스크톱 카카오 공유는 웹 플랫폼 제약상 '파일 첨부'가 원천 불가라
    링크 카드만 가능한데, 카드 대표이미지가 앱 아이콘(icon-512)이라 '안내 이미지만 온다'는 오해를 샀다.
    앱 아이콘 대신 '실제 상담서 첫 장'을 카드 이미지로 보여줘 문서처럼 보이게 한다(모바일은 별개로
    navigator.share 로 PDF 파일 자체가 전송됨). 첫 요청 때 1회 래스터화해 캐시(반복 스크랩 저비용).
    get_pdf 와 동일하게 무인증 공개(토큰만 알면 열람 — 기존 설계 유지)."""
    if not _TOKEN_RE.match(token):
        raise HTTPException(status_code=404, detail="not found")
    pdf_path = _PDF_DIR / f"{token}.pdf"
    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail="not found")
    thumb_path = _PDF_DIR / f"{token}.thumb.png"
    if not thumb_path.is_file():
        try:
            import fitz  # PyMuPDF — 렌더만(별도 프로세스 불요)
            doc = fitz.open(str(pdf_path))
            try:
                page = doc.load_page(0)
                # 폭 ~800px 목표로 첫 장 래스터화(카카오 피드 카드 권장 해상도)
                zoom = (800 / page.rect.width) if page.rect.width else 1.5
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                pix.save(str(thumb_path))
            finally:
                doc.close()
        except Exception:  # noqa: BLE001 — 렌더 실패해도 링크 자체는 동작(카드 이미지만 공백)
            raise HTTPException(status_code=404, detail="thumb unavailable")
    return FileResponse(str(thumb_path), media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})
