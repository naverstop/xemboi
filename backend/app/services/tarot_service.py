"""타로 서비스 — CSPRNG 드로우 확정 + 입장료 차감 + LLM 해석 스트리밍(궁합 미러링).

- 드로우: 세션 생성 시 secrets(CSPRNG) Fisher-Yates 로 78장 셔플 순서 + 카드별 역방향(50%)을
  확정해 DB에 저장(비공개). 사용자가 부채꼴에서 고른 인덱스(0~77)를 그 순서에 매핑.
- picks 는 세션당 1회 확정, 재호출은 저장된 동일 결과 반환(멱등).
- 빌링: 입장료(entry_cost_tarot)는 생성 시 1회 차감(compat 와 동일 메커니즘, 최초 해석 포함).
  추가질문은 depth(basic/deep)별 차감 — chat_service._decide_billing(allow_free_quota=False) 재사용.
- 카드명·방향·포지션은 서버 결정값을 그대로 렌더. LLM 은 해석 본문만 생성(창작 금지).
"""
from __future__ import annotations

import logging
import queue as _queue
import re
import secrets
import threading
import uuid
from datetime import datetime
from typing import Any

_log = logging.getLogger("saju.tarot")

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
   각 카드에 '해설'이 주어지면 그 해설의 영역별(성격·연애·재물·직업·건강·조언) 내용을 질문·포지션 맥락에
   맞게 근거로 활용하되, 그대로 베끼지 말고 이 사람의 질문에 맞춰 풀어 쓰세요.
   종합·마무리에서는 앞서 포지션별로 이미 서술한 문장·표현을 그대로 되풀이하지 말고, 카드들을 관통하는
   새로운 흐름·통찰과 실행 조언만 담으세요(같은 말을 결론에서 반복하면 분량만 늘 뿐 빈약해집니다).
3. 단정적인 길흉 판정 대신 가능성과 행동 조언 중심으로 설명하세요. 타로는 확정된 미래가 아니라 현재 흐름의 거울임을 전제로 하세요.
   "반드시 ~됩니다", "100%", "틀림없이" 같은 확언은 쓰지 마세요.
4. 충분히 풍부하게 설명하세요 — 7장 스프레드는 최소 2,600자, 11장 스프레드는 최소 4,000자(운영자 상향).
   포지션마다 ①카드 그림·상징이 말하는 것 ②그 의미를 질문 상황에 구체적으로 대입 ③그로 인한 조언·주의점
   세 겹을 담아 5~8문장으로 서술하세요. 모든 포지션을 하나도 빠짐없이 각각 다루고(후반 포지션 뭉뚱그림 금지),
   앞 포지션과 뒤 포지션의 분량을 비슷하게 유지하세요.
5. "~합니다" 존댓말을 사용하고, 사용자를 존중하는 부드러운 상담 어조를 유지하세요.
   질문 문장을 그대로 반복하며 시작하지 말고, 상담사가 말을 건네듯 자연스럽게 시작하세요.
6. 마무리는 결과 카드의 톤을 유지하세요. 부정적·유보적 카드인데 근거 없는 응원 덕담으로 끝내지 마세요.
7. 조언은 질문자가 실행할 수 있는 구체적 행동 1~3가지(무엇을, 어떤 순서로)로 제시하세요.
8. 의료 금지: 질병명을 단정하거나 진단·예후처럼 말하지 마세요("갑상선이다", "자궁질환이 있다", "암이 온다" 등 금지).
   사용자가 건강을 묻지 않았다면 건강·질병 이야기를 먼저 꺼내지 마세요. 건강을 물었더라도 진단이 아니라
   생활 관리 관점의 일반적 조언으로만 다루고, 이상이 느껴지면 의료기관 진료를 권하는 문장으로 마무리하세요.
9. 금전·투자·법률 등도 확정 수익·구체적 금액·기한을 단정하지 마세요(가능성과 준비 관점으로 서술).
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
TAROT_PROSE_STYLE_RULE = (
    "[작성 형식 — 필수] 마크다운(헤더 #, 굵게 **, 목록 -·*, 번호 1., 표, 구분선 '---')을 "
    "쓰지 말고, 상담가가 마주 앉아 이야기하듯 자연스러운 줄글 문단으로만 쓰세요. "
    "문단마다 충분한 문장(3문장 이상)으로 근거→해석→조언을 풀어 쓰고, 한 줄로 끊어 "
    "나열하거나 내용이 빈약해지면 안 됩니다."
)


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
    "★[의료·민감] 질병명을 단정하거나 진단·예후처럼 말하지 마세요. 사용자가 먼저 묻지 "
    "않았으면 건강·죽음 이야기를 먼저 꺼내지 말고, 물으면 생활 관리 수준의 일반 조언과 "
    "의료기관 진료 권유로 마무리하세요. 금전·투자·법률도 확정적으로 단정하지 마세요.\n"
)

TAROT_GENERATE_SYSTEM = (
    "당신은 한국어로 상담하는 타로 상담사입니다. 주어진 [타로 스프레드](질문·섹션·포지션별 "
    "카드·방향·키워드)에 기반해 해석하세요.\n"
    "원칙:\n"
    "1. 카드명·방향·포지션은 주어진 값만 사용하세요(창작 금지).\n"
    "2. 포지션별 해석(각 5~8문장: 상징 → 질문 대입 → 조언) → 카드 상호작용 → 종합 → 구체적 조언 "
    "순으로, 최소 2,600자 이상(11장 스프레드는 4,000자 이상).\n"
    "3. 단정적 길흉 대신 가능성·행동 조언 중심, \"~합니다\" 존댓말.\n"
    "4. 마크다운 없이 자연스러운 줄글 문단으로만, 최종 본문만 출력하세요.\n"
    "★[의료·민감] 질병명을 단정하거나 진단·예후처럼 말하지 마세요. 사용자가 먼저 묻지 "
    "않았으면 건강·죽음 이야기를 먼저 꺼내지 말고, 물으면 생활 관리 수준의 일반 조언과 "
    "의료기관 진료 권유로 마무리하세요. 금전·투자·법률도 확정적으로 단정하지 마세요.\n"
)

# 타로 해설 전용 생성 상한 — 장문(2배 풍부화) 목표가 전역 num_predict(3072tok)에 잘리지 않게 확장.
# num_ctx(16384) 안이므로 안전. 보강(qwen)·재생성·스트림 모두 동일 상한 사용.
TAROT_EXPLAIN_NUM_PREDICT = 6144

# 베트남어(vi) 폴백 생성 프롬프트 — ko TAROT_GENERATE_SYSTEM 대응(로컬 엔진 전체 다운 시 vi 본문 생성).
TAROT_GENERATE_SYSTEM_VI = (
    "Bạn là một nhà tư vấn Tarot tiếng Việt. Hãy luận giải dựa trên [trải bài] đã cho "
    "(câu hỏi·chủ đề·lá theo vị trí·chiều·từ khoá).\n"
    "Nguyên tắc:\n"
    "1. Chỉ dùng đúng tên lá·chiều·vị trí đã cho, không bịa ra lá·chiều·vị trí mới.\n"
    "2. Theo thứ tự: giải từng vị trí → tương tác giữa các lá → tổng hợp → lời khuyên cụ thể.\n"
    "3. Tránh phán hung/cát tuyệt đối; tập trung vào khả năng và lời khuyên hành động. "
    "Không dùng \"chắc chắn\", \"100%\".\n"
    "4. Viết thành các đoạn văn tự nhiên (không markdown), chỉ xuất phần luận giải. "
    "Chỉ dùng tiếng Việt có dấu; TUYỆT ĐỐI không dùng chữ Hán / tiếng Trung.\n"
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


# 카드 해설에 운영자가 붙여둔 '건강은 …' 노트(줄 단위) — 무면허 의료 서술 리스크가 있어
# 인생 종합(life) 이외 섹션(연애·금전·직업·학업·선택)에는 주입하지 않는다.
# 실측(2026-07-11): 156필드 중 33건에만 존재하며, 제거해도 일반 리딩 본문은 온전히 남는다(빈 본문 0건).
_HEALTH_NOTE_RE = re.compile(r"[ \t]*건강[은도][^\n]*", re.MULTILINE)
_HEALTH_OK_SECTIONS = {"life"}   # 인생 종합·심층에서만 건강 노트 허용


def _strip_health_notes(text: str) -> str:
    """'건강은/건강도 …' 로 시작하는 부분을 그 줄 끝까지 제거(앞 내용은 보존)."""
    out = _HEALTH_NOTE_RE.sub("", text or "")
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def _render_spread_for_llm(row: TarotSession) -> str:
    """LLM 입력 컨텍스트 — 질문/섹션/스프레드/포지션별 확정 카드."""
    section_label = tarot_deck.SECTION_LABELS.get(row.section, row.section)
    allow_health = row.section in _HEALTH_OK_SECTIONS
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
        if interp and not allow_health:
            interp = _strip_health_notes(interp)   # 주제와 무관한 건강/질병 서술 주입 차단
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
        "positions": tarot_deck.localized_positions(spread_type, locale),
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
    positions_vi = tarot_deck.SPREAD_POSITIONS_VI.get(row.spread_type, [])
    cards = [
        tarot_deck.card_payload(
            k, positions[k], order[idx], bool(flags[idx]),
            position_name_vi=(positions_vi[k] if k < len(positions_vi) else ""),
        )
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
    resp_positions = tarot_deck.localized_positions(row.spread_type, getattr(row, "locale", "ko"))
    messages = []
    for m in row.messages:
        content = m.content
        if m.is_preview and not m.preview_revealed:
            content = chat_service._make_preview(content)
        if m.role == "assistant":
            content = chat_service.fix_term_hanja(content)   # 저장본 재열람 정리(멱등) — '---' 등 소급
            content = _repair_question_terms(content, row.question or "")  # 질문어 1글자 손상 소급 복원
        # 잔류 한자(嗎·結果 등) 소급 세탁 — 답변뿐 아니라 '클릭한 추천질문(user)'에 샌 한자도(스샷 사례).
        content = _dehanja_tarot(content)
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
        "positions": resp_positions,
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
            # 장문 해설(풍부화 2배)을 보강이 다시 뱉어야 하므로 생성 상한도 동일하게 확장
            out = chat_service._call_ollama(msgs, model=s.ollama_refine_model, temperature=temp,
                                            num_predict=TAROT_EXPLAIN_NUM_PREDICT)
        except chat_service.ServiceUnavailableError:
            return None
        out = (out or "").strip()
        if chat_service._looks_korean_clean(out):
            return out
    return None


def _tarot_claude_call(system: str, user_block: str, *, allow_overseas: bool = False) -> str | None:
    """외부(Claude) 호출 공통 — external_llm 의 클라이언트/모델 결정 재사용(타로 시스템 프롬프트).

    allow_overseas: 국외이전 동의 게이트(H4, 개인정보보호법 제28조의8). False면 전송하지 않는다.
    기본값 False(fail-closed) — 호출부가 게이트를 빠뜨리면 전송되지 않고 조용히 None 이 된다.
    """
    if not allow_overseas:
        return None
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


def _tarot_claude_refine(
    *, question: str, draft: str, spread: str, dialect_instruction: str | None,
    allow_overseas: bool = False,
) -> str | None:
    """외부(Claude) 심화 보강 — external_llm.refine_answer 미러(타로 프롬프트). 미동의 시 전송 안 함."""
    parts = [spread, f"[사용자 질문]\n{question}", f"[1차 해석(보강 대상)]\n{draft}"]
    if dialect_instruction:
        parts.append(dialect_instruction)
    # 국외전송 가명화(#4) — 사주챗과 동일하게 정확 나이를 연령대로 일반화 후 전송.
    return _tarot_claude_call(
        TAROT_REFINE_SYSTEM, external_llm._pseudonymize_for_transfer("\n\n".join(parts)),
        allow_overseas=allow_overseas,
    )


def _tarot_generate_fallback(
    *, question: str, spread: str, dialect_instruction: str | None,
    allow_overseas: bool = False, locale: str = "ko",
) -> str | None:
    """로컬 엔진 전체 다운 시 외부(Claude)로 본문 생성 폴백 — external_fallback_answer 미러. 미동의 시 전송 안 함.

    vi 로케일이면 vi 프롬프트/질문 라벨을 쓰고, ko 방언 지시는 주입하지 않는다(언어 충돌 방지)."""
    q_label = "[Câu hỏi]" if locale == "vi" else "[사용자 질문]"
    parts = [spread, f"{q_label}\n{question}"]
    if dialect_instruction and locale != "vi":
        parts.append(dialect_instruction)
    system = TAROT_GENERATE_SYSTEM_VI if locale == "vi" else TAROT_GENERATE_SYSTEM
    # 국외전송 가명화(#4) — 정확 나이를 연령대로 일반화 후 전송.
    return _tarot_claude_call(
        system, external_llm._pseudonymize_for_transfer("\n\n".join(parts)),
        allow_overseas=allow_overseas,
    )


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


# 한글 카드명이 일반어와 겹쳐 오탐을 내는 카드 — 본문 대조에서 한글명 검사는 제외(영문명으로만 검사)
_AMBIGUOUS_KR = {"힘", "별", "달", "태양", "세계", "연인", "정의", "심판", "죽음", "절제", "탑", "바보"}
_ONLY_HANGUL = re.compile(r"[가-힣]+")


def _verify_body_against_cards(text: str, cards: list[dict[str, Any]]) -> dict[str, list[str]]:
    """생성 본문을 '확정 카드'와 대조(런타임 검증). 텍스트를 바꾸지 않고 문제만 보고한다.

    E) offspread : 이번 스프레드에 없는 카드가 본문에 등장(환각). 영문명 + 비모호 한글명으로 검사.
    F) direction : 확정 방향과 본문 서술이 어긋남(카드명 뒤 24자 내 '정방향/역방향' 토큰 대조).
    ※ _localize_card_names(영문→한글 치환) 이전에 호출해야 영문 환각이 세탁되기 전에 잡힌다.
    """
    drawn = {str(c.get("code", "")) for c in (cards or [])}
    offspread: list[str] = []
    for c in tarot_deck.all_cards():
        if c["code"] in drawn:
            continue
        en, kr = c["name_en"], c["name_kr"]
        if en and en in text:
            offspread.append(f"{kr}({en})")
        elif kr and kr not in _AMBIGUOUS_KR and kr in text:
            offspread.append(kr)

    mismatch: list[str] = []
    for c in (cards or []):
        kr = str(c.get("name_kr") or "")
        if not kr or kr in _AMBIGUOUS_KR:
            continue
        want = "역방향" if c.get("orientation") == "reversed" else "정방향"
        other = "정방향" if want == "역방향" else "역방향"
        for m in re.finditer(re.escape(kr), text):
            win = text[m.end():m.end() + 24]
            if other in win and want not in win:
                mismatch.append(f"{kr}: 확정 {want} → 본문 {other}")
                break
    return {"offspread": sorted(set(offspread)), "direction": mismatch}


def _repair_question_terms(text: str, question: str) -> str:
    """사용자 질문어의 1글자 손상형을 결정적으로 복원(포인트 수정).

    qwen 등이 드물게 음절 하나를 깨뜨린다(예 '레트로축제'→'렆트로축제', 렆=레+ㅂ받침).
    질문과 본문에 '공통으로' 등장하는 고유 한글어(4자+)만 앵커로 삼고, 본문에서 그와 정확히
    1음절만 다른 같은 길이 구간을 정답으로 되돌린다. 앵커가 정답 형태로 본문에 실존할 때만
    동작하므로(질문에만 있는 게 아니라 본문에도 최소 1회 정상 등장) 오탐이 극소화된다.
    """
    if not text or not question:
        return text
    terms: set[str] = set()
    for L in range(10, 3, -1):                       # 긴 것 우선(4~10자)
        for i in range(len(question) - L + 1):
            g = question[i:i + L]
            if _ONLY_HANGUL.fullmatch(g) and g in text:
                terms.add(g)
    terms_l = [t for t in terms if not any(t != u and t in u for u in terms)]  # 최장 토큰만
    for term in sorted(terms_l, key=len, reverse=True):
        L = len(term)
        out: list[str] = []
        i = 0
        n = len(text)
        while i < n:
            if i <= n - L:
                win = text[i:i + L]
                if win == term:
                    out.append(term); i += L; continue
                if sum(1 for a, b in zip(win, term) if a != b) == 1:  # 1음절만 손상 → 복원
                    out.append(term); i += L; continue
            out.append(text[i]); i += 1
        text = "".join(out)
    return text


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


# 중국어 문말·기능 조사 — 한자 독음이 있어도 한국어 문장에선 드리프트이므로 음역 말고 제거.
_CJK_DROP = set("了的是嗎吗呢吧啊哦嘛呀么麼喇嘞喔唄囉咧咯哩呐嗯喲欸誒咦嘿")
_CJK_PUNCT = {"，": ", ", "。": ". ", "？": "? ", "！": "! ", "、": " · ", "；": "; ", "：": ": ",
              "（": "(", "）": ")", "「": "'", "」": "'", "『": '"', "』": '"', "《": "<", "》": ">"}
_CJK_IDEO_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")


def _dehanja_tarot(text: str) -> str:
    """타로 본문의 잔류 한자·중국어를 결정적으로 한글화/제거 — 타로는 CJK 미허용 도메인.

    qwen3 전환(2026-07-16) 후 보강(qwen)이 OFF면 draft 가 CJK 가드를 안 거쳐, 간헐 드리프트
    (예: '맞아 보여嗎?'의 嗎, '結果로'의 結果)가 그대로 노출됐다(운영자 보고). refine 채택 가드
    (_tarot_text_ok)와 별개로, 최종 표시 직전 결정적으로 세탁한다:
      - 한자 단어는 한글 독음으로 치환(結果→결과, 現在→현재, 財物→재물)
      - 독음 없는 자·중국어 문말 조사는 제거(嗎→'')
      - 중국어 구두점은 한글/ASCII 로 치환
    """
    if not text or not _CJK_RE.search(text):
        return text
    from backend.app.saju.naming import _reading  # 한자→대표 한글독음(지연 임포트)
    cjk_n = 0
    out: list[str] = []
    for ch in text:
        if ch in _CJK_PUNCT:
            out.append(_CJK_PUNCT[ch])
            continue
        if _CJK_IDEO_RE.match(ch):
            cjk_n += 1
            if ch in _CJK_DROP:
                continue
            try:
                rd = _reading(ch)
            except Exception:  # noqa: BLE001
                rd = ""
            out.append(rd or "")   # 독음 없으면 제거
            continue
        out.append(ch)
    res = "".join(out)
    res = re.sub(r"[ \t]{2,}", " ", res)      # 제거로 생긴 이중 공백
    res = re.sub(r" +([.,!?)\]…])", r"\1", res)  # 문말 조사 제거로 생긴 '구두점 앞 공백'
    if cjk_n:
        _log.warning("tarot CJK drift cleaned: %d char(s)", cjk_n)  # 대량이면 모델 드리프트 신호
    return res


def _refine_len_ok(refined: str, original: str, *, min_ratio: float = 0.6,
                   allow_abs: int | None = 1200) -> bool:
    """보강 결과 채택 가드 — 보강이 본문을 크게 축약(요약 사고)하면 원문을 유지한다.

    기본(추가질문): 원문의 60% 이상 또는 절대 1,200자 이상.
    해석(explain)은 풍부화 2배 목표라 min_ratio=0.8, allow_abs=None 로 호출 —
    4,000자 초안을 1,200자로 요약한 보강이 절대 기준으로 새는 것을 차단(운영자 풍부화 지시).
    """
    r = len(refined.strip())
    if r >= int(len(original.strip()) * min_ratio):
        return True
    return allow_abs is not None and r >= allow_abs


# 한국어 상담문이 정상 종결됐는지 — num_predict 상한 절단(문장 중간 끊김) 채택 방지.
_CLEAN_END_RE = re.compile(r"[다요죠.!?…”\"』」)\]]\s*$")


def _ends_clean(text: str) -> bool:
    return bool(_CLEAN_END_RE.search((text or "").rstrip()[-8:]))


def _trim_to_sentence(text: str) -> str:
    """끝이 문장 중간이면 마지막 완결 문장까지로 결정적 절단(저장·표시 전 최종 안전망)."""
    t = (text or "").rstrip()
    if not t or _ends_clean(t):
        return text
    m = None
    for m in re.finditer(r"[다요죠.!?…”\"』」)\]](?=\s|$)", t):
        pass
    return t[: m.end()] if m else text


def _compose_tarot_sys(base: str, dialect: str | None, locale: str = "ko") -> str:
    """타로용 시스템 프롬프트 합성 — 사주 전용 규칙(간지/대운/용신) 대신 상담체 규칙만 주입.

    vi 는 한국어 방언·상담체 규칙(ko)을 주입하면 언어 충돌 → vi 전용 줄글 규칙만 덧붙인다."""
    if locale == "vi":
        return base + "\n\n" + TAROT_STYLE_RULE_VI
    parts = [base]
    di = chat_service._dialect_instruction(dialect)
    if di:
        parts.append(di)
    # [교차검증 2026-07-22] 예전에는 chat 의 CONSULTANT_STYLE_RULE 을 그대로 빌려 썼다
    # (주석도 '마크다운 금지'였다). 그런데 그 규칙이 사주 답변용으로 **마크다운을 요구하는**
    # 내용으로 바뀌면서 타로만 발밑이 뒤집혔다 — 타로는 자체 프롬프트 2곳이 마크다운을 금지하고
    # (TAROT_SYSTEM 4항·TAROT_GENERATE_SYSTEM 4항) 코드(_strip_markdown)가 실제로 제거한다.
    # 지시와 코드가 싸우면 모델이 '**'를 붙였다가 잘려 문장이 깨진다 → 빌려 쓰지 않고
    # 타로에 맞는 줄글 규칙을 직접 둔다. ⚠️CONSULTANT_STYLE_RULE 을 다시 붙이지 말 것.
    parts.append(TAROT_PROSE_STYLE_RULE)
    return "\n\n".join(parts)


# ============================================================
# 포지션 커버리지 가드 — 조기 중단(예: 7카드 호스슈가 3번에서 요약으로 뭉개짐) 방어
#   실측(2026-07-09, 구 exaone): 해설 주입 유무와 무관하게 드래프트가 호스슈(7)를 종종 3번까지만
#   번호로 다루고 뒤를 뭉뚱그린다(11카드 켈틱은 안정적). 구조 강제 프롬프트로 기본율을 올리고,
#   그래도 누락되면 누락 포지션만 결정적으로 이어 붙인다(헤더는 코드가 붙여 커버 100% 보장).
# ============================================================
def _covered_positions(text: str, need: int) -> set[int]:
    """본문에서 'N.' 또는 'N)' 로 시작하는 번호 문단이 등장한 포지션 집합.

    ⚠️ 마크다운 헤더 접두(#·**)를 허용해야 한다 — qwen3(2026-07-16 메인 엔진)는 포지션
    헤더를 '### 1. 과거:' 처럼 H3로 쓴다. 접두 미허용 시(구 exaone용 정규식) 전 포지션이
    '누락'으로 오판돼 커버리지 가드가 100% 헛발동(불필요 재생성·중복·수백초 지연). 표시 단계
    _strip_markdown 이 어차피 #·** 를 걷어내므로 감지만 접두에 관대하게 한다.
    """
    return {n for n in range(1, need + 1)
            if re.search(rf"(^|\n)[ \t]*(?:#{{1,6}}[ \t]*)?(?:\*+[ \t]*)?{n}[.)]", text)}


def _missing_positions(text: str, need: int) -> list[int]:
    covered = _covered_positions(text, need)
    return [n for n in range(1, need + 1) if n not in covered]


def _gen_position_fill(sys_content: str, brief: str, card: dict, di: str | None) -> str:
    """누락된 단일 포지션 본문만 생성해 '번호. 포지션명 — 카드(방향)' 헤더(코드가 부여)와 결합.

    헤더를 코드가 붙이므로 커버리지 감지는 결정적으로 통과한다(모델 번호 누락과 무관).
    """
    n = card["position_index"] + 1
    is_rev = card["orientation"] == "reversed"
    ori = "역방향" if is_rev else "정방향"
    kw = ", ".join(card.get("keywords") or [])
    interp = tarot_deck.interp_for(card.get("code", ""), is_rev).strip()
    uc = (
        f"{brief}\n\n[집중 해석] {n}번 포지션 '{card['position_name']}'에 놓인 "
        f"{card['name_kr']}({ori}) 카드만 3~5문장으로 해석하세요. 이 방향의 의미: {kw}."
    )
    if interp:
        uc += f" 참고 해설(그대로 베끼지 말 것): {interp}"
    uc += " 번호·포지션명 헤더 없이 해석 본문 문장만 쓰세요."
    if di:
        uc += f"\n{di}"
    try:
        body = chat_service._call_ollama(
            [{"role": "system", "content": sys_content}, {"role": "user", "content": uc}],
            temperature=0.5,
        )
    except chat_service.ServiceUnavailableError:
        return ""
    body = _strip_markdown((body or "").strip()).strip()
    if not body:
        return ""
    header = f"{n}. {card['position_name']} — {card['name_kr']}({ori})"
    return f"{header}\n{body}"


def _fill_missing_positions(sys_content: str, brief: str, cards: list, miss: list[int],
                            di: str | None) -> str:
    """누락 포지션들을 순서대로 결정적 보완, 이어 붙일 블록 문자열 반환('' 이면 실패)."""
    by_pos = {c["position_index"] + 1: c for c in cards}
    blocks = [b for n in miss if (b := _gen_position_fill(sys_content, brief, by_pos[n], di))]
    return "\n\n".join(blocks)


def _regen_explain(sys_content: str, ucontent: str) -> str | None:
    """해석 전체 1회 재생성(동일 구조 프롬프트) — 조기중단 시 중복 없는 깔끔한 복구용."""
    try:
        out = chat_service._call_ollama(
            [{"role": "system", "content": sys_content}, {"role": "user", "content": ucontent}],
            temperature=0.5, num_predict=TAROT_EXPLAIN_NUM_PREDICT,
        )
    except chat_service.ServiceUnavailableError:
        return None
    return (out or "").strip() or None


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
    """공개 진입점 — 내부 스트림을 감싸 '예상 밖 예외'에서도 선차감을 보상한다.

    [버그 2026-07-25] free-ride 차단을 위해 추가질문은 답변 생성 '전'에 유료차감을 확정 커밋한다
    (tool_service·compat·dream 과 동일 설계). 그런데 내부 방어분기(LLM 장애·빈 답변·저장 실패) '밖'에서
    예외가 나면(후처리 동기함수 _strip_markdown/_localize_card_names/_trim_to_sentence 등) api/tarot.py 의
    포괄 except 가 삼켜 error 만 내보내고 환불하지 않아, 답변을 못 받은 채 실포인트(1,000/3,000P)가
    사라졌다 → 재질문 시 이중차감. tool_service.stream_message·dream 과 동일한 catch-all 보상 래퍼로 닫는다.

    이중환불 방지: 내부가 스스로 환불한 지점에서는 receipt 를 비운다(_receipt.clear()).
    ⚠️ GeneratorExit(클라 이탈)은 환불하지 않고 그대로 올린다 — free-ride 차단 규약.
    """
    receipt: dict[str, Any] = {}
    try:
        yield from _stream_message_inner(
            db, tarot_id, message, user=user, depth=depth, _receipt=receipt)
    except GeneratorExit:
        raise                       # 클라 이탈 — 정상 종료 경로(과금 유지)
    except Exception as e:  # noqa: BLE001
        if receipt.get("bill") is not None:
            try:
                db.rollback()
                chat_service.refund_followup(
                    db, user, receipt["bill"], receipt.get("pre_charged", 0),
                    reason="tarot_q", ref_id=tarot_id)
            except Exception:  # noqa: BLE001 — 보상 실패가 에러 전달을 막지 않는다
                pass
        import logging
        logging.getLogger("saju.tarot").warning("tarot stream failed(refunded): %s", e)
        yield ("error", {"detail": "답변 처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
                         "code": "internal_error"})


def _stream_message_inner(
    db: Session,
    tarot_id: str,
    message: str,
    user: User | None = None,
    depth: str = "deep",
    _receipt: dict[str, Any] | None = None,
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
            # 구조 강제(실측: 호스슈 7카드가 3번에서 요약으로 뭉개지는 조기중단 방어) — 번호 문단 강제 +
            # 뒤 포지션 분량 균형 + '해설'은 참고자료(복붙 금지). 부족분은 아래 커버리지 가드가 결정적 보완.
            # 예시 헤더는 실제 1번 포지션명으로 조립 — '포지션명'이라는 플레이스홀더를 쓰면 모델이
            # 문자 그대로 "1. 포지션명: 과거"로 출력한 실사례(운영자 보고 스크린샷)가 있어 금지.
            _pos1 = (row.cards_json[0].get("position_name") or "과거") if row.cards_json else "과거"
            _min_chars = 4000 if _n_cards >= 11 else 2600   # 풍부화 2배 목표(운영자 지시 2026-07-15)
            ucontent = (
                f"{brief}\n\n"
                f"먼저 {_n_cards}개 포지션을 각각 '1. {_pos1}:'처럼 번호와 그 자리의 포지션 이름으로 "
                f"시작하는 번호 문단으로 1번부터 {_n_cards}번까지 빠짐없이 하나씩 해석하세요. "
                f"절대 3~4번에서 멈추거나 뒤 포지션을 하나로 묶지 마세요 — {_n_cards}개 번호 문단이 "
                f"모두 있어야 하며, 뒤 포지션도 앞과 같은 분량으로 다루세요. 각 포지션은 5~8문장으로: "
                f"①카드 그림·상징이 말하는 것 ②그 의미를 이 질문 상황에 구체적으로 대입 ③그로 인한 "
                f"조언·주의점까지 세 겹을 담고, 카드 한글명·방향을 명시하세요. 각 카드의 '해설:'은 참고 "
                f"자료이니 그대로 베끼지 말고 이 질문·포지션에 맞게 소화해 쓰세요.\n"
                f"{_n_cards}개 번호 문단을 마친 뒤에는 ②카드 간 상호작용(서로 강화·충돌하는 조합 2가지 "
                f"이상을 짚어 두 문단) → ③종합(질문에 대한 답을 분명히 하는 문단) → ④구체적 조언(실행 "
                f"순서가 있는 3~5가지) 순서로 풍부하게 마무리하세요. 전체 분량은 최소 {_min_chars}자 "
                f"이상으로 충분히 자세히 쓰세요."
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
        # free-ride 차단: 추가질문 유료차감·멤버십 선점을 '생성 전' 확정 커밋(끝 커밋은 disconnect 시 롤백됨).
        _pre_charged = chat_service.precharge_followup(db, user, bill, reason="tarot_q", ref_id=tarot_id)
        # 미정산 청구 등록 — 아래 방어분기를 벗어난 예외가 나면 래퍼(stream_message)가 이걸 보고 보상한다.
        if _receipt is not None and not is_explain:
            _receipt.update(bill=bill, pre_charged=_pre_charged)
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
            # 해석(장문 풍부화)은 전역 num_predict(3072tok)에 잘리지 않게 확장 상한 사용
            _np = TAROT_EXPLAIN_NUM_PREDICT if is_explain else None
            for tok in chat_service._stream_ollama(
                msgs, model=chat_service._draft_model(locale), stop_event=stop_event, num_predict=_np
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

    _q_text = message or "타로 스프레드 전체 해석"

    # ---- 1차 로컬(qwen3:14b) 실패 → 외부(Claude) 폴백 (compat 동일) ----
    local_ok = "e" not in _err
    if not local_ok:
        e = _err["e"]
        fb = None
        if not is_preview:
            # 국외이전 게이트(H4, 제28조의8) — 전역 폴백 설정 ON + 회원 동의일 때만 전송(compat/tool 동일).
            fb = _tarot_generate_fallback(
                question=_q_text, spread=brief, dialect_instruction=di or None, locale=locale,
                allow_overseas=(settings_service.get_bool(db, "overseas_llm_fallback_enabled", False)
                                and getattr(user, "overseas_transfer_opt_in", False)),
            )
        if fb:
            parts = [fb]
            yield ("refine", {"text": fb, "reason": "로컬 엔진 불가 — 외부 AI 폴백"})
        elif isinstance(e, chat_service.ServiceUnavailableError):
            if not is_explain:   # explain 은 입장료 커버(precharge 안 함) — bill/_pre_charged 미정의라 환불도 하지 않음
                chat_service.refund_followup(db, user, bill, _pre_charged, reason="tarot_q", ref_id=tarot_id)
                if _receipt is not None: _receipt.clear()   # 자체 환불 완료 — 래퍼의 이중환불 차단
            yield ("error", {"detail": str(e), "code": "service_unavailable"})
            return
        else:
            if not is_explain:
                chat_service.refund_followup(db, user, bill, _pre_charged, reason="tarot_q", ref_id=tarot_id)
                if _receipt is not None: _receipt.clear()   # 자체 환불 완료 — 래퍼의 이중환불 차단
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
        # 해석(explain)에서는 보강이 커버된 포지션을 되레 줄이면(요약 사고) 기각 — 완성도 회귀 방지.
        _cov_ok = (not is_explain) or len(_covered_positions(qb or "", need_cov)) >= len(
            _covered_positions(answer_full, need_cov))
        # 풍부화 가드: 해석은 80% 미만 축약 기각(절대치 우회 금지) + 문장 중간 절단본 기각
        _len_ok = (_refine_len_ok(qb or "", answer_full, min_ratio=0.8, allow_abs=None)
                   if is_explain else _refine_len_ok(qb or "", answer_full))
        _end_ok = (not is_explain) or _ends_clean(qb or "")
        if qb and _len_ok and _tarot_text_ok(qb) and _cov_ok and _end_ok:
            answer_full = qb.strip()
            refined = True
            yield ("refine", {"text": answer_full, "reason": "내부 보강(qwen)"})
        yield ("stage", {"phase": "refine_done"})

    # ---- ② 외부 Claude 보강 (심화 전용, qwen 다음) ----
    if do_claude and local_ok and answer_full.strip():
        yield ("stage", {"phase": "refining"})
        cb = None
        for ev in chat_service._bg_with_heartbeat(s, lambda af=answer_full: _tarot_claude_refine(
                question=_q_text, draft=af, spread=brief, dialect_instruction=di or None,
                allow_overseas=getattr(user, "overseas_transfer_opt_in", False))):
            if ev[0] == "result":
                cb = ev[1]
            else:
                yield ev
        _cov_ok = (not is_explain) or len(_covered_positions(cb or "", need_cov)) >= len(
            _covered_positions(answer_full, need_cov))
        _len_ok = (_refine_len_ok(cb or "", answer_full, min_ratio=0.8, allow_abs=None)
                   if is_explain else _refine_len_ok(cb or "", answer_full))
        _end_ok = (not is_explain) or _ends_clean(cb or "")
        if cb and _len_ok and _tarot_text_ok(cb) and _cov_ok and _end_ok:
            answer_full = cb.strip()
            refined = True
            yield ("refine", {"text": answer_full, "reason": "심화 검증·보강(Claude)"})
        yield ("stage", {"phase": "refine_done"})

    # ---- 표현 정리(자료 인용 말투 + 마크다운 제거 + 카드명 한글화 + 문장 절단 정리) ----
    if not is_preview and answer_full.strip():
        _scrubbed = chat_service._scrub_self_reference(chat_service._scrub_source_refs(answer_full))
        _scrubbed = _strip_markdown(_scrubbed or answer_full)
        # 런타임 대조(E 환각 카드 / F 방향 불일치) — 반드시 한글화 '이전'에.
        # _localize_card_names 가 영문 환각 카드까지 한글로 바꿔 놓으면 흔적이 사라진다.
        try:
            _chk = _verify_body_against_cards(_scrubbed, row.cards_json or [])
            if _chk["offspread"] or _chk["direction"]:
                _log.warning(
                    "tarot body/card mismatch tarot_id=%s section=%s mode=%s offspread=%s direction=%s",
                    tarot_id, row.section, "explain" if is_explain else "followup",
                    _chk["offspread"], _chk["direction"],
                )
        except Exception:  # noqa: BLE001 — 검증 실패가 답변을 막지 않게
            pass
        if locale != "vi":
            _scrubbed = _localize_card_names(_scrubbed)  # vi: 카드 한글명 주입 방지
        _scrubbed = _repair_question_terms(_scrubbed, row.question or "")  # 질문어 1글자 손상 복원(포인트)
        # 공용 정리 체인 — 종전엔 재열람(get_tarot)에만 걸려 있어 **처음 보는 화면**에는
        # '---' 구분선(포지션 사이 전부)과 중복 문장이 그대로 노출됐다(전수감사 실측).
        # 생성·읽기 대칭 원칙에 맞춰 생성 경로에도 적용(멱등).
        _scrubbed = chat_service.fix_term_hanja(_scrubbed)
        _scrubbed = _dehanja_tarot(_scrubbed)  # 잔류 한자·중국어 결정적 세탁(refine OFF 시 draft 방어)
        if is_explain:
            _scrubbed = _trim_to_sentence(_scrubbed)  # num_predict 절단 등 꼬리 파편 제거(최종 안전망)
        if _scrubbed and _scrubbed != answer_full:
            answer_full = _scrubbed
            refined = True
            yield ("refine", {"text": answer_full, "reason": "표현 정리"})

    # 반복 퇴행(같은 구절 폭주) 최종 가드 — 구제되면 정상본(교체본 전송), 구제 실패면 ''(→ 빈답변 경로로 미저장·환불/재시도)
    # 조기중단(_degen_aborted)으로 끊긴 잘린 답은 보수적 판정에 안 걸려도 강제 재생성(force)한다.
    if answer_full.strip() and (_degen_aborted or chat_service._looks_degenerate(answer_full)):
        # [2026-08-04 퀵윈] 동기 직호출(1~4분 완전 무음) → 하트비트 랩 — '무음사망' 차단(운영자 지시).
        #   전수감사에서 타로의 유일한 실결함(P5)으로 판정된 지점. 신년운세·궁합과 동일 패턴.
        _fixed = None
        for ev in chat_service._bg_with_heartbeat(s, lambda af=answer_full: chat_service._correct_degenerate(
                af, sys_content=sys_content,
                base_user=(msgs[1]["content"] if len(msgs) > 1 else ""), force=_degen_aborted),
                progress_phase="verifying"):
            if ev[0] == "result":
                _fixed = (ev[1] or "").strip() if ev[1] is not None else None
            else:
                yield ev
        if _fixed is not None and _fixed != answer_full:
            answer_full = _fixed
            if answer_full and not is_preview:
                refined = True
                yield ("refine", {"text": answer_full, "reason": "반복 정리"})

    # 빈 응답(무내용 또는 구제 불가 퇴행) — 유료 followup 이면 precharge 보상, explain 은 저장 않고 에러(재시도 유도).
    # ⚠️ explain 은 입장료가 create 차감 — 재시도(무과금)로 정상본을 받으므로 재환불하지 않는다(이중환불 위험).
    if not answer_full.strip():
        if not is_explain:
            chat_service.refund_followup(db, user, bill, _pre_charged, reason="tarot_q", ref_id=tarot_id)
            if _receipt is not None: _receipt.clear()   # 자체 환불 완료 — 래퍼의 이중환불 차단
        yield ("error", {"detail": "답변을 생성하지 못했어요. 잠시 후 다시 시도해 주세요.", "code": "internal_error"})
        return

    # ---- 잔액 조회 (차감·선점은 precharge_followup 에서 '생성 전' 완료됨 — 이중차감 금지) ----
    balance_after: int | None = auth_service.get_balance(db, user.id) if user is not None else None

    # ---- 영속 (compat 동일 패턴) ----
    now = datetime.utcnow()
    try:
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
        if not is_explain:                       # 유료 추가질문만 영수증 대상 — EOF 완결 마킹(persist 커밋에 합류)
            from backend.app.services import receipt_service
            receipt_service.finalize_receipt(db, bill.get("receipt_id"), message_id=aid)
        db.commit()
    except Exception:  # noqa: BLE001 — 저장/커밋 실패 시 생성 전 확정한 과금을 보상 원복.
        db.rollback()
        if not is_explain:
            chat_service.refund_followup(db, user, bill, _pre_charged, reason="tarot_q", ref_id=tarot_id)
            if _receipt is not None: _receipt.clear()   # 자체 환불 완료 — 래퍼의 이중환불 차단
        yield ("error", {"detail": "저장 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", "code": "internal_error"})
        return

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
    raw = chat_service.suggestions_from_convo("\n".join(parts), n, topic="타로 상담", fallback=_TAROT_FALLBACK)
    # 추천질문도 qwen3 생성 → 간헐 한자 드리프트를 정리. 소량 한자(結果 등)는 한글 독음으로 세탁하되,
    # 통짜 중국어(한자 비율 높음)는 음역하면 오히려 뜻 모를 gibberish 라 폴백으로 대체한다(클릭 오염 차단).
    out: list[str] = []
    for q in raw:
        qs2 = (q or "").strip()
        n_cjk = len(_CJK_IDEO_RE.findall(qs2))
        n_ch = len(re.sub(r"\s", "", qs2)) or 1
        if n_cjk and n_cjk / n_ch > 0.3:          # 통짜 중국어 드리프트 → 폴백
            out.append("")
            continue
        cq = _dehanja_tarot(qs2)
        out.append(cq if (cq and not _CJK_RE.search(cq)) else "")
    fb = [x for x in _TAROT_FALLBACK if x not in out]
    result = [q or (fb.pop(0) if fb else _TAROT_FALLBACK[0]) for q in out]
    return result[:n]
