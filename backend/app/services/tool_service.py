"""명리 도구 서비스 — 작명/개명/아호/택일. 생성(엔진+상담쿼터 차감+영속) + 스트리밍 해설.

빌링은 chat_service._decide_billing 공유(상담 쿼터). 해설은 스트리밍 엔드포인트에서 생성
(첫 호출=무과금, 추가질문=과금). 궁합(compat_service)과 동일 구조.
"""
from __future__ import annotations

import queue as _queue
import threading
import uuid
from datetime import date as date_t, datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.domain.chat_dto import BirthDTO
from backend.app.repositories.auth_models import User
from backend.app.repositories.models import ToolMessage, ToolSession
from backend.app.saju import naming as naming_engine
from backend.app.saju import taekil as taekil_engine
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput
from backend.app.services import auth_service, chat_service, external_llm, settings_service

NAMING_SYSTEM = """당신은 한국 성명학(작명) 전문가입니다.
아래 [분석]은 규칙 엔진이 계산한 객관적 근거(수리 81수·자원오행·발음오행·음양)입니다.
- 관법은 학파마다 다르니 단정하지 말고 여러 관점을 존중하세요.
- 길흉 단정을 피하고, 강점→유의점→추천/조언 흐름으로 설명하세요.
- 한국어로, 한자 술어는 한글(한자)로 표기하세요.
- A4 약 70%(최소 1,000자) 분량으로 충분히 설명하세요.
"""

TAEKIL_SYSTEM = """당신은 한국 택일(좋은 날 고르기) 전문가입니다.
아래 [분석]은 규칙 엔진이 계산한 근거(황도흑도·본인 사주 충형 회피·손없는날)입니다.
- 관법은 학파마다 다르니 단정하지 말고 여러 관점을 존중하세요.
- 추천 길일의 이유와 피해야 할 날을 강점→유의점→조언 흐름으로 설명하세요.
- 한국어로, 한자 술어는 한글(한자)로 표기하세요. A4 약 70%(최소 1,000자).
"""


def _to_birth_input(b: BirthDTO, locale: str = "ko") -> BirthInput:
    # locale 은 요청 로케일(get_locale) 단일 진실원 — vi 면 105°E·hongoc_duc 경로.
    return BirthInput(
        birth_date=b.birth_date, birth_time=b.birth_time, calendar=b.calendar,
        is_leap_month=b.is_leap_month, gender=b.gender,
        apply_true_solar_time=b.apply_true_solar_time,
        birth_longitude=b.birth_longitude,
        apply_equation_of_time=b.apply_equation_of_time,
        night_zi_mode=b.night_zi_mode,
        locale=locale,
    )


def _mask_preview_result(result: dict | None) -> dict | None:
    """비로그인 미리보기(is_preview): 핵심 산출물(작명 후보·택일 길일/회피일)을 일부만 노출.
    입장료를 안 낸 익명 사용자가 프리미엄 상품 전량을 무료 취득(입장료 우회)하는 것을 서버단에서 차단.
    DB엔 전체가 저장되며 반환값만 마스킹(작명/택일에만 작용 — 궁합 등 다른 result 구조엔 무영향)."""
    if not isinstance(result, dict):
        return result
    n = 3
    r = dict(result)
    locked = 0
    if isinstance(r.get("candidates"), list) and len(r["candidates"]) > n:
        locked += len(r["candidates"]) - n
        r["candidates"] = r["candidates"][:n]
    if isinstance(r.get("best"), list) and len(r["best"]) > n:
        locked += len(r["best"]) - n
        r["best"] = r["best"][:n]
    if isinstance(r.get("avoid"), list) and len(r["avoid"]) > 1:
        r["avoid"] = r["avoid"][:1]
    if locked:
        r["preview_locked"] = locked
        r["is_preview"] = True
    return r


def _persist_and_bill(
    db: Session, tool: str, kind: str, birth: BirthDTO, chart, input_json: dict,
    result_json: dict, user: User | None, depth: str, locale: str = "ko",
) -> dict[str, Any]:
    """입장료 차감(생성=입장) + 세션 영속. tool_id/billing 반환.

    프리미엄 5개 메뉴 정책: 생성 시 메뉴별 입장료(entry_cost_*)를 1회 차감.
    menu 키: 작명=jakmyeong / 개명=gaemyeong / 아호=aho / 택일=taekil.
    """
    menu = kind if tool == "naming" else "taekil"
    bill = chat_service._decide_entry_billing(db, user, menu, claim=True)
    is_preview = bill["is_preview"]
    credits = bill["credits_to_charge"]
    tid = uuid.uuid4().hex
    balance_after = None
    if user is not None:
        # 무료/멤버십 카운터는 _decide_entry_billing(claim=True)에서 원자적으로 선점됨 — 여기서 미증가.
        if credits > 0:
            balance_after = auth_service.adjust_credit(db, user.id, -credits, reason=tool, ref_id=tid)
        else:
            balance_after = auth_service.get_balance(db, user.id)
    row = ToolSession(
        tool_id=tid, tool=tool, kind=kind, user_id=user.id if user else None,
        locale=locale,
        birth_date=birth.birth_date, birth_time=birth.birth_time,
        calendar=birth.calendar.value if hasattr(birth.calendar, "value") else str(birth.calendar),
        is_leap_month=birth.is_leap_month,
        gender=birth.gender.value if hasattr(birth.gender, "value") else str(birth.gender),
        apply_true_solar_time=birth.apply_true_solar_time,
        chart_json=chart.model_dump(mode="json"),
        input_json=input_json, result_json=result_json,
        is_preview=is_preview, credits_charged=credits,
    )
    db.add(row)
    db.commit()
    return {
        "tool_id": tid, "tool": tool, "kind": kind,
        "result": _mask_preview_result(result_json) if is_preview else result_json,
        "is_preview": is_preview, "billing_mode": bill["billing_mode"],
        "credits_charged": credits, "balance_after": balance_after, "explain": "",
    }


# ── 생성 ──────────────────────────────────────────────────────
def create_naming(
    db: Session, kind: str, birth: BirthDTO, surname: str | None,
    current_name: str | None, user: User | None = None, depth: str = "deep",
    reading: str | None = None, locale: str = "ko",
) -> dict[str, Any]:
    chart = build_chart(_to_birth_input(birth, locale=locale))
    if kind == "gaemyeong":
        name = (current_name or "").strip()
        if len(name) < 2:
            raise ValueError("current_name required: 현재 이름(한자 2자 이상)이 필요합니다.")
        sur, given = name[0], name[1:]
        analysis = naming_engine.analyze_name(sur, given, chart, reading=reading)
        result = {"kind": kind, "analysis": analysis.model_dump(mode="json"),
                  "deficient": naming_engine._deficient_elements(chart)}
        input_json = {"current_name": name}
    else:  # jakmyeong | aho
        sur = (surname or "").strip() if kind == "jakmyeong" else ""
        if kind == "jakmyeong" and not sur:
            raise ValueError("surname required: 작명에는 한자 성(姓)이 필요합니다.")
        cands = naming_engine.recommend_names(sur, chart, top=40, gender=str(birth.gender))
        result = {"kind": kind, "surname": sur,
                  "candidates": [c.model_dump(mode="json") for c in cands],
                  "deficient": naming_engine._deficient_elements(chart)}
        input_json = {"surname": sur}
    return _persist_and_bill(db, "naming", kind, birth, chart, input_json, result, user, depth, locale)


def create_taekil(
    db: Session, birth: BirthDTO, purpose: str, start: date_t, days: int,
    user: User | None = None, depth: str = "deep", birth2: BirthDTO | None = None,
    locale: str = "ko",
) -> dict[str, Any]:
    chart = build_chart(_to_birth_input(birth, locale=locale))
    chart2 = build_chart(_to_birth_input(birth2, locale=locale)) if (birth2 and purpose == "birth") else None
    res = taekil_engine.recommend_dates(chart, start, days=days, purpose=purpose, top=10, user_chart2=chart2, locale=locale)
    result = res.model_dump(mode="json")
    input_json = {"purpose": purpose, "start_date": start.isoformat(), "days": days}
    return _persist_and_bill(db, "taekil", purpose, birth, chart, input_json, result, user, depth, locale)


def get_tool(db: Session, tool_id: str, user: User | None) -> dict[str, Any] | None:
    row = db.get(ToolSession, tool_id)
    if row is None:
        return None
    if row.user_id is not None and (user is None or user.id != row.user_id):
        raise PermissionError("not your session")
    asst = next((m for m in row.messages if m.role == "assistant"), None)
    explain = ""
    if asst:
        explain = chat_service._make_preview(asst.content) if (asst.is_preview and not asst.preview_revealed) else asst.content
    return {"tool_id": tool_id, "tool": row.tool, "kind": row.kind,
            "result": _mask_preview_result(row.result_json) if row.is_preview else row.result_json,
            "explain": explain, "is_preview": row.is_preview}


# ── 해설 렌더 ─────────────────────────────────────────────────
_WX_KO = {"木": "목", "火": "화", "土": "토", "金": "금", "水": "수"}


def _render(row: ToolSession) -> str:
    r = row.result_json or {}
    if row.tool == "taekil":
        lines = [f"[택일 분석] 용도: {r.get('purpose_label')} · 본인 일지: {r.get('user_day_branch')}"]
        lines.append("추천 길일:")
        for d in (r.get("best") or [])[:7]:
            lines.append(f"- {d['date']} {d['ganzhi']} {d['hwangdo']} 손없음={d['sonless']} {d['score']}점({d['grade']})")
        if r.get("avoid"):
            lines.append("회피일: " + ", ".join(f"{d['date']}({'/'.join(d['warnings']) or d['grade']})" for d in r["avoid"]))
        lines.append("\n위 근거로 추천 길일의 이유와 회피일을 설명하세요.")
        return "\n".join(lines)
    # naming
    kind = r.get("kind")
    if kind == "gaemyeong":
        a = r.get("analysis", {})
        lines = [f"[개명 진단] 현재 이름: {a.get('name')}({a.get('reading')})"]
        for f in (a.get("factors") or {}).values():
            lines.append(f"- {f['label']}: {f['score']}점 | {f['detail']}")
        fp = a.get("four_pillars", {})
        lines.append("4격: " + ", ".join(f"{v['label']} {v['num']}({v['grade']})" for v in fp.values()))
        lines.append("\n위 근거로 현재 이름의 강점·유의점과 개명 필요 여부를 설명하세요.")
        return "\n".join(lines)
    # jakmyeong | aho
    defc = "·".join(_WX_KO.get(e, e) for e in (r.get("deficient") or []))
    label = "작명" if kind == "jakmyeong" else "아호"
    lines = [f"[{label} 추천] 성: {r.get('surname') or '(없음)'} · 사주 부족오행: {defc}"]
    for c in (r.get("candidates") or [])[:8]:
        lines.append(f"- {c['given']}({c['reading']}) {c['score']}점 81수[{c['suri_grade']}] 오행{c['elements']} : {c['meaning']}")
    lines.append(f"\n위 후보 중 추천작을 골라 {label} 원리(수리·오행·발음)와 함께 설명하세요.")
    return "\n".join(lines)


def _system_for(row: ToolSession) -> str:
    return TAEKIL_SYSTEM if row.tool == "taekil" else NAMING_SYSTEM


# ── 스트리밍 해설 / 추가질문 ──────────────────────────────────
def stream_message(
    db: Session, tool_id: str, message: str, user: User | None = None,
    depth: str = "deep", explain_level: str = "normal",
):
    row = db.get(ToolSession, tool_id)
    if row is None:
        raise KeyError(tool_id)
    if row.user_id is not None and (user is None or user.id != row.user_id):
        raise PermissionError("not your session")
    s = get_settings()
    depth = "deep" if depth == "deep" else "basic"
    message = (message or "").strip()

    brief = _render(row)
    dialect = (getattr(user, "answer_dialect", None) or "standard") if user else "standard"
    di = chat_service._dialect_instruction(dialect)
    locale = getattr(row, "locale", "ko")   # 세션 확정 로케일 — 응답 언어·모델 선택(chat 미러)
    has_assistant = any(m.role == "assistant" for m in row.messages)
    is_explain = not has_assistant

    # ---- 내부 RAG(학습 코퍼스) — 사주와 동일하게 기본·심화 모두 활용 ----
    rag_query = (f"{message}\n{brief}" if message else brief)[:600]
    chunks = chat_service.retrieve_for_menu(
        rag_query, depth, session_id=tool_id, question=(message or None)
    )
    rag_ctx = chat_service.rag_context_block(chunks)

    if is_explain:
        is_preview = row.is_preview
        billing_mode = "tool_explain"; credits = 0
        use_free = use_daily = use_mem = False
        sys_content = chat_service._compose_sys_content(_system_for(row), dialect, explain_level, locale)
        ucontent = brief if not rag_ctx else f"{brief}\n\n[참고자료]\n{rag_ctx}"
        msgs = [{"role": "system", "content": sys_content}, {"role": "user", "content": ucontent}]
        save_user = None
    else:
        if not message:
            yield ("error", {"detail": "질문을 입력해 주세요."}); return
        # 프리미엄 메뉴 추가질문: 무료한도 미적용(항상 1,000/3,000P 차감)
        bill = chat_service._decide_billing(db, user, depth, allow_free_quota=False, claim=True)
        is_preview = bill["is_preview"]; credits = bill["credits_to_charge"]
        billing_mode = bill["billing_mode"]
        use_free = bill["use_free_quota"]; use_daily = bill["use_daily_free"]; use_mem = bill["use_membership"]
        sys_content = chat_service._compose_sys_content(_system_for(row), dialect, explain_level, locale)
        analysis = f"[분석]\n{brief}" + (f"\n\n[참고자료]\n{rag_ctx}" if rag_ctx else "")
        # 메뉴 이탈 질문(내 명식/일간/세운 등) 대비 — 전체 명식 요약 + 현재 세운/월운 + 질문날짜 간지 주입.
        # 택일/작명 brief엔 4주가 없어 직접 명식 질문 시 환각 → chat과 동일 정보로 일관 차단.
        _aux = chat_service._aux_ganji_blocks(
            message, getattr(row, "chart_json", None), include_summary=True)
        if _aux:
            analysis = f"{analysis}\n\n{_aux}"
        msgs = [{"role": "system", "content": sys_content},
                {"role": "user", "content": analysis}]
        for m in [mm for mm in row.messages if mm.role in ("user", "assistant")][-12:]:
            msgs.append({"role": m.role, "content": m.content})
        msgs.append({"role": "user", "content": message})
        save_user = message

    _claude_avail = (settings_service.get_bool(db, "external_llm_enabled", True)
                     and external_llm.is_enabled())
    do_qwen = (not is_preview) and s.deep_local_refine_enabled          # 1차 내부 보강(기본·심화)
    do_claude = depth == "deep" and (not is_preview) and _claude_avail  # 심화 외부 보강
    will_refine = do_qwen or do_claude
    yield ("meta", {"billing_mode": billing_mode, "is_preview": is_preview,
                    "mode": "explain" if is_explain else "followup", "will_refine": will_refine})

    parts: list[str] = []
    tok_q: "_queue.Queue[Any]" = _queue.Queue()
    SENT = object()
    err: dict[str, Exception] = {}
    stop_event = threading.Event()  # 클라 이탈 시 메인 Ollama producer 조기 종료

    def _produce():
        try:
            for tok in chat_service._stream_ollama(
                msgs, model=chat_service._draft_model(locale), stop_event=stop_event
            ):
                tok_q.put(tok)
        except Exception as e:  # noqa: BLE001
            err["e"] = e
        finally:
            tok_q.put(SENT)

    threading.Thread(target=_produce, daemon=True).start()
    pchars = 0; cut = False
    # 클라 이탈(GeneratorExit) 시 finally 가 stop_event 를 set → 고아 추론 차단.
    try:
        while True:
            try:
                item = tok_q.get(timeout=s.sse_heartbeat_sec)
            except _queue.Empty:
                yield ("ping", {}); continue
            if item is SENT:
                break
            parts.append(item)
            if is_preview:
                if not cut:
                    rem = s.preview_max_chars - pchars
                    if rem > 0:
                        snd = item[:rem]; pchars += len(snd)
                        if snd:
                            yield ("chunk", {"text": snd})
                    if pchars >= s.preview_max_chars:
                        cut = True; yield ("cut", {"reason": "preview_limit"})
            else:
                yield ("chunk", {"text": item})
    finally:
        stop_event.set()

    # ---- 1차 로컬(exaone) 실패 → 외부(Claude) 폴백 (사주와 동일) ----
    local_ok = "e" not in err
    if not local_ok:
        e = err["e"]
        fb = None
        if not is_preview:
            fb = chat_service.external_fallback_answer(
                question=(message or "해설"), evidence=brief, rag_context=rag_ctx,
                dialect_instruction=di or None, locale=locale,
            )
        if fb:
            parts = [fb]
            yield ("refine", {"text": fb, "reason": "로컬 엔진 불가 — 외부 AI 폴백"})
        else:
            code = "service_unavailable" if isinstance(e, chat_service.ServiceUnavailableError) else None
            yield ("error", {"detail": str(e), **({"code": code} if code else {})}); return

    answer = "".join(parts)
    refined = False
    _q = message or "해설"
    # ---- ① 내부 qwen 보강 (기본·심화 공통, 로컬 1차 정상) ----
    if do_qwen and local_ok and answer.strip():
        yield ("stage", {"phase": "draft_done"}); yield ("stage", {"phase": "refining"})
        qb = None
        for ev in chat_service._bg_with_heartbeat(s, lambda af=answer: chat_service._refine_with_qwen(
                question=_q, draft=af, saju_summary=None, evidence=brief,
                rag_context=rag_ctx, dialect_instruction=di or None, locale=locale)):
            if ev[0] == "result":
                qb = ev[1]
            else:
                yield ev
        if qb:
            answer = qb.strip(); refined = True
            yield ("refine", {"text": answer, "reason": "내부 보강(qwen)"})
        yield ("stage", {"phase": "refine_done"})

    # ---- ② 외부 Claude 보강 (심화 전용, qwen 다음) ----
    if do_claude and local_ok and answer.strip():
        yield ("stage", {"phase": "refining"})
        cb = None
        for ev in chat_service._bg_with_heartbeat(s, lambda af=answer: chat_service._claude_boost(
                question=_q, draft=af, saju_summary=None, evidence=brief,
                rag_context=rag_ctx, dialect_instruction=di or None, locale=locale)):
            if ev[0] == "result":
                cb = ev[1]
            else:
                yield ev
        if cb:
            answer = cb.strip(); refined = True
            yield ("refine", {"text": answer, "reason": "심화 검증·보강(Claude)"})
        yield ("stage", {"phase": "refine_done"})

    # ---- 명식 정합성 검증·교정 (절대규칙) — 답변의 4주 지지가 본인 명식과 다르면 교정 ----
    if not is_preview and answer.strip():
        _cj = getattr(row, "chart_json", None)
        _allow = chat_service._allowed_from_charts(_cj)
        _no_date = (row.tool == "taekil")  # 택일은 '그날 일지'(날짜) 오탐 방지
        # 지지(날짜문맥 제외는 택일만) + 일간(천간) 동시 검증 — 둘은 독립
        _branch_bad = chat_service._verify_branches(answer, _allow, exclude_date_ctx=_no_date)
        _stem_bad = chat_service._verify_day_stem(answer, _cj)
        if _branch_bad or _stem_bad:
            yield ("stage", {"phase": "verifying"})
            _fixed = None
            for ev in chat_service._bg_with_heartbeat(s, lambda af=answer: chat_service._correct_branches(
                    af, allowed=_allow, truth=chat_service._myeongsik_truth(_cj), question=_q,
                    sys_content=sys_content, saju_summary=brief, exclude_date_ctx=_no_date,
                    chart_json=_cj)):
                if ev[0] == "result":
                    _fixed = ev[1]
                else:
                    yield ev
            if _fixed and _fixed.strip() and _fixed.strip() != answer:
                answer = _fixed.strip(); refined = True
                yield ("refine", {"text": answer, "reason": "명식 정합성 자동 교정"})
        # 자료 인용 말투 제거(전문가 화법)
        _scrubbed = chat_service._scrub_source_refs(answer)
        if _scrubbed and _scrubbed != answer:
            answer = _scrubbed; refined = True
            yield ("refine", {"text": answer, "reason": "표현 정리"})
        # 십성 등 한자 병기 정자(正字) 교정(전문가 지적)
        _h = chat_service.fix_term_hanja(answer)
        if _h != answer:
            answer = _h; refined = True
            yield ("refine", {"text": answer, "reason": "한자 표기 정정"})

    # 미리보기 등 위 분기를 안 탄 경로까지 저장/재로드본 일관 교정(멱등).
    answer = chat_service.fix_term_hanja(answer)

    balance_after = None
    if user is not None:
        # 무료/멤버십 카운터는 _decide_billing(claim=True)에서 원자적으로 선점됨 — 여기서 미증가.
        if credits > 0:
            balance_after = auth_service.adjust_credit(db, user.id, -credits, reason="tool_q", ref_id=tool_id)
        else:
            balance_after = auth_service.get_balance(db, user.id)

    now = datetime.utcnow()
    if save_user is not None:
        db.add(ToolMessage(tool_id=tool_id, role="user", content=save_user, created_at=now,
                           is_preview=False, preview_revealed=True, credits_charged=0))
    asst = ToolMessage(tool_id=tool_id, role="assistant", content=answer, created_at=datetime.utcnow(),
                       is_preview=is_preview, preview_revealed=not is_preview, credits_charged=credits)
    db.add(asst); db.flush()
    aid = asst.id
    db.commit()

    vlen = len(chat_service._make_preview(answer)) if is_preview else len(answer)
    yield ("done", {"assistant_message_id": aid, "is_preview": is_preview,
                    "preview_revealed": not is_preview, "full_length": len(answer),
                    "preview_length": vlen, "credits_charged": credits,
                    "balance_after": balance_after, "billing_mode": billing_mode,
                    "refined": refined, "flash": not is_preview})


# ── 후속 추천질문 (사주와 동일 — 해설/추가질문 아래 칩으로 노출, 추가 상담 유도) ──
_TOOL_FALLBACK: dict[str, list[str]] = {
    "taekil": ["추천일 중 최고의 날은?", "피해야 할 시간대는?", "이사 방위도 봐주세요",
               "예비 날짜도 알려주세요", "그날 주의할 점은?", "좋은 시(時)도 정해주세요"],
    "jakmyeong": ["이 이름의 한자 뜻은?", "발음이 더 좋은 이름은?", "받침 없는 이름 추천?",
                  "돌림자로 지으려면?", "형제 이름과 어울리나요?", "영문 표기는 어떻게?"],
    "gaemyeong": ["개명하면 뭐가 좋아지나요?", "추천 이름도 지어주세요", "지금 이름의 약점은?",
                  "발음이 더 좋은 이름은?", "한자만 바꿔도 되나요?", "개명 사유 예시는?"],
    "aho": ["이 아호의 뜻 풀이는?", "더 부드러운 아호는?", "사업용 아호 추천?",
            "한 글자 아호도 되나요?", "아호 사용 예절은?", "낙관·도장에 쓰려면?"],
}
_NAMING_TOPIC = {"jakmyeong": "작명 상담", "gaemyeong": "개명 상담", "aho": "아호 상담"}


def _tool_fallback(row: ToolSession) -> list[str]:
    key = "taekil" if row.tool == "taekil" else (row.kind or "jakmyeong")
    return _TOOL_FALLBACK.get(key) or _TOOL_FALLBACK["taekil"]


def generate_tool_suggestions(db: Session, tool_id: str, n: int = 6) -> list[str]:
    """택일/작명/개명/아호 해설 맥락으로 후속 추천질문 n개(로컬 LLM, 무과금)."""
    row = db.get(ToolSession, tool_id)
    if row is None:
        return []
    fb = _tool_fallback(row)
    msgs = [m for m in row.messages if m.role in ("user", "assistant")]
    if not msgs:
        return fb[:n]
    parts = ["분석: " + _render(row)[:300]]
    for m in msgs[-4:]:
        parts.append(f"{'질문' if m.role == 'user' else '답변'}: {(m.content or '')[:400]}")
    topic = "택일 상담" if row.tool == "taekil" else _NAMING_TOPIC.get(row.kind or "", "작명 상담")
    return chat_service.suggestions_from_convo("\n".join(parts), n, topic=topic, fallback=fb)
