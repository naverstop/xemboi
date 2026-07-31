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
COMPAT_SYSTEM = """당신은 한국 명리학(사주팔자) 궁합 전문 상담사입니다.

원칙:
1. 아래 [궁합 분석]은 규칙 엔진이 계산한 객관적 근거(일간·일지 합충, 오행 상호보완, 십성, 신살)입니다. 이 근거에 기반해 해설하세요.
2. 궁합 관법은 학파마다 다릅니다. 제시된 세 관점(결혼·부부궁 / 균형 / 연애·끌림)을 존중하고, 한쪽이 정답이라 단정하지 마세요.
3. 길흉을 단정하지 말고, 강점 → 주의점 → 관계 조언 흐름으로 설명하세요.
4. 도화 등 해석이 갈리는 항목은 여러 관점을 함께 소개하세요.
5. 한국어로, 한자 술어는 한글(한자) 형식으로 표기하세요. 예: 정관(正官), 육합(六合).
6. A4 약 70%(최소 1,200자) 분량으로 충분히 설명하세요.
"""

COMPAT_FOLLOWUP_HINT = (
    "\n[추가 질문 안내] 사용자가 위 궁합 분석에 대해 추가로 묻습니다. "
    "분석 근거(합·충·오행·십성·신살)와 이전 대화를 토대로, 질문에 구체적으로 답하세요."
)

_FACTOR_LABEL = {
    "day_branch": "일지(부부궁)",
    "day_stem": "일간(천간합)",
    "wuxing": "오행 상호보완",
    "ten_god": "십성(정재·정관)",
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
    result: CompatResult, label_a: str, label_b: str, sa: str, sb: str
) -> str:
    parts = [f"[{label_a} 명식]\n{sa}", f"[{label_b} 명식]\n{sb}", "[궁합 분석]"]
    for key, f in result.factors.items():
        # f.label 은 엔진이 로케일에 맞춰 산출(ko 는 _FACTOR_LABEL 와 동일) → vi 브리핑도 로케일 일관.
        line = f"- {f.label}: {f.score}점"
        if f.items:
            line += " | " + "; ".join(it.detail for it in f.items)
        parts.append(line)
    if result.penalties:
        parts.append("[주의 요소] " + ", ".join(f"{p.type}({p.detail})" for p in result.penalties))
    parts.append("[관법별 종합]")
    for k, p in result.perspectives.items():
        parts.append(f"- {p.label}: {p.total}점 ({p.grade})")
    if result.dohwa_readings:
        parts.append("[도화 해석(여러 관점)] " + " / ".join(result.dohwa_readings))
    parts.append(
        f"\n위 근거로 {label_a}와 {label_b}의 궁합을 강점→주의점→조언 흐름으로 해설하세요."
    )
    return "\n".join(parts)


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

    result = CompatResult.model_validate(row.result_json or {})
    chart_a = SajuChart.model_validate(row.a_chart_json or {})
    chart_b = SajuChart.model_validate(row.b_chart_json or {})
    sa = chat_service._build_saju_summary(chart_a)
    sb = chat_service._build_saju_summary(chart_b)
    la, lb = row.a_label or "사람 A", row.b_label or "사람 B"
    brief = _render_result_for_llm(result, la, lb, sa, sb)

    dialect = (getattr(user, "answer_dialect", None) or "standard") if user else "standard"
    di = chat_service._dialect_instruction(dialect)
    locale = getattr(row, "locale", "ko")   # 세션 확정 로케일 — 응답 언어·모델 선택(chat 미러)

    has_assistant = any(m.role == "assistant" for m in row.messages)
    is_explain = not has_assistant

    # ---- 내부 RAG(학습 코퍼스) — 사주와 동일하게 기본·심화 모두 활용 ----
    rag_query = (f"{message}\n{brief}" if message else brief)[:600]
    chunks = chat_service.retrieve_for_menu(
        rag_query, depth, session_id=compat_id, question=(message or None)
    )
    rag_ctx = chat_service.rag_context_block(chunks)

    if is_explain:
        # 해설: create 차감에 포함 → 추가 무과금. preview는 세션값 사용.
        is_preview = row.is_preview
        billing_mode = "compat_explain"
        credits_to_charge = 0
        use_free = use_daily = use_mem = False
        sys_content = chat_service._compose_sys_content(COMPAT_SYSTEM, dialect, explain_level, locale)
        ucontent = brief if not rag_ctx else f"{brief}\n\n[참고자료]\n{rag_ctx}"
        msgs = [{"role": "system", "content": sys_content}, {"role": "user", "content": ucontent}]
        save_user: str | None = None
    else:
        if not message:
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
        sys_content = chat_service._compose_sys_content(
            COMPAT_SYSTEM + COMPAT_FOLLOWUP_HINT, dialect, explain_level, locale
        )
        analysis = f"[궁합 분석]\n{brief}" + (f"\n\n[참고자료]\n{rag_ctx}" if rag_ctx else "")
        # 메뉴 이탈 질문(올해 세운/특정 날짜) 대비 — 현재 세운/월운 + 질문날짜 간지 주입(두 명식은 brief에 이미 있음)
        _aux = chat_service._aux_ganji_blocks(message, include_summary=False)
        if _aux:
            analysis = f"{analysis}\n\n{_aux}"
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

    preview_chars = 0
    cut_sent = False
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
            if is_preview:
                if not cut_sent:
                    remaining = s.preview_max_chars - preview_chars
                    if remaining > 0:
                        send = item[:remaining]
                        preview_chars += len(send)
                        if send:
                            yield ("chunk", {"text": send})
                    if preview_chars >= s.preview_max_chars:
                        cut_sent = True
                        yield ("cut", {"reason": "preview_limit"})
            else:
                yield ("chunk", {"text": item})
    finally:
        stop_event.set()

    # ---- 1차 로컬(exaone) 실패 → 외부(Claude) 폴백 (사주와 동일) ----
    local_ok = "e" not in _err
    if not local_ok:
        e = _err["e"]
        fb = None
        if not is_preview:
            fb = chat_service.external_fallback_answer(
                question=(message or f"{la}와 {lb}의 궁합 해설"),
                evidence=brief, rag_context=rag_ctx, dialect_instruction=di or None,
                saju_summary=f"{sa}\n\n{sb}",
            )
        if fb:
            parts = [fb]
            yield ("refine", {"text": fb, "reason": "로컬 엔진 불가 — 외부 AI 폴백"})
        elif isinstance(e, chat_service.ServiceUnavailableError):
            yield ("error", {"detail": str(e), "code": "service_unavailable"})
            return
        else:
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
                rag_context=rag_ctx, dialect_instruction=di or None, locale=locale)):
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
                rag_context=rag_ctx, dialect_instruction=di or None)):
            if ev[0] == "result":
                cb = ev[1]
            else:
                yield ev
        if cb:
            answer_full = cb.strip()
            refined = True
            yield ("refine", {"text": answer_full, "reason": "심화 검증·보강(Claude)"})
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
        _scrubbed = chat_service._scrub_source_refs(answer_full)
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

    # ---- 차감/무료 갱신 (추가질문만) ----
    balance_after: int | None = None
    if user is not None:
        # 무료/멤버십 카운터는 _decide_billing(claim=True)에서 원자적으로 선점됨 — 여기서 미증가.
        if credits_to_charge > 0:
            balance_after = auth_service.adjust_credit(
                db, user.id, -credits_to_charge, reason="compatibility_q", ref_id=compat_id
            )
        else:
            balance_after = auth_service.get_balance(db, user.id)

    # ---- 영속 ----
    now = datetime.utcnow()
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
    db.commit()

    visible_len = len(chat_service._make_preview(answer_full)) if is_preview else len(answer_full)
    yield ("done", {
        "assistant_message_id": aid,
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
