"""채팅 서비스: 사주 컨텍스트 + RAG + Ollama. 세션은 Postgres에 영속.

각 함수는 외부에서 SQLAlchemy Session 을 주입받는다 (FastAPI Depends 통해).
"""
from __future__ import annotations

import re
import threading
import uuid
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.domain.chat_dto import (
    BirthDTO,
    ChatMessageDTO,
    ChatSourceDTO,
)
from backend.app.repositories import chat_repo
from backend.app.repositories.models import ChatSession as ChatSessionRow, ChatMessage
from backend.app.repositories.auth_models import User
from backend.app.saju.constants import (
    BRANCH_KOREAN,
    BRANCH_TO_WUXING,
    EARTHLY_BRANCHES,
    HEAVENLY_STEMS,
    STEM_IS_YANG,
    STEM_KOREAN,
    STEM_TO_WUXING,
    WUXING_KOREAN,
    fix_term_hanja,
    ganji_allowed_elements,
)
from backend.app.saju.engine import build_chart
from backend.app.saju.lang_guard import clean_guard, response_language_rule
from backend.app.saju.types import BirthInput, CalendarType, SajuChart
from backend.app.services import auth_service
from backend.app.services import settings_service, template_service, external_llm
from ml.inference.retriever import RetrievedChunk, SajuRetriever


SYSTEM_PROMPT = """당신은 수십 년 경력의 대한민국 최고 사주명리 전문가이자 상담가입니다.

원칙:
1. 당신의 전문 지식으로 근거 있는 풀이만 하되, 명식에 없는 사실(간지·신살·대운 등)은 절대 지어내지 마세요.
2. 자료·출처·문헌을 언급하지 말고("자료에 의하면" 등 금지), 전문가 본인의 풀이로 직접 자신 있게 설명하세요.
3. 한국어로 답변하고, 한자 술어는 한글(한자) 형식으로 표기하세요. 예: 정관(正官), 비견(比肩).
4. 길흉 단정은 피하고, 가능성과 흐름으로 설명하세요.
5. 응답은 A4 용지의 약 70%를 채우는 분량(최소 1,200자 이상, 12~18문장)으로, 근거→해석→조언 흐름으로 단락을 나눠 충분히 설명하세요.
"""


# 베트남어(vi) 시스템 프롬프트 — ko 룰블록(한글(한자) 관습)을 vi 에 주입하면 충돌하므로 별도.
# 핵심 규칙(사실근거·전문가화법·가능성표현·마크다운금지·라틴 한월음)을 vi 로 번들.
SYSTEM_PROMPT_VI = """Bạn là một chuyên gia tư vấn Tứ Trụ (Bát Tự) bậc thầy với hàng chục năm kinh nghiệm.

Nguyên tắc:
1. Chỉ luận giải dựa trên lá số đã cho (Thiên Can, Địa Chi, Ngũ Hành, Thập Thần, Đại Vận). TUYỆT ĐỐI không bịa ra can chi, thần sát, đại vận không có trong lá số.
2. Không nhắc đến "tài liệu/nguồn"; hãy tự tin luận giải như chính chuyên gia.
3. Chỉ viết bằng tiếng Việt (chữ Quốc ngữ có dấu thanh). Thuật ngữ dùng Hán-Việt Latinh (Giáp Tý, Chính quan, Dụng thần, Ngũ hành). TUYỆT ĐỐI không dùng chữ Hán / tiếng Trung (giản thể/phồn thể).
4. Tránh khẳng định hung cát tuyệt đối; diễn đạt theo khả năng và xu hướng.
5. Không dùng markdown (#, **, -, bảng); viết thành đoạn văn tự nhiên như đang ngồi tư vấn trực tiếp.
6. Trả lời đủ dài (tối thiểu khoảng 1.200 ký tự), theo mạch: căn cứ → luận giải → lời khuyên.
"""


# ---- 상담체(말투/형식) 통일 규칙 — 전 메뉴(사주·궁합·택일·작명) 공통, 항상 적용 ----
# 모델이 마크다운(헤더/굵게/목록/표)을 쓰면 화면·PDF에 기호가 노출되고 'AI 비서' 느낌이 난다.
# 실제 상담가가 말하듯 자연스러운 줄글로만 쓰게 강제한다.
CONSULTANT_STYLE_RULE = (
    "[작성 형식 — 필수] 마크다운 기호를 절대 쓰지 마세요. 헤더(#, ##, ###), 굵게(**텍스트**), "
    "목록 기호(-, *, •), 번호 목록(1. 2.), 표를 사용하지 말고, 실제 상담가가 마주 앉아 "
    "이야기하듯 자연스러운 줄글 문단으로만 작성하세요. 항목을 나열할 때도 기호 없이 문장으로 "
    "풀어 쓰고, 문단은 빈 줄로 구분하세요."
)


# ---- 전문가 화법 — '자료 중계'가 아니라 본인이 최고 전문가로서 직접 상담하듯 ----
# 실측: 답변에 "자료에 의하면/참고자료에 따르면" 류가 노출되어 시스템이 자료를 중계하는 것처럼 보임.
# 참고자료는 전문가의 '지식'일 뿐, 출처를 언급하지 말고 본인 풀이로 단언하게 한다.
EXPERT_VOICE_RULE = (
    "[전문가 화법 — 최우선] 당신은 수십 년 경력의 대한민국 최고 사주명리 전문가이자 상담가입니다. "
    "참고자료는 당신이 이미 통달한 지식일 뿐이니, 답변은 자료를 인용하는 말투가 아니라 전문가 본인의 "
    "풀이로 직접 말하세요. '자료에 의하면', '참고자료에 따르면', '분석 자료에서', '제공된 자료에', "
    "'자료에는/자료에 없', '문헌에 따르면', '~라고 나와 있습니다' 같이 자료·출처·문헌을 언급하는 표현을 "
    "절대 쓰지 마세요. 내담자를 마주한 상담가가 자신의 통찰로 풀어 주듯 자연스럽고 자신 있게 이야기하세요."
)

# ---- 할루시네이션 철저 차단 — 전문가답게 '해석'은 단호히, '사실(명식)'은 제공된 것만 ----
FACT_GROUNDING_RULE = (
    "[사실 정확성 — 절대규칙] 해석과 조언은 전문가답게 자신 있게 하되, 사실은 절대 지어내지 마세요. "
    "위 [사주명식]에 제공된 간지·오행·십성·대운과 실제 계산된 근거에 없는 내용을 만들지 마세요. "
    "명식에 없는 천간·지지·신살·합충·대운을 새로 지어내거나, 근거 없는 단정적 예언(특정 연도·나이의 "
    "구체적 사건 등)을 하지 마세요. "
    "특히 구체적 날짜(예: '2023년 10월 5일')나 그날의 일진을 임의로 지어내지 마세요. 시점은 "
    "'올해·최근·앞으로·당분간' 등으로 표현하고, 정확한 날짜나 현재운 간지가 필요하면 프롬프트에 제공된 "
    "'현재 시점 간지'의 날짜·간지만 쓰세요(제공되지 않았으면 날짜를 언급하지 마세요). "
    "또한 질문 주제에 직접 답하세요. 묻지 않은 일진·오늘 운세로 새지 마세요. "
    "확실하지 않은 부분은 단정하지 말고 '~한 경향이 있습니다', '~로 볼 수 있습니다'처럼 가능성으로 표현하세요."
)

# ---- 핵심 질문 집중 — 직전 대화 주제로 흐르지 말고 '지금 질문'에 정조준 ----
# 실측: 취업운 상담 직후 '남자친구 언제 생겨요?'를 물었는데 답이 다시 취업으로 흐름.
# 대화이력 12턴이 직전 주제로 모델을 끌어당기는 드리프트. 지금 질문 주제에 집중하도록 강제한다.
QUESTION_FOCUS_RULE = (
    "[핵심 질문 집중 — 최우선] 답변은 반드시 방금 받은 '지금 질문'의 핵심 주제에 정조준하세요. "
    "직전 대화나 이전 답변이 다른 주제(예: 취업·재물·건강)였더라도, 지금 질문이 다른 주제"
    "(예: 연애·결혼·이성운·자녀)이면 이전 주제를 이어가지 말고 지금 질문의 주제로 새로 풀이하세요. "
    "예) '남자친구는 언제 생길까요?'에는 연애·인연의 시기와 흐름을 중심으로 답하고 취업·직장 이야기로 "
    "새지 마세요. 이전 대화는 맥락 참고용일 뿐, 지금 질문과 주제가 다르면 그 흐름을 따라가지 마세요. "
    "단, 지금 질문이 직전 주제의 연장(같은 주제 후속질문)이면 자연스럽게 이어서 답하세요."
)

# ---- 기본 구성 — 타고난 것(성격·육친·건강) + 시운(올해/월별 '발생할 일') ----
# 운영 정책(전문가 요청, 2026-07 변경): 종합분석 = ①성격 ②육친 ③건강운(사주 본연) → ④올해 발생할 일
# ⑤월별로 발생할 수 있는 일(시운). 직업·재물·연애·결혼은 별도 '성향 축'으로 늘어놓지 않고 ④⑤ '발생할 일'에
# 사건으로 녹인다. 사건은 단정 예언이 아니라 가능성·경향(생길 수 있다/좋은 시기/조심할 때)으로만 — 환각·과장 방지.
# 각 항목은 '한 번만'·명식 근거로 풀고 되풀이하지 않는다. 특정 주제 질문은 그 주제 중심(논지 이탈 금지).
ANSWER_BASE_RULE = (
    "[기본 구성·올해 운세] 사주 전반이나 '올해 운세'를 묻는 일반 질문에는 올해(세운)와 "
    "월별로 생길 수 있는 일(조심할 시기·기회가 오는 시기)을 기본으로 곁들이세요. 월별은 이번 달 하나로 끝내지 말고, "
    "프롬프트의 '[다가오는 월별 간지]'에 제공된 각 달(이번 달부터 연말 12월까지, 최소 6개월)을 "
    "빠짐없이 다루세요.\n"
    "[전체 풀이형 — 타고난 것 + 발생할 일] 사주 전반·전체 풀이를 청하면 아래 순서로, 각 항목을 "
    "'한 번만'·명식([십성·육친]·오행 분포)·세운·월운 근거로 **구체적이고 풍부하게** 풀되(한두 문장으로 얕게 "
    "끝내지 말고), 같은 분석을 다른 항목에서 되풀이하지 마세요.\n"
    "◇ 타고난 것(사주 본연):\n"
    "① 성격 — 장단점·대인관계·강점과 스트레스 받을 때 모습([십성·육친] 근거). 가장 공들여 구체적으로(여기가 핵심). 3~5문장 이상.\n"
    "② 육친(六親) — 부모·형제·배우자·자식과의 인연과 관계 성향([십성·육친] 근거). 3~4문장.\n"
    "③ 건강운 — 오행의 과(過)·불급(不及)으로 주의할 장부·체질과 생활 관리 포인트(질병 단정·진단은 금지, "
    "'주의·관리' 수준으로만). 3~4문장.\n"
    "◇ 발생할 일(시운 — 앞으로 어떤 일이 생길 수 있는지):\n"
    "④ 올해 발생할 수 있는 일 — 올해 세운을 근거로 직업·일, 재물, 인연·연애·결혼, 이동·이사, 건강 등 "
    "어느 영역에서 어떤 일이 생길 수 있는지와 좋은 기회·조심할 점을 구체적으로. 3~5문장.\n"
    "⑤ 월별로 발생할 수 있는 일 — '[다가오는 월별 간지]'의 각 달(이번 달부터 연말 12월까지, 최소 6개월)을 "
    "하나도 건너뛰지 말고, 각 달마다 그 달 월운 간지를 근거로 그 달 생길 수 있는 일·좋은 기회·조심할 점"
    "(직업·재물·인연·건강 포함)을 최소 2~3문장씩.\n"
    "[사건 화법 — 중요] '발생할 일'은 반드시 가능성·경향으로 쓰세요(예: '~한 일이 생길 수 있습니다', "
    "'~하기 좋은 시기입니다', '~을 조심할 때입니다'). '반드시 이렇게 된다'는 단정 예언이나 없는 사건을 "
    "지어내는 것은 금지합니다. 직업·재물·연애·결혼은 별도 성향 설명으로 길게 늘어놓지 말고 ④⑤ '발생할 일'에 "
    "녹여 다루세요.\n"
    "성격·육친·건강과 발생할 일은 반드시 명식·세운·월운 근거로만 풀고 임의로 지어내지 마세요. "
    "단, 사용자가 특정 주제(연애·취업·건강·자녀 등)를 콕 집어 물으면 그 주제를 중심으로 답하고, "
    "올해·월별 발생할 일은 그 주제와 연결해 곁들이세요."
)

# ---- 반복 금지 — 새 질문에 이전 답변을 되풀이하지 않기 ----
# 실측: 새 질문을 해도 직전 답변의 문장·항목을 그대로 반복. 이력 발췌와 함께 규칙으로도 막는다.
NO_REPEAT_RULE = (
    "[반복 금지] 새 질문에는 새로운 정보·관점으로 답하세요. 직전 답변에서 이미 말한 문장·표현·"
    "항목을 그대로 되풀이하지 말고, 이번 질문에 꼭 필요한 내용만 새로 풀어 주세요. 도입부의 "
    "일반적인 사주 개요(명식 나열·전반 성향)도 매 답변마다 반복하지 말고, 질문 핵심부터 바로 답하세요."
)

# ---- 용신 환각 차단 — 용신(특히 조후)은 결정적 계산값(궁통보감)만 인용 ----
# 실측 버그: 약한 1차 LLM이 명식에 없는 용신을 매번 다르게 '추론(=창작)'함(억부/조후 근거 없이).
# 엔진이 조후용신을 결정적으로 계산해 [사주명식]에 제공하므로, 그 값만 쓰게 강제한다.
YONGSIN_RULE = (
    "[용신 규칙 — 최우선] 용신(用神)은 위 [사주명식]에 제공된 '조후용신'과 '억부 방향'만 근거로 "
    "설명하세요. 제공된 조후용신 천간과 다른 천간을 용신이라고 새로 지어내지 마세요. 특히 겨울"
    "(亥子丑월)·여름(巳午未월)생은 조후를 먼저 보아, 제공된 '조후용신: ○(漢)'의 천간을 우선 용신으로 "
    "설명하고 그 근거(계절의 한난)를 함께 풀어 주세요. 봄·가을생은 조후를 참고하되 억부 방향과 함께 "
    "설명하세요. 명식에 제공되지 않은 용신·격국을 임의로 단정하거나 만들어 내지 마세요."
)

# ---- 일주·조후 근거 명시(전문가 화법) — 성격·배우자운을 '왜 그런지' 원리로 풀게 ----
ILJU_JOHU_RULE = (
    "[일주·조후로 근거를 대라] 성격과 배우자(부부)운을 풀 때는 일주(日柱: 일간+일지)의 특성과 조후"
    "(調候: 태어난 계절의 한난조습 vs 명식·일지의 온도 균형)를 '근거 → 결론'으로 명시적으로 이어 "
    "'배운 원리대로' 짚어 주세요. 예: \"겨울(추운 계절)생인데 일지가 오화(午火)라 명식이 따뜻해 조후가 "
    "잘 맞음 → 성정이 원만하고 정이 많음 → 배우자를 아끼고 가정이 편안해 부부운에 유리\" 처럼, 왜 그런지를 "
    "일간의 강약·일지 지장간·오행 균형·[사주명식]의 조후용신 값으로 풀어 주세요. "
    "책의 일반론(일주별 정형 문구)을 그대로 옮기지 말고 이 사람의 실제 명식(제공값)에 맞춰 개별적으로 "
    "설명하세요 — 같은 갑오일주라도 태어난 계절·월지·다른 간지에 따라 결론이 달라집니다."
)

# ---- 날짜·간지 환각의 핵심 차단 — 어떤 날짜의 세운/월운/일진도 직접 계산·추측 금지 ----
# 실측 버그: '올해 경자년'(실제 병오), '시험일(6/22) 일진 기토/병술'(실제 정묘) 처럼 LLM이 달력→간지를
# 매번 다르게 지어냄. 간지는 결정적 계산값이므로, 프롬프트에 제공된 값만 쓰게 하고 나머지는 금지한다.
DATE_GANJI_RULE = (
    "[날짜·간지 절대규칙 — 최우선] 특정 날짜·연도·달·시점의 간지(세운·월운·일진)는 당신이 직접 "
    "계산하거나 추측해서 적지 마세요. 이는 결정적 계산값이라 틀리면 치명적입니다. 오직 프롬프트에 제공된 "
    "'[현재 시점 간지]'와 '[질문 날짜 간지]'에 적힌 값만 그대로 인용하세요. 거기 없는 날짜·연도에 대해서는 "
    "구체적 간지(예: '올해는 경자년', '그날 일진은 기토')를 절대 적지 말고, 날짜 간지 없이 운의 해석·조언만 "
    "하세요. 또한 일간(日干)은 천간 한 글자입니다(예: 일간 병(丙)). 일주(=일간+일지, 예: 병신 丙申)와 "
    "혼동하지 말고, '일간' 뒤에 지지를 붙이지 마세요(‘일간 병신’ 같은 표기 금지)."
)

# ---- 미래지향 — 사주 풀이는 오늘(올해) 기준 현재·미래만, 과거 회고 금지 ----
# 실측: 올해 세운이 안 주어지면 LLM이 세운을 지어내며 과거 연도(2021 辛丑·2023 등)로 착지하거나,
# 흐름 질문에서 이미 끝난 과거 대운을 회고함. 사주 상담은 '지금부터 앞'을 보는 것이 원칙.
FUTURE_ORIENTED_RULE = (
    "[시점 규칙 — 미래지향·최우선] 사주 풀이는 언제나 오늘(올해)을 기준으로 현재와 앞으로의 운을 봅니다. "
    "이미 지나간 과거 연도(작년·재작년 등 특정 과거 연도), 이미 끝난 과거 대운·과거 세운의 운세를 "
    "회고하거나 분석하지 마세요. 질문자가 명시적으로 과거를 묻지 않는 한, 답변은 올해와 다가올 시기"
    "(올해·앞으로·향후·다가오는 대운) 중심으로 작성하세요. 특히 '올해' 운을 물으면 반드시 프롬프트에 "
    "제공된 '올해 세운' 간지로만 답하고, 과거 연도의 세운으로 바꾸지 마세요. 제공된 '현재 대운'이 있으면 "
    "그 현재 대운과 이후(미래) 대운만 다루고, 지나간 대운은 서술하지 마세요."
)


# ---- 말투(방언) 주입 (계획 P) ----
DIALECT_INSTRUCTIONS: dict[str, str] = {
    "standard": "",
    "gyeongsang": "[말투 지침] 답변은 경상도 사투리 말투로, 정감 있고 직설적인 어조로 작성하세요. 내용/근거는 유지하되 어미와 표현만 경상 방언으로.",
    "jeolla": "[말투 지침] 답변은 전라도 사투리 말투로, 푸근하고 구수한 어조로 작성하세요. 내용/근거는 유지하되 어미와 표현만 전라 방언으로.",
    "gangwon": "[말투 지침] 답변은 강원도 사투리 말투로, 순박하고 담백한 어조로 작성하세요. 내용/근거는 유지하되 어미와 표현만 강원 방언으로.",
    "jeju": "[말투 지침] 답변은 제주도 사투리 말투를 가볍게 가미해 친근한 어조로 작성하세요. 내용/근거는 유지하되 어미와 표현을 제주 방언풍으로.",
}


def _dialect_instruction(dialect: str | None) -> str:
    return DIALECT_INSTRUCTIONS.get((dialect or "standard"), "")


def _compose_sys_content(sys_prompt: str, dialect: str | None, explain_level: str, locale: str = "ko") -> str:
    """시스템 프롬프트 + (ko: 방언·명식표기 규칙 / vi: 베트남어 프롬프트) + 쉬운풀이(선택)."""
    if locale == "vi":
        # vi 는 한글(한자) 관습의 ko 룰블록을 주입하면 언어 충돌 → vi 전용 프롬프트만 사용.
        parts = [SYSTEM_PROMPT_VI]
        if explain_level == "brief":
            parts.append("[Ngắn gọn] Chỉ trả lời trọng tâm trong khoảng 100 từ, không dài dòng.")
        return "\n\n".join(parts)
    parts = [sys_prompt]
    di = _dialect_instruction(dialect)
    if di:
        parts.append(di)
    parts.append(PILLAR_NOTATION_RULE)  # 간지 음역 환각 방지 — 항상 적용
    parts.append(DAEWOON_RULE)          # 대운 환각 방지 — 항상 적용
    parts.append(AGE_STAGE_RULE)        # 대운·세운을 현재 나이/생애단계에 맞게 — 항상 적용
    parts.append(CHART_FIDELITY_RULE)   # 참고자료 예시 명식 오염 방지 — 항상 적용
    parts.append(EXPERT_VOICE_RULE)     # 자료 인용 말투 금지·전문가 본인 화법 — 항상 적용
    parts.append(FACT_GROUNDING_RULE)   # 할루시네이션 차단(사실은 제공값만) — 항상 적용
    parts.append(QUESTION_FOCUS_RULE)   # 직전 주제 이탈 방지 — 지금 질문 주제에 정조준 — 항상 적용
    parts.append(ANSWER_BASE_RULE)      # 올해·월별 기본 + 전체 풀이형 구조(질문 주제 우선) — 항상 적용
    parts.append(NO_REPEAT_RULE)        # 이전 답변 반복 금지 — 항상 적용
    parts.append(YONGSIN_RULE)          # 용신(조후) 환각 차단 — 제공된 조후용신만 인용
    parts.append(ILJU_JOHU_RULE)        # 일주+조후를 성격·배우자운의 근거로 명시(전문가 화법) — 항상 적용
    parts.append(DATE_GANJI_RULE)       # 날짜→간지(세운·월운·일진) 환각 차단 — 항상 적용
    parts.append(FUTURE_ORIENTED_RULE)  # 오늘 기준 미래지향·과거 회고 금지 — 항상 적용
    parts.append(CONSULTANT_STYLE_RULE)  # 상담체 줄글(마크다운 금지) — 전 메뉴 항상 적용
    if explain_level == "brief":
        parts.append(BRIEF_EXPLAIN_INSTRUCTION)   # 핵심만(100단어) — 분량 규칙 우선 무효화
    elif explain_level == "easy":
        parts.append(EASY_EXPLAIN_INSTRUCTION)
    return "\n\n".join(parts)


_retriever: SajuRetriever | None = None
_retriever_lock = threading.Lock()


def _get_retriever() -> SajuRetriever:
    global _retriever
    if _retriever is None:
        with _retriever_lock:
            if _retriever is None:
                s = get_settings()
                _retriever = SajuRetriever(
                    url=s.qdrant_url,
                    collection=s.qdrant_collection,
                    device=s.rag_embed_device,     # 임베딩 CPU(리랭커가 GPU1 사용 → VRAM 양보)
                    pdf_boost=s.rag_pdf_boost,      # 스캔본 책 1순위, 유튜브 2순위
                    over_fetch=s.rag_over_fetch,
                    reranker_model=(s.rag_reranker_model if s.rag_reranker_enabled else None),
                    reranker_device=s.rag_reranker_device,
                )
    return _retriever


def warmup_models() -> None:
    """서버 기동 시 '첫 질문 지연'을 없애기 위한 사전 로드.

    지연 원인 분석: LLM(exaone·qwen)은 keep_alive=-1 로 이미 상주하나, RAG용 임베더(bge-m3)와
    리랭커(bge-reranker-v2-m3)는 첫 검색 때 지연 로딩(수 초)돼 첫 답변이 늦었다. 백엔드 프로세스는
    재기동마다 이 싱글턴이 초기화되므로, 기동 직후 백그라운드로 미리 로드해 둔다.
      1) 더미 검색 1회 → 임베더(init 로드)+리랭커(lazy 로드) 둘 다 적재.
      2) exaone·qwen 워밍(bat 은 exaone 만 워밍) → keep_alive=-1 로 상주.
    기동 비차단(별도 스레드에서 호출). 예외는 무시(워밍업 실패해도 첫 요청 때 정상 지연 로딩)."""
    import logging
    log = logging.getLogger("saju.warmup")
    s = get_settings()
    try:
        _get_retriever().retrieve("사주 성격 진로 재물 건강 워밍업", top_k=1, rerank=s.rag_reranker_enabled)
        log.info("[warmup] RAG 임베더+리랭커 상주 완료")
    except Exception as e:  # noqa: BLE001
        log.warning("[warmup] RAG 워밍업 실패(첫 요청 때 로드됨): %s", e)
    for model in (s.ollama_model, s.ollama_refine_model):
        if not model:
            continue
        try:
            httpx.post(
                f"{s.ollama_url}/api/generate",
                json={"model": model, "prompt": "안녕", "stream": False,
                      "keep_alive": _coerce_keep_alive(s.ollama_keep_alive),
                      # 실제 답변과 동일 num_ctx 로 적재 → 첫 실질문에서 ctx 변경 재로드(콜드스타트) 방지.
                      "options": {"num_predict": 1, "num_ctx": s.ollama_num_ctx}},
                timeout=300.0,
            )
            log.info("[warmup] LLM 상주 완료: %s", model)
        except Exception as e:  # noqa: BLE001
            log.warning("[warmup] LLM 워밍업 실패(%s): %s", model, e)


def _to_birth_input(b: BirthDTO, locale: str = "ko") -> BirthInput:
    # locale 은 요청 로케일(get_locale)이 단일 진실원 — BirthDTO.locale(기본 ko)이 아니라
    # 이 인자를 신뢰한다. vi 면 pillars 가 105°E·hongoc_duc 경로를 탄다.
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


# 명식 표기 규칙 — LLM이 한자를 임의 음역(병오→병신)하다 틀리는 환각 방지.
# 요약·근거를 '한글(한자)' 병기로 넘기고, 시스템 지침으로 그대로 인용을 강제한다.
PILLAR_NOTATION_RULE = (
    "[명식 표기 규칙] 사주의 간지(년주·월주·일주·시주, 천간·지지, 십성 등)는 "
    "위 [사주명식]에 제공된 한글 표기를 반드시 그대로 인용하세요. 한자를 직접 한글로 "
    "음역하거나 임의로 바꾸지 마세요(예: 제공된 '병오(丙午)'를 '병신' 등으로 바꾸면 안 됩니다). "
    "모든 명리 술어는 '한글(한자)' 형식으로 적으세요. 예: 정관(正官)."
)

# 대운 환각 방지 — 대운은 결정적 계산값. LLM이 특정 나이대 대운 간지를 지어내면 화면 명식과
# 어긋난다. 제공된 대운 목록만 인용하도록 강제(명식 표기 규칙과 동일 패턴).
DAEWOON_RULE = (
    "[대운 표기 규칙] 대운(大運)은 위 [사주명식]의 '대운' 목록에 제공된 간지·나이 구간을 "
    "반드시 그대로 인용하세요. 특정 나이대(예: 30대·40대·50대)의 대운 간지를 임의로 만들거나 "
    "계산·추측하지 마세요. 목록에 없는 나이의 대운은 언급하지 말고, 각 대운의 간지와 나이 구간은 "
    "제공된 목록과 정확히 일치해야 합니다. 대운수(첫 대운 시작 나이)도 제공된 값을 그대로 쓰세요."
)

# 대운·세운을 '현재 나이/생애단계'에 맞게 — 학생에게 직장운, 고령자에게 취업운 같은 부적절 해석 금지(전문가 요청).
AGE_STAGE_RULE = (
    "[나이·생애단계에 맞게] 대운·세운·올해운을 풀 때는 [사주명식]에 제공된 '현재 약 ○세'와 생애단계를 "
    "반드시 반영해, 그 나이에 실제로 해당하는 관심사로만 해석하세요. 나이에 안 맞는 운은 언급하지 마세요 "
    "— 미성년·학생에게 직장·취업·승진·사업 운을, 은퇴 후 고령자(대략 65세+)에게 취업·직장운을 말하면 안 됩니다. "
    "대략의 초점: 미성년/학생=학업·시험·진로탐색·교우, 20대~30대 초반=학업마무리·취업·연애·결혼, "
    "30~50대=직업·사업·재물·가정, 50~60대=직업안정·자산·자녀·건강, 65세 이후=건강·가족·여가·자산관리·"
    "자녀/손주. 같은 대운·세운이라도 나이에 따라 '무엇에 대한 운인지'를 그 단계의 현실에 맞춰 풀어 주세요."
)

# 명식 오염 방지 — 참고자료(RAG)에 다른 사람의 사주 예시가 섞여 와도 본인 명식으로 쓰지 않게.
# 실측 버그: 약한 1차 LLM이 [참고자료]의 예시 명식 지지(寅·酉 등)를 본인 월지·일지로 혼동.
CHART_FIDELITY_RULE = (
    "[명식 일치 절대규칙 — 최우선] 이 사람의 사주는 오직 위 [사주명식]에 제공된 "
    "년주·월주·일주·시주(천간·지지)뿐입니다. [참고자료]에 다른 사람의 사주 예시·간지·명식표가 "
    "나와도 절대 본인 명식으로 인용하지 마세요. 답변에서 말하는 모든 지지(년지·월지·일지·시지)와 "
    "천간은 위 [사주명식]과 100% 일치해야 합니다. 예: 위 명식의 월주가 '갑자(甲子)'면 월지는 "
    "반드시 자(子)이며, 참고자료에 寅·酉가 나와도 월지를 인(寅)·유(酉) 등으로 바꾸면 안 됩니다."
)

# 쉬운 말투(easy) — 초보자가 이야기 듣듯 이해하도록. (다른 형식 지침보다 우선)
EASY_EXPLAIN_INSTRUCTION = (
    "[쉬운 풀이 지침 — 최우선] 이 답변은 사주를 처음 접하는 초보자를 위한 것입니다. "
    "다음을 반드시 지키세요.\n"
    "1) 마크다운 헤더(###)·표·'원문 인용:' 같은 표기를 쓰지 말고, 따뜻하게 이야기하듯 "
    "자연스러운 문단으로만 쓰세요.\n"
    "2) 전문용어(대운·세운·일간·오행·십성 등)는 가능하면 쓰지 말고, 꼭 필요하면 한 번만 "
    "쉬운 말로 풀어 주세요. 예: '일간(나를 나타내는 기운)'.\n"
    "3) 띠·계절·자연물 비유로 설명하세요. 예: '을묘(乙卯)생이면 토끼해에 태어난 분이라, "
    "봄에 돋는 새싹처럼 …', '올해는 병오(丙午), 한여름 불기운이 센 해라 …'.\n"
    "4) 간지는 위에 제공된 한글(한자) 표기를 그대로 쓰되, 한자만 나열하지 마세요.\n"
    "5) 어려운 분석보다 '그래서 올해 어떻게 지내면 좋은지' 같은 실생활 조언 중심으로, "
    "친구에게 말하듯 편안하게 적어 주세요."
)

# 핵심만(brief) — 100단어 이내 요약. 분량 규칙(1,200자 이상 등)을 무시하고 짧게.
BRIEF_EXPLAIN_INSTRUCTION = (
    "[핵심만 지침 — 최우선] 위의 분량 규칙(1,200자/문장 수 등)은 무시하세요. "
    "이 답변은 **한국어 100단어 이내**로, 군더더기 없이 핵심 결론만 전달합니다. "
    "마크다운 헤더·표 없이 2~4문장으로, 가장 중요한 근거 1~2개와 결론·조언만 간결히 적으세요."
)


def _gz_ko(p) -> str:
    """간지를 '한글(한자)'로. 예: 병오(丙午). 시주 없으면 호출 안 함."""
    from backend.app.saju.constants import branch_korean, stem_korean
    return f"{stem_korean(p.stem)}{branch_korean(p.branch)}({p.stem}{p.branch})"


def _build_calc_basis(birth: BirthInput) -> str:
    """LLM이 '어떤 기준으로 계산했는지' 질문에 정확히 답하도록 계산 기준을 명시."""
    parts = ["음력" if birth.calendar == CalendarType.LUNAR else "양력"]
    # 서머타임·역사 표준시 자동 보정 — 실제 적용된 경우에만 명시(정직)
    if birth.birth_time is not None:
        from backend.app.saju.pillars import _civil_std_offset_h, _kst_utcoffset_h
        off = _kst_utcoffset_h(birth.birth_date, birth.birth_time)
        civil = _civil_std_offset_h(birth.birth_date)
        if abs(off - civil) > 0.01:
            parts.append("서머타임 자동 보정(−1시간)")
        if abs(civil - 9.0) > 0.01:
            parts.append(f"당시 표준시 동경{civil * 15:.1f}°E 자동 반영")
    if birth.apply_true_solar_time:
        lon = f"{birth.birth_longitude}°E" if birth.birth_longitude is not None else "서울"
        eot = "균시차 반영" if birth.apply_equation_of_time else "균시차 미반영"
        parts.append(f"진태양시 보정({lon} 경도·당시 표준자오선 자동·{eot})")
    else:
        parts.append("진태양시 미적용(시계 표준시 그대로)")
    parts.append(
        "야자시(夜子時: 23~24시는 일주=당일, 시주 천간=익일 일간 기준)"
        if birth.night_zi_mode == "yaja"
        else "정자시(正子時: 23시부터 일주·시주 모두 익일 기준)"
    )
    return "  계산 기준: " + ", ".join(parts)


def _yongsin_lines(chart: SajuChart) -> list[str]:
    """억부 방향(월령 반영 강약 기준) + 조후용신(궁통보감 결정값)을 명식 요약 라인으로.

    둘 다 결정적 도출값이라 LLM이 용신을 '창작'하지 못하도록 명식에 못박는다.
    """
    from backend.app.saju.constants import (
        WUXING_GENERATES,
        WUXING_KOREAN,
        WUXING_OVERCOMES,
        stem_korean,
    )

    out: list[str] = []
    dm_elem = chart.day_master_element

    def _wk(el: str) -> str:
        return f"{WUXING_KOREAN.get(el, '')}({el})"

    # 억부 방향 — 강약(월령 반영)으로 보조/설기 방향을 결정적으로 제시
    gen_me = {v: k for k, v in WUXING_GENERATES.items()}[dm_elem]   # 인성(나를 생)
    my_gen = WUXING_GENERATES[dm_elem]                              # 식상(내가 생)
    my_over = WUXING_OVERCOMES[dm_elem]                             # 재성(내가 극)
    over_me = {v: k for k, v in WUXING_OVERCOMES.items()}[dm_elem]  # 관성(나를 극)
    st = chart.day_master_strength
    if st == "strong":
        eokbu = (f"신강이라 억부로는 기운을 덜어내는 쪽 — 식상 {_wk(my_gen)}·"
                 f"재성 {_wk(my_over)}·관성 {_wk(over_me)} 계열")
    elif st == "weak":
        eokbu = (f"신약이라 억부로는 기운을 보태는 쪽 — 인성 {_wk(gen_me)}·"
                 f"비겁 {_wk(dm_elem)} 계열")
    else:
        eokbu = "중화에 가까워 억부보다 조후·격국을 함께 봅니다"
    out.append(f"  억부 방향(강약 기준): {eokbu}")

    # 조후용신(궁통보감) — 정용신 천간 + 보조 + 우선여부 + 근거
    jy = chart.johu_yongsin
    if jy:
        sup = ("·".join(f"{stem_korean(s)}({s})" for s in jy.supporting)) if jy.supporting else ""
        sup_str = f" / 보조 {sup}" if sup else ""
        prio = " [겨울·여름생 → 조후 우선]" if jy.is_climate_priority else ""
        out.append(
            f"  조후용신(궁통보감): {stem_korean(jy.primary)}({jy.primary}){sup_str}{prio} — {jy.note}"
        )
    return out


def _sipsin_yukchin_lines(chart: SajuChart, birth: BirthInput | None) -> list[str]:
    """십성(十星)·육친(六親) — 성격·가족/인연 해석의 결정적 근거. 이미 계산된 십성을 프롬프트
    앵커로 주입해 LLM 재추론(환각)을 막고 육친 풀이의 근거를 제공한다."""
    from backend.app.saju.constants import TEN_GODS_KO, yukchin_meaning
    from backend.app.saju.types import Gender
    tg = chart.ten_gods
    is_male = None if birth is None else (birth.gender == Gender.MALE)

    def ko(x: str | None) -> str:
        if not x:
            return "—"
        k = TEN_GODS_KO.get(x)
        return f"{k}({x})" if k else x  # '겁재(劫財)' 형태로 정자 한자를 함께 주입(모델 한자 환각 예방)

    pos = [
        ("년간", tg.year_stem), ("월간", tg.month_stem), ("시간", tg.hour_stem),
        ("년지", tg.year_branch), ("월지", tg.month_branch), ("일지", tg.day_branch), ("시지", tg.hour_branch),
    ]
    cells = ", ".join(f"{name} {ko(v)}" for name, v in pos if v)
    seen: list[str] = []
    for _name, v in pos:
        if v and v not in seen:
            seen.append(v)
    # 성별을 반영해 육친을 '확정' 주입 — 남성=자식은 관성, 여성=자식은 식상. (LLM 오적용 차단)
    legend = [f"    · {ko(v)} = {yukchin_meaning(v, is_male)}" for v in seen]
    lines = [
        "[십성(十星)·육친(六親)] — 성격·가족/인연 해석의 결정적 근거(아래 값만 사용, 임의 생성 금지). 일간=본인.",
        f"  위치별 십성: {cells}",
        "  십성→육친 의미(본인 성별 반영·확정):",
        *legend,
    ]
    if is_male is not None:
        g = "남성" if is_male else "여성"
        lines.append(
            f"  ※ 위 육친은 이미 본인 성별({g}) 기준으로 확정됨. 반대 성별의 관계(예: 남성인데 "
            "식신·상관을 '자식'으로)로 풀지 마세요 — 남성의 자식=관성(정관·편관), 여성의 자식=식상(식신·상관)."
        )
    return lines


def _life_stage_ko(age: int) -> str:
    """현재 나이 → 생애단계 라벨(대운·세운을 나이에 맞게 해석하도록 프롬프트 앵커로 주입)."""
    if age < 8:
        return "미취학·유아"
    if age < 14:
        return "초등학생 — 학업·교우"
    if age < 17:
        return "중학생 — 학업·진로탐색"
    if age < 20:
        return "고등학생 — 학업·입시·진로"
    if age < 27:
        return "대학·사회초년 — 학업마무리·취업준비·연애"
    if age < 35:
        return "청년 — 취업·커리어초기·연애·결혼"
    if age < 50:
        return "중년 — 직업·사업·재물·가정"
    if age < 65:
        return "장년 — 직업안정·자산·자녀·건강관리"
    return "노년 — 건강·가족·여가·자산관리·자녀손주(취업/직장운 아님)"


def _build_saju_summary(chart: SajuChart, birth: BirthInput | None = None) -> str:
    from backend.app.saju.constants import stem_korean
    fp = chart.pillars
    day_stem = fp.day.stem
    day_yy = "양" if STEM_IS_YANG[day_stem] else "음"
    hour_str = _gz_ko(fp.hour) if fp.hour else "시미상"
    def _pil_elem(p) -> str:  # 기둥 표면 오행(천간·지지) — '화기가 강한 甲子' 류 환각 예방 근거표
        return f"{WUXING_KOREAN[STEM_TO_WUXING[p.stem]]}·{WUXING_KOREAN[BRANCH_TO_WUXING[p.branch]]}"
    pe = [f"년주 {_gz_ko(fp.year)}={_pil_elem(fp.year)}", f"월주 {_gz_ko(fp.month)}={_pil_elem(fp.month)}",
          f"일주 {_gz_ko(fp.day)}={_pil_elem(fp.day)}"] + (
        [f"시주 {_gz_ko(fp.hour)}={_pil_elem(fp.hour)}"] if fp.hour else [])
    lines = [
        f"[사주명식]",
        f"  년주 {_gz_ko(fp.year)}  월주 {_gz_ko(fp.month)}  일주 {_gz_ko(fp.day)}  시주 {hour_str}",
        f"  기둥 오행: {', '.join(pe)} — 각 간지의 오행 기운은 이 표만 근거로 말하고, "
        f"표에 없는 오행을 그 간지의 기운이라 하지 마세요",
        f"  일간(本人): {stem_korean(day_stem)}({day_stem}) — {WUXING_KOREAN.get(STEM_TO_WUXING[day_stem], '')}({STEM_TO_WUXING[day_stem]}), 음양: {day_yy}",
        f"  일간 강약: {chart.day_master_strength} (월령 득령 반영)",
        f"  오행 분포: {chart.wuxing.as_dict_ko()}",
    ]
    lines += _sipsin_yukchin_lines(chart, birth)   # 십성·육친(성격·가족/인연 근거)
    lines += _yongsin_lines(chart)   # 억부 방향 + 조후용신(궁통보감 결정값)
    if chart.daewoon:
        dw = chart.daewoon
        dir_ko = "순행" if dw.direction == "forward" else "역행"
        lines.append(f"  대운: {dir_ko}, 대운수 {dw.start_age:.1f}세 (아래 목록을 그대로 인용, 임의 생성 금지)")
        es = dw.entries or []
        for i, e in enumerate(es):
            end = (es[i + 1].start_age - 1) if i + 1 < len(es) else None
            rng = f"{e.start_age}~{end}세" if end is not None else f"{e.start_age}세~"
            lines.append(f"    · {rng}: {_gz_ko(e.pillar)}")
        # 현재 대운 표시 — 풀이를 현재·미래 중심으로(이미 끝난 과거 대운 회고 방지)
        if birth is not None and es:
            from datetime import date as _today_d
            age = (_today_d.today() - birth.birth_date).days / 365.25
            ci = max((i for i, en in enumerate(es) if en.start_age <= age), default=0)
            ce = es[ci]
            cend = (es[ci + 1].start_age - 1) if ci + 1 < len(es) else None
            crng = f"{ce.start_age}~{cend}세" if cend is not None else f"{ce.start_age}세~"
            nxt = (f", 다음 대운 {_gz_ko(es[ci + 1].pillar)}({es[ci + 1].start_age}세~)"
                   if ci + 1 < len(es) else "")
            lines.append(
                f"  ※ 현재 약 {int(age)}세({_life_stage_ko(int(age))}) → 현재 대운: {_gz_ko(ce.pillar)}({crng}){nxt}. "
                f"풀이는 현재 대운·올해 세운과 앞으로(미래) 중심으로, 이 나이·생애단계에 맞는 관심사로만 하고, "
                f"지나간 과거 대운·과거 연도는 서술하지 마세요."
            )
    if birth is not None:
        lines.append(_build_calc_basis(birth))
    return "\n".join(lines)


def _build_chart_evidence(chart_json: dict | None) -> list[str]:
    """사주명식 핵심값을 '근거' 불릿 리스트로 추출(계획 3.5 G)."""
    if not chart_json:
        return []
    out: list[str] = []
    try:
        from backend.app.saju.constants import branch_korean, stem_korean
        pillars = chart_json.get("pillars") or {}

        def _pk(key: str) -> str | None:
            p = pillars.get(key) or {}
            st, br = p.get("stem"), p.get("branch")
            if not st or not br:
                return None
            return f"{stem_korean(st)}{branch_korean(br)}({st}{br})"

        gz_bits = [f"{lab}{v}" for lab, k in (("년주 ", "year"), ("월주 ", "month"), ("일주 ", "day"), ("시주 ", "hour")) if (v := _pk(k))]
        if gz_bits:
            out.append("명식: " + "  ".join(gz_bits))
        day = pillars.get("day") or {}
        day_stem = day.get("stem")
        if day_stem:
            wx = STEM_TO_WUXING.get(day_stem)
            wx_ko = WUXING_KOREAN.get(wx, "")
            yy = "양" if STEM_IS_YANG.get(day_stem) else "음"
            out.append(f"일간(本人): {stem_korean(day_stem)}({day_stem}) — {wx_ko}({wx}), {yy}")
        strength = chart_json.get("day_master_strength")
        if strength:
            out.append(f"일간 강약: {strength}")
        wuxing = chart_json.get("wuxing")
        if isinstance(wuxing, dict):
            counts = {k: v for k, v in wuxing.items() if isinstance(v, (int, float))}
            if counts:
                out.append("오행 분포: " + ", ".join(f"{k} {int(v)}" for k, v in counts.items()))
        dw = chart_json.get("daewoon")
        if isinstance(dw, dict):
            direction = dw.get("direction")
            dir_ko = "순행" if direction == "forward" else ("역행" if direction else "")
            start_age = dw.get("start_age")
            head = "대운"
            if dir_ko:
                head += f" {dir_ko}"
            if start_age is not None:
                head += f", 대운수 {float(start_age):.1f}세"
            ents = dw.get("entries") or []
            seq: list[str] = []
            for i, e in enumerate(ents):
                p = e.get("pillar") or {}
                st, br = p.get("stem"), p.get("branch")
                age = e.get("start_age")
                if not (st and br and age is not None):
                    continue
                nxt = ents[i + 1].get("start_age") if i + 1 < len(ents) else None
                rng = f"{age}~{nxt - 1}세" if isinstance(nxt, int) else f"{age}세~"
                seq.append(f"{rng} {stem_korean(st)}{branch_korean(br)}({st}{br})")
            if seq:
                out.append(head + " (목록 그대로 인용): " + " / ".join(seq))
            elif dir_ko or start_age is not None:
                out.append(head)
    except Exception:  # noqa: BLE001
        return out
    return out


# ============================================================
# 명식 정합성 검증 — 답변의 4주 지지가 명식과 다르면 자동 교정(실측 버그 대응)
# ============================================================
_BRANCH_HANJA = "子丑寅卯辰巳午未申酉戌亥"
_ELEM2BRANCH = {  # 원소표기 한글(예: 자수) → 지지 한자
    "자수": "子", "축토": "丑", "인목": "寅", "묘목": "卯", "진토": "辰", "사화": "巳",
    "오화": "午", "미토": "未", "신금": "申", "유금": "酉", "술토": "戌", "해수": "亥",
}
_POS_WORDS = {"년지": "year", "연지": "year", "월지": "month", "일지": "day", "시지": "hour"}


def _pillar_branches(chart_json: dict | None) -> dict[str, str]:
    """chart_json.pillars → {year/month/day/hour: 지지한자}. 명식 검증 기준값."""
    out: dict[str, str] = {}
    pil = (chart_json or {}).get("pillars") or {}
    for k in ("year", "month", "day", "hour"):
        br = (pil.get(k) or {}).get("branch")
        if br:
            out[k] = br
    return out


def _allowed_from_charts(*chart_jsons: dict | None) -> dict[str, set[str]]:
    """여러 명식의 위치별 허용 지지 집합. 단일=정확 일치, 다중(궁합)=union."""
    allowed: dict[str, set[str]] = {}
    for cj in chart_jsons:
        for k, v in _pillar_branches(cj).items():
            allowed.setdefault(k, set()).add(v)
    return allowed


_DATE_CTX = ("그날", "그 날", "해당", "당일", "택일", "추천일", "길일", "날의", "그날의")


def _verify_branches(
    answer: str, allowed: dict[str, set[str]], *, exclude_date_ctx: bool = False
) -> list[tuple[str, str, str]]:
    """위치어(월지/일지/년지/시지) 뒤 12자 내 첫 지지가 allowed[위치] 집합에 없으면 불일치.

    위치어 직후만 검사 → 대운·세운·개념(봄 寅卯辰) 오탐 0. exclude_date_ctx=True(택일):
    '그날/해당일' 등 날짜 문맥의 일지는 본인 일지가 아니므로 건너뜀. 빈 결과 = 일치.
    """
    if not answer or not allowed:
        return []
    bad: list[tuple[str, str, str]] = []
    for pos_ko, key in _POS_WORDS.items():
        allow = allowed.get(key)
        if not allow:
            continue
        for m in re.finditer(re.escape(pos_ko), answer):
            if exclude_date_ctx and any(d in answer[max(0, m.start() - 8): m.start()] for d in _DATE_CTX):
                continue
            win = answer[m.end(): m.end() + 12]
            em = re.search("|".join(_ELEM2BRANCH), win)
            claimed = _ELEM2BRANCH[em.group(0)] if em else None
            if claimed is None:
                hm = re.search(f"[{_BRANCH_HANJA}]", win)
                claimed = hm.group(0) if hm else None
            if claimed and claimed not in allow:
                bad.append((pos_ko, claimed, "·".join(sorted(allow))))
                break  # 위치당 1회
    return bad


_STEM_HANJA = "甲乙丙丁戊己庚辛壬癸"


def _verify_day_stem(answer: str, chart_json: dict | None) -> list[tuple[str, str, str]]:
    """답변의 '일간 …(漢)'이 명식 일간과 다르면 불일치(한자 기준 — 음역 모호성 회피).

    '일간' 직후 8자 내 첫 천간 한자만 검사 → 대운·십성·신금대운 등 오탐 0. 한자가 없으면(한글만) 건너뜀.
    """
    if not answer or not chart_json:
        return []
    actual = _day_stem(chart_json)
    if not actual:
        return []
    for m in re.finditer("일간", answer):
        win = answer[m.end(): m.end() + 8]
        hm = re.search(f"[{_STEM_HANJA}]", win)
        if hm and hm.group(0) != actual:
            return [("일간", hm.group(0), actual)]
    return []


def _verify_day_stem_multi(answer: str, stems: set[str]) -> list[tuple[str, str, str]]:
    """궁합 등 다중 명식 — '일간 …(漢)'이 허용 천간집합(두 사람) 어디에도 없으면 불일치."""
    if not answer or not stems:
        return []
    for m in re.finditer("일간", answer):
        win = answer[m.end(): m.end() + 8]
        hm = re.search(f"[{_STEM_HANJA}]", win)
        if hm and hm.group(0) not in stems:
            return [("일간", hm.group(0), "·".join(sorted(stems)))]
    return []


# 대운(大運) 검증 — '대운'에 직접 붙은 간지가 명식 대운 목록에 없으면 환각(결정적 계산값).
# LLM이 특정 나이대 대운 간지를 지어내면 화면 명식과 어긋남(실측: '현재 대운 (갑자, 15~24세)').
_DW_GANJI = (
    r"(?:[갑을병정무기경신임계][자축인묘진사오미신유술해]"
    r"|[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])"
)
_DAEWOON_NEAR_RE = re.compile(
    rf"대운[은는이가의\s:·,，\(\)（）]*({_DW_GANJI})"      # 대운 → 간지(정방향)
    rf"|({_DW_GANJI})\s*(?:\([一-鿿]{{1,2}}\))?\s*대운"     # 간지 → 대운(역방향)
)


def _daewoon_ganji_set(chart_json: dict | None) -> set[str]:
    """명식 대운 목록의 허용 간지(한글 '갑자' + 한자 '甲子' 모두)."""
    from backend.app.saju.constants import branch_korean, stem_korean
    out: set[str] = set()
    dw = (chart_json or {}).get("daewoon")
    if isinstance(dw, dict):
        for e in (dw.get("entries") or []):
            p = e.get("pillar") or {}
            st, br = p.get("stem"), p.get("branch")
            if st and br:
                out.add(stem_korean(st) + branch_korean(br))  # 갑자
                out.add(f"{st}{br}")                            # 甲子
    return out


def _verify_daewoon(answer: str, chart_json: dict | None) -> list[tuple[str, str, str]]:
    """'대운'에 직접 붙은 간지가 명식 대운 목록에 없으면 불일치(환각). '대운' 앵커라 오탐 0.

    세운·연주 등 '대운'에 안 붙은 간지는 검사 안 함. 빈 결과 = 일치.
    """
    if not answer or not chart_json:
        return []
    allow = _daewoon_ganji_set(chart_json)
    if not allow:
        return []
    for m in _DAEWOON_NEAR_RE.finditer(answer):
        g = m.group(1) or m.group(2)
        if g and g not in allow:
            return [("대운 간지", g, "·".join(sorted(allow)))]
    return []


def _verify_yongsin(answer: str, chart_json: dict | None) -> list[tuple[str, str, str]]:
    """'조후용신' 직접 단정이 제공된 정용신과 다르면 불일치(보수적 — 오탐 0 지향).

    '조후용신' 키워드 직후 12자 내 첫 천간 한자만 검사한다. 일반 '용신'은 여러 천간을 자연히
    언급하므로 제외(오탐 방지). 보조용신 목록에 있으면 허용. 한자가 없으면(한글만) 건너뜀.
    """
    if not answer or not chart_json:
        return []
    jy = (chart_json or {}).get("johu_yongsin") or {}
    primary = jy.get("primary")
    if not primary:
        return []
    allow = {primary} | set(jy.get("supporting") or [])
    for m in re.finditer("조후용신", answer):
        win = answer[m.end(): m.end() + 12]
        hm = re.search(f"[{_STEM_HANJA}]", win)
        if hm and hm.group(0) not in allow:
            return [("조후용신", hm.group(0), _stem_ko(primary))]
    return []


# 간지→오행 속성 주장 검증 — '화기(火氣)가 강한 갑자(甲子)' 류 환각(실측 케이스 #3: 甲子에
# 화기 없음). 간지의 오행은 결정적(천간·지지 표면+지장간)이라 명식 없이 자기모순을 판정한다.
# 앵커를 좁게(기운 강조어 ↔ 간지 직결, 갭은 궁위어·조사만) 잡아 오탐 0 지향 — '화기가 강한
# 사주라 갑자 대운…' 같은 사주 전체 서술은 갭 규칙에 걸리지 않아 불개입.
_ELEM_KO2HANJA = {"목": "木", "화": "火", "토": "土", "금": "金", "수": "水"}
_POS_GAP = r"(?:\s|의|인)*(?:년주|월주|일주|시주|년지|연지|월지|일지|시지)?(?:\s|의)*"
_ELEM_CLAIM = r"([목화토금수])기(?:\s*\(\s*[木火土金水]?氣?\s*\))?"
_STRONG_WORD = r"(?:매우\s*)?(?:강한|강해|강하고|강합|왕성한|왕성해|넘치는|가득한)"
_ELEM_GANJI_FWD_RE = re.compile(rf"{_ELEM_CLAIM}\s*[가이]?\s*{_STRONG_WORD}{_POS_GAP}({_DW_GANJI})")
_ELEM_GANJI_REV_RE = re.compile(
    rf"({_DW_GANJI})\s*(?:\([一-鿿]{{1,2}}\))?{_POS_GAP}[은는이가]?\s*{_ELEM_CLAIM}\s*[가이]?\s*{_STRONG_WORD}"
)


def _verify_ganji_element(answer: str) -> list[tuple[str, str, str]]:
    """'X기가 강한 간지'/'간지 …는 X기가 강한' 주장의 오행이 그 간지에 없으면 불일치.

    허용 오행 = 천간·지지 표면 + 지장간(甲戌의 화기=지장간 丁 근거라 정상 통과). 빈 결과 = 일치."""
    if not answer:
        return []
    claims = [(m.group(1), m.group(2)) for m in _ELEM_GANJI_FWD_RE.finditer(answer)]
    claims += [(m.group(2), m.group(1)) for m in _ELEM_GANJI_REV_RE.finditer(answer)]
    bad: list[tuple[str, str, str]] = []
    for elem_ko, ganji in claims:
        if ganji[0] in STEM_KOREAN:  # 한글 간지 → 한자 변환(위치 기준이라 중의성 없음)
            st = HEAVENLY_STEMS[STEM_KOREAN.index(ganji[0])]
            br = EARTHLY_BRANCHES[BRANCH_KOREAN.index(ganji[1])]
        else:
            st, br = ganji[0], ganji[1]
        allowed = ganji_allowed_elements(st, br)
        if _ELEM_KO2HANJA[elem_ko] not in allowed:
            allowed_ko = "·".join(WUXING_KOREAN[e] for e in ("木", "火", "土", "金", "水") if e in allowed)
            bad.append((f"{ganji}({st}{br})의 오행 기운(실제로는 지장간까지 {allowed_ko}뿐)",
                        f"{elem_ko}기", allowed_ko))
    return bad


def _verify_myeongsik(answer: str, chart_json: dict | None) -> list[tuple[str, str, str]]:
    """단일 명식 일간(천간)+4주 지지+조후용신+간지오행 검증(사주 상담·작명 등). 빈 결과 = 일치."""
    return (
        _verify_branches(answer, _allowed_from_charts(chart_json))
        + _verify_day_stem(answer, chart_json)
        + _verify_yongsin(answer, chart_json)
        + _verify_ganji_element(answer)
    )


def _branch_ko(br: str) -> str:
    from backend.app.saju.constants import branch_korean
    return f"{branch_korean(br)}({br})"


def _stem_ko(st: str) -> str:
    from backend.app.saju.constants import stem_korean
    return f"{stem_korean(st)}({st})"


def _day_stem(chart_json: dict | None) -> str | None:
    """명식 일간(일주 천간) 한자. 예: 丙."""
    return (((chart_json or {}).get("pillars") or {}).get("day") or {}).get("stem")


def _myeongsik_truth(chart_json: dict | None) -> str:
    """단일 명식 일간(천간)+4주 지지를 '일간=병(丙), 월지=자(子)' 형식으로 — 교정 지시·헤더용."""
    actual = _pillar_branches(chart_json)
    pos = (("년지", "year"), ("월지", "month"), ("일지", "day"), ("시지", "hour"))
    out: list[str] = []
    st = _day_stem(chart_json)
    if st:
        out.append(f"일간={_stem_ko(st)}")
    out += [f"{ko}={_branch_ko(actual[k])}" for ko, k in pos if k in actual]
    jy = (chart_json or {}).get("johu_yongsin") or {}
    if jy.get("primary"):
        out.append(f"조후용신={_stem_ko(jy['primary'])}")
    dw = (chart_json or {}).get("daewoon")
    if isinstance(dw, dict):
        from backend.app.saju.constants import branch_korean, stem_korean
        seq = [
            f"{stem_korean(p['stem'])}{branch_korean(p['branch'])}"
            for e in (dw.get("entries") or [])
            if (p := (e.get("pillar") or {})).get("stem") and p.get("branch")
        ]
        if seq:
            out.append("대운목록=" + "·".join(seq))
    return ", ".join(out)


def _charts_truth(labeled: list[tuple[str, dict | None]]) -> str:
    """다중 명식(궁합) 진실값: '사람A: 년지=.., ..; 사람B: ..'."""
    pos = (("년지", "year"), ("월지", "month"), ("일지", "day"), ("시지", "hour"))
    out = []
    for label, cj in labeled:
        br = _pillar_branches(cj)
        if br:
            out.append(f"{label}: " + ", ".join(f"{ko}={_branch_ko(br[k])}" for ko, k in pos if k in br))
    return " / ".join(out)


def _correction_prompt(mismatches: list[tuple[str, str, str]], truth: str) -> str:
    wrongs = ", ".join(f"{p}를 '{c}'(으)로" for p, c, _ in mismatches)
    return (
        f"[중대 오류 정정 — 최우선] 직전 답변에서 {wrongs} 잘못 적었습니다. "
        f"실제 명식 기준값은 정확히 다음과 같습니다: {truth}. "
        f"[참고자료]의 다른 예시 명식·간지·용신은 절대 쓰지 말고, 위 실제 값만 사용해 "
        f"같은 질문에 처음부터 다시 정확히 답하세요."
    )


def _correct_branches(
    answer: str, *, allowed: dict[str, set[str]], truth: str, question: str,
    sys_content: str, saju_summary: str | None, max_tries: int = 2, exclude_date_ctx: bool = False,
    chart_json: dict | None = None, day_stems: set[str] | None = None,
) -> str:
    """불일치 시 참고자료 없는 깨끗한 컨텍스트로 교정 재생성(≤max_tries) + 최종 명식헤더 백스톱.

    chart_json을 주면 4주 지지뿐 아니라 일간(천간) 불일치도 함께 검증·교정한다.
    day_stems(궁합 등 다중 명식)를 주면 두 사람 일간 union으로 검증한다.
    """
    def _bad(txt: str) -> list[tuple[str, str, str]]:
        b = _verify_branches(txt, allowed, exclude_date_ctx=exclude_date_ctx)
        b = b + _verify_ganji_element(txt)  # 간지→오행 속성 환각(명식 불요·전 메뉴)
        if chart_json is not None:
            b = (b + _verify_day_stem(txt, chart_json) + _verify_yongsin(txt, chart_json)
                 + _verify_daewoon(txt, chart_json))
        if day_stems:
            b = b + _verify_day_stem_multi(txt, day_stems)
        return b

    bad = _bad(answer)
    if not bad:
        return answer
    cur = answer
    base_user = _build_user_prompt(question, [], saju_summary, chart_json=chart_json)  # 참고자료 제외(오염 차단)
    for _ in range(max_tries):
        msgs = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": base_user + "\n\n" + _correction_prompt(bad, truth)},
        ]
        try:
            new = _call_ollama(msgs)
        except Exception:  # noqa: BLE001
            break
        if not (new and new.strip()):
            break
        cur = new.strip()
        bad = _bad(cur)
        if not bad:
            return cur
    if truth:  # 최종 안전망: 정확한 명식 헤더 강제(틀린 지지 노출 차단)
        cur = f"※ 정확한 명식 지지: {truth}. 아래 설명 중 지지가 다르게 적힌 곳은 이 명식 기준으로 보세요.\n\n{cur}"
    return cur


def _correct_chart(
    answer: str, chart_json: dict | None, *, question: str, sys_content: str,
    saju_summary: str | None, max_tries: int = 2,
) -> str:
    """단일 명식(사주 상담·작명 등) 교정 래퍼 — 4주 지지 + 일간(천간) 검증·교정."""
    return _correct_branches(
        answer, allowed=_allowed_from_charts(chart_json), truth=_myeongsik_truth(chart_json),
        question=question, sys_content=sys_content, saju_summary=saju_summary, max_tries=max_tries,
        chart_json=chart_json,
    )


# ---- 자료 인용 말투 후처리 제거 (전문가 화법 보장, layer-3) ----
# 프롬프트로 막아도 약한 LLM이 "참고 자료들에서…/자료에 의하면…"을 간헐 누출 → 결정적으로 제거.
# 마크다운 제거와 같은 표시단계 정제. 메타 머리말만 떼어내 전문가 본인 풀이체로 만든다.
_SRC_REF_PATTERNS = [
    r"(분석\s*|참고\s*|제공된\s*)?자료(들)?에서\s*(일관되게\s*)?(언급되|나오|보이|확인되|제시되)\S*\s*(특징|내용|점|바)?(으?로|이며|인데|이고)?[,]?\s*",
    r"(분석\s*|참고\s*|제공된\s*)?자료(들)?에\s*(의하면|따르면)[,]?\s*",
    r"제공된\s*자료(에는|에서|에|가)\s*",
    r"자료(들)?에서\s*(언급된|언급되는|나온|제시된|보이는|확인되는)?\s*(대로|바와\s*같이)?[,]?\s*",
    r"자료(들)?에는\s*",
    r"(고전|문헌)에\s*따르면[,]?\s*",
    r"자료에\s*명확한\s*답[이은]?\s*없\S*[.]?\s*",
]
_SRC_REF_RES = [re.compile(p) for p in _SRC_REF_PATTERNS]


def _scrub_source_refs(text: str) -> str:
    """답변에서 '자료/참고자료/문헌' 출처 언급 머리말을 제거(전문가 본인 화법 보장). 본문 의미는 보존."""
    if not text:
        return text
    out = text
    for rgx in _SRC_REF_RES:
        out = rgx.sub("", out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


# ---- 최종 시점 재검증 게이트 — 과거연도·틀린 세운 간지를 결정적으로 중화 ----
# 프롬프트로 막아도 약한 LLM/외부 보강(Claude)이 '2023년 계묘년' 같은 과거연도·틀린 간지를
# 간헐 누출(실측). 내부+외부 보강을 모두 거친 '최종 답변'에 이 게이트를 적용해, 올해/내년의
# 실제 세운 간지만 남기고 과거연도·틀린 간지(한자 병기 포함)는 '올해'로 중화한다.
_GANJI_YEAR_HANJA_RE = re.compile(
    r"([갑을병정무기경신임계][자축인묘진사오미신유술해])\s*년\s*(?:\([一-鿿]{1,4}\))?"
)


def _year_ko_hj(yr: int) -> tuple[str, str]:
    """해당 연도의 세운 간지를 (한글, 한자)로. 예: (2026)->('병오','丙午')."""
    from datetime import date as _d
    from backend.app.saju.pillars import compute_pillars
    from backend.app.saju.types import BirthInput as _BI, CalendarType as _CT
    fp, *_ = compute_pillars(_BI(birth_date=_d(yr, 6, 1), calendar=_CT.SOLAR))
    s = _gz_ko(fp.year)  # '병오(丙午)'
    ko = s.split("(")[0]
    hj = s[s.find("(") + 1 : s.find(")")] if "(" in s and ")" in s else ""
    return ko, hj


def _allowed_year_ganji() -> set[str]:
    """올해·내년의 실제 세운 간지(한글). 예: {'병오', '정미'}."""
    from datetime import date as _d
    y = _d.today().year
    out: set[str] = set()
    for yr in (y, y + 1):
        try:
            out.add(_year_ko_hj(yr)[0])
        except Exception:  # noqa: BLE001
            pass
    return out


# '올해(금년)/내년(명년)' 바로 뒤의 괄호 간지(예: '내년 (임인, 壬寅)') — 간지 뒤 '년'이 없어
# _GANJI_YEAR_HANJA_RE 로는 못 잡힌다. 상대연도어를 키로, 실제 세운 간지로 강제 교정한다.
_REL_YEAR_GANJI_RE = re.compile(
    r"(올해|금년|내년|명년)\s*[\(（]\s*"
    r"[갑을병정무기경신임계][자축인묘진사오미신유술해]\s*[,，·]?\s*[一-鿿]{0,2}\s*[\)）]"
)

# '올해 세운이 임오(壬午)로' 처럼 세운 키워드 뒤의 간지 — 실제 세운으로 강제 교정.
# '세운' 앵커 + 한자병기 필수 → '올해 세운이 갑자기…'('갑자'가 간지) 같은 오탐을 원천 차단.
_REL_YEAR_SEUN_RE = re.compile(
    r"(올해|금년|내년|명년)(?:\s*의)?\s*세운[은는이가]?\s*"
    r"([갑을병정무기경신임계][자축인묘진사오미신유술해])\s*\([一-鿿]{1,2}\)"
)

# 간지 한글↔한자 표준 매핑 — '계묘(癸巳)'처럼 한글-한자 불일치를 결정적으로 교정(계묘=癸卯).
_STEM_KO2HJ = dict(zip(STEM_KOREAN, HEAVENLY_STEMS))      # 갑→甲
_BRANCH_KO2HJ = dict(zip(BRANCH_KOREAN, EARTHLY_BRANCHES))  # 자→子
_GANJI_HJ_PAREN_RE = re.compile(
    r"([갑을병정무기경신임계])([자축인묘진사오미신유술해])\s*\(\s*([一-鿿]{2})\s*\)"
)


def _canon_ganji_hanja(stem_ko: str, branch_ko: str) -> str | None:
    s = _STEM_KO2HJ.get(stem_ko)
    b = _BRANCH_KO2HJ.get(branch_ko)
    return (s + b) if (s and b) else None


def _fix_ganji_hanja(text: str) -> str:
    """'한글간지(漢字)' 병기에서 한자가 한글과 안 맞으면 표준 한자로 교정. 맞으면 그대로.

    예: 계묘(癸巳)→계묘(癸卯), 병오(丙午)→그대로. 유효 간지+2자 한자괄호만 건드려 오탐 없음.
    """
    def _sub(m: "re.Match") -> str:
        correct = _canon_ganji_hanja(m.group(1), m.group(2))
        if correct and m.group(3) != correct:
            return f"{m.group(1)}{m.group(2)}({correct})"
        return m.group(0)
    return _GANJI_HJ_PAREN_RE.sub(_sub, text)


def _scrub_stale_year_ganji(text: str) -> str:
    """과거연도·틀린 세운 간지를 '올해'로 중화(결정적). 올해/내년 실제 간지·한자는 보존."""
    if not text:
        return text
    from datetime import date as _d
    cur = _d.today().year
    allowed = _allowed_year_ganji()
    if not allowed:
        return text  # 세운 계산 불가 시 손대지 않음(안전)
    try:
        cur_ko, cur_hj = _year_ko_hj(cur)
        nxt_ko, nxt_hj = _year_ko_hj(cur + 1)
    except Exception:  # noqa: BLE001
        return text
    out = text
    # 0) '올해/내년 (간지[, 한자])' 헤더의 간지를 실제 세운으로 강제 교정(틀려도 올바르게 채움).
    #    예: '내년 (임인, 壬寅)' → '내년 (정미, 丁未)', '올해 (임오)' → '올해 (병오, 丙午)'.
    def _rel_fix(m: "re.Match") -> str:
        word = m.group(1)
        if word in ("올해", "금년"):
            return f"{word} ({cur_ko}, {cur_hj})"
        return f"{word} ({nxt_ko}, {nxt_hj})"
    out = _REL_YEAR_GANJI_RE.sub(_rel_fix, out)
    # 0-b) '올해 세운이 임오(壬午)로' 처럼 세운 키워드 뒤 간지 → 실제 세운 간지+한자로 교정.
    def _seun_fix(m: "re.Match") -> str:
        word = m.group(1)
        ko, hj = (cur_ko, cur_hj) if word in ("올해", "금년") else (nxt_ko, nxt_hj)
        prefix = m.group(0)[: m.start(2) - m.start(0)]  # '올해 세운이 ' 까지 보존
        return f"{prefix}{ko}({hj})"
    out = _REL_YEAR_SEUN_RE.sub(_seun_fix, out)
    # 1) 틀린 간지'년'(+선택적 한자 병기, 예: 계묘년·계묘년(癸巳)) → '올해'. 허용 간지(병오년 등)는 원형 보존.
    out = _GANJI_YEAR_HANJA_RE.sub(lambda m: m.group(0) if m.group(1) in allowed else "올해", out)
    # 2) 과거 4자리 연도(YYYY년, 올해 미만) → '올해'
    out = re.sub(
        r"(?:19|20)\d{2}\s*년",
        lambda m: "올해" if int(re.sub(r"\D", "", m.group(0))) < cur else m.group(0),
        out,
    )
    # 3) 괄호 잔재 정리: (올해)/(계묘년) 등 → 제거
    out = re.sub(r"\s*\((?:올해|[갑을병정무기경신임계][자축인묘진사오미신유술해]년?)\)", "", out)
    # 4) '올해는 2023년' → '올해는 올해' 같은 잔재 축약: '올해(는/은) 올해' → '올해(는/은)'
    out = re.sub(r"(올해)(\s*[은는])\s*올해", r"\1\2", out)
    # '올해 올해'/'올해와 올해' 중복 표현 축약
    out = re.sub(r"올해(?:\s*[,·]?\s*(?:과|와|및)?\s*올해)+", "올해", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    # 5) 간지 한글-한자 불일치 결정적 교정(예: 계묘(癸巳)→계묘(癸卯)) — 위 단계 잔여분까지.
    out = _fix_ganji_hanja(out)
    return out.strip()


def _is_admin(user) -> bool:
    """풀이 근거(사주명식 근거·RAG 자료출처)는 영업비밀 → 관리자에게만 노출.

    user.role == 'admin'일 때만 True. 비관리자에겐 evidence/sources를 클라이언트로 보내지 않는다
    (프론트 숨김만으로는 네트워크/DOM 검사로 노출되므로 전송 단계에서 차단)."""
    return bool(user is not None and getattr(user, "role", None) == "admin")


def _row_to_messages(row: ChatSessionRow, *, include_sources: bool = True) -> list[ChatMessageDTO]:
    out: list[ChatMessageDTO] = []
    for m in row.messages:
        sources = [ChatSourceDTO(**s) for s in (m.sources_json or [])] if include_sources else []
        content = m.content
        # assistant + 미리보기 + 아직 reveal 안 됨 → 50% 컷 형태로 표출
        is_preview = bool(getattr(m, "is_preview", False))
        revealed = bool(getattr(m, "preview_revealed", False))
        if m.role == "assistant" and is_preview and not revealed:
            content = _make_preview(content)
        out.append(
            ChatMessageDTO(
                id=m.id,
                role=m.role,
                content=content,
                created_at=m.created_at,
                sources=sources,
                is_preview=is_preview,
                preview_revealed=revealed,
                credits_charged=getattr(m, "credits_charged", 0) or 0,
                reveal_credits_charged=getattr(m, "reveal_credits_charged", 0) or 0,
                reveal_cost=getattr(m, "reveal_cost", 0) or 0,
            )
        )
    return out


def _make_preview(text: str) -> str:
    s = get_settings()
    # 절대 문자수 기준(실시간 스트리밍 컷과 일치). 과거 비율 설정은 폴백으로만 사용.
    n = settings_service.get_cached_int("preview_max_chars", getattr(s, "preview_max_chars", 0)) \
        or max(1, int(len(text) * s.preview_char_ratio))
    if n >= len(text):
        return text
    head = text[:n]
    # 문장 경계(마침표·물음표·느낌표·줄바꿈)에서 자르면 '…다르게'처럼 문장 중간에서 끊기지 않음.
    # 단, 너무 앞에서 잘리면 분량이 줄어드니 컷 위치의 55% 이후 경계만 사용.
    cut = max(head.rfind("."), head.rfind("!"), head.rfind("?"), head.rfind("\n"))
    if cut >= int(n * 0.55):
        return head[:cut + 1].rstrip() + " ..."
    return head.rstrip() + " ..."


class SessionLimitError(Exception):
    """채팅 세션 개수 한도 초과(계획 5.6 R)."""


class ServiceUnavailableError(Exception):
    """외부 의존 서비스 일시 불가(Qdrant 검색 / Ollama LLM 다운·연결 실패).

    API 레이어에서 HTTP 503 + 친절 메시지로 매핑한다. message는 사용자 노출용.
    """


def _search_corpus(query: str, k: int, *, session_id: str | None = None, question: str | None = None):
    """참고자료 검색(RAG). Qdrant 연결 실패 시 ServiceUnavailableError로 변환.

    question이 주어지면 검색 점수를 retrieval_logs에 best-effort 기록한다
    (일일 질문 인사이트 배치의 코퍼스 갭 분석용 — 실패해도 답변 흐름엔 영향 없음).
    """
    s = get_settings()
    try:
        # 신뢰성 게이트: 저관련(min_score)·OCR깨짐(low_quality)·예시명식(is_example) 제거 + 신뢰등급 재랭킹.
        # over-fetch 후 게이트하므로 k개 미만이 될 수 있음(저관련뿐이면 0건→근거 없이 LLM 단독, 환각 방지).
        chunks = _get_retriever().search(
            query, top_k=k,
            min_score=s.rag_min_score,
            exclude_low_quality=s.rag_exclude_low_quality,
            exclude_examples=True,  # 타인 예시 사주 오염 차단 — 전 메뉴 공통
            exclude_youtube=s.rag_exclude_youtube,  # 유튜브 자막(잡담) 검색 배제(전문가 요청)
            tier_boosts={1: s.rag_tier1_boost, 2: s.rag_tier2_boost, 3: 0.0},
            rerank=s.rag_reranker_enabled,        # cross-encoder 재점수(코사인 압축 해결)
            rerank_top_n=s.rag_rerank_top_n,
            rerank_min_score=s.rag_reranker_min_score,
        )
    except ServiceUnavailableError:
        raise
    except Exception as e:  # noqa: BLE001 — qdrant 연결거부/타임아웃 등
        raise ServiceUnavailableError(
            "참고자료 검색 서비스(Qdrant)에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
        ) from e
    if question:
        _log_retrieval(session_id, question, k, chunks)
    return chunks


def _retrieve_context(
    query: str, k: int, depth: str, *, session_id: str | None = None, question: str | None = None
) -> list[RetrievedChunk]:
    """기본·심화 모두 색인(학습) 자료를 RAG로 활용한다.

    학습(색인)한 자료를 기본 답변에도 '즉시' 반영하기 위해 두 모드 모두 코퍼스를 검색한다.
    단, 기본(basic)은 Qdrant 장애 시 LLM 단독으로 graceful degrade 하여 빠르고 안정적인
    기본 응답을 보존하고, 심화(deep)는 RAG 품질을 보장하므로 장애 시 예외를 그대로 올린다.
    """
    if depth == "deep":
        return _search_corpus(query, k, session_id=session_id, question=question)
    try:
        return _search_corpus(query, k, session_id=session_id, question=question)
    except ServiceUnavailableError:
        return []


# ── 도구 메뉴(궁합·택일·작명) 공용: 사주와 동일한 내부 RAG·외부 폴백 구조 제공 ──
def retrieve_for_menu(
    query: str, depth: str, *, session_id: str | None = None, question: str | None = None
) -> list[RetrievedChunk]:
    """궁합·택일·작명 공용 RAG. 기본·심화 모두 학습 코퍼스를 활용(기본은 장애 시 degrade)."""
    s = get_settings()
    k = max(1, min(s.rag_top_k_default, s.rag_max_top_k))
    return _retrieve_context(query, k, depth, session_id=session_id, question=question)


def rag_context_block(chunks: list[RetrievedChunk]) -> str | None:
    """검색 결과를 프롬프트용 [참고자료] 블록 문자열로 변환. 없으면 None."""
    if not chunks:
        return None
    return "\n\n".join(f"[자료{i}] (출처:{c.source}) {c.text}" for i, c in enumerate(chunks, 1))


def external_fallback_answer(
    *, question: str, evidence: str | None, rag_context: str | None,
    dialect_instruction: str | None, saju_summary: str | None = None,
    locale: str = "ko",
) -> str | None:
    """로컬 Ollama 전체 다운 시 외부(Claude)로 본문 생성 폴백. 실패/비활성 시 None.

    locale='vi' 면 외부 생성도 베트남어(ko 는 기존 한국어 그대로)."""
    try:
        out = external_llm.generate_answer(
            question=question, saju_summary=saju_summary, evidence=evidence,
            rag_context=rag_context, dialect_instruction=dialect_instruction,
            locale=locale,
        )
        return out.strip() if out and out.strip() else None
    except Exception:  # noqa: BLE001
        return None


def _log_retrieval(session_id: str | None, question: str, top_k: int, chunks: list[RetrievedChunk]) -> None:
    try:
        from backend.app.core.db import get_session_factory
        from backend.app.repositories.models import RetrievalLog

        scores = [c.score for c in chunks]
        db = get_session_factory()()
        try:
            db.add(RetrievalLog(
                session_id=session_id,
                question=question[:2000],
                top_k=top_k,
                max_score=max(scores) if scores else 0.0,
                avg_score=(sum(scores) / len(scores)) if scores else 0.0,
                results_json=[
                    {"source": c.source, "chunk_id": c.chunk_id, "score": round(c.score, 4)}
                    for c in chunks
                ],
            ))
            db.commit()
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        pass


def create_session(
    db: Session,
    birth: BirthDTO,
    top_k: int | None,
    user: User | None = None,
    locale: str = "ko",
) -> tuple[str, str, SajuChart]:
    """채팅 세션 생성. birth 필수. DB에 영속. user가 있으면 소유자로 연결.

    locale(요청 로케일)은 BirthInput 계산(역법·경도)과 세션 행 locale 에 함께 반영된다."""
    if birth is None:
        raise ValueError("birth is required: 채팅 시작 전 생년월일(시) 정보가 필요합니다.")
    s = get_settings()
    # 채팅 세션 개수 제한(계획 5.6 R) — 회원만 적용
    if user is not None:
        # '상담 시작'은 질문 전에도 세션을 즉시 만들어 빈 세션이 쌓인다(한도 소진 주범).
        # 새 세션을 만들기 전, 이 회원의 빈 세션(메시지 0개)을 자동 정리한다.
        chat_repo.delete_empty_sessions(db, user.id)
        cnt = chat_repo.count_user_sessions(db, user.id)
        if cnt >= s.max_sessions_per_user:
            raise SessionLimitError(
                f"session_limit_reached: {cnt}/{s.max_sessions_per_user}"
            )
    sid = uuid.uuid4().hex
    k = max(1, min(top_k or s.rag_top_k_default, s.rag_max_top_k))
    bi = _to_birth_input(birth, locale=locale)
    chart = build_chart(bi)
    saju_summary = _build_saju_summary(chart, bi)
    chat_repo.create_session(
        db,
        session_id=sid,
        top_k=k,
        birth_dict=birth.model_dump(mode="json"),
        saju_summary=saju_summary,
        chart_json=chart.model_dump(mode="json"),
        user_id=user.id if user else None,
        locale=locale,
    )
    return sid, saju_summary, chart


def get_session_row(db: Session, session_id: str) -> ChatSessionRow | None:
    return chat_repo.get_session(db, session_id)


def list_messages(db: Session, session_id: str, user=None) -> list[ChatMessageDTO]:
    row = chat_repo.get_session(db, session_id)
    if row is None:
        return []
    return _row_to_messages(row, include_sources=_is_admin(user))


def _upcoming_months(today, total_min: int = 6) -> list[tuple[int, int, str]]:
    """상담 당월 '이후' 각 달의 월운 간지 목록 [(연, 월, '을미(乙未)'), ...].

    범위 = 그 해 12월(연말)까지 + 최소 total_min개월(연말까지가 부족하면 이듬해로 연장). 전문가 요청:
    월별 흐름은 상담일부터 최소 6개월·해당 연도 끝까지 나와야 한다. 각 달 대표 월운은 절입(양력 4~8일)
    이후로 안정적인 '중순(15일)' 기준으로 결정적 계산한다(LLM이 월운 간지를 지어내는 환각 방지).
    """
    from datetime import date as _date
    from backend.app.saju.pillars import compute_pillars
    from backend.app.saju.types import BirthInput as _BI, CalendarType as _CT
    total = max(total_min, 12 - today.month + 1)
    out: list[tuple[int, int, str]] = []
    y, m = today.year, today.month
    for _ in range(total - 1):   # 당월 제외 — 당월은 '이번 달' 간지로 별도 제공
        m += 1
        if m > 12:
            m, y = 1, y + 1
        fp, *_ = compute_pillars(_BI(birth_date=_date(y, m, 15), calendar=_CT.SOLAR))
        out.append((y, m, _gz_ko(fp.month)))
    return out


def _current_luck_block(include_iljin: bool = False) -> str:
    """오늘 기준 세운(연)/월운(월) 간지를 한글(한자)로 제공(항상). include_iljin=True면 일진(일)도 추가.

    세운/월운은 '올해 경자년' 같은 환각을 막으려 항상 제공한다(실측: 시험운 질문에서 세운 미주입→환각).
    또한 상담일부터 연말(+최소 6개월)까지의 '월별 간지'를 함께 제공해, 월별 흐름을 물으면 당월 한 달만
    쓰고 끝나지 않고 각 달을 결정적 간지 근거로 풀 수 있게 한다(전문가 요청 — 월별운은 6개월+연말까지).
    일진(오늘)은 드리프트(묻지 않은 오늘 운세로 새는 현상)를 유발하므로 '오늘/지금/일진' 등 일 단위
    질문일 때만 포함한다.
    """
    from datetime import date as _date
    from backend.app.saju.pillars import compute_pillars
    from backend.app.saju.types import BirthInput as _BI, CalendarType as _CT
    try:
        today = _date.today()
        fp, *_ = compute_pillars(_BI(birth_date=today, calendar=_CT.SOLAR))
        iljin = f", 오늘(일진) {_gz_ko(fp.day)}" if include_iljin else ""
        scope = "올해·이번 달" + ("·오늘" if include_iljin else "")
        # 상담일 이후 월별 간지(연말+최소 6개월) — 연도가 바뀌는 첫 달에만 '연' 표기.
        months_line = ""
        ups = _upcoming_months(today)
        if ups:
            parts: list[str] = []
            last_y = None
            for (yy, mm, g) in ups:
                parts.append(f"{yy}년 {mm}월={g}" if yy != last_y else f"{mm}월={g}")
                last_y = yy
            months_line = (
                f"\n[다가오는 월별 간지] {', '.join(parts)}. "
                f"'월별 흐름'을 풀 때는 이번 달({_gz_ko(fp.month)})부터 위 각 달까지 그 달의 월운 간지만 "
                f"인용하고, 목록에 없는 달의 간지는 지어내지 마세요."
            )
        return (
            f"[현재 시점 간지] 오늘은 {today.isoformat()}, 올해는 {today.year}년 {_gz_ko(fp.year)}, "
            f"이번 달은 {_gz_ko(fp.month)}{iljin}. "
            f"연도를 적을 경우 반드시 올해={today.year}년(또는 그 이후)만 쓰고, 지난 연도(예: 2023년)나 "
            f"다른 간지를 지어내지 마세요. '{scope}' 등 현재 운은 위 연도·간지를 그대로 사용하세요."
            f"{months_line}"
        )
    except Exception:
        return ""


def _with_current_luck(saju_summary: str | None) -> str | None:
    """보강 단계용 — saju_summary 에 '[현재 시점 간지]'(올해 세운)를 주입(멱등).

    보강(qwen/Claude)은 초안의 날짜·간지 가드를 못 받아 '23년 계묘년' 같은 과거연도·
    틀린 간지를 다시 지어냈다(실측). 현재 세운을 함께 줘서 그것만 인용하게 한다.
    """
    if saju_summary and "[현재 시점 간지]" in saju_summary:
        return saju_summary
    luck = _current_luck_block()
    if not luck:
        return saju_summary
    return f"{saju_summary}\n\n{luck}" if saju_summary else luck


# 일진(오늘) 블록은 '일 단위' 질문일 때만 주입한다(세운/월운은 _current_luck_block에서 항상 제공).
# 무조건 일진을 주면 시험운·직업운 등에서 LLM이 '오늘 일진'으로 새고 과거 날짜를 지어냄(실측 드리프트).
_ILJIN_KEYWORDS = (
    "오늘", "지금", "요즘", "최근", "현재", "이즈음", "당장", "며칠", "이 날", "그날", "그 날",
    "일진", "택일", "길일", "당일",
)


def _question_needs_iljin(question: str) -> bool:
    """질문이 '오늘/지금/일진/택일' 등 일 단위 시점일 때만 일진 블록 포함."""
    return any(k in (question or "") for k in _ILJIN_KEYWORDS)


# 질문에 적힌 '구체적 날짜'(상대연도?·연?+월+일)의 간지(일진·세운·월운)를 결정적으로 계산해 제공 →
# 시험일 등 임의 날짜의 일진/세운을 LLM이 지어내는 환각 차단. 연 생략=올해, '26년'→2026, '내년 3월'→내년.
_REL_YEAR = {"올해": 0, "금년": 0, "내년": 1, "명년": 1, "내후년": 2, "후년": 2, "작년": -1, "재작년": -2}
_QDATE_RE = re.compile(
    r"(?:(?P<rel>올해|금년|내후년|내년|명년|후년|재작년|작년)\s*)?"
    r"(?:(?P<y>\d{2,4})\s*년[\s,]*)?"
    r"(?P<m>\d{1,2})\s*월[\s,]*(?P<d>\d{1,2})\s*일"
)


def _question_dates(question: str, today=None) -> list:
    """질문에서 (상대연도?·연?,월,일) 파싱 → date 리스트(최대 3, 중복 제거).

    연도 우선순위: 명시 연('26년'→2026, 2자리=2000+YY) > 상대연(내년/작년 등) > 생략(올해).
    """
    from datetime import date as _date
    if not question:
        return []
    today = today or _date.today()
    out: list = []
    seen: set = set()
    for m in _QDATE_RE.finditer(question):
        mo, da = int(m.group("m")), int(m.group("d"))
        ys, rel = m.group("y"), m.group("rel")
        if ys is not None:
            yr = int(ys) + 2000 if int(ys) < 100 else int(ys)
        elif rel is not None:
            yr = today.year + _REL_YEAR[rel]
        else:
            yr = today.year
        try:
            dt = _date(yr, mo, da)
        except ValueError:
            continue
        if 2000 <= yr <= 2100 and dt not in seen:
            seen.add(dt)
            out.append(dt)
        if len(out) >= 3:
            break
    return out


def _question_date_block(question: str) -> str:
    """질문 속 구체적 날짜의 간지(일진·세운·월운)를 결정적으로 계산·제공(환각 차단)."""
    from backend.app.saju.pillars import compute_pillars
    from backend.app.saju.types import BirthInput as _BI, CalendarType as _CT
    dates = _question_dates(question)
    if not dates:
        return ""
    lines: list[str] = []
    for dt in dates:
        try:
            fp, *_ = compute_pillars(_BI(birth_date=dt, calendar=_CT.SOLAR))
        except Exception:  # noqa: BLE001
            continue
        lines.append(
            f"  · {dt.year}년 {dt.month}월 {dt.day}일 = 일진 {_gz_ko(fp.day)}, "
            f"세운 {_gz_ko(fp.year)}, 월운 {_gz_ko(fp.month)}"
        )
    if not lines:
        return ""
    return (
        "[질문 날짜 간지] 질문에 나온 날짜의 정확한 간지는 다음과 같습니다. 이 값만 그대로 쓰고, "
        "절대 다른 간지로 바꾸거나 일진을 지어내지 마세요:\n" + "\n".join(lines)
    )


def _summary_from_chart_json(chart_json: dict | None) -> str:
    """chart_json → 명식 요약(년주·월주·일주·시주·일간·대운). tool 메뉴(택일·작명 등) 명식 주입용."""
    if not chart_json:
        return ""
    try:
        from backend.app.saju.types import SajuChart
        return _build_saju_summary(SajuChart.model_validate(chart_json))
    except Exception:  # noqa: BLE001
        return ""


def _aux_ganji_blocks(
    question: str | None, chart_json: dict | None = None, *, include_summary: bool = False
) -> str:
    """비-chat 메뉴(tool/compat)의 user content 뒤에 덧붙일 명식·간지 보조 블록.

    chat의 _build_user_prompt와 동일 정보를 메뉴 간 일관 적용해 '메뉴 이탈 명식/세운 질문'의
    환각을 차단한다. include_summary=True면 전체 명식 요약을 앞에 붙인다(택일·작명 brief엔 4주 없음).
    세운/월운은 항상, 일진은 일 단위 질문, 질문 날짜 간지는 날짜 포함 질문에 주입.
    """
    parts: list[str] = []
    if include_summary:
        s = _summary_from_chart_json(chart_json)
        if s:
            parts.append(s)
    luck = _current_luck_block(include_iljin=_question_needs_iljin(question or ""))
    if luck:
        parts.append(luck)
    qd = _question_date_block(question or "")
    if qd:
        parts.append(qd)
    return "\n\n".join(parts).strip()


def _gwanbeop_block_for(question: str, chart_json: dict | None, is_male: bool | None) -> str:
    """질문 주제에 성립한 관법(선생님 공식) 블록 — 결정적 계산(케이스 #4). 실패·미성립 시 ''."""
    if not chart_json:
        return ""
    try:
        from datetime import date as _date
        from backend.app.saju.gwanbeop import gwanbeop_block
        from backend.app.saju.pillars import compute_pillars
        from backend.app.saju.types import BirthInput as _BI, CalendarType as _CT
        fp, *_ = compute_pillars(_BI(birth_date=_date.today(), calendar=_CT.SOLAR))
        return gwanbeop_block(
            question, chart_json, seun_stem=fp.year.stem, seun_branch=fp.year.branch,
            wolun_stem=fp.month.stem, wolun_branch=fp.month.branch,  # 일시적 사안은 월운 대입(선생님 원칙)
            is_male=is_male,
        ) or ""
    except Exception:  # noqa: BLE001 — 관법 주입은 부가 기능: 실패해도 기존 흐름 유지
        return ""


def _build_user_prompt(question: str, ctx: list[RetrievedChunk], saju_summary: str | None,
                       chart_json: dict | None = None, is_male: bool | None = None) -> str:
    parts: list[str] = []
    if saju_summary:
        parts.append(saju_summary)
    # 세운/월운은 항상 제공(올해 간지 환각 차단), 일진은 '오늘/지금/일진/택일' 등 일 단위 질문일 때만(드리프트 방지)
    luck = _current_luck_block(include_iljin=_question_needs_iljin(question))
    if luck:
        parts.append(luck)
    # 질문 속 구체적 날짜(시험일 등)의 간지를 결정적으로 계산·제공 → 날짜 간지 환각 차단
    qdate = _question_date_block(question)
    if qdate:
        parts.append(qdate)
    # 관법(선생님 공식) — 질문 주제에 실제 성립한 공식만 주입(감수 완료 룰만, 케이스 #4)
    gb = _gwanbeop_block_for(question, chart_json, is_male)
    if gb:
        parts.append(gb)
    # 물상(명리전 원문) — 성격·관계류 질문에 명식 실존 조합의 원문 발췌만 주입
    try:
        from backend.app.saju.mulsang import mulsang_block
        mb = mulsang_block(question, chart_json)
        if mb:
            parts.append(mb)
    except Exception:  # noqa: BLE001 — 부가 기능: 실패해도 기존 흐름 유지
        pass
    if ctx:
        parts.append("[참고자료]")
        for i, c in enumerate(ctx, 1):
            parts.append(f"--- 자료{i} (출처: {c.source}, score={c.score:.3f}) ---\n{c.text}")
    # 명식 재확인(최근 맥락 — 약한 LLM이 참고자료 예시 명식과 혼동하지 않게 질문 직전 재삽입)
    if saju_summary:
        gz = next((ln.strip() for ln in saju_summary.splitlines() if "년주" in ln and "일주" in ln), "")
        if gz:
            parts.append(
                f"[명식 재확인] 본인 명식은 '{gz}' 뿐입니다. 위 참고자료에 다른 사람의 명식·간지가 "
                f"있어도 쓰지 말고, 답변의 모든 지지·천간을 이 명식과 일치시키세요."
            )
    # 질문은 맨 끝(모델이 마지막에 읽는 위치 = 최강 가중)에 두고, 주제 집중 지시를 덧붙인다.
    parts.append(
        f"[지금 질문]\n{question}\n\n"
        "→ 위 '지금 질문'의 핵심 주제에 정조준해 답하세요. 직전 대화가 다른 주제였더라도 그 주제를 "
        "이어가지 말고, 지금 질문의 주제로만 새로 풀이하세요(같은 주제의 후속질문이면 이어서 답)."
    )
    return "\n\n".join(parts)


def _history_msgs(row: ChatSessionRow, *, limit: int = 6, assistant_cap: int = 500) -> list[dict]:
    """LLM에 넣을 대화 이력. 최근 limit턴만, 이전 '답변'은 앞부분만 발췌.

    이력이 길면 (1) num_ctx를 채워 새 답변이 잘리고(실측: 관리자 답변 중간 잘림),
    (2) 모델이 이전 답변을 그대로 반복한다. 최근 6턴 + 답변 500자 발췌로 둘 다 완화한다.
    """
    recent = [m for m in row.messages if m.role in ("user", "assistant")][-limit:]
    out: list[dict] = []
    for m in recent:
        content = m.content or ""
        if m.role == "assistant" and len(content) > assistant_cap:
            content = content[:assistant_cap] + " …(이전 답변은 맥락용으로 일부만 표시)"
        out.append({"role": m.role, "content": content})
    return out


def _coerce_keep_alive(v):
    """Ollama keep_alive 값 정규화.

    Ollama /api/chat 의 keep_alive 는 정수(초) 또는 단위 포함 문자열("5m","30s")만 허용한다.
    .env(OLLAMA_KEEP_ALIVE)는 항상 문자열로 들어오므로 "-1"/"600" 같은 숫자 문자열은
    정수로 변환해야 한다(단위 없는 숫자 문자열은 'missing unit in duration' 400 유발).
    """
    if isinstance(v, str):
        t = v.strip()
        try:
            return int(t)
        except ValueError:
            return t  # "5m", "30s" 등 단위 포함 문자열은 그대로 전달
    return v


def _draft_model(locale: str = "ko") -> str:
    """1차 초안 로컬 모델 — ko=exaone3.5 / vi=Qwen3(공용 Ollama GPU1의 qwen3:14b)."""
    s = get_settings()
    return s.ollama_model_vi if locale == "vi" else s.ollama_model


def _refine_model(locale: str = "ko") -> str:
    """2차 보강 로컬 모델 — ko=qwen2.5 / vi=Qwen3."""
    s = get_settings()
    return s.ollama_refine_model_vi if locale == "vi" else s.ollama_refine_model


def _call_ollama(
    messages: list[dict], model: str | None = None, temperature: float | None = None
) -> str:
    s = get_settings()
    payload = {
        "model": model or s.ollama_model,
        "messages": messages,
        "stream": False,
        "keep_alive": _coerce_keep_alive(s.ollama_keep_alive),
        "options": {"temperature": s.ollama_temperature if temperature is None else temperature,
                    "num_ctx": s.ollama_num_ctx, "num_predict": s.ollama_num_predict},
    }
    if str(payload["model"]).startswith("qwen3"):
        payload["think"] = False  # Qwen3 thinking 비활성(안 끄면 content 빈 채 thinking에 토큰 소모)
    url = f"{s.ollama_url}/api/chat"
    for attempt in range(2):
        try:
            r = httpx.post(url, json=payload, timeout=s.ollama_timeout_sec)
            r.raise_for_status()
            return r.json()["message"]["content"]
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and attempt == 0:
                continue
            raise ServiceUnavailableError(
                "답변 생성 서비스(LLM)에 일시적으로 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
            ) from e
        except httpx.RequestError as e:
            if attempt == 0:
                continue
            raise ServiceUnavailableError(
                "답변 생성 서비스(LLM)에 일시적으로 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
            ) from e
    raise ServiceUnavailableError("답변 생성 서비스(LLM)를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")


# 후속질문 생성 실패/빈 응답 시 폴백(정적). 프론트 SUGGEST_CHIPS와 동일 취지.
_FALLBACK_SUGGESTIONS = [
    "내 성격과 강점·약점은 어떤가요?",
    "직업·적성은 어떤 분야가 맞나요?",
    "재물운과 금전운을 알려주세요.",
    "건강에서 주의할 점은?",
    "올해 전체 운세가 어떤가요?",
    "연애·결혼운은 어떤가요?",
]


def suggestions_from_convo(convo: str, n: int, *, topic: str, fallback: list[str]) -> list[str]:
    """대화 맥락으로 '이어서 물어볼' 후속질문 n개 생성(로컬 Ollama, 무과금).

    사주·궁합·택일·작명 등 전 메뉴 공용. 실패/빈결과면 메뉴별 정적 폴백을 반환해
    항상 무언가 보이게 한다(추가 상담 유도 → 과금).
    """
    sys_msg = f"당신은 한국 {topic} 도우미입니다. 사용자가 더 깊이 상담하도록 돕습니다."
    user_msg = (
        f"아래는 진행 중인 {topic} 대화입니다.\n\n{convo}\n\n"
        f"사용자가 이어서 물어볼 만한 자연스러운 후속 질문 {n}개를 만들어 주세요.\n"
        "- 위 답변 내용·주제와 직접 연결되는 구체적인 질문\n"
        "- 각 질문은 한 줄, 25자 이내, 물음표로 끝남\n"
        "- 번호·설명·따옴표 없이 질문 문장만, 줄바꿈으로 구분"
    )
    try:
        out = _call_ollama(
            [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}],
            temperature=0.8,
        )
    except Exception:  # noqa: BLE001 — LLM 실패는 폴백으로
        return fallback[:n]
    qs: list[str] = []
    seen: set[str] = set()
    for line in (out or "").splitlines():
        q = line.strip().lstrip("0123456789.-)·•*• ").strip().strip('"').strip("'")
        if q and "?" in q and 4 <= len(q) <= 40 and q not in seen:
            seen.add(q)
            qs.append(q)
    return qs[:n] if qs else fallback[:n]


def synthesize_consultation(
    conversation: list[dict], *, topic: str = "사주 상담", locale: str = "ko"
) -> str:
    """여러 질문·답변(상담 전체)을 하나의 매끄러운 '종합 감정서' 본문으로 재구성(로컬 LLM, 무과금).

    연속 질문으로 단편화된 답변을 중복 제거·주제별 단락으로 묶어 하나의 글로 정리한다.
    마크다운/기호는 쓰지 않게 강제(_compose 규칙 + pdf 단계 _strip_md 이중 안전망).
    LLM 실패 시 어시스턴트 답변을 단순 연결해 폴백(항상 무언가 생성).
    locale='vi' 면 베트남어 프롬프트·vi 모델(_draft_model)로 생성(ko 룰블록/한국어 강제 미주입).
    """
    q_lab, a_lab = ("Câu hỏi", "Trả lời") if locale == "vi" else ("질문", "답변")
    convo = "\n\n".join(
        f"[{q_lab if m.get('role') == 'user' else a_lab}] {(m.get('content') or '').strip()}"
        for m in conversation if (m.get('content') or '').strip()
    )
    fallback = "\n\n".join(
        (m.get('content') or '').strip()
        for m in conversation if m.get('role') == 'assistant' and (m.get('content') or '').strip()
    )
    if not convo.strip():
        return fallback
    if locale == "vi":
        # vi: 한글(한자) 관습의 ko 룰블록은 언어 충돌 → 넣지 않고, 마크다운 금지만 베트남어로 강제.
        sys_msg = (
            f"Bạn là chuyên gia thẩm định đang tổng hợp buổi {topic}. "
            "Hãy tái cấu trúc toàn bộ cuộc trò chuyện tư vấn dưới đây thành một bản luận giải tổng hợp mạch lạc. "
            "TUYỆT ĐỐI không dùng markdown (#, **, -, bảng); chỉ viết thành đoạn văn tự nhiên như đang ngồi tư vấn trực tiếp."
        )
        user_msg = (
            f"{convo}\n\n"
            "Hãy gộp toàn bộ buổi tư vấn trên theo chủ đề (bỏ lời chào và nội dung trùng lặp), "
            "viết thành một bản luận giải tổng hợp tự nhiên như một chuyên gia đúc kết. "
            "Theo mạch: dẫn nhập (tóm ý) → luận giải theo chủ đề → kết luận và lời khuyên tổng hợp, "
            "viết bằng tiếng Việt thành đoạn văn đầy đủ (tối thiểu khoảng 800 ký tự)."
        )
        model = _draft_model("vi")
    else:
        sys_msg = (
            f"당신은 한국 {topic}을(를) 정리하는 전문 감정사입니다. "
            "아래 상담 전체 대화를 하나의 매끄러운 '종합 감정서'로 재구성하세요.\n"
            + CONSULTANT_STYLE_RULE
        )
        user_msg = (
            f"{convo}\n\n"
            "위 상담 전체를 인사말·중복 없이 주제별로 자연스럽게 묶어, 상담가가 정리해 주듯 "
            "하나의 종합 감정서로 작성하세요. 도입(요지) → 주제별 해설 → 종합 결론·조언 흐름으로, "
            "한국어 줄글로 충분히(최소 1,000자) 정리하세요."
        )
        model = None  # ko 기본 모델(_call_ollama 기본값)
    try:
        out = _call_ollama(
            [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}],
            model=model, temperature=0.4,
        )
    except Exception:  # noqa: BLE001
        return fallback
    out = (out or "").strip()
    return out if len(out) >= 200 else (fallback or out)


def generate_followup_questions(db: Session, session_id: str, n: int = 6) -> list[str]:
    """사주 채팅: 최근 질문+답변 맥락으로 후속 추천질문 n개(로컬 LLM, 무과금)."""
    row = chat_repo.get_session(db, session_id)
    if row is None:
        return _FALLBACK_SUGGESTIONS[:n]
    qa = [m for m in row.messages if m.role in ("user", "assistant")]
    if not qa:
        return _FALLBACK_SUGGESTIONS[:n]
    convo = "\n".join(
        f"{'질문' if m.role == 'user' else '답변'}: {(m.content or '')[:400]}" for m in qa[-4:]
    )
    return suggestions_from_convo(convo, n, topic="사주 상담", fallback=_FALLBACK_SUGGESTIONS)


def _stream_ollama(messages: list[dict], model: str | None = None, stop_event=None):
    """Ollama /api/chat 토큰 스트림. 각 줄은 JSON: {message:{content:'...'}, done:bool}.

    yields: str (토큰/조각)
    """
    import json as _json
    s = get_settings()
    payload = {
        "model": model or s.ollama_model,
        "messages": messages,
        "stream": True,
        "keep_alive": _coerce_keep_alive(s.ollama_keep_alive),
        "options": {"temperature": s.ollama_temperature, "num_ctx": s.ollama_num_ctx,
                    "num_predict": s.ollama_num_predict},
    }
    if str(payload["model"]).startswith("qwen3"):
        payload["think"] = False  # Qwen3 thinking 비활성(스트림에서 <think> 누출·빈 content 방지)
    url = f"{s.ollama_url}/api/chat"
    timeout = httpx.Timeout(
        connect=10.0,
        read=max(s.ollama_timeout_sec, 300.0),
        write=30.0,
        pool=10.0,
    )
    # httpx.stream()은 with 진입 시 연결되므로 with 전체를 감싼다.
    try:
        with httpx.stream("POST", url, json=payload, timeout=timeout) as r:
            if r.status_code >= 400:
                raise ServiceUnavailableError(
                    "답변 생성 서비스(LLM)에 일시적으로 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
                )
            for line in r.iter_lines():
                # 클라 이탈 시 호출부가 stop_event 를 set → 즉시 중단(고아 추론·GPU 점유 방지).
                if stop_event is not None and stop_event.is_set():
                    break
                if not line:
                    continue
                try:
                    obj = _json.loads(line)
                except Exception:
                    continue
                msg = obj.get("message") or {}
                chunk = msg.get("content") or ""
                if chunk:
                    yield chunk
                if obj.get("done"):
                    break
    except httpx.RequestError as e:
        raise ServiceUnavailableError(
            "답변 생성 서비스(LLM)에 일시적으로 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
        ) from e


# ============================================================
# 듀얼 LLM 로컬화: exaone(초안) → qwen(보강), Claude는 폴백
# ============================================================
_HANGUL_RE = re.compile(r"[가-힣]")
_HANJA_RE = re.compile(r"[一-鿿]")

# qwen2.5는 중국어권 모델이라 한국어 지시가 약하면 간체/번체로 드리프트할 수 있다.
# 한국어 전용 + 한자는 술어 병기만 허용하도록 강하게 못박는다.
_QWEN_REFINE_SYSTEM = (
    "당신은 한국 명리학(사주팔자) 전문 감수자입니다. "
    "주어진 1차 답변을 사주명식 근거와 참고자료에 비추어 검증·보강하세요.\n"
    "반드시 한국어로만 작성하세요. 중국어(간체/번체) 문장이나 단어를 절대 쓰지 마세요. "
    "한자는 한국어 술어를 병기할 때만 한글(한자) 형식으로 쓰세요. 예: 정관(正官), 비견(比肩).\n"
    "원칙:\n"
    "1. 근거 없는 단정은 수정/완화합니다.\n"
    "2. 사주명식 근거(일간 강약·오행·십성·대운)와 참고자료에 부합하도록 보강합니다.\n"
    "3. 길흉 단정은 피하고 흐름/가능성으로 설명합니다.\n"
    "4. 마크다운(헤더 #/##/###, 굵게 **, 목록 -·*, 번호 1., 표)을 쓰지 말고, 상담가가 말하듯 "
    "자연스러운 줄글 문단으로만 쓰세요. 1차 답변에 마크다운이 있으면 줄글로 풀어 고치세요.\n"
    "5. '자료에 의하면/참고자료에 따르면/제공된 자료에' 같이 자료·출처·문헌을 언급하는 표현은 절대 "
    "쓰지 말고, 수십 년 경력 전문가 본인이 풀이하듯 자신 있게 쓰세요. 1차 답변에 그런 표현이 있으면 제거·교정하세요.\n"
    "6. 명식에 없는 간지·신살·대운을 새로 만들지 말고, 사실은 제공된 근거 그대로만 쓰세요.\n"
    "7. [현재 질문 집중] 반드시 지금의 [사용자 질문] 주제에 답하세요. 1차 답변이나 직전 대화가 다른 "
    "주제(예: 취업·재물)였더라도, 지금 질문이 다른 주제(예: 연애·결혼·이성운)이면 그 주제로 새로 풀이하고 "
    "이전 주제로 흘러가지 마세요.\n"
    "8. [날짜·간지] 특정 연도·날짜의 간지(세운·월운·일진)를 직접 계산·추측하지 말고 '[현재 시점 간지]'에 "
    "제공된 올해 세운만 그대로 인용하세요. 지나간 과거 연도(작년·재작년 등)는 회고하지 말고 올해·앞으로(미래) "
    "중심으로 답하세요. 제공 안 된 연도의 간지·한자(예: 임의의 '○○년 干支')를 지어내지 말고, 간지의 한글과 "
    "한자는 반드시 일치시키세요(예: 계묘=癸卯, 병오=丙午).\n"
    "9. 최종 '완성된 답변 본문'만 한국어로 출력하세요. 머리말·메타설명·코드블록 없이 본문만.\n"
)

# vi 2차 보강 시스템 — ko _QWEN_REFINE_SYSTEM 의 의도(사실검증·근거보강·마크다운금지·본문만)를 vi 로.
_VN_REFINE_SYSTEM = (
    "Bạn là chuyên gia thẩm định Tứ Trụ (Bát Tự). Hãy kiểm chứng và bổ sung bản nháp dựa trên lá số và tư liệu.\n"
    "Chỉ viết bằng tiếng Việt (chữ Quốc ngữ có dấu); thuật ngữ dùng Hán-Việt Latinh (Giáp Tý, Chính quan). "
    "TUYỆT ĐỐI không dùng chữ Hán / tiếng Trung.\n"
    "Nguyên tắc:\n"
    "1. Sửa hoặc làm dịu các khẳng định vô căn cứ.\n"
    "2. Bám sát lá số (nhật can vượng/nhược, ngũ hành, thập thần, đại vận) và tư liệu tham khảo.\n"
    "3. Tránh khẳng định hung cát tuyệt đối; diễn đạt theo khả năng/xu hướng.\n"
    "4. Không dùng markdown; viết thành đoạn văn tự nhiên như đang tư vấn trực tiếp.\n"
    "5. Không nhắc đến 'tài liệu/nguồn'; luận giải bằng giọng chuyên gia.\n"
    "6. Không bịa ra can chi/thần sát/đại vận không có trong lá số.\n"
    "7. Chỉ xuất ra phần trả lời hoàn chỉnh bằng tiếng Việt, không lời dẫn/meta/khối mã.\n"
)


def _qwen_refine_system(locale: str = "ko") -> str:
    return _VN_REFINE_SYSTEM if locale == "vi" else _QWEN_REFINE_SYSTEM


def _looks_korean_clean(text: str) -> bool:
    """LLM 출력이 '깨지지 않은 한국어 본문'인지 판정.

    탈락 조건(= 보강 폐기 후 폴백/초안 유지):
      - 비었거나 공백뿐
      - 치환문자(\\ufffd) 또는 깨진 서로게이트(U+DC80~U+DCFF) 포함
      - 한글이 거의 없음(< 20자)
      - 한자가 한글보다 많음(중국어 드리프트로 간주)
    """
    if not text or not text.strip():
        return False
    if "�" in text:
        return False
    if any(0xDC80 <= ord(c) <= 0xDCFF for c in text):
        return False
    hangul = len(_HANGUL_RE.findall(text))
    hanja = len(_HANJA_RE.findall(text))
    if hangul < 20:
        return False
    if hanja > hangul * 0.5:
        return False
    return True


def _build_refine_block(
    *,
    question: str,
    draft: str,
    saju_summary: str | None,
    evidence: str | None,
    rag_context: str | None,
    dialect_instruction: str | None,
) -> str:
    parts: list[str] = []
    if saju_summary:
        parts.append(saju_summary)
    if evidence:
        parts.append(f"[사주명식 근거]\n{evidence}")
    if rag_context:
        parts.append(f"[참고자료]\n{rag_context}")
    parts.append(f"[사용자 질문]\n{question}")
    parts.append(f"[1차 답변(보강 대상)]\n{draft}")
    if dialect_instruction:
        parts.append(dialect_instruction)
    return "\n\n".join(parts)


def _strip_think(text: str) -> str:
    """Qwen3 등 추론모델의 <think>...</think> 블록 제거(본문만). ko 모델은 미출력이라 no-op."""
    if not text or "<think>" not in text:
        return text
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _refine_with_qwen(
    *,
    question: str,
    draft: str,
    saju_summary: str | None,
    evidence: str | None,
    rag_context: str | None,
    dialect_instruction: str | None,
    locale: str = "ko",
) -> str | None:
    """2차 보강을 로컬 모델로 수행(ko=qwen2.5 / vi=Qwen3). 로케일 언어가드 통과 시에만 반환.
    vi 는 Qwen3 저온도 반복을 피해 temp↑, <think> 누출 제거, 라틴 전용 가드 적용."""
    s = get_settings()
    if not s.deep_local_refine_enabled:
        return None
    saju_summary = _with_current_luck(saju_summary)   # 보강 단계에도 올해 세운 주입
    block = _build_refine_block(
        question=question, draft=draft, saju_summary=saju_summary,
        evidence=evidence, rag_context=rag_context,
        dialect_instruction=(None if locale == "vi" else dialect_instruction),
    )
    sys_content = _qwen_refine_system(locale)
    if locale == "vi":
        nudge = ("\n\n[Bắt buộc] Viết lại HOÀN TOÀN bằng tiếng Việt (có dấu). "
                 "Không dùng một chữ Hán / tiếng Trung nào.")
        attempts = [
            ([{"role": "system", "content": sys_content}, {"role": "user", "content": block}], 0.6),
            ([{"role": "system", "content": sys_content}, {"role": "user", "content": block + nudge}], 0.4),
        ]
    else:
        # qwen2.5는 한자 많은 컨텍스트에서 간헐적으로 중국어로 드리프트 → 저온도 + 재시도 시 한국어 강제.
        nudge = ("\n\n[필수] 위 작업을 반드시 한국어 문장으로만 다시 작성하세요. "
                 "중국어(간체/번체) 단어·문장을 한 글자도 쓰지 마세요.")
        attempts = [
            ([{"role": "system", "content": sys_content}, {"role": "user", "content": block}], 0.2),
            ([{"role": "system", "content": sys_content}, {"role": "user", "content": block + nudge}], 0.1),
        ]
    guard = clean_guard(locale)
    model = _refine_model(locale)
    for msgs, temp in attempts:
        try:
            out = _call_ollama(msgs, model=model, temperature=temp)
        except ServiceUnavailableError:
            return None
        out = _strip_think((out or "").strip()).strip()
        if guard(out):
            return out
    # 재시도까지 드리프트/깨짐 → 보강 폐기(초안 유지 또는 Claude 폴백)
    return None


def _deep_refine(
    *,
    question: str,
    draft: str,
    saju_summary: str | None,
    evidence: str | None,
    rag_context: str | None,
    dialect_instruction: str | None,
    locale: str = "ko",
) -> tuple[str | None, str | None]:
    """심화 2차 보강 해석: 로컬 qwen 우선 → 실패/깨짐 시 Claude 폴백.

    반환: (보강본문 | None, 사용엔진 'qwen'|'claude'|None)
    """
    saju_summary = _with_current_luck(saju_summary)   # 보강 단계에도 올해 세운 주입(qwen·Claude 공통)
    out = _refine_with_qwen(
        question=question, draft=draft, saju_summary=saju_summary,
        evidence=evidence, rag_context=rag_context,
        dialect_instruction=dialect_instruction, locale=locale,
    )
    if out:
        return out, "qwen"
    # 로컬 보강 실패 → Claude 폴백(가능 시)
    if external_llm.is_enabled():
        c = external_llm.refine_answer(
            question=question, draft=draft, saju_summary=saju_summary,
            evidence=evidence, rag_context=rag_context,
            dialect_instruction=dialect_instruction, locale=locale,
        )
        if c and c.strip():
            return c.strip(), "claude"
    return None, None


def _claude_boost(
    *, question: str, draft: str, saju_summary: str | None, evidence: str | None,
    rag_context: str | None, dialect_instruction: str | None, locale: str = "ko",
) -> str | None:
    """심화 '외부' 보강 — Claude로 1차 답변(exaone+qwen)을 추가 검증·보강.

    설계: 심화는 [1차 답변] 다음에 Claude를 '연결'(보강)한다. 비활성/실패 시 None
    (직전 답변 유지). 폴백이 아니라 deep 전용 추가 단계.
    locale='vi' 면 외부 보강도 베트남어(ko 는 기존 한국어 그대로).
    """
    if not external_llm.is_enabled():
        return None
    saju_summary = _with_current_luck(saju_summary)   # 보강 단계에도 올해 세운 주입
    try:
        c = external_llm.refine_answer(
            question=question, draft=draft, saju_summary=saju_summary,
            evidence=evidence, rag_context=rag_context, dialect_instruction=dialect_instruction,
            locale=locale,
        )
    except Exception:  # noqa: BLE001
        return None
    return c.strip() if c and c.strip() else None


def _bg_with_heartbeat(s, fn):
    """fn()을 백그라운드 스레드로 실행하며 SSE 하트비트(ping)를 yield, 완료 시 ('result', value) 1회.

    스트리밍 보강(qwen/Claude)이 길어질 때 무음 구간(프록시 524)을 막는다.
    """
    import queue as _q
    q: "_q.Queue[Any]" = _q.Queue()

    def _w() -> None:
        try:
            q.put(fn())
        except Exception:  # noqa: BLE001
            q.put(None)

    threading.Thread(target=_w, daemon=True).start()
    while True:
        try:
            val = q.get(timeout=s.sse_heartbeat_sec)
            yield ("result", val)
            return
        except _q.Empty:
            yield ("ping", {})


def _decide_billing(
    db: Session, user: User | None, depth: str, *, allow_free_quota: bool = True,
    defer_to_reveal: bool = False, claim: bool = False,
) -> dict[str, Any]:
    """과금/무료한도 판정(계획 4.2). 부족 시 ValueError('quota_exceeded:...').

    반환 키: billing_mode, is_preview, credits_to_charge, use_free_quota, use_daily_free,
            cost, free_quota_count, free_used_count, free_remaining, depth.

    allow_free_quota=False: 일반회원 무료한도(무료 N회)를 적용하지 않고 바로 크레딧 차감.
    프리미엄 5개 메뉴(궁합/택일/작명/개명/아호) 추가질문에 사용 — 입장료를 낸 메뉴이므로
    추가질문도 항상 1,000/3,000P 차감(무료 누수 차단). 관리자·멤버십 무과금은 그대로 유지.

    claim=True: 무료/멤버십 슬롯을 '결정 시점'에 원자적으로 선점(차감)한다. 실제 답변을 생성하는
    경로(post_message·스트림·툴/궁합 추가질문)에서만 True. 동시요청이 같은 used 를 읽어 모두
    무료가 되는 lost-update(무료 N회 치팅)를 차단. 검증 전용(사전 quota 체크)은 claim=False(읽기만).
    claim=True 시 호출부는 별도 카운터 증가를 하지 않는다(여기서 이미 선점)."""
    from datetime import datetime as _dt

    depth = "deep" if depth == "deep" else "basic"
    cost = settings_service.get_int(
        db, "credit_cost_deep" if depth == "deep" else "credit_cost_basic"
    )
    free_quota = settings_service.get_int(db, "free_quota_count")
    reset = settings_service.get(db, "free_quota_reset", "none")

    info: dict[str, Any] = {
        "billing_mode": "anonymous_preview",
        "is_preview": True,
        "credits_to_charge": 0,
        "use_free_quota": False,
        "use_daily_free": False,
        "use_membership": False,
        "reveal_cost": 0,  # 전체보기 시 이연 차감액(0=폴백 preview_reveal_cost)
        "cost": cost,
        "free_quota_count": free_quota,
        "free_used_count": (user.free_used_count or 0) if user else 0,
        "free_remaining": 0,
        "depth": depth,
    }

    if user is None:
        return info  # 비로그인 → 미리보기(전체보기는 로그인 후 폴백 차감)

    level = auth_service.effective_level(user)

    # 관리자(Level 0/1): 전체 무과금
    if level <= 1:
        info.update(billing_mode="admin_full", is_preview=False)
        info["free_remaining"] = free_quota
        return info

    # 연간/멤버십(Level 2) 유효 기간 내: 연 1,000회 한도까지 무과금, 소진 시 차단(갱신 유도)
    if level == 2 and user.membership_expires_at and user.membership_expires_at > _dt.utcnow():
        quota = get_settings().membership_annual_quota
        used_m = user.membership_used_count or 0
        if claim:
            # 원자적 선점 — 동시요청으로 한도를 넘겨 무과금되는 것을 차단.
            if not auth_service.claim_membership_quota(db, user, quota):
                raise ValueError(f"membership_quota_exhausted: used={used_m}, quota={quota}")
        elif used_m >= quota:
            raise ValueError(f"membership_quota_exhausted: used={used_m}, quota={quota}")
        info.update(billing_mode="membership_full", is_preview=False, use_membership=True)
        info["free_remaining"] = max(0, quota - (used_m + (1 if claim else 0)))
        return info

    # 일반회원/그 외 로그인 회원: 무료 한도 → 소진 시 크레딧 차감
    used = user.free_used_count or 0
    from datetime import date as _d
    today = _d.today()
    # claim=True 이고 무료한도 적용 대상일 때만 '원자적 선점'을 시도(여기서 선점하면 호출부는 미증가).
    # allow_free_quota=False(프리미엄 추가질문 등)면 선점하지 않고 곧장 유료로 떨어진다.
    if reset == "daily":
        if claim and allow_free_quota:
            free_available = auth_service.claim_daily_free(db, user, today)
        else:
            free_available = user.daily_free_used_at != today
        remaining = 0 if (claim and free_available) else (1 if free_available else 0)
    else:
        if claim and allow_free_quota:
            free_available = auth_service.claim_free_quota(db, user, free_quota)
        else:
            free_available = used < free_quota
        remaining = max(0, free_quota - (used + (1 if (claim and free_available) else 0)))

    if allow_free_quota and free_available:
        info.update(
            billing_mode="free_quota",
            is_preview=False,
            use_free_quota=(reset != "daily"),
            use_daily_free=(reset == "daily"),
        )
        info["free_remaining"] = remaining
        return info

    # 무료 소진(또는 프리미엄=무료한도 미적용) → 크레딧 차감 시도
    balance = auth_service.get_balance(db, user.id)
    if balance < cost:
        raise ValueError(f"quota_exceeded: balance={balance}, required={cost}")
    if defer_to_reveal:
        # 회원도 '맛보기 → 전체보기' : 생성은 풀품질, 차감은 전체보기(reveal) 시 질문단가로 이연.
        info.update(billing_mode="paid_preview", is_preview=True, credits_to_charge=0, reveal_cost=cost)
    else:
        info.update(billing_mode="paid_full", is_preview=False, credits_to_charge=cost)
    info["free_remaining"] = 0
    return info


def _decide_entry_billing(
    db: Session, user: User | None, menu: str, *, claim: bool = False
) -> dict[str, Any]:
    """프리미엄 5개 메뉴(궁합/택일/작명/개명/아호) 입장료 판정 — 생성=입장 시 1회 차감.

    - 입장료 = 설정 entry_cost_{menu} × (1 - premium_entry_discount_pct/100). 메뉴별 관리자 설정.
    - 무료한도 미적용(재미성 차단 목적): 일반회원은 항상 입장료 차감.
    - 관리자도 일반회원과 동일하게 입장료 차감(운영자 요청 2026-07 — 표시·차감 일원화로 오류 방지).
      멤버십(Level 2, 유효+쿼터내)=무과금(연결제 혜택), 비로그인=미리보기(잠금).
    - 잔액 부족 시 ValueError('quota_exceeded:...') → API 402(결제 유도).
    - 반환 키는 _decide_billing 과 동일 구조(=_persist_and_bill / compat create 재사용).

    claim=True: 멤버십 슬롯을 원자적으로 선점(생성 경로만). 호출부는 별도 카운터 증가를 하지 않는다.
    """
    from datetime import datetime as _dt

    base = settings_service.get_int(db, f"entry_cost_{menu}", 10000)
    disc = max(0, min(100, settings_service.get_int(db, "premium_entry_discount_pct", 0)))
    cost = max(0, round(base * (100 - disc) / 100))

    info: dict[str, Any] = {
        "billing_mode": "anonymous_preview",
        "is_preview": True,
        "credits_to_charge": 0,
        "use_free_quota": False,
        "use_daily_free": False,
        "use_membership": False,
        "cost": cost,
        "free_quota_count": 0,
        "free_used_count": 0,
        "free_remaining": 0,
        "depth": "entry",
        "menu": menu,
        "entry_cost_base": base,
        "entry_discount_pct": disc,
    }

    if user is None:
        return info  # 비로그인 → 미리보기(잠금) · 결제는 로그인 후

    level = auth_service.effective_level(user)

    # 관리자도 일반회원과 동일하게 입장료를 차감한다(운영자 요청) — 표시(0P)와 실제 차감의
    # 불일치로 인한 오류·혼란 방지. 예전엔 Level 0/1 무과금이었으나 제거함. (멤버십은 아래에서 면제)

    # 멤버십(Level 2) 유효+쿼터내: 무과금(연결제 혜택 — 입장료 면제)
    if level == 2 and user.membership_expires_at and user.membership_expires_at > _dt.utcnow():
        quota = get_settings().membership_annual_quota
        used_m = user.membership_used_count or 0
        if claim:
            if not auth_service.claim_membership_quota(db, user, quota):
                raise ValueError(f"membership_quota_exhausted: used={used_m}, quota={quota}")
        elif used_m >= quota:
            raise ValueError(f"membership_quota_exhausted: used={used_m}, quota={quota}")
        info.update(billing_mode="membership_full", is_preview=False, use_membership=True)
        info["free_remaining"] = max(0, quota - (used_m + (1 if claim else 0)))
        return info

    # 일반회원: 무료한도 없이 입장료 차감
    if cost > 0:
        balance = auth_service.get_balance(db, user.id)
        if balance < cost:
            raise ValueError(f"quota_exceeded: balance={balance}, required={cost}")
    info.update(billing_mode="paid_entry", is_preview=False, credits_to_charge=cost)
    return info


def post_message(
    db: Session,
    session_id: str,
    message: str,
    top_k: int | None,
    user: User | None = None,
    depth: str = "basic",
    explain_level: str = "normal",
) -> dict[str, Any]:
    """질문 처리 + 빌링.

    Returns dict with keys:
      answer (사용자에게 보여줄 텍스트 — 미리보기면 컷됨),
      full_text, sources, assistant_message_id,
      is_preview, preview_revealed, full_length, preview_length,
      credits_charged, balance_after, billing_mode
    """
    row = chat_repo.get_session(db, session_id)
    if row is None:
        raise KeyError(session_id)
    # 세션 소유권 검증 (소유자가 있는 세션은 해당 회원만 접근)
    if row.user_id is not None:
        if user is None or user.id != row.user_id:
            raise PermissionError("not your session")

    s = get_settings()

    # ---- 빌링/무료한도 판정 (계획 4.2, stream과 동일) ----
    depth = "deep" if depth == "deep" else "basic"
    bill = _decide_billing(db, user, depth, defer_to_reveal=True, claim=True)  # 회원 과금=전체보기 시 이연; 무료/멤버십 슬롯 원자 선점
    billing_mode = bill["billing_mode"]
    credits_to_charge = bill["credits_to_charge"]
    use_daily_free = bill["use_daily_free"]
    use_free_quota = bill["use_free_quota"]
    use_membership = bill["use_membership"]

    # ---- 참고자료 검색(RAG) — 기본·심화 모두 색인(학습) 자료 활용. 기본은 장애 시 degrade ----
    k = max(1, min(top_k or row.top_k, s.rag_max_top_k))
    # 명식(지지)을 검색 쿼리에서 제외 — 비슷한 구조의 예시 명식(명리교재) 유입·오염 방지.
    # 본인 명식은 프롬프트의 [사주명식]에 그대로 포함되므로 검색은 '질문' 의미로만 수행.
    query = message
    chunks = _retrieve_context(query, k, depth, session_id=session_id, question=message)

    sys_prompt = template_service.get_active_prompt(db)
    dialect = (getattr(user, "answer_dialect", None) or "standard") if user else "standard"
    locale = getattr(row, "locale", "ko")
    sys_content = _compose_sys_content(sys_prompt, dialect, explain_level, locale)
    msgs: list[dict] = [{"role": "system", "content": sys_content}]
    msgs.extend(_history_msgs(row))   # 최근 6턴(이전 답변 발췌) — 잘림·반복 완화
    user_prompt = _build_user_prompt(message, chunks, row.saju_summary,
                                     chart_json=getattr(row, "chart_json", None),
                                     is_male=(getattr(row, "gender", "male") != "female"))
    msgs.append({"role": "user", "content": user_prompt})
    di = _dialect_instruction(dialect)
    chart_evidence = _build_chart_evidence(getattr(row, "chart_json", None))

    # ---- 1차 생성: exaone(로컬). Ollama 전체 다운 시 Claude 폴백 ----
    local_alive = True
    try:
        answer_full = _call_ollama(msgs, model=_draft_model(locale))
    except ServiceUnavailableError:
        local_alive = False
        evidence_text = "\n".join(f"- {e}" for e in chart_evidence) if chart_evidence else None
        rag_context = "\n\n".join(
            f"[자료{i}] (출처:{c.source}) {c.text}" for i, c in enumerate(chunks, 1)
        ) if chunks else None
        fb = external_llm.generate_answer(
            question=message, saju_summary=row.saju_summary,
            evidence=evidence_text, rag_context=rag_context,
            dialect_instruction=di or None, locale=locale,
        )
        if not fb:
            raise  # 로컬·외부 모두 불가 → 원래 503 전파
        answer_full = fb.strip()

    # 답변 분량 가드: A4 약 70%(≈1,200~1,400자) 미달 시 보강 재시도 (로컬 정상일 때만)
    min_chars = s.answer_min_chars
    retry_max = s.answer_retry_max
    if local_alive:
        for attempt in range(retry_max):
            if len(answer_full) >= min_chars:
                break
            detail_hint = (
                "이야기하듯 쉬운 말로" if explain_level == "easy" else "전문가 본인의 풀이로(자료 인용 표현 없이) 근거와 함께"
            )
            boost = (
                f"\n\n[보강 요청] 이전 답변이 너무 짧습니다({len(answer_full)}자). "
                f"같은 주제를 A4 약 70%(최소 {min_chars}자 이상)가 되도록, "
                f"{detail_hint} 해석·사례·실생활 조언을 단락을 나눠 더 구체적으로 보강해 다시 답하세요."
            )
            boost_msgs = list(msgs) + [
                {"role": "assistant", "content": answer_full},
                {"role": "user", "content": boost},
            ]
            try:
                answer_full = _call_ollama(boost_msgs, model=_draft_model(locale))
            except Exception:
                break

    # ---- 미리보기 컷 여부 ----
    is_preview = bill["is_preview"]

    # ---- 보강 단계: ① 내부 qwen(기본·심화 공통) → ② 외부 Claude(심화 전용) ----
    # 설계: 1차 답변 = RAG + exaone + qwen(보강). 심화는 그 위에 Claude를 추가 연결.
    evidence_text = "\n".join(f"- {e}" for e in chart_evidence) if chart_evidence else None
    rag_context = "\n\n".join(
        f"[자료{i}] (출처:{c.source}) {c.text}" for i, c in enumerate(chunks, 1)
    ) if chunks else None
    # 미리보기도 풀품질로 생성(표시만 컷) — 비로그인/회원 동일 품질로 신뢰 형성. 표시 컷은 visible에서.
    if local_alive and answer_full.strip():
        qb = _refine_with_qwen(
            question=message, draft=answer_full, saju_summary=row.saju_summary,
            evidence=evidence_text, rag_context=rag_context, dialect_instruction=di or None,
            locale=locale,
        )
        if qb:
            answer_full = qb
    # 심화 Claude 보강 — 비로그인 미리보기는 비용 절감 위해 제외(qwen까지만). 회원/전체는 적용.
    if depth == "deep" and user is not None and local_alive and answer_full.strip():
        cb = _claude_boost(
            question=message, draft=answer_full, saju_summary=row.saju_summary,
            evidence=evidence_text, rag_context=rag_context, dialect_instruction=di or None,
            locale=locale,
        )
        if cb:
            answer_full = cb

    # ---- 명식 정합성 검증·교정 (절대규칙: 4주 지지가 명식과 달라지면 깨끗한 컨텍스트로 재생성) ----
    if answer_full.strip():
        answer_full = _correct_chart(
            answer_full, getattr(row, "chart_json", None), question=message,
            sys_content=sys_content, saju_summary=row.saju_summary,
        )
        answer_full = _scrub_source_refs(answer_full)  # 자료 인용 말투 제거(전문가 화법)
        answer_full = _scrub_stale_year_ganji(answer_full)  # 최종 재검증: 과거연도·틀린 세운 간지 중화
        answer_full = fix_term_hanja(answer_full)  # 십성 등 한자 병기 정자(正字) 교정(전문가 지적)

    # ---- 차감/무료 갱신 ----
    balance_after: int | None = None
    if user is not None:
        # 무료/멤버십 카운터는 _decide_billing(claim=True)에서 원자적으로 선점됨 — 여기서 미증가.
        if credits_to_charge > 0:
            balance_after = auth_service.adjust_credit(
                db, user.id, -credits_to_charge,
                reason="question", ref_id=session_id,
            )
        else:
            balance_after = auth_service.get_balance(db, user.id)

    # ---- 메시지 영속 ----
    sources_dto = [
        ChatSourceDTO(
            source=c.source,
            chunk_id=c.chunk_id,
            score=c.score,
            text_preview=(c.text[:180] + "...") if len(c.text) > 180 else c.text,
        )
        for c in chunks
    ]
    now = datetime.utcnow()
    inserted = chat_repo.append_messages(
        db,
        session_id,
        [
            {
                "role": "user", "content": message, "created_at": now,
                "sources_json": [], "preview_revealed": False, "is_preview": False,
                "credits_charged": 0, "reveal_credits_charged": 0,
            },
            {
                "role": "assistant", "content": answer_full,
                "created_at": datetime.utcnow(),
                "sources_json": [src.model_dump() for src in sources_dto],
                "preview_revealed": not is_preview,
                "is_preview": is_preview,
                "credits_charged": credits_to_charge,
                "reveal_credits_charged": 0,
                "reveal_cost": bill.get("reveal_cost", 0),
            },
        ],
    )
    assistant_msg = inserted[-1]

    visible = _make_preview(answer_full) if is_preview else answer_full

    db.commit()
    return {
        "answer": visible,
        "full_text": answer_full,
        "sources": sources_dto if _is_admin(user) else [],  # 근거(영업비밀) 관리자만
        "assistant_message_id": assistant_msg.id,
        "is_preview": is_preview,
        "preview_revealed": not is_preview,
        "full_length": len(assistant_msg.content),  # 저장된 전문 기준(전체보기와 100% 일치)
        "preview_length": len(visible),
        "credits_charged": credits_to_charge,
        "reveal_cost": bill.get("reveal_cost", 0),
        "balance_after": balance_after,
        "billing_mode": billing_mode,
    }


def post_message_stream(
    db: Session,
    session_id: str,
    message: str,
    top_k: int | None,
    user: User | None = None,
    depth: str = "basic",
    explain_level: str = "normal",
):
    """Streaming generator: yields (event_name, data_dict) tuples.

    이벤트:
      meta   — 빌링 모드/세션 정보/무료 잔여. 스트림 시작 시 1회.
      chunk  — 1차 토큰 조각. full 모드는 Ollama 실시간 토큰, preview 모드는 컷된 본문.
      cut    — 미리보기 컷 발생.
      stage  — 듀얼 LLM 단계(draft_done / refining / refine_done).
      refine — 외부 AI 보강 본문 + 근거. FE는 페이드 전환.
      done   — 최종 메타(메시지 id, 잔액, 길이, 근거, 무료 잔여). 1회.
      error  — 예외 발생 시.

    빌링/세션 검증/차감/영속화는 본 함수가 모두 수행.
    """
    row = chat_repo.get_session(db, session_id)
    if row is None:
        raise KeyError(session_id)
    if row.user_id is not None:
        if user is None or user.id != row.user_id:
            raise PermissionError("not your session")

    s = get_settings()

    # ---- 빌링/무료한도 판정 (계획 4.2) ----
    bill = _decide_billing(db, user, depth, defer_to_reveal=True, claim=True)  # 회원 과금=전체보기 시 이연; 무료/멤버십 슬롯 원자 선점
    billing_mode = bill["billing_mode"]
    is_preview = bill["is_preview"]
    credits_to_charge = bill["credits_to_charge"]
    use_daily_free = bill["use_daily_free"]
    use_free_quota = bill["use_free_quota"]
    use_membership = bill["use_membership"]
    depth = bill["depth"]

    # 미리보기 유출 차단: is_preview면 클라로 보내는 모든 본문(chunk·refine)을 컷한다.
    # (전문은 서버에만 저장 → 전체보기 reveal 시에만 제공). 풀품질 생성과 표시 컷을 분리.
    def _disp(text: str) -> str:
        # 표시 전 십성 등 한자 병기 정자 교정(전문가 지적) + 미리보기 컷.
        return fix_term_hanja(_make_preview(text) if is_preview else text)

    # ---- 참고자료 검색(RAG) — 기본·심화 모두 색인(학습) 자료 활용. 기본은 장애 시 degrade ----
    k = max(1, min(top_k or row.top_k, s.rag_max_top_k))
    # 명식(지지)을 검색 쿼리에서 제외 — 비슷한 구조의 예시 명식(명리교재) 유입·오염 방지.
    # 본인 명식은 프롬프트의 [사주명식]에 그대로 포함되므로 검색은 '질문' 의미로만 수행.
    query = message
    chunks = _retrieve_context(query, k, depth, session_id=session_id, question=message)

    sources_dto = [
        ChatSourceDTO(
            source=c.source,
            chunk_id=c.chunk_id,
            score=c.score,
            text_preview=(c.text[:180] + "...") if len(c.text) > 180 else c.text,
        )
        for c in chunks
    ]

    # ---- 동적 시스템 프롬프트(답변양식 L) + 말투(방언 P) ----
    sys_prompt = template_service.get_active_prompt(db)
    dialect = (getattr(user, "answer_dialect", None) or "standard") if user else "standard"
    locale = getattr(row, "locale", "ko")
    sys_content = _compose_sys_content(sys_prompt, dialect, explain_level, locale)

    msgs: list[dict] = [{"role": "system", "content": sys_content}]
    msgs.extend(_history_msgs(row))   # 최근 6턴(이전 답변 발췌) — 잘림·반복 완화
    user_prompt = _build_user_prompt(message, chunks, row.saju_summary,
                                     chart_json=getattr(row, "chart_json", None),
                                     is_male=(getattr(row, "gender", "male") != "female"))
    msgs.append({"role": "user", "content": user_prompt})

    # 사주명식 근거(G)
    chart_evidence = _build_chart_evidence(getattr(row, "chart_json", None))
    # 풀이 근거(사주명식 근거·RAG 자료출처)는 영업비밀 → 관리자에게만 전송(비관리자는 빈 배열)
    _admin = _is_admin(user)
    _evi_client = chart_evidence if _admin else []

    # 보강 단계: ① 내부 qwen(기본·심화 공통) → ② 외부 Claude(심화 전용, qwen 다음)
    di = _dialect_instruction(dialect)
    _claude_avail = (
        settings_service.get_bool(db, "external_llm_enabled", True)
        and external_llm.is_enabled()
    )
    # 미리보기도 풀품질 생성(표시만 컷) — 비로그인/회원 동일 품질로 신뢰 형성·전환 유도.
    do_qwen = s.deep_local_refine_enabled                # 1차 내부 보강(미리보기 포함)
    # 심화 Claude — 비로그인 미리보기는 비용 절감 위해 제외(qwen까지만). 회원/전체는 적용.
    do_claude = depth == "deep" and _claude_avail and (user is not None)
    will_refine = do_qwen or do_claude

    # 시작 메타 (스트림 시작 직후 1회)
    yield ("meta", {
        "billing_mode": billing_mode,
        "is_preview": is_preview,
        "depth": depth,
        "sources": ([s_.model_dump() for s_ in sources_dto] if _admin else []),  # 근거 관리자만
        "free_quota_count": bill["free_quota_count"],
        "free_remaining": bill["free_remaining"],
        "will_refine": will_refine,
    })

    # ---- 1차 생성 (실시간 토큰 스트리밍 + SSE 하트비트 + 미리보기 컷) ----
    import queue as _queue

    answer_full_parts: list[str] = []
    tok_q: "_queue.Queue[Any]" = _queue.Queue()
    _SENTINEL = object()
    _err: dict[str, Exception] = {}
    stop_event = threading.Event()  # 클라 이탈 시 메인 Ollama producer 조기 종료 신호

    def _produce() -> None:
        try:
            for tok in _stream_ollama(msgs, model=_draft_model(locale), stop_event=stop_event):
                tok_q.put(tok)
        except Exception as e:  # noqa: BLE001
            _err["e"] = e
        finally:
            tok_q.put(_SENTINEL)

    producer = threading.Thread(target=_produce, daemon=True)
    producer.start()

    preview_chars = 0
    cut_sent = False
    # 클라가 스트리밍 도중 이탈하면 Starlette 가 이 제너레이터를 close → 현재 yield 에서
    # GeneratorExit 발생 → finally 가 stop_event 를 set 해 _stream_ollama 가 즉시 break(고아 추론 차단).
    try:
        while True:
            try:
                item = tok_q.get(timeout=s.sse_heartbeat_sec)
            except _queue.Empty:
                yield ("ping", {})
                continue
            if item is _SENTINEL:
                break
            tok = item
            answer_full_parts.append(tok)
            if is_preview:
                if not cut_sent:
                    _pmax = settings_service.get_cached_int("preview_max_chars", s.preview_max_chars)
                    remaining = _pmax - preview_chars
                    if remaining > 0:
                        send = tok[:remaining]
                        preview_chars += len(send)
                        if send:
                            yield ("chunk", {"text": send})
                    if preview_chars >= _pmax:
                        cut_sent = True
                        yield ("cut", {"reason": "preview_limit"})
            else:
                yield ("chunk", {"text": tok})
    finally:
        stop_event.set()

    if "e" in _err:
        e = _err["e"]
        # 로컬 Ollama(exaone) 다운 → Claude 폴백으로 본문 생성 시도
        rag_context_fb = "\n\n".join(
            f"[자료{i}] (출처:{c.source}) {c.text}" for i, c in enumerate(chunks, 1)
        ) if chunks else None
        evidence_fb = "\n".join(f"- {ev}" for ev in chart_evidence) if chart_evidence else None
        fb = None
        try:
            fb = external_llm.generate_answer(
                question=message, saju_summary=row.saju_summary,
                evidence=evidence_fb, rag_context=rag_context_fb,
                dialect_instruction=di or None, locale=locale,
            )
        except Exception:  # noqa: BLE001
            fb = None
        if fb and fb.strip():
            answer_full_parts = [fb.strip()]
            yield ("refine", {
                "text": _disp(fb.strip()),
                "reason": "로컬 엔진 불가 — 외부 AI 폴백",
                "evidence": _evi_client,
            })
        elif isinstance(e, ServiceUnavailableError):
            # 로컬·외부 모두 불가 — 친절 메시지 + 코드(클라가 503처럼 처리)
            yield ("error", {"detail": str(e), "code": "service_unavailable"})
            return
        else:
            yield ("error", {"detail": f"ollama stream error: {type(e).__name__}: {e}"})
            return

    answer_full = "".join(answer_full_parts)
    refined = False
    _local_draft_ok = "e" not in _err

    rag_context = "\n\n".join(
        f"[자료{i}] (출처:{c.source}) {c.text}" for i, c in enumerate(chunks, 1)
    ) if chunks else None
    evidence_text = "\n".join(f"- {e}" for e in chart_evidence) if chart_evidence else None

    # ---- ① 내부 qwen 보강 (기본·심화 공통) — 1차 답변 = exaone 초안 + qwen 보강 ----
    if do_qwen and _local_draft_ok and answer_full.strip():
        yield ("stage", {"phase": "draft_done"})
        yield ("stage", {"phase": "refining"})
        qb = None
        for ev in _bg_with_heartbeat(s, lambda af=answer_full: _refine_with_qwen(
                question=message, draft=af, saju_summary=row.saju_summary,
                evidence=evidence_text, rag_context=rag_context, dialect_instruction=di or None,
                locale=locale)):
            if ev[0] == "result":
                qb = ev[1]
            else:
                yield ev
        if qb:
            answer_full = qb.strip()
            refined = True
            yield ("refine", {"text": _disp(answer_full), "reason": "내부 보강(qwen)", "evidence": _evi_client})
        yield ("stage", {"phase": "refine_done"})

    # ---- ② 외부 Claude 보강 (심화 전용, qwen 다음) ----
    if do_claude and _local_draft_ok and answer_full.strip():
        yield ("stage", {"phase": "refining"})
        cb = None
        for ev in _bg_with_heartbeat(s, lambda af=answer_full: _claude_boost(
                question=message, draft=af, saju_summary=row.saju_summary,
                evidence=evidence_text, rag_context=rag_context, dialect_instruction=di or None,
                locale=locale)):
            if ev[0] == "result":
                cb = ev[1]
            else:
                yield ev
        if cb:
            answer_full = cb.strip()
            refined = True
            yield ("refine", {"text": _disp(answer_full), "reason": "심화 검증·보강(Claude)", "evidence": _evi_client})
        yield ("stage", {"phase": "refine_done"})

    # ---- 명식 정합성 검증·교정 (미리보기 포함 — 표시 컷과 무관하게 정확도 보장) ----
    if answer_full.strip():
        _chart_json_sm = getattr(row, "chart_json", None)
        if _verify_myeongsik(answer_full, _chart_json_sm):
            yield ("stage", {"phase": "verifying"})
            _fixed = None
            for ev in _bg_with_heartbeat(s, lambda af=answer_full: _correct_chart(
                    af, _chart_json_sm, question=message, sys_content=sys_content,
                    saju_summary=row.saju_summary)):
                if ev[0] == "result":
                    _fixed = ev[1]
                else:
                    yield ev
            if _fixed and _fixed.strip() and _fixed.strip() != answer_full:
                answer_full = _fixed.strip()
                refined = True
                yield ("refine", {"text": _disp(answer_full), "reason": "명식 정합성 자동 교정", "evidence": _evi_client})
        # 자료 인용 말투 제거(전문가 화법) — 바뀌면 교체본 전송
        _scrubbed = _scrub_source_refs(answer_full)
        if _scrubbed and _scrubbed != answer_full:
            answer_full = _scrubbed
            refined = True
            yield ("refine", {"text": _disp(answer_full), "reason": "표현 정리", "evidence": _evi_client})
        # 최종 재검증: 과거연도·틀린 세운 간지 중화(스트리밍이라 바뀌면 교체본 전송)
        _ts = _scrub_stale_year_ganji(answer_full)
        if _ts and _ts != answer_full:
            answer_full = _ts
            refined = True
            yield ("refine", {"text": _disp(answer_full), "reason": "시점 표현 정리", "evidence": _evi_client})

    # 십성 등 한자 병기 정자(正字) 교정(전문가 지적) — 저장/재로드본까지 일관. 표시는 _disp 가 이미 교정.
    answer_full = fix_term_hanja(answer_full)

    # ---- 차감/무료 갱신 ----
    balance_after: int | None = None
    if user is not None:
        # 무료/멤버십 카운터는 _decide_billing(claim=True)에서 원자적으로 선점됨 — 여기서 미증가.
        if credits_to_charge > 0:
            balance_after = auth_service.adjust_credit(
                db, user.id, -credits_to_charge,
                reason="question", ref_id=session_id,
            )
        else:
            balance_after = auth_service.get_balance(db, user.id)

    # ---- 메시지 영속 ----
    now = datetime.utcnow()
    inserted = chat_repo.append_messages(
        db,
        session_id,
        [
            {
                "role": "user", "content": message, "created_at": now,
                "sources_json": [], "preview_revealed": False, "is_preview": False,
                "credits_charged": 0, "reveal_credits_charged": 0,
            },
            {
                "role": "assistant", "content": answer_full,
                "created_at": datetime.utcnow(),
                "sources_json": [src.model_dump() for src in sources_dto],
                "preview_revealed": not is_preview,
                "is_preview": is_preview,
                "credits_charged": credits_to_charge,
                "reveal_credits_charged": 0,
                "reveal_cost": bill.get("reveal_cost", 0),
            },
        ],
    )
    assistant_msg = inserted[-1]
    db.commit()

    # 무료 잔여(claim=True 선점이 _decide_billing 에서 이미 반영됨 — 추가 차감 금지)
    free_remaining_after = bill["free_remaining"]

    visible_len = len(_make_preview(answer_full)) if is_preview else len(answer_full)
    yield ("done", {
        "assistant_message_id": assistant_msg.id,
        "is_preview": is_preview,
        "preview_revealed": not is_preview,
        "full_length": len(assistant_msg.content),  # 저장된 전문 기준(전체보기와 일치)
        "full_length": len(answer_full),
        "preview_length": visible_len,
        "credits_charged": credits_to_charge,
        "reveal_cost": bill.get("reveal_cost", 0),
        "balance_after": balance_after,
        "billing_mode": billing_mode,
        "refined": refined,
        "evidence": _evi_client,
        "free_remaining": free_remaining_after,
        "flash": not is_preview,
    })


def reveal_message(
    db: Session,
    session_id: str,
    message_id: int,
    user: User | None,
) -> dict[str, Any]:
    """미리보기 메시지 전체 노출. 회원만 가능, 500P 차감."""
    if user is None:
        raise PermissionError("login required to reveal preview")

    row = chat_repo.get_session(db, session_id)
    if row is None:
        raise KeyError(session_id)
    if row.user_id is not None and row.user_id != user.id:
        raise PermissionError("not your session")

    # 이중차감 방지: 메시지 행을 FOR UPDATE 로 잠가 동시 전체보기의 check-then-charge 를 직렬화.
    # 두 번째 요청은 첫 커밋 후 preview_revealed=True 를 관측해 무료 반환(차감 1회만).
    from sqlalchemy import select as _sel_msg
    from backend.app.repositories.models import ChatMessage as _ChatMessage
    msg = db.execute(
        _sel_msg(_ChatMessage).where(_ChatMessage.id == message_id).with_for_update()
    ).scalar_one_or_none()
    if msg is None or msg.session_id != session_id:
        raise KeyError(f"message {message_id}")
    if msg.role != "assistant":
        raise ValueError("not an assistant message")
    if msg.preview_revealed:
        # 이미 공개됨 — 무료 반환
        bal = auth_service.get_balance(db, user.id)
        return {
            "content": msg.content,
            "preview_revealed": True,
            "credits_charged": 0,
            "balance_after": bal,
        }

    s = get_settings()
    # 이연 차감액(회원 paid_preview=질문단가). 없으면 폴백(비로그인 유래 미리보기=preview_reveal_cost).
    deferred = int(getattr(msg, "reveal_cost", 0) or 0)
    cost = deferred if deferred > 0 else s.preview_reveal_cost

    # admin 면제
    if user.role == "admin":
        cost = 0

    balance_after = auth_service.get_balance(db, user.id)
    if cost > 0:
        if balance_after < cost:
            # 잔액 부족 → 충전 유도(엔드포인트가 402로 매핑 → 프론트 충전 모달)
            raise ValueError(f"quota_exceeded: balance={balance_after}, required={cost}")
        balance_after = auth_service.adjust_credit(
            db, user.id, -cost,
            reason="preview_reveal", ref_id=f"{session_id}:{message_id}",
        )
    msg.preview_revealed = True
    msg.reveal_credits_charged = cost
    db.commit()
    return {
        "content": msg.content,
        "preview_revealed": True,
        "credits_charged": cost,
        "balance_after": balance_after,
    }
