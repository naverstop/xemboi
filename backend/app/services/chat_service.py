"""채팅 서비스: 사주 컨텍스트 + RAG + Ollama. 세션은 Postgres에 영속.

각 함수는 외부에서 SQLAlchemy Session 을 주입받는다 (FastAPI Depends 통해).
"""
from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from functools import lru_cache
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
from backend.app.saju.types import BirthInput, CalendarType, SajuChart
# 팔자8(천간+지지본기) 오행 개수 — 화면 명식표와 같은 기준. 옛 chart_json 도 pillars 로 자동 재계산.
from backend.app.saju.wuxing import wuxing_eight_of as _wuxing_eight_of
from backend.app.saju.wuxing import wuxing_eight_ko_from_json as _wuxing_eight_ko_from_json
from backend.app.services import auth_service
from backend.app.services import settings_service, template_service, external_llm
from ml.inference.retriever import RetrievedChunk, SajuRetriever


SYSTEM_PROMPT = """당신은 수십 년 경력의 대한민국 최고 사주명리 전문가이자 상담가입니다.

원칙:
1. 당신의 전문 지식으로 근거 있는 풀이만 하되, 명식에 없는 사실(간지·신살·대운 등)은 절대 지어내지 마세요.
2. 자료·출처·문헌을 언급하지 말고("자료에 의하면" 등 금지), 전문가 본인의 풀이로 직접 자신 있게 설명하세요.
3. 한국어로 답변하세요. 한자 병기는 답변 전체에서 핵심 용어 2~3개까지만 허용됩니다 — 그 외에는 모두 한글로만 쓰세요(무·토·정관·식신처럼). 괄호 한자가 많을수록 답변이 어려워 보인다는 점을 기억하세요.
4. 길흉 단정은 피하고, 가능성과 흐름으로 설명하세요.
5. 응답은 풍부하게 — 최소 1,500자(대략 1,800~2,500자, 15~24문장) 분량으로, 큰 주제마다 단락을 나눠 근거→해석→조언 흐름으로 구체적으로 설명하세요. 항목만 나열하고 내용이 빈약해지지 않게 하세요. 근거로는 그 주제와 가장 관련 깊은 간지·십성 1~2가지만 짚고, 용어를 쓴 뒤에는 곧바로 그것이 생활에서 뜻하는 바를 쉬운 말로 이어서 풀어 주세요. 풍부함은 용어의 개수가 아니라 생활 밀착형 해석과 조언의 깊이로 만드세요.
6. 첫 문장은 '~살펴보겠습니다/풀어드리겠습니다' 같은 인사말·예고가 아니라, 이 사주(또는 고민)의 핵심을 규정하는 '한 줄 판정'으로 시작하세요(특징+시사점 압축). 초안에 상담자 호칭(○○님)이 있으면 그대로 유지하세요.
"""


# ---- 상담체(말투/형식) 통일 규칙 — 전 메뉴(사주·궁합·택일·작명) 공통, 항상 적용 ----
# [2026-07-21 운영자 지시로 반전] 기존 '마크다운 전면 금지'(줄글만) → '구조·강조 적극 사용'.
# 근거: 프런트 renderRich()(lib/format.ts)가 **굵게**/### 헤더/불릿을 화면에 정식 렌더하고
# stripMarkdown()이 PDF·복사본을 평문화하므로 기호 노출 우려가 없다. qwen3 전환 후 모델이
# 금지 지시를 충실히 따르면서 답변이 밋밋해져(구조·강조 실종) 운영자가 서식 복원을 지시함.
# 단 표(마크다운 표)는 renderRich 미지원이라 계속 금지.
CONSULTANT_STYLE_RULE = (
    "[작성 형식 — 필수] 답변은 구조적으로, 서식을 적극 활용해 작성하세요. "
    "큰 주제마다 '### 소제목' 줄을 두고, 핵심 간지·십성·시기·결론 단어는 **굵게** 강조하며, "
    "나열이 자연스러운 곳은 '- ' 불릿을 사용하세요. 각 소제목 아래에는 상담가가 마주 앉아 "
    "이야기하듯 충분한 문장(3문장 이상)으로 근거→해석→조언을 풀어 쓰세요. "
    "소제목만 나열하고 내용이 빈약해지면 안 됩니다. 표(마크다운 표)와 구분선('---')은 사용하지 "
    "마세요 — 화면에 기호가 그대로 노출됩니다. 섹션 구분은 '### 소제목'만으로 하세요. "
    # [실측 2026-07-28] 월별 흐름을 12월까지 나열하고 마지막 달에서 뚝 끊겨 마무리가 없었다.
    "[마무리 — 필수] 월별·항목 나열로 끝내지 말고, 반드시 맨 끝에 '### 마무리' 소제목으로 전체를 "
    "한 문단(3문장 이상)으로 갈무리하세요 — 올해의 큰 흐름 요약 + 가장 중요한 조언 1~2가지로 따뜻하게 "
    "맺습니다. 마지막 달 서술만 하고 답변을 끝내면 안 됩니다."
)

# 집중(특정주제)·비종합 후속 답변은 '짧고 정조준'이 원칙 → CONSULTANT_STYLE_RULE 의 '소제목 3문장 이상·
# ### 마무리 필수'(전체 풀이용)와 충돌한다(전수감사 #8: 약모델이 '간결'과 '3문장·마무리' 충돌에서 구조를
# 먼저 버려 평문 한 덩어리가 됨). 짧은 답에선 그 강제를 풀어 충돌 자체를 없앤다(과잉확장·억지 마무리 방지).
_STYLE_RELAX_CONCISE = (
    "[서식 완화 — 짧고 집중된 답] 이 답변은 짧고 정조준된 답입니다. 위 [작성 형식]·[마무리]의 '각 소제목 "
    "3문장 이상'·'### 마무리 소제목 필수'는 전체 풀이용이니 여기선 적용하지 마세요. 대신 결론 낱말은 "
    "**굵게**, 근거·항목이 두 갈래 이상이면 '### 소제목' 1~2개 또는 '- ' 불릿으로 나누고, 답이 짧으면 "
    "소제목·마무리 없이 결론을 **굵게** + 근거 불릿만으로 마쳐도 됩니다(분량을 억지로 늘리거나 마무리 문단을 "
    "새로 지어내지 마세요)."
)

# [2026-07-31] 집중·후속 전용 서식 — '짧게'가 아니라 '밀도형'. 위 [마무리 — 필수]의 강제 요약 섹션만 빼서
#   약모델이 결론에 도입을 복붙하는 패딩 벡터를 없앤다(패딩 검수: 결론=도입 ~600자 복붙 실측). 분량은
#   본문에서 '새 내용'으로 채우고, 요약 재진술로 늘리지 않는다.
_NARROW_STYLE_RULE = (
    "[집중답변 서식 — 밀도형] 이 답변은 한 주제에 정조준한 집중 답변입니다. 위 [마무리 — 필수]의 강제 "
    "'### 마무리' 요약 소제목은 만들지 마세요(그 요약 섹션은 '전체 풀이'용). 끝맺음이 필요하면 앞 내용을 "
    "복붙·요약하지 말고 앞에서 안 한 '새 실행 포인트' 한두 줄로만 맺으세요. 대신 물어본 주제를 여러 각도"
    "(서로 다른 근거·구체 사례·시기·실행 단계)로 충분히·밀도 있게 풀어 주세요 — 분량은 같은 말 부연이 "
    "아니라 새 내용으로만 채웁니다."
)


# ---- 전문가 화법 — '자료 중계'가 아니라 본인이 최고 전문가로서 직접 상담하듯 ----
# 실측: 답변에 "자료에 의하면/참고자료에 따르면" 류가 노출되어 시스템이 자료를 중계하는 것처럼 보임.
# 참고자료는 전문가의 '지식'일 뿐, 출처를 언급하지 말고 본인 풀이로 단언하게 한다.
# [P3-E1] '자료를 따르라'는 **자료가 실제로 있을 때만** 말해야 한다. 0건이면 [참고자료] 블록이
# 통째로 사라지는데(rag_context_block([]) → None) 이 문구는 무조건 붙어 있었다 — 존재하지 않는
# 자료를 따르라는 유령 지시라, 모델이 근거를 지어낼 여지를 만든다(꿈해몽 실측 가짜 문헌 인용 2건).
# → 화법 규칙(출처 언급 금지)은 항상, 자료 우선 문장은 chunks 가 있을 때만.
_EXPERT_VOICE_HEAD = (
    "[전문가 화법 — 최우선] 당신은 수십 년 경력의 대한민국 최고 사주명리 전문가이자 상담가입니다. ")
_EXPERT_VOICE_WITH_SRC = (
    "참고자료는 감수를 거친 선생님 자료입니다 — 해석·관법은 자료를 우선 따르되, 답변은 자료를 "
    "인용하는 말투가 아니라 전문가 본인의 풀이로 직접 말하세요. ")
_EXPERT_VOICE_NO_SRC = (
    "이번 답변에는 참고자료가 없습니다 — 위 [사주명식]의 계산값과 명리 원리만으로 풀이하고, "
    "책·문헌·자료 이름을 지어내 인용하지 마세요. ")
_EXPERT_VOICE_TAIL = (
    "'자료에 의하면', '참고자료에 따르면', '분석 자료에서', '제공된 자료에', "
    "'자료에는/자료에 없', '문헌에 따르면', '~라고 나와 있습니다' 같이 자료·출처·문헌을 언급하는 표현을 "
    "절대 쓰지 마세요. 내담자를 마주한 상담가가 자신의 통찰로 풀어 주듯 자연스럽고 자신 있게 이야기하세요.")


def expert_voice_rule(has_sources: bool = True) -> str:
    """전문가 화법 규칙. has_sources=False면 '자료 우선' 대신 '자료 없음'을 명시한다."""
    mid = _EXPERT_VOICE_WITH_SRC if has_sources else _EXPERT_VOICE_NO_SRC
    return _EXPERT_VOICE_HEAD + mid + _EXPERT_VOICE_TAIL


EXPERT_VOICE_RULE = expert_voice_rule(True)   # 하위호환(기존 참조·테스트)


# [교차검증 2026-07-22] P3-E1 을 chat 시스템프롬프트에만 넣고 **보강·폴백 경로에는 안 넣었다**.
# _QWEN_REFINE_SYSTEM 과 external_llm 의 두 프롬프트는 '참고자료에 비추어 검증하라'를 조건 없이
# 말한다 — 0건이면 없는 자료를 근거로 삼으라는 유령 지시가 되어 모델이 문헌명을 지어낸다.
# 이 문구를 자료가 없을 때만 덧붙여 층을 맞춘다(chat 쪽 expert_voice_rule 과 같은 취지).
NO_SOURCES_NOTE = (
    "\n[참고자료 없음] 이번 요청에는 [참고자료]가 주어지지 않았습니다. 위 사주명식의 계산값과 "
    "명리 원리만으로 검증·보강하고, 참고자료가 있는 것처럼 말하거나 책·문헌 이름을 지어내지 마세요."
)


def refine_system_for(base: str, rag_context: str | None) -> str:
    """보강·폴백 시스템 프롬프트 — 자료가 없으면 '자료 없음'을 명시해 유령 지시를 없앤다."""
    return base if rag_context else (base + NO_SOURCES_NOTE)

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

# ---- 어려운 관계용어(합충류) 절제 + 궁(자리) 라벨 정합 — 항상 적용 ----
# 실측(2026-07-21, 운영자 지적): "월지 미(未)와 년지 묘(卯)가 반합" 류 어려운 나열의 출처는
# b54dbda4(2026-07-16)의 [월별 간지·십성·관계] 주입 표 — 구 exaone(지시 소화력 낮음)은 표를 뭉개고
# 지나갔지만 qwen3는 표기를 충실히 옮겨 적어 표면화됨. 주입 표 지시문(months_line)에 '그대로
# 옮겨 적기 금지'를 추가했고, 본 규칙은 그 외 모델 자체 합충 언급까지 포괄하는 일반 절제 규칙.
EASY_TERMS_RULE = (
    "[쉬운 설명·용어 절제 — 필수] 반합·삼합·육합·원진·형·충·파·해 같은 지지 관계 용어는 "
    "이 사주에서 실제로 의미가 큰 것 1~2개만 골라 쓰고, 쓸 때는 반드시 바로 뒤에 일상어로 "
    "뜻과 영향을 풀어 주세요(예: '묘미 반합 — 목 기운이 한층 강해져 추진력이 붙는 흐름입니다'). "
    "여러 관계를 나열식으로 줄줄이 언급하지 마세요. "
    "지지의 자리 이름(년지·월지·일지·시지)은 [사주명식] 표와 정확히 일치할 때만 쓰고, "
    "한 사주에서 같은 자리를 서로 다른 지지로 두 번 말하지 마세요(예: '월지 미'와 '월지 묘' 동시 언급 금지). "
    "대운·세운의 지지는 자리 이름으로 부르지 말고 '현재 대운의 지지', '올해(내년)의 기운'처럼 부르세요. "
    "십성(정관·편관·식신·비견 등)과 오행·강약 용어도 같은 원칙입니다 — 용어를 쓴 문장에서 곧바로 "
    "그것이 생활에서 뜻하는 바를 일상어로 이어 말하고(예: '식신이 있어 — 즉 표현하고 즐기는 힘이 좋아'), "
    "용어만으로 문장을 끝내지 마세요. 전체적으로 상담가가 마주 앉아 이야기하듯 짧고 자연스러운 "
    "문장으로 쓰세요."
)

# ---- 핵심 질문 집중 — 직전 대화 주제로 흐르지 말고 '지금 질문'에 정조준 ----
# 실측: 취업운 상담 직후 '남자친구 언제 생겨요?'를 물었는데 답이 다시 취업으로 흐름.
# 대화이력 12턴이 직전 주제로 모델을 끌어당기는 드리프트. 지금 질문 주제에 집중하도록 강제한다.
QUESTION_FOCUS_RULE = (
    "[핵심 질문 집중 — 최우선] 답변은 반드시 방금 받은 '지금 질문'의 핵심 주제에 정조준하세요. "
    "먼저 '지금 질문'에서 사용자가 실제로 물은 핵심 낱말(무엇을·누구의·어떤 점을 묻는지)을 정확히 "
    "집어내고, 바로 그 낱말·주제로만 답하세요. 직전 대화나 이전 답변이 다른 주제였더라도 그 주제를 "
    "이어가지 말고, 지금 질문이 가리키는 주제로 새로 풀이하세요. 질문에 없는 다른 주제"
    "(연애·재물·직업·건강 등 무엇이든)를 임의로 끌어와 답을 그쪽으로 돌리지 마세요. "
    # ⛔ 여기에 특정 주제(예: 연애) 예시를 다시 넣지 말 것 — 과거 '남자친구→연애·인연' 예시가 '남자'
    #    한 낱말을 연애로 앵커링해 '남자 술주정' 질문을 연애운으로 동문서답시킨 실측 원인이다(2026-07-25).
    "특히 질문 속 한 낱말만 보고 넘겨짚어 다른 주제로 바꾸지 마세요(예: '남자'라는 낱말이 있다고 곧바로 "
    "'연애'로, '돈'이 있다고 곧바로 '투자'로 해석하지 말 것 — 질문이 실제로 묻는 것에만 답합니다). "
    "이전 대화는 맥락 참고용일 뿐입니다. 단, 지금 질문이 직전 주제의 자연스러운 연장(같은 주제 "
    "후속질문)이면 이어서 답하세요."
)

# ---- 기본 구성 — 타고난 것(성격·육친·건강) + 시운(올해/월별 '발생할 일') ----
# 운영 정책(전문가 요청, 2026-07 변경): 종합분석 = ①성격 ②육친 ③건강운(사주 본연) → ④올해 발생할 일
# ⑤월별로 발생할 수 있는 일(시운). 직업·재물·연애·결혼은 별도 '성향 축'으로 늘어놓지 않고 ④⑤ '발생할 일'에
# 사건으로 녹인다. 사건은 단정 예언이 아니라 가능성·경향(생길 수 있다/좋은 시기/조심할 때)으로만 — 환각·과장 방지.
# 각 항목은 '한 번만'·명식 근거로 풀고 되풀이하지 않는다. 특정 주제 질문은 그 주제 중심(논지 이탈 금지).
ANSWER_BASE_RULE = (
    "[기본 구성·올해 운세] 사주 전반이나 '올해 운세'를 묻는 일반 질문에는 올해(세운)와 "
    "월별로 생길 수 있는 일(조심할 시기·기회가 오는 시기)을 기본으로 곁들이세요. 월별은 이번 달 하나로 끝내지 말고, "
    "프롬프트의 '[월별 간지…]' 표에 제공된 각 달(이번 달부터 연말 12월까지, 최소 6개월)을 "
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
    "⑤ 월별로 발생할 수 있는 일 — '[월별 간지…]' 표의 각 달(이번 달부터 연말 12월까지, 최소 6개월)을, 표에 십성·관계가 있으면 그것을 근거로 "
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

# ---- 특정 주제 질문 → 집중 답변(결정적 라우팅) ----
# 실측(동문서답): '내년 이직운 몇월'을 물었는데 성격·육친·건강 종합 템플릿으로 답함. 원인=ANSWER_BASE_RULE
# (전체 풀이 구조)이 질문 종류와 무관하게 항상 주입돼, 약한 1차 LLM이 큰 템플릿에 이끌려 끝의 '특정 주제
# 중심' 단서를 무시. 해결=질문에서 특정 주제를 결정적으로 감지하면 종합 템플릿 대신 '집중 답변 규칙'을 준다.
_FOCUS_TOPIC_KO = {
    "contract": "계약·매매", "career": "직업·이직", "promotion": "승진", "exam": "시험·합격",
    "business": "사업", "invest": "투자", "love": "연애·결혼", "money": "재물·금전",
}
_FOCUS_EXTRA = {
    "건강": ("건강", "아픈", "아프", "질병", "병원", "장부", "체질", "수술"),
    "자녀": ("자녀", "자식", "아이", "임신", "출산", "태교"),
    # 성격·성향 = 사람의 기질·행실·버릇을 묻는 질문. 실측 동문서답(2026-07-25) '남자 술주정있을까요'가
    # 어느 키워드에도 안 걸려 연애로 튀었다 → 술주정·주사·바람기 등 '행실·버릇'류를 대폭 보강한다.
    # ⚠️ 이 화이트리스트는 원리상 불완전하다(사람이 물을 표현은 무한) — 목록 밖 표현은 여전히 []로 떨어진다.
    #    근본 백스톱은 출력측 _verify_nonresponsive(동문서답 검출)이다. 여기 추가는 '1차 방어'일 뿐.
    # ⚠️ 부분문자열 매칭(k in q)이라 충돌 주의: 'ㅁ술을/기술을'과 겹치는 bare '술'·'술을'은 넣지 말 것
    #    (수술=건강과도 충돌). '음주/술주정/술버릇/술 마시'처럼 명확한 형태만 사용.
    "성격·성향": ("성격", "성향", "기질", "성정", "성품", "성질", "인품", "됨됨이", "품성",
               "어떤 사람", "어떤사람",
               # 음주·행실
               "술주정", "술버릇", "주사", "주정", "음주", "술 마시", "술고래",
               "바람기", "바람둥이", "바람피", "외도",
               "폭력", "폭행", "때리", "손찌검", "다혈질", "욱하", "화를 잘", "다혈",
               "거짓말", "허풍", "사기",
               # 성실성·근면
               "성실", "게으", "나태", "부지런", "근면",
               # 기질 세부 — ⚠️'예민·소심·까칠·무뚝뚝·우유부단' 등 감정상태 형용사는 넣지 말 것:
               #   "예민함을 조절하는 방법" 같은 '대처법' 질문에서 오발동한다(실측 test_followup_defaults_focused).
               #   구체 '행실·습성' 명사만 유지하고, 형용사 성향은 _verify_nonresponsive 백스톱에 맡긴다.
               "고집", "고지식", "내성적", "외향적", "참을성", "인내심", "끈기", "책임감",
               # 효·금전 습성
               "효자", "효녀", "불효", "효심", "씀씀이", "낭비", "구두쇠", "인색",
               "버릇", "습관", "행실", "품행"),
    "이사·이동": ("이사", "이동", "이전", "방위", "이주"),
}
# 이 표지가 있으면 특정 주제어가 섞여도 '전체 풀이'로 간주(집중 라우팅 해제)
_GENERAL_MARKERS = ("전체", "종합", "전반", "다 풀", "다풀", "모두", "전부", "총평", "다 봐", "다봐")


def _focused_topic_labels(question: str) -> list[str]:
    """질문에서 결정적으로 감지한 특정 주제 라벨. 비면 전체 풀이(종합 템플릿)."""
    q = question or ""
    if any(g in q for g in _GENERAL_MARKERS):
        return []
    labels: list[str] = []
    try:
        from backend.app.saju.gwanbeop import route_topics
        labels += [_FOCUS_TOPIC_KO.get(t, t) for t in route_topics(q)]
    except Exception:  # noqa: BLE001
        pass
    for label, kws in _FOCUS_EXTRA.items():
        if any(k in q for k in kws):
            labels.append(label)
    return list(dict.fromkeys(labels))


def _focused_structure_rule(labels: list[str], depth: str = "basic") -> str:
    topics = "·".join(labels)
    # [2026-07-31] 집중 답변도 '충분한 깊이'로 — 주제는 좁히되 그 안에서 빈약하지 않게(운영자 지시).
    # [패딩 검수 반영] 단일주제 3,000자는 과함 → 밀도형 2,000~2,500 목표(새 내용으로만, ANTI_RESTATE 병행).
    _len = ("2,500자 안팎으로 깊고 밀도 있게" if depth == "deep" else "2,000자 안팎으로 충분하되 밀도 있게")
    return (
        f"[집중 답변 — 특정 주제 질문] 사용자가 '{topics}' 주제를 콕 집어 물었습니다. 성격·육친·건강 "
        "전반을 처음부터 차례로 나열하지 마세요(그 종합 구성은 '전체 풀이'를 청할 때만). 질문한 주제를 "
        f"중심으로 {_len}, 명식([십성·육친]·오행)·세운·월운 근거로 구체적으로 답하고, '몇 월/언제가 좋은지·"
        "나쁜지'를 물으면 '[월별 간지…]' 표의 각 달(십성·관계 포함 시 그 근거)로 유리한 달·조심할 달을 "
        "구체적으로 짚어 주세요. 도입부를 일반 사주 개요나 성격 총평으로 시작하지 말고 질문 핵심부터 바로 "
        "답하되, 그 주제에 대해서는 근거·사례·실생활 조언을 여러 단락으로 충분히 전개하세요(몇 줄로 빈약하게 "
        "끝내지 말 것). "
        # [2026-07-29 전수감사 #8] 서식 지시가 없어 평문 한 덩어리로 나오던 문제 — 구조화 강제.
        "읽기 쉽게 구조화하세요 — 핵심 결론·간지·시기 낱말은 **굵게**, 근거나 항목이 두 갈래 이상이면 "
        "'### 소제목' 또는 '- ' 불릿으로 나눠 주세요."
    )


# 추가질문(follow-up) 기본 = 집중 답변. 전체 풀이·올해/월별 운세를 다시 나열하지 않는다(실측: '스트레스
# 관리법'을 물었는데 이전 질문의 월별 재물운까지 주저리 반복). '전체/종합' 또는 시점(올해·월별·몇월)을
# 명시적으로 물을 때만 종합/월별을 편다.
_COMPREHENSIVE_MARKERS = ("전체", "종합", "전반", "다 풀", "다풀", "모두", "전부", "총평", "다 봐", "다봐",
                          "올해 운세", "월별", "달별", "몇 월", "몇월", "언제", "시기")


def _wants_comprehensive(question: str) -> bool:
    q = question or ""
    return any(k in q for k in _COMPREHENSIVE_MARKERS)


def _followup_focus_rule(depth: str = "basic") -> str:
    # 실측(2026-07-25): 후속질문이 결정적 주제라벨을 못 얻으면(route 빈값) 이 소프트 규칙만 남는다.
    # 직전 연애 답변 발췌가 이력에 ~157:1로 잔존하면 약한 모델이 그쪽으로 끌린다 → '질문 핵심어를 답에
    # 그대로 담아라'로 정박을 강제해 이력 지배를 누른다(원문 인용이 가장 강한 앵커).
    # [2026-07-31] 운영자 지시 — 추가질문 답변이 빈약. '짧게'를 '그 주제에 대해 충분한 깊이'로 전환하되
    #   정박(핵심어 인용)·주제고정·반복금지 방어는 그대로 유지(빈약 해소 + 드리프트 방어 동시).
    # [패딩 검수 반영] 단일주제에 3,000자는 과함(약모델이 부연·복붙으로 패딩) → 밀도형 2,000~2,500 목표로
    #   하향. 분량은 '새 내용'으로만(ANTI_RESTATE_RULE 병행). 근거가 풍부하면 자연히 더 길어져도 됨.
    _len = ("2,500자 안팎으로 깊고 밀도 있게" if depth == "deep" else "2,000자 안팎으로 충분하되 밀도 있게")
    return (
        "[추가질문 — 주제 정조준 + 충분한 깊이] 이건 추가 질문입니다. 먼저 이 질문이 실제로 묻는 핵심 낱말을 "
        "정확히 집어내고, 그 낱말을 답변 안에 반드시 그대로 담아 오직 그 주제에만 정조준하세요. "
        "질문에 없는 다른 주제(연애·재물·직업·건강 등)를 새로 꺼내지 말고, 질문 속 한 낱말만 보고 넘겨짚어 "
        "다른 주제로 바꾸지 마세요(예: '남자'가 있다고 곧바로 '연애'로 답하지 말 것). "
        "성격·육친·건강 전반이나 '올해·월별 운세'를 처음부터 다시 나열하지 말고(사용자가 그걸 콕 집어 물었을 "
        "때만), 앞선 답변에서 이미 말한 문장·표현을 그대로 되풀이하지 마세요(질문과 무관한 곁가지 나열은 금지). "
        f"단, 물어본 그 주제 '하나'에 대해서만큼은 {_len} — 명식(십성·육친·오행)·세운·월운 근거와 구체적 "
        "사례·실생활 조언을 여러 단락으로 나눠 깊이 있게 풀어 주세요(몇 줄로 빈약하게 끝내지 말 것). 결론을 "
        "먼저 제시한 뒤 근거→해석→조언 순으로 충분히 전개하세요. "
        # [2026-07-28] 서식 지시 부재로 '평문 한 덩어리'로 나오던 문제(#8) — 마크다운 마커 강제 유지.
        "읽기 쉽게 구조화하세요 — 핵심 결론 낱말은 **굵게**, 근거·항목이 두 갈래 이상이면 '### 소제목'으로 "
        "나누거나 '- '로 시작하는 불릿으로 정리하세요."
    )


# ---- 반복 금지 — 새 질문에 이전 답변을 되풀이하지 않기 ----
# 실측: 새 질문을 해도 직전 답변의 문장·항목을 그대로 반복. 이력 발췌와 함께 규칙으로도 막는다.
NO_REPEAT_RULE = (
    "[반복 금지] 새 질문에는 새로운 정보·관점으로 답하세요. 직전 답변에서 이미 말한 문장·표현·"
    "항목을 그대로 되풀이하지 말고, 이번 질문에 꼭 필요한 내용만 새로 풀어 주세요. 도입부의 "
    "일반적인 사주 개요(명식 나열·전반 성향)도 매 답변마다 반복하지 말고, 질문 핵심부터 바로 답하세요."
)

# ---- 한 답변 안 반복·복붙 금지(intra-answer) — 분량 확대 시 약모델의 '부연 패딩' 차단 ----
# [2026-07-31] 실측: 분량 목표를 올리자 qwen3 가 새 내용 대신 같은 논점을 여러 섹션에 재진술하고
#   결론에 도입부를 거의 그대로 복붙(~600자 순수 패딩, 8어절 반복 104건). 아래 규칙으로 차단한다.
ANTI_RESTATE_RULE = (
    "[같은 말 반복·복붙 금지 — 매우 중요] 한 답변 안에서 같은 논점(같은 십성·대운·오행·간지 해석)을 "
    "여러 문단·섹션에 되풀이하지 마세요. 특히 <결론/마무리>에서 <도입부>나 앞 문단의 문장을 그대로 복사"
    "(복붙)하지 마세요 — 결론은 앞 내용의 요약 재진술이 아니라 '핵심 한 줄 판단 + 앞에서 안 한 새 실행 "
    "포인트'로 짧게 맺으세요(맺을 새 말이 없으면 결론 문단을 생략). 각 소제목·문단은 반드시 서로 다른 새 "
    "정보(다른 근거·다른 각도·구체 사례·시기·실행 단계)를 담아야 합니다. 분량이 부족해 보여도 같은 말을 "
    "늘리거나 부연해 채우지 말고, 새 관점을 더하거나 그대로 짧게 끝내세요(억지 부연·복붙은 빈약보다 나쁩니다)."
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
    "혼동하지 말고, '일간' 뒤에 지지를 붙이지 마세요(‘일간 병신’ 같은 표기 금지). "
    "또한 특정 연도의 세운 간지(예: '내년은 2027년 정미')는 반드시 '세운'이라고만 부르고 '대운'이라 "
    "하지 마세요 — 대운은 [사주명식]의 대운 목록에 있는 간지만 가리킵니다(세운=그 해 운, 대운=10년 주기)."
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

# ---- 회고 허용 — 질문자가 '특정 지난 연도'를 명시적으로 물었을 때만(FUTURE_ORIENTED_RULE의 예외조항 활성화) ----
# 실측(동문서답): "계묘년 갑진년 사업운 어땠을까"에 '올해 병오'로 답함. 원인=① 그 해 세운이 프롬프트에
# 미주입 ② 미래지향 규칙이 과거 서술을 막음 ③ 출력단 scrub이 과거 간지를 '올해'로 파괴.
# 이 규칙은 질문이 명시한 과거 연도(들)에 한해서만 회고를 허용하고, 그 밖의 과거·간지는 계속 금지한다
# (비회고 질문에는 절대 주입 안 함 → 반대방향 환각 회귀 차단).
RETROSPECTIVE_RULE = (
    "[과거 회고 허용 — 이 질문 한정·최우선] 질문자가 특정 지난 연도(들)를 명시적으로 물었습니다. "
    "프롬프트의 '[질문한 연도 세운]'에 제공된 바로 그 해의 세운 간지를 근거로, 물어본 그 연도(들)의 "
    "운을 회고·판정·서술하세요. 절대 '올해'로 바꾸지 말고, 물어본 연도를 그대로(예: '2023년 계묘년') "
    "쓰되 반드시 제공된 세운 간지만 사용하세요. '[질문한 연도 세운]'에 없는 다른 과거 연도의 간지는 "
    "지어내지 마세요. 각 해를 두루뭉술하게 넘기지 말고 '그 해 ○○운은 ~였습니다'처럼 분명히 판정하세요."
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


def _display_name(user) -> str:
    """상담자 호칭용 이름 — 로그인 사용자의 이메일 '@ 앞부분'만 사용(운영 정책). 없으면 ''(호칭 생략).

    ⚠️ 운영자 결정(2026-07) — 호칭은 반드시 이메일 아이디(예: orion0321). 닉네임을 쓰면 원치 않는
       값('연수' 등)이 노출됨. 다른 에이전트/작업자는 이 정책을 닉네임 등으로 되돌리지 말 것."""
    if user is None:
        return ""
    email = (getattr(user, "email", None) or "").strip()
    local = email.split("@")[0].strip() if "@" in email else ""
    return local[:20]  # 과도한 길이 방지


# ---- 도입 규칙(Phase1) — 한 줄 결론 먼저 + 개인화 호칭 ----
# 경쟁사(운세위키) 대비 보완: 장황한 서론/명식 나열로 시작하지 말고, 질문·고민에 대한 '한 줄 결론'을
# 맨 앞에 제시(판정) 후 근거를 잇는다. 회원 닉네임이 있으면 '○○님'으로 자연스럽게 부른다.
def _lead_verdict_rule(name: str) -> str:
    # 호칭은 '제공된 이름'만 쓰게 하고, 예시엔 이름을 넣지 않는다(약한 LLM이 예시 이름 '연수님'을
    # 실제 호칭으로 베끼던 실측 버그 차단).
    call = (
        f"상담자 호칭은 반드시 '{name}님'만 쓰고(첫 문장에서 한 번), 다른 이름을 지어내지 마세요. "
        if name else
        "상담자 이름이 제공되지 않았으니 호칭(○○님)을 만들어 붙이지 말고 바로 본론으로 시작하세요. "
    )
    return (
        "[도입 규칙 — 판정부터 바로] 답변의 첫 문장은 곧바로 핵심 판정이어야 합니다. 요즘 고민이 함께 "
        "제시됐으면 '그 고민'에 대한 결론을(예: '내년 이직은 급히 옮기기보다 하반기를 노리는 게 유리합니다.'), "
        "없으면 이 사주의 핵심 특징+시사점을(예: '목(木) 기운이 강해 추진력은 좋지만 마무리에서 새는 사주라, "
        "올해는 벌이기보다 정리에 유리합니다.') 한 문장으로 압축하세요. "
        "절대 하지 말 것: '~살펴보겠습니다/풀어드리겠습니다/알아보겠습니다' 같은 예고·인사 문장을 "
        "첫 문장으로 쓰기, '한 줄 판정' 같은 제목·라벨 붙이기, 명식 나열·일반론으로 시작하기, "
        "예시에 나온 이름을 그대로 쓰기. "
        f"{call}이 판정도 근거는 제공된 명식·세운에 두고, 없는 사실을 단정하지 마세요."
    )


def _compose_sys_content(sys_prompt: str, dialect: str | None, explain_level: str,
                         question: str | None = None, person_name: str = "",
                         is_followup: bool = False, has_sources: bool = True,
                         depth: str = "basic") -> str:
    """시스템 프롬프트 + 방언 + 명식표기 규칙(항상) + 쉬운풀이(선택).

    question이 특정 주제(이직·연애·건강 등)를 콕 집으면 종합 템플릿(ANSWER_BASE_RULE) 대신
    '집중 답변 규칙'을 주입해 동문서답(주제 무시하고 성격·육친·건강 나열)을 결정적으로 차단한다.
    is_followup(추가질문)이면 기본을 집중 답변으로 — 전체/월별 운세를 다시 나열하지 않는다.
    has_sources: [참고자료]가 실제로 붙는지(P3-E1). False면 '자료 우선' 문구를 빼고
    '자료 없음 — 문헌명을 지어내지 말라'로 바꾼다. 기본 True 는 기존 호출부 호환."""
    parts = [sys_prompt]
    di = _dialect_instruction(dialect)
    if di:
        parts.append(di)
    parts.append(PILLAR_NOTATION_RULE)  # 간지 음역 환각 방지 — 항상 적용
    parts.append(DAEWOON_RULE)          # 대운 환각 방지 — 항상 적용
    parts.append(AGE_STAGE_RULE)        # 대운·세운을 현재 나이/생애단계에 맞게 — 항상 적용
    parts.append(CHART_FIDELITY_RULE)   # 참고자료 예시 명식 오염 방지 — 항상 적용
    parts.append(expert_voice_rule(has_sources))   # 화법은 항상, '자료 우선'은 자료 있을 때만(P3-E1)
    parts.append(FACT_GROUNDING_RULE)   # 할루시네이션 차단(사실은 제공값만) — 항상 적용
    parts.append(EASY_TERMS_RULE)       # 합충류 용어 절제+일상어 풀이+자리 라벨 정합 — 항상 적용
    parts.append(QUESTION_FOCUS_RULE)   # 직전 주제 이탈 방지 — 지금 질문 주제에 정조준 — 항상 적용
    _focus = _focused_topic_labels(question or "")
    if _focus:
        parts.append(_focused_structure_rule(_focus, depth))  # 특정 주제 질문 → 집중 답변(종합 템플릿 대체)
    elif is_followup and not _wants_comprehensive(question or ""):
        parts.append(_followup_focus_rule(depth))      # 추가질문 → 주제 정조준 + 충분한 깊이
    else:
        parts.append(ANSWER_BASE_RULE)  # 전체 풀이형 구조(성격·육친·건강+발생할일) — 첫 풀이/종합·시점 질문
    parts.append(_lead_verdict_rule(person_name))  # 한 줄 결론 먼저 + 개인화 호칭(Phase1) — 항상 적용
    parts.append(NO_REPEAT_RULE)        # 이전 답변 반복 금지 — 항상 적용
    parts.append(ANTI_RESTATE_RULE)     # 한 답변 안 복붙·재진술 금지(분량확대 패딩 차단) — 항상 적용
    parts.append(YONGSIN_RULE)          # 용신(조후) 환각 차단 — 제공된 조후용신만 인용
    parts.append(ILJU_JOHU_RULE)        # 일주+조후를 성격·배우자운의 근거로 명시(전문가 화법) — 항상 적용
    parts.append(DATE_GANJI_RULE)       # 날짜→간지(세운·월운·일진) 환각 차단 — 항상 적용
    # 질문자가 특정 지난 연도를 명시하면(회고) 그 해에 한해 회고를 허용, 아니면 미래지향 유지
    if _is_retrospective(question or ""):
        parts.append(RETROSPECTIVE_RULE)  # 명시한 지난 연도 세운으로 회고·판정 허용(그 밖 과거는 계속 금지)
    else:
        parts.append(FUTURE_ORIENTED_RULE)  # 오늘 기준 미래지향·과거 회고 금지
    parts.append(CONSULTANT_STYLE_RULE)  # 서식(소제목·굵게·불릿) 상담체 — 사주 계열 메뉴 공통
    # ⚠️규칙 본문은 '마크다운을 쓰라'다(2026-07 개정). 이 주석이 '금지'로 잘못 남아 있어
    #   되돌림을 유도했다 — 타로는 반대로 마크다운을 금지하므로 이 규칙을 빌려 쓰지 않는다.
    # [2026-07-31] 집중·후속은 '충분한 깊이(밀도형)'는 유지하되, 강제 '### 마무리 요약' 섹션은 뺀다 —
    #   패딩 검수 실측에서 약모델이 결론에 도입부를 그대로 복붙(~600자 순수 패딩)하던 벡터를 제거.
    #   '짧게'가 아니라 밀도형이라 _STYLE_RELAX_CONCISE 대신 _NARROW_STYLE_RULE(마무리완화+밀도)을 쓴다.
    if _focus or (is_followup and not _wants_comprehensive(question or "")):
        parts.append(_NARROW_STYLE_RULE)
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

    지연 원인 분석: LLM(qwen3:14b)은 keep_alive=-1 로 이미 상주하나, RAG용 임베더(bge-m3)와
    리랭커(bge-reranker-v2-m3)는 첫 검색 때 지연 로딩(수 초)돼 첫 답변이 늦었다. 백엔드 프로세스는
    재기동마다 이 싱글턴이 초기화되므로, 기동 직후 백그라운드로 미리 로드해 둔다.
      1) 더미 검색 1회 → 임베더(init 로드)+리랭커(lazy 로드) 둘 다 적재.
      2) qwen3:14b 워밍(saju_start.bat 이 기동 시 워밍) → keep_alive=-1 로 상주.
    기동 비차단(별도 스레드에서 호출). 예외는 무시(워밍업 실패해도 첫 요청 때 정상 지연 로딩)."""
    import logging
    log = logging.getLogger("saju.warmup")
    s = get_settings()
    try:
        _get_retriever().search("사주 성격 진로 재물 건강 워밍업", top_k=1, rerank=s.rag_reranker_enabled)
        log.info("[warmup] RAG 임베더+리랭커 상주 완료")
    except Exception as e:  # noqa: BLE001
        log.warning("[warmup] RAG 워밍업 실패(첫 요청 때 로드됨): %s", e)
    # refine 모델(qwen2.5)은 2차보강이 켜진 경우에만 상주 — 꺼져 있으면 VRAM만 차지(실측 4.8GB).
    warm_targets = [s.ollama_model]
    if s.deep_local_refine_enabled:
        warm_targets.append(s.ollama_refine_model)
    for model in warm_targets:
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


def _to_birth_input(b: BirthDTO) -> BirthInput:
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
    "자녀/손주. 같은 대운·세운이라도 나이에 따라 '무엇에 대한 운인지'를 그 단계의 현실에 맞춰 풀어 주세요. "
    "단, 이 나이·생애단계는 '관심 가능 영역'을 고르기 위한 참고일 뿐입니다. 사용자를 '고등학생·대학생·"
    "직장인·취업준비생·수험생' 등 특정 신분으로 단정하거나 '○○로 추정된다'고 쓰지 마세요 — 신분은 "
    "제공되지 않았습니다. 신분을 전제하지 말고 그 나이대의 일반 관심사로만 서술하세요."
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


def _twelve_life_gongmang_lines(chart: SajuChart) -> list[str]:
    """십이운성·십이신살·공망·납음·사령을 프롬프트에 주입(엔진이 이미 계산해 둔 결정값).

    [RAG 전수감사 2026-07-22 최우선 결함] engine.build_chart 가 twelve_life·twelve_sinsal·
    gongmang·napeum·saryeong 을 전부 계산하는데, 소비처가 부적 문구와 사후 검증기뿐이라
    **프롬프트에는 한 줄도 안 들어갔다**. 그 결과 3개 명식 전수에서 오답:
      엔진 {년 관대, 월 장생, 일 관대, 시 양} → 답변 "월지 卯=관대, 일지 丑=장생"(뒤바꿈)
      엔진 공망 寅卯 → 답변 "일주와 시주에 공망이 발생"
    즉 'RAG가 명식을 이긴' 게 아니라 **결정값이 비어 환각이 빈칸을 메운** 것이라, 값 주입만으로
    바로 해소되는 유형이다. ⚠️이 줄을 빼면 십이운성·공망 환각이 즉시 재발한다.
    """
    out: list[str] = []
    tl = getattr(chart, "twelve_life", None) or {}
    if tl:
        out.append("  십이운성(일간 기준, 자리별): "
                   + ", ".join(f"{k}주 {v}" for k, v in tl.items())
                   + " — 이 배정을 바꾸지 말고 그대로 쓰세요")
    ts = getattr(chart, "twelve_sinsal", None) or {}
    if ts:
        out.append("  십이신살(년지 기준, 자리별): " + ", ".join(f"{k}주 {v}" for k, v in ts.items()))
    gm = getattr(chart, "gongmang", None) or []
    if gm:
        out.append(f"  공망(空亡, 일주 기준): {'·'.join(gm)} — 공망은 이 두 지지뿐입니다. "
                   "'일주와 시주가 공망' 처럼 자리로 말하지 말고 위 지지로만 말하세요")
    np_ = getattr(chart, "napeum", None) or {}
    if np_:
        out.append("  납음(納音): " + ", ".join(f"{k}주 {v}" for k, v in np_.items()))
    sr = getattr(chart, "saryeong", "") or ""
    if sr:
        from backend.app.saju.constants import stem_korean as _sk
        out.append(f"  사령(司令): {_sk(sr)}({sr})")
    return out


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
    """현재 나이 → 생애단계 '관심 가능 영역' 라벨(프롬프트 앵커).

    ★ 전문가 지적(2026-07): 사주로 사용자의 신분(고등학생/대학생/직장인 등)을 단정·추정하면 안 됨.
      종전엔 '고등학생 — …'처럼 특정 학교급을 단정했고, 경계도 어긋나(만 19세→고등학생) 2006년생을
      '고등학생으로 추정'하는 환각을 유발했다. → 신분을 명시하지 않고 나이대의 관심 영역만 제시한다.
    """
    if age < 8:
        return "미취학 나이대 — 정서·건강·기초학습"
    if age < 14:
        return "학령 초기 — 학업·교우·적성"
    if age < 17:
        return "학령 중기 — 학업·진로탐색·교우"
    if age < 19:
        return "학업·입시·진로 관심기"
    if age < 24:
        return "진학마무리·취업준비·진로·연애 관심기"
    if age < 30:
        return "취업·커리어초기·연애·결혼 관심기"
    if age < 35:
        return "커리어·결혼·재물 관심기"
    if age < 50:
        return "직업·사업·재물·가정"
    if age < 65:
        return "직업안정·자산·자녀·건강관리"
    return "건강·가족·여가·자산관리·자녀손주(취업/직장운 아님)"


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
        # 극(剋) 방향을 안 주면 뒤집어 쓴다(전수감사 실측 궁합: '금은 화를 억제' — 정답은 火剋金).
        "  오행 상생(生): 목→화→토→금→수→목 / 상극(剋): 목극토, 토극수, 수극화, 화극금, 금극목"
        " — 방향을 바꿔 말하지 마세요",
        f"  일간(本人): {stem_korean(day_stem)}({day_stem}) — {WUXING_KOREAN.get(STEM_TO_WUXING[day_stem], '')}({STEM_TO_WUXING[day_stem]}), 음양: {day_yy}",
        f"  일간 강약: {chart.day_master_strength} (월령 득령 반영 · 지장간 통근까지 계산한 값)",
        # [2026-07-22 운영자 지적] 종전엔 full(천간+지지본기+지장간, 합14)을 넣어 화면 명식표(8글자)와
        #   어긋났다 — 팔자에 금이 0인데 '금 1'로 주입돼 LLM 이 없는 오행을 있다고 서술했다.
        #   화면과 같은 팔자8 기준으로 통일한다. ⚠️ 강약은 위 줄대로 계속 지장간 포함 값을 쓴다.
        f"  오행 분포(팔자 8글자 기준: 천간+지지): {_wuxing_eight_of(chart).as_dict_ko()}"
        " — 이 개수가 명식표와 같은 값입니다. 0개인 오행을 '있다'고 하지 마세요",
    ]
    lines += _sipsin_yukchin_lines(chart, birth)   # 십성·육친(성격·가족/인연 근거)
    lines += _yongsin_lines(chart)   # 억부 방향 + 조후용신(궁통보감 결정값)
    lines += _twelve_life_gongmang_lines(chart)   # 십이운성·십이신살·공망·납음(엔진 결정값)
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
            # [Patch A 2026-07-05] 내년 시점 대운을 결정적으로 주입 — 약한 모델이 과거 대운(예: 19~28세)을
            #   '내년 대운'으로 오인 인용하는 것을 원천 차단(51세 케이스에서 무인19~28을 내년대운이라 헛소리한 재발 방지).
            nage = age + 1.0
            ni = max((i for i, en in enumerate(es) if en.start_age <= nage), default=ci)
            ne = es[ni]
            nend = (es[ni + 1].start_age - 1) if ni + 1 < len(es) else None
            nrng = f"{ne.start_age}~{nend}세" if nend is not None else f"{ne.start_age}세~"
            _dwchg = " (올해와 동일 대운, 대운 전환 아님)" if ni == ci else " (내년에 대운 전환)"
            lines.append(
                f"  ※ 내년(약 {int(nage)}세) → 내년 대운: {_gz_ko(ne.pillar)}({nrng}){_dwchg}. "
                f"'내년·미래' 질문은 반드시 이 내년 대운만 인용하고, 현재 나이보다 낮은 과거 나이대 대운을 "
                f"'내년 대운이 무엇으로 바뀐다'는 식으로 서술하지 마세요."
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
        # 보강(qwen)·외부 LLM 프롬프트의 '근거' 줄. 종전엔 chart_json['wuxing'](full·영문키)을 그대로 써서
        #   ①명식표(팔자8)와 다른 개수가 ②영문 키(wood/fire…)로 재주입돼, 1차 브리프와 모순된 두 값이
        #   한 프롬프트에 공존했다 → 팔자8·한글키로 통일(옛 chart_json 도 pillars 로 재계산).
        eight = _wuxing_eight_ko_from_json(chart_json)
        if eight:
            out.append("오행 분포(팔자 8글자 기준): " + ", ".join(f"{k} {v}" for k, v in eight.items()))
        else:
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
# [P2-7] 이 요청에 실린 참고자료 출처(감사용). 검증 flag 가 남을 때 함께 로깅해 '계산값과
# 충돌한 자료'를 역추적한다. ContextVar 라 요청·태스크마다 독립이며 실패해도 답변에 영향 없음.
_LAST_CHUNKS: "ContextVar[list[tuple[str, int, float]]]" = ContextVar("_LAST_CHUNKS", default=[])


def _rag_trace(limit: int = 6) -> str:
    """직전 검색에 쓰인 청크를 'source#chunk_id@score' 로 요약. 실패해도 빈 문자열."""
    try:
        return ", ".join(f"{s}#{cid}@{sc}" for s, cid, sc in (_LAST_CHUNKS.get() or [])[:limit]) or "-"
    except Exception:  # noqa: BLE001
        return "-"


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


_DATE_CTX = ("그날", "그 날", "해당", "당일", "택일", "추천일", "길일", "날의", "그날의", "오늘", "내일", "모레")
# 'N일은 일지가…'(캘린더)·'10월은 월지 술토'(월운 서술) — 특정 날짜/달의 간지는 본인 명식이 아님.
_DATE_NUM_CTX_RE = re.compile(r"\d{1,2}\s*[일월]\s*[은는의도]?\s*$")
# N월(중순 대표)→지지: 1월=丑…12월=子(연도 무관, 월별표의 15일 기준 compute_pillars와 동일 규약).
# 월별 흐름 단락에서 'N월…월지 X' 서술의 X가 그 달 월운 지지와 일치하면 명식 월지 오탐으로 처리하지 않는다
# (실측 2026-07-21: 오탐이 종합풀이 거의 전건에서 60~130초 재생성+백스톱 헤더 노출을 유발).
_CIVIL_MONTH_BR = "丑寅卯辰巳午未申酉戌亥子"


# 위치어와 지지 사이에 끼면 '그 지지는 명식이 아니라 저쪽 것'이 되는 스코프어.
_OTHER_SCOPE_RE = re.compile(r"세운|대운|월운|년운|연운|일진|오늘|올해|내년|작년|그\s*해")
# 비교 표현 — 스코프어가 끼어 있어도 뒤의 지지는 위치어(명식) 것을 말한다.
_COMPARE_RE = re.compile(r"같은|같이|달리|마찬가지|비해|대비|과\s*동일|와\s*동일")


def _verify_branches(
    answer: str, allowed: dict[str, set[str]], *, exclude_date_ctx: bool = False
) -> list[tuple[str, str, str]]:
    """위치어(월지/일지/년지/시지) 뒤 12자 내 첫 지지가 allowed[위치] 집합에 없으면 불일치.

    위치어 직후만 검사 → 대운·세운·개념(봄 寅卯辰) 오탐 0. exclude_date_ctx=True(택일·오늘운세·캘린더):
    '그날/오늘/N일은' 등 날짜 문맥의 일지는 본인 일지가 아니므로 건너뜀(실측: '오늘 일지 사(巳)가…'
    정답 해설을 본인 일지와 대조해 오탐·교정 오염). 빈 결과 = 일치.
    """
    if not answer or not allowed:
        return []
    bad: list[tuple[str, str, str]] = []
    for pos_ko, key in _POS_WORDS.items():
        allow = allowed.get(key)
        if not allow:
            continue
        for m in re.finditer(re.escape(pos_ko), answer):
            pre = answer[max(0, m.start() - 8): m.start()]
            if exclude_date_ctx and (any(d in pre for d in _DATE_CTX) or _DATE_NUM_CTX_RE.search(pre)):
                continue
            win = answer[m.end(): m.end() + 12]
            # '일지는 오늘 일진과 같은 오화(午)로'처럼 비교 표현이 끼면 지지가 12자 창 밖으로
            # 밀린다(오늘운세의 지배적 화법 — 반례 사냥 실측). 비교 표현이 있을 때만 창을 넓힌다.
            _wide = answer[m.end(): m.end() + 32]
            if _COMPARE_RE.search(_wide[:12]) and not re.search(f"[{_BRANCH_HANJA}]", win):
                win = _wide
            em = re.search("|".join(_ELEM2BRANCH), win)
            claimed = _ELEM2BRANCH[em.group(0)] if em else None
            at = em.start() if em else None
            if claimed is None:
                hm = re.search(f"[{_BRANCH_HANJA}]", win)
                claimed = hm.group(0) if hm else None
                at = hm.start() if hm else None
            # 다른 스코프의 지지 가드: '내 월지와 세운 지지 오(午)가 …'처럼 위치어와 지지 사이에
            # 세운·대운·일진 등이 끼면 그 지지는 명식이 아니라 그쪽 것이다(실측 오탐 — 매번 교정
            # 재생성 1~2분을 헛돌게 만들었다). 위치어 바로 뒤에 붙은 지지만 명식 주장으로 본다.
            # 단, '일지는 오늘 일진과 **같은** 오화(午)'처럼 비교 표현이 끼면 그 지지는
            # 위치어(명식) 쪽 주장이다 — 가드를 풀어 검증한다(반례 사냥 실측).
            if (claimed and at is not None and _OTHER_SCOPE_RE.search(win[:at])
                    and not _COMPARE_RE.search(win[:at])):
                continue
            if pos_ko == "월지" and claimed:
                # 월별 흐름 단락 가드: 앞 400자 내 'N월' 언급이 있고 X가 그 달 월운 지지면
                # 명식 월지 오류가 아니라 월운 서술 — 검증 제외(실측 오탐 msg1002/1012, 거리 15~133자).
                near = answer[max(0, m.start() - 400): m.start()]
                mns = {int(x) for x in re.findall(r"(\d{1,2})\s*월", near) if 1 <= int(x) <= 12}
                if any(claimed == _CIVIL_MONTH_BR[mm - 1] for mm in mns):
                    continue
            if claimed and claimed not in allow:
                bad.append((pos_ko, claimed, "·".join(sorted(allow))))
                break  # 위치당 1회
    return bad


_STEM_HANJA = "甲乙丙丁戊己庚辛壬癸"


# 한글 천간 → 한자. '일간 계수'처럼 한글전용 표기의 일간 오독을 잡기 위한 역매핑(케이스: 무→계).
_KO_STEM_TO_HANJA = {"갑": "甲", "을": "乙", "병": "丙", "정": "丁", "무": "戊",
                     "기": "己", "경": "庚", "신": "辛", "임": "壬", "계": "癸"}
# '일간' 직후 한글 천간 + (그 오행 목화토금수 | 한자병기 '(') — 이 suffix 요구로 '일간이 신약(辛→신)'
# 같은 일반어 오탐을 차단. 예: '일간 계수', '일간은 무토', '일간 계(癸)'.
_DAY_STEM_KO_RE = re.compile(r"일간[은는이가\s]{0,3}([갑을병정무기경신임계])\s*(?:\(\s*[一-鿿]|[목화토금수])")


def _verify_day_stem(answer: str, chart_json: dict | None) -> list[tuple[str, str, str]]:
    """답변의 '일간 …'이 명식 일간과 다르면 불일치. 한자('일간 癸')와 한글('일간 계수') 양쪽 포착.

    한자: '일간' 직후 8자 내 첫 천간 한자. 한글: '일간 <천간><오행/한자>' 형태만(신약 등 오탐 차단).
    """
    if not answer or not chart_json:
        return []
    actual = _day_stem(chart_json)
    if not actual:
        return []
    # ① 한자 표기
    for m in re.finditer("일간", answer):
        # '일간과 辛의 편관'(오늘운세 — 오늘 천간과의 십성 비교)처럼 비교 조사('과/와')가 붙으면
        # 뒤 천간은 일간 자체가 아니라 비교 대상 — 검사 제외(실측 오탐: 정답 해설을 교정 오염).
        if answer[m.end(): m.end() + 1] in ("과", "와"):
            continue
        win = answer[m.end(): m.end() + 8]
        hm = re.search(f"[{_STEM_HANJA}]", win)
        if hm and hm.group(0) != actual:
            return [("일간", hm.group(0), actual)]
    # ② 한글 전용 표기('일간 계수') — 케이스: 무(戊)를 계(癸)로 오독
    for m in _DAY_STEM_KO_RE.finditer(answer):
        han = _KO_STEM_TO_HANJA.get(m.group(1))
        if han and han != actual:
            return [("일간", f"{m.group(1)}({han})", actual)]
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


# 대운·기둥 간지 정규식 공용 조각(한글 '갑자' 또는 한자 '甲子'). 아래 여러 검증기가 참조.
_DW_GANJI = (
    r"(?:[갑을병정무기경신임계][자축인묘진사오미신유술해]"
    r"|[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])"
)


# 4주(柱) 간지 재서술 검증 (전수감사 케이스 #8) — _verify_branches는 '월지/일지' 위치어만 앵커해
# '일주 신미'·'월주 병신'처럼 柱어에 붙은 '간지 통짜' 재서술을 100% 놓친다(실측: 명식 재서술의
# 지배적 화법). 柱어 직후 간지가 명식 해당 기둥과 다르면 플래그(정방향 앵커라 오탐 극소).
_PILLAR_WORD = {"년주": "year", "연주": "year", "월주": "month", "일주": "day", "시주": "hour"}
_PILLAR_NEAR_RE = re.compile(rf"(년주|연주|월주|일주|시주)[은는이가:\s·,()（）]*({_DW_GANJI})")


def _verify_pillar_ganji(answer: str, chart_json: dict | None) -> list[tuple[str, str, str]]:
    """'일주 신미'처럼 柱어 직후 간지가 명식 그 기둥의 간지와 다르면 불일치. 빈 결과 = 일치."""
    if not answer or not chart_json:
        return []
    from backend.app.saju.constants import branch_korean, stem_korean
    pil = (chart_json or {}).get("pillars") or {}
    truth: dict[str, set[str]] = {}
    for key in ("year", "month", "day", "hour"):
        p = pil.get(key) or {}
        st, br = p.get("stem"), p.get("branch")
        if st and br:
            truth[key] = {stem_korean(st) + branch_korean(br), f"{st}{br}"}
    for m in _PILLAR_NEAR_RE.finditer(answer):
        key = _PILLAR_WORD[m.group(1)]
        allow = truth.get(key)
        if allow and m.group(2) not in allow:
            return [(m.group(1), m.group(2), "·".join(sorted(allow)))]
    return []


# 대운(大運) 검증 — '대운'에 직접 붙은 간지가 명식 대운 목록에 없으면 환각(결정적 계산값).
# LLM이 특정 나이대 대운 간지를 지어내면 화면 명식과 어긋남(실측: '현재 대운 (갑자, 15~24세)').
# (_DW_GANJI 는 위 4주 검증에서 함께 쓰려 앞서 정의됨)
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


# ── 대운 나이구간·현재대운 검증 (전수감사 케이스 #6·#7) ─────────────
# _verify_daewoon은 간지 '집합 멤버십'만 봐서 나이구간↔간지 '짝'이 밀려도(간지 자체는 목록에
# 있으면) 통과한다(실측: '11~20세 갑오, 21~30세 계사'의 구간 밀림 / '19세→갑오 대운'). 나이구간과
# 현재대운은 daewoon.entries(start_age)와 birth_date로 완전 결정적이라 명식만으로 재계산해 대조한다.
def _daewoon_ranges(chart_json: dict | None) -> list[tuple[int, int | None, str, str]]:
    """[(시작나이, 끝나이|None, '갑오', '甲午'), ...] — start_age 오름차순. 끝나이=다음 시작-1."""
    from backend.app.saju.constants import branch_korean, stem_korean
    dw = (chart_json or {}).get("daewoon")
    if not isinstance(dw, dict):
        return []
    es = [e for e in (dw.get("entries") or []) if (e.get("pillar") or {}).get("stem")]
    es = sorted(es, key=lambda e: e.get("start_age", 0))
    out: list[tuple[int, int | None, str, str]] = []
    for i, e in enumerate(es):
        p = e["pillar"]
        st, br = p["stem"], p["branch"]
        s = int(e.get("start_age", 0))
        end = int(es[i + 1]["start_age"]) - 1 if i + 1 < len(es) else None
        out.append((s, end, stem_korean(st) + branch_korean(br), f"{st}{br}"))
    return out


_RANGE_DW_RE = re.compile(rf"(\d{{1,3}})\s*[~∼\-–]\s*(\d{{1,3}})\s*세\s*[:：·\s\(（]{{0,3}}({_DW_GANJI})")


def _verify_daewoon_age_range(answer: str, chart_json: dict | None) -> list[tuple[str, str, str]]:
    """'N~M세 간지' 나이구간↔간지 짝이 명식 대운과 어긋나면 불일치. 빈 결과 = 일치.

    간지가 대운목록에 없으면 _verify_daewoon 관할이라 여기선 건너뜀(이중보고 방지). 구간이 대운
    나이대와 ±1세 안에서 안 맞거나 그 나이대의 간지와 다르면 플래그(±1=만나이·대운수 소수 흡수)."""
    if not answer or not chart_json:
        return []
    ranges = _daewoon_ranges(chart_json)
    if not ranges:
        return []
    allow = _daewoon_ganji_set(chart_json)
    for m in _RANGE_DW_RE.finditer(answer):
        lo, g = int(m.group(1)), m.group(3)
        if g not in allow:
            continue  # 간지 자체 환각 → _verify_daewoon 관할
        # 이 간지가 배정돼야 할 실제 구간
        want = next((r for r in ranges if r[2] == g or r[3] == g), None)
        if want and abs(want[0] - lo) > 1:
            rng = f"{want[0]}~{want[1]}세" if want[1] is not None else f"{want[0]}세~"
            return [(f"대운 나이구간({want[2]}={rng})", f"{lo}세대에 {g}", f"{want[2]}는 {rng}")]
    return []


def _chart_birth_date(chart_json: dict | None):
    """chart_json.input.birth_date(ISO) → date. 없으면 None."""
    s = ((chart_json or {}).get("input") or {}).get("birth_date")
    if not s:
        return None
    from datetime import date as _date
    try:
        return _date.fromisoformat(s) if isinstance(s, str) else s
    except Exception:  # noqa: BLE001
        return None


_CUR_DW_RE = re.compile(
    rf"(?:현재|지금)[^\n]{{0,24}}?대운[은는이가:\s·,()（）]*({_DW_GANJI})"        # 현재…대운 X
    rf"|(?:현재|지금|약)\s*(\d{{1,3}})\s*세[^\n]{{0,30}}?대운[은는이가:\s·,()（）]*({_DW_GANJI})"  # 현재 N세…대운 X
)


def _verify_current_daewoon(answer: str, chart_json: dict | None, today=None) -> list[tuple[str, str, str]]:
    """'현재 대운은 X'/'현재 N세…대운 X'의 X가 결정 계산한 현재 대운과 다르면 불일치.

    '현재/지금/약 N세' 문맥에만 좁게 앵커 → '11~20세: 갑오' 같은 목록 나열은 잡지 않음(오탐 방지)."""
    if not answer or not chart_json:
        return []
    bd = _chart_birth_date(chart_json)
    ranges = _daewoon_ranges(chart_json)
    if not bd or not ranges:
        return []
    from datetime import date as _date
    today = today or _date.today()
    age = (today - bd).days / 365.25
    cur = None
    for (s, end, ko, han) in ranges:
        if s <= age:
            cur = (s, end, ko, han)
    if cur is None:
        cur = ranges[0]
    allow = _daewoon_ganji_set(chart_json)
    for m in _CUR_DW_RE.finditer(answer):
        g = m.group(1) or m.group(3)
        if not g or g not in allow:
            continue  # 미포착·간지환각(_verify_daewoon 관할)
        if g not in (cur[2], cur[3]):
            rng = f"{cur[0]}~{cur[1]}세" if cur[1] is not None else f"{cur[0]}세~"
            return [("현재 대운", g, f"{cur[2]}({rng})")]
    return []


# [Patch G 2026-07-05] '내년/명년 대운은 X'의 X가 '과거 대운'(나이구간 끝 < 현재 나이)이면 오인 인용으로 플래그.
#   실측 사고: 51세 고객에게 과거 대운 무인(19~28세)을 '내년 대운이 무인으로 바뀐다'고 서술 → 게이트 통과했었음.
#   내년 대운 = (현재나이+1)이 속한 대운. 이것과 다른데다 과거 구간이면 명백 오류 → 실제 내년 대운으로 교정 유도.
_NEXT_DW_RE = re.compile(rf"(?:내년|명년)[^\n]{{0,30}}?대운[은는이가:\s·,()（）]{{0,12}}?({_DW_GANJI})")


def _verify_future_daewoon(answer: str, chart_json: dict | None, today=None) -> list[tuple[str, str, str]]:
    """'내년 대운은 X'의 X가 과거(현재 나이 이전) 대운이면 불일치. 내년 대운 = 현재나이+1 기준."""
    if not answer or not chart_json:
        return []
    bd = _chart_birth_date(chart_json)
    ranges = _daewoon_ranges(chart_json)
    if not bd or not ranges:
        return []
    from datetime import date as _date
    today = today or _date.today()
    age = (today - bd).days / 365.25
    nage = age + 1.0
    nxt = None
    for (s, end, ko, han) in ranges:
        if s <= nage:
            nxt = (s, end, ko, han)
    if nxt is None:
        nxt = ranges[0]
    allow = _daewoon_ganji_set(chart_json)
    for m in _NEXT_DW_RE.finditer(answer):
        g = m.group(1)
        if not g or g not in allow:
            continue  # 간지 환각은 _verify_daewoon 관할(이중보고 방지)
        if g not in (nxt[2], nxt[3]):
            cited = next((r for r in ranges if r[2] == g or r[3] == g), None)
            if cited and cited[1] is not None and cited[1] < age:  # 인용 대운이 과거 구간
                rng = f"{nxt[0]}~{nxt[1]}세" if nxt[1] is not None else f"{nxt[0]}세~"
                return [("내년 대운(과거 대운 오인)", g, f"{nxt[2]}({rng})")]
    return []


# ── 공망(空亡) 검증 (전수감사 P1) — chart_json.gongmang 2지지와 대조 ──
# ⚠️[P2 프로브 실측 오탐] '공망인 자(子)와 축(丑)'에서 조사 '인'을 지지 寅으로 먹어 정답을
# 오답으로 뒤집었다(공망이 寅을 포함하지 않는 모든 명식에서 재현). 조사 '인'은 **뒤에 공백·괄호가
# 올 때만** 소비하고, '공망 인·묘'처럼 지지로 쓰인 인은 그대로 남긴다.
# ⛔⛔ (?>...) 원자그룹을 일반 그룹 (?:...) 으로 바꾸지 마세요 — 승인 없이 수정 금지 ⛔⛔
#   일반 그룹이면 '공망인 술토와 해수'에서 백트래킹으로 조사 '인'을 도로 뱉어내 다시 지지 寅으로
#   잡는다(실측). 그러면 **공망에 寅이 없는 모든 명식에서 정답이 오답으로 뒤집힌다**.
#   '정규식이 낯설다'는 이유로 되돌리는 일이 없게 여기 박아 둔다.
#   테스트: backend/tests/test_p2_verifier_coverage.py::test_gongmang_particle_in_not_eaten_as_branch
_GONGMANG_NEAR_RE = re.compile(
    r"공망(?>(?:인(?=[\s(（])|[은는이가의:\s·,()（）])*)"
    r"([자축인묘진사오미신유술해子丑寅卯辰巳午未申酉戌亥])"
    r"[\s·,와과및\(（]{0,3}"
    r"([자축인묘진사오미신유술해子丑寅卯辰巳午未申酉戌亥])"
)
# 공망을 '수식어'로 쓰는 문장(구간·신살 서술)은 제외 — 앵커 좌측 8자에 이 어휘가 있으면 skip
_GONGMANG_SKIP_LEFT = ("장성", "반안", "역마", "화개", "대운", "세운", "~세", "면", "이면")


# [P2-4] 공망 지지 1개만 단정하는 화법('공망인 술토가…')도 잡는다. 단, '공망은 사주에서…'의
# '사'를 巳로 오인하지 않도록 **한자 병기 또는 오행자 접미**가 붙은 경우만 지지 주장으로 인정한다.
_GONGMANG_ONE_RE = re.compile(
    r"공망(?:은|는|이|가|인|의|:)?[\s·,()（）]{0,3}(?:지지\s*)?"
    r"(?:([子丑寅卯辰巳午未申酉戌亥])"
    r"|([자축인묘진사오미신유술해])(?=\s*[\(（]\s*[子丑寅卯辰巳午未申酉戌亥]\s*[\)）]|[목화토금수]))"
)
# [P2-4] '일주와 시주가 공망' — 자리로 말하는 화법. 실측 오답이 정확히 이 형태였고 기존
# 검증기는 지지 2개를 요구해 100% 통과시켰다. 위치어와 '공망' 사이에 다른 내용이 끼면
# ('일지 축(丑)은 공망 지지 술·해와 달리…') 주장이 아니므로 인접 패턴만 인정한다.
_PALACE_ALT = r"(?:년주|연주|월주|일주|시주|년지|연지|월지|일지|시지)"
_GONGMANG_PALACE_RE = re.compile(
    rf"({_PALACE_ALT}(?:\s*[·,와과및]\s*{_PALACE_ALT})*)"
    r"\s*(?:에|가|는|은|이|도|들이|들은)?\s*(?:모두\s*)?공망")
_GONGMANG_PALACE_REV_RE = re.compile(
    rf"공망(?:은|는|이|가)?\s*(?:자리는|위치는|해당하는\s*자리는)?\s*"
    rf"({_PALACE_ALT}(?:\s*[·,와과및]\s*{_PALACE_ALT})*)")
_GONGMANG_COND = ("면", "아니", "않", "없", "가정", "대운", "세운", "일진", "만약")


def _verify_gongmang(answer: str, chart_json: dict | None) -> list[tuple[str, str, str]]:
    """공망 단정(지지 2개·1개·자리)이 명식 공망과 다르면 불일치. 빈 결과 = 일치.

    ① '공망은 술·해'(2개) ② '공망인 술토'(1개, 한자·오행 접미 필수) ③ '일주와 시주가 공망'(자리).
    ③은 그 자리 지지가 실제 공망 지지인지로 판정한다(공망은 지지의 성질이지 자리의 성질이 아니다)."""
    if not answer or not chart_json:
        return []
    gm = (chart_json or {}).get("gongmang") or []
    if len(gm) < 2:
        return []
    from backend.app.saju.constants import branch_korean
    gm_ko = "·".join(f"{branch_korean(b)}({b})" for b in gm)

    def _norm(c: str) -> str:
        if c in "子丑寅卯辰巳午未申酉戌亥":
            return c
        return EARTHLY_BRANCHES[BRANCH_KOREAN.index(c)] if c in BRANCH_KOREAN else c

    for m in _GONGMANG_NEAR_RE.finditer(answer):
        left = answer[max(0, m.start() - 8): m.start()]
        if any(k in left for k in _GONGMANG_SKIP_LEFT):
            continue
        if not {_norm(m.group(1)), _norm(m.group(2))}.issubset(set(gm)):
            return [("공망", f"{m.group(1)}·{m.group(2)}", gm_ko)]
    for m in _GONGMANG_ONE_RE.finditer(answer):
        left = answer[max(0, m.start() - 8): m.start()]
        if any(k in left for k in _GONGMANG_SKIP_LEFT):
            continue
        claimed = m.group(1) or m.group(2)
        if _norm(claimed) not in set(gm):
            return [("공망", claimed, gm_ko)]
    # ③ 자리 서술 — 그 자리의 지지가 공망 지지가 아니면 오류
    br = _pillar_branches(chart_json)
    for rgx in (_GONGMANG_PALACE_RE, _GONGMANG_PALACE_REV_RE):
        for m in rgx.finditer(answer):
            # 가정·부정 판정은 **같은 문장 안에서만** — 고정 창(±10자)이면 앞 문장 끝의
            # '…없습니다.' 같은 무관한 글자를 삼켜 진성 오류를 놓친다(실측 5/337 미검출).
            s0 = max((answer.rfind(c, 0, m.start()) for c in ".!?。\n"), default=-1) + 1
            e0 = next((k for k in range(m.end(), min(len(answer), m.end() + 20))
                       if answer[k] in ".!?。\n"), min(len(answer), m.end() + 20))
            if any(k in answer[s0:e0] for k in _GONGMANG_COND):
                continue
            for pal in re.findall(_PALACE_ALT, m.group(1)):
                key = _PALACE_ANY.get(pal)
                actual = br.get(key)
                if actual and actual not in gm:
                    true_pal = [p for p, k in (("년주", "year"), ("월주", "month"),
                                               ("일주", "day"), ("시주", "hour"))
                                if br.get(k) in gm]
                    want = ("·".join(true_pal) + f"({gm_ko})") if true_pal else f"공망 지지 {gm_ko}는 명식에 없음"
                    return [("공망 자리", f"{pal}({branch_korean(actual)})", want)]
    return []


# ── 대운 순/역행 검증 (전수감사 P1) — chart_json.daewoon.direction ──
_DIRECTION_RE = re.compile(
    r"대운[은는이가의\s:·,，()（）]*(순행|역행)"
    r"|(순행|역행)\s*(?:하[며면고는]|합?니?다|으?로)?[^。.\n]{0,6}대운"
)


def _verify_daewoon_direction(answer: str, chart_json: dict | None) -> list[tuple[str, str, str]]:
    """'대운은 역행' 방향 주장이 명식 방향과 다르면 불일치. 대운 앵커라 오탐 낮음."""
    if not answer or not chart_json:
        return []
    dw = (chart_json or {}).get("daewoon")
    if not isinstance(dw, dict) or dw.get("direction") not in ("forward", "backward"):
        return []
    want = "순행" if dw["direction"] == "forward" else "역행"
    for m in _DIRECTION_RE.finditer(answer):
        claimed = m.group(1) or m.group(2)
        ctx = answer[max(0, m.start() - 6): m.end() + 8]   # 방향어 앞뒤 — 부정문·타운(세운) 가드
        if any(k in ctx for k in ("세운", "월운", "연운", "아니", "않", "말고")):
            continue
        if claimed and claimed != want:
            return [("대운 방향", claimed, want)]
    return []


# ── 용신 단정 앵커 (P2-1) ───────────────────────────────────────────
# 기존 검증기는 '조후용신' 정확일치만 스캔해 실서비스의 지배적 화법인 '용신은 임(壬)'·'용신 己土'
# 를 전부 놓쳤다(전수감사 16케이스 중 미포착). '용신' 일반 앵커로 넓히되 오탐을 3중으로 막는다:
#   ① 다른 개념어(억부·희신·기신…)가 좌측에 있으면 skip
#   ② 부정문('용신이 아니')이면 skip
#   ③ 주장 천간의 오행이 **억부 방향**과 맞으면 skip — 조후(壬 등)와 억부(水 계열)는 층이 달라
#      둘 다 정답일 수 있다. 이 가드가 없으면 '신약하니 용신은 계수' 같은 정답을 재생성으로 파괴한다.
_YONGSIN_OTHER_LEFT = ("억부", "희신", "기신", "구신", "한신", "격국", "병약", "통관", "전왕", "조후는")
_YONGSIN_CLAIM_RE = re.compile(
    r"용신(?:으로|[은는이가인:])?[\s,·]{0,2}(?:천간\s*)?"
    rf"(?:([{_STEM_HANJA}])|([갑을병정무기경신임계])(?=\s*[\(（]\s*[一-鿿]|[목화토금수]))"
)
_YONGSIN_NEG_RE = re.compile(r"아니|아닙|아닌|않|없|말고|대신")


def _eokbu_elements(chart_json: dict | None) -> set[str]:
    """억부(강약) 관점에서 용신이 될 수 있는 오행 집합. 중화면 전체(=불개입)."""
    from backend.app.saju.constants import WUXING_GENERATES, WUXING_OVERCOMES
    dm = (chart_json or {}).get("day_master_element")
    if not dm or dm not in WUXING_GENERATES:
        return set()
    st = (chart_json or {}).get("day_master_strength")
    if st == "strong":     # 설기·극제 — 식상·재성·관성
        gen_me_over = {v: k for k, v in WUXING_OVERCOMES.items()}[dm]
        return {WUXING_GENERATES[dm], WUXING_OVERCOMES[dm], gen_me_over}
    if st == "weak":       # 부조 — 인성·비겁
        return {{v: k for k, v in WUXING_GENERATES.items()}[dm], dm}
    return {"木", "火", "土", "金", "水"}


def _verify_yongsin(answer: str, chart_json: dict | None) -> list[tuple[str, str, str]]:
    """'용신은 X(천간)' 단정이 조후용신(정·보조)과도, 억부 방향과도 어긋나면 불일치.

    '조후용신' 표기는 조후 정답 집합만으로 엄격 판정하고, 일반 '용신' 표기는 억부 허용 오행까지
    열어 준다(두 관법이 공존하므로). 오행만 말한 경우('용신은 화')는 층이 달라 불개입.
    """
    if not answer or not chart_json:
        return []
    jy = (chart_json or {}).get("johu_yongsin") or {}
    primary = jy.get("primary")
    if not primary:
        return []
    allow = {primary} | set(jy.get("supporting") or [])
    # ① 엄격 앵커 — '조후용신'은 조후 정답만 허용
    for m in re.finditer("조후용신", answer):
        win = answer[m.end(): m.end() + 12]
        hm = re.search(f"[{_STEM_HANJA}]", win)
        if hm and hm.group(0) not in allow:
            return [("조후용신", hm.group(0), _stem_ko(primary))]
    # ② 일반 앵커 — 조후 ∪ 억부오행 어디에도 못 걸리면 환각
    eokbu = _eokbu_elements(chart_json)
    for m in _YONGSIN_CLAIM_RE.finditer(answer):
        left = answer[max(0, m.start() - 10): m.start()]
        if any(k in left for k in _YONGSIN_OTHER_LEFT):
            continue
        if _YONGSIN_NEG_RE.search(answer[m.start(): m.end() + 10]):
            continue
        han = m.group(1) or HEAVENLY_STEMS[STEM_KOREAN.index(m.group(2))]
        if han in allow or STEM_TO_WUXING.get(han) in eokbu:
            continue
        return [("용신", _stem_ko(han), _stem_ko(primary))]
    return []


# ── 4주 천간 자리 검증 (P2-2) ────────────────────────────────────────
# _POS_WORDS 는 지지 4자리만 다뤄 년간·월간·시간 오식이 **무검증 통과**했다(일간만 별도 검증기).
# '시간'은 time 과 동음이라 오탐 위험이 크므로 ①직후에 천간 토큰이 붙을 때만 ②수량 문맥
# ('3시간','몇 시간') 제외 ③다른 스코프(세운·대운) 개입 시 skip — 세 겹으로 좁힌다.
_STEM_POS_WORD = {"년간": "year", "연간": "year", "월간": "month", "시간": "hour"}
_STEM_POS_RE = re.compile(
    r"(년간|연간|월간|시간)\s*(?:[\(（]\s*[年月時]?\s*干\s*[\)）])?[은는이가의인:·,]{0,2}\s*(?:천간\s*)?"
    rf"(?:([{_STEM_HANJA}])|([갑을병정무기경신임계])(?=\s*[\(（]\s*[一-鿿]|[목화토금수]))"
)
_QTY_LEFT_RE = re.compile(r"[0-9몇여러한두세네다섯여섯일곱여덟아홉열\s]$")


@lru_cache(maxsize=64)
def _luck_stems(kind: str, num: int, base_year: int) -> frozenset[str]:
    """월별/연도별 '운(運)' 천간 후보. kind='month'면 num=N월, 'year'면 num=연도.

    [P2-6 오탐 사냥 실측] '#### 3월 (신묘월) — **월간 십성 정재**'처럼 월별 흐름 단락에서
    '월간'은 그 달 월운의 천간을 뜻한다(명식 월간이 아니다). 이 값과 일치하면 명식 오류가
    아니므로 검증을 건너뛴다 — _verify_branches 의 월별 가드와 같은 원리·같은 목적이다.
    """
    from datetime import date as _date
    from backend.app.saju.pillars import compute_pillars
    from backend.app.saju.types import BirthInput as _BI, CalendarType as _CT
    out: set[str] = set()
    try:
        if kind == "month":
            for y in (base_year, base_year + 1):
                fp, *_ = compute_pillars(_BI(birth_date=_date(y, num, 15), calendar=_CT.SOLAR))
                out.add(fp.month.stem)
        else:
            fp, *_ = compute_pillars(_BI(birth_date=_date(num, 6, 15), calendar=_CT.SOLAR))
            out.add(fp.year.stem)
    except Exception:  # noqa: BLE001
        return frozenset()
    return frozenset(out)


def _verify_pillar_stems(answer: str, chart_json: dict | None) -> list[tuple[str, str, str]]:
    """'월간 庚'·'시간은 을목'처럼 천간 자리 단정이 명식과 다르면 불일치. 빈 결과 = 일치."""
    if not answer or not chart_json:
        return []
    from datetime import date as _date
    pil = (chart_json or {}).get("pillars") or {}
    cur_year = _date.today().year
    for m in _STEM_POS_RE.finditer(answer):
        pos_ko = m.group(1)
        key = _STEM_POS_WORD[pos_ko]
        actual = (pil.get(key) or {}).get("stem")
        if not actual:
            continue
        left = answer[max(0, m.start() - 8): m.start()]
        if _OTHER_SCOPE_RE.search(left) and not _COMPARE_RE.search(left):
            continue
        if pos_ko == "시간" and _QTY_LEFT_RE.search(left):
            continue      # '3시간 정도'류 수량 표현 — 명식 주장이 아니다
        han = m.group(2) or HEAVENLY_STEMS[STEM_KOREAN.index(m.group(3))]
        if han == actual:
            continue
        near = answer[max(0, m.start() - 400): m.start()]
        if key == "month":     # 월별 흐름 단락의 '월간' = 그 달 월운 천간(명식 아님)
            mons = {int(x) for x in re.findall(r"(\d{1,2})\s*월", near) if 1 <= int(x) <= 12}
            if any(han in _luck_stems("month", mm, cur_year) for mm in mons):
                continue
        if key == "year":      # 'YYYY년 …' 단락의 '년간' = 그 해 세운 천간
            yrs = {int(x) for x in re.findall(r"(20\d{2})\s*년", near)}
            if any(han in _luck_stems("year", yy, cur_year) for yy in yrs):
                continue
        return [(pos_ko, _stem_ko(han), _stem_ko(actual))]
    return []


# ── 십이운성·십이신살 검증 (P2-5) ────────────────────────────────────
# P0-1 로 결정값(twelve_life·twelve_sinsal)을 프롬프트에 주입했으므로 이제 대조가 가능하다.
# 실측 오답: 엔진 {월 장생, 일 관대} → 답변 '월지 卯=관대, 일지 丑=장생'(자리 뒤바꿈).
# 한 글자 단계어(쇠·병·사·묘·절·태·양)는 일상어·지지(卯=묘)와 충돌하므로 **한자 병기형만** 인정한다.
_LIFE_MULTI = ("장생", "목욕", "관대", "건록", "제왕")
_LIFE_SINGLE_HANJA = {"衰": "쇠", "病": "병", "死": "사", "墓": "묘", "絶": "절", "絕": "절",
                      "胎": "태", "養": "양"}
# ⚠️두 글자 단계어도 일상어와 충돌한다 — '관대하다'(너그럽다)는 성격 풀이의 단골이고,
# '목욕탕'·'제왕절개'도 있다. 단계어로 인정할 때 이 세 꼬리를 배제한다.
_LIFE_MULTI_RE = r"(?:장생|목욕(?!탕)|관대(?!하|함|히|해)|건록|제왕(?!절))"
_LIFE_TOKEN_RE = re.compile(
    f"({_LIFE_MULTI_RE})" + r"|[가-힣]?\s*[\(（]\s*(" + "|".join(_LIFE_SINGLE_HANJA) + r")\s*[\)）]"
)
# [P2-6 실측] 위 정규식만으로는 검출률이 45%에 그쳤다 — 12단계 중 7개가 한 글자라 '월지는 태'
# 처럼 한자 없이 쓰면 통째로 빠져나간다. 그렇다고 맨 '묘·병·사·양'을 잡으면 지지 卯·오행어와
# 충돌한다. → **같은 문장에 '운성/포태'가 있을 때만** 맨 한 글자를 단계어로 인정한다.
# 뒤는 '조사/문장부호'만 허용 — 이 lookahead 가 곧 '단어의 첫 글자'(사주·태왕·양기·병존·묘하게)와
# 단계어를 가르는 선이다. 단순한 (?![가-힣]) 로는 '태입니다'조차 못 잡아 검출률이 45%에 머물렀다.
_LIFE_BARE_RE = re.compile(
    r"(?<![가-힣])(" + "|".join(dict.fromkeys(_LIFE_SINGLE_HANJA.values())) + r")"
    r"(?=[\s.,;:·)\]!?]|$|입니|이다|이며|이고|이라|에|의|으로|인|로|을|를|와|과|은|는|이|가)")
# 문맥 판정어 — '운성·포태' 외에 명확한 두 글자 단계어가 같은 문장에 있으면 그 문장은
# 십이운성 나열이다('년주 관대, 월주 태, 일주 묘'). 그때만 맨 한 글자를 단계어로 읽는다.
_LIFE_CTX_RE = re.compile(f"운성|포태|{_LIFE_MULTI_RE}")
_SENT_SPLIT_RE = re.compile(r"[.!?。\n]")
_PALACE_ANY = {"년지": "year", "연지": "year", "월지": "month", "일지": "day", "시지": "hour",
               "년주": "year", "연주": "year", "월주": "month", "일주": "day", "시주": "hour"}
# ⚠️engine.build_chart 는 twelve_life·twelve_sinsal·napeum 을 **한글 키**('년','월','일','시')로
# 만든다(pillars 만 영문 키). 프로브에서 실제로 이 불일치에 걸려 검증기가 통째로 무발동했다.
_PALACE_TL_KEY = {"year": "년", "month": "월", "day": "일", "hour": "시"}


def _verify_twelve_life(answer: str, chart_json: dict | None) -> list[tuple[str, str, str]]:
    """'월지는 관대'처럼 자리별 십이운성 단정이 엔진 계산과 다르면 불일치. 빈 결과 = 일치."""
    if not answer or not chart_json:
        return []
    tl = (chart_json or {}).get("twelve_life") or {}
    if not tl:
        return []
    for pos_ko, key in _PALACE_ANY.items():
        want = tl.get(_PALACE_TL_KEY[key]) or tl.get(key)
        if not want:
            continue
        for m in re.finditer(re.escape(pos_ko), answer):
            win = answer[m.end(): m.end() + 18]
            tm = _LIFE_TOKEN_RE.search(win)
            claimed = (tm.group(1) or _LIFE_SINGLE_HANJA.get(tm.group(2) or "", "")) if tm else ""
            if not claimed:
                # 한 글자 단계어는 '운성/포태'가 같은 문장에 있을 때만 인정(卯·병(病)·양(陽) 오탐 차단)
                s0 = max((answer.rfind(c, 0, m.start()) for c in ".!?。\n"), default=-1) + 1
                e0 = next((k for k in range(m.end(), min(len(answer), m.end() + 60))
                           if answer[k] in ".!?。\n"), min(len(answer), m.end() + 60))
                if not _LIFE_CTX_RE.search(answer[s0:e0]):
                    continue
                tm = _LIFE_BARE_RE.search(win)
                if not tm:
                    continue
                claimed = tm.group(1)
            if _OTHER_SCOPE_RE.search(win[:tm.start()]):
                continue      # '월지와 세운의 관대' 류 — 명식 자리 주장이 아니다
            if claimed != want:
                return [(f"{pos_ko} 십이운성", claimed, want)]
            break             # 자리당 1회(정답 확인)
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


# 월별 흐름의 '월번호↔간지' 매핑 검증 — 표가 한 칸 밀려 다음 달 간지가 앞 달에 붙는 환각
# (실측 케이스 #5: 7월(丙申)·8월(丁酉)… 전체 밀림). 달력 월의 대표 간지(중순 기준)는 결정적
# 계산값이라 명식 없이 판정한다. '작년 7월' 등 과거 문맥은 불개입.
_MONTH_GANJI_CLAIM_RE = re.compile(
    r"(?:(20\d{2})\s*년\s*)?(\d{1,2})\s*월\s*[\s\(\[]{0,3}"
    rf"({_DW_GANJI})"
)
_MONTH_PAST_CTX = ("작년", "지난", "재작년", "그해", "그 해", "당시", "과거")


def _verify_month_ganji(answer: str, today=None) -> list[tuple[str, str, str]]:
    """'N월 (간지)' 주장 전수를 결정 계산값과 대조. 빈 결과 = 일치.

    연도 추론: 명시 연도 > (월 ≥ 당월이면 올해, 아니면 내년 — 월별 흐름은 미래 서술이므로)."""
    if not answer:
        return []
    from datetime import date as _date
    from backend.app.saju.pillars import compute_pillars
    from backend.app.saju.types import BirthInput as _BI, CalendarType as _CT
    today = today or _date.today()
    bad: list[tuple[str, str, str]] = []
    seen: set[tuple[int, int]] = set()
    for m in _MONTH_GANJI_CLAIM_RE.finditer(answer):
        ystr, mon_s, g = m.group(1), m.group(2), m.group(3)
        mon = int(mon_s)
        if not 1 <= mon <= 12:
            continue
        ctx = answer[max(0, m.start() - 10): m.start()]
        if any(k in ctx for k in _MONTH_PAST_CTX):
            continue
        # 연도 추론: 명시 연도 > 근접 문맥('내년'→+1, '올해/금년'→올해) > 무표기=올해·내년 양쪽 후보.
        # 실측 오탐 2건: ①'내년 8월 무신월'(정답)을 올해 기준 오판 ②연도 무표기 신년운세형 답변
        # ('1월 (기축월)…', 올해 1~6월 나열 — 2026 정답)을 과거월=내년 규칙으로 2027 대조해 전건 오탐.
        # → 무표기는 올해·내년 '둘 다' 틀릴 때만 플래그(오탐이 정답을 재생성으로 파괴하는 해악 차단;
        #   진짜 표밀림 환각은 어느 해와도 안 맞아 여전히 검출됨).
        wide_ctx = answer[max(0, m.start() - 24): m.start()]
        if ystr:
            years = [int(ystr)]
        elif "내년" in wide_ctx or "명년" in wide_ctx:
            years = [today.year + 1]
        elif "올해" in wide_ctx or "금년" in wide_ctx:
            years = [today.year]
        else:
            years = [today.year, today.year + 1]
        years = [y for y in years if y >= today.year]
        if not years or (years[0], mon) in seen:
            continue
        if g[0] in STEM_KOREAN:   # 한글 간지 → 한자(위치 기준이라 중의성 없음)
            claimed = HEAVENLY_STEMS[STEM_KOREAN.index(g[0])] + EARTHLY_BRANCHES[BRANCH_KOREAN.index(g[1])]
        else:
            claimed = g
        exps = []
        matched = False
        for y in years:
            fp, *_ = compute_pillars(_BI(birth_date=_date(y, mon, 15), calendar=_CT.SOLAR))
            exps.append(fp.month)
            if claimed == fp.month.stem + fp.month.branch:
                matched = True
                break
        if not matched:
            seen.add((years[0], mon))
            exp_ko = _gz_ko(exps[0])   # 대표 정답 = 1순위 후보 연도
            bad.append((f"{mon}월 월운(정답 {exp_ko})", g, exp_ko))
    return bad


# ── 특정 연도↔세운 간지 검증 (전수감사 P1) — 'YYYY년 간지'가 그 해 실제 세운과 다르면 ──
_YEAR_GANJI_CLAIM_RE = re.compile(rf"(20\d{{2}})\s*년\s*[\s\(（]{{0,2}}({_DW_GANJI})")


def _verify_year_ganji(answer: str) -> list[tuple[str, str, str]]:
    """'2027년 갑자'처럼 명시 연도 뒤 세운 간지가 그 해 실제 간지와 다르면 불일치. 빈 결과 = 일치.

    올해 이후 연도만(과거는 _scrub_stale_year_ganji 관할). '2027년 3월' 등 뒤가 간지 아니면 불개입."""
    if not answer:
        return []
    from datetime import date as _date
    cur_year = _date.today().year
    seen: set[int] = set()
    for m in _YEAR_GANJI_CLAIM_RE.finditer(answer):
        year, g = int(m.group(1)), m.group(2)
        if year < cur_year or year in seen:
            continue
        seen.add(year)
        try:
            ko, hj = _year_ko_hj(year)
        except Exception:  # noqa: BLE001
            continue
        if g not in (ko, hj):
            return [(f"{year}년 세운(정답 {ko}({hj}))", g, f"{ko}({hj})")]
    return []


# ── 궁합 관계 검증 (전수감사 P1) — 두 일지/일간의 합·충·삼합 라벨이 결정값과 반대면 ──
# 궁합 경로는 _verify_branches+day_stem만 돌아 '관계 라벨'(육합/삼합/충)은 전혀 검증 안 됨.
# 두 일지·일간은 chart_json에 있고 관계는 constants로 완전 결정적. 라벨이 뒤바뀌면(육합↔충 등) 플래그.
def _compat_day_relations(a_cj: dict | None, b_cj: dict | None) -> dict[str, str]:
    """{'일지관계': '육합'|'삼합'|'충'|'무', '일간관계': '천간합'|'천간충'|'무'}. 정답 계산."""
    from backend.app.saju.constants import (
        BRANCH_CONFLICTS, BRANCH_SIX_COMBINATIONS, BRANCH_TRIPLE_COMBINATIONS,
        STEM_COMBINATIONS, STEM_CONFLICTS,
    )
    out: dict[str, str] = {}
    da, db_ = _day_stem(a_cj), _day_stem(b_cj)
    ba = ((a_cj or {}).get("pillars") or {}).get("day", {}).get("branch")
    bb = ((b_cj or {}).get("pillars") or {}).get("day", {}).get("branch")
    if ba and bb:
        pair = frozenset({ba, bb})
        if pair in BRANCH_SIX_COMBINATIONS:
            out["일지관계"] = "육합"
        # len==2 가드: 같은 일지는 1원소 집합이라 삼합 부분집합 검사에 항상 걸림(엔진 오판과 동일 결함).
        # compatibility._score_day_branch 의 가드와 반드시 동시 유지 — 한쪽만 고치면 교정 루프가 되돌림.
        elif len(pair) == 2 and any(pair <= t for t in BRANCH_TRIPLE_COMBINATIONS):
            out["일지관계"] = "삼합"
        elif pair in BRANCH_CONFLICTS:
            out["일지관계"] = "충"
    if da and db_:
        pair = frozenset({da, db_})
        if pair in STEM_COMBINATIONS:
            out["일간관계"] = "천간합"
        elif pair in STEM_CONFLICTS:
            out["일간관계"] = "천간충"
    return out


_COMPAT_REL_TOKENS = {
    "일지": [("육합", ("육합",)), ("삼합", ("삼합", "반합")), ("충", ("충",))],
    "일간": [("천간합", ("천간합", "간합")), ("천간충", ("천간충", "간충"))],
}
_COMPAT_NEG = ("아니", "아닙", "아닌", "없", "않", "말고")  # '충이 아닙니다/아닌'(정답 부정문) 오탐 방지


def _verify_compat_relations(answer: str, a_cj: dict | None, b_cj: dict | None) -> list[tuple[str, str, str]]:
    """궁합 답변이 일지/일간 관계를 결정값과 반대로 단정하면 불일치. 빈 결과 = 일치.

    '일지'/'일간' 직후 창에 실제 관계어가 있으면 통과; 없고 다른(상반) 관계어만 있으면 플래그.
    부정문(~아니/없다)은 skip(오탐 방지)."""
    if not answer:
        return []
    rel = _compat_day_relations(a_cj, b_cj)
    for palace in ("일지", "일간"):
        want = rel.get(f"{palace}관계")
        if not want:
            continue
        want_toks = dict(_COMPAT_REL_TOKENS[palace])[want]
        for m in re.finditer(palace, answer):
            win = answer[m.end(): m.end() + 16]
            if any(n in win for n in _COMPAT_NEG):
                continue
            if any(t in win for t in want_toks):
                continue  # 정답 관계어가 있음 → 통과
            wrong = next((canon for canon, toks in _COMPAT_REL_TOKENS[palace]
                          if canon != want and any(t in win for t in toks)), None)
            if wrong:
                return [(f"{palace} 관계", wrong, want)]
    return []


# ── 4주 통짜 명식 검출 (P2-3) ────────────────────────────────────────
# 지금까지의 검증기는 전부 '위치어(월지·일주) 앵커' 방식이라, 위치어 없이 명식을 통째로 적는
# 두 화법을 구조적으로 못 잡았다 — 이게 RAG 오염(남의 사주 인용)이 답변에 실리는 주된 통로다.
#   ① 산문형: '무오년 을묘월 갑술일 신미시입니다'
#   ② 표/그리드형: 천간이 늘어선 줄 바로 아래 지지가 늘어선 줄(스캔본 명식표 그대로 복사)
# 둘 다 '내 명식'을 말하는 자리에서만 성립하는 화법이라, 값이 명식과 다르면 곧 타인 명식이다.
_PROSE_G = (r"(?:[갑을병정무기경신임계][자축인묘진사오미신유술해]"
            r"|[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])")
_PROSE_FOUR_RE = re.compile(
    rf"({_PROSE_G})\s*년[\s,·]{{0,3}}({_PROSE_G})\s*월[\s,·]{{0,3}}({_PROSE_G})\s*일"
    rf"(?:[\s,·]{{0,3}}({_PROSE_G})\s*시)?")
_PROSE_SKIP_LEFT = ("세운", "대운", "월운", "일진", "오늘", "예를", "예시", "가령", "만약", "샘플")
_GRID_STEM_RE = re.compile(f"[{_STEM_HANJA}]")
_GRID_BRANCH_RE = re.compile(f"[{_BRANCH_HANJA}]")


_GRID_SKIP_CTX = ("대운", "세운", "월운", "연운", "년운", "유년", "일진", "예시", "예를", "샘플", "가령")


def _grid_pillars(text: str) -> list[tuple[list[str], list[str]]]:
    """천간 3~4개가 늘어선 짧은 줄 + 뒤 3줄 안의 지지 줄 → (천간들, 지지들) 목록.

    라벨 셀('| 천간 |')이 붙은 마크다운 표도 포착하려 '줄에서 뽑은 개수'로 판정한다.
    · 줄 길이 60자 상한 → 산문(천간을 여럿 언급하는 해설) 배제
    · 개수 3~4 상한 → 대운·세운 표(간지 8~10개)를 4주표로 오인하지 않음
    · 주변 4줄에 대운·세운·예시 어휘가 있으면 4주표가 아니므로 skip(오탐 차단)"""
    lines = text.splitlines()
    out: list[tuple[list[str], list[str]]] = []
    for i, ln in enumerate(lines):
        if len(ln) > 60:
            continue
        st = _GRID_STEM_RE.findall(ln)
        if not (3 <= len(st) <= 4) or len(_GRID_BRANCH_RE.findall(ln)) > 1:
            continue
        for j in range(i + 1, min(i + 4, len(lines))):
            nx = lines[j]
            if len(nx) > 60:
                continue
            br = _GRID_BRANCH_RE.findall(nx)
            if not (3 <= len(br) <= 4) or len(_GRID_STEM_RE.findall(nx)) > 1:
                continue
            ctx = "\n".join(lines[max(0, i - 2): j + 2])
            if not any(k in ctx for k in _GRID_SKIP_CTX):
                out.append((st, br))
            break
    return out


def _verify_whole_chart(answer: str, chart_json: dict | None) -> list[tuple[str, str, str]]:
    """4주를 통째로 적은 서술(산문형·표형)이 명식과 다르면 불일치 — 타인 명식 인용 차단."""
    if not answer or not chart_json:
        return []
    from backend.app.saju.constants import branch_korean, stem_korean
    pil = (chart_json or {}).get("pillars") or {}
    truth: dict[str, set[str]] = {}
    for key in ("year", "month", "day", "hour"):
        p = pil.get(key) or {}
        if p.get("stem") and p.get("branch"):
            truth[key] = {stem_korean(p["stem"]) + branch_korean(p["branch"]),
                          p["stem"] + p["branch"]}
    # ① 산문형
    for m in _PROSE_FOUR_RE.finditer(answer):
        if any(k in answer[max(0, m.start() - 12): m.start()] for k in _PROSE_SKIP_LEFT):
            continue
        for gi, key in ((1, "year"), (2, "month"), (3, "day"), (4, "hour")):
            g = m.group(gi)
            allow = truth.get(key)
            if g and allow and g not in allow:
                return [("명식 통짜 서술", m.group(0).strip(),
                         " ".join(f"{sorted(truth[k])[0]}{s}" for k, s in
                                  (("year", "년"), ("month", "월"), ("day", "일"), ("hour", "시"))
                                  if k in truth))]
    # ② 표/그리드형 — 표 방향(년→시 / 시→년)이 자료마다 달라 순서 대신 다중집합으로 대조하고,
    #    '시주 미상'으로 3칸만 적는 정상 표를 살리려 부분집합(claimed ⊆ truth)으로 판정한다.
    #    타인 명식이면 천간 10·지지 12 조합상 부분집합이 성립할 확률이 사실상 없다.
    from collections import Counter
    want_st, want_br = Counter(), Counter()
    for p in pil.values():
        if not isinstance(p, dict):
            continue        # 시주 미상이면 pillars.hour = None (실측 크래시 — 368건 중 다수)
        if p.get("stem"):
            want_st[p["stem"]] += 1
        if p.get("branch"):
            want_br[p["branch"]] += 1
    for st, br in _grid_pillars(answer):
        if (Counter(st) - want_st) or (Counter(br) - want_br):
            return [("명식표(타인 명식 복사 의심)", "".join(st) + "/" + "".join(br),
                     "".join(want_st.elements()) + "/" + "".join(want_br.elements()))]
    return []


def _verify_myeongsik(answer: str, chart_json: dict | None) -> list[tuple[str, str, str]]:
    """단일 명식 일간(천간)+4주 지지+조후용신+간지오행+월운매핑 검증(사주 상담·작명 등). 빈 결과 = 일치."""
    return (
        _verify_branches(answer, _allowed_from_charts(chart_json))
        + _verify_pillar_ganji(answer, chart_json)
        + _verify_day_stem(answer, chart_json)
        + _verify_yongsin(answer, chart_json)
        + _verify_ganji_element(answer)
        + _verify_month_ganji(answer)
        + _verify_year_ganji(answer)
        + _verify_gongmang(answer, chart_json)
        + _verify_pillar_stems(answer, chart_json)     # [P2-2] 년간·월간·시간 오식
        + _verify_twelve_life(answer, chart_json)      # [P2-5] 십이운성 자리 뒤바꿈
        + _verify_whole_chart(answer, chart_json)      # [P2-3] 4주 통짜 서술·표 복사
        + _verify_daewoon(answer, chart_json)          # 대운 간지 환각(게이트-교정기 정합화)
        + _verify_daewoon_direction(answer, chart_json)
        + _verify_daewoon_age_range(answer, chart_json)
        + _verify_current_daewoon(answer, chart_json)
        + _verify_future_daewoon(answer, chart_json)       # [Patch G] 과거 대운을 내년 대운으로 오인 인용 차단
    )


# ---- 동문서답(질문 주제 이탈) 검출 — 원인 무관 출력측 백스톱 ----
# 실측(2026-07-25): 후속질문 '남자 술주정있을까요'에 '남자친구·연애운' 답변. route_topics()=[] 로 결정적
# 주제앵커가 없고, 이력(연애 발췌 ~157:1) + QUESTION_FOCUS_RULE 연애 예시가 약한 1차모델을 연애로 끌었다.
# 입력측 수정(라우팅 키워드·프롬프트)은 원리상 불완전(화이트리스트) → 출력측에서 '질문 핵심어가 답에
# 전무한가'로 최종 방어한다. 어떤 경로(라우팅 miss·이력 지배·RAG 편향)로 튀든 여기서 잡힌다.
# ⚠️ 오탐 극도 경계(P2-6 교훈: 오탐 재생성이 정답을 파괴한다). 아래 5조건을 모두 만족할 때만 플래그하고,
#    변형·동의어 매칭은 '넉넉하게'(=덜 플래그=안전 방향) 한다. 하나라도 어긋나면 무동작(정답 보존 우선).
_NONRESP_LOW_SALIENCE = {   # 사람·관계 지시어는 변별력 낮음('남자 술주정'의 핵심은 '술주정')
    "남자", "여자", "사람", "분", "이분", "그분", "본인", "자기", "자신", "그", "저", "우리", "저희",
    "남편", "아내", "부인", "신랑", "와이프", "배우자", "애인", "여친", "남친", "여자친구", "남자친구",
    "부모", "아버지", "어머니", "엄마", "아빠", "부친", "모친", "형제", "자매", "형", "누나", "동생",
    "오빠", "언니", "친구", "상대", "상대방",
}
_NONRESP_TAILS = (   # 의문·서술 꼬리(질문 토큰 끝에서 벗겨낼 어미) — 긴 것부터 반복 제거
    "있을까요", "없을까요", "있습니까", "없습니까", "있을까", "없을까", "있나요", "없나요", "있어요",
    "없어요", "있는지", "없는지", "심한가요", "심할까요", "강한가요", "약한가요", "좋을까요", "나쁠까요",
    "많을까요", "적을까요", "어떤가요", "어떨까요", "어떠한가", "어때요", "어떤지", "인가요", "일까요",
    "할까요", "될까요", "한가요", "은가요", "는가요", "센가요", "인지요", "하나요", "되나요", "습니까",
    "입니까", "였나요", "겠어요", "겠네요", "을까요", "나요", "가요", "까요", "어요", "아요", "여요",
    "해요", "네요", "군요", "인지", "는지", "은지", "을지", "인", "은", "는", "이", "가", "을", "를",
    "와", "과", "의", "도", "만", "에", "로", "으로", "편", "것", "거", "점", "요", "까", "죠", "임",
    "음", "함", "다",
)
_NONRESP_STOP = {   # 의문사/부사 — 핵심어 아님
    "언제", "어디", "어떻게", "무엇", "뭐", "왜", "얼마나", "몇", "몇월", "좀", "제발", "진짜", "정말",
    "혹시", "그냥", "많이", "자꾸", "계속", "앞으로", "요즘", "최근", "이번", "올해", "내년", "작년",
    "다시", "그리고", "근데", "그런데", "궁금", "궁금해요", "알려주세요", "봐주세요",
    "어때", "어떤", "어떨", "어떠", "같", "그런", "무슨", "어느",
}
_NONRESP_SYN_GROUPS = [   # 동의어/변형 — 답이 다른 낱말로 같은 주제를 다뤘을 때 오탐 방지(넉넉히)
    {"술주정", "주사", "술버릇", "음주", "술", "주정", "술고래"},
    {"바람기", "바람둥이", "외도", "바람", "불륜"},
    {"성격", "성향", "기질", "성정", "성품", "성질", "인품", "됨됨이", "품성", "성깔", "성미"},
    {"건강", "몸", "질병", "체질", "장부"},
    {"자녀", "자식", "아이", "출산", "임신"},
    {"직업", "직장", "커리어", "진로", "이직", "취업"},
    {"재물", "돈", "금전", "재산", "씀씀이", "낭비", "구두쇠", "인색"},
    {"폭력", "폭행", "때리", "손찌검", "다혈질"},
    {"거짓말", "허풍", "사기"},
    {"성실", "근면", "부지런"},
    {"게으", "나태", "게을"},
    {"고집", "고지식", "완고"},
    {"효자", "효녀", "효심"},
]


def _strip_q_tail(tok: str) -> str:
    """질문 토큰 끝의 의문·서술 어미를 반복 제거해 어간을 남긴다. '술주정있을까요'→'술주정'."""
    tails = sorted(_NONRESP_TAILS, key=len, reverse=True)
    prev, cur = None, tok
    while cur != prev:
        prev = cur
        for suf in tails:
            if len(cur) > len(suf) and cur.endswith(suf):
                cur = cur[: -len(suf)]
                break
    return cur


def _question_salient_terms(question: str) -> list[str]:
    """질문의 '변별 핵심어'(구체 명사)만 추출. 사람·관계 지시어와 의문사는 제외.

    없으면 빈 리스트 → 동문서답 검출 자체를 건너뜀(안전). 변별어가 없고 관계어만 있으면 관계어로 폴백."""
    q = re.sub(r"[^가-힣0-9\s]", " ", question or "")
    distinctive: list[str] = []
    fallback: list[str] = []
    for raw in q.split():
        t = _strip_q_tail(raw)
        if len(t) < 2 or t in _NONRESP_STOP:
            continue
        (fallback if t in _NONRESP_LOW_SALIENCE else distinctive).append(t)
    seen: set[str] = set()
    return [t for t in (distinctive or fallback) if not (t in seen or seen.add(t))]


def _term_variants(t: str) -> set[str]:
    vs = {t}
    for grp in _NONRESP_SYN_GROUPS:
        if t in grp:
            vs |= grp
    if len(t) >= 3:
        vs.add(t[:2])   # 어간 2자 prefix(넉넉한 매칭 = 덜 플래그 = 안전)
    return {v for v in vs if len(v) >= 2}


def _answer_dominant_offtopic(answer: str, question: str) -> bool:
    """답변이 '질문이 안 물은' 라우팅 주제(연애·재물·직업 등)로 지배되어 있으면 True(이중 게이트)."""
    try:
        from backend.app.saju.gwanbeop import TOPIC_KEYWORDS, route_topics
    except Exception:  # noqa: BLE001
        return False
    asked = set(route_topics(question or ""))
    best_t, best_n = None, 0
    for t, kws in TOPIC_KEYWORDS.items():
        n = sum(1 for k in kws if k in answer)
        if n > best_n:
            best_t, best_n = t, n
    return best_t is not None and best_n >= 3 and best_t not in asked


def _verify_nonresponsive(answer: str, question: str) -> list[tuple[str, str, str]]:
    """동문서답(질문 핵심어를 답이 전혀 안 다룸) 검출. 빈 결과 = 정상. 고정밀·저오탐."""
    ans = (answer or "").strip()
    # 짧은 답/명료화(되묻기)는 면제하되, 3문장급(≈80자+) 드리프트는 잡는다. 오탐 방지는 아래 이중
    # 게이트(_answer_dominant_offtopic: 다른 라우팅 주제 ≥3히트)가 담당하므로 여기 임계는 낮게 둔다.
    if len(ans) < 80:
        return []
    if _wants_comprehensive(question or ""):    # 종합·시점 요청은 집중 대상 아님
        return []
    terms = _question_salient_terms(question or "")
    if not terms:
        return []
    for t in terms:                             # 핵심어·변형·동의어가 하나라도 있으면 응답으로 간주
        for v in _term_variants(t):
            if v in ans:
                return []
    if not _answer_dominant_offtopic(ans, question or ""):   # 이중 게이트
        return []
    return [("동문서답(질문 주제 이탈)", terms[0], "질문 핵심어가 답변에 전무")]


def _correct_nonresponsive(answer: str, question: str, *, sys_content: str,
                           saju_summary: str | None, chart_json: dict | None) -> str:
    """동문서답이면 '질문 핵심어에 정면으로 답하라' 지시로 1회 재생성. 실패 시 원본 보존(로그만, 본문 무해)."""
    bad = _verify_nonresponsive(answer, question)
    if not bad:
        return answer
    term = bad[0][1]
    base_user = _build_user_prompt(question, [], saju_summary, chart_json=chart_json)  # 자료 제외(오염 차단)
    # [2026-07-28] 종전 지시 '결론부터 짧고 명료하게'가 긴 유료 답변을 짧은 재생성본으로 통째 교체하는
    # 최대 삭감 누수였다(운영자 지적 #7). 긴 원본은 '분량·깊이 유지, 주제만 재정렬'로 지시해 삭감을 막는다.
    _rich = len(answer) >= 500
    _len_instr = (
        "원래 답변의 분량과 깊이는 그대로 유지하세요 — 요약·축약하지 말고, 근거(명식·세운·월운)를 "
        "원래만큼 충분히 제시하되 초점만 '{t}'로 바로잡으세요.".format(t=term)
        if _rich else
        "결론부터 명료하게 답하세요."
    )
    focus = (
        f"\n\n[직전 답변 — 주제 이탈, 교정 대상]\n{answer}\n\n"
        f"[교정 지시 — 중요] 위 답변은 '지금 질문'이 실제로 물은 '{term}'에 대해 답하지 않고 다른 주제로 "
        f"흘렀습니다(동문서답). '{term}'을(를) 명식([십성·육친]·오행)·세운·월운 근거로 정면으로 다시 "
        f"답하세요. 답변 안에 '{term}'을(를) 반드시 다루고, 질문에 없는 다른 주제(연애·재물·직업 등)로 "
        f"새지 마세요. {_len_instr}"
    )
    try:
        new = _call_ollama(
            [{"role": "system", "content": sys_content},
             {"role": "user", "content": base_user + focus}],
            num_predict=max(1024, min(5120, len(answer) + 768)),  # 3,500자 답변 교정 잘림 방지(4096→5120)
        )
    except Exception:  # noqa: BLE001
        return answer
    cand = (new or "").strip()
    if len(cand) < 80:                          # 잘린/과단축 재생성본 거부
        return answer
    if _verify_nonresponsive(cand, question):   # 재생성도 여전히 동문서답 → 원본 보존 + 로그
        logging.getLogger("saju.chat").warning(
            "nonresponsive uncorrected: term=%s q=%r", term, (question or "")[:50])
        return answer
    # 유료 답변 급삭감 방지 — 긴 원본을 크게 줄이거나 잘린 재생성본은 거부하고 원본 보존.
    #   0.7 기준은 유지(주제 재정렬은 드리프트 제거로 다소 짧아지는 게 정당 — test_content_shrink_gate).
    #   [2026-07-29 전수감사 P2] 잘림(_looks_truncated) 검사를 추가 — 길이만 넘고 문장 중간에 끊긴
    #   재생성본이 채택되던 갭을 막는다(_correct_branches 와 동일한 잘림 방어를 nonresponsive 에도 통일).
    if len(answer) >= 500 and (len(cand) < int(len(answer) * 0.7) or _looks_truncated(cand)):
        logging.getLogger("saju.chat").warning(
            "nonresponsive correction rejected (shrink/trunc %d→%d, term=%s)", len(answer), len(cand), term)
        return answer
    return cand


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
        # 나이구간·현재대운 명시(케이스 #6·#7 교정 강화)
        ranges = _daewoon_ranges(chart_json)
        if ranges:
            rng_s = "·".join(
                f"{s}~{end}세 {ko}" if end is not None else f"{s}세~ {ko}"
                for (s, end, ko, _han) in ranges
            )
            out.append("대운나이구간=" + rng_s)
            bd = _chart_birth_date(chart_json)
            if bd:
                from datetime import date as _date
                age = (_date.today() - bd).days / 365.25
                cur = next((r for r in reversed(ranges) if r[0] <= age), ranges[0])
                crng = f"{cur[0]}~{cur[1]}세" if cur[1] is not None else f"{cur[0]}세~"
                out.append(f"현재대운={cur[2]}({crng})")
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
        f"[중대 오류 정정 — 최우선] 위 [직전 답변 — 교정 대상]에서 {wrongs} 잘못 적었습니다. "
        f"실제 명식 기준값은 정확히 다음과 같습니다: {truth}. "
        f"[참고자료]의 다른 예시 명식·간지·용신은 절대 쓰지 말고, 위 실제 값만 사용하세요. "
        f"[직전 답변]의 '### 소제목'·'**굵게**'·불릿 구조와 문단 순서·분량은 그대로 유지한 채, "
        f"잘못 적힌 간지 표기와 그 간지에 직접 기댄 해석 문장만 바로잡아 전체 본문을 처음부터 끝까지 "
        f"다시 출력하세요. [직전 답변]의 틀린 간지를 그대로 베끼지 말고, 새 주제 추가나 구조 변경도 하지 마세요."
    )


def _correct_branches(
    answer: str, *, allowed: dict[str, set[str]], truth: str, question: str,
    sys_content: str, saju_summary: str | None, max_tries: int = 1, exclude_date_ctx: bool = False,
    chart_json: dict | None = None, day_stems: set[str] | None = None,
    compat_charts: tuple[dict | None, dict | None] | None = None,
    extra_verifiers: "list | None" = None,
    initial_bad: "list[tuple[str, str, str]] | None" = None,
) -> str:
    """불일치 시 참고자료 없는 깨끗한 컨텍스트로 교정 재생성(≤max_tries) + 최종 명식헤더 백스톱.

    chart_json을 주면 4주 지지뿐 아니라 일간(천간) 불일치도 함께 검증·교정한다.
    day_stems(궁합 등 다중 명식)를 주면 두 사람 일간 union으로 검증한다.
    compat_charts=(a_cj,b_cj)를 주면 궁합 관계 라벨(육합/삼합/충)도 재검증한다.

    [대기시간 — 운영자 승인 2026-07-16] max_tries 기본 2→1: 재생성은 비스트리밍 전체 LLM 호출이라
    긴 답변(월별 포함)에서 회당 1~3분 — '확인하는 중' 장기대기의 진범이었다(검증 배터리는 ms).
    1회로 못 잡으면 즉시 결정적 백스톱(정확한 명식 헤더 강제)으로 마감해 정확도는 유지.
    initial_bad: 게이트(_verify_myeongsik 등)가 이미 계산한 불일치 목록 — 주면 진입 직후
    동일 배터리 중복 재실행을 건너뛴다(같은 텍스트를 두 번 검사하던 실측 중복 제거).
    """
    def _bad(txt: str) -> list[tuple[str, str, str]]:
        b = _verify_branches(txt, allowed, exclude_date_ctx=exclude_date_ctx)
        b = b + _verify_ganji_element(txt)  # 간지→오행 속성 환각(명식 불요·전 메뉴)
        b = b + _verify_month_ganji(txt)    # 월번호↔간지 밀림 환각(케이스 #5, 명식 불요)
        b = b + _verify_year_ganji(txt)     # 특정연도↔세운 간지(P1, 명식 불요)
        if chart_json is not None:
            b = (b + _verify_pillar_ganji(txt, chart_json) + _verify_day_stem(txt, chart_json)
                 + _verify_yongsin(txt, chart_json) + _verify_daewoon(txt, chart_json)
                 + _verify_daewoon_age_range(txt, chart_json) + _verify_current_daewoon(txt, chart_json)
                 + _verify_gongmang(txt, chart_json) + _verify_daewoon_direction(txt, chart_json)
                 + _verify_pillar_stems(txt, chart_json)      # [P2-2]
                 + _verify_twelve_life(txt, chart_json)       # [P2-5]
                 + _verify_whole_chart(txt, chart_json)       # [P2-3]
                 + _verify_future_daewoon(txt, chart_json))       # [Patch G] 과거 대운 오인 차단
        if day_stems:
            b = b + _verify_day_stem_multi(txt, day_stems)
        if compat_charts:
            b = b + _verify_compat_relations(txt, compat_charts[0], compat_charts[1])
        for vf in (extra_verifiers or []):   # 메뉴별 검증기(택일 황도·개명 수리 등) 주입
            b = b + vf(txt)
        return b

    bad = initial_bad if initial_bad is not None else _bad(answer)
    if not bad:
        return answer
    cur = answer
    base_user = _build_user_prompt(question, [], saju_summary, chart_json=chart_json)  # 참고자료 제외(오염 차단)
    # [운영자 결정 2026-07-27] 교정 재생성이 내용을 최대 40% 삭감하던 문제(min_ratio 0.6) 대응:
    #   ① 게이트를 0.85 로 조여 '분량 그대로 유지' 지시를 안 지킨 과단축 교정본은 거부한다.
    #   ② 거부 시 즉시 포기(원본=틀린 간지 유지)하지 말고, '절대 줄이지 말라' 강화 지시로 한 번 더
    #      재생성해 '내용 온전 + 간지 정확' 둘 다를 노린다. 그래도 안 되면 그때 백스톱.
    strengthened = False
    tries_left = max_tries
    while tries_left > 0:
        tries_left -= 1
        cp = _correction_prompt(bad, truth)
        if strengthened:
            cp += ("\n[분량 절대 유지 — 재강조] 앞서 답변이 짧아졌습니다. 위 [직전 답변]의 모든 문단·"
                   "소제목·월별 서술을 하나도 빼지 말고 그대로 유지한 채, 틀린 간지 표기와 그에 직접 "
                   "기댄 문장만 바로잡아 **전체를 처음부터 끝까지 빠짐없이** 다시 출력하세요. 요약·축약 금지.")
        msgs = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": base_user + "\n\n[직전 답변 — 교정 대상]\n" + cur + "\n\n" + cp},
        ]
        try:
            # 교정 재생성 상한 — 타임아웃과 잘림 사이 균형: 답변 길이 기반 동적 + 5120 캡.
            # 고정 2048은 신년운세 등 장문(4천자+)을 교정하며 중간 절단(실측 2026-07-21).
            # [2026-07-31] 본문 3,500자 확대로 4096(≈3,600자)은 장문 교정 시 근접 절단 → 5120(≈4,500자)로
            #   상향(68tok/s 기준 ~75s, 180s 타임아웃 안). 5120 초과는 느린 생성 시 타임아웃 위험이라 금지.
            # 궁합·택일/작명 교정도 이 경로 공유 — 2048 미만으로 줄이지 말 것(장문 잘림).
            new = _call_ollama(msgs, num_predict=max(2048, min(5120, len(cur) + 768)))
        except Exception:  # noqa: BLE001
            break
        if not (new and new.strip()):
            break
        _cand = _safe_replace(cur, new.strip(), min_ratio=0.85, hard_floor=True)
        if not _cand:      # 잘린 모양/과단축 재생성본 — 한 번은 '줄이지 마' 강화 재시도, 그래도면 원본 유지
            if not strengthened:
                strengthened = True
                tries_left += 1     # 강화 재시도 1회 보장(정상 재시도 예산과 별도)
                continue
            break
        if _cand == cur:   # [P2-6] 무변화 재생성 — 같은 지시로 또 돌려도 결과가 같다(실측 헛돎 1~3분)
            break
        cur = _cand
        prev_bad = bad
        bad = _bad(cur)
        if not bad:
            return cur
        if bad == prev_bad:   # [P2-6] 불일치 목록이 그대로 → 교정 불능. 재시도 대신 즉시 마감.
            break
    if bad:
        # [2026-07-21 운영자 지적] 과거의 "※ 정확한 명식 지지/월별 간지" 백스톱 헤더는 내부
        # 진실값(대운목록 등)을 고객 본문·PDF에 그대로 노출해 신뢰를 깎았다 → 제거.
        # 미해소 불일치는 관리자 로그로만 남긴다(F1 오탐 가드 후 잔존 flag는 진성 오류만).
        # [P2-7] 그 답변에 실렸던 참고자료 출처를 함께 남긴다 — 계산값과 자료가 충돌할 때
        # 어느 문서가 오염원인지 역추적할 수 있어야 코퍼스를 고칠 수 있다(로그만, 본문 불변).
        logging.getLogger("saju.chat").warning(
            "myeongsik gate unresolved after retry: %s | rag=%s", bad, _rag_trace())
    return cur


def _correct_chart(
    answer: str, chart_json: dict | None, *, question: str, sys_content: str,
    saju_summary: str | None, max_tries: int = 1,
    initial_bad: "list[tuple[str, str, str]] | None" = None,
) -> str:
    """단일 명식(사주 상담·작명 등) 교정 래퍼 — 4주 지지 + 일간(천간) 검증·교정.

    initial_bad: 게이트 _verify_myeongsik 결과를 그대로 전달하면 진입 직후 중복 검증 생략
    (게이트와 _bad 배터리는 단일 명식 경로에서 동일 구성)."""
    return _correct_branches(
        answer, allowed=_allowed_from_charts(chart_json), truth=_myeongsik_truth(chart_json),
        question=question, sys_content=sys_content, saju_summary=saju_summary, max_tries=max_tries,
        chart_json=chart_json, initial_bad=initial_bad,
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
    # [운영자 지적 2026-08-03] 출처 라벨·책·페이지 앵무새 차단
    #   ('자료1 및 명리전2권 p. 358 등 여러 자료들을 종합하면,' → 전부 제거).
    r"여러\s*자료(들)?(을|를)?\s*종합\S*[,·]?\s*",
    r"[가-힣]{2,12}\s*\d+\s*권\s*(?:p\.?\s*|페이지\s*|쪽\s*)\d+\s*(?:등|참고|참조)?[,·]?\s*",
    r"자료\s*\d+\s*(?:및|과|와|,|·)?\s*",
    r"예시처럼\s*",   # 프롬프트 예시 누출('예시처럼 …와 같이')
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


# 마크다운 구분선(---/***/___)만 있는 줄 — 프롬프트로 금지해도 약한 LLM이 간헐 출력하면
# 화면에 기호가 그대로 노출된다. 재생성(보강/교정)에 의존하지 않고 결정적으로 제거한다
# (형식 정리를 '내용 변경 재생성'과 분리 — 운영자 지적 2026-07-27: 정리하다 내용이 삭감됨).
# ⚠️ 표 구분선(|---|)은 건드리지 않는다 — '|' 없는 순수 구분선 줄만.
_HR_LINE_RE = re.compile(r"^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$", re.M)


def _tidy_markdown(text: str) -> str:
    """표시용 형식 정리(내용 무손실): 구분선 줄 제거 + 과다 빈줄 축약. 글자(내용)는 절대 지우지 않는다."""
    if not text:
        return text
    out = _HR_LINE_RE.sub("", text)          # '---' 단독 줄 → 삭제(표 |---| 는 '|'가 있어 미매칭)
    # 헤딩 '#' 뒤 공백 보장(무손실) — '####9월' → '#### 9월'. 공백 없으면 프론트/표준 마크다운이
    # 헤더로 인식 못 해 '####'가 날것으로 노출된다(실측 2026-07-28). 레벨(#개수)은 보존한다.
    out = re.sub(r"(?m)^([ \t]*#{1,6})(?=[^\s#])", r"\1 ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)      # 3줄+ 빈줄 → 1빈줄
    return out.strip()


# 월별 흐름의 월운 간지를 '을미년'으로 오표기 → '을미월'로 교정(실측). 'N월 (간지년)'처럼 월 헤딩 안의
# 간지가 '년'으로 붙은 경우만(월 헤딩 안의 년-표기 간지는 항상 월운 오표기라 오탐 없음).
_MONTH_LABEL_RE = re.compile(
    r"(\d{1,2}\s*월\s*[\(（:·]?\s*)"      # 'N월' 직후(공백·괄호·콜론만 허용 — 정상 문장 오탐 차단)
    r"([갑을병정무기경신임계][자축인묘진사오미신유술해]|[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])"
    r"\s*년"
)


def _fix_month_ganji_label(text: str) -> str:
    """'7월 (을미년)' → '7월 (을미월)'. 월 헤딩 직후 간지+년을 월로 결정적 교정."""
    if not text:
        return text
    return _MONTH_LABEL_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}월", text)


# '내년 (올해, 2027년)'처럼 내년 옆에 모순되게 '올해'를 붙이는 오표기 → '내년 (2027년)'. Patch B로 막아도
# 약한 LLM이 헤딩에서 재발(실측). 연도는 보존하고 모순된 '올해'만 제거.
_REL_YEAR_CONFLATE_RE = re.compile(r"(내년|명년|후년|내후년)(\s*[\(（]\s*)올해[,，\s]*(\d{4}\s*년?)")


def _fix_relative_year_conflation(text: str) -> str:
    """'내년 (올해, 2027년)' → '내년 (2027년)'. 상대연도어에 모순 붙은 '올해' 제거(연도 보존)."""
    if not text:
        return text
    return _REL_YEAR_CONFLATE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}", text)


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


def _year_ganzhi_ko(year: int) -> str:
    """해당 연도의 세운 간지(한글, 예: 2023->'계묘'). 엔진 계산과 일치."""
    return _year_ko_hj(year)[0]


# 간지 한글(예 '계묘') → 서기연도. 60갑자 주기라 한 간지는 60년마다 반복하므로 anchor 기준 방향을 정한다.
# Track A(회고): 과거 질문이므로 anchor(올해) 이하에서 가장 가까운 해로 결정(미래 오매핑 원천 차단).
def _ganzhi_to_year(ganzhi_ko: str, anchor_year: int, direction: str = "past") -> int | None:
    """간지 한글 → 서기연도. direction='past'면 anchor 이하 최근값, 'future'면 anchor 이상 최근값.

    ★ 미래 방향(direction='future')은 '남자 만날 시기'류 발현연도 스캔에 필요하며 관법 판단이 얽혀
      뽀 감수 대상 — Track A(회고)에서는 'past'만 사용한다.
    """
    if not ganzhi_ko:
        return None
    rng = (range(anchor_year, anchor_year - 60, -1) if direction == "past"
           else range(anchor_year, anchor_year + 60))
    for y in rng:
        try:
            if _year_ganzhi_ko(y) == ganzhi_ko:
                return y
        except Exception:  # noqa: BLE001
            continue
    return None


def _allowed_year_ganji(extra_years: "list[int] | None" = None) -> set[str]:
    """올해·내년의 실제 세운 간지(한글). 예: {'병오', '정미'}.

    extra_years: 질문자가 명시한 회고 대상 연도(들). 주어지면 그 해 세운 간지도 허용집합에 포함해
    scrub이 파괴하지 않게 한다(회고 질문 한정)."""
    from datetime import date as _d
    y = _d.today().year
    out: set[str] = set()
    for yr in (y, y + 1):
        try:
            out.add(_year_ko_hj(yr)[0])
        except Exception:  # noqa: BLE001
            pass
    for yr in (extra_years or []):
        try:
            out.add(_year_ganzhi_ko(yr))
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
        cur = m.group(3)
        # 기존 괄호 한자가 '천간자+지지자' 조합이 아니면(예: 십성 正印·正財) 간지가 아니므로 불개입.
        #   버그: 십성 '정인(正印)'의 한글 '정인'이 간지 독음 정인(丁寅=丁+寅)과 겹쳐, 한자를 丁寅으로
        #   오교정했다(월 헤더 '월지 정인(正印)' → '정인(丁寅)'). 괄호 한자까지 간지꼴일 때만 표준화한다.
        if not (len(cur) == 2 and cur[0] in HEAVENLY_STEMS and cur[1] in EARTHLY_BRANCHES):
            return m.group(0)
        correct = _canon_ganji_hanja(m.group(1), m.group(2))
        if correct and cur != correct:
            return f"{m.group(1)}{m.group(2)}({correct})"
        return m.group(0)
    return _GANJI_HJ_PAREN_RE.sub(_sub, text)


# 도입부 인사말/예고 문장 결정적 제거 — 로컬(qwen3:14b)·Claude 어느 모델이 붙여도 '판정부터'를 보장.
# 매우 보수적: 첫 문장이 (예고 동사=살펴/분석/풀어/정리 등) + '~겠습니다/게요'로 끝나고, 뒤에 실질 내용이
# 충분할 때만 그 첫 문장을 제거. 실제 판정문('~입니다/~유리합니다')·조언('~좋겠습니다')은 예고동사가 없어 보존.
_LEAD_META_VERB = re.compile(r"(살펴|들여다|분석|풀어|풀이|알아|짚어|말씀|설명|안내|정리|봐\s*드리|시작하)")
_LEAD_END = re.compile(r"(?:겠습니다|겠어요|볼게요|드릴게요|ㄹ게요|게요)\s*[.。!]?\s*$")


def _strip_lead_filler(text: str) -> str:
    """맨 앞 인사말/예고 문장(내용 없는 도입)만 결정적으로 제거해 '판정부터' 시작하게 한다."""
    if not text:
        return text
    t = text.lstrip()
    m = re.match(r"([^\n]{0,120}?[다요][.。!]?)(?:\s+)(.+)", t, re.S)
    if not m:
        return text
    first, rest = m.group(1).strip(), m.group(2).strip()
    if len(first) <= 100 and len(rest) >= 40 and _LEAD_END.search(first) and _LEAD_META_VERB.search(first):
        return rest
    return text


def _scrub_stale_year_ganji(text: str, allowed_years: "list[int] | None" = None) -> str:
    """과거연도·틀린 세운 간지를 '올해'로 중화(결정적). 올해/내년 실제 간지·한자는 보존.

    allowed_years: 질문자가 명시적으로 물은 회고 대상 연도(들). 주어지면 그 해의 세운 간지와
    4자리 연도는 중화하지 않고 보존한다(회고 답변 파괴 방지). 비회고 질문에선 None → 종전과 동일.
    """
    if not text:
        return text
    from datetime import date as _d
    cur = _d.today().year
    retro = {int(y) for y in (allowed_years or [])}
    allowed = _allowed_year_ganji(list(retro))
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
    # 2) 과거 4자리 연도(YYYY년, 올해 미만) → '올해'. 단, 질문자가 명시한 회고 대상 연도는 보존.
    out = re.sub(
        r"(?:19|20)\d{2}\s*년",
        lambda m: (m.group(0) if (int(re.sub(r"\D", "", m.group(0))) in retro
                                  or int(re.sub(r"\D", "", m.group(0))) >= cur) else "올해"),
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


# ── 신년운세 세운 간지 교정 (#10) — '세운/올해/그해/{그 해}년'에 딸린 세운 간지 환각을 ──
#    그 해 실제 세운으로 결정적 교정. chat 의 _scrub_stale_year_ganji 는 today() 기준이라
#    신년운세(대상 연도 = result.year)에는 못 쓴다. '세운' 앵커 + 한자병기가 있을 때만 건드려
#    월운(월 간지)·명식 간지는 절대 손대지 않는다(실측 환각: 세운 병오를 '갑'으로 서술 #10).
_SINNYEON_GANJI = r"[갑을병정무기경신임계][자축인묘진사오미신유술해]"


# 월별 흐름 'N월 (XX월)'의 XX가 유효한 60갑자 한글 독음이 아니면(예: 乙未를 '을미' 아닌 '으미'로 환각)
# 그 달의 실제 월간지 독음으로 결정적 교정. 유효 간지(맞든 표밀림이든)는 _verify_month_ganji 관할이라 불개입.
_VALID_GANJI_KO = frozenset(STEM_KOREAN[i % 10] + BRANCH_KOREAN[i % 12] for i in range(60))
_MONTH_READING_RE = re.compile(r"([1-9]|1[0-2])(\s*월\s*[（(]\s*)([가-힣]{2})(\s*월\s*[)）])")
# 섹션 헤딩 한자 환각(영역별 심화 → 英域別深化 등)을 한글로 환원(프롬프트가 쓰는 고정 라벨만).
_HEADING_HANJA_FIX = {"英域別深化": "영역별 심화", "月別흐름": "월별 흐름", "總運": "총운"}


def _fix_sinnyeon_month_reading(text: str, year: int | None = None, today=None) -> str:
    """'N월 (XX월)'에서 XX가 유효 간지 독음이 아니면(예: 乙巳→'으사' 환각) 그 달 실제 월간지 독음으로 교정.

    year 주어지면(신년운세=연도 확정) 그 해 기준. 없으면(사주 상담 등) 문맥으로 추론 —
    과거 회고는 불개입, '내년'이면 +1, 그 외엔 올해(월별 흐름은 대개 올해 세운). 유효 간지(맞든 표밀림이든)는
    _verify_month_ganji 관할이라 불개입 — 여기선 '무효 독음'만 결정적 교정한다."""
    if not text:
        return text
    for wrong, right in _HEADING_HANJA_FIX.items():
        if wrong in text:
            text = text.replace(wrong, right)
    from datetime import date as _date
    from backend.app.saju.pillars import compute_pillars
    from backend.app.saju.constants import branch_korean, stem_korean
    from backend.app.saju.types import BirthInput as _BI, CalendarType as _CT
    _today = today or _date.today()

    def _sub(m: "re.Match") -> str:
        reading = m.group(3)
        if reading in _VALID_GANJI_KO:      # 유효 독음 → 불개입(매핑 밀림은 검증기 관할)
            return m.group(0)
        ctx = text[max(0, m.start() - 12): m.start()]
        if any(k in ctx for k in _MONTH_PAST_CTX):
            return m.group(0)               # 과거 회고 문맥은 불개입(오탐 방지)
        _naenyeon = "내년" in ctx or "명년" in ctx
        if year:
            if _naenyeon:
                return m.group(0)           # 연도확정(리포트)인데 '내년' 문맥 = 모순 → 안전하게 불개입
            _y = int(year)
        elif _naenyeon:
            _y = _today.year + 1            # 연도 미지정 + '내년' → +1년
        else:
            _y = _today.year                # 월별 흐름 기본=올해 세운
        try:
            fp, *_ = compute_pillars(_BI(birth_date=_date(_y, int(m.group(1)), 15), calendar=_CT.SOLAR))
        except Exception:  # noqa: BLE001
            return m.group(0)
        correct = f"{stem_korean(fp.month.stem)}{branch_korean(fp.month.branch)}"
        return f"{m.group(1)}{m.group(2)}{correct}{m.group(4)}"

    return _MONTH_READING_RE.sub(_sub, text)


def _fix_sinnyeon_seun_ganji(text: str, year: int) -> str:
    """신년운세 답변의 세운 간지 환각을 그 해 실제 세운(예: 2026→병오(丙午))으로 결정적 교정.

    안전장치: (a)'세운' 키워드 또는 (b)그 해 4자리 연도 또는 (c)'올해/금년/그해' 헤더에
    '직접 딸린' 간지 + 한자병기가 있을 때만 교정한다. 월운 간지(신묘월 등)·명식 간지·천간
    단독('세운 천간 병(丙)')은 앵커·형태가 달라 건드리지 않는다."""
    if not text or not year:
        return text
    try:
        ko, hj = _year_ko_hj(int(year))     # 2026 → ('병오','丙午')
    except Exception:  # noqa: BLE001
        return text
    correct = f"{ko}({hj})"
    G = _SINNYEON_GANJI
    # (a) '세운[조사] <간지>(한자)' — 세운 뒤 6자 이내(조사·공백만)에 온 완성 간지+한자병기
    text = re.sub(rf"(세운[은는이가의을를로며라고도만에서\s]{{0,6}}){G}\s*\(\s*[一-鿿]{{1,2}}\s*\)",
                  lambda m: m.group(1) + correct, text)
    # (b) '{그 해}년 [세운] <간지>(한자)'
    text = re.sub(rf"({year}\s*년\s*(?:세운[은는이가의\s]{{0,4}})?[\s(（]{{0,2}}){G}\s*\(\s*[一-鿿]{{1,2}}\s*\)",
                  lambda m: m.group(1) + correct, text)
    # (c) '올해/금년/그해 (<간지>[, 한자])' 헤더형
    text = re.sub(rf"(올해|금년|그해)\s*[\(（]\s*{G}\s*[,，·]?\s*[一-鿿]{{0,2}}\s*[\)）]",
                  lambda m: f"{m.group(1)} ({correct})", text)
    # (d) 남은 간지 한글-한자 불일치 최종 표준화(갑오(甲午) 등) — 월운 포함 항상 안전
    return _fix_ganji_hanja(text)


# ── 신분(학교급/직업) 추정 표현 결정적 제거 (전문가 지적 2026-07: '고등학생으로 추정' 금지) ──
_STATUS_WORDS = "고등학생|중학생|대학생|초등학생|직장인|취업준비생|수험생|재수생|사회초년생"
_STATUS_PRESUME_RE = re.compile(
    rf"(?:현재\s*)?(?:나이[가는이]?\s*)?(?:{_STATUS_WORDS})(?:으?로|이라고|일\s*것으로)?\s*추정\S*"
)


def _scrub_status_presumption(text: str) -> str:
    """'(현재 나이가) 고등학생으로 추정되므로' 같은 신분 단정·추정 표현을 결정적으로 제거.

    사주로는 사용자의 학교급·직업 신분을 알 수 없다(전문가 지적: '니가 무슨 추정을 하냐'). 나이대
    관심사 서술은 남기되, 특정 신분을 단정·추정하는 표현만 제거한다.
    """
    if not text:
        return text
    out = _STATUS_PRESUME_RE.sub("", text)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\s+([,.·])", r"\1", out)        # 제거로 생긴 ' ,' 정리
    out = re.sub(r"([,·])\s*(?=[,.])", "", out)     # 잔여 이중 구두점 정리
    return out


# ── AI 자기지칭 다짐 교정 (운영자 지적: '미래 창출에 앞서겠습니다!' — AI가 손님의 미래에 앞장선다?) ──
# 사주를 보고 미래를 만드는 주체는 '손님'인데, 약모델이 마무리에서 글쓴이(AI)를 주어로 '~하겠습니다'
# 다짐·약속조로 끝내는 환각. 명백한 경우만 결정적으로 손님을 향한 표현으로 교정한다(오탐 최소·보수적).
_SELF_REF_FIXES: list[tuple["re.Pattern[str]", str]] = [
    (re.compile(r"에\s*앞서겠습니다"), "에 앞장서 나아가시길 바랍니다"),
    (re.compile(r"앞장\s*서\s*나가겠습니다"), "앞장서 나아가시길 바랍니다"),
    (re.compile(r"앞장\s*서겠습니다"), "앞장서 나아가시길 바랍니다"),
    (re.compile(r"앞장서겠습니다"), "앞장서 나아가시길 바랍니다"),
    (re.compile(r"앞서겠습니다"), "앞장서 나아가시길 바랍니다"),
    (re.compile(r"(미래|삶|인생|길)(을|를)?\s*열어\s*가겠습니다"), r"\1\2 열어 가시길 바랍니다"),
    (re.compile(r"(미래|삶|인생|길)(을|를)?\s*만들어\s*가겠습니다"), r"\1\2 만들어 가시길 바랍니다"),
    (re.compile(r"(미래|삶|인생|길)(을|를)?\s*이끌어\s*가겠습니다"), r"\1\2 이끌어 가시길 바랍니다"),
]


def _scrub_self_reference(text: str) -> str:
    """AI가 손님의 미래·삶을 자기가 하겠다고 1인칭 다짐으로 끝맺는 환각을 손님 지향 표현으로 교정."""
    if not text:
        return text
    for pat, repl in _SELF_REF_FIXES:
        text = pat.sub(repl, text)
    return text


# ── 세운 간지를 '대운'이라 부른 오라벨 결정적 교정 (전문가 지적: '정미 대운' → '정미 세운') ──
def _fix_sewoon_daewoon_label(text: str, chart_json: dict | None) -> str:
    """답변의 '간지 대운'/'대운 (…간지…)'에서 그 간지가 대운 목록엔 없고 그 해(올해·내년·언급연도)의
    실제 세운이면 '대운'을 '세운'으로 결정적으로 바꾼다.

    실측: 내년 세운 정미(丁未)를 '내년 대운 (2027년 정미 대운)'으로 오라벨(대운·세운 혼동). 프롬프트로
    정확히 줘도 약한 모델이 혼동, _verify_daewoon이 잡아도 재생성이 못 고침 → 결정적 교정으로 마감.
    대운이기도 한 간지는 모호하므로 건드리지 않는다(오탐 0)."""
    if not text or not chart_json:
        return text
    allow = _daewoon_ganji_set(chart_json)  # 대운 간지(한글·한자)
    if not allow:
        return text
    from datetime import date as _d
    cur = _d.today().year
    years = {cur, cur + 1}
    for m in re.finditer(r"(?:19|20)\d{2}", text):
        years.add(int(m.group(0)))
    sewoon: set[str] = set()
    for y in years:
        try:
            sewoon.add(_year_ganzhi_ko(y))
        except Exception:  # noqa: BLE001
            pass
    sewoon -= allow  # 대운이기도 한 간지는 모호 → 교정 제외
    if not sewoon:
        return text
    gz = r"[갑을병정무기경신임계][자축인묘진사오미신유술해]"
    # 1) '정미 대운' → '정미 세운'
    text = re.sub(rf"({gz})(\s*)대운",
                  lambda m: (f"{m.group(1)}{m.group(2)}세운" if m.group(1) in sewoon else m.group(0)),
                  text)
    # 2) '대운 (2027년 정미…' 헤더형 → '세운 (2027년 정미…'
    text = re.sub(rf"대운(\s*[\(（][^)）]{{0,12}}?)({gz})",
                  lambda m: (f"세운{m.group(1)}{m.group(2)}" if m.group(2) in sewoon else m.group(0)),
                  text)
    return text


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
        if m.role == "assistant":
            # 저장본 재열람도 정리 체인(멱등) — 수정 전 저장된 답변의 '---'·오병기·중복 소급 정리.
            # 사용자 메시지(원문)는 절대 건드리지 않는다.
            content = fix_term_hanja(content)
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


def _search_corpus(query: str, k: int, *, session_id: str | None = None,
                   question: str | None = None, menu: str | None = None):
    """참고자료 검색(RAG). Qdrant 연결 실패 시 ServiceUnavailableError로 변환.

    검색을 수행하면 **항상** retrieval_logs에 best-effort 기록한다(실패해도 답변 흐름 무영향).

    [P3-D1 2026-07-22] 예전에는 `if question:` 이라 question 이 없으면 기록을 건너뛰었는데,
    프론트가 유료 본해설을 message="" 로 보내기 때문에(ExplainChat.tsx / CompatibilityPage.tsx)
    **정작 돈 받는 답변의 회수 품질만 통째로 미기록**이었다(tool 세션 327건 중 로그 19.9%,
    꿈해몽 0/29). 그 상태로는 쿼리를 고쳐도 좋아졌는지 확인할 수 없어 관측을 먼저 켠다.
    question 이 없으면 '[explain] {menu}' 태그로 남겨 본해설 경로임을 구분한다.
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
    _log_retrieval(session_id, question or f"[explain] {menu or '?'}", k, chunks, menu=menu)
    _LAST_CHUNKS.set([(c.source, c.chunk_id, round(c.score, 3)) for c in chunks])
    return chunks


def _retrieve_context(
    query: str, k: int, depth: str, *, session_id: str | None = None,
    question: str | None = None, menu: str | None = None
) -> list[RetrievedChunk]:
    """기본·심화 모두 색인(학습) 자료를 RAG로 활용한다.

    학습(색인)한 자료를 기본 답변에도 '즉시' 반영하기 위해 두 모드 모두 코퍼스를 검색한다.
    단, 기본(basic)은 Qdrant 장애 시 LLM 단독으로 graceful degrade 하여 빠르고 안정적인
    기본 응답을 보존하고, 심화(deep)는 RAG 품질을 보장하므로 장애 시 예외를 그대로 올린다.
    """
    if depth == "deep":
        return _search_corpus(query, k, session_id=session_id, question=question, menu=menu)
    try:
        return _search_corpus(query, k, session_id=session_id, question=question, menu=menu)
    except ServiceUnavailableError:
        return []


# ── 도구 메뉴(궁합·택일·작명) 공용: 사주와 동일한 내부 RAG·외부 폴백 구조 제공 ──
def retrieve_for_menu(
    query: str, depth: str, *, session_id: str | None = None,
    question: str | None = None, menu: str | None = None
) -> list[RetrievedChunk]:
    """궁합·택일·작명 공용 RAG. 기본·심화 모두 학습 코퍼스를 활용(기본은 장애 시 degrade).

    menu: 회수 로그의 메뉴 태그(P3-D1). 세션이 지워져도 메뉴별 품질을 추적할 수 있게 한다."""
    s = get_settings()
    k = max(1, min(s.rag_top_k_default, s.rag_max_top_k))
    return _retrieve_context(query, k, depth, session_id=session_id, question=question, menu=menu)


# ── 관계 표를 '읽으면 그대로 쓸 수 있는 쉬운 문장'으로 ──────────────────────
# 운영자 실측(2026-07-22): 답변이 "세운 지지 오(午)는 당신의 년지(초년·조상궁) 묘(卯)와 월지
# (사회·직장궁) 묘(卯)를 파(破)로, 일지(배우자·가정궁) 인(寅)…을 반합(半合)으로 연결합니다"
# 처럼 나온다. 이건 모델이 지어낸 게 아니라 **브리핑 표 문자열을 충실히 옮긴 것**이다
# (luck_natal_relations 출력이 정확히 그 모양). 즉 난해함의 출처는 자료 자체다.
# → 표를 만들 때부터 쉬운 문장으로 준다. 간지 병기는 남겨 근거·검증 여지를 유지한다.
_REL_PLAIN = {
    "합": "서로 잘 맞아 끌어당깁니다", "육합": "서로 잘 맞아 끌어당깁니다",
    "삼합": "힘이 크게 모입니다", "반합": "부분적으로 힘이 모입니다",
    "방합": "같은 방향으로 힘이 모입니다",
    "충": "부딪혀 흔들립니다", "형": "마찰·시비가 생기기 쉽습니다",
    "파": "어긋나 깨지기 쉽습니다", "해": "서로 손해를 보기 쉽습니다",
    "원진": "까닭 없이 불편해집니다", "귀문": "신경이 예민해지기 쉽습니다",
}
_PALACE_PLAIN = {
    "년지(초년·조상궁)": "어린 시절·집안 자리", "월지(사회·직장궁)": "사회·직장 자리",
    "일지(배우자·가정궁)": "배우자·가정 자리", "시지(자녀·말년궁)": "자녀·노년 자리",
    "일간": "나 자신",
}
_SCOPE_PLAIN = {"세운 지지": "올해 기운", "세운 천간": "올해 기운",
                "월운 지지": "이 달 기운", "월운 천간": "이 달 기운",
                "오늘 지지": "오늘 기운", "오늘 천간": "오늘 기운",
                "대운 지지": "지금 대운 기운", "대운 천간": "지금 대운 기운"}
_REL_LINE_RE = re.compile(
    r"^(?P<scope>\S+ (?:지지|천간)) (?P<lk>[가-힣])\((?P<lh>[一-鿿])\)"
    r"↔내 (?P<pal>\S+) (?P<rk>[가-힣])\((?P<rh>[一-鿿])\) (?P<rel>\S+)$")


def plain_relation(line: str, *, with_scope: bool = True) -> str:
    """'세운 지지 오(午)↔내 월지(사회·직장궁) 인(寅) 반합'
    → '올해 기운 오(午)가 사회·직장 자리 인(寅)과 부분적으로 힘이 모입니다 [반합]'."""
    m = _REL_LINE_RE.match((line or "").strip())
    if not m:
        return line
    scope = _SCOPE_PLAIN.get(m.group("scope"), m.group("scope"))
    palace = _PALACE_PLAIN.get(m.group("pal"), m.group("pal"))
    rel = m.group("rel")
    plain = _REL_PLAIN.get(rel)
    if not plain:
        return line                       # 모르는 관계어는 손대지 않는다
    lk, lh, rk, rh = m.group("lk"), m.group("lh"), m.group("rk"), m.group("rh")
    has_batchim = lambda ch: bool((ord(ch) - 0xAC00) % 28)   # 받침 유무로 조사 선택
    subj = "이" if has_batchim(lk) else "가"
    with_ = "과" if has_batchim(rk) else "와"
    head = f"{scope} {lk}({lh})" if with_scope else f"{lk}({lh})"
    return f"{head}{subj} {palace} {rk}({rh}){with_} {plain} [{rel}]"


def plain_relations(lines: list[str], *, with_scope: bool = True) -> list[str]:
    """월별처럼 소제목이 이미 달을 말해 주는 자리에서는 with_scope=False 로 접두를 뺀다
    (12개월×여러 관계면 접두 반복이 브리핑을 비대하게 만든다)."""
    return [plain_relation(x, with_scope=with_scope) for x in (lines or [])]


# ── 자료 우선 규칙(P1) — '무엇이 우선인가'를 층으로 갈라 명문화 ────────────────
# [RAG 전수감사 2026-07-22] 운영자 요구는 'RAG 우선'인데, 프롬프트에서 '참고자료'가 나오는
# 곳은 전부 금지·격하 문맥이었고 우선 지침은 한 줄도 없었다(꿈해몽 한 줄뿐, 그 메뉴는 회수 0건).
# 그 결과 해석층은 규칙도 검증도 없이 '자료가 지배'하는 창발 상태였다 — 코퍼스에 뭐가 있든
# 그대로 사실이 되고, 그게 남의 상담문이어도 마찬가지였다.
# → 사실(값으로 제공된 계산값)은 계산값 절대우위, 해석·관법·시기론은 자료 우위로 못박는다.
# ⛔⛔ 승인 없이 수정 금지 — 이 규칙은 P0(예시명식 재태깅·게이트 정합화) 완료를 **전제**한다 ⛔⛔
#   오염된 코퍼스에서 이걸 켜면 남의 사주가 그대로 사실이 된다. 게이트를 완화하면서 이 규칙만
#   남겨 두는 조합이 가장 위험하다 — 둘은 한 세트다.
#   또한 이 문구는 rag_context_block() 이 **자료가 있을 때만** 붙인다. 0건일 때도 붙게 바꾸면
#   '없는 자료를 따르라'는 유령 지시가 되어 모델이 문헌명을 지어낸다(꿈해몽 실측 2건).
#   관련: docs/rag_hallucination_audit_2026-07-22.md 2장
#   테스트: backend/tests/test_p1_evidence_priority.py, test_p3_rag_coverage.py
EVIDENCE_PRIORITY_RULE = (
    "[자료 우선 — 해석층] 위 [참고자료]는 감수를 거친 선생님 자료입니다. "
    "해석·관법·통변·시기 판단이 자료와 당신의 일반 지식이 다르면 반드시 **자료를 따르세요**. "
    "단 간지·십성·용신·대운·오행 분포처럼 위 [사주명식]에 **값으로 제공된 것**은 자료가 다르게 "
    "말해도 절대 바꾸지 마세요 — 사실은 계산값, 해석은 자료입니다. "
    "자료가 특정인의 사주 사례라면 그 사람 전용 판정(예: '정유년에 이사하면 잘된다')을 이 사람에게 "
    "그대로 옮기지 말고, 그 판정이 성립한 **원리만** 가져와 이 명식에 맞게 다시 판단하세요."
)


def chart_reconfirm_block(chart_json: dict | None) -> str | None:
    """[명식 재확인] 가드 — chat 에만 있던 것을 tool·compat 이 함께 쓰도록 공용화(P1-4).

    [RAG 전수감사] 신년운세는 RAG 가 사용자 프롬프트의 38~40%, 무료 메뉴(오늘·개명·부적)는
    84~86%를 차지하는데 이 가드가 없었다. 자료에 남의 명식이 섞여 오면 막을 장치가 없다.
    """
    p = ((chart_json or {}).get("pillars") or {})
    gz = []
    for label, key in (("년주", "year"), ("월주", "month"), ("일주", "day"), ("시주", "hour")):
        c = p.get(key) or {}
        if c.get("stem") and c.get("branch"):
            gz.append(f"{label} {c['stem']}{c['branch']}")
    if not gz:
        return None
    return ("[명식 재확인] 본인 명식은 '" + ", ".join(gz) + "' 뿐입니다. "
            "위 참고자료에 다른 사람의 명식·간지가 있어도 쓰지 말고, "
            "답변의 모든 지지·천간을 이 명식과 일치시키세요.")


def rag_context_block(chunks: list[RetrievedChunk]) -> str | None:
    """검색 결과를 프롬프트용 [참고자료] 블록 문자열로 변환. 없으면 None.

    블록 말미에 층 경계(EVIDENCE_PRIORITY_RULE)를 붙여, 자료를 주입하는 모든 경로가
    같은 우선순위를 갖게 한다(chat·tool·compat·external 공용).
    """
    if not chunks:
        return None
    # ⚠️ 출처명(파일·책·페이지)을 모델에 주면 약한 LLM이 '자료1·명리전2권 p.358 등을 종합하면'처럼
    #   그대로 앵무새로 뱉는다(운영자 지적). 출처는 관리자 감사 로그에만 남기고 모델엔 본문만 준다.
    body = "\n\n".join(f"[자료{i}] {c.text}" for i, c in enumerate(chunks, 1))
    return f"{body}\n\n{EVIDENCE_PRIORITY_RULE}"


def external_fallback_answer(
    *, question: str, evidence: str | None, rag_context: str | None,
    dialect_instruction: str | None, saju_summary: str | None = None,
    allow_overseas: bool = False,
) -> str | None:
    """로컬 Ollama 전체 다운 시 외부(Claude)로 본문 생성 폴백. 실패/비활성/미동의 시 None.

    allow_overseas: 국외이전 동의 게이트(H4) — 전역 폴백 설정 ON + 회원 동의일 때만 True. False면 전송 안 함."""
    if not allow_overseas:
        return None
    try:
        out = external_llm.generate_answer(
            question=question, saju_summary=saju_summary, evidence=evidence,
            rag_context=rag_context, dialect_instruction=dialect_instruction,
        )
        return out.strip() if out and out.strip() else None
    except Exception:  # noqa: BLE001
        return None


def _log_retrieval(session_id: str | None, question: str, top_k: int,
                   chunks: list[RetrievedChunk], menu: str | None = None) -> None:
    try:
        from backend.app.core.db import get_session_factory
        from backend.app.repositories.models import RetrievalLog

        scores = [c.score for c in chunks]
        db = get_session_factory()()
        try:
            db.add(RetrievalLog(
                session_id=session_id,
                menu=menu,
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
) -> tuple[str, str, SajuChart]:
    """채팅 세션 생성. birth 필수. DB에 영속. user가 있으면 소유자로 연결."""
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
    bi = _to_birth_input(birth)
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
    """상담 '당월부터' 각 달의 월운 간지 목록 [(연, 월, '을미(乙未)'), ...].

    범위 = 그 해 12월(연말)까지 + 최소 total_min개월(연말까지가 부족하면 이듬해로 연장). 전문가 요청:
    월별 흐름은 상담일부터 최소 6개월·해당 연도 끝까지 나와야 한다. 각 달 대표 월운은 절입(양력 4~8일)
    이후로 안정적인 '중순(15일)' 기준으로 결정적 계산한다(LLM이 월운 간지를 지어내는 환각 방지).

    당월 포함(케이스 #5): 종전엔 당월을 빼고 다음 달부터 제공해, 절입 전(월초)에는 당월 간지가
    프롬프트 어디에도 없었다 → 약한 1차 모델이 목록을 한 칸 밀어 다음 달 간지를 당월에 붙임(실측:
    7월에 丙申). 당월(15일 대표)부터 제공해 표를 그대로 베끼면 정답이 되게 한다.
    """
    from datetime import date as _date
    from backend.app.saju.pillars import compute_pillars
    from backend.app.saju.types import BirthInput as _BI, CalendarType as _CT
    total = max(total_min, 12 - today.month + 1)
    out: list[tuple[int, int, str]] = []
    y, m = today.year, today.month
    for i in range(total):
        if i > 0:
            m += 1
            if m > 12:
                m, y = 1, y + 1
        fp, *_ = compute_pillars(_BI(birth_date=_date(y, m, 15), calendar=_CT.SOLAR))
        out.append((y, m, _gz_month_ko(fp.month)))
    return out


def _gz_month_ko(p) -> str:
    """월운 간지를 '을미월(乙未月)'로 — LLM이 월운을 '을미년'으로 오표기하는 것 방지(실측)."""
    from backend.app.saju.constants import branch_korean, stem_korean
    return f"{stem_korean(p.stem)}{branch_korean(p.branch)}월({p.stem}{p.branch}月)"


def _months_of_year(year: int) -> list[tuple[int, int, str]]:
    """특정 연도의 1~12월 월운 간지 목록 — '내년(2027) 매수운 몇월' 류에 그 해 12달을 제공."""
    from datetime import date as _date
    from backend.app.saju.pillars import compute_pillars
    from backend.app.saju.types import BirthInput as _BI, CalendarType as _CT
    out: list[tuple[int, int, str]] = []
    for m in range(1, 13):
        fp, *_ = compute_pillars(_BI(birth_date=_date(year, m, 15), calendar=_CT.SOLAR))
        out.append((year, m, _gz_month_ko(fp.month)))
    return out


# 질문의 상대연도(내년·명년·후년…) → 오프셋. 구체 날짜(_question_dates)가 없을 때만 월별 스코프에 반영.
_REL_YEAR_MONTHS = {"내년": 1, "명년": 1, "내후년": 2, "후년": 2, "재작년": -2, "작년": -1}


def _target_year_offset(question: str) -> int:
    """질문에 '내년/명년/후년/작년'이 있으면 그 연도 오프셋(월별 흐름을 그 해로 이동). 없으면 0."""
    q = question or ""
    for kw, off in _REL_YEAR_MONTHS.items():
        if kw in q:
            return off
    return 0


def _current_luck_block(include_iljin: bool = False, question: str | None = None,
                        chart_json: dict | None = None) -> str:
    """오늘 기준 세운(연)/월운(월) 간지를 한글(한자)로 제공(항상). include_iljin=True면 일진(일)도 추가.

    chart_json이 주어지면 월별 표에 십성·내 사주와의 합충 관계까지 병기(월별 풍부화 — 결정적 계산).

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
        # [Patch B 2026-07-05] 내년 세운을 결정적으로 주입 — '내년' 질문에서 올해/내년/연도 혼동
        #   ('내년(올해, 2027년)') 재발 방지. 세운은 입춘 기준이라 내년 중반(6/1)으로 안전 계산.
        _ny = today.year + 1
        try:
            _fpn, *_r = compute_pillars(_BI(birth_date=_date(_ny, 6, 1), calendar=_CT.SOLAR))
            _ny_ganji = _gz_ko(_fpn.year)
        except Exception:
            _ny_ganji = ""
        next_year_line = (
            f" 내년은 {_ny}년 {_ny_ganji}(세운) — '내년·명년' 질문은 이 내년 연도·세운만 쓰고, "
            f"'내년(올해, {_ny}년)'처럼 올해/내년을 뒤섞지 마세요."
            if _ny_ganji else ""
        )
        # 당월부터 월별 간지(연말+최소 6개월) — 연도가 바뀌는 첫 달에만 '연' 표기. (케이스 #5:
        # 당월을 빼면 절입 전 월초엔 당월 간지가 없어 목록이 한 칸 밀림 — 당월 포함으로 차단)
        # [2026-07 실측] '내년 매수운 몇월'인데 올해 월별을 답함 → 상대연도가 있으면 그 해 1~12월 제공.
        months_line = ""
        _off = _target_year_offset(question or "")
        if _off > 0:
            _ty = today.year + _off
            ups = _months_of_year(_ty)
            _scope_note = f"{_ty}년({'내년' if _off == 1 else '해당 연도'}) 12개월"
            # 혼합 스코프(실측 공백): '올해 말과 내년 초'처럼 두 해를 함께 물으면 내년 표로 완전
            # 교체돼 올해 말 근거가 소실됐다 — 올해 잔여 달을 앞에 병기.
            if "올해" in (question or "") or "금년" in (question or ""):
                ups = _upcoming_months(today) + ups
                _scope_note = f"이번 달부터 연말까지 + {_scope_note}"
        else:
            ups = _upcoming_months(today)
            _scope_note = "이번 달부터 연말까지"
        if ups:
            first_y, first_m, first_g = ups[0]
            # [월별 풍부화 — 전수감사 2026-07-16] 명식이 있으면 각 달에 월간·월지 십성과
            # 월운↔내 4주 합충형파(궁위)를 결정적으로 병기 — 신년운세(커밋 61a1f3a1)와 동일 원칙.
            # 상담 본해설·추가질문 + 전 tool 메뉴 추가질문(_aux_ganji_blocks 경유)이 함께 수혜.
            rel_rows: list[str] = []
            if chart_json:
                try:
                    from backend.app.saju.pillars import compute_pillars as _cp
                    from backend.app.saju.relations import (
                        branch_ten_god as _btg, luck_natal_relations as _lnr, ten_god_ko as _tgk,
                    )
                    from backend.app.saju.constants import compute_ten_god as _ctg
                    _ds = ((chart_json.get("pillars") or {}).get("day") or {}).get("stem")
                    for (yy, mm, _g) in ups:
                        mp, *_r = _cp(_BI(birth_date=_date(yy, mm, 15), calendar=_CT.SOLAR))
                        st, br = mp.month.stem, mp.month.branch
                        segs = [f"{yy}년 {mm}월 {_gz_month_ko(mp.month)}"]
                        if _ds:
                            segs.append(f"십성 {_tgk(_ctg(_ds, st))}/{_tgk(_btg(_ds, br))}")
                        rels = _lnr(chart_json, st, br, scope="월")
                        _pr = plain_relations(rels)
                        segs.append(("관계: " + "; ".join(_pr)) if _pr else "관계: 없음(무난)")
                        rel_rows.append("  · " + " · ".join(segs))
                except Exception:  # noqa: BLE001 — 관계 병기는 부가: 실패 시 간지 표만
                    rel_rows = []
            if rel_rows:
                months_line = (
                    f"\n[월별 간지·십성·내 사주와의 관계({_scope_note}) — 전부 결정적 계산]\n"
                    + "\n".join(rel_rows) + "\n"
                    f"'월별 흐름'을 풀 때는 반드시 이 표의 달↔간지 짝과 십성·관계만 근거로 쓰세요 — "
                    f"각 달은 '월운'이므로 '을미월'처럼 '월'로 쓰고 '을미년'처럼 '년'으로 쓰지 마세요. "
                    f"표를 한 칸씩 밀거나({first_m}월={first_g}) 표에 없는 달의 간지·십성·합충을 "
                    f"지어내지 마세요. '관계: 없음'인 달에 합충을 만들어 붙이지 마세요. "
                    f"단, 이 표의 관계 항목은 해석용 '근거 데이터'일 뿐입니다 — 관계 행을 그대로 "
                    f"옮겨 적거나 여러 관계를 나열하지 말고, "
                    f"흐름이 크게 바뀌는 달 1~2곳만 골라 일상어로 풀어 쓰세요"
                    f"(예: '7월에는 협력·인연의 기운이 유난히 강해집니다'). "
                    f"표의 '월운 천간·월운 지지'는 그 달 월운의 간지를 가리키는 내부 표기이니, 답변에서는 "
                    f"자리 이름 대신 'N월의 기운'이라고 부르세요.\n"
                    f"★관계의 '종류'를 바꿔 부르지 마세요 — 표에 '원진'이면 원진이고 '반합'이면 반합입니다"
                    f"(실측 오류: 표의 방합을 '반합'이라 하고, 파가 아닌 짝을 '파'라고 함).\n"
                    f"★관계의 '상대 자리'도 표 그대로 쓰세요 — 표가 '미(未)↔내 월지 묘(卯) 반합'이면 "
                    f"상대는 월지 묘(卯)입니다. 자리를 다른 자리(일지·년지·시지)로 바꿔 옮기면 "
                    f"실제로는 아무 관계도 아닌 짝을 근거로 삼게 됩니다(실측 오류: 未↔卯 반합을 "
                    f"'未와 일지 酉가 반합'이라 서술 — 未·酉는 아무 관계가 없습니다).\n"
                    f"★관계 줄은 그대로 옮겨 써도 읽히는 쉬운 문장입니다 — 그 문장을 살려 쓰고 "
                    f"끝의 [대괄호] 안 술어는 본문에서 빼세요.\n"
                    f"[관계 뜻] 합(合)=끌어당김·협조, 충(沖)=부딪힘·변동, 형(刑)=마찰·시비·구설, "
                    f"파(破)=깨짐·틀어짐, 해(害)=서로 손해 보는 어긋남(흉), 원진(怨嗔)=까닭 없는 미움(흉), "
                    f"반합(半合)=부분적 결속. 해·원진·형·파는 흉 관계이니 좋은 기회로 뒤집어 쓰지 마세요."
                )
            else:
                parts: list[str] = []
                last_y = None
                for (yy, mm, g) in ups:
                    parts.append(f"{yy}년 {mm}월={g}" if yy != last_y else f"{mm}월={g}")
                    last_y = yy
                months_line = (
                    f"\n[월별 간지(달력 월 기준, 중순 대표 — {_scope_note})] {', '.join(parts)}. "
                    f"'월별 흐름'을 풀 때는 반드시 이 표의 달↔간지 짝을 그대로 쓰세요 — 각 달은 '월운'이므로 "
                    f"'을미월'처럼 '월'로 쓰고 '을미년'처럼 '년'으로 쓰지 마세요. 표를 한 칸씩 밀거나 "
                    f"({first_m}월={first_g}) 표에 없는 달의 간지를 지어내지 마세요."
                )
        # 회고 질문(질문자가 특정 지난 연도를 명시)이면 '올해 이후만' 제약을 완화 — 그 해 세운은
        # '[질문한 연도 세운]'으로 제공되므로 지어내는 게 아니라 제공값 인용이다(비회고면 종전 제약 유지).
        if _is_retrospective(question or ""):
            year_rule = (
                f"올해는 {today.year}년입니다. 질문자가 명시한 지난 연도는 '[질문한 연도 세운]'에 제공된 "
                f"세운 간지로 그 해를 서술하고, 그 밖의 연도·간지는 지어내지 마세요."
            )
        else:
            year_rule = (
                f"연도를 적을 경우 반드시 올해={today.year}년(또는 그 이후)만 쓰고, 지난 연도(예: 2023년)나 "
                f"다른 간지를 지어내지 마세요."
            )
        return (
            f"[현재 시점 간지] 오늘은 {today.isoformat()}, 올해는 {today.year}년 {_gz_ko(fp.year)}, "
            f"이번 달은 {_gz_ko(fp.month)}{iljin}.{next_year_line} "
            f"{year_rule} '{scope}' 등 현재 운은 위 연도·간지를 그대로 사용하세요."
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


# ── 질문이 명시한 '지난 연도' 추출·주입 (Track A — 회고 동문서답 해소, 2026-07-12) ──
# 실측: "계묘년 갑진년 사업운 어땠을까"에 '올해'로 답하는 동문서답. 원인 = 간지연도(계묘=2023)·
# 절대연도(2023년)를 인식하는 파서 부재로 그 해 세운이 프롬프트에 미주입. 엔진은 산출 가능하나 호출부가 없음.
_GANZHI_YEAR_Q_RE = re.compile(r"([갑을병정무기경신임계][자축인묘진사오미신유술해])\s*년")
_ABS_YEAR_Q_RE = re.compile(r"((?:19|20)\d{2})\s*년")


def _question_target_years(question: str, today=None) -> list[int]:
    """질문에 명시된 '지난 연도'를 서기연도로 추출(간지년 계묘년→2023 · 절대연도 2023년).

    회고(Track A)만 대상: 올해 미만(과거)·최근 100년 이내로 국한하고, 미래·올해는 제외(각각 기존
    상대연도·올해 세운 경로가 담당). 미래 방향 간지 매핑은 관법(뽀 감수) 대상이라 하지 않는다.
    """
    from datetime import date as _d
    if not question:
        return []
    cur = (today or _d.today()).year
    cand: list[int] = []
    for m in _GANZHI_YEAR_Q_RE.finditer(question):
        y = _ganzhi_to_year(m.group(1), cur, "past")
        if y is not None:
            cand.append(y)
    for m in _ABS_YEAR_Q_RE.finditer(question):
        cand.append(int(m.group(1)))
    out: list[int] = []
    for y in cand:
        if (cur - 100) <= y < cur and y not in out:   # 과거만(올해·미래 제외)
            out.append(y)
    out.sort()
    return out[:4]


def _is_retrospective(question: str, today=None) -> bool:
    """질문이 특정 '지난 연도'를 명시적으로 물었는가 — 회고 허용 게이트(결정적)."""
    return bool(_question_target_years(question, today))


# ── Track B: 답변 전 사전 선택질문 — 애매한 질문에 임의 추정 대신 사용자에게 맥락을 묻는다 ──
# 실측: "내년에 새 학교 vs 취업?"에 AI가 '고등학생으로 추정'하며 학업으로 편향(반쪽 답). 전문가 지침:
# 애매하면 추정하지 말고 선택지를 제시. 질문·선택지·활성여부는 data/clarify(뽀 감수, reviewed만 발동).
from pathlib import Path as _Path
_CLARIFY_PATH = _Path(__file__).resolve().parents[3] / "data" / "clarify" / "clarify_questions.json"


def _clarify_forms_data() -> dict:
    try:
        import json as _json
        return _json.loads(_CLARIFY_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 파일 부재/파손 시 사전질문 비활성(기존 흐름 유지)
        return {}


def _clarify_form(question: str) -> dict | None:
    """애매한 질문이면 답변 전에 물을 사전 선택폼을 반환. 아니면 None.

    이미 '[상담맥락]'이 붙은(사용자가 선택/건너뛴) 재질문에는 다시 묻지 않는다(무한루프 차단).
    reviewed:true 인 폼만 발동(뽀 감수 게이트).
    """
    q = question or ""
    if not q or "[상담맥락]" in q:
        return None
    for f in _clarify_forms_data().get("forms", []):
        if not f.get("reviewed"):
            continue
        anyk, andk, notk = f.get("any") or [], f.get("and_any") or [], f.get("not_any") or []
        if anyk and not any(k in q for k in anyk):
            continue
        if andk and not any(k in q for k in andk):
            continue
        if notk and any(k in q for k in notk):
            continue
        return {"kind": "clarify", "key": f.get("key", ""),
                "question": f.get("question", ""), "options": list(f.get("options") or []),
                "skippable": True}
    return None


def _question_years_block(question: str, today=None) -> str:
    """질문이 명시한 지난 연도(들)의 세운 간지를 결정적으로 계산·주입(그 해로 회고·판정하게)."""
    years = _question_target_years(question, today)
    if not years:
        return ""
    lines: list[str] = []
    for y in years:
        try:
            ko, hj = _year_ko_hj(y)
        except Exception:  # noqa: BLE001
            continue
        lines.append(f"  · {y}년 = 세운 {ko}({hj})")
    if not lines:
        return ""
    return (
        "[질문한 연도 세운] 질문자가 아래 지난 연도(들)를 명시적으로 물었습니다. 이 세운 간지를 근거로 "
        "그 해의 운을 회고·판정하세요(이 연도에 한해 과거 회고 허용, '올해'로 바꾸지 마세요):\n"
        + "\n".join(lines)
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
    luck = _current_luck_block(include_iljin=_question_needs_iljin(question or ""), question=question,
                               chart_json=chart_json)   # 명식 있으면 월별 십성·합충 관계 병기(전 tool 공용)
    if luck:
        parts.append(luck)
    qy = _question_years_block(question or "")   # 질문이 명시한 지난 연도 세운(회고 동문서답 해소)
    if qy:
        parts.append(qy)
    qd = _question_date_block(question or "")
    if qd:
        parts.append(qd)
    return "\n\n".join(parts).strip()


def _gwanbeop_block_for(question: str, chart_json: dict | None, is_male: bool | None) -> str:
    """질문 주제에 성립한 관법(선생님 공식) 블록 — 결정적 계산(케이스 #4). 실패·미성립 시 ''.

    시기 스코프(전수감사 수정): 종전엔 항상 date.today() 고정이라 '내년 이직'·'2023년 사업운'
    질문에도 2026년 공식을 '올해 세운' 라벨로 주입해 자기모순 프롬프트가 됐다. 질문이 명시한
    대상 연도(내년 오프셋·회고 연도)의 세운으로 성립판정한다 — 공식은 세운 일반 룰이라 대입
    연도만 바뀌며(결정적), 월운 스코프는 현재 시점 질문일 때만 함께 계산(단발 사안 원칙).
    """
    if not chart_json:
        return ""
    try:
        from datetime import date as _date
        from backend.app.saju.gwanbeop import gwanbeop_block
        from backend.app.saju.pillars import compute_pillars
        from backend.app.saju.types import BirthInput as _BI, CalendarType as _CT
        today = _date.today()
        target_year = today.year
        retro = _question_target_years(question)
        _off = _target_year_offset(question)
        if retro:
            target_year = retro[-1]        # 회고: 물은 해(복수면 최근 해) 기준 성립판정
        elif _off > 0:
            target_year = today.year + _off
        if target_year == today.year:
            fp, *_ = compute_pillars(_BI(birth_date=today, calendar=_CT.SOLAR))
            return gwanbeop_block(
                question, chart_json, seun_stem=fp.year.stem, seun_branch=fp.year.branch,
                wolun_stem=fp.month.stem, wolun_branch=fp.month.branch,  # 일시적 사안은 월운 대입(선생님 원칙)
                is_male=is_male,
            ) or ""
        fp, *_ = compute_pillars(_BI(birth_date=_date(target_year, 6, 1), calendar=_CT.SOLAR))
        return gwanbeop_block(
            question, chart_json, seun_stem=fp.year.stem, seun_branch=fp.year.branch,
            is_male=is_male,               # 타겟 연도가 다르면 '이번 달 월운' 스코프는 제외(시점 불일치)
            seun_label=f"{target_year}년 세운",
        ) or ""
    except Exception:  # noqa: BLE001 — 관법 주입은 부가 기능: 실패해도 기존 흐름 유지
        return ""


def _build_user_prompt(question: str, ctx: list[RetrievedChunk], saju_summary: str | None,
                       chart_json: dict | None = None, is_male: bool | None = None) -> str:
    parts: list[str] = []
    if saju_summary:
        parts.append(saju_summary)
    # 세운/월운은 항상 제공(올해 간지 환각 차단), 일진은 '오늘/지금/일진/택일' 등 일 단위 질문일 때만(드리프트 방지)
    luck = _current_luck_block(include_iljin=_question_needs_iljin(question), question=question,
                               chart_json=chart_json)   # 명식 있으면 월별 십성·합충 관계 병기
    if luck:
        parts.append(luck)
    # 질문이 명시한 지난 연도(계묘=2023 등)의 세운을 결정적으로 계산·제공 → 회고 동문서답 차단(Track A)
    qyears = _question_years_block(question)
    if qyears:
        parts.append(qyears)
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
            # 출처명·점수는 모델에 노출하지 않는다(앵무새 인용 차단) — 본문만. 출처는 감사 로그에만.
            parts.append(f"--- 자료{i} ---\n{c.text}")
        parts.append(EVIDENCE_PRIORITY_RULE)   # 층 경계 — 해석은 자료 우선, 값은 계산값 절대우위
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


def _ollama_extra_kwargs(model: str | None) -> dict:
    """모델별 추가 페이로드. Qwen3 계열은 기본 thinking 모드라 본문 앞에 긴 내부 추론을
    생성해 첫 토큰이 크게 늦어진다 → 상담 스트림에서는 끈다. 비-thinking 모델에
    think 파라미터를 보내면 Ollama가 400을 반환하므로 모델명에 qwen3가 있을 때만 부착."""
    return {"think": False} if "qwen3" in (model or "").lower() else {}


def _call_ollama(
    messages: list[dict], model: str | None = None, temperature: float | None = None,
    num_predict: int | None = None,
) -> str:
    s = get_settings()
    payload = {
        "model": model or s.ollama_model,
        "messages": messages,
        "stream": False,
        "keep_alive": _coerce_keep_alive(s.ollama_keep_alive),
        # num_predict 오버라이드: 타로 해설 등 장문 생성이 전역 상한(3072tok)에 잘리지 않게 호출별 확장
        "options": {"temperature": s.ollama_temperature if temperature is None else temperature,
                    "num_ctx": s.ollama_num_ctx,
                    "num_predict": num_predict or s.ollama_num_predict,
                    # 반복 퇴행 억제(실측: 개명·신년운세 무한반복) — 원천 방어
                    "repeat_penalty": s.ollama_repeat_penalty,
                    "repeat_last_n": s.ollama_repeat_last_n},
    }
    payload.update(_ollama_extra_kwargs(payload["model"]))
    url = f"{s.ollama_url}/api/chat"
    # 장문 생성(num_predict 확장) 시 타임아웃을 생성량에 비례해 연장 — 실측: qwen3 ~23tok/s에서
    # 5120tok ≈ 222s > 고정 180s → 보강 타임아웃 무산. 20tok/s 보수 추정 + prefill 여유 60s.
    _np = num_predict or s.ollama_num_predict
    _timeout = max(s.ollama_timeout_sec, _np / 20.0 + 60.0)
    for attempt in range(2):
        try:
            r = httpx.post(url, json=payload, timeout=_timeout)
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


def suggestions_from_convo(convo: str, n: int, *, topic: str, fallback: list[str],
                           num_predict: int = 160) -> list[str]:
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
        # num_predict 상한: 전역(3072)을 그대로 쓰면 qwen3가 부연설명까지 길게 생성해
        # 23초+ 지연(실측 2026-07-21) → 칩이 답변 한참 뒤에 떠서 '안 나온다'로 보임.
        # n개 질문(각 25자≈18tok)에는 160tok이면 충분. 마지막 줄이 잘리면 파서가 그 줄만
        # 버려 5개가 뜰 수 있음(무해) — np3 공유 속도(~17tok/s) 기준 최악 ~9초.
        out = _call_ollama(
            [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}],
            temperature=0.8, num_predict=num_predict,
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


def synthesize_consultation(conversation: list[dict], *, topic: str = "사주 상담") -> str:
    """여러 질문·답변(상담 전체)을 하나의 매끄러운 '종합 감정서' 본문으로 재구성(로컬 LLM, 무과금).

    연속 질문으로 단편화된 답변을 중복 제거·주제별 단락으로 묶어 하나의 글로 정리한다.
    마크다운/기호는 쓰지 않게 강제(_compose 규칙 + pdf 단계 _strip_md 이중 안전망).
    LLM 실패 시 어시스턴트 답변을 단순 연결해 폴백(항상 무언가 생성).
    """
    convo = "\n\n".join(
        f"[{'질문' if m.get('role') == 'user' else '답변'}] {(m.get('content') or '').strip()}"
        for m in conversation if (m.get('content') or '').strip()
    )
    fallback = "\n\n".join(
        (m.get('content') or '').strip()
        for m in conversation if m.get('role') == 'assistant' and (m.get('content') or '').strip()
    )
    if not convo.strip():
        return fallback
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
    try:
        out = _call_ollama(
            [{"role": "system", "content": sys_msg}, {"role": "user", "content": user_msg}],
            temperature=0.4,
        )
    except Exception:  # noqa: BLE001
        return fix_term_hanja(fallback)
    out = (out or "").strip()
    # 정리 체인 필수 — 이 결과는 화면을 거치지 않고 곧장 PDF로 인쇄된다(전수감사 실측: 감정서 PDF에
    # '---' 5줄과 십성 한자 단독 '劫財'가 그대로 찍혔다). 다른 경로는 전부 체인을 타는데 여기만 빠졌다.
    return fix_term_hanja(out if len(out) >= 200 else (fallback or out))


def generate_followup_questions(db: Session, session_id: str, n: int = 6) -> list[str]:
    """사주 채팅: 최근 질문+답변 맥락으로 후속 추천질문 n개(로컬 LLM, 무과금).

    [경량화 2026-07-21] qwen3(23tok/s) 기준 생성시간 = num_predict에 비례 → 맥락 2턴·250자,
    96tok 상한으로 ~4초. 궁합/타로/택일 호출부는 기존 파라미터(160) 유지."""
    row = chat_repo.get_session(db, session_id)
    if row is None:
        return _FALLBACK_SUGGESTIONS[:n]
    qa = [m for m in row.messages if m.role in ("user", "assistant")]
    if not qa:
        return _FALLBACK_SUGGESTIONS[:n]
    convo = "\n".join(
        f"{'질문' if m.role == 'user' else '답변'}: {(m.content or '')[:250]}" for m in qa[-2:]
    )
    return suggestions_from_convo(convo, n, topic="사주 상담", fallback=_FALLBACK_SUGGESTIONS,
                                  num_predict=96)


# ---- 추천질문 프리페치 캐시 — done 직전에 백그라운드 선계산, GET은 즉시 반환 ----
# 실측(2026-07-21): 프런트가 done 후 GET 시점에야 동기 LLM 생성을 시작해 칩이 ~10초 늦게 떴다.
_SUGGEST_TTL_SEC = 300.0
_SUGGEST_CACHE: dict[str, tuple[float, list[str] | None, threading.Event]] = {}
_SUGGEST_LOCK = threading.Lock()


def prefetch_suggestions_async(session_id: str) -> None:
    """답변 done 직전에 호출 — 등록을 스레드 시작 전에 마쳐 GET 레이스를 차단한다."""
    ev = threading.Event()
    now = time.monotonic()
    with _SUGGEST_LOCK:
        for k in [k for k, (exp, _, _) in _SUGGEST_CACHE.items() if exp < now]:
            _SUGGEST_CACHE.pop(k, None)   # 만료 항목 기회적 정리
        _SUGGEST_CACHE[session_id] = (now + _SUGGEST_TTL_SEC, None, ev)

    def _run() -> None:
        qs: list[str] = []
        try:
            # 요청 스코프 Session은 스레드 비안전 + 요청 종료 시 close → 새 세션을 연다.
            from backend.app.core.db import get_session_factory
            with get_session_factory()() as db2:
                qs = generate_followup_questions(db2, session_id, n=4)
        except Exception:  # noqa: BLE001 — 실패 시 빈 캐시(폴백 경로가 처리)
            qs = []
        finally:
            with _SUGGEST_LOCK:
                _SUGGEST_CACHE[session_id] = (time.monotonic() + _SUGGEST_TTL_SEC, qs, ev)
            ev.set()

    threading.Thread(target=_run, daemon=True).start()


def get_suggestions_cached(db: Session, session_id: str, n: int = 4, wait_sec: float = 12.0) -> list[str]:
    """프리페치 캐시 우선 조회. 미등록/만료면 현행 동기 경로로 폴백.

    프리페치가 아직 실행 중이면 완료를 잠깐 기다리되, 타임아웃 시 동기 재생성은 하지 않는다
    (프리페치 LLM이 도는 중에 병렬 호출을 얹으면 GPU 경합으로 둘 다 느려짐 — 정적 폴백이 안전)."""
    now = time.monotonic()
    with _SUGGEST_LOCK:
        entry = _SUGGEST_CACHE.get(session_id)
    if entry is None or entry[0] < now:
        return generate_followup_questions(db, session_id, n=n)
    exp, qs, ev = entry
    if qs is None:
        ev.wait(timeout=wait_sec)
        with _SUGGEST_LOCK:
            entry = _SUGGEST_CACHE.get(session_id)
        qs = entry[1] if entry else None
    return qs[:n] if qs else _FALLBACK_SUGGESTIONS[:n]


def _stream_ollama(messages: list[dict], model: str | None = None, stop_event=None,
                   num_predict: int | None = None):
    """Ollama /api/chat 토큰 스트림. 각 줄은 JSON: {message:{content:'...'}, done:bool}.

    yields: str (토큰/조각)
    num_predict: 호출별 생성 상한 오버라이드(타로 장문 해설 등) — 미지정 시 전역 설정.
    """
    import json as _json
    s = get_settings()
    payload = {
        "model": model or s.ollama_model,
        "messages": messages,
        "stream": True,
        "keep_alive": _coerce_keep_alive(s.ollama_keep_alive),
        "options": {"temperature": s.ollama_temperature, "num_ctx": s.ollama_num_ctx,
                    "num_predict": num_predict or s.ollama_num_predict,
                    # 반복 퇴행 억제(실측: 개명·신년운세 무한반복) — 원천 방어
                    "repeat_penalty": s.ollama_repeat_penalty,
                    "repeat_last_n": s.ollama_repeat_last_n},
    }
    payload.update(_ollama_extra_kwargs(payload["model"]))
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
                    # [2026-07-22] 컨텍스트 천장에 닿아 답변이 잘려도 HTTP 는 200 이라
                    # 지금까지 무성 실패였다(실측: 프롬프트 16,243 + 생성 141 = num_ctx 16,384
                    # 정확 일치로 잘린 답변이 고객에게 그대로 나감). done_reason 을 남겨
                    # 최소한 탐지 가능하게 한다 — 근본 수리는 num_ctx 상향(24GB 카드 전제).
                    if obj.get("done_reason") == "length":
                        logging.getLogger("saju.chat").warning(
                            "answer truncated by context/limit: prompt_eval=%s eval=%s num_ctx=%s",
                            obj.get("prompt_eval_count"), obj.get("eval_count"), s.ollama_num_ctx,
                        )
                    break
    except httpx.RequestError as e:
        raise ServiceUnavailableError(
            "답변 생성 서비스(LLM)에 일시적으로 연결할 수 없습니다. 잠시 후 다시 시도해 주세요."
        ) from e


# ============================================================
# 로컬 생성: qwen3:14b 단독(구 exaone 대체). 로컬 2차 보강(qwen2.5)은 현재 비활성. Claude=심화보강/폴백
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
    "4. [작성 형식 — CONSULTANT_STYLE_RULE과 동기 유지] 큰 주제마다 '### 소제목' 줄을 두고 핵심 단어는 "
    "**굵게** 강조하며, 나열이 자연스러운 곳은 '- ' 불릿을 쓰세요. 1차 답변의 소제목·강조·불릿 구조는 "
    "그대로 유지·보강하고, 표(마크다운 표)와 구분선('---')은 쓰지 마세요(화면에 기호가 그대로 노출됨).\n"
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
    "10. [반복·표 복사 금지] 같은 문장·같은 표현을 두 번 쓰지 마세요(한 문단 안 중복 금지 — 1차 답변에 "
    "중복 문장이 있으면 하나로 합치세요). 근거 표의 행('월간 십성 …·관계: …')을 소제목·본문에 그대로 "
    "복사하지 말고, 전문 술어는 한 번만 쓰고 쉬운 생활어로 풀어쓰세요. 1차 답변의 쉬운 문체를 어렵게 "
    "바꾸지 마세요. 십성 병기는 '정재(正財)'처럼 한글(한자)만 허용 — '정재(정재)' 금지.\n"
    "11. [끝맺음] 답변은 반드시 완결된 문장으로 끝내세요. 분량이 부족해도 문장을 중간에 끊지 말고, "
    "마무리 조언 한 문단으로 자연스럽게 닫으세요.\n"
)


# 간체(중국) 전용 글자 — 한국은 정자(繁體)만 써서 이 글자가 나오면 중국어 드리프트로 확정.
_SIMPLIFIED_CN = set(
    "职业财关恋爱强稳应会现专领义汉维护灵适变谐决计务发观进时带机传"
    "门问学习节乐东车认识实师协单丰临书买卖贵个们这那对说话语两"
)
# 중국어 문법 글자(한국어 한자병기엔 등장하지 않음) — 하나만 나와도 강한 신호.
# (與는 정자라 한국 문헌에 드물게 나와 제외 — 오탐 방지)
_CN_FUNCTION = set("的是了着吗呢")
_CN_MARKERS = _SIMPLIFIED_CN | _CN_FUNCTION

# 영어 문장 드리프트(qwen/exaone이 한국어 답변 중간에 영어로 code-switch) 감지 —
# 연속된 영어 단어가 6개 이상 이어지면 '영어 문장 덩어리'로 보고 보강 폐기(브랜드·약어·소수 영단어는 통과).
_EN_SENTENCE_RUN_RE = re.compile(r"(?:[A-Za-z][A-Za-z’']*(?:\s+|\s*[,.;:—-]\s*)){6,}")


def _looks_korean_clean(text: str) -> bool:
    """LLM 출력이 '깨지지 않은 한국어 본문'인지 판정.

    탈락 조건(= 보강 폐기 후 폴백/초안 유지):
      - 비었거나 공백뿐 / 치환문자(\\ufffd)·깨진 서로게이트(U+DC80~U+DCFF)
      - 한글이 거의 없음(< 20자) / 한자가 한글보다 많음(전체 비율)
      - [강화] 중국어 마커(간체·중문 문법자)가 2자 이상 — 실측: 긴 한국어 상단 뒤 월별이 중국어로
        드리프트해도 전체 비율은 통과하던 누출을 차단
      - [강화] '한 문단이라도' 중국어 덩어리(한자≥8·한글<3인 줄) — 부분 드리프트 포착
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
    # 중국어 마커 2자 이상이면 부분 드리프트로 간주(전체 비율 무관)
    if sum(1 for c in text if c in _CN_MARKERS) >= 2:
        return False
    # 영어 문장 드리프트(연속 영단어 6+) — 한국어 답변 중간 영어 code-switch 포착(중국어와 동급 폐기)
    if _EN_SENTENCE_RUN_RE.search(text):
        return False
    # 줄 단위: 한자 덩어리(≥8)인데 한글이 거의 없는(<3) 줄이 있으면 중국어 문단
    for ln in text.splitlines():
        if len(_HANJA_RE.findall(ln)) >= 8 and len(_HANGUL_RE.findall(ln)) < 3:
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


# ── 교체 안전 게이트(운영자 실측 2026-07-22: "잘 나왔던 것도 검증·보강 후에 잘린다") ──
# 초안은 12월까지 완결 스트리밍됐는데 보강(qwen/Claude)·교정 재생성이 만든 '잘린 본문'이
# 원본을 교체("**에너지가"에서 절단). 원인(토큰 한계·ctx 예산)이 어디든, 교체 후보가
# ①문장 미완결(잘린 모양) 또는 ②원본보다 크게 짧으면 교체를 거부하고 원본을 유지한다.
_SENT_END_RE = re.compile(r"[.!?다요…\"'」\)\]。]$")


def _looks_truncated(text: str) -> bool:
    """생성이 중간에 끊긴 모양인지(결정적): 종결부호/종결어미로 안 끝나거나 '**' 굵게가 홀수로 열림.

    [2026-07-22 오탐 수정] 마크다운 강조로 끝나는 정상 문장('…참고용이에요.**')을 잘림으로
    오판하던 문제 — 판정 전에 꼬리의 마크다운 기호(*·_·`·공백)를 벗겨낸다(꿈해몽 실측)."""
    raw = (text or "").rstrip()
    t = raw.rstrip("*_`~ \t")       # 종결 판정은 꼬리 마크다운 기호를 벗겨서
    if not t:
        return True
    if not _SENT_END_RE.search(t[-1]):
        return True
    if raw.count("**") % 2 == 1:    # 짝 검사는 원문으로 — '**에너지가' 류 열린 굵게 마커
        return True
    return False


# ---- 반복 퇴행(degeneration) 감지 — 약한 LLM이 같은 구절을 무한 반복하는 폭주 차단 ----
# 실측(2026-07-27): 개명 답변 '연, 영, 연, 영…' 2천자, 신년운세 tool#305 '인연에 대한 기회가
# 생길 때까지는' 228회 저장·과금. repeat_penalty(원천 억제)로도 못 막은 경우의 최종 결정적 백스톱.
# 캘리브레이션: 실 DB 정상답변 425건 오탐 0, 퇴행 샘플·실제 #305 전부 포착.
_DEGEN_FORMAT_CHARS = set("-=*_#>.·▪◦•●○※★☆ \t\n\r|")


def _degenerate_span(text: str) -> tuple[str, int, int]:
    """가장 긴 '연속 단위 반복'의 (unit, reps, span_chars). 반복 없으면 ('',0,0).

    단위 길이 1~24를 훑어 같은 조각이 연달아 몇 번 나오는지 본다. 반복 구간은 건너뛰어
    전체적으로 O(n·24)에 수렴(정상 문장은 내부 while이 즉시 종료)."""
    best = ("", 0, 0)
    n = len(text)
    for L in range(1, 25):
        i = 0
        while i <= n - 2 * L:
            unit = text[i:i + L]
            j = i + L
            reps = 1
            while text[j:j + L] == unit:
                reps += 1
                j += L
            if reps >= 2:
                span = reps * L
                if span > best[2]:
                    best = (unit, reps, span)
                i = j
            else:
                i += 1
    return best


def _low_diversity_run(text: str, win: int = 150, max_distinct: int = 6) -> bool:
    """공백·형식문자 제외 글자열에서 길이 win 창의 서로 다른 글자가 max_distinct 이하로 유지되면
    퇴행(근사 반복 포함 — 'A B A C A B…'처럼 변주가 섞여도 글자 다양성이 바닥이라 잡힌다)."""
    from collections import Counter
    chars = [c for c in text if not c.isspace() and c not in _DEGEN_FORMAT_CHARS]
    if len(chars) < win:
        return False
    cnt = Counter(chars[:win])
    if len(cnt) <= max_distinct:
        return True
    for i in range(len(chars) - win):
        cnt[chars[i]] -= 1
        if cnt[chars[i]] == 0:
            del cnt[chars[i]]
        cnt[chars[i + win]] += 1
        if len(cnt) <= max_distinct:
            return True
    return False


def _looks_degenerate(text: str) -> bool:
    """답변이 반복 퇴행(같은 구절/글자 폭주)이면 True. 최종본·저장·과금 판정용(보수적)."""
    if not text or len(text) < 60:
        return False
    unit, reps, span = _degenerate_span(text)
    u = unit.strip()
    if u and (set(u) - _DEGEN_FORMAT_CHARS):     # 순수 형식문자(---, ***) 반복은 제외
        if span >= 300:                          # 300자+ 순수 반복
            return True
        if len(u) >= 2 and reps >= 15:           # 2자+ 구절 15회+
            return True
        if len(u) == 1 and reps >= 40:           # 한 글자 40회+
            return True
    return _low_diversity_run(text)              # 변주 섞인 근사 반복까지


def _stream_is_degenerating(tail: str) -> bool:
    """스트림 도중 '최근 꼬리'가 퇴행 중인지(조기 중단용, 더 민감). tail은 누적 답변의 끝 ~400자."""
    if len(tail) < 120:
        return False
    unit, reps, _ = _degenerate_span(tail)
    u = unit.strip()
    if u and (set(u) - _DEGEN_FORMAT_CHARS) and ((len(u) >= 2 and reps >= 6) or (len(u) == 1 and reps >= 20)):
        return True
    return _low_diversity_run(tail, win=100, max_distinct=5)


def _correct_degenerate(answer: str, *, sys_content: str, base_user: str, force: bool = False) -> str:
    """답변이 반복 퇴행이면 '반복 금지' 지시로 1회 재생성. 구제되면 정상 문자열, 구제 실패면 ''.

    '' 반환 시 호출부는 빈 답변 경로로 처리(퇴행 답변을 저장·과금하지 않고 환불/재시도). base_user 는
    원래 사용자 프롬프트 본문(메뉴별로 다름 — chat=명식+질문, tool/compat=브리프) 그대로 넘긴다.
    force=True: 스트림 조기중단(더 민감한 임계)으로 끊긴 '잘린 부분답'은 최종 판정(_looks_degenerate,
    보수적 임계)에 안 걸려도 재생성해야 잘린 답 저장을 막는다 — 이때 감지 게이트를 건너뛴다."""
    if not answer or (not force and not _looks_degenerate(answer)):
        return answer
    hint = (
        base_user + "\n\n[재생성 — 반복 절대 금지] 직전 생성이 같은 단어·구절을 무한 반복하는 오류를 냈습니다. "
        "같은 표현을 되풀이하지 말고, 각 문장을 서로 다른 내용으로 간결하게 작성하세요. 예시 목록이 필요하면 "
        "3~5개만 제시하고 절대 반복하지 마세요."
    )
    try:
        new = _call_ollama(
            [{"role": "system", "content": sys_content}, {"role": "user", "content": hint}],
            num_predict=min(5120, max(1024, len(answer) + 768)),  # 3,500자 답변 퇴행교정 잘림 방지(3072→5120)
        )
    except Exception:  # noqa: BLE001
        new = None
    cand = (new or "").strip()
    if cand and len(cand) >= 60 and not _looks_degenerate(cand):
        return cand
    logging.getLogger("saju.chat").warning(
        "degenerate unrecoverable (len=%d) — 빈답변 처리로 환불/재시도", len(answer))
    return ""   # 구제 실패 → 빈 답변 취급(퇴행 저장·과금 차단)


# 달 소제목 — 실제 운영 답변이 쓰는 형식을 폭넓게 인정하되, **평문 줄머리는 배제**한다.
# 반례 사냥 실측: 운영 DB의 '#### 1월: 기축월(己丑月) …'·'- **1월 기축월 (己丑月)**' 를
# 종전 패턴이 전혀 못 잡아 월별 백스톱이 통째로 무발동했다. 반대로 접두를 안 요구하면
# 총운 안의 '3월 전후로 큰 결정을…' 같은 평문을 헤딩으로 오인해 그 위를 통째로 지운다
# → 헤딩 마커(#)·굵게(**)·불릿 중 하나를 **반드시** 요구한다.
_MONTH_HEAD_RE = re.compile(
    # 헤딩(#)·줄머리 굵게(**)는 조사가 붙어도 소제목이다('**7월은 …**').
    r"(?m)^[ \t]*(?:(?:#{2,6}[ \t]*\*{0,2}|\*{2})(\d{1,2})월(?=[\s*(:·)\]은는이의가로]|$)"
    # 불릿형은 **굵게를 필수로** 요구한다('- **1월 기축월 (己丑月)**' 실측 형식).
    # 굵게를 안 요구하면 '- 1월 서술 …' 같은 본문 불릿까지 헤딩으로 잡혀 섹션이 산산조각 난다.
    r"|[-•·*+][ \t]*\*{2}(\d{1,2})월(?=[\s*(:·)\]]|$)"
    # [교차검증 2026-07-22] 서식 규칙(CONSULTANT_STYLE_RULE)이 '- ' 불릿을 권장하게 바뀌면서
    # **굵게 없는** '- 4월 …' 형태가 새 사각지대가 됐다(실측: '- **3월**'은 잡고 '- 4월'은 못 잡음).
    # 그렇다고 뒤에 공백만 와도 인정하면 '- 3월 전후로 큰 결정을' 같은 본문 불릿까지 헤딩이 되어
    # 섹션이 산산조각 난다 → **소제목에만 오는 꼬리**(줄끝·콜론·괄호·간지월)일 때만 인정한다.
    r"|[-•·*+][ \t]*(\d{1,2})월(?=[ \t]*(?:[:：(（]|$)"
    r"|[ \t]+(?:[갑을병정무기경신임계][자축인묘진사오미신유술해]월|[一-鿿]{2}[ \t]*월)))")


_TABLE_ECHO_RE = re.compile(
    r"^[-•·*]?\s*\*{0,2}\s*(?:월간\s*십성|월지\s*십성|관계)\s*\*{0,2}\s*[:：]")


def _section_body_scan(text: str) -> dict[str, tuple[int, int]]:
    """월 섹션별 (실질 서술 줄 수, 글자 수). 헤딩 잔여·표 복사줄·빈 줄은 제외."""
    out: dict[str, tuple[int, int]] = {}
    t = text or ""
    heads = list(_MONTH_HEAD_RE.finditer(t))
    for i, m in enumerate(heads):
        nl = t.find("\n", m.end())                    # 헤딩 '줄 전체'를 건너뛴다(잔여 '(경자월)' 오카운트 방지)
        start = (nl + 1) if nl != -1 else len(t)
        end = heads[i + 1].start() if i + 1 < len(heads) else len(t)
        n = chars = 0
        for ln in t[start:end].split("\n"):
            s = ln.strip()
            if not s:
                continue
            if s.startswith("#"):
                break                                  # 다음 대섹션(### 마무리 조언 등) 진입 → 종료
            if _TABLE_ECHO_RE.match(s):
                continue                               # 근거표 복사줄은 내용으로 치지 않음
            n += 1
            chars += len(s)
        out[m.group(1) or m.group(2) or m.group(3)] = (n, chars)   # 헤딩/굵게불릿/평문불릿 중 잡힌 쪽
    return out


def _section_body_counts(text: str) -> dict[str, int]:
    """월 섹션별 '실질 서술 줄 수'. 보강 후 내용 증발 탐지용."""
    return {k: v[0] for k, v in _section_body_scan(text).items()}


# 한 달치 서술이 이 글자 수에 못 미치면 '빈약한 달'로 본다(운영자 요구 5~7줄의 절반 수준).
# 줄 수만 세면 한 문단형으로 쓴 달은 내용이 3문장으로 쪼그라들어도 1줄이라 백스톱이 안 걸렸다
# (전수감사 실측: 11월 121자·12월 101자인데 '빈 달 0건'으로 통과).
# [반례 사냥 실측] 운영 DB 실제 분포 [57,107,125,127,131,137,139,172,175,190,208,223] 대조 —
# 140은 중앙값 바로 아래라 127·131·137자짜리 '정상' 달까지 빈약으로 오판해 불필요한 재생성을
# 유발했다. 확실히 빈약한 구간만 잡도록 110으로 낮춘다.
_THIN_MONTH_CHARS = 110


def _thin_month_keys(text: str) -> list[str]:
    """서술이 아예 없거나(0줄) 너무 짧은 달의 번호 목록 — 월별 분리 재생성 트리거."""
    return [k for k, (n, c) in _section_body_scan(text).items()
            if n == 0 or c < _THIN_MONTH_CHARS]


# 월 헤더: '3월', '3月', '#### 3월', '• 3월', '9月 (정유월)' 등. 지지'월'(신묘월)은 앞에 숫자가 없어 제외.
_MONTH_HDR_LINE = re.compile(r"^[ \t]*(?:#{1,6}[ \t]*)?(?:[▶▴■◆◇●○•·※\-*]+[ \t]*)?(\d{1,2})\s*[월月]\b")
# 비월별 큰 섹션(총운·영역별·마무리·①②③④ 등) — 이 줄을 만나면 '중복 건너뛰기'를 해제한다.
_NONMONTH_SECTION = re.compile(r"^[ \t]*(?:#{1,6}[ \t]*)?(?:[①②③④⑤⑥]|총운|영역별|영역\s*심화|마무리|종합)")


def _dedupe_month_sections(text: str) -> str:
    """월별 섹션이 중복 생성된 경우, 같은 달의 '두 번째 이후' 블록을 결정적으로 제거(첫 블록만 유지).

    재생성이 아니라 '전체를 읽어 중복만 걷어내는' 정리(운영자 지시 2026-08-04: 월별 재생성이 좋은 첫
    답변에 중복·순서뒤섞임을 덧붙임). 총운·영역별·마무리 등 비월별 블록은 건드리지 않는다. 실제 중복이
    없으면 원문 그대로 반환(무해)."""
    if not text or ("월" not in text and "月" not in text):
        return text
    lines = text.split("\n")
    # 먼저 각 달이 몇 번 헤더로 등장하는지 — 중복이 없으면 아무것도 안 한다.
    from collections import Counter
    cnt = Counter()
    for ln in lines:
        m = _MONTH_HDR_LINE.match(ln)
        if m and 1 <= int(m.group(1)) <= 12:
            cnt[int(m.group(1))] += 1
    if not any(v >= 2 for v in cnt.values()):
        return text
    out: list[str] = []
    seen: set[int] = set()
    skipping = False
    for ln in lines:
        m = _MONTH_HDR_LINE.match(ln)
        if m and 1 <= int(m.group(1)) <= 12:
            mn = int(m.group(1))
            if mn in seen:
                skipping = True          # 이미 나온 달 → 이 블록 통째 건너뜀
                continue
            seen.add(mn); skipping = False; out.append(ln); continue
        if _NONMONTH_SECTION.match(ln):
            skipping = False; out.append(ln); continue   # 비월별 섹션 시작 → 스킵 해제
        if skipping:
            continue
        out.append(ln)
    res = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return res


# 문장 경계: 종결부호(.!?。) 또는 줄바꿈까지 한 덩어리. 긴 문장의 '복붙 반복'만 제거용.
_SENT_TOKEN = re.compile(r"[^.!?。\n]*(?:[.!?。]+|\n|$)")


def _dedupe_repeated_sentences(text: str, min_len: int = 28) -> str:
    """여러 곳(달·영역)에 복붙된 '긴 문장'(정규화 min_len자↑)의 2번째 이후를 제거(첫 번째만 유지).

    재생성이 아니라 '전체를 읽어 반복만 걷어내는' 정리(운영자 #10: 좁은 해에 모델이 같은 조언 문장을
    여러 달에 복붙). 짧은 문장·헤더·구두점은 보존(정상 반복 보호). 반복 없으면 원문 그대로(무해)."""
    if not text:
        return text
    seen: set[str] = set()
    out: list[str] = []
    changed = False
    for m in _SENT_TOKEN.finditer(text):
        seg = m.group(0)
        if not seg:
            continue
        key = re.sub(r"[^가-힣一-鿿]", "", seg)   # 한글·한자만 남겨 정규화(공백·기호·숫자 무시)
        if len(key) >= min_len:
            if key in seen:
                changed = True
                if seg.endswith("\n"):
                    out.append("\n")             # 레이아웃 유지 위해 줄바꿈만 남김
                continue
            seen.add(key)
        out.append(seg)
    if not changed:
        return text
    res = re.sub(r"[ \t]{2,}", " ", "".join(out))
    res = re.sub(r"\n{3,}", "\n\n", res)
    return res.strip()


def _splice_month_section(original: str, months_only: str | None) -> str | None:
    """월별 구간만 따로 생성한 결과를 원본의 월별 구간에 끼워 넣는다(총운·영역·마무리는 보존).

    운영자 실측(2026-07-22): 한 번에 4천자를 쓰게 하면 뒷달(5·6·7월…)이 근거표 2줄만 남는 열화.
    → 월별만 재생성해 교체. 새 월별이 원본보다 '서술이 있는 달'을 더 많이 담을 때만 적용(무회귀).
    반환 None = 교체하지 않음(원본 유지).
    """
    m = (months_only or "").strip()
    if not original or not m:
        return None
    new_heads = list(_MONTH_HEAD_RE.finditer(m))
    if len(new_heads) < 6:                       # 최소 절반 이상 담겨야 교체 가치
        return None
    # 개선 판정: '빈약한 달'이 줄어야 교체(줄 수뿐 아니라 글자 수도 본다 — 한 문단형 달이
    # 3문장으로 쪼그라들어도 1줄이라 줄 수만으로는 열화가 잡히지 않았다).
    if len(_thin_month_keys(m)) >= len(_thin_month_keys(original)):
        return None
    old_heads = list(_MONTH_HEAD_RE.finditer(original))
    if not old_heads:
        return None
    start = old_heads[0].start()
    # 월별 구간의 끝 = 마지막 월 이후 처음 나오는 대섹션(### …) 또는 문서 끝
    tail_from = old_heads[-1].end()
    nxt = re.search(r"(?m)^#{2,4}[ \t]*(?!\d)", original[tail_from:])
    end = (tail_from + nxt.start()) if nxt else len(original)
    body = m[new_heads[0].start():].strip()
    return (original[:start] + body + "\n\n" + original[end:]).strip()


def _safe_replace(original: str, candidate: str | None, *, min_ratio: float = 0.75,
                  hard_floor: bool = False) -> str | None:
    """보강/교정 교체 후보 검증 — 안전하면 candidate, 아니면 None(원본 유지).

    ① 잘린 모양(_looks_truncated) ② 과단축(원본 대비 min_ratio 미만; 짧은 원본은 기본 0.6)
    ③ [2026-07-22 실측] 구조 증발 — 원본에 서술이 있던 월 섹션이 후보에서 표만 남고 비었으면 거부.
       (11·12월 서술이 통째로 사라진 채 길이·끝맺음은 정상이라 ①②를 통과하던 사고)

    hard_floor=True: 짧은 원본(800자 미만) 완화를 끄고 min_ratio 를 그대로 강제한다.
      [2026-07-28] 종전엔 원본<800자면 min_ratio(0.85/0.9/1.0)를 조용히 0.6으로 낮춰, 교정/보강이
      800자 미만 유료 답변을 40%까지 삭감해도 통과했다(운영자 지적 #7). 교정·보강·분량보강 호출은
      hard_floor=True 로 엄격 비율을 유지한다(전역 길이검사가 종합/성격 답변 삭감도 함께 막음).
    """
    c = (candidate or "").strip()
    if not c:
        return None
    if _looks_truncated(c):
        return None
    o = (original or "").strip()
    ratio = min_ratio if (hard_floor or len(o) >= 800) else 0.6
    if o and len(c) < len(o) * ratio:
        return None
    # 구조 보존: 원본에서 서술이 2줄 이상이던 달이 후보에서 0줄이면 내용 증발 → 교체 거부
    try:
        o_scan, c_scan = _section_body_scan(o), _section_body_scan(c)
        o_sec = {k: v[0] for k, v in o_scan.items()}
        c_sec = {k: v[0] for k, v in c_scan.items()}
        if o_sec:
            lost = [k for k, v in o_sec.items() if v >= 2 and c_sec.get(k, 0) == 0]
            if lost:
                return None
            # 부분 열화: 앞달은 그대로 두고 뒷달만 얇아지는 재생성(운영자 실측 "위는 정상, 아래는 빈약").
            # 판정은 **글자 수**로 한다 — 줄 수로만 보면 같은 내용을 불릿에서 한 문단으로 재작성한
            # 정당한 교정본(줄 48→12, 글자는 오히려 증가)까지 거부한다(반례 사냥 실측).
            o_chars = sum(v[1] for v in o_scan.values())
            c_chars = sum(c_scan.get(k, (0, 0))[1] for k in o_scan)
            if o_chars >= 400 and c_chars < o_chars * 0.7:
                return None
            thinned = [k for k, v in o_scan.items()
                       if v[1] >= 120 and c_scan.get(k, (0, 0))[1] < v[1] * 0.4]
            if len(thinned) >= 2:
                return None
    except Exception:  # noqa: BLE001 — 구조 검사는 부가: 실패해도 위 검사 결과 사용
        pass
    return c


def _refine_with_qwen(
    *,
    question: str,
    draft: str,
    saju_summary: str | None,
    evidence: str | None,
    rag_context: str | None,
    dialect_instruction: str | None,
) -> str | None:
    """심화 2차 보강을 로컬 qwen으로 수행. 한국어 가드 통과 시에만 반환, 아니면 None.

    [교체 안전 게이트] 결과가 잘린 모양이거나 초안보다 크게 짧으면 None(초안 유지)."""
    s = get_settings()
    if not s.deep_local_refine_enabled:
        return None
    saju_summary = _with_current_luck(saju_summary)   # 보강 단계에도 올해 세운 주입
    block = _build_refine_block(
        question=question, draft=draft, saju_summary=saju_summary,
        evidence=evidence, rag_context=rag_context,
        dialect_instruction=dialect_instruction,
    )
    # qwen2.5는 한자 많은 컨텍스트에서 간헐적으로 중국어로 드리프트한다.
    # 저온도(0.2)로 1차 시도 → 가드 탈락 시 '한국어 강제' 못을 더 박아 1회 재시도.
    base_msgs = [
        {"role": "system", "content": refine_system_for(_QWEN_REFINE_SYSTEM, rag_context)},
        {"role": "user", "content": block},
    ]
    attempts = [
        (base_msgs, 0.2),
        (
            [
                {"role": "system", "content": refine_system_for(_QWEN_REFINE_SYSTEM, rag_context)},
                {
                    "role": "user",
                    "content": block
                    + "\n\n[필수] 위 작업을 반드시 한국어 문장으로만 다시 작성하세요. "
                    "중국어(간체/번체) 단어·문장을 한 글자도 쓰지 마세요.",
                },
            ],
            0.1,
        ),
    ]
    # 보강본이 초안보다 짧게 잘리지 않게 초안 길이 기반 동적 상한(한국어 ~1자≈1tok 근사, 과대추정 무해).
    # 실측(2026-07-21): 신년운세 장문이 전역 3072에서 5월 부근 중간 잘림 — qwen 보강이 재작성하며 절단.
    _np = max(s.ollama_num_predict, min(8192, len(draft) + 1024))
    for msgs, temp in attempts:
        try:
            out = _call_ollama(msgs, model=s.ollama_refine_model, temperature=temp, num_predict=_np)
        except ServiceUnavailableError:
            return None
        out = (out or "").strip()
        if _looks_korean_clean(out):
            # 교체 안전 게이트 — 잘린 모양/과단축이면 폐기(초안 유지). 실측: 보강본 절단 교체 사고.
            return _safe_replace(draft, out, min_ratio=0.9, hard_floor=True)  # 보강은 줄이면 안 됨(0.9·짧은 원본도 완화 없음)
    # 재시도까지 중국어 드리프트/깨짐 → 보강 폐기(초안 유지 또는 Claude 폴백)
    return None


def _deep_refine(
    *,
    question: str,
    draft: str,
    saju_summary: str | None,
    evidence: str | None,
    rag_context: str | None,
    dialect_instruction: str | None,
) -> tuple[str | None, str | None]:
    """심화 2차 보강 해석: 로컬 qwen 우선 → 실패/깨짐 시 Claude 폴백.

    반환: (보강본문 | None, 사용엔진 'qwen'|'claude'|None)
    """
    saju_summary = _with_current_luck(saju_summary)   # 보강 단계에도 올해 세운 주입(qwen·Claude 공통)
    out = _refine_with_qwen(
        question=question, draft=draft, saju_summary=saju_summary,
        evidence=evidence, rag_context=rag_context,
        dialect_instruction=dialect_instruction,
    )
    if out:
        return out, "qwen"
    # 로컬 보강 실패 → Claude 폴백(가능 시)
    if external_llm.is_enabled():
        c = external_llm.refine_answer(
            question=question, draft=draft, saju_summary=saju_summary,
            evidence=evidence, rag_context=rag_context,
            dialect_instruction=dialect_instruction,
        )
        c2 = _safe_replace(draft, c, min_ratio=0.9, hard_floor=True)   # 보강은 줄이면 안 됨(0.9) — 잘린/과단축 폐기
        if c2:
            return c2, "claude"
    return None, None


def _claude_boost(
    *, question: str, draft: str, saju_summary: str | None, evidence: str | None,
    rag_context: str | None, dialect_instruction: str | None,
) -> str | None:
    """심화 '외부' 보강 — Claude로 1차 답변(qwen3:14b)을 추가 검증·보강.

    설계: 심화는 [1차 답변] 다음에 Claude를 '연결'(보강)한다. 비활성/실패 시 None
    (직전 답변 유지). 폴백이 아니라 deep 전용 추가 단계.
    """
    if not external_llm.is_enabled():
        return None
    saju_summary = _with_current_luck(saju_summary)   # 보강 단계에도 올해 세운 주입
    try:
        c = external_llm.refine_answer(
            question=question, draft=draft, saju_summary=saju_summary,
            evidence=evidence, rag_context=rag_context, dialect_instruction=dialect_instruction,
        )
    except Exception:  # noqa: BLE001
        return None
    # 교체 안전 게이트 — Claude 보강본이 잘린 모양/과단축이면 폐기(직전 답변 유지). 실측 절단 사고.
    return _safe_replace(draft, c, min_ratio=0.9, hard_floor=True)  # 보강은 줄이면 안 됨(0.9)


def _bg_with_heartbeat(s, fn, progress_phase: str | None = None):
    """fn()을 백그라운드 스레드로 실행하며 SSE 하트비트(ping)를 yield, 완료 시 ('result', value) 1회.

    스트리밍 보강(qwen/Claude)이 길어질 때 무음 구간(프록시 524)을 막는다.
    progress_phase 지정 시 ping 대신 stage(phase, elapsed) 를 yield — 프런트는 SSE 주석(': ping')을
    파싱하지 않아 교정 50~140초 구간이 완전 무음(멈춤)으로 보이던 문제의 진행표시(실측 2026-07-21).
    """
    import queue as _q
    q: "_q.Queue[Any]" = _q.Queue()

    def _w() -> None:
        try:
            q.put(fn())
        except Exception:  # noqa: BLE001
            q.put(None)

    threading.Thread(target=_w, daemon=True).start()
    waited = 0.0
    while True:
        try:
            val = q.get(timeout=s.sse_heartbeat_sec)
            yield ("result", val)
            return
        except _q.Empty:
            waited += s.sse_heartbeat_sec
            if progress_phase:
                yield ("stage", {"phase": progress_phase, "elapsed": int(waited)})
            else:
                yield ("ping", {})


def _refund_free_claim(db: Session, user: User | None, bill: dict[str, Any]) -> None:
    """생성 실패(명시적 error) 시 _decide_billing(claim=True)이 선점한 무료/멤버십 슬롯을 되돌린다(원자적 보상).

    스트리밍은 무한무료 방지를 위해 선점을 '생성 전'에 커밋하므로(post_message_stream), 실제 답변을
    만들지 못한 error 경로에서는 이 보상으로 카운터를 원복해 사용자가 무료 1회를 억울하게 잃지 않게 한다.
    (클라 disconnect 는 서버가 답변을 생성했으므로 보상 대상 아님 — 소비 유지가 정책.)"""
    if user is None:
        return
    from sqlalchemy import update as _upd
    if bill.get("use_free_quota"):
        db.execute(_upd(User).where(User.id == user.id, User.free_used_count > 0)
                   .values(free_used_count=User.free_used_count - 1))
    elif bill.get("use_daily_free"):
        # claim 성공 = 오늘 첫 무료였다는 뜻 → NULL 로 원복(오늘 미사용 상태).
        db.execute(_upd(User).where(User.id == user.id).values(daily_free_used_at=None))
    elif bill.get("use_membership"):
        db.execute(_upd(User).where(User.id == user.id, User.membership_used_count > 0)
                   .values(membership_used_count=User.membership_used_count - 1))
    elif bill.get("use_pass_free") and bill.get("pass_id"):
        from backend.app.services import pass_service
        pass_service.refund_free_basic(db, bill["pass_id"])
    # 영수증도 환불로 마감(현금·무료슬롯 공통, 리컨실 재복구 차단). refund_followup·챗 에러분기 5곳을 일괄 커버.
    from backend.app.services import receipt_service
    receipt_service.close_refunded(db, bill.get("receipt_id"))


def precharge_followup(db: Session, user: User | None, bill: dict[str, Any], *, reason: str, ref_id: str) -> int:
    """추가질문(프리미엄 메뉴 입장 후 후속질문) 소비를 '생성 전' 확정 커밋 — 전체 답변 전달 후 클라가
    disconnect 하면 함수 끝의 commit 이 롤백돼 유료 차감·멤버십 선점이 사라져 무료가 되던 free-ride 차단.

    유료(credits_to_charge)는 즉시 차감, 무료/멤버십/pass 선점은 이미 _decide_billing(claim=True)에서 선점됐으니
    커밋으로 확정한다. 반환=차감한 크레딧(생성 실패 시 refund_followup 보상용). 잔액부족은 _decide_billing 이 이미
    ValueError 로 걸러냈으므로 여기 도달 시 차감 성공을 가정한다."""
    if user is None:
        return 0
    charged = 0
    c = int(bill.get("credits_to_charge", 0) or 0)
    if c > 0:
        auth_service.adjust_credit(db, user.id, -c, reason=reason, ref_id=ref_id)
        charged = c
    # 크래시 orphan(선점 O·답변 X) 탐지 앵커 — 현금·무료슬롯(멤버십/pass) 공통. 선점/차감과 '같은 커밋'(아래)에 합류.
    #   각 메뉴 'done'(EOF)에서 finalize_receipt(complete), 오류/환불(_refund_free_claim)에서 close_refunded 로 전이.
    from backend.app.services import receipt_service
    bill["receipt_id"] = receipt_service.open_for_bill(
        db, user_id=user.id, menu=reason, ref_id=ref_id, bill=bill, charged=charged)
    if charged or bill.get("use_membership") or bill.get("use_pass_free") \
            or bill.get("use_free_quota") or bill.get("use_daily_free"):
        db.commit()
    return charged


def refund_followup(db: Session, user: User | None, bill: dict[str, Any], charged: int, *, reason: str, ref_id: str) -> None:
    """생성 실패(명시적 error) 시 precharge_followup 으로 확정한 크레딧·선점을 원복(보상)."""
    if user is None:
        return
    _rid = bill.get("receipt_id")
    if charged and charged > 0:
        # 리컨실과 '동일한' idem_key → in-process 환불과 orphan 리컨실이 DB 레벨에서 상호 멱등
        #   (둘 다 같은 receipt 를 환불하려 해도 adjust_credit 게이트가 1회만 반영 — 이중환불 원천차단).
        _idem = f"receipt:{_rid}:refund" if _rid else None
        auth_service.adjust_credit(db, user.id, +charged, reason=f"{reason}_refund", ref_id=ref_id, idem_key=_idem)
    _refund_free_claim(db, user, bill)   # 무료슬롯 복원 + 영수증 close_refunded(공통 처리)
    db.commit()


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
        "use_pass_free": False,   # B-7 플러스 월 무료 기본질문 선점 여부(무한무료 차단·보상용)
        "pass_id": None,
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

    # B-7 플러스 패스: 월 1회 기본질문 무료(원자적 선점) → 소진 시 추가질문 % 할인
    try:
        from backend.app.services import pass_service
        _pass = pass_service.get_pass(db, user.id)
    except Exception:  # noqa: BLE001 — 패스 조회 실패가 과금 판정을 막지 않음
        _pass = None
    if _pass is not None and _pass.tier == "plus":
        free_q = settings_service.get_int(db, "pass_free_basic_monthly", 5)
        # [버그 2026-07-23] allow_free_quota 를 안 봐서, '입장료를 냈으니 추가질문은 항상 차감'이어야 할
        #   프리미엄·툴 계열 추가질문이 플러스의 월 무료 5회를 대신 소진시켰다(위 docstring 계약 위반).
        #   바로 아래 일반 무료한도(`if allow_free_quota and free_available`)는 제대로 막혀 있었는데
        #   패스 블록만 빠져 있었다. 플러스 회원이 궁합 추가질문 5개만 던지면 월 무료가 조용히 사라지고
        #   정작 사주 기본질문엔 못 썼다. 할인(아래 disc)은 프리미엄 추가질문에도 계속 적용된다.
        if allow_free_quota and depth == "basic" and free_q > 0:
            if claim:
                if pass_service.claim_free_basic(db, _pass.id):
                    # use_pass_free/pass_id 로 스트림이 이 선점을 '생성 전 커밋'하고 실패 시 보상(무한무료 차단).
                    info.update(billing_mode="pass_free", is_preview=False,
                                use_pass_free=True, pass_id=_pass.id)
                    return info
            elif (_pass.free_basic_used or 0) < free_q:
                info.update(billing_mode="pass_free", is_preview=False)
                return info
        disc = settings_service.get_int(db, "pass_followup_discount_pct", 30)
        if disc > 0:
            cost = max(0, round(cost * (100 - disc) / 100))
            info["cost"] = cost

    # 일반회원/그 외 로그인 회원: 무료 한도 → 소진 시 크레딧 차감
    from datetime import date as _d
    today = _d.today()
    # (버그2) free_quota_reset='monthly' — 월 경계에서 free_used_count 를 원자적으로 0 리셋한 뒤 판정한다.
    #   (daily 는 daily_free_used_at 날짜플래그라 자동 리셋, none 은 평생 누적.) 리셋+선점은 호출부 커밋에 함께 확정.
    if reset == "monthly" and allow_free_quota:
        auth_service.reset_monthly_free_if_needed(db, user)
    used = user.free_used_count or 0
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


# ── 집중·후속 단일질문(요점만) 분리 ─────────────────────────────────
# [운영자 지적 2026-08-03] '성격 어때?' 같은 단일 후속에 앞말 반복·장황(패딩). 원인=동시 병합의
#   num_predict 6144↑ 가 1차 생성부터 늘어질 여지를 주고, focused 바닥(1,500/1,800)이 억지 분량을
#   강제(=[[answer-length-padding-trap]] '재생성 강제=최악의 패딩원'). 종합 답변은 병합 의도대로 풍부하게
#   두고, 집중·후속만 여지(num_predict)를 줄이고 바닥을 낮춰 '밀도로' 채우게 한다(억지 길이 금지).
#   ⚠️ 400~800자는 과소(운영자) → 바닥 950~1,100(밀도형 근거로 자연히 이 이상), 여지 3072(≈종합의 절반).
_FOCUSED_NUM_PREDICT = 3072


def _focused_floor(depth: str) -> int:
    """집중·후속 단일질문의 소프트 바닥(억지 재생성 패딩 방지) — 종합 바닥과 별개."""
    return 1100 if depth == "deep" else 950


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
    chunks = _retrieve_context(query, k, depth, session_id=session_id, question=message, menu="chat")

    sys_prompt = template_service.get_active_prompt(db)
    dialect = (getattr(user, "answer_dialect", None) or "standard") if user else "standard"
    _is_followup = any(getattr(m, "role", None) == "assistant" for m in (row.messages or []))
    # 집중 주제·단일 후속(요점만) — 1차 생성 여지·바닥을 낮춰 패딩·반복 억제(종합은 풍부하게 유지).
    _is_narrow = bool(_focused_topic_labels(message or "")) or (_is_followup and not _wants_comprehensive(message or ""))
    sys_content = _compose_sys_content(sys_prompt, dialect, explain_level, question=message,
                                       person_name=_display_name(user), is_followup=_is_followup,
                                       has_sources=bool(chunks), depth=depth)
    msgs: list[dict] = [{"role": "system", "content": sys_content}]
    msgs.extend(_history_msgs(row))   # 최근 6턴(이전 답변 발췌) — 잘림·반복 완화
    user_prompt = _build_user_prompt(message, chunks, row.saju_summary,
                                     chart_json=getattr(row, "chart_json", None),
                                     is_male=(getattr(row, "gender", "male") != "female"))
    msgs.append({"role": "user", "content": user_prompt})
    di = _dialect_instruction(dialect)
    chart_evidence = _build_chart_evidence(getattr(row, "chart_json", None))

    # ---- 1차 생성: qwen3:14b(로컬). Ollama 전체 다운 시 Claude 폴백 ----
    local_alive = True
    try:
        # 집중·후속은 여지를 줄여(6144→3072) 1차 생성 늘어짐·반복 억제. 종합은 전역(풍부).
        answer_full = _call_ollama(msgs, num_predict=(_FOCUSED_NUM_PREDICT if _is_narrow else None))
    except ServiceUnavailableError:
        local_alive = False
        # 국외이전 미동의 폴백 차단(H4) — 전역 설정 OFF 또는 회원 미동의면 외부(미국) 전송 안 함.
        if not (settings_service.get_bool(db, "overseas_llm_fallback_enabled", False)
                and getattr(user, "overseas_transfer_opt_in", False)):
            raise
        evidence_text = "\n".join(f"- {e}" for e in chart_evidence) if chart_evidence else None
        # [P3-E3] 손으로 조립하면 EVIDENCE_PRIORITY_RULE(층 경계 — 값은 계산값, 해석은 자료)이
        # 빠진 채 보강·폴백 LLM 에 전달된다. 자료를 주입하는 모든 경로가 같은 규칙을 갖도록
        # 공용 함수로 통일한다(반환 규약 str|None 동일이라 하위 호출부는 그대로).
        rag_context = rag_context_block(chunks)
        fb = external_llm.generate_answer(
            question=message, saju_summary=row.saju_summary,
            evidence=evidence_text, rag_context=rag_context,
            dialect_instruction=di or None,
        )
        if not fb:
            raise  # 로컬·외부 모두 불가 → 원래 503 전파
        answer_full = fb.strip()

    # 답변 분량 가드: 소프트 바닥 미달 시 보강 재시도 (로컬 정상일 때만).
    # [2026-07-31] 심화(deep)는 상향 목표. brief(핵심만)는 미적용. [패딩 검수] 단일주제(집중·후속)는 낮은
    #  안전바닥(1,500/1,800)만 — 강제 재생성 패딩 방지. 종합만 3,000/3,500.
    if explain_level == "brief":
        min_chars = 0
    elif _is_narrow:
        min_chars = _focused_floor(depth)     # 요점만 — 억지 재생성 패딩 방지(밀도로 채움)
    else:
        min_chars = s.answer_min_chars_deep if depth == "deep" else s.answer_min_chars
    retry_max = s.answer_retry_max
    if local_alive:
        for attempt in range(retry_max):
            if len(answer_full) >= min_chars:
                break
            detail_hint = (
                "이야기하듯 쉬운 말로" if explain_level == "easy" else "전문가 본인의 풀이로(자료 인용 표현 없이) 근거와 함께"
            )
            boost = (
                f"\n\n[보강 요청] 이전 답변이 너무 짧습니다({len(answer_full)}자). 최소 {min_chars}자 이상이 "
                f"되도록 {detail_hint} 보강하되, 이전 답변의 문장·논점을 반복·부연·복붙하지 말고 아직 다루지 "
                f"않은 새 근거·각도·구체 사례만 더하세요(도입·결론 복붙 금지, 같은 말 늘리기 금지)."
            )
            boost_msgs = list(msgs) + [
                {"role": "assistant", "content": answer_full},
                {"role": "user", "content": boost},
            ]
            try:
                _boosted = _call_ollama(boost_msgs)
            except Exception:
                break
            # 교체 안전 게이트 — 보강본이 잘렸거나 오히려 짧으면 버리고 원본 유지(무조건 대입 금지).
            # 짧은 원본(<800자)은 _safe_replace 내부 완화비율이 걸리므로 길이 비교를 따로 둔다.
            _bc = _safe_replace(answer_full, _boosted, min_ratio=1.0, hard_floor=True)
            if not (_bc and len(_bc) > len(answer_full)):
                break
            answer_full = _bc

    # ---- 미리보기 컷 여부 ----
    is_preview = bill["is_preview"]

    # ---- 보강 단계: ① 내부 qwen(기본·심화 공통) → ② 외부 Claude(심화 전용) ----
    # 설계: 1차 답변 = RAG + qwen3:14b(로컬 단독). 심화는 그 위에 Claude를 추가 연결(2차 로컬 보강은 현재 비활성).
    evidence_text = "\n".join(f"- {e}" for e in chart_evidence) if chart_evidence else None
    rag_context = rag_context_block(chunks)   # [P3-E3] 층 경계 규칙 포함 공용 조립
    # 미리보기도 풀품질로 생성(표시만 컷) — 비로그인/회원 동일 품질로 신뢰 형성. 표시 컷은 visible에서.
    if local_alive and answer_full.strip():
        qb = _refine_with_qwen(
            question=message, draft=answer_full, saju_summary=row.saju_summary,
            evidence=evidence_text, rag_context=rag_context, dialect_instruction=di or None,
        )
        if qb:
            answer_full = qb
    # 심화 Claude 보강 — 비로그인 미리보기는 비용 절감 위해 제외(qwen까지만). 회원/전체는 적용.
    if depth == "deep" and user is not None and local_alive and answer_full.strip():
        cb = _claude_boost(
            question=message, draft=answer_full, saju_summary=row.saju_summary,
            evidence=evidence_text, rag_context=rag_context, dialect_instruction=di or None,
        )
        if cb:
            answer_full = cb

    # ---- 명식 정합성 검증·교정 (절대규칙: 4주 지지가 명식과 달라지면 깨끗한 컨텍스트로 재생성) ----
    if answer_full.strip():
        # 동문서답(질문 주제 이탈) 백스톱 — 명식교정보다 먼저 돌려 재생성본이 이후 교정·스크럽을 모두 거치게 함.
        answer_full = _correct_nonresponsive(
            answer_full, message, sys_content=sys_content,
            saju_summary=row.saju_summary, chart_json=getattr(row, "chart_json", None),
        )
        answer_full = _correct_chart(
            answer_full, getattr(row, "chart_json", None), question=message,
            sys_content=sys_content, saju_summary=row.saju_summary,
        )
        answer_full = _scrub_self_reference(_scrub_source_refs(answer_full))  # 자료 인용 말투 + AI 자기지칭 다짐 제거
        answer_full = _fix_month_ganji_label(answer_full)  # '을미년'→'을미월'(scrub보다 먼저 — 중화 방지)
        answer_full = _fix_sinnyeon_month_reading(answer_full)  # 'N월(으사월)' 무효독음→그 달 실제 월간지(연도추론)
        answer_full = _fix_relative_year_conflation(answer_full)  # '내년 (올해, 2027년)'→'내년 (2027년)'
        answer_full = _fix_sewoon_daewoon_label(answer_full, getattr(row, "chart_json", None))  # '정미 대운'→'정미 세운'
        answer_full = _scrub_status_presumption(answer_full)  # '고등학생으로 추정' 제거(신분 단정 금지)
        # 최종 재검증: 과거연도·틀린 세운 간지 중화. 질문이 명시한 회고 연도는 보존(파괴 방지).
        answer_full = _scrub_stale_year_ganji(answer_full, allowed_years=_question_target_years(message))
        answer_full = _strip_lead_filler(answer_full)  # 도입부 인사말/예고 제거 — '판정부터' 시작 보장
        answer_full = fix_term_hanja(answer_full)  # 십성 등 한자 병기 정자(正字) 교정(전문가 지적)
        answer_full = _tidy_markdown(answer_full)   # 구분선(---)·과다 빈줄 결정적 제거(무손실)
        # 반복 퇴행(같은 구절 폭주) 최종 가드 — 구제 실패면 ''(→ 아래 빈답변 경로로 환불·미저장)
        answer_full = _correct_degenerate(
            answer_full, sys_content=sys_content,
            base_user=_build_user_prompt(message, [], row.saju_summary,
                                         chart_json=getattr(row, "chart_json", None)))

    # ---- 차감/무료 갱신 ----
    # (홀) 빈 응답(예외 없는 무내용 또는 구제 불가 퇴행) — 선점한 무료/멤버십/pass 를 원복하고 저장·과금하지 않는다.
    if not answer_full.strip():
        _refund_free_claim(db, user, bill)
        db.commit()
        raise ServiceUnavailableError("답변을 생성하지 못했어요. 잠시 후 다시 시도해 주세요.")

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
    """공개 진입점 — 내부 스트림을 감싸 '예상 밖 예외'에서도 선점한 무료/멤버십/패스 슬롯을 보상한다.

    [버그 2026-07-23] 무료·일일무료·멤버십·패스 슬롯은 free-ride 차단을 위해 답변 생성 '전'에
    확정 커밋된다(_claimed_free → db.commit()). 내부가 방어한 4개 분기(RAG 장애·LLM 장애·빈 답변·
    저장 실패) 밖에서 예외가 나면 api/chat.py 의 포괄 except 가 삼켜 슬롯이 그대로 증발했다.
    → 답변을 못 받았는데 무료 1회가 사라진다. 일반회원 무료 N회·일일무료·멤버십·플러스 패스 전부 해당.

    이중환불 방지는 tool_service.stream_message 와 같은 receipt 규약을 쓴다.
    ⚠️ GeneratorExit(클라 이탈)은 보상하지 않고 그대로 올린다 — free-ride 차단 규약.
    """
    receipt: dict[str, Any] = {}
    try:
        yield from _post_message_stream_inner(
            db, session_id, message, top_k, user=user, depth=depth,
            explain_level=explain_level, _receipt=receipt)
    except GeneratorExit:
        raise                       # 클라 이탈 — 정상 종료 경로(선점 유지)
    except Exception as e:  # noqa: BLE001
        if receipt.get("bill") is not None:
            try:
                db.rollback()
                _refund_free_claim(db, user, receipt["bill"])
                db.commit()
            except Exception:  # noqa: BLE001 — 보상 실패가 에러 전달을 막지 않는다
                pass
        import logging as _lg
        _lg.getLogger("saju.chat").warning("chat stream failed(refunded): %s", e)
        yield ("error", {"detail": "답변 처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
                         "code": "internal_error"})


def _post_message_stream_inner(
    db: Session,
    session_id: str,
    message: str,
    top_k: int | None,
    user: User | None = None,
    depth: str = "basic",
    explain_level: str = "normal",
    _receipt: dict[str, Any] | None = None,
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

    # ---- 사전 선택질문(Track B) — 애매한 질문이면 답변 전에 맥락을 묻는다(과금·생성·저장 없음) ----
    # 빌링/생성 전에 단락. 사용자가 선택/건너뛰면 '[상담맥락]'이 붙어 재전송되고 그땐 바로 답한다.
    _cf = _clarify_form(message)
    if _cf:
        yield ("clarify", _cf)
        return

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
    # 버그1(무한무료) 차단: 무료/멤버십 선점을 '생성 전' 즉시 커밋 — 전체 답변을 draft 로 실시간 전달한 뒤
    #   클라가 끊으면 함수 끝의 commit 이 롤백돼 선점이 사라지던 문제. 명시적 생성실패는 아래 error 경로에서 보상 원복.
    _claimed_free = bool(use_free_quota or use_daily_free or use_membership or bill.get("use_pass_free"))
    if _claimed_free:
        # 무료/멤버십/pass 슬롯 orphan(선점 O·답변 X, 크래시) 탐지 앵커 — 선점과 '같은 커밋'에 합류.
        #   persist 에서 finalize_receipt(complete), 에러분기 _refund_free_claim 에서 close_refunded 로 전이.
        from backend.app.services import receipt_service as _rcpt
        bill["receipt_id"] = _rcpt.open_for_bill(
            db, user_id=(user.id if user else None), menu="question", ref_id=session_id, bill=bill, charged=0)
        db.commit()
        # 미정산 선점 등록 — 아래 방어 분기를 벗어난 예외가 나면 래퍼(post_message_stream)가 보상한다.
        if _receipt is not None:
            _receipt.update(bill=bill)

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
    try:
        chunks = _retrieve_context(query, k, depth, session_id=session_id, question=message, menu="chat")
    except Exception as _rag_e:  # noqa: BLE001 — RAG(deep=Qdrant) 장애가 '선점 커밋' 뒤에 나면 토큰루프 try 밖이라
        #   무료/멤버십/pass 선점이 미환불되던 홀(FIX_INCOMPLETE) — 여기서 보상 원복 후 에러 반환.
        if _claimed_free:
            _refund_free_claim(db, user, bill)
            if _receipt is not None: _receipt.clear()   # 자체 보상 완료 — 래퍼의 이중환불 차단
            db.commit()
        _rcode = "service_unavailable" if isinstance(_rag_e, ServiceUnavailableError) else "internal_error"
        yield ("error", {"detail": "답변을 준비하지 못했어요. 잠시 후 다시 시도해 주세요.", "code": _rcode})
        return

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
    _is_followup = any(getattr(m, "role", None) == "assistant" for m in (row.messages or []))
    # 집중 주제·단일 후속(요점만) — 1차 생성 여지·바닥을 낮춰 패딩·반복 억제(종합은 풍부하게 유지).
    _is_narrow = bool(_focused_topic_labels(message or "")) or (_is_followup and not _wants_comprehensive(message or ""))
    sys_content = _compose_sys_content(sys_prompt, dialect, explain_level, question=message,
                                       person_name=_display_name(user), is_followup=_is_followup,
                                       has_sources=bool(chunks), depth=depth)

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
    # 심화 외부(미국) 보강은 국외이전 별도 동의(H4, 제28조의8) 회원만 — 미동의 회원은 내부 보강까지만.
    do_claude = depth == "deep" and _claude_avail and (user is not None) and getattr(user, "overseas_transfer_opt_in", False)
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
            # 집중·후속은 여지를 줄여(6144→3072) 1차 생성 늘어짐·반복 억제. 종합은 전역(풍부).
            for tok in _stream_ollama(msgs, stop_event=stop_event,
                                      num_predict=(_FOCUSED_NUM_PREDICT if _is_narrow else None)):
                tok_q.put(tok)
        except Exception as e:  # noqa: BLE001
            _err["e"] = e
        finally:
            tok_q.put(_SENTINEL)

    producer = threading.Thread(target=_produce, daemon=True)
    producer.start()

    preview_chars = 0
    cut_sent = False
    _tok_since_degen = 0            # 반복 퇴행 조기중단 — 매 40토큰마다 꼬리 점검
    _degen_aborted = False          # 조기중단 발동 여부 — 발동 시 최종본을 강제 재생성(잘린 답 저장 방지)
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
            # 반복 퇴행 조기중단 — 최근 꼬리가 폭주하면 생성을 끊는다(화면·토큰 낭비 최소화;
            # 최종본은 아래 _correct_degenerate 가 교정, 구제 불가 시 환불). repeat_penalty 로 대부분 예방됨.
            _tok_since_degen += 1
            if _tok_since_degen >= 40:
                _tok_since_degen = 0
                _acc = "".join(answer_full_parts)
                if len(_acc) >= 240 and _stream_is_degenerating(_acc[-400:]):
                    _degen_aborted = True
                    stop_event.set()
                    break
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
        # 로컬 Ollama(qwen3:14b) 다운 → Claude 폴백으로 본문 생성 시도
        # 국외이전 미동의 폴백 차단(H4) — 전역 설정 OFF 또는 회원 미동의면 외부(미국) 전송 안 함.
        _fb_allowed = (settings_service.get_bool(db, "overseas_llm_fallback_enabled", False)
                       and getattr(user, "overseas_transfer_opt_in", False))
        rag_context_fb = rag_context_block(chunks)   # [P3-E3] 층 경계 규칙 포함 공용 조립
        evidence_fb = "\n".join(f"- {ev}" for ev in chart_evidence) if chart_evidence else None
        fb = None
        try:
            fb = external_llm.generate_answer(
                question=message, saju_summary=row.saju_summary,
                evidence=evidence_fb, rag_context=rag_context_fb,
                dialect_instruction=di or None,
            ) if _fb_allowed else None
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
            # 로컬·외부 모두 불가 — 친절 메시지 + 코드(클라가 503처럼 처리). 답변 생성 실패 → 선점 무료 보상 원복.
            if _claimed_free:
                _refund_free_claim(db, user, bill)
                if _receipt is not None: _receipt.clear()   # 자체 보상 완료 — 래퍼의 이중환불 차단
                db.commit()
            yield ("error", {"detail": str(e), "code": "service_unavailable"})
            return
        else:
            if _claimed_free:
                _refund_free_claim(db, user, bill)
                if _receipt is not None: _receipt.clear()   # 자체 보상 완료 — 래퍼의 이중환불 차단
                db.commit()
            yield ("error", {"detail": f"ollama stream error: {type(e).__name__}: {e}"})
            return

    answer_full = "".join(answer_full_parts)
    refined = False
    _local_draft_ok = "e" not in _err

    rag_context = rag_context_block(chunks)   # [P3-E3] 층 경계 규칙 포함 공용 조립
    evidence_text = "\n".join(f"- {e}" for e in chart_evidence) if chart_evidence else None

    # ---- ⓪ 분량 바닥(유료·종합 답변 풍부화) ----
    # [2026-07-28] 스트리밍 경로엔 비스트리밍(post_message)에 있던 answer_min_chars 바닥이 없어
    #  초안이 짧으면 그대로 확정됐다(운영자 지적 #7 '유료인데 풍부하지 않다'). 임계 미달이면 1회 보강 재생성.
    # [2026-07-31] 집중·추가질문도 빈약하지 않게 확대(운영자 지시). brief(핵심만)만 제외.
    # [패딩 검수 반영] 재생성 강제는 '최악의 패딩원'이라, 단일주제(집중·후속)는 낮은 안전바닥(1,500/심화 1,800)
    #  만 둔다 — 분량은 프롬프트(밀도형)+실제 근거로 자연히 채우고, 종합 답변만 3,000/3,500 바닥. 미달 시에도
    #  _safe_replace(1.0)로 '더 길고 안 잘린' 경우만 채택 + 보강 프롬프트가 '새 내용만' 요구(부연·복붙 금지).
    _skip_floor = (explain_level == "brief")
    if _is_narrow:
        _min_target = _focused_floor(depth)   # 요점만 — 억지 재생성 패딩 방지(밀도로 채움)
    else:
        _min_target = s.answer_min_chars_deep if depth == "deep" else s.answer_min_chars
    if (_local_draft_ok and answer_full.strip() and not _skip_floor
            and len(answer_full) < _min_target):
        yield ("stage", {"phase": "refining"})
        _detail = ("이야기하듯 쉬운 말로" if explain_level == "easy"
                   else "전문가 본인의 풀이로(자료 인용 표현 없이) 근거와 함께")
        _boost_user = (
            f"\n\n[보강 요청] 이전 답변이 너무 짧습니다({len(answer_full)}자). 물어본 그 주제에 정조준한 채로 "
            f"최소 {_min_target}자 이상이 되도록 {_detail} 보강하되, 이전 답변의 문장·논점을 반복·부연·복붙하지 "
            f"말고 아직 다루지 않은 새 근거·각도·구체 사례·실행 단계만 더하세요(도입·결론 복붙 금지, 같은 말 늘리기 "
            f"금지). 다른 주제로 넓히거나 없는 사실을 지어내지 말고 명식 근거 안에서 새 깊이만 더하세요."
        )
        _boost_msgs = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": _build_user_prompt(
                message, [], row.saju_summary, chart_json=getattr(row, "chart_json", None))},
            {"role": "assistant", "content": answer_full},
            {"role": "user", "content": _boost_user},
        ]
        _bd = None
        for ev in _bg_with_heartbeat(s, lambda bm=_boost_msgs: _call_ollama(bm),
                                     progress_phase="refining"):
            if ev[0] == "result":
                _bd = ev[1]
            else:
                yield ev
        _bc = _safe_replace(answer_full, (_bd or ""), min_ratio=1.0, hard_floor=True)
        if _bc and len(_bc) > len(answer_full):
            answer_full = _bc
            refined = True
            yield ("refine", {"text": _disp(answer_full), "reason": "분량 보강", "evidence": _evi_client})

    # ---- ① 내부 2차 보강(qwen2.5) — 현재 비활성(deep_local_refine_enabled=false). 1차 = qwen3:14b 단독 ----
    if do_qwen and _local_draft_ok and answer_full.strip():
        yield ("stage", {"phase": "draft_done"})
        yield ("stage", {"phase": "refining"})
        qb = None
        for ev in _bg_with_heartbeat(s, lambda af=answer_full: _refine_with_qwen(
                question=message, draft=af, saju_summary=row.saju_summary,
                evidence=evidence_text, rag_context=rag_context, dialect_instruction=di or None)):
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
                evidence=evidence_text, rag_context=rag_context, dialect_instruction=di or None)):
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
        # 동문서답(질문 주제 이탈) 백스톱 — 명식교정보다 먼저(재생성본이 이후 교정·스크럽을 모두 거치게).
        if _verify_nonresponsive(answer_full, message):
            yield ("stage", {"phase": "verifying"})
            _nr = None
            for ev in _bg_with_heartbeat(s, lambda af=answer_full: _correct_nonresponsive(
                    af, message, sys_content=sys_content, saju_summary=row.saju_summary,
                    chart_json=_chart_json_sm), progress_phase="verifying"):
                if ev[0] == "result":
                    _nr = ev[1]
                else:
                    yield ev
            if _nr and _nr.strip() and _nr.strip() != answer_full:
                answer_full = _nr.strip()
                refined = True
                yield ("refine", {"text": _disp(answer_full), "reason": "질문 주제 재정렬", "evidence": _evi_client})
        _gate_bad = _verify_myeongsik(answer_full, _chart_json_sm)
        if _gate_bad:
            yield ("stage", {"phase": "verifying"})
            _fixed = None
            # 게이트 결과를 그대로 전달 — 교정기 진입 직후 동일 배터리 중복 재실행 제거(운영자 지적)
            for ev in _bg_with_heartbeat(s, lambda af=answer_full: _correct_chart(
                    af, _chart_json_sm, question=message, sys_content=sys_content,
                    saju_summary=row.saju_summary, initial_bad=_gate_bad), progress_phase="verifying"):
                if ev[0] == "result":
                    _fixed = ev[1]
                else:
                    yield ev
            if _fixed and _fixed.strip() and _fixed.strip() != answer_full:
                answer_full = _fixed.strip()
                refined = True
                yield ("refine", {"text": _disp(answer_full), "reason": "명식 정합성 자동 교정", "evidence": _evi_client})
        # 자료 인용 말투 제거(전문가 화법) — 바뀌면 교체본 전송
        _scrubbed = _scrub_self_reference(_scrub_source_refs(answer_full))
        if _scrubbed and _scrubbed != answer_full:
            answer_full = _scrubbed
            refined = True
            yield ("refine", {"text": _disp(answer_full), "reason": "표현 정리", "evidence": _evi_client})
        # 월별 흐름 '을미년'→'을미월' + 'N월(으사월)' 무효독음→실제 월간지 + '내년(올해,2027)'→'내년(2027)' 교정
        _ml = _fix_relative_year_conflation(_fix_sinnyeon_month_reading(_fix_month_ganji_label(answer_full)))
        if _ml != answer_full:
            answer_full = _ml
            refined = True
            yield ("refine", {"text": _disp(answer_full), "reason": "월운·연도 표기 정정", "evidence": _evi_client})
        # '정미 대운'→'정미 세운'(세운/대운 혼동 결정적 교정) + '고등학생으로 추정' 신분추정 제거
        _dl = _scrub_status_presumption(_fix_sewoon_daewoon_label(answer_full, _chart_json_sm))
        if _dl != answer_full:
            answer_full = _dl
            refined = True
            yield ("refine", {"text": _disp(answer_full), "reason": "세운·신분 표현 정정", "evidence": _evi_client})
        # 최종 재검증: 과거연도·틀린 세운 간지 중화(스트리밍이라 바뀌면 교체본 전송). 회고 연도는 보존.
        _ts = _scrub_stale_year_ganji(answer_full, allowed_years=_question_target_years(message))
        if _ts and _ts != answer_full:
            answer_full = _ts
            refined = True
            yield ("refine", {"text": _disp(answer_full), "reason": "시점 표현 정리", "evidence": _evi_client})
        # 도입부 인사말/예고 제거 — '판정부터' 시작 보장(모델 무관·결정적, 교체본 전송)
        _lf = _strip_lead_filler(answer_full)
        if _lf != answer_full:
            answer_full = _lf
            refined = True
            yield ("refine", {"text": _disp(answer_full), "reason": "도입 정리", "evidence": _evi_client})

    # 십성 등 한자 병기 정자(正字) 교정(전문가 지적) — 저장/재로드본까지 일관. 표시는 _disp 가 이미 교정.
    answer_full = fix_term_hanja(answer_full)
    answer_full = _tidy_markdown(answer_full)   # 구분선(---)·과다 빈줄 결정적 제거(무손실)

    # 반복 퇴행(같은 구절 폭주) 최종 가드 — 구제되면 교체본 전송, 구제 실패면 ''(→ 아래 빈답변 경로로 환불·미저장)
    # 조기중단(_degen_aborted)으로 끊긴 잘린 답은 보수적 판정에 안 걸려도 강제 재생성(force)한다.
    if answer_full.strip() and (_degen_aborted or _looks_degenerate(answer_full)):
        yield ("stage", {"phase": "verifying"})
        _dg = None
        for ev in _bg_with_heartbeat(s, lambda af=answer_full: _correct_degenerate(
                af, sys_content=sys_content,
                base_user=_build_user_prompt(message, [], row.saju_summary,
                                             chart_json=getattr(row, "chart_json", None)),
                force=_degen_aborted),
                progress_phase="verifying"):
            if ev[0] == "result":
                _dg = ev[1]
            else:
                yield ev
        answer_full = (_dg or "").strip()
        if answer_full:
            yield ("refine", {"text": _disp(answer_full), "reason": "반복 정리", "evidence": _evi_client})

    # (홀3) 빈 응답(Ollama done:true·content="" 등 예외 없는 무내용 또는 구제 불가 퇴행) — 선점한 무료/멤버십/pass
    #   를 보상 원복하고 빈 답변을 저장·과금하지 않는다(무료 소실/빈 미리보기 reveal 과차감 방지).
    if not answer_full.strip():
        if _claimed_free:
            _refund_free_claim(db, user, bill)
            if _receipt is not None: _receipt.clear()   # 자체 보상 완료 — 래퍼의 이중환불 차단
            db.commit()
        yield ("error", {"detail": "답변을 생성하지 못했어요. 잠시 후 다시 시도해 주세요.", "code": "empty_answer"})
        return

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
    try:
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
            commit=False,   # finalize 와 '단일 커밋'으로 원자화(아래 db.commit) — crash 시 메시지+영수증 함께 롤백
        )
        assistant_msg = inserted[-1]
        if _claimed_free:                       # 무료/멤버십/pass 슬롯 영수증 EOF 완결 마킹(persist 커밋에 합류)
            from backend.app.services import receipt_service as _rcpt
            _rcpt.finalize_receipt(db, bill.get("receipt_id"), message_id=getattr(assistant_msg, "id", None))
        db.commit()
    except Exception:  # noqa: BLE001 — 저장/커밋 실패 시 조기 커밋된 무료/멤버십 선점을 보상 원복(답변 미저장).
        if _claimed_free:
            try:
                db.rollback()
                _refund_free_claim(db, user, bill)
                if _receipt is not None: _receipt.clear()   # 자체 보상 완료 — 래퍼의 이중환불 차단
                db.commit()
            except Exception:  # noqa: BLE001
                pass
        yield ("error", {"detail": "답변 저장 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", "code": "internal_error"})
        return

    # 무료 잔여(claim=True 선점이 _decide_billing 에서 이미 반영됨 — 추가 차감 금지)
    free_remaining_after = bill["free_remaining"]
    # done 직전 추천질문 선계산 — 교정·영속 commit 완료 후라 GPU 경합 없고 새 DB 세션이 최신 답변을 읽음.
    prefetch_suggestions_async(session_id)

    visible_len = len(_make_preview(answer_full)) if is_preview else len(answer_full)
    yield ("done", {
        "assistant_message_id": assistant_msg.id,
        "is_preview": is_preview,
        "preview_revealed": not is_preview,
        # 최종 표시본 — 스트림 중 chunk/refine 은 _tidy_markdown(구분선·빈줄 정리) '이전' 텍스트라
        #   화면에 '---'가 남았다(운영자 지적). done 에서 정리·검증 완료된 최종본으로 화면을 재동기화한다.
        #   _disp 로 preview 마스킹을 통과시켜 미리보기 유출 없음. (프론트 done 핸들러가 content 로 교체)
        "content": _disp(answer_full),
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
    """미리보기 메시지 전체 노출. 회원만 가능, 이연차감액(없으면 preview_reveal_cost 설정값) 차감."""
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
            # 전체보기 반환도 목록·재조회 경로와 동일 정리 체인 적용 — 스테일 저장분의 '---'·간지 오표기
            # (2026-07-22 스트립 이전 생성분)이 reveal 시 그대로 노출되던 유일 경로였다(전수감사). 멱등.
            "content": _tidy_markdown(fix_term_hanja(msg.content)),
            "preview_revealed": True,
            "credits_charged": 0,
            "balance_after": bal,
        }

    # (홀2) 빈 미리보기(생성 무내용)를 전체보기해도 과차감하지 않는다 — 무료로 공개 처리(내용 없는데 이연차감 방지).
    if not (msg.content or "").strip():
        msg.preview_revealed = True
        db.commit()
        return {"content": msg.content, "preview_revealed": True, "credits_charged": 0,
                "balance_after": auth_service.get_balance(db, user.id)}

    # 이연 차감액(회원 paid_preview=질문단가). 없으면 폴백(비로그인 유래 미리보기=preview_reveal_cost).
    # ⚠️ 폴백은 관리자 설정(DB app_settings)을 읽어야 함 — config 기본값(500)을 쓰면 실차감이 설정가와 어긋난다.
    deferred = int(getattr(msg, "reveal_cost", 0) or 0)
    cost = deferred if deferred > 0 else settings_service.get_int(db, "preview_reveal_cost")

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
        # 목록·재조회 경로와 동일 정리 체인(멱등) — 스테일 '---'·간지 오표기 노출 차단(전수감사 유일 실경로).
        "content": _tidy_markdown(fix_term_hanja(msg.content)),
        "preview_revealed": True,
        "credits_charged": cost,
        "balance_after": balance_after,
    }
