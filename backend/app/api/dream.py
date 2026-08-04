"""B-9 꿈해몽 API — 채팅형 풀이(SSE 스트리밍) + 후속질문용 tool 세션 발급.

기존 LLM 파이프라인 그대로 재사용: 내부 RAG(retrieve_for_menu) + qwen3:14b 스트림
+ 로컬 다운 시 Claude 폴백. 과금은 사주 상담과 동일 정책(_decide_billing — 무료쿼터 적용,
비로그인=미리보기 컷). 이탈 시 stop_event 로 GPU 고아 추론 차단([[gpu-runaway-explain-cause]]).

첫 풀이 완료 시 ToolSession(tool="dream")과 대화(꿈+풀이)를 영속하고 done 이벤트에 tool_id 를
동봉 — 추가질문은 공용 /api/tools/{id}/messages/stream(프리미엄 표준: 기본/심화 차감)을 탄다.

해몽 코퍼스: 색인에 해몽 자료가 올라오면 RAG 가 자동 활용(업로드 학습 파이프라인).
자료가 없으면 전통 통설 기반 가능성 화법으로만 답하고 가짜 문헌 인용은 프롬프트로 금지.
"""
from __future__ import annotations

import json
import logging
import queue as _queue
import threading
from typing import Any, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.db import get_db
from backend.app.core.deps import get_optional_user
from backend.app.repositories.auth_models import User
from backend.app.services import auth_service, chat_service
from backend.app.services import dream_symbols
from backend.app.services import settings_service
from backend.app.services.tool_service import DREAM_SYSTEM  # 시스템 프롬프트 일원화(후속질문과 동일 톤)

router = APIRouter(prefix="/api/dream", tags=["dream"])
_log = logging.getLogger("saju.dream")


class DreamReq(BaseModel):
    content: str = Field(min_length=5, max_length=2000)   # 꿈 내용
    # (선택) 사주 연계 — 있으면 일간·오행 연결 단락 추가
    birth_date: Optional[str] = None
    birth_time: Optional[str] = None
    calendar: str = "solar"
    is_leap_month: bool = False
    gender: str = "male"


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
def dream_stream(
    req: DreamReq,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_optional_user),
):
    s = get_settings()

    def gen():
        _pre_charged = 0
        bill = None
        try:
            # 과금 판정 — 사주 상담과 동일(무료쿼터/일일무료/멤버십/패스 전부 동일 경로)
            try:
                bill = chat_service._decide_billing(db, user, "basic", allow_free_quota=True, claim=True)
            except ValueError as e:
                yield _sse("error", {"detail": str(e), "code": "quota"})
                return
            is_preview = bill["is_preview"]
            credits = bill["credits_to_charge"]
            # free-ride 차단: 무료/멤버십/pass 선점 + 유료차감을 '생성 전' 확정 커밋 — 전체 답변 전달 후 disconnect 시
            #   함수 끝 commit 롤백으로 무료·유료가 무한 소비되던 문제(사주챗/추가질문과 동일). 명시적 생성실패는 보상 원복.
            _pre_charged = chat_service.precharge_followup(db, user, bill, reason="dream", ref_id=None)

            # (선택) 사주 연계 블록
            saju_block = ""
            saju_chart_json = None       # 후속질문 brief 가 쓸 명식 — 세션에 함께 저장한다
            if req.birth_date:
                try:
                    from backend.app.saju.engine import build_chart
                    from backend.app.saju.types import BirthInput
                    ch = build_chart(BirthInput(
                        birth_date=req.birth_date, birth_time=req.birth_time,
                        calendar=req.calendar, is_leap_month=req.is_leap_month, gender=req.gender,
                    ), with_daewoon=False)
                    saju_chart_json = ch.model_dump(mode="json")
                    # 오행 개수는 화면 명식표와 같은 팔자8(천간+지지본기) 기준 — 종전 full(지장간 포함)은
                    #   팔자에 없는 오행을 '있다'고 알려줘 해몽이 어긋났다(운영자 지적 2026-07-22).
                    from backend.app.saju.wuxing import wuxing_eight_of as _wx8
                    saju_block = (f"\n\n[내 사주]\n일간 {ch.pillars.day.stem}({ch.day_master_element}) · "
                                  f"오행 분포(팔자 8글자) {_wx8(ch).as_dict_ko()}")
                except Exception:  # noqa: BLE001 — 사주 연계 실패는 무시(해몽은 계속)
                    saju_block = ""
                    saju_chart_json = None

            # RAG — 해몽 코퍼스가 색인에 있으면 자동 활용
            # [P3-D1] session_id·question 을 안 넘겨 **꿈해몽 첫 풀이는 회수가 100% 미기록**이었다
            # (dream 세션 29건, 로그 0건). 해몽은 결정적 엔진이 없어 RAG 가 유일 근거인데도
            # 품질을 볼 방법이 없었다. 세션 id 는 생성 후에야 생기므로(아래 persist) None 으로 둔다.
            chunks = []
            try:
                chunks = chat_service.retrieve_for_menu(
                    f"꿈 해몽 {req.content[:200]}", "basic",
                    question=req.content[:500], menu="dream",
                )
            except Exception:  # noqa: BLE001
                chunks = []
            rag_ctx = chat_service.rag_context_block(chunks)
            # [P4] 정적 상징 사전 — 코퍼스가 실질 0건이라 이게 **주근거**다(RAG 는 보조).
            # 매칭된 항목만 주입한다(전량 금지 — 타로가 78장 중 뽑힌 카드만 넣는 것과 같다).
            sym_ctx = dream_symbols.context_block(req.content)

            ucontent = f"[꿈 이야기]\n{req.content}"
            if sym_ctx:
                ucontent += f"\n\n{sym_ctx}"
            if rag_ctx:
                ucontent += f"\n\n[참고자료]\n{rag_ctx}"
            ucontent += saju_block
            # [P3-E4] 이 경로만 _compose_sys_content 를 안 거쳐 공통 가드가 전부 빠져 있었다 —
            # CHART_FIDELITY_RULE(타인 명식 오염 차단)·EXPERT_VOICE_RULE(출처 언급 금지)·
            # FACT_GROUNDING_RULE(사실 날조 금지) 없이 DREAM_SYSTEM 한 줄로만 돌았다.
            # 실측 피해: 저장된 dream 답변 50건 중 가짜 문헌 인용 2건("[참고자료: '꿈 해석 사전'에
            # 따르면…]" — 그런 자료는 코퍼스에 없다), 명식 모순 3건(답변 '일간이 목(木)' vs 실제 癸).
            # 해몽은 결정적 엔진이 없어 RAG 가 유일 근거인데 그 RAG 마저 0건인 메뉴라 가드가 특히 중요하다.
            sys_content = chat_service._compose_sys_content(
                DREAM_SYSTEM, None, "normal", has_sources=bool(rag_ctx or sym_ctx))
            _cr = chat_service.chart_reconfirm_block(saju_chart_json)
            if _cr:
                ucontent += f"\n\n{_cr}"
            msgs = [{"role": "system", "content": sys_content}, {"role": "user", "content": ucontent}]

            yield _sse("meta", {"billing_mode": bill["billing_mode"], "is_preview": is_preview})

            parts: list[str] = []
            tok_q: "_queue.Queue[Any]" = _queue.Queue()
            SENT = object()
            err: dict[str, Exception] = {}
            stop_event = threading.Event()

            def _produce():
                try:
                    for tok in chat_service._stream_ollama(msgs, stop_event=stop_event):
                        tok_q.put(tok)
                except Exception as e:  # noqa: BLE001
                    err["e"] = e
                finally:
                    tok_q.put(SENT)

            threading.Thread(target=_produce, daemon=True).start()
            _pmax = settings_service.get_cached_int("preview_max_chars", s.preview_max_chars)
            pchars = 0
            cut = False
            try:
                while True:
                    try:
                        item = tok_q.get(timeout=s.sse_heartbeat_sec)
                    except _queue.Empty:
                        yield _sse("ping", {})
                        continue
                    if item is SENT:
                        break
                    parts.append(item)
                    if is_preview:
                        if not cut:
                            rem = _pmax - pchars
                            if rem > 0:
                                snd = item[:rem]
                                pchars += len(snd)
                                if snd:
                                    yield _sse("chunk", {"text": snd})
                            if pchars >= _pmax:
                                cut = True
                                yield _sse("cut", {"reason": "preview_limit"})
                    else:
                        yield _sse("chunk", {"text": item})
            finally:
                stop_event.set()   # 클라 이탈 → Ollama 고아 추론 차단

            answer = "".join(parts)
            # 로컬 다운 → 외부 폴백(사주와 동일)
            if "e" in err:
                fb = None
                if not is_preview:
                    from backend.app.services import settings_service as _ss
                    # [2026-08-04 퀵윈] 외부폴백(최대 ~25s) 동기 대기 무음 → 하트비트 랩('무음사망' 차단).
                    def _fb_call():
                        return chat_service.external_fallback_answer(
                            question=f"꿈 해몽: {req.content[:300]}", evidence=None,
                            rag_context=rag_ctx, dialect_instruction=None,
                            allow_overseas=(_ss.get_cached_bool("overseas_llm_fallback_enabled", False)
                                            and getattr(user, "overseas_transfer_opt_in", False)),
                        )
                    for _ev in chat_service._bg_with_heartbeat(s, _fb_call, progress_phase="refining"):
                        if _ev[0] == "result":
                            fb = _ev[1]
                        else:
                            yield _sse(_ev[0], _ev[1])
                if fb:
                    answer = fb
                    yield _sse("refine", {"text": fb, "reason": "로컬 엔진 불가 — 외부 AI 폴백"})
                else:
                    # 답변 생성 실패 → 생성 전 확정한 과금(유료/선점) 보상 원복.
                    chat_service.refund_followup(db, user, bill, _pre_charged, reason="dream", ref_id=None)
                    yield _sse("error", {"detail": str(err["e"])})
                    return

            # 유료·선점은 precharge_followup 에서 '생성 전' 확정됨 — 여기선 이중차감 금지.
            #   단 빈 응답(생성 실패)은 원래 미차감이었으므로 확정분을 보상 원복.
            if not answer.strip():
                chat_service.refund_followup(db, user, bill, _pre_charged, reason="dream", ref_id=None)
                yield _sse("error", {"detail": "해몽을 생성하지 못했어요. 잠시 후 다시 시도해 주세요."}); return
            # 출력 정리 체인 — 다른 메뉴는 전부 거치는데 이 경로만 빠져 있어(전수감사 실측)
            # 한글(한글) 오병기·중복 문장이 저장본·화면·PDF까지 그대로 갔다. 멱등.
            answer = chat_service.fix_term_hanja(answer)
            # [P3-E4] 출처 인용 말투 제거 + 명식 정합 검증 — 다른 메뉴는 전부 도는 배터리인데
            # 이 경로만 빠져 있었다. 사주 연계가 있을 때만 검증(꿈만 물은 경우엔 대조할 명식이 없음).
            answer = chat_service._scrub_source_refs(answer)
            # 구분선(---)·과다 빈줄 정리 — 종전 주석은 '---' 제거를 표방했으나 fix_term_hanja 는
            # 실제로 '---'를 못 지웠다(전수감사 실측). _tidy_markdown 으로 실제 제거(무손실·헤딩 보존).
            answer = chat_service._tidy_markdown(answer)
            # [2026-08-04 퀵윈] 화면=DB 동기화 — 위 무음 교정(한자·인용톤·tidy)이 이벤트 없이 저장본만
            #   바꿔 새로고침 전까지 화면과 달랐다(전수감사 P4). 실질 변화 시에만 최종본 1회 푸시(미리보기 제외).
            if not is_preview and answer != "".join(parts):
                yield _sse("refine", {"text": answer, "reason": "표현 정리"})
            if saju_chart_json:
                _bad = chat_service._verify_myeongsik(answer, saju_chart_json)
                if _bad:
                    # 해몽은 짧고 재생성 비용이 크지 않지만, 사용자를 더 기다리게 하지 않는다 —
                    # 다른 메뉴와 같이 로그로만 남기고(관리자 추적) 본문은 그대로 내보낸다.
                    _log.warning("dream myeongsik mismatch: %s | rag=%s",
                                 _bad, chat_service._rag_trace())
            balance_after = auth_service.get_balance(db, user.id) if user is not None else None

            # 후속질문용 tool 세션 영속(풀이 성공 시에만) — 공용 tools 스트림이 컨텍스트로 사용.
            # 사주 미연계면 birth가 없어 자리표시(1900-01-01)로 저장(input_json.no_birth 표기).
            tool_id = None
            if answer.strip():
                try:
                    from datetime import date as _date
                    from backend.app.repositories.models import ToolMessage
                    from backend.app.services import tool_service
                    _bd = _date.fromisoformat(req.birth_date) if req.birth_date else _date(1900, 1, 1)
                    # chart_json 을 반드시 넘긴다 — 이게 없으면 후속질문 brief(_render dream)가
                    # 일간·오행 분포를 못 실어, 水가 0개인 명식에 '물이 풍요롭다'는 창작이 나온다
                    # (전수감사 실측 6런 중 5런). 첫 풀이는 saju_block 으로 정확했는데 추가질문만 틀렸다.
                    tool_id = tool_service.persist_free_session(
                        db, "dream", "dream", birth_date=_bd, birth_time=req.birth_time,
                        calendar=req.calendar, is_leap_month=req.is_leap_month, gender=req.gender,
                        chart_json=saju_chart_json,
                        input_json={"content": req.content, "saju_linked": bool(saju_block),
                                    "no_birth": not bool(req.birth_date)},
                        result_json=None, user=user,
                    )
                    db.add(ToolMessage(tool_id=tool_id, role="user", content=req.content,
                                       is_preview=is_preview))
                    db.add(ToolMessage(tool_id=tool_id, role="assistant", content=answer,
                                       is_preview=is_preview, credits_charged=credits if answer.strip() else 0))
                    # 유료 해몽 영수증 EOF 완결 마킹(persist 커밋에 합류) + dream 링크 교정
                    #   (precharge 시엔 tool_id 미생성이라 ref_id=None 이었음 → 여기서 tool_id 주입).
                    from backend.app.services import receipt_service
                    receipt_service.finalize_receipt(db, bill.get("receipt_id"), ref_id=tool_id)
                    db.commit()
                except Exception:  # noqa: BLE001 — 세션 영속 실패해도 풀이 자체는 전달
                    tool_id = None

            yield _sse("done", {
                "is_preview": is_preview, "credits_charged": credits if answer.strip() else 0,
                "balance_after": balance_after, "full_length": len(answer),
                "tool_id": tool_id,
            })
        except Exception as e:  # noqa: BLE001
            # 확정한 과금(precharge_followup)을 보상 원복(후처리 예외로 답변 미전달 시).
            try:
                db.rollback()
                chat_service.refund_followup(db, user, bill, _pre_charged, reason="dream", ref_id=None)
            except Exception:  # noqa: BLE001
                pass
            yield _sse("error", {"detail": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})
