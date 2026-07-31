"""타로 서비스 — CSPRNG 드로우 확정 + 입장료 차감 + LLM 해석 스트리밍(궁합 미러링).

- 드로우: 세션 생성 시 secrets(CSPRNG) Fisher-Yates 로 78장 셔플 순서 + 카드별 역방향(50%)을
  확정해 DB에 저장(비공개). 사용자가 부채꼴에서 고른 인덱스(0~77)를 그 순서에 매핑.
- picks 는 세션당 1회 확정, 재호출은 저장된 동일 결과 반환(멱등).
- 빌링: 입장료(entry_cost_tarot)는 생성 시 1회 차감(compat 와 동일 메커니즘, 최초 해석 포함).
  추가질문은 depth(basic/deep)별 차감 — chat_service._decide_billing(allow_free_quota=False) 재사용.
- 카드명·방향·포지션은 서버 결정값을 그대로 렌더. LLM 은 해석 본문만 생성(창작 금지).
"""
from __future__ import annotations

import queue as _queue
import re
import secrets
import threading
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.repositories.auth_models import User
from backend.app.repositories.models import TarotMessage, TarotSession
from backend.app.services import auth_service, chat_service, external_llm, settings_service
from backend.app.services import tarot_deck

# 회원당 보관 가능한 타로 세션 최대 개수(확정 정책). 채팅(max_sessions_per_user, 빈세션 제외)과
# 달리 타로는 빈 세션(카드만 뽑음)도 입장료 낸 자산이라 전부 카운트한다 → 별도 상한값(20).
TAROT_MAX_SESSIONS = 20

# ============================================================
# 시스템 프롬프트 (타로 전용 — 사주 규칙 미주입)
# ============================================================
TAROT_SYSTEM = """당신은 한국어로 상담하는 따뜻하고 통찰력 있는 타로 상담사입니다.

입력으로 질문, 섹션(상담 주제), 스프레드명, 포지션별 카드(포지션명, 카드 한글명(영문), 방향, 키워드)가 주어집니다.

원칙:
1. 카드명·방향(정방향/역방향)·포지션은 반드시 주어진 값만 사용하세요. 주어지지 않은 카드나 방향, 포지션을 새로 만들어내지 마세요.
   역방향은 '나쁨'의 뜻이 아닙니다. 각 카드 옆의 키워드가 곧 그 방향의 의미입니다 —
   키워드가 긍정적 전환(예: 회복 조짐, 교착 해소, 관심 회복)이면 그대로 긍정적 전환으로 풀이하세요.
2. 해석 순서: 포지션별 해석 → 카드 간 상호작용(흐름·대비·강화) → 종합 → 질문에 대한 구체적 조언.
   포지션별 해석에서는 각 카드의 한글 이름과 방향을 본문에 명시적으로 언급하세요(뭉뚱그리지 말 것).
3. 단정적인 길흉 판정 대신 가능성과 행동 조언 중심으로 설명하세요. 타로는 확정된 미래가 아니라 현재 흐름의 거울임을 전제로 하세요.
   "반드시 ~됩니다", "100%", "틀림없이" 같은 확언은 쓰지 마세요.
4. 충분히 풍부하게 설명하세요 — 7장 스프레드는 최소 1,200자, 11장 스프레드는 최소 1,800자.
   모든 포지션을 하나도 빠짐없이 각각 다루세요(후반 포지션을 뭉뚱그리지 말 것).
5. "~합니다" 존댓말을 사용하고, 사용자를 존중하는 부드러운 상담 어조를 유지하세요.
   질문 문장을 그대로 반복하며 시작하지 말고, 상담사가 말을 건네듯 자연스럽게 시작하세요.
6. 마무리는 결과 카드의 톤을 유지하세요. 부정적·유보적 카드인데 근거 없는 응원 덕담으로 끝내지 마세요.
7. 조언은 질문자가 실행할 수 있는 구체적 행동 1~3가지(무엇을, 어떤 순서로)로 제시하세요.
"""

TAROT_FOLLOWUP_HINT = (
    "\n[추가 질문 안내] 사용자가 위 타로 스프레드 해석에 대해 추가로 묻습니다. "
    "이미 뽑힌 카드(포지션·방향·키워드)와 이전 대화를 토대로, 질문에 구체적으로 답하세요. "
    "새 카드를 뽑거나 카드·방향을 바꾸지 마세요."
)

# 베트남어(vi) 타로 시스템 프롬프트 — ko 룰(한국어 존댓말·상담체)을 vi 에 주입하면 충돌하므로 별도.
TAROT_SYSTEM_VI = """Bạn là một nhà tư vấn Tarot tiếng Việt ấm áp, sâu sắc và tinh tế.

Đầu vào gồm câu hỏi, chủ đề, tên trải bài và từng lá theo vị trí (tên vị trí, tên lá, chiều xuôi/ngược, từ khoá).

Nguyên tắc:
1. Chỉ dùng đúng tên lá, chiều (xuôi/ngược) và vị trí đã cho; không bịa ra lá, chiều hay vị trí mới.
   Lá ngược KHÔNG có nghĩa là "xấu" — từ khoá bên cạnh chính là ý nghĩa của chiều đó.
2. Thứ tự luận giải: giải theo từng vị trí → tương tác giữa các lá → tổng hợp → lời khuyên cụ thể cho câu hỏi.
   Khi giải từng vị trí, hãy nêu rõ tên lá và chiều của nó trong bài viết.
3. Tránh phán hung/cát tuyệt đối; tập trung vào khả năng và lời khuyên hành động. Không dùng "chắc chắn", "100%".
4. Viết đủ dài và phong phú; xử lý đầy đủ tất cả các vị trí, không gộp qua loa các lá về sau.
5. Dùng giọng lịch sự, tôn trọng người hỏi; mở đầu tự nhiên, không lặp lại nguyên văn câu hỏi.
6. Chỉ viết bằng tiếng Việt (chữ Quốc ngữ có dấu). TUYỆT ĐỐI không dùng chữ Hán / tiếng Trung.
"""

TAROT_FOLLOWUP_HINT_VI = (
    "\n[Câu hỏi thêm] Người dùng hỏi thêm về phần luận giải trải bài ở trên. "
    "Dựa trên các lá đã rút (vị trí·chiều·từ khoá) và cuộc trò chuyện trước, hãy trả lời cụ thể. "
    "Không rút lá mới, không đổi lá hay chiều."
)

# vi 상담체 줄글 규칙(마크다운 금지) — ko CONSULTANT_STYLE_RULE 대응.
TAROT_STYLE_RULE_VI = (
    "[Định dạng — bắt buộc] Không dùng markdown (#, **, -, danh sách đánh số, bảng); "
    "viết thành các đoạn văn tự nhiên như đang tư vấn trực tiếp."
)

# 내부(qwen)·외부(Claude) 보강용 — 사주 감수 프롬프트를 쓰면 명리 용어가 오염되므로 타로 전용으로 분리.
TAROT_REFINE_SYSTEM = (
    "당신은 한국어 타로 상담 감수자입니다. 주어진 1차 해석을 [타로 스프레드] 근거에 비추어 "
    "검증·보강하세요.\n"
    "반드시 한국어로만 작성하세요. 중국어(간체/번체) 문장이나 단어를 절대 쓰지 마세요.\n"
    "원칙:\n"
    "1. 카드명·방향·포지션은 주어진 값만 사용하고, 없는 카드·방향을 새로 만들지 마세요.\n"
    "2. 포지션별 해석 → 카드 상호작용 → 종합 → 구체적 조언 흐름을 유지·강화하세요. "
    "각 카드의 한글 이름과 방향이 본문에 명시적으로 남아 있어야 합니다(빼먹지 말 것).\n"
    "3. 단정적 길흉 대신 가능성·행동 조언 중심으로, \"~합니다\" 존댓말로 쓰세요.\n"
    "4. 마크다운(헤더 #, 굵게 **, 목록 -·*, 번호 1., 표)을 쓰지 말고, 상담가가 말하듯 "
    "자연스러운 줄글 문단으로만 쓰세요. 1차 해석에 마크다운이 있으면 줄글로 풀어 고치세요.\n"
    "5. '자료에 의하면' 같은 출처 언급 없이 전문가 본인이 풀이하듯 자신 있게 쓰세요.\n"
    "6. 요약 금지 — 1차 해석의 분량과 세부 내용을 유지하거나 더 풍부하게 보강하세요. "
    "문단을 통째로 덜어내거나 짧게 줄이지 마세요.\n"
    "7. 본문 서술이 [타로 스프레드]의 방향·키워드와 어긋나면 반드시 바로잡으세요. "
    "특히 역방향 카드를 기계적으로 '부정적'으로 풀이한 부분은 주어진 키워드의 의미"
    "(긍정 전환이면 긍정 전환)로 교정하세요. 카드 이름은 한글명으로 쓰세요.\n"
    "8. 본문 첫 문장이 질문을 되풀이하면 삭제하고 자연스러운 도입으로 바꾸세요. "
    "마지막 문단이 \"힘내세요\"류 범용 덕담이면 결과 카드의 톤에 맞는 마무리로 교체하세요. "
    "\"반드시 ~됩니다\", \"보장합니다\"류 확언은 걷어내세요.\n"
    "9. 최종 '완성된 해석 본문'만 출력하세요. 메타설명·머리말·코드블록 없이 본문만.\n"
)

TAROT_GENERATE_SYSTEM = (
    "당신은 한국어로 상담하는 타로 상담사입니다. 주어진 [타로 스프레드](질문·섹션·포지션별 "
    "카드·방향·키워드)에 기반해 해석하세요.\n"
    "원칙:\n"
    "1. 카드명·방향·포지션은 주어진 값만 사용하세요(창작 금지).\n"
    "2. 포지션별 해석 → 카드 상호작용 → 종합 → 구체적 조언 순으로, 최소 1,200자 이상.\n"
    "3. 단정적 길흉 대신 가능성·행동 조언 중심, \"~합니다\" 존댓말.\n"
    "4. 마크다운 없이 자연스러운 줄글 문단으로만, 최종 본문만 출력하세요.\n"
)


# ============================================================
# 드로우(CSPRNG) — 서버 확정, 비공개 저장
# ============================================================
def _csprng_shuffle_deck() -> tuple[list[int], list[bool]]:
    """secrets 기반 Fisher-Yates 셔플 순서(카드 id 78개) + 카드별 역방향(50%)."""
    order = list(range(tarot_deck.DECK_SIZE))
    for i in range(tarot_deck.DECK_SIZE - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        order[i], order[j] = order[j], order[i]
    reversed_flags = [secrets.randbelow(2) == 1 for _ in range(tarot_deck.DECK_SIZE)]
    return order, reversed_flags


def _render_spread_for_llm(row: TarotSession) -> str:
    """LLM 입력 컨텍스트 — 질문/섹션/스프레드/포지션별 확정 카드."""
    section_label = tarot_deck.SECTION_LABELS.get(row.section, row.section)
    spread_label = tarot_deck.SPREAD_LABELS.get(row.spread_type, row.spread_type)
    parts = [
        "[타로 스프레드]",
        f"- 섹션(상담 주제): {section_label}",
        f"- 질문: {row.question or '(질문 없음 — 주제 전반)'}",
        f"- 스프레드: {spread_label}",
        "[뽑힌 카드]",
    ]
    for c in (row.cards_json or []):
        is_rev = c["orientation"] == "reversed"
        ori = "역방향" if is_rev else "정방향"
        kw = ", ".join(c.get("keywords") or [])
        line = (
            f"{c['position_index'] + 1}. {c['position_name']}: "
            f"{c['name_kr']}({c['name_en']}) — {ori} | 이 방향({ori})의 의미: {kw}"
        )
        # 정통(RWS) 해석 서술 — 덱에서 code+방향으로 조회(정적 확장, RAG 아님).
        # 짧은 키워드 위에 근거를 두껍게 해 의미론적 빈약·일반론화를 완화한다.
        interp = tarot_deck.interp_for(c.get("code", ""), is_rev).strip()
        if interp:
            line += f"\n   해설: {interp}"
        parts.append(line)
    return "\n".join(parts)


# ============================================================
# 생성 — 입장료 차감(궁합 미러) + 드로우 확정
# ============================================================
def create_tarot(
    db: Session, section: str, question: str, user: User | None = None, locale: str = "ko"
) -> dict[str, Any]:
    """타로 세션 생성: 섹션 검증 → 입장료 1회 차감(compat 동일) → CSPRNG 드로우 확정 저장.

    이 차감이 '타로 1회'이며, 최초 해석 스트림은 추가 과금하지 않는다.
    locale(요청 로케일)은 세션 행에 저장돼 해석 스트림의 응답 언어·모델을 결정한다.
    """
    spread_type, positions = tarot_deck.spread_for_section(section)
    question = (question or "").strip()

    # ---- 세션 개수 한도(계획 5.6 R 미러) — 회원만, 입장료 차감 '전'에 검사 ----
    # 타로는 빈 세션(카드만 뽑음)도 입장료 낸 자산이라 전부 카운트한다(chat 과 달리 빈세션
    # 정리 없음). 만료(1주 초과) 세션은 먼저 정리해 한도를 확보한 뒤 카운트한다.
    # ★ 반드시 _decide_entry_billing(차감/선점) 전에 예외를 던져 초과 시 입장료가 새지 않게 한다.
    if user is not None:
        from backend.app.repositories import tarot_repo
        tarot_repo.purge_expired(db)
        cnt = tarot_repo.count_user_sessions(db, user.id)
        if cnt >= TAROT_MAX_SESSIONS:
            raise chat_service.SessionLimitError(
                f"session_limit_reached: {cnt}/{TAROT_MAX_SESSIONS}"
            )

    # ---- 빌링(타로 입장료 1회 차감 — compat 미러) ----
    bill = chat_service._decide_entry_billing(db, user, "tarot", claim=True)
    is_preview = bill["is_preview"]
    credits_to_charge = bill["credits_to_charge"]

    tarot_id = uuid.uuid4().hex
    order, reversed_flags = _csprng_shuffle_deck()

    # ---- 차감/무료 갱신 (compat create 와 동일) ----
    balance_after: int | None = None
    if user is not None:
        # 무료/멤버십 카운터는 _decide_entry_billing(claim=True)에서 원자적으로 선점됨 — 여기서 미증가.
        if credits_to_charge > 0:
            balance_after = auth_service.adjust_credit(
                db, user.id, -credits_to_charge, reason="tarot", ref_id=tarot_id
            )
        else:
            balance_after = auth_service.get_balance(db, user.id)

    row = TarotSession(
        tarot_id=tarot_id,
        user_id=user.id if user else None,
        locale=locale,
        section=section,
        question=question,
        spread_type=spread_type,
        deck_order_json=order,
        reversed_json=reversed_flags,
        picks_json=None,
        cards_json=None,
        is_preview=is_preview,
        credits_charged=credits_to_charge,
    )
    db.add(row)
    db.commit()

    return {
        "tarot_id": tarot_id,
        "spread_type": spread_type,
        "need": len(positions),
        "positions": positions,
        "section": section,
        "question": question,
        "is_preview": is_preview,
        "billing_mode": bill["billing_mode"],
        "credits_charged": credits_to_charge,
        "balance_after": balance_after,
    }


# ============================================================
# 픽 제출 — 세션당 1회 확정, 재호출 멱등
# ============================================================
def submit_picks(
    db: Session, tarot_id: str, indices: list[int], user: User | None = None
) -> dict[str, Any]:
    """부채꼴 인덱스(0~77) → 서버 확정 셔플 순서에 매핑해 카드 확정(1회, 멱등)."""
    # 동시 이중 제출 방지 — 행 잠금 후 확정 여부 재확인(멱등 보장)
    row = db.get(TarotSession, tarot_id, with_for_update=True)
    if row is None:
        raise KeyError(tarot_id)
    if row.user_id is not None and (user is None or user.id != row.user_id):
        raise PermissionError("not your tarot session")

    if row.cards_json:
        db.rollback()  # 잠금 해제(변경 없음)
        return {"cards": row.cards_json}

    positions = tarot_deck.SPREAD_POSITIONS[row.spread_type]
    need = len(positions)
    if len(indices) != need:
        raise ValueError(f"indices length must be {need}")
    if any((not isinstance(i, int)) or i < 0 or i >= tarot_deck.DECK_SIZE for i in indices):
        raise ValueError("indices must be integers in 0..77")
    if len(set(indices)) != need:
        raise ValueError("indices must be unique")

    order = row.deck_order_json or []
    flags = row.reversed_json or []
    cards = [
        tarot_deck.card_payload(k, positions[k], order[idx], bool(flags[idx]))
        for k, idx in enumerate(indices)
    ]
    row.picks_json = list(indices)
    row.cards_json = cards
    db.commit()
    return {"cards": cards}


# ============================================================
# 세션 스냅샷 — 재조회 시 동일 카드 보장
# ============================================================
def get_tarot(db: Session, tarot_id: str, user: User | None) -> dict[str, Any] | None:
    row = db.get(TarotSession, tarot_id)
    if row is None:
        return None
    if row.user_id is not None and (user is None or user.id != row.user_id):
        raise PermissionError("not your tarot session")
    positions = tarot_deck.SPREAD_POSITIONS[row.spread_type]
    messages = []
    for m in row.messages:
        content = m.content
        if m.is_preview and not m.preview_revealed:
            content = chat_service._make_preview(content)
        messages.append({
            "id": m.id,
            "role": m.role,
            "content": content,
            "created_at": m.created_at.isoformat() if m.created_at else None,
            "is_preview": m.is_preview,
            "preview_revealed": m.preview_revealed,
            "credits_charged": m.credits_charged,
        })
    return {
        "tarot_id": row.tarot_id,
        "section": row.section,
        "question": row.question,
        "spread_type": row.spread_type,
        "need": len(positions),
        "positions": positions,
        "cards": row.cards_json,   # 뽑기 전이면 None
        "messages": messages,
        "is_preview": row.is_preview,
    }


# ============================================================
# 보강/폴백 (타로 전용 프롬프트 — 구조는 사주/궁합과 동일)
# ============================================================
def _tarot_refine_qwen(*, question: str, draft: str, spread: str, dialect_instruction: str | None) -> str | None:
    """내부(qwen) 1차 보강 — chat_service._refine_with_qwen 미러(타로 프롬프트)."""
    s = get_settings()
    if not s.deep_local_refine_enabled:
        return None
    parts = [spread, f"[사용자 질문]\n{question}", f"[1차 해석(보강 대상)]\n{draft}"]
    if dialect_instruction:
        parts.append(dialect_instruction)
    block = "\n\n".join(parts)
    attempts = [
        ([{"role": "system", "content": TAROT_REFINE_SYSTEM},
          {"role": "user", "content": block}], 0.2),
        ([{"role": "system", "content": TAROT_REFINE_SYSTEM},
          {"role": "user", "content": block + "\n\n[필수] 위 작업을 반드시 한국어 문장으로만 다시 "
           "작성하세요. 중국어(간체/번체) 단어·문장을 한 글자도 쓰지 마세요."}], 0.1),
    ]
    for msgs, temp in attempts:
        try:
            out = chat_service._call_ollama(msgs, model=s.ollama_refine_model, temperature=temp)
        except chat_service.ServiceUnavailableError:
            return None
        out = (out or "").strip()
        if chat_service._looks_korean_clean(out):
            return out
    return None


def _tarot_claude_call(system: str, user_block: str) -> str | None:
    """외부(Claude) 호출 공통 — external_llm 의 클라이언트/모델 결정 재사용(타로 시스템 프롬프트)."""
    if not external_llm.is_enabled() or external_llm._provider() != "claude" or external_llm.anthropic is None:
        return None
    s = get_settings()
    try:
        # 긴 해석 본문(2,000자+) 보강은 기본 타임아웃(25s)으로 부족 — 전용 긴 타임아웃.
        # SSE 는 _bg_with_heartbeat 로 유지되므로 대기 시간이 연결을 끊지 않는다.
        client = external_llm.anthropic.Anthropic(
            api_key=s.anthropic_api_key,
            timeout=max(120.0, float(s.external_llm_timeout_sec)),
            max_retries=2,
        )
        resp = client.messages.create(
            model=external_llm.resolve_claude_model(),
            max_tokens=8000,
            system=system,
            messages=[{"role": "user", "content": user_block}],
        )
        text = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text"
        ).strip()
        return text or None
    except Exception:  # noqa: BLE001
        return None


def _tarot_claude_refine(*, question: str, draft: str, spread: str, dialect_instruction: str | None) -> str | None:
    """외부(Claude) 심화 보강 — external_llm.refine_answer 미러(타로 프롬프트)."""
    parts = [spread, f"[사용자 질문]\n{question}", f"[1차 해석(보강 대상)]\n{draft}"]
    if dialect_instruction:
        parts.append(dialect_instruction)
    return _tarot_claude_call(TAROT_REFINE_SYSTEM, "\n\n".join(parts))


def _tarot_generate_fallback(*, question: str, spread: str, dialect_instruction: str | None) -> str | None:
    """로컬 엔진 전체 다운 시 외부(Claude)로 본문 생성 폴백 — external_fallback_answer 미러."""
    parts = [spread, f"[사용자 질문]\n{question}"]
    if dialect_instruction:
        parts.append(dialect_instruction)
    return _tarot_claude_call(TAROT_GENERATE_SYSTEM, "\n\n".join(parts))


_MD_HEADER = re.compile(r"(?m)^[ \t]{0,3}#{1,6}[ \t]*")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_BULLET = re.compile(r"(?m)^[ \t]{0,3}[-*][ \t]+")


def _strip_markdown(text: str) -> str:
    """마크다운 기호 결정적 제거 — 프롬프트 지시(줄글만)를 모델이 어겨도 상담문 형식 보장.

    헤더(#)·볼드(**)·불릿(-,*) 기호만 걷어내고 문장 내용·줄바꿈은 보존한다.
    번호 목록(1. )은 카드/포지션 열거("1. 과거")와 구분이 안 되므로 건드리지 않는다.
    """
    out = _MD_HEADER.sub("", text)
    out = _MD_BOLD.sub(r"\1", out)
    out = _MD_BULLET.sub("", out)
    return out


def _localize_card_names(text: str) -> str:
    """영문 카드명을 한글명으로 결정적 치환 — 모델이 "Knight of Swords"처럼 영문만 쓴 경우 보정.

    직전 12자 안에 해당 한글명이 이미 있으면(예: "전차(The Chariot)") 치환하지 않는다.
    78개 영문명은 서로 겹치지 않는 고유 문자열이라 안전하다.
    """
    for c in tarot_deck.all_cards():
        en, kr = c["name_en"], c["name_kr"]
        if en not in text:
            continue
        out: list[str] = []
        last = 0
        for m in re.finditer(re.escape(en), text):
            out.append(text[last:m.start()])
            lookback = text[max(0, m.start() - 12):m.start()]
            out.append(en if kr in lookback else kr)
            last = m.end()
        out.append(text[last:])
        text = "".join(out)
    return text


_CJK_RE = re.compile(r"[一-鿿㐀-䶿，。？！、]")


def _tarot_text_ok(text: str) -> bool:
    """보강본 채택 전 청정성 검사 — 타로 본문은 한자·중국어 구두점이 필요 없는 도메인.

    (사주와 달리 간지·용신 표기가 없으므로) 한자가 한 글자라도 섞이면 중국어 드리프트로
    간주하고 기각한다. qwen이 중국어 지시문을 통째로 유출한 사례(QC 2026-07-03)의 결정적 방어.
    """
    return chat_service._looks_korean_clean(text) and not _CJK_RE.search(text)


def _refine_len_ok(refined: str, original: str) -> bool:
    """보강 결과 채택 가드 — 보강이 본문을 크게 축약(요약 사고)하면 원문을 유지한다.

    채택 조건: 보강본이 원문의 60% 이상이거나, 절대 분량 1,200자 이상.
    (추가질문처럼 원문이 짧은 경우는 상대 기준이 자연스럽게 허용)
    """
    r = len(refined.strip())
    return r >= int(len(original.strip()) * 0.6) or r >= 1200


def _compose_tarot_sys(base: str, dialect: str | None, locale: str = "ko") -> str:
    """타로용 시스템 프롬프트 합성 — 사주 전용 규칙(간지/대운/용신) 대신 상담체 규칙만 주입.

    vi 는 한국어 방언·상담체 규칙(ko)을 주입하면 언어 충돌 → vi 전용 줄글 규칙만 덧붙인다."""
    if locale == "vi":
        return base + "\n\n" + TAROT_STYLE_RULE_VI
    parts = [base]
    di = chat_service._dialect_instruction(dialect)
    if di:
        parts.append(di)
    parts.append(chat_service.CONSULTANT_STYLE_RULE)  # 마크다운 금지·상담체 줄글(전 메뉴 공통)
    return "\n\n".join(parts)


# ============================================================
# 스트리밍 해석 / 추가질문 (SSE) — compat.stream_message 미러
# ============================================================
def stream_message(
    db: Session,
    tarot_id: str,
    message: str,
    user: User | None = None,
    depth: str = "deep",
):
    """SSE 제너레이터 — (event, data) 튜플 yield. 궁합 스트림과 동일 구조.

    - 첫 호출(아직 해설 없음): 스프레드 전체 해석. create 시 입장료에 포함 → 추가 무과금.
    - 이후 호출(추가질문): depth(basic/deep)별 과금(무료한도 미적용 — 궁합과 동일).
    """
    row = db.get(TarotSession, tarot_id)
    if row is None:
        raise KeyError(tarot_id)
    if row.user_id is not None and (user is None or user.id != row.user_id):
        raise PermissionError("not your tarot session")
    if not row.cards_json:
        yield ("error", {"detail": "cards_not_picked: 먼저 카드를 뽑아 주세요."})
        return

    s = get_settings()
    depth = "deep" if depth == "deep" else "basic"
    message = (message or "").strip()

    brief = _render_spread_for_llm(row)
    dialect = (getattr(user, "answer_dialect", None) or "standard") if user else "standard"
    di = chat_service._dialect_instruction(dialect)
    locale = getattr(row, "locale", "ko")   # 세션 확정 로케일 — 응답 언어·모델 선택(chat 미러)

    has_assistant = any(m.role == "assistant" for m in row.messages)
    is_explain = not has_assistant

    if is_explain:
        # 해석: create(입장료) 차감에 포함 → 추가 무과금. preview 는 세션값 사용.
        is_preview = row.is_preview
        billing_mode = "tarot_explain"
        credits_to_charge = 0
        _base = TAROT_SYSTEM_VI if locale == "vi" else TAROT_SYSTEM
        sys_content = _compose_tarot_sys(_base, dialect, locale)
        _n_cards = len(row.cards_json or [])
        if locale == "vi":
            ucontent = (
                f"{brief}\n\nHãy luận giải trải bài trên theo thứ tự: giải từng vị trí → "
                f"tương tác giữa các lá → tổng hợp → lời khuyên cụ thể cho câu hỏi. "
                f"Xử lý đầy đủ {_n_cards} vị trí, từ 1 đến {_n_cards}, không bỏ sót lá nào."
            )
        else:
            ucontent = (
                f"{brief}\n\n위 스프레드를 포지션별 해석 → 카드 간 상호작용 → 종합 → "
                f"질문에 대한 구체적 조언 순서로 충분히 풀이해 주세요. "
                f"{_n_cards}개 포지션을 1번부터 {_n_cards}번까지 하나도 빠짐없이 각각 다뤄 주세요."
            )
        msgs = [{"role": "system", "content": sys_content}, {"role": "user", "content": ucontent}]
        save_user: str | None = None
    else:
        if not message:
            yield ("error", {"detail": "질문을 입력해 주세요."})
            return
        # 프리미엄 메뉴 추가질문: 무료한도 미적용(항상 1,000/3,000P 차감) — compat 동일
        bill = chat_service._decide_billing(db, user, depth, allow_free_quota=False, claim=True)
        is_preview = bill["is_preview"]
        credits_to_charge = bill["credits_to_charge"]
        billing_mode = bill["billing_mode"]
        _base = (TAROT_SYSTEM_VI + TAROT_FOLLOWUP_HINT_VI) if locale == "vi" else (TAROT_SYSTEM + TAROT_FOLLOWUP_HINT)
        sys_content = _compose_tarot_sys(_base, dialect, locale)
        msgs = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": brief},
        ]
        for m in [mm for mm in row.messages if mm.role in ("user", "assistant")][-12:]:
            msgs.append({"role": m.role, "content": m.content})
        msgs.append({"role": "user", "content": message})
        save_user = message

    _claude_avail = (
        settings_service.get_bool(db, "external_llm_enabled", True)
        and external_llm.is_enabled()
    )
    # vi: 타로 보강 프롬프트(_tarot_refine_qwen/_tarot_claude_refine)는 '한국어로만' 강제라
    # vi 초안을 한국어로 되돌려버린다 → vi 는 보강 단계를 건너뛰고 qwen3 초안을 그대로 사용.
    do_qwen = (not is_preview) and s.deep_local_refine_enabled and locale != "vi"   # 1차 내부 보강(기본·심화)
    do_claude = depth == "deep" and (not is_preview) and _claude_avail and locale != "vi"  # 심화 외부 보강
    will_refine = do_qwen or do_claude

    yield ("meta", {
        "billing_mode": billing_mode,
        "is_preview": is_preview,
        "depth": depth,
        "mode": "explain" if is_explain else "followup",
        "will_refine": will_refine,
    })

    # ---- 1차 토큰 스트리밍 (하트비트 + 미리보기 컷) — compat 동일 ----
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

    _q_text = message or "타로 스프레드 전체 해석"

    # ---- 1차 로컬(exaone) 실패 → 외부(Claude) 폴백 (compat 동일) ----
    local_ok = "e" not in _err
    if not local_ok:
        e = _err["e"]
        fb = None
        if not is_preview:
            fb = _tarot_generate_fallback(
                question=_q_text, spread=brief, dialect_instruction=di or None,
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

    # ---- ① 내부 qwen 보강 (기본·심화 공통, 로컬 1차 정상) ----
    if do_qwen and local_ok and answer_full.strip():
        yield ("stage", {"phase": "draft_done"})
        yield ("stage", {"phase": "refining"})
        qb = None
        for ev in chat_service._bg_with_heartbeat(s, lambda af=answer_full: _tarot_refine_qwen(
                question=_q_text, draft=af, spread=brief, dialect_instruction=di or None)):
            if ev[0] == "result":
                qb = ev[1]
            else:
                yield ev
        if qb and _refine_len_ok(qb, answer_full) and _tarot_text_ok(qb):
            answer_full = qb.strip()
            refined = True
            yield ("refine", {"text": answer_full, "reason": "내부 보강(qwen)"})
        yield ("stage", {"phase": "refine_done"})

    # ---- ② 외부 Claude 보강 (심화 전용, qwen 다음) ----
    if do_claude and local_ok and answer_full.strip():
        yield ("stage", {"phase": "refining"})
        cb = None
        for ev in chat_service._bg_with_heartbeat(s, lambda af=answer_full: _tarot_claude_refine(
                question=_q_text, draft=af, spread=brief, dialect_instruction=di or None)):
            if ev[0] == "result":
                cb = ev[1]
            else:
                yield ev
        if cb and _refine_len_ok(cb, answer_full) and _tarot_text_ok(cb):
            answer_full = cb.strip()
            refined = True
            yield ("refine", {"text": answer_full, "reason": "심화 검증·보강(Claude)"})
        yield ("stage", {"phase": "refine_done"})

    # ---- 표현 정리(자료 인용 말투 + 마크다운 제거 + 카드명 한글화) ----
    if not is_preview and answer_full.strip():
        _scrubbed = chat_service._scrub_source_refs(answer_full)
        _scrubbed = _strip_markdown(_scrubbed or answer_full)
        if locale != "vi":
            _scrubbed = _localize_card_names(_scrubbed)  # vi: 카드 한글명 주입 방지(영문/베트남어 유지)
        if _scrubbed and _scrubbed != answer_full:
            answer_full = _scrubbed
            refined = True
            yield ("refine", {"text": answer_full, "reason": "표현 정리"})

    # ---- 차감/무료 갱신 (추가질문만) ----
    balance_after: int | None = None
    if user is not None:
        # 무료/멤버십 카운터는 _decide_billing(claim=True)에서 원자적으로 선점됨 — 여기서 미증가.
        if credits_to_charge > 0:
            balance_after = auth_service.adjust_credit(
                db, user.id, -credits_to_charge, reason="tarot_q", ref_id=tarot_id
            )
        else:
            balance_after = auth_service.get_balance(db, user.id)

    # ---- 영속 (compat 동일 패턴) ----
    now = datetime.utcnow()
    if save_user is not None:
        db.add(TarotMessage(
            tarot_id=tarot_id, role="user", content=save_user, created_at=now,
            is_preview=False, preview_revealed=True, credits_charged=0,
        ))
    assistant = TarotMessage(
        tarot_id=tarot_id, role="assistant", content=answer_full,
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


# ── 후속 추천질문 (compat 미러 — 해석 아래 칩으로 노출, 추가 상담 유도) ──
_TAROT_FALLBACK = [
    "이 결과에서 제가 조심할 점은요?", "조언 카드를 더 풀어 주세요?",
    "시기적으로 언제쯤 풀릴까요?", "상대방의 마음은 어떤가요?",
    "지금 제가 할 행동 한 가지는요?", "장애물 카드를 극복하려면요?",
]


def generate_tarot_suggestions(db: Session, tarot_id: str, n: int = 6) -> list[str]:
    """타로 해석 맥락으로 후속 추천질문 n개(로컬 LLM, 무과금)."""
    row = db.get(TarotSession, tarot_id)
    if row is None:
        return []
    msgs = [m for m in row.messages if m.role in ("user", "assistant")]
    if not msgs:
        return _TAROT_FALLBACK[:n]
    parts = [f"{'질문' if m.role == 'user' else '답변'}: {(m.content or '')[:400]}" for m in msgs[-4:]]
    return chat_service.suggestions_from_convo("\n".join(parts), n, topic="타로 상담", fallback=_TAROT_FALLBACK)
