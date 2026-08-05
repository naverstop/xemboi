"""궁합(宮合) 서비스 — 두 사주명식 → 룰 엔진 + 상담쿼터 차감 + LLM 해설 + 평균 집계.

- 빌링/무료한도는 상담과 동일 로직(chat_service._decide_billing)을 공유한다(상담 쿼터 공유).
- 요소별 근거점수(관법 중립)는 compat_sessions 에 컬럼으로 저장 → '전체 평균' 펜타곤 오버레이.
"""
from __future__ import annotations

import queue as _queue
import threading
import uuid
from datetime import datetime, time as time_t
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.domain.chat_dto import BirthDTO
from backend.app.domain.compat_dto import CompatPersonDTO
from backend.app.repositories.auth_models import SajuProfile, User
from backend.app.repositories.models import CompatibilityMessage, CompatibilitySession
from backend.app.saju.compatibility import CompatResult, compute_compatibility
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, SajuChart
from backend.app.services import auth_service, chat_service, external_llm, settings_service

# 궁합 해설용 시스템 프롬프트 — 룰 엔진 근거 기반, 관법 단정 금지.
from backend.app.services.tool_service import EASY_STYLE_RULE as _EASY  # noqa: E402  # 쉬운 글 공통(운영자 지적)

COMPAT_SYSTEM = """당신은 한국 명리학(사주팔자) 궁합 전문 상담사입니다.
이 상담은 입장료를 낸 유료 리포트입니다 — 빈약하면 안 됩니다. 아래 구성을 반드시 지키세요:
① 총평 한 문단 — 두 사람 관계의 큰 그림(끌림·안정·과제).
② 요소별 심화 — 일지(부부궁)·일간(천간합)·오행 상호보완·십성·신살 다섯 요소를 '각각 별도 문단'으로:
   점수와 계산 근거([궁합 분석]의 detail)를 쉬운 말로 풀고, 그것이 실제 연애·결혼 생활에서
   어떤 장면으로 나타나는지(예: 다툼 패턴·잘 맞는 순간)까지 구체적으로.
③ 관법별 종합(결혼·부부궁 / 균형 / 연애·끌림) — 점수 차이가 뜻하는 바를 비교 해설.
④ 관계 조언 — 실행 가능한 구체 조언 3가지(무엇을·어떻게).
원칙:
1. 아래 [궁합 분석]은 규칙 엔진이 계산한 객관적 근거입니다. 간지·합충·신살·점수는 이 값만 쓰세요.
   해석·관법·조언은 [참고자료]가 있으면 그 자료를 우선 근거로 삼으세요(값은 계산값, 뜻은 자료).
2. 궁합 관법은 학파마다 다릅니다. 한쪽이 정답이라 단정하지 마세요. 길흉 단정 금지.
3. 도화 등 해석이 갈리는 항목은 여러 관점을 함께 소개하세요.
4. [환각 금지] 분석에 없는 합·충·신살·간지를 지어내지 마세요.
5. 한국어로, 한자 술어는 한글(한자) 형식으로 표기하세요. 예: 정관(正官), 육합(六合).
6. 전체 최소 1,800자 — 반복 없이 구체성으로 채우세요.
""" + _EASY

COMPAT_FOLLOWUP_HINT = (
    "\n[추가 질문 안내] 사용자가 위 궁합 분석에 대해 추가로 묻습니다. "
    "분석 근거(합·충·오행·십성·신살)와 이전 대화를 토대로, 질문에 구체적으로 답하세요."
)

_FACTOR_LABEL = {
    "day_branch": "일지(부부궁)",
    "day_stem": "일간(천간합)",
    "wuxing": "오행 상호보완",
    # '십성(정재·정관)'은 '정재·정관이면 높은 점수'라는 채점 기준이지 이 커플의 십성이 아니다.
    # 모델이 이 라벨을 소제목으로 그대로 옮겨 본문(정인·상관)과 정면 모순됐다(전수감사 실측 3건 중 2건)
    # → 값으로 오인될 수 없는 이름으로 바꾼다. 실제 십성은 아래 f.items 의 detail 이 싣는다.
    "ten_god": "십성 궁합(서로를 보는 십성)",
    "sinsal": "신살(神煞)",
}


# ============================================================
# 입력 해석 (프로필 / 즉석입력)
# ============================================================
def _profile_to_birth(p: SajuProfile) -> BirthDTO:
    bt: time_t | None = None
    if p.birth_time:
        try:
            hh, mm = str(p.birth_time).split(":")[:2]
            bt = time_t(int(hh), int(mm))
        except Exception:  # noqa: BLE001
            bt = None
    return BirthDTO(
        birth_date=p.birth_date,
        birth_time=bt,
        calendar=p.calendar,
        is_leap_month=p.is_leap_month,
        gender=p.gender,
        apply_true_solar_time=p.apply_true_solar_time,
        birth_longitude=p.birth_longitude,
        apply_equation_of_time=p.apply_equation_of_time,
        night_zi_mode=p.night_zi_mode or "yaja",
    )


def _resolve_person(
    db: Session, person: CompatPersonDTO, user: User | None
) -> tuple[BirthDTO, str | None]:
    """CompatPersonDTO → (BirthDTO, label). profile_id 우선."""
    if person.profile_id is not None:
        if user is None:
            raise PermissionError("profile requires login")
        p = db.get(SajuProfile, person.profile_id)
        if p is None or p.user_id != user.id:
            raise KeyError(f"profile not found: {person.profile_id}")
        return _profile_to_birth(p), (person.label or p.label)
    if person.birth is not None:
        return person.birth, person.label
    raise ValueError("person requires profile_id or birth")


def _to_birth_input(b: BirthDTO, locale: str = "ko") -> BirthInput:
    # locale 은 요청 로케일(get_locale) 단일 진실원 — vi 면 105°E·hongoc_duc 경로.
    return BirthInput(
        birth_date=b.birth_date,
        birth_time=b.birth_time,
        calendar=b.calendar,
        is_leap_month=b.is_leap_month,
        gender=b.gender,
        apply_true_solar_time=b.apply_true_solar_time,
        birth_longitude=b.birth_longitude,
        apply_equation_of_time=b.apply_equation_of_time,
        night_zi_mode=b.night_zi_mode,
        locale=locale,
    )


# ============================================================
# LLM 해설
# ============================================================
def _render_result_for_llm(
    result: CompatResult, label_a: str, label_b: str, sa: str, sb: str, locale: str = "ko"
) -> str:
    # 요소·감점·관점·도화 내용(f.label / p.type·detail / p.label·grade / dohwa)은 엔진이 로케일에
    # 맞춰 산출하므로, 여기서는 감싸는 섹션 라벨·단위·마무리 지시만 vi 로 번들한다.
    vi = locale == "vi"
    if vi:
        parts = [f"[Lá số {label_a}]\n{sa}", f"[Lá số {label_b}]\n{sb}", "[Phân tích hợp đôi]"]
    else:
        parts = [f"[{label_a} 명식]\n{sa}", f"[{label_b} 명식]\n{sb}", "[궁합 분석]"]
    unit = " điểm" if vi else "점"
    for key, f in result.factors.items():
        line = f"- {f.label}: {f.score}{unit}"
        if f.items:
            line += " | " + "; ".join(it.detail for it in f.items)
        parts.append(line)
    if result.penalties:
        head = "[Yếu tố cần lưu ý] " if vi else "[주의 요소] "
        parts.append(head + ", ".join(f"{p.type}({p.detail})" for p in result.penalties))
    parts.append("[Tổng hợp theo trường phái]" if vi else "[관법별 종합]")
    for k, p in result.perspectives.items():
        parts.append(f"- {p.label}: {p.total}{unit} ({p.grade})")
    if result.dohwa_readings:
        head = "[Luận Đào Hoa (nhiều góc nhìn)] " if vi else "[도화 해석(여러 관점)] "
        parts.append(head + " / ".join(result.dohwa_readings))
    if vi:
        parts.append(
            f"\nDựa vào các căn cứ trên, hãy luận giải sự hợp đôi của {label_a} và {label_b} "
            f"theo mạch: điểm mạnh → điểm cần lưu ý → lời khuyên."
        )
    else:
        parts.append(
            f"\n위 근거로 {label_a}와 {label_b}의 궁합을 강점→주의점→조언 흐름으로 해설하세요."
        )
    return "\n".join(parts)


# ── RAG 검색 쿼리 (P3-A1) ────────────────────────────────────────────
# [전수감사 2026-07-22] 예전에는 rag_query = brief[:600] 이었다. 그런데 brief 는
# '[A 명식] → [B 명식] → [궁합 분석]' 순으로 조립되고 A 한 사람 요약만 1,197~1,418자라
# 600자 컷이 **A 명식 표 안에서 끝난다**. 실세션 23건 전수 확인 결과 검색 쿼리에
# '궁합'이라는 단어도 상대방(B)도 **0/23 으로 단 한 글자도 들어가지 않았다**(절단률 78~82%).
# 즉 궁합 자료는 해설 경로에서 구조적으로 검색될 수 없었고, 대신 '명식 표를 닮은 문서'
# = 남의 사주 풀이가 올라왔다(실측: 명식표 쿼리의 회수물 50%가 타인 명식 해설).
# → 표를 임베딩하지 말고 **무엇을 묻는지**를 한국어 산문으로 만든다. 명식 표는 검색어에서
#   빼되 프롬프트(ucontent)에는 그대로 남으므로 해설 근거는 하나도 줄지 않는다.
# ⚠️추가질문 경로(message 있음)는 원래 정상이었다 — 사용자 질문을 맨 앞에 그대로 둔다.
def _rag_query(result: CompatResult, chart_a: SajuChart, chart_b: SajuChart,
               message: str | None = None) -> str:
    """궁합 검색 쿼리 — 사용자 질문(있으면) + 관계 라벨 산문. 명식 표는 제외."""
    from backend.app.saju.constants import branch_korean, stem_korean

    def _dg(ch: SajuChart) -> tuple[str, str]:
        d = ch.pillars.day
        return (f"{stem_korean(d.stem)}({d.stem})", f"{branch_korean(d.branch)}({d.branch})")

    da, ba = _dg(chart_a)
    db_, bb = _dg(chart_b)
    parts = [f"궁합 해석 — 일간 {da}와 {db_}의 관계, 일지 {ba}와 {bb}의 합·충·형, 배우자궁 판단"]
    # 계산으로 확정된 관계 라벨만 덧붙인다(점수·이름은 검색에 무의미해 제외).
    labels: list[str] = []
    for key, f in (result.factors or {}).items():
        for it in (f.items or []):
            for tok in ("육합", "삼합", "반합", "방합", "충", "형", "파", "해", "원진", "귀문", "천간합"):
                if tok in (it.detail or "") and tok not in labels:
                    labels.append(tok)
    if labels:
        parts.append("관계 요소: " + "·".join(labels))
    if result.penalties:
        pt = [p.type for p in result.penalties if p.type]
        if pt:
            parts.append("주의 요소: " + "·".join(dict.fromkeys(pt)))
    parts.append("궁합 관법: 일간 상호관계, 일지 부부궁, 오행 상호보완, 신살")
    body = "\n".join(parts)
    return (f"{message}\n{body}" if message else body)[:600]


# 시기 질문 감지 — "결혼 시기 몇 월?"(기본 칩) 등. 감지 시에만 세운/월운↔두 명식 관계 주입(노이즈 방지).
_TIMING_KEYWORDS = ("몇 월", "몇월", "언제", "시기", "올해", "내년", "월별", "몇 년", "몇년", "타이밍")


def _timing_relations_block(question: str, a_cj: dict | None, b_cj: dict | None,
                            label_a: str, label_b: str) -> str:
    """시기 질문일 때 올해·내년 세운(+올해 당월 월운) ↔ 두 명식의 관계를 결정적으로 계산(전수감사 Phase 3).

    종전엔 간지 표만 주입돼 '내년 未가 A일지 卯와 해묘미 반합' 같은 판단을 전부 LLM이 자력 도출
    (신년운세가 제거한 바로 그 환각 표면). 공용 relations 모듈(반합·원진·해 포함) 재사용."""
    q = question or ""
    if not q or not any(k in q for k in _TIMING_KEYWORDS) or not (a_cj or b_cj):
        return ""
    try:
        from datetime import date as _d
        from backend.app.saju.pillars import compute_pillars
        from backend.app.saju.relations import luck_natal_relations
        from backend.app.saju.types import BirthInput as _BI
        today = _d.today()
        lines = ["[시기 근거 — 세운·월운과 두 사람 명식의 관계(전부 결정적 계산)]"]
        scopes: list[tuple[str, str, str]] = []
        fp_now, *_ = compute_pillars(_BI(birth_date=today))
        scopes.append((f"올해({today.year}) 세운", fp_now.year.stem, fp_now.year.branch))
        scopes.append((f"이번 달 월운", fp_now.month.stem, fp_now.month.branch))
        fp_next, *_ = compute_pillars(_BI(birth_date=_d(today.year + 1, 6, 1)))
        scopes.append((f"내년({today.year + 1}) 세운", fp_next.year.stem, fp_next.year.branch))
        for label, st, br in scopes:
            _scope_word = "세운" if "세운" in label else "월운"
            for who, cj in ((label_a, a_cj), (label_b, b_cj)):
                if not cj:
                    continue
                rels = luck_natal_relations(cj, st, br, scope=_scope_word)
                if rels:
                    lines.append(f"· {label} × {who}: " + "; ".join(rels))
        if len(lines) == 1:
            return ""
        lines.append("→ 시기 판단은 위 관계만 근거로 하고, 표에 없는 합·충·반합을 지어내지 마세요.")
        return "\n".join(lines)
    except Exception:  # noqa: BLE001 — 시기 관계는 부가: 실패해도 기존 흐름 유지
        return ""


# ============================================================
# 생성 — 엔진+빌링+영속 (해설은 스트리밍 엔드포인트에서 생성)
# ============================================================
def create_compatibility(
    db: Session,
    req_person_a: CompatPersonDTO,
    req_person_b: CompatPersonDTO,
    user: User | None = None,
    depth: str = "deep",
    explain_level: str = "normal",
    locale: str = "ko",
) -> dict[str, Any]:
    """궁합 생성: 두 명식 → 엔진 → 빌링(상담쿼터 공유, 1회 차감) → 저장.

    해설은 생성하지 않고 결과를 즉시 반환한다(스트리밍 해설은 별도 엔드포인트).
    이 차감이 '궁합 1회'이며, 첫 해설 스트림은 추가 과금하지 않는다.
    locale(요청 로케일)은 두 명식 계산(역법·경도)과 세션 행 locale 에 함께 반영된다.
    """
    birth_a, label_a = _resolve_person(db, req_person_a, user)
    birth_b, label_b = _resolve_person(db, req_person_b, user)
    label_a = label_a or "사람 A"
    label_b = label_b or "사람 B"

    chart_a = build_chart(_to_birth_input(birth_a, locale=locale))
    chart_b = build_chart(_to_birth_input(birth_b, locale=locale))
    result = compute_compatibility(chart_a, chart_b, locale=locale)

    # ---- 빌링(궁합 입장료 1회 차감) ----
    bill = chat_service._decide_entry_billing(db, user, "compat", claim=True)
    is_preview = bill["is_preview"]
    credits_to_charge = bill["credits_to_charge"]

    compat_id = uuid.uuid4().hex

    # ---- 차감/무료 갱신 (post_message와 동일) ----
    balance_after: int | None = None
    if user is not None:
        # 무료/멤버십 카운터는 _decide_entry_billing(claim=True)에서 원자적으로 선점됨 — 여기서 미증가.
        if credits_to_charge > 0:
            balance_after = auth_service.adjust_credit(
                db, user.id, -credits_to_charge, reason="compatibility", ref_id=compat_id
            )
        else:
            balance_after = auth_service.get_balance(db, user.id)

    # ---- 영속 (요소점수 컬럼 = 평균 집계용) ----
    f = result.factors
    p = result.perspectives
    row = CompatibilitySession(
        compat_id=compat_id,
        user_id=user.id if user else None,
        locale=locale,
        a_label=label_a,
        a_birth_date=birth_a.birth_date, a_birth_time=birth_a.birth_time,
        a_calendar=birth_a.calendar.value if hasattr(birth_a.calendar, "value") else str(birth_a.calendar),
        a_is_leap_month=birth_a.is_leap_month,
        a_gender=birth_a.gender.value if hasattr(birth_a.gender, "value") else str(birth_a.gender),
        a_apply_true_solar_time=birth_a.apply_true_solar_time,
        a_chart_json=chart_a.model_dump(mode="json"),
        b_label=label_b,
        b_birth_date=birth_b.birth_date, b_birth_time=birth_b.birth_time,
        b_calendar=birth_b.calendar.value if hasattr(birth_b.calendar, "value") else str(birth_b.calendar),
        b_is_leap_month=birth_b.is_leap_month,
        b_gender=birth_b.gender.value if hasattr(birth_b.gender, "value") else str(birth_b.gender),
        b_apply_true_solar_time=birth_b.apply_true_solar_time,
        b_chart_json=chart_b.model_dump(mode="json"),
        result_json=result.model_dump(mode="json"),
        f_day_branch=f["day_branch"].score,
        f_day_stem=f["day_stem"].score,
        f_wuxing=f["wuxing"].score,
        f_ten_god=f["ten_god"].score,
        f_sinsal=f["sinsal"].score,
        total_a=p["A"].total, total_b=p["B"].total, total_c=p["C"].total,
        is_preview=is_preview,
        credits_charged=credits_to_charge,
    )
    db.add(row)
    db.commit()

    return {
        "compat_id": compat_id,
        "person_a": {"label": label_a, "chart": chart_a.model_dump(mode="json")},
        "person_b": {"label": label_b, "chart": chart_b.model_dump(mode="json")},
        "result": _mask_compat_preview(result.model_dump(mode="json")) if is_preview
        else result.model_dump(mode="json"),
        "explain": "",  # 해설은 스트리밍 엔드포인트에서
        "is_preview": is_preview,
        "billing_mode": bill["billing_mode"],
        "credits_charged": credits_to_charge,
        "balance_after": balance_after,
    }


def _mask_compat_preview(result: dict | None) -> dict | None:
    """비로그인 미리보기(is_preview): 궁합 깊은 해석(관점별 점수·감점·도화)을 가리고 총점·요인(펜타곤)만
    티저로 노출. 입장료(기본 1만P) 미납 익명이 구조화 결과 전량을 무료 취득하는 것을 차단.
    DB엔 전체 저장·반환만 컷(작명/택일 마스킹과 동일 패턴)."""
    if not isinstance(result, dict):
        return result
    r = dict(result)
    if isinstance(r.get("perspectives"), dict):
        r["perspectives"] = {}
    if "penalties" in r:
        r["penalties"] = []
    if "dohwa_readings" in r:
        r["dohwa_readings"] = []
    r["preview_locked"] = True
    return r


def list_user_compat(
    db: Session, user_id: int, limit: int = 30, offset: int = 0,
) -> list[dict[str, Any]]:
    """회원 본인 궁합 세션 목록(최신순) — '지난 결과' 재열람용(무차감).

    각 항목은 목록 카드 표시용 최소 필드(두 사람 라벨·생일)만. 상세는 get_compatibility 로 재조회.
    입장료를 낸 세션이므로 모두 노출한다.
    """
    stmt = (
        select(CompatibilitySession)
        .where(CompatibilitySession.user_id == user_id)
        .order_by(CompatibilitySession.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    out: list[dict[str, Any]] = []
    for r in db.execute(stmt).scalars().all():
        out.append({
            "compat_id": r.compat_id,
            "created_at": r.created_at,
            "a_label": r.a_label,
            "b_label": r.b_label,
            "a_birth_date": r.a_birth_date.isoformat() if r.a_birth_date else None,
            "b_birth_date": r.b_birth_date.isoformat() if r.b_birth_date else None,
        })
    return out


def get_compatibility(db: Session, compat_id: str, user: User | None) -> dict[str, Any] | None:
    row = db.get(CompatibilitySession, compat_id)
    if row is None:
        return None
    if row.user_id is not None and (user is None or user.id != row.user_id):
        raise PermissionError("not your compatibility session")
    msg = db.execute(
        select(CompatibilityMessage)
        .where(CompatibilityMessage.compat_id == compat_id, CompatibilityMessage.role == "assistant")
        .order_by(CompatibilityMessage.id)
    ).scalars().first()
    explain = ""
    if msg:
        explain = chat_service._make_preview(msg.content) if (msg.is_preview and not msg.preview_revealed) else msg.content
        explain = chat_service.fix_term_hanja(explain)   # 저장본 재열람 정리(멱등) — '---'·오병기 소급
    return {
        "compat_id": compat_id,
        "person_a": {"label": row.a_label, "chart": row.a_chart_json},
        "person_b": {"label": row.b_label, "chart": row.b_chart_json},
        "result": _mask_compat_preview(row.result_json) if row.is_preview else row.result_json,
        "explain": explain,
        "is_preview": row.is_preview,
    }


# ============================================================
# 스트리밍 해설 / 추가질문 (SSE)
# ============================================================
def stream_message(
    db: Session,
    compat_id: str,
    message: str,
    user: User | None = None,
    depth: str = "deep",
    explain_level: str = "normal",
):
    """공개 진입점 — 내부 스트림을 감싸 '예상 밖 예외'에서도 선차감을 보상한다.

    [버그 2026-07-25] free-ride 차단을 위해 추가질문은 답변 생성 '전'에 유료차감을 확정 커밋한다
    (tool_service·dream 과 동일 설계). 그런데 내부 방어분기(LLM 장애·빈 답변·저장 실패) '밖'에서
    예외가 나면(후처리 동기함수 _verify_*/_scrub_source_refs/fix_term_hanja/_timing_relations_block 등)
    api/compatibility.py 의 포괄 except 가 삼켜 error 만 내보내고 환불하지 않아, 답변을 못 받은 채
    실포인트(1,000/3,000P)가 사라졌다 → 재질문 시 이중차감. tool_service.stream_message·dream 과
    동일한 catch-all 보상 래퍼로 닫는다.

    이중환불 방지: 내부가 스스로 환불한 지점에서는 receipt 를 비운다(_receipt.clear()).
    ⚠️ GeneratorExit(클라 이탈)은 환불하지 않고 그대로 올린다 — free-ride 차단 규약.
    """
    receipt: dict[str, Any] = {}
    try:
        yield from _stream_message_inner(
            db, compat_id, message, user=user, depth=depth, explain_level=explain_level, _receipt=receipt)
    except GeneratorExit:
        raise                       # 클라 이탈 — 정상 종료 경로(과금 유지)
    except Exception as e:  # noqa: BLE001
        if receipt.get("bill") is not None:
            try:
                db.rollback()
                chat_service.refund_followup(
                    db, user, receipt["bill"], receipt.get("pre_charged", 0),
                    reason="compatibility_q", ref_id=compat_id)
            except Exception:  # noqa: BLE001 — 보상 실패가 에러 전달을 막지 않는다
                pass
        import logging
        logging.getLogger("saju.compat").warning("compat stream failed(refunded): %s", e)
        yield ("error", {"detail": "답변 처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
                         "code": "internal_error"})


def _stream_message_inner(
    db: Session,
    compat_id: str,
    message: str,
    user: User | None = None,
    depth: str = "deep",
    explain_level: str = "normal",
    _receipt: dict[str, Any] | None = None,
):
    """SSE 제너레이터 — (event, data) 튜플 yield. 채팅 스트림과 동일 구조.

    - 첫 호출(아직 해설 없음): 궁합 해설 생성. create 시 과금에 포함 → 추가 무과금.
    - 이후 호출(추가질문): 상담 메시지처럼 과금.
    """
    row = db.get(CompatibilitySession, compat_id)
    if row is None:
        raise KeyError(compat_id)
    if row.user_id is not None and (user is None or user.id != row.user_id):
        raise PermissionError("not your compatibility session")

    s = get_settings()
    depth = "deep" if depth == "deep" else "basic"
    message = (message or "").strip()

    locale = getattr(row, "locale", "ko")   # 세션 확정 로케일 — 응답 언어·모델 선택(chat 미러)
    result = CompatResult.model_validate(row.result_json or {})
    chart_a = SajuChart.model_validate(row.a_chart_json or {})
    chart_b = SajuChart.model_validate(row.b_chart_json or {})
    sa = chat_service._build_saju_summary(chart_a, locale=locale)
    sb = chat_service._build_saju_summary(chart_b, locale=locale)
    la, lb = row.a_label or "사람 A", row.b_label or "사람 B"
    brief = _render_result_for_llm(result, la, lb, sa, sb, locale)

    dialect = (getattr(user, "answer_dialect", None) or "standard") if user else "standard"
    di = chat_service._dialect_instruction(dialect)

    has_assistant = any(m.role == "assistant" for m in row.messages)
    is_explain = not has_assistant

    # ---- 내부 RAG(학습 코퍼스) — 사주와 동일하게 기본·심화 모두 활용 ----
    rag_query = _rag_query(result, chart_a, chart_b, message)
    chunks = chat_service.retrieve_for_menu(
        rag_query, depth, session_id=compat_id, question=(message or None), menu="compat"
    )
    rag_ctx = chat_service.rag_context_block(chunks)

    if is_explain:
        # 해설: create 차감에 포함 → 추가 무과금. preview는 세션값 사용.
        is_preview = row.is_preview
        billing_mode = "compat_explain"
        credits_to_charge = 0
        use_free = use_daily = use_mem = False
        sys_content = chat_service._compose_sys_content(
            COMPAT_SYSTEM, dialect, explain_level, has_sources=bool(rag_ctx), locale=locale)
        ucontent = brief if not rag_ctx else f"{brief}\n\n[참고자료]\n{rag_ctx}"
        # P1-4: 자료에 남의 명식이 섞여 와도 두 사람 명식으로 쓰지 않게(chat 전용 가드를 이식)
        if rag_ctx:
            for _lbl, _cj in (("A", getattr(row, "a_chart_json", None)),
                              ("B", getattr(row, "b_chart_json", None))):
                _cr = chat_service.chart_reconfirm_block(_cj)
                if _cr:
                    ucontent += f"\n\n[{_lbl}] {_cr}"
        msgs = [{"role": "system", "content": sys_content}, {"role": "user", "content": ucontent}]
        save_user: str | None = None
    else:
        if not message:
            # [운영자 승인 2026-08-05] 해설이 이미 저장된 세션에 빈 메시지(복원 화면 '설명' 클릭·구프론트)가
            #   오면 에러 대신 저장 해설 '재전송'(멱등·무과금). 종전엔 "질문을 입력해 주세요" → 청크 0개 →
            #   프론트가 "해설 생성이 지연"으로 오표시(신년운세 F1과 동일 결함). 궁합도 동일하게 봉합.
            _prev = next((m for m in reversed(row.messages) if m.role == "assistant"), None)
            if _prev and (_prev.content or "").strip():
                _locked = _prev.is_preview and not _prev.preview_revealed
                _content = chat_service._make_preview(_prev.content) if _locked else _prev.content
                _content = chat_service.fix_term_hanja(_content)
                yield ("meta", {"billing_mode": "compat_explain_replay", "is_preview": _locked,
                                "mode": "explain", "will_refine": False})
                for _seg in _content.split("\n\n"):
                    if _seg.strip():
                        yield ("chunk", {"text": _seg + "\n\n"})
                yield ("done", {"assistant_message_id": _prev.id, "content": _content,
                                "is_preview": _locked, "preview_revealed": not _locked,
                                "full_length": len(_content), "preview_length": len(_content),
                                "credits_charged": 0,
                                "balance_after": (auth_service.get_balance(db, user.id) if user else None),
                                "billing_mode": "compat_explain_replay", "refined": False, "flash": False})
                return
            yield ("error", {"detail": "질문을 입력해 주세요."})
            return
        # 프리미엄 메뉴 추가질문: 무료한도 미적용(항상 1,000/3,000P 차감)
        bill = chat_service._decide_billing(db, user, depth, allow_free_quota=False, claim=True)
        is_preview = bill["is_preview"]
        credits_to_charge = bill["credits_to_charge"]
        billing_mode = bill["billing_mode"]
        use_free = bill["use_free_quota"]
        use_daily = bill["use_daily_free"]
        use_mem = bill["use_membership"]
        # free-ride 차단: 추가질문 유료차감·멤버십 선점을 '생성 전' 확정 커밋(끝 커밋은 disconnect 시 롤백됨).
        _pre_charged = chat_service.precharge_followup(db, user, bill, reason="compatibility_q", ref_id=compat_id)
        # 미정산 청구 등록 — 아래 방어분기를 벗어난 예외가 나면 래퍼(stream_message)가 이걸 보고 보상한다.
        if _receipt is not None and not is_explain:
            _receipt.update(bill=bill, pre_charged=_pre_charged)
        # [2026-07-25] 후속질문(else=has_assistant)에 question·is_followup 전달 — 종전 미전달로 주제집중
        # 라우팅/추가질문 규칙이 빠져 종합템플릿이 주입되던 동문서답 재발원 봉합(chat과 동일 결함).
        sys_content = chat_service._compose_sys_content(
            COMPAT_SYSTEM + COMPAT_FOLLOWUP_HINT, dialect, explain_level,
            question=message, is_followup=True, has_sources=bool(rag_ctx), locale=locale
        )
        analysis = f"[궁합 분석]\n{brief}" + (f"\n\n[참고자료]\n{rag_ctx}" if rag_ctx else "")
        if rag_ctx:                                  # P1-4 명식 가드(두 사람 각각)
            for _lbl, _cj in (("A", getattr(row, "a_chart_json", None)),
                              ("B", getattr(row, "b_chart_json", None))):
                _cr = chat_service.chart_reconfirm_block(_cj)
                if _cr:
                    analysis += f"\n\n[{_lbl}] {_cr}"
        # 메뉴 이탈 질문(올해 세운/특정 날짜) 대비 — 현재 세운/월운 + 질문날짜 간지 주입(두 명식은 brief에 이미 있음)
        _aux = chat_service._aux_ganji_blocks(message, include_summary=False)
        if _aux:
            analysis = f"{analysis}\n\n{_aux}"
        # 시기 질문(전수감사 Phase 3): "결혼 시기 몇 월?"(기본 칩) 등에서 세운·월운↔'두 명식' 관계가
        # 전무해 반합·삼합을 LLM이 자력 도출(환각 표면). 두 사람 각각 결정적으로 계산해 주입.
        _tb = _timing_relations_block(message, getattr(row, "a_chart_json", None),
                                      getattr(row, "b_chart_json", None),
                                      row.a_label or "A", row.b_label or "B")
        if _tb:
            analysis = f"{analysis}\n\n{_tb}"
        msgs = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": analysis},
        ]
        for m in [mm for mm in row.messages if mm.role in ("user", "assistant")][-12:]:
            msgs.append({"role": m.role, "content": m.content})
        msgs.append({"role": "user", "content": message})
        save_user = message

    _claude_avail = (
        settings_service.get_bool(db, "external_llm_enabled", True)
        and external_llm.is_enabled()
    )
    do_qwen = (not is_preview) and s.deep_local_refine_enabled          # 1차 내부 보강(기본·심화)
    do_claude = depth == "deep" and (not is_preview) and _claude_avail  # 심화 외부 보강
    will_refine = do_qwen or do_claude

    yield ("meta", {
        "billing_mode": billing_mode,
        "is_preview": is_preview,
        "depth": depth,
        "mode": "explain" if is_explain else "followup",
        "will_refine": will_refine,
    })

    # ---- 1차 토큰 스트리밍 (하트비트 + 미리보기 컷) ----
    parts: list[str] = []
    tok_q: "_queue.Queue[Any]" = _queue.Queue()
    _SENTINEL = object()
    _err: dict[str, Exception] = {}
    stop_event = threading.Event()  # 클라 이탈 시 메인 Ollama producer 조기 종료

    def _produce() -> None:
        try:
            for tok in chat_service._stream_ollama(
                msgs, model=chat_service._draft_model(locale), stop_event=stop_event
            ):
                tok_q.put(tok)
        except Exception as e:  # noqa: BLE001
            _err["e"] = e
        finally:
            tok_q.put(_SENTINEL)

    threading.Thread(target=_produce, daemon=True).start()

    _pmax = settings_service.get_cached_int("preview_max_chars", s.preview_max_chars)  # 관리자 설정 반영(사주 chat 과 통일)
    preview_chars = 0
    cut_sent = False
    _dg_since = 0   # 반복 퇴행 조기중단 카운터
    _degen_aborted = False   # 조기중단 발동 여부 — 발동 시 최종본 강제 재생성(잘린 답 저장 방지)
    # 클라 이탈(GeneratorExit) 시 finally 가 stop_event 를 set → 고아 추론 차단.
    try:
        while True:
            try:
                item = tok_q.get(timeout=s.sse_heartbeat_sec)
            except _queue.Empty:
                yield ("ping", {})
                continue
            if item is _SENTINEL:
                break
            parts.append(item)
            # 반복 퇴행 조기중단 — 꼬리 폭주 시 생성 끊기(최종본은 _correct_degenerate 가 교정/환불)
            _dg_since += 1
            if _dg_since >= 40:
                _dg_since = 0
                _acc = "".join(parts)
                if len(_acc) >= 240 and chat_service._stream_is_degenerating(_acc[-400:]):
                    _degen_aborted = True
                    stop_event.set()
                    break
            if is_preview:
                if not cut_sent:
                    remaining = _pmax - preview_chars
                    if remaining > 0:
                        send = item[:remaining]
                        preview_chars += len(send)
                        if send:
                            yield ("chunk", {"text": send})
                    if preview_chars >= _pmax:
                        cut_sent = True
                        yield ("cut", {"reason": "preview_limit"})
            else:
                yield ("chunk", {"text": item})
    finally:
        stop_event.set()

    # ---- 1차 로컬(qwen3:14b) 실패 → 외부(Claude) 폴백 (사주와 동일) ----
    local_ok = "e" not in _err
    if not local_ok:
        e = _err["e"]
        fb = None
        if not is_preview:
            fb = chat_service.external_fallback_answer(
                question=(message or f"{la}와 {lb}의 궁합 해설"),
                evidence=brief, rag_context=rag_ctx, dialect_instruction=di or None,
                saju_summary=f"{sa}\n\n{sb}", locale=locale,
            )
        if fb:
            parts = [fb]
            yield ("refine", {"text": fb, "reason": "로컬 엔진 불가 — 외부 AI 폴백"})
        elif isinstance(e, chat_service.ServiceUnavailableError):
            if not is_explain:   # explain 은 입장료 커버(precharge 안 함) — bill/_pre_charged 미정의라 환불도 하지 않음
                chat_service.refund_followup(db, user, bill, _pre_charged, reason="compatibility_q", ref_id=compat_id)
                if _receipt is not None: _receipt.clear()   # 자체 환불 완료 — 래퍼의 이중환불 차단
            yield ("error", {"detail": str(e), "code": "service_unavailable"})
            return
        else:
            if not is_explain:
                chat_service.refund_followup(db, user, bill, _pre_charged, reason="compatibility_q", ref_id=compat_id)
                if _receipt is not None: _receipt.clear()   # 자체 환불 완료 — 래퍼의 이중환불 차단
            yield ("error", {"detail": f"stream error: {type(e).__name__}: {e}"})
            return

    answer_full = "".join(parts)
    refined = False

    _q = (message or f"{la}와 {lb}의 궁합 해설")
    _ss = f"{sa}\n\n{sb}"
    # ---- ① 내부 qwen 보강 (기본·심화 공통, 로컬 1차 정상) ----
    if do_qwen and local_ok and answer_full.strip():
        yield ("stage", {"phase": "draft_done"})
        yield ("stage", {"phase": "refining"})
        qb = None
        for ev in chat_service._bg_with_heartbeat(s, lambda af=answer_full: chat_service._refine_with_qwen(
                question=_q, draft=af, saju_summary=_ss, evidence=brief,
                rag_context=rag_ctx, dialect_instruction=di or None, locale=locale), progress_phase="refining"):
            if ev[0] == "result":
                qb = ev[1]
            else:
                yield ev
        if qb:
            answer_full = qb.strip()
            refined = True
            yield ("refine", {"text": answer_full, "reason": "내부 보강(qwen)"})
        yield ("stage", {"phase": "refine_done"})

    # ---- ② 외부 Claude 보강 (심화 전용, qwen 다음) ----
    if do_claude and local_ok and answer_full.strip():
        yield ("stage", {"phase": "refining"})
        cb = None
        for ev in chat_service._bg_with_heartbeat(s, lambda af=answer_full: chat_service._claude_boost(
                question=_q, draft=af, saju_summary=_ss, evidence=brief,
                rag_context=rag_ctx, dialect_instruction=di or None, locale=locale), progress_phase="refining"):
            if ev[0] == "result":
                cb = ev[1]
            else:
                yield ev
        if cb:
            answer_full = cb.strip()
            refined = True
            yield ("refine", {"text": answer_full, "reason": "심화 검증·보강(Claude)"})
        yield ("stage", {"phase": "refine_done"})

    # ---- 분량 백스톱(유료 메뉴 — 운영자 지시: 돈 받는 메뉴가 빈약하면 안 됨. 실측 889자) ----
    # [2026-07-31] 첫 해설(is_explain, 종합)은 3,000(심화 3,500)로 상향. [패딩 검수 반영] 추가질문
    #  (is_explain=False)은 단일주제라 낮은 안전바닥(1,500/1,800)만 — 강제 재생성 패딩 방지.
    #  _safe_replace(1.0)로 더 길고 완결일 때만 채택 + 확장은 '새 내용만'(부연·복붙 금지) 요구.
    if is_explain:
        _min_c = 3500 if depth == "deep" else 3000
    else:
        _min_c = 1800 if depth == "deep" else 1500
    if local_ok and answer_full.strip() and len(answer_full) < _min_c:
        yield ("stage", {"phase": "refining"})
        _expand_user = (
            f"{brief}\n\n[이전 답변]\n{answer_full}\n\n"
            f"[지시] 이전 답변이 {len(answer_full)}자로 너무 짧습니다(유료 리포트 최소 {_min_c}자). "
            "같은 구성과 같은 사실을 유지한 채 다섯 요소·관법별 종합·조언을 각각 훨씬 풍부하게 다시 "
            "작성하되, 이전 답변의 문장·논점을 반복·부연·복붙하지 말고 아직 다루지 않은 새 내용만 더하세요"
            "(도입·결론 복붙 금지). "
            "★[궁합 분석]에 없는 합·충·신살·간지·점수는 절대 추가하지 마세요."
        )
        def _expand_call(_u=_expand_user, _sc=sys_content):
            try:
                return chat_service._call_ollama(
                    [{"role": "system", "content": _sc}, {"role": "user", "content": _u}],
                    num_predict=5120)
            except Exception:  # noqa: BLE001 — 확장 실패 시 원본 유지
                return None
        _exp = None
        for ev in chat_service._bg_with_heartbeat(s, _expand_call, progress_phase="refining"):
            if ev[0] == "result":
                _exp = ev[1]
            else:
                yield ev
        _expc = chat_service._safe_replace(answer_full, _exp, min_ratio=1.0, hard_floor=True)  # 더 길고 완결일 때만
        if _expc and len(_expc) > len(answer_full):
            answer_full = chat_service.fix_term_hanja(_expc)
            refined = True
            yield ("refine", {"text": answer_full, "reason": "분량 보강(유료 리포트 기준)"})
        yield ("stage", {"phase": "refine_done"})

    # ---- 명식 정합성 검증·교정 (절대규칙) — 답변의 4주 지지가 두 명식(union)에 없으면 교정 ----
    if not is_preview and answer_full.strip():
        _a_cj, _b_cj = getattr(row, "a_chart_json", None), getattr(row, "b_chart_json", None)
        _allow = chat_service._allowed_from_charts(_a_cj, _b_cj)
        _stems = {st for st in (chat_service._day_stem(_a_cj), chat_service._day_stem(_b_cj)) if st}
        # 지지(union) + 일간(두 사람 union) 동시 검증
        if chat_service._verify_branches(answer_full, _allow) or chat_service._verify_day_stem_multi(answer_full, _stems):
            yield ("stage", {"phase": "verifying"})
            _truth = chat_service._charts_truth([(la, _a_cj), (lb, _b_cj)])
            _fixed = None
            for ev in chat_service._bg_with_heartbeat(s, lambda af=answer_full: chat_service._correct_branches(
                    af, allowed=_allow, truth=_truth, question=_q, sys_content=sys_content,
                    saju_summary=_ss, day_stems=_stems)):
                if ev[0] == "result":
                    _fixed = ev[1]
                else:
                    yield ev
            if _fixed and _fixed.strip() and _fixed.strip() != answer_full:
                answer_full = _fixed.strip()
                refined = True
                yield ("refine", {"text": answer_full, "reason": "명식 정합성 자동 교정"})
        # 자료 인용 말투 제거(전문가 화법)
        _scrubbed = chat_service._scrub_self_reference(chat_service._scrub_source_refs(answer_full))
        if _scrubbed and _scrubbed != answer_full:
            answer_full = _scrubbed
            refined = True
            yield ("refine", {"text": answer_full, "reason": "표현 정리"})
        # 십성 등 한자 병기 정자(正字) 교정(전문가 지적)
        _h = chat_service.fix_term_hanja(answer_full)
        if _h != answer_full:
            answer_full = _h
            refined = True
            yield ("refine", {"text": answer_full, "reason": "한자 표기 정정"})

    # 미리보기 등 위 분기를 안 탄 경로까지 저장/재로드본 일관 교정(멱등).
    answer_full = chat_service.fix_term_hanja(answer_full)
    # 구분선(---)·과다 빈줄 정리 — 상담(chat)과 통일(무손실·헤딩 보존).
    answer_full = chat_service._tidy_markdown(answer_full)

    # 반복 퇴행(같은 구절 폭주) 최종 가드 — 구제되면 정상본, 구제 실패면 ''(→ 아래 빈답변 경로로 미저장·환불/재시도)
    # 조기중단(_degen_aborted)으로 끊긴 잘린 답은 보수적 판정에 안 걸려도 강제 재생성(force)한다.
    if answer_full.strip() and (_degen_aborted or chat_service._looks_degenerate(answer_full)):
        # [2026-08-04 퀵윈] 동기 직호출 → 하트비트 랩: 구제 재생성(최대 수 분)이 SSE 완전 무음이라
        # CF 100s 컷으로 유료 스트림이 죽던 '무음사망' 차단(운영자 지시) — 신년운세와 동일 패턴.
        _fixed = None
        for ev in chat_service._bg_with_heartbeat(s, lambda af=answer_full: chat_service._correct_degenerate(
                af, sys_content=sys_content, base_user=msgs[1]["content"], force=_degen_aborted),
                progress_phase="verifying"):
            if ev[0] == "result":
                _fixed = (ev[1] or "").strip() if ev[1] is not None else None
            else:
                yield ev
        if _fixed is not None and _fixed != answer_full:
            answer_full = _fixed
            if answer_full:
                refined = True
                yield ("refine", {"text": answer_full, "reason": "반복 정리"})

    # 빈 응답(무내용 또는 구제 불가 퇴행) — 유료 followup 이면 precharge 보상, explain 은 저장 않고 에러(재시도 유도).
    # ⚠️ explain 은 입장료가 create 에서 차감됨 — 재시도(무과금)로 정상본을 받으므로 여기서 재환불하지 않는다(이중환불 위험).
    if not answer_full.strip():
        if not is_explain:
            chat_service.refund_followup(db, user, bill, _pre_charged, reason="compatibility_q", ref_id=compat_id)
            if _receipt is not None: _receipt.clear()   # 자체 환불 완료 — 래퍼의 이중환불 차단
        yield ("error", {"detail": "답변을 생성하지 못했어요. 잠시 후 다시 시도해 주세요.", "code": "internal_error"})
        return

    # ---- 잔액 조회 (차감·선점은 precharge_followup 에서 '생성 전' 완료됨 — 여기서 이중차감 금지) ----
    balance_after: int | None = auth_service.get_balance(db, user.id) if user is not None else None

    # ---- 영속 ----
    now = datetime.utcnow()
    try:
        if save_user is not None:
            db.add(CompatibilityMessage(
                compat_id=compat_id, role="user", content=save_user, created_at=now,
                is_preview=False, preview_revealed=True, credits_charged=0,
            ))
        assistant = CompatibilityMessage(
            compat_id=compat_id, role="assistant", content=answer_full,
            created_at=datetime.utcnow(), is_preview=is_preview, preview_revealed=not is_preview,
            credits_charged=credits_to_charge,
        )
        db.add(assistant)
        db.flush()
        aid = assistant.id
        if not is_explain:                       # 유료 추가질문만 영수증 대상 — EOF 완결 마킹(persist 커밋에 합류)
            from backend.app.services import receipt_service
            receipt_service.finalize_receipt(db, bill.get("receipt_id"), message_id=aid)
        db.commit()
    except Exception:  # noqa: BLE001 — 저장/커밋 실패 시 생성 전 확정한 과금을 보상 원복.
        db.rollback()
        if not is_explain:
            chat_service.refund_followup(db, user, bill, _pre_charged, reason="compatibility_q", ref_id=compat_id)
            if _receipt is not None: _receipt.clear()   # 자체 환불 완료 — 래퍼의 이중환불 차단
        yield ("error", {"detail": "저장 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", "code": "internal_error"})
        return

    visible_len = len(chat_service._make_preview(answer_full)) if is_preview else len(answer_full)
    yield ("done", {
        "assistant_message_id": aid,
        # [2026-08-04 퀵윈] 최종 표시본 — 무음 교정(한자·tidy) 반영본으로 화면 재동기화(chat done.content
        #   규약과 동일, 화면=DB). 미리보기는 _make_preview 마스킹 통과라 유출 없음.
        "content": (chat_service._make_preview(answer_full) if is_preview else answer_full),
        "is_preview": is_preview,
        "preview_revealed": not is_preview,
        "full_length": len(answer_full),
        "preview_length": visible_len,
        "credits_charged": credits_to_charge,
        "balance_after": balance_after,
        "billing_mode": billing_mode,
        "refined": refined,
        "flash": not is_preview,
    })


# ── 후속 추천질문 (사주와 동일 — 해설/추가질문 아래 칩으로 노출, 추가 상담 유도) ──
_COMPAT_FALLBACK = [
    "두 사람 결혼 시기는 언제가 좋나요?", "갈등을 줄이려면 어떻게 할까요?",
    "재물·금전 궁합은 어떤가요?", "자녀운은 어떤가요?",
    "성격 차이를 조율하는 법은?", "올해 두 사람 관계운은?",
]


def generate_compat_suggestions(db: Session, compat_id: str, n: int = 6) -> list[str]:
    """궁합 해설 맥락으로 후속 추천질문 n개(로컬 LLM, 무과금)."""
    row = db.get(CompatibilitySession, compat_id)
    if row is None:
        return []
    msgs = [m for m in row.messages if m.role in ("user", "assistant")]
    if not msgs:
        return _COMPAT_FALLBACK[:n]
    parts = [f"{'질문' if m.role == 'user' else '답변'}: {(m.content or '')[:400]}" for m in msgs[-4:]]
    return chat_service.suggestions_from_convo("\n".join(parts), n, topic="궁합 상담", fallback=_COMPAT_FALLBACK)


# ============================================================
# 평균 집계 — '전체 평균' 펜타곤/게이지 오버레이 (점3)
# ============================================================
def get_average(db: Session) -> dict[str, Any]:
    """궁합 본 사람들의 요소점수·관법총점 평균. 표본이 적으면 average=None."""
    min_n = settings_service.get_int(db, "compat_avg_min_samples") or 5
    row = db.execute(
        select(
            func.count(CompatibilitySession.compat_id),
            func.avg(CompatibilitySession.f_day_branch),
            func.avg(CompatibilitySession.f_day_stem),
            func.avg(CompatibilitySession.f_wuxing),
            func.avg(CompatibilitySession.f_ten_god),
            func.avg(CompatibilitySession.f_sinsal),
            func.avg(CompatibilitySession.total_a),
            func.avg(CompatibilitySession.total_b),
            func.avg(CompatibilitySession.total_c),
        )
    ).one()
    n = int(row[0] or 0)
    if n < min_n:
        return {"count": n, "min_samples": min_n, "average": None}

    def _r(v) -> float | None:
        return round(float(v), 1) if v is not None else None

    return {
        "count": n,
        "min_samples": min_n,
        "average": {
            "factors": {
                "day_branch": _r(row[1]), "day_stem": _r(row[2]), "wuxing": _r(row[3]),
                "ten_god": _r(row[4]), "sinsal": _r(row[5]),
            },
            "totals": {"A": _r(row[6]), "B": _r(row[7]), "C": _r(row[8])},
        },
    }
