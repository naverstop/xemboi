"""DB 답변 재활용 — chat(사주) 답변 → 영상 소스(읽기전용).

부록 A-1/C-3 레시피 A. content는 항상 전체답변, chart_json·birth는 평문(복호화 불요).
적대검증 4조건: _strip_md 필수 / johu_yongsin None 허용 / wuxing 영문키→한글 / 익명세션 권한.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from backend.app.repositories import chat_repo
from backend.app.repositories.models import ChatMessage, ChatSession
from backend.app.services.pdf_service import _strip_md
from backend.app.saju.constants import EARTHLY_BRANCHES, BRANCH_ZODIAC, TEN_GODS_KO
from backend.app.saju.types import FourPillars
from backend.app.saju.wuxing import compute_ten_gods

_WX_KO = {"wood": "목", "fire": "화", "earth": "토", "metal": "금", "water": "수"}


def _age_stage_of(birth_date: Any) -> tuple[int | None, str]:
    """출생연도 → 현재 만나이(근사) + 현재 생애단계. 시제(과거/현재/미래) 판단용."""
    import datetime
    try:
        y = int(str(birth_date)[:4])
        age = max(0, datetime.date.today().year - y)
    except (ValueError, TypeError):
        return None, ""
    st = "초년" if age < 8 else "유년" if age < 20 else "청년" if age < 40 else "장년" if age < 60 else "노년"
    return age, st


def _ten_gods_of(chart: dict[str, Any] | None) -> list[str]:
    """명식(pillars)에서 실제 육신(십성)을 결정적 계산 → 중복 제거 한글 리스트(환각 방지)."""
    try:
        tg = compute_ten_gods(FourPillars.model_validate(chart["pillars"])).model_dump()
        seen: list[str] = []
        for v in tg.values():
            ko = TEN_GODS_KO.get(v, v) if v else None
            if ko and ko not in seen:
                seen.append(ko)
        return seen
    except Exception:
        return []


class VideoSourceError(Exception):
    """소스 조회/권한 오류. code: not_found | forbidden | not_assistant."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass
class VideoSource:
    message_id: int
    session_id: str
    narration_src: str            # 마크다운 제거된 전체 답변
    summary: str | None           # 명식 요약 텍스트
    chart: dict[str, Any] | None  # chart_json (평문)
    zodiac: str                   # 띠(쥐~돼지) — 캐릭터 키
    gender: str = "male"          # male | female — 더빙 음성 성별
    wuxing_ko: dict[str, int] = field(default_factory=dict)  # 오행 한글 분포
    ten_gods: list[str] = field(default_factory=list)        # 명식 계산 육신(한글, 환각방지 근거)
    age: int | None = None        # 현재 만나이(근사) — 시제 판단용
    cur_stage: str = ""           # 현재 생애단계(초년~노년) — 이전=과거/현재/이후=미래
    birth_masked: str = ""        # 산출물/로그용 마스킹 생년(YYYY-**)


def _mask_birth(d: Any) -> str:
    s = str(d or "")
    return (s[:4] + "-**-**") if len(s) >= 4 else "****"


def _zodiac_of(chart: dict[str, Any] | None) -> str:
    try:
        br = chart["pillars"]["year"]["branch"]  # 한자 지지
        return BRANCH_ZODIAC[EARTHLY_BRANCHES.index(br)]
    except Exception:
        return ""


def _authorize(sess: ChatSession, requester: Any, is_admin: bool) -> None:
    """권한(D9): 익명세션(user_id NULL)=운영자만, 소유세션=본인/운영자만."""
    if is_admin:
        return
    if sess.user_id is None:
        raise VideoSourceError("forbidden", "anonymous session requires admin")
    uid = getattr(requester, "id", None)
    if uid is None or sess.user_id != uid:
        raise VideoSourceError("forbidden", "not owner")


def fetch_saju_video_source(
    db: Session, message_id: int, requester: Any = None, is_admin: bool = False
) -> VideoSource:
    """(message_id) → 영상 소스. assistant 메시지·권한·마크다운 제거를 강제."""
    msg: ChatMessage | None = chat_repo.get_message(db, message_id)
    if msg is None:
        raise VideoSourceError("not_found", "message not found")
    if msg.role != "assistant":
        raise VideoSourceError("not_assistant", "only assistant answers can be filmed")
    sess: ChatSession | None = db.get(ChatSession, msg.session_id)
    if sess is None:
        raise VideoSourceError("not_found", "session not found")
    _authorize(sess, requester, is_admin)

    chart = sess.chart_json
    wux = {}
    try:
        for k, v in (chart.get("wuxing") or {}).items():
            wux[_WX_KO.get(k, k)] = int(v)
    except Exception:
        wux = {}

    return VideoSource(
        message_id=msg.id,
        session_id=sess.session_id,
        narration_src=_strip_md(msg.content or ""),
        summary=sess.saju_summary,
        chart=chart,
        zodiac=_zodiac_of(chart),
        gender=(sess.gender or "male"),
        wuxing_ko=wux,
        ten_gods=_ten_gods_of(chart),
        age=_age_stage_of(sess.birth_date)[0],
        cur_stage=_age_stage_of(sess.birth_date)[1],
        birth_masked=_mask_birth(sess.birth_date),
    )
