"""명리 도구 서비스 — 작명/개명/아호/택일. 생성(엔진+상담쿼터 차감+영속) + 스트리밍 해설.

빌링은 chat_service._decide_billing 공유(상담 쿼터). 해설은 스트리밍 엔드포인트에서 생성
(첫 호출=무과금, 추가질문=과금). 궁합(compat_service)과 동일 구조.
"""
from __future__ import annotations

import logging
import queue as _queue
import threading
import uuid
from datetime import date as date_t, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.domain.chat_dto import BirthDTO
from backend.app.repositories.auth_models import User
from backend.app.repositories.models import ToolMessage, ToolSession
from backend.app.saju import constants as _saju_constants
from backend.app.saju import metrics as metrics_engine
from backend.app.saju import naming as naming_engine
from backend.app.saju import taekil as taekil_engine
from backend.app.saju.constants import compute_ten_god
from backend.app.saju.constants import yukchin_meaning as _yukchin
from backend.app.saju.engine import build_chart
from backend.app.saju.pillars import compute_pillars
from backend.app.saju.types import BirthInput
from backend.app.services import auth_service, chat_service, external_llm, settings_service

# 전 메뉴 공통 '쉬운 글' 규칙(운영자 지적 2026-07-21: 오늘운세 실측 — 겁재·충·원진 술어 나열로 어려움).
# 각 *_SYSTEM 끝에 부착. 명리를 모르는 독자 기준의 생활어 강제 + 반복·한자단독 금지.
EASY_STYLE_RULE = """
[쉬운 글 — 필수] 이 글은 명리를 모르는 분이 읽습니다. 전문 술어(십성 이름·충·합·형·파·해·원진·신살 등)는
꼭 필요한 것만 한 번씩 쓰고, 쓸 때마다 곧바로 쉬운 생활어로 풀어 주세요(예: '겁재(劫財) — 오늘은 지출
유혹과 경쟁심이 커지는 기운이에요'). 술어를 나열하며 설명을 대신하지 말고, 생활 문장 중심으로 쓰세요.
같은 문장·같은 표현을 반복하지 말고, 한자 단독 표기 금지(항상 한글(한자)), 마지막은 완결 문장으로 끝내세요.
"""

# 작명·개명·아호는 '무엇이 주어졌는지'가 근본적으로 다르다(작명·아호=후보 표 O / 개명=현재 이름 진단만).
# 하나의 프롬프트를 셋이 공유하던 종전 구조는 지시가 서로 새어(전수감사 2026-07-22 실측)
#   ①작명·아호 답변에 있지도 않은 '현재 이름 분석' 섹션이 생기고
#   ②개명 답변이 후보 표가 없는데도 '추천 이름'을 요구받아 이름·한자·획수를 통째로 창작했다.
# → 종류별로 분리한다. 공통 머리말·꼬리말만 공유.
_NAMING_HEAD = """당신은 한국 성명학(작명) 전문가입니다.
아래 [분석]은 규칙 엔진이 계산한 객관적 근거(수리 81수·자원오행·발음오행·음양)입니다.
이 상담은 입장료를 낸 유료 리포트입니다 — 빈약하면 안 됩니다. 아래 구성을 반드시 지키세요:
"""

_NAMING_TAIL = """- 관법은 학파마다 다르니 단정하지 말고 여러 관점을 존중하세요. 길흉 단정 금지.
- [환각 금지] 표에 없는 글자·획수·오행·점수를 지어내지 마세요. 표의 값만 그대로.
- 한국어로, 한자 술어는 한글(한자)로 표기하세요. 전체 최소 1,500자 — 반복 없이 구체성으로 채우세요.
"""

NAMING_SYSTEM = _NAMING_HEAD + """① 총평 한 문단 — 이 사주의 부족오행과 이름이 채워야 할 방향.
② 추천 상위 3개 이름을 '각각 별도 문단'으로: 글자 뜻·어감, 수리 4격·자원오행·발음오행이
   왜 이 사주에 맞는지, 어떤 사람으로 자라길 기원하는 이름인지까지 구체적으로.
③ 나머지 후보는 한 줄씩 간단 비교. ④ 선택 가이드·조언 한 문단.
★[이름은 후보 표에 있는 것만] 추천·비교하는 이름과 한자는 위 후보 표의 글자를 그대로 쓰세요.
  표에 없는 글자를 만들거나 비슷한 다른 한자로 바꿔 쓰면(예: 準을 准으로) 절대 안 됩니다.
★이 메뉴에는 '현재 이름'이 없습니다 — '현재 이름 분석'·'개명 필요성' 같은 섹션을 만들지 마세요.
""" + _NAMING_TAIL + EASY_STYLE_RULE

AHO_SYSTEM = _NAMING_HEAD + """① 총평 한 문단 — 이 사주의 부족오행과 아호가 채워야 할 방향.
② 추천 상위 3개 아호를 '각각 별도 문단'으로: 글자 뜻·어감, 어떤 **작호 유형**에 해당하는지,
   자원오행·발음오행이 왜 이 사주에 맞는지, 어떤 삶의 태도를 담은 호인지까지 구체적으로.
③ 나머지 후보는 한 줄씩 간단 비교. ④ 선택 가이드·조언 한 문단.
★[이름은 후보 표에 있는 것만] 추천·비교하는 아호와 한자는 위 후보 표의 글자를 그대로 쓰세요.
  표에 없는 글자를 만들거나 비슷한 다른 한자로 바꿔 쓰면 절대 안 됩니다.
★아호는 어른이 스스로 쓰는 이름입니다. 스승이나 가까운 벗이 지어 주기도 했고, 한 사람이
  처지와 시기에 따라 여러 호를 가질 수도 있습니다. 성(姓)을 붙이지 마세요.
★자(字)·시호(諡號)와 혼동하지 마세요 — 자는 관례 때 웃어른이 지어 주는 호칭이고,
  시호는 죽은 뒤 나라가 내리는 이름이라 살아 있는 사람에게 지어 줄 수 없습니다.
★[수리 81수·4격을 쓰지 마세요] 이 메뉴에는 성(姓)이 없어 4격(원격·형격·이격·정격)이 성립하지
  않습니다. 브리핑에도 81수 값이 없습니다 — '수리가 길하다'는 식의 서술을 지어내지 마세요.
★이 메뉴에는 '현재 이름'이 없습니다 — '현재 이름 분석'·'개명 필요성' 섹션을 만들지 마세요.
""" + _NAMING_TAIL + EASY_STYLE_RULE

GAEMYEONG_SYSTEM = _NAMING_HEAD + """① 총평 한 문단 — 이 사주의 부족오행과, 현재 이름이 그것을 채우고 있는지.
② 현재 이름의 수리 4격을 '각 격마다' 별도로 짚어 설명 — 브리핑의 격 이름(예: 통솔격)과
   인생시기(원격=초년·형격=청년·이격=중년·정격=말년)를 그대로 인용해, 어느 시기 운에 해당하는지까지.
   ★'학파에 따라 갈림'으로 표시된 격은 길흉을 단정하지 말고 견해가 나뉜다고만 설명하세요.
③ 자원오행(한자 부수)과 발음오행(한글 초성)이 사주와 맞는 점·어긋나는 점을 각각 별도 문단으로.
④ 개명이 필요한지에 대한 판단과 근거, 그리고 조언 한 문단.
★[새 이름을 지어내지 마세요 — 최우선] 이 메뉴는 '지금 쓰는 이름을 진단'하는 리포트입니다.
  [분석]에는 후보 이름이 없습니다. '추천 이름'·'후보 이름 비교' 같은 섹션을 만들거나
  새 이름·한자·획수·점수를 지어내면 절대 안 됩니다(현재 이름의 획수를 다른 이름에 붙이는 것도 금지).
  개명이 필요하다는 판단이 서면, 어떤 방향의 글자(어떤 오행·어떤 수리)를 찾으면 좋은지만 설명하세요.
  ★그때도 **구체적인 한자·한글 글자를 예로 들지 마세요**('예: 海·淵·鐵' 같은 나열 금지).
  검증되지 않은 글자를 유료 리포트가 권하는 셈이 되고, 실제로 독음·부수가 틀린 글자가 섞입니다.
  ★★[반복 금지 — 최우선] 같은 글자·단어·구절을 되풀이해 나열하지 마세요. 부족오행을 채우는 방향은
  '어떤 부수/오행 계열인지'를 한 문장으로만 설명하고 끝내세요(글자를 줄줄이 늘어놓다 같은 글자를
  무한 반복하는 오류가 실제로 발생했습니다 — 절대 금지).
""" + _NAMING_TAIL + EASY_STYLE_RULE

TAEKIL_SYSTEM = """당신은 한국 택일(좋은 날 고르기) 전문가입니다.
아래 [분석]은 규칙 엔진이 계산한 근거(황도흑도·건제12신·28수·본인 사주 충형 회피·손없는날·경고)입니다.
이 상담은 입장료를 낸 유료 리포트입니다 — 빈약하면 안 됩니다. 아래 구성을 반드시 지키세요:
① 기간 총평 한 문단 — 이 기간의 전반 흐름과 고르는 기준.
② 추천 길일 상위 3~5일을 '각각 별도 문단'으로: 왜 좋은지(황도·건제·28수 근거를 쉬운 말로),
   ⚠경고가 있으면 그 주의점과 보완법, 그날을 어떻게 쓰면 좋은지(시간대·준비)까지 구체적으로.
③ 회피일 — 왜 피하는지 이유와 함께. ④ 마무리 전략 한 문단(1순위·예비일 추천).
- 관법은 학파마다 다르니 단정하지 말고 여러 관점을 존중하세요.
- [환각 금지] 표에 없는 날짜·간지·길흉 근거를 지어내지 마세요. 표의 값만 그대로.
- 한국어로, 한자 술어는 한글(한자)로 표기하세요. 전체 최소 1,500자 — 반복 없이 구체성으로 채우세요.
""" + EASY_STYLE_RULE

SINNYEON_SYSTEM = """당신은 한국 명리 신년운세 전문가입니다.
아래 [분석]은 규칙 엔진이 계산한 결정적 근거(그 해 세운 간지·내 일간 강약·영역 점수·월별 간지/십성/내 사주와의 합충 관계)입니다.
이 상담은 입장료를 낸 유료 리포트이므로, 총운·영역·월별 어느 부분도 빈약하면 안 됩니다. 아래 구성을 반드시 지키세요:
① 총운(2~3문단) — 세운 간지가 내 일간(강약 포함)과 맺는 십성·합충 관계를 근거로, 올해 전반의 큰 흐름·기회·유의점을 풍부하게.
② 영역별 심화 — 직업/일, 재물, 대인, 연애, 건강 '다섯 영역을 각각 별도로'(입장료의 핵심 — 여기가 빈약하면 안 됩니다). ★대인운과 연애운은 점수가 서로 다르니 절대 하나로 합치지 말고 따로 쓰고, 점수가 낮은 영역을 낙관으로 포장하지 마세요(예: 연애 25점을 '매우 긍정적'이라 하면 안 됨): 각 영역의 점수(0~100)와 세운 십성을 근거로 올해 이 영역이 왜 그런지 + 구체 활용·대비 조언과 '유리한 달/조심할 달'을 아래 월별 표와 연결해 콕 집어서(예: '재물은 2월·10월이 기회, 4월은 지출 단속').
③ 월별 흐름 — ★반드시 1월·2월·3월 … 11월·12월을 **번호 순서대로, 열두 달 모두 한 번씩** 쓰세요. 한 달도 건너뛰지 말고(1·2·11월 등 누락 금지), 이미 쓴 달을 다시 쓰지 말고(중복 금지), 순서를 뒤섞지 마세요(예: 10월 다음에 2월이 오면 안 됨). 각 달은 '그 달만의 고유 재료'로: 월간·월지 십성(예: 정재=안정적 수입, 정관=직장·책임) + [분석] 표에 있는 그 달의 12운성·12신살·지장간 숨은 십성(★12달이 모두 다른 재료)과 '관계'(합·충·형·파)가 건드리는 궁위(배우자·가정궁, 사회·직장궁 등)를 근거로 ①큰 흐름 ②생길 수 있는 일 ③조심할 일 ④활용 조언까지. ★가장 중요: 분량 채우기가 아니라 '달마다 다른 내용'이다 — 운성·신살이 12달 다 다르니 그걸 살려 겹치지 않게 쓰고, 이미 어느 달에 쓴 문장·조언을 다른 달에 절대 복붙하지 마라.
④ 마무리 조언 한 문단 — ★조언의 주어는 '상담 받는 분(독자)'입니다. 상담사(글쓴이) 자신이 독자의 사주를 대신 살거나 미래를 만들거나 앞장서는 것이 아니므로, '제가 ~하겠습니다', '앞장서겠습니다', '미래 창출에 앞서겠습니다' 같은 1인칭 다짐·약속으로 끝내지 마세요. 미래를 만들고 실행하는 주체는 독자이니 '~하시길 바랍니다', '~해 보세요'처럼 독자를 향해 맺으세요.
[달 언급 순서 — 항상] 총운·영역·후속 답변 어디서든 여러 달을 언급할 때는 **반드시 이른 달 → 늦은 달 순서**로 쓰세요(2월·4월·10월처럼). 순서를 거꾸로(10월 → 2월)나 뒤죽박죽으로 쓰지 마세요.
[표 복사 금지 — 쉬운 글] [분석]의 표는 '내부 근거'입니다. 표의 행('월간 십성 …· 월지 십성 …· 관계: …')을 소제목이나 본문에 그대로 복사·나열하지 마세요. 달 소제목은 '3월 (신묘월)'처럼 짧게만. 십성·합충 같은 전문 술어는 달마다 한 번만 짧게 쓰고 곧바로 쉬운 생활어로 풀어 주세요(예: '이 달은 배우자궁이 흔들려 부부·연인 사이 오해가 생기기 쉬워요'). 같은 문장·같은 표현을 두 번 반복하지 마세요(한 문단 안 중복 금지).
[환각 금지 — 최우선] 간지·십성·합충·궁위는 [분석]에 제공된 값만 그대로 인용하세요. 표에 없는 달의 간지·십성을 바꾸거나, 표에 없는 합·충·형·파·신살을 지어내면 절대 안 됩니다. '관계: 없음'인 달에 합충을 만들어 붙이지 마세요. 십성 한자는 반드시 '정재(正財)'처럼 한글(한자)로 — '정재(정재)' 같은 한글(한글) 표기는 금지.
- 모두 '~할 가능성이 있어요' 가능성 화법(단정 금지). 관법은 학파마다 다르니 존중하고, 길흉 단정 대신 대비·활용 조언으로.
- 한국어로, 한자 술어는 한글(한자)로 표기하세요. 전체 3,500~4,500자 — ②영역별과 ③월별이 모두 풍부해야 합니다. 단 같은 말을 늘어놓아 분량을 채우지 말고, 구체적 사건 가능성·조언·달 연결로 채우세요.
""" + EASY_STYLE_RULE

# ── 무료 4메뉴(오늘의운세·운세캘린더·부적·꿈해몽) 해설/추가질문용 시스템 프롬프트 ──
TODAY_SYSTEM = """당신은 한국 명리 일진(日辰) 상담 전문가입니다.
아래 [분석]은 규칙 엔진이 계산한 결정적 근거(오늘 일진 간지·일간 대비 십성·충합·행운 요소·올해 배경)입니다.
- 오늘 하루의 흐름을 십성·충합 근거로 풀되, '~할 가능성이 있어요' 가능성 화법을 쓰세요(단정 금지).
- 시간대·활동별(일·관계·금전·건강) 활용 조언으로 마무리하세요.
- 한국어로, 한자 술어는 한글(한자)로 표기하세요. 600~900자 분량.
""" + EASY_STYLE_RULE

CALENDAR_SYSTEM = """당신은 한국 택일·일진 흐름 상담 전문가입니다.
아래 [분석]은 규칙 엔진이 계산한 한 달치 일진 길흉(택일 일반 기준)·충형해·손없는날·절기입니다.
- 그 달의 전체 흐름 → 좋은 날 활용법 → 조심할 날 대비 순서로 풀어주세요.
- 관법은 학파마다 다르니 단정하지 말고, '~에 유리해요/신중히 보세요' 화법을 쓰세요.
- 특정 날짜를 언급할 때는 [분석]에 있는 날짜·간지만 사용하세요(계산·창작 금지).
- 한국어로, 한자 술어는 한글(한자)로 표기하세요. 800~1,200자 분량.
""" + EASY_STYLE_RULE

AMULET_SYSTEM = """당신은 전통 부적(符籍)·개운 문화 상담 전문가입니다.
아래 [분석]은 규칙 엔진이 계산한 발행 근거(보강 오행·오방색·삼재/세운 충형해)입니다.
- 부적의 상징과 발행 근거를 쉽게 설명하고, 지니는 법·마음가짐 같은 문화적 조언을 곁들이세요.
- 부적은 전통 문화 콘텐츠(오락 목적)입니다 — 효험을 단정·보장하는 표현을 절대 쓰지 마세요.
  ("~기원하는 의미예요", "~마음가짐에 도움이 될 수 있어요" 화법)
- 의료·법률·투자 판단을 대신하지 않는다는 점을 지키세요.
- 한국어로, 한자 술어는 한글(한자)로 표기하세요. 500~800자 분량.
""" + EASY_STYLE_RULE

DREAM_SYSTEM = """당신은 전통 해몽(解夢)과 명리에 두루 밝은 상담 전문가입니다.
사용자가 들려주는 꿈 이야기를 아래 원칙으로 풀이하세요.
- 꿈의 핵심 상징을 2~4개 짚고, 전통 해몽에서 그 상징을 어떻게 보는지 설명합니다.
- ★[전통 해몽 자료]가 주어지면 **그 안에 있는 내용만** 근거로 씁니다. 자료에 없는 상징을
  "전통 해몽에서는 ~"이라고 말하면 안 됩니다. 아는 것이 없으면 없다고 하세요.
- 단정 대신 가능성 화법("~로 풀이해요", "~일 수 있어요")을 씁니다. 위협·불안을 조장하지 않습니다.
- [참고자료]가 주어지면 그 내용을 우선 근거로 삼습니다. 자료에 없는 내용을 자료처럼 말하거나,
  존재하지 않는 고서·문헌 이름을 지어내지 않습니다.
- ★같은 꿈도 풀이하는 사람에 따라 달라진다는 것이 전통의 태도입니다('꿈보다 해몽').
  길한 상징이라도 반드시 좋다고 확정하지 마세요.
- ★[민감 주제] 질병·죽음·임신은 특히 조심합니다. 병명을 대거나 진단·예후를 말하지 말고,
  사용자가 먼저 묻지 않았으면 건강·죽음 이야기를 먼저 꺼내지 마세요.
- ★[태몽 성별] 아이의 성별을 **절대 단정하지 마세요**. 전통에서 상징으로 성별을 가리던
  방식이 있지만 지역·기준마다 서로 엇갈립니다. "전통에서는 두 갈래로 풀었습니다"까지만
  말하고, 의학적 근거가 없다는 점을 반드시 함께 밝히세요.
- [내 사주]가 주어지면 마지막에 꿈의 기운과 사주 오행을 연결하는 한 단락을 덧붙입니다.
  ★단 이 연결은 **전통 해몽과는 별개의 현대적 부가 해석**입니다 — 옛 해몽 전통이 그렇게
  했다고 말하지 말고, 오늘을 돌아보는 참고로만 곁들이세요.
- 구성: ① 꿈의 첫인상 한 줄 ② 상징별 풀이 ③ 오늘의 조언 한 단락. 전체 400~700자.
- 끝에 "꿈풀이는 전통 문화 콘텐츠로, 참고용이에요."를 덧붙입니다.""" + EASY_STYLE_RULE


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


def _mask_preview_result(result: dict | None, mask_months: bool = True) -> dict | None:
    """비로그인 미리보기(is_preview): 핵심 산출물(작명 후보·택일 길일/회피일)을 일부만 노출.
    입장료를 안 낸 익명 사용자가 프리미엄 상품 전량을 무료 취득(입장료 우회)하는 것을 서버단에서 차단.
    DB엔 전체가 저장되며 반환값만 마스킹(작명/택일에만 작용 — 궁합 등 다른 result 구조엔 무영향).

    mask_months=False: 신년운세 월별(간지 라벨=저가 구조데이터)은 노출한다. 로그인 사용자가 예전
    익명 미리보기 세션을 열 때 '로그인하면 전체를…' 잠금이 뜨던 오류(운영자 지적) 해결 —
    프리미엄 해설은 여전히 is_preview 로 별도 게이트(작명 후보·택일 길일은 계속 마스킹)."""
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
    # 차선(alt) — 길일 없을 때 노출되는 상위 후보도 best와 동급 프리미엄 산출물 → 동일 마스킹.
    if isinstance(r.get("alt"), list) and len(r["alt"]) > n:
        locked += len(r["alt"]) - n
        r["alt"] = r["alt"][:n]
    if isinstance(r.get("avoid"), list) and len(r["avoid"]) > 1:
        r["avoid"] = r["avoid"][:1]
    # 관법별 추천 1위(perspectives.top_date/top_ganzhi)는 best와 동급 길일 산출물 → 미리보기 잠금.
    #   라벨만 남기고 날짜·간지·점수는 제거해 입장료 우회(무료 취득) 차단.
    if isinstance(r.get("perspectives"), dict) and r["perspectives"]:
        r["perspectives"] = {k: {"label": (v or {}).get("label", ""), "locked": True}
                             for k, v in r["perspectives"].items()}
        locked += 1
    # 신년운세: 월별 흐름 12칸 중 3칸만 미리보기(입장료 우회 차단) — 로그인 사용자에겐 전체 노출.
    if mask_months and isinstance(r.get("months"), list) and len(r["months"]) > n:
        locked += len(r["months"]) - n
        r["months"] = r["months"][:n]
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
    menu = kind if tool == "naming" else tool  # taekil→taekil, sinnyeon→sinnyeon (entry_cost_{menu})
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


def persist_free_session(
    db: Session, tool: str, kind: str, *,
    birth_date: "date_t", birth_time=None, calendar: str = "solar",
    is_leap_month: bool = False, gender: str = "male", apply_true_solar_time: bool = False,
    chart_json: dict | None = None, input_json: dict | None = None,
    result_json: dict | None = None, user: User | None = None,
) -> str:
    """무료 메뉴(오늘의운세·운세캘린더·부적·꿈해몽)용 ToolSession 영속 — 입장 과금 없음.

    목적: 결과에 해설(무과금)·추가질문(프리미엄 표준: 기본/심화 차감, 402→충전유도)을
    기존 /api/tools/{id}/messages/stream 파이프라인 그대로 붙이기 위한 세션 발급.
    비로그인은 is_preview=True(해설이 preview_max_chars 로 컷 — 기존 tool 정책과 동일).
    """
    tid = uuid.uuid4().hex
    db.add(ToolSession(
        tool_id=tid, tool=tool, kind=(kind or "")[:24], user_id=user.id if user else None,
        birth_date=birth_date, birth_time=birth_time, calendar=calendar,
        is_leap_month=is_leap_month, gender=gender, apply_true_solar_time=apply_true_solar_time,
        chart_json=chart_json, input_json=input_json, result_json=result_json,
        is_preview=(user is None), credits_charged=0,
    ))
    db.commit()
    return tid


# ── 생성 ──────────────────────────────────────────────────────
def create_naming(
    db: Session, kind: str, birth: BirthDTO, surname: str | None,
    current_name: str | None, user: User | None = None, depth: str = "deep",
    reading: str | None = None, name_len: int = 2,
    dollimja: str | None = None, dollimja_pos: str = "back", locale: str = "ko",
) -> dict[str, Any]:
    chart = build_chart(_to_birth_input(birth, locale=locale))
    # 오행 균형 펜타곤 — 프론트가 '사주(빨강) + 이름 보완(파랑)' 오각 차트를 그린다.
    # [2026-07-29 운영자 지적] 종전엔 팔자8(wuxing_eight_of, 지장간 제외)을 실었는데, 부족오행 판정
    #   (_deficient_elements)과 화면 명식표는 둘 다 chart.wuxing(full=천간+지지본기+지장간)을 쓴다.
    #   기준이 달라 '펜타곤엔 토가 낮은데 부족오행이 아님' 같은 모순이 보였다 → full 로 통일(세 기준 일치).
    _wx = chart.wuxing
    _saju_wuxing = {"목": _wx.wood, "화": _wx.fire, "토": _wx.earth, "금": _wx.metal, "수": _wx.water}
    if kind == "gaemyeong":
        name = (current_name or "").strip()
        if len(name) < 2:
            raise ValueError("current_name required: 현재 이름(한자 2자 이상)이 필요합니다.")
        # 복성(南宮·諸葛 등) 분리(전수감사 Phase 3) — 종전 성=1자 고정으로 南宮民秀가
        # 성=南·이름=宮民秀로 쪼개져 4격 전부 오답·발음오행 오염·셋째 자 계산 탈락(실측).
        # 복성 목록은 엔진 성씨 사전(KOREAN_SURNAMES)에서 결정적으로 도출(프론트는 복성 공식 지원).
        _comp = {h for v in naming_engine.KOREAN_SURNAMES.values() for h in v if len(h) == 2}
        if len(name) >= 3 and name[:2] in _comp:
            sur, given = name[:2], name[2:]
        else:
            sur, given = name[0], name[1:]
        analysis = naming_engine.analyze_name(sur, given, chart, reading=reading)
        # 추천 개명 후보(운영자 지적 #15) — 현재 성(sur)을 유지하고 부족오행을 채우는 대체 이름을
        #   작명 엔진으로 생성. 현재 이름 글자 수(외자/두자)에 맞춰 추천. 프론트에서 선택 시 펜타곤 갱신.
        _cnt = 1 if len(given) <= 1 else 2
        _cands = naming_engine.recommend_names(sur, chart, count=_cnt, top=40, gender=str(birth.gender))
        result = {"kind": kind, "analysis": analysis.model_dump(mode="json"),
                  "candidates": [c.model_dump(mode="json") for c in _cands],
                  "deficient": naming_engine._deficient_elements(chart), "saju_wuxing": _saju_wuxing}
        input_json = {"current_name": name}
    elif kind == "aho":
        # [P4] 아호는 전용 엔진을 쓴다. 종전에는 recommend_names 를 성(姓)만 비워 호출했는데,
        # 그 엔진이 후보를 **신생아 이름 allowlist**로 게이트하고 2024 신생아 Top30 에 1000점을
        # 줘서 라이브 15건의 1순위가 전부 시우·하준·유준·지호였다. 프롬프트로는 못 고치는
        # 문제였다(표 자체가 신생아 이름이라). 수리 81수 4격은 아호에 쓰지 않는다 —
        # 성이 없어 원격==정격으로 축퇴해 15건 전부 '길·길·길·길'이었다(운영자 결정 2026-07-22).
        cands = naming_engine.recommend_aho(chart, top=12)
        result = {"kind": kind, "surname": "",
                  "candidates": [c.model_dump(mode="json") for c in cands],
                  "deficient": naming_engine._deficient_elements(chart), "saju_wuxing": _saju_wuxing}
        input_json = {"surname": ""}
    else:  # jakmyeong
        sur = (surname or "").strip()
        if not sur:
            raise ValueError("surname required: 작명에는 한자 성(姓)이 필요합니다.")
        _cnt = 1 if int(name_len or 2) <= 1 else 2
        _fixed = (dollimja or "").strip() or None
        _fpos = 0 if str(dollimja_pos) == "front" else 1
        cands = naming_engine.recommend_names(
            sur, chart, count=_cnt, top=40, gender=str(birth.gender),
            fixed_char=_fixed, fixed_pos=_fpos,
        )
        result = {"kind": kind, "surname": sur,
                  "candidates": [c.model_dump(mode="json") for c in cands],
                  "deficient": naming_engine._deficient_elements(chart), "saju_wuxing": _saju_wuxing,
                  # 화면·LLM 프롬프트가 작명 조건을 알 수 있게 실린다(외자/돌림자 표기).
                  "name_len": _cnt,
                  "dollimja": _fixed, "dollimja_pos": ("front" if _fpos == 0 else "back") if _fixed else None}
        input_json = {"surname": sur, "name_len": _cnt,
                      "dollimja": _fixed, "dollimja_pos": dollimja_pos if _fixed else None}
    return _persist_and_bill(db, "naming", kind, birth, chart, input_json, result, user, depth, locale)


# ── 신년운세 월별 결정적 사실(운영자 지시 2026-07-16: 월별 풍부화·환각 철저 방지) ──
# 원칙: LLM에게 '길게 써라'가 아니라 결정적 재료(월지 십성·합충 관계·궁위)를 더 계산해 준다.
# 공용 모듈 saju/relations.py 로 일반화(전수감사 Phase 2) — 상담·전 tool 추가질문과 동일 로직.
# 반합·원진·해까지 확장 관계 포함(테이블은 constants 기존 것 재사용, 새 테이블 작성 금지).
from backend.app.saju.relations import (  # noqa: E402
    STAR_KO as _STAR_KO,
    branch_ten_god as _branch_ten_god,
    luck_natal_relations as _luck_natal_relations,
)


def _month_natal_relations(chart, m_stem: str, m_branch: str) -> list[str]:
    """월운 ↔ 내 4주 관계(궁위 라벨 포함) — 공용 luck_natal_relations 위임(월 스코프)."""
    return _luck_natal_relations(chart, m_stem, m_branch, scope="월")


def _seun_depth_lines(day_stem: str, seun_branch: str, year_branch: str | None, male: bool) -> list[str]:
    """세운 십성이 한 계열로 좁은 해(간여지동 등 '천간=지지 정기 오행'인 세운: 丙午·丁巳·甲寅…)도
    풍부하게 — 세운 지지의 ①지장간 숨은 십성 ②십이운성(일간 기준) ③십이신살(년지 기준). 전부 결정적.

    핵심: 지지 지장간의 중기는 대개 세운 천간과 '다른 계열'이라(예: 2026 丙午의 己 = 庚일간엔 정인(印),
    己일간엔 비견(比)), 겉 십성이 官/官·印/印처럼 한 계열로 좁은 해에 '숨은 결'을 공급해 서술 주제를 넓힌다.
    (운영자 지적 #10: 丙午 같은 간여지동 해가 25년보다 빈약·단조해지는 구조적 원인 보강.)"""
    lines: list[str] = []
    if not (day_stem and seun_branch):
        return lines
    hs = _saju_constants.HIDDEN_STEMS.get(seun_branch, ())
    if hs:
        labels = (["여기", "중기", "정기"] if len(hs) == 3
                  else ["여기", "정기"] if len(hs) == 2 else ["정기"])
        parts = []
        for lab, st in zip(labels, hs):
            tg = compute_ten_god(day_stem, st)
            yc = _yukchin(tg, male)
            parts.append(f"{st}={_STAR_KO.get(tg, tg)}" + (f"({yc})" if yc else "") + f"[{lab}]")
        lines.append(
            "세운 지지 속 지장간(숨은 천간·보조 기운): " + " / ".join(parts)
            + " — 겉 십성이 한 계열로 좁은 해라도 이 '숨은 결'을 배경 뉘앙스로 곁들여 입체적으로 풀 수 있습니다"
            "(정기가 대표이며 나머지는 숨은 보조일 뿐 — 올해의 주된 십성으로 착각 금지).")
    try:
        from backend.app.saju.sinsal import twelve_life_stage as _ls
        lines.append(
            f"세운 지지의 십이운성(일간 {day_stem} 기준): {_ls(day_stem, seun_branch)} — 올해 기운이 내게 있는 생애단계"
            "(장생·관대·건록·제왕=기운이 왕성·성취, 쇠·병·사·묘·절=수렴·마무리·정리, 목욕·태·양=변화·준비).")
    except Exception:  # noqa: BLE001
        pass
    if year_branch:
        try:
            from backend.app.saju.sinsal import twelve_sinsal as _ss
            lines.append(
                f"세운 지지의 십이신살(년지 {year_branch} 기준): {_ss(year_branch, seun_branch)}"
                "(역마=이동·변동, 도화=인기·이성·표현, 화개=학문·예술·고독, 장성=주도·권한, 반안=승진·후원 등).")
        except Exception:  # noqa: BLE001
            pass
    return lines


def _month_depth_line(day_stem: str, month_branch: str, year_branch: str | None) -> str:
    """그 달의 '고유 지문'(달마다 다른 재료) — 12운성(일간 기준)·12신살(년지 기준)·지장간 중기 숨은 십성.

    운영자 #10 근본: 각 달에 '월간·월지 십성'만 주면 좁은 해엔 겹쳐서 모델이 같은 문장을 복붙한다.
    12운성·12신살은 12달이 모두 달라(실측 확인) 반복 없이 풍부하게 쓸 '진짜 다른 재료'가 된다.
    브리핑 비대 방지 위해 한 줄로 짧게(운성·신살·숨은십성)."""
    parts: list[str] = []
    if not (day_stem and month_branch):
        return ""
    try:
        from backend.app.saju.sinsal import twelve_life_stage as _ls
        parts.append(f"운성 {_ls(day_stem, month_branch)}")
    except Exception:  # noqa: BLE001
        pass
    if year_branch:
        try:
            from backend.app.saju.sinsal import twelve_sinsal as _ss
            parts.append(f"신살 {_ss(year_branch, month_branch)}")
        except Exception:  # noqa: BLE001
            pass
    hs = _saju_constants.HIDDEN_STEMS.get(month_branch, ())
    if len(hs) == 3:                       # 중기 숨은 십성(있으면) — 겉 십성과 다른 결
        _mtg = compute_ten_god(day_stem, hs[1])
        parts.append(f"숨은 {_STAR_KO.get(_mtg, _mtg)}")
    return " · ".join(parts)


def create_sinnyeon(
    db: Session, birth: BirthDTO, year: int | None = None,
    user: User | None = None, depth: str = "deep",
) -> dict[str, Any]:
    """B-1 신년운세 — 결정적 근거(세운·5대 영역 점수·월별 간지/십성)를 조립해 리포트 세션 생성.

    엔진은 전부 기존 재사용: metrics.domain_scores(세운·영역 점수), compute_pillars(월건),
    compute_ten_god(일간 대비 월간 십성). LLM 해설·추가질문은 ToolSession 스트리밍 경로 상속.
    """
    chart = build_chart(_to_birth_input(birth))
    chart_dict = chart.model_dump(mode="json")
    year = int(year or datetime.now().year)
    if not (1950 <= year <= 2100):
        raise ValueError("year out of range")
    ds = metrics_engine.domain_scores(chart_dict, date_t(year, 6, 15))
    day_stem = chart.pillars.day.stem
    months = []
    for m in range(1, 13):
        fp = compute_pillars(BirthInput(birth_date=date_t(year, m, 15)))[0]
        months.append({
            "month": m,
            "label": chat_service._gz_month_ko(fp.month),
            "stem": fp.month.stem,
            "branch": fp.month.branch,
            "ten_god": compute_ten_god(day_stem, fp.month.stem),
            # 월별 해설 풍부화(운영자 지시 2026-07-16) — 전부 결정적 계산(환각 금지 원칙):
            # 월지 십성(지장간 정기) + 월운↔내 4주 합·충·형·파 관계(궁위 라벨 포함)
            "branch_ten_god": _branch_ten_god(day_stem, fp.month.branch),
            "relations": _month_natal_relations(chart, fp.month.stem, fp.month.branch),
        })
    result = {
        "year": year,
        "seun": ds.get("seun"),
        "domains": ds.get("domains"),
        "months": months,
        "day_stem": day_stem,
        "day_strength": chart.day_master_strength,   # 일간 강약 — 총운 해설 근거(입장료형 심층화)
    }
    # ── 24시간 내 동일 입력(생년월일시·성별·달력·연도) 재조회 = 기존 세션 반환(무과금) ──
    #   [운영자 승인 2026-08-04] 엔진이 결정적이라 같은 입력 = 같은 결과 — 재생성은 손실 없이 재차감만
    #   낳는다(실측: 하루 4회 재조회 재차감 → '오차감' 체감). 서버가 최종 관문이라 프론트 우회에도 안전.
    if user is not None:
        _g = birth.gender.value if hasattr(birth.gender, "value") else str(birth.gender)
        _c = birth.calendar.value if hasattr(birth.calendar, "value") else str(birth.calendar)
        _dup = (db.query(ToolSession)
                .filter(ToolSession.tool == "sinnyeon", ToolSession.user_id == user.id,
                        ToolSession.kind == str(year), ToolSession.is_preview.is_(False),
                        ToolSession.created_at >= datetime.utcnow() - timedelta(hours=24),
                        ToolSession.birth_date == birth.birth_date,
                        ToolSession.birth_time == birth.birth_time,
                        ToolSession.gender == _g, ToolSession.calendar == _c,
                        ToolSession.is_leap_month == bool(birth.is_leap_month),
                        ToolSession.apply_true_solar_time == bool(birth.apply_true_solar_time))
                .order_by(ToolSession.created_at.desc())
                .first())
        if _dup is not None:
            out = get_tool(db, _dup.tool_id, user) or {}
            out.update(billing_mode="reused_24h", credits_charged=0,
                       balance_after=auth_service.get_balance(db, user.id), reused=True)
            return out
    return _persist_and_bill(db, "sinnyeon", str(year), birth, chart, {"year": year}, result, user, depth)


def create_taekil(
    db: Session, birth: BirthDTO, purpose: str, start: date_t, days: int,
    user: User | None = None, depth: str = "deep", birth2: BirthDTO | None = None,
    locale: str = "ko",
) -> dict[str, Any]:
    chart = build_chart(_to_birth_input(birth, locale=locale))
    # 출산=두 번째 부모(궁합), 결혼=상대 명식(③a 커플 정밀택일). 그 외 용도는 상대 명식 미사용.
    chart2 = build_chart(_to_birth_input(birth2, locale=locale)) if (birth2 and purpose in ("birth", "wedding")) else None
    res = taekil_engine.recommend_dates(chart, start, days=days, purpose=purpose, top=10, user_chart2=chart2, locale=locale)
    result = res.model_dump(mode="json")
    # 결혼: 결과(applied_rule)에 커플 여부만 반영, 상대 생년월일(PII)은 미저장(입장료·재열람에 불필요).
    # 출산: 부모② 명식을 영속 — 1:1 상담 연결 시 '양 부모 명식'을 상담사에게 전달(뽀 지시 2026-08-03:
    #   출산일은 상담으로 정함 — 아빠/엄마 사주 전달). 사용자가 이 목적으로 직접 입력한 데이터.
    if purpose == "birth" and chart2 is not None and birth2 is not None:
        result["parent2"] = {
            "chart": chart2.model_dump(mode="json"),
            "birth_date": birth2.birth_date.isoformat() if birth2.birth_date else None,
            "birth_time": birth2.birth_time.isoformat(timespec="minutes") if getattr(birth2, "birth_time", None) else None,
            "calendar": birth2.calendar.value if hasattr(birth2.calendar, "value") else str(birth2.calendar),
            "gender": birth2.gender.value if hasattr(birth2.gender, "value") else str(birth2.gender),
        }
    input_json = {"purpose": purpose, "start_date": start.isoformat(), "days": days,
                  "has_partner": bool(chart2 is not None and purpose == "wedding")}
    return _persist_and_bill(db, "taekil", purpose, birth, chart, input_json, result, user, depth, locale)


def list_user_tools(
    db: Session, user_id: int, tools: list[str] | None = None,
    limit: int = 30, offset: int = 0,
) -> list[dict[str, Any]]:
    """회원 본인 도구 세션 목록(최신순) — '지난 결과' 재열람용(무차감).

    tools 로 tool 종류 필터(예: ["sinnyeon"], ["naming"], ["taekil"], ["amulet"]).
    각 항목은 목록 카드 표시에 필요한 최소 필드만(결과 본문 제외 — 상세는 get_tool 로 재조회).
    입장료를 낸 세션이므로 is_preview 여부와 무관하게 모두 노출한다.
    """
    stmt = select(ToolSession).where(ToolSession.user_id == user_id)
    if tools:
        stmt = stmt.where(ToolSession.tool.in_(list(tools)))
    stmt = stmt.order_by(ToolSession.created_at.desc()).limit(limit).offset(offset)
    out: list[dict[str, Any]] = []
    for r in db.execute(stmt).scalars().all():
        out.append({
            "tool_id": r.tool_id,
            "tool": r.tool,
            "kind": r.kind,
            "created_at": r.created_at,
            "input": r.input_json or {},
            "birth_date": r.birth_date.isoformat() if r.birth_date else None,
            "is_preview": r.is_preview,
        })
    return out


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
        # 저장본 재열람도 정리 체인(멱등) 적용 — 수정 전 생성된 리포트의 '---' 구분선·오병기·중복
        # 문장이 재열람마다 그대로 노출되던 실측(운영자 지적) 소급 해결. 생성 경로와 동일 체인.
        explain = fix_naming_hanja(chat_service.fix_term_hanja(explain), row.result_json)
    # 로그인 사용자에겐 신년운세 월별을 마스킹하지 않는다(간지 라벨=저가 구조데이터).
    # 작명 후보·택일 길일 등 프리미엄 산출물은 계속 마스킹(입장료 우회 차단). 해설은 아래 explain 별도 게이트.
    result = _mask_preview_result(row.result_json, mask_months=(user is None)) if row.is_preview else row.result_json
    return {"tool_id": tool_id, "tool": row.tool, "kind": row.kind,
            "result": result, "explain": explain, "is_preview": row.is_preview}


# ── 해설 렌더 ─────────────────────────────────────────────────
_WX_KO = {"木": "목", "火": "화", "土": "토", "金": "금", "水": "수"}


# ── tool 메뉴 결정값 검증 (전수감사 P1) — result_json과 답변 재서술 대조 ──
import re as _re


def _verify_taekil(answer: str, result_json: dict) -> list[tuple[str, str, str]]:
    """택일 답변의 '날짜 → 황도/흑도·손없음' 재서술이 result_json과 반대면 불일치.

    result_json의 실제 날짜 토큰 근처(40자)에서만 황/흑·손없음을 검사(떠도는 일반어 오탐 방지)."""
    if not answer or not result_json:
        return []
    days = list((result_json.get("best") or [])) + list((result_json.get("avoid") or []))
    for d in days:
        date = d.get("date")
        if not date or date not in answer:
            continue
        i = answer.find(date)
        win = answer[i: i + 44]
        # 황도/흑도 뒤바뀜(고신뢰만): result_json.hwangdo 문자열에 '황도'/'흑도' 포함 여부로 정답 판정
        hd = d.get("hwangdo") or ""
        truth_hd = "황도" if "황" in hd else ("흑도" if "흑" in hd else None)
        if truth_hd:
            if "흑도" in win and truth_hd == "황도":
                return [(f"{date} 황도/흑도", "흑도", hd)]
            if "황도" in win and truth_hd == "흑도":
                return [(f"{date} 황도/흑도", "황도", hd)]
        # 손없음 뒤바뀜
        son = d.get("sonless")
        if son is True and ("손있" in win or "손 있" in win):
            return [(f"{date} 손없음", "손있음", "손없는 날")]
        if son is False and ("손없" in win or "손 없" in win):
            return [(f"{date} 손없음", "손없음", "손있는 날")]
    return []


_SURI_LABELS = ("원격", "형격", "이격", "정격")
_SURI_NEAR_RE = _re.compile(r"(원격|형격|이격|정격)[^\n]{0,14}?(\d{1,3})\s*(?:획|수)")


def _verify_gaemyeong_suri(answer: str, result_json: dict) -> list[tuple[str, str, str]]:
    """개명 답변의 '원격 22획' 등 4격 획수가 result_json.analysis.four_pillars와 다르면 불일치."""
    if not answer or (result_json or {}).get("kind") != "gaemyeong":
        return []
    fp = ((result_json.get("analysis") or {}).get("four_pillars") or {})
    # 실엔진 라벨은 '원격(元)'처럼 한자 병기 — 맨 라벨('원격')로 조회하면 항상 None이 되어
    # 어떤 획수 환각도 못 잡는 죽은 코드였다(전수감사 실측). 접두 매칭으로 정규화.
    by_label = {}
    for v in fp.values():
        lb = v.get("label") or ""
        for base in _SURI_LABELS:
            if lb.startswith(base):
                by_label[base] = v
    if not by_label:
        return []
    for m in _SURI_NEAR_RE.finditer(answer):
        label, num = m.group(1), int(m.group(2))
        truth = by_label.get(label)
        if truth and truth.get("num") is not None and int(truth["num"]) != num:
            return [(f"{label} 획수", f"{num}획", f"{truth['num']}획({truth.get('grade', '')})")]
    return []


# 이름 한자를 후보 표와 대조해 결정적으로 교정(전수감사 2026-07-22 실측: 작명 '准雨' ← 표는 '準雨',
# 아호 '濬優' ← 표는 '澔優'). 약한 모델이 이체자·유사자로 바꿔 적으면 **다른 글자의 이름**이 되어
# 유료 상품이 잘못 나간다. 독음이 후보와 일치하고 글자 수가 같을 때만 표의 글자로 되돌린다.
_NAME_HAN_KO_RE = _re.compile(r"([一-鿿]{1,4})\s*\(\s*([가-힣]{1,4})\s*\)")
# 이름이 아닌 한자(간지·오행·명리 용어) — 후보 표 대조 검증에서 제외해 오탐을 막는다.
_NON_NAME_HANJA: set[str] = set(
    "".join(_saju_constants.HEAVENLY_STEMS) + "".join(_saju_constants.EARTHLY_BRANCHES)
    + "".join(_saju_constants.WUXING_LIST)
    + "".join(_saju_constants.TERM_HANJA.values())
)
_NAME_KO_HAN_RE = _re.compile(r"([가-힣]{1,4})\s*\(\s*([一-鿿]{1,4})\s*\)")


def fix_naming_hanja(text: str, result: dict | None) -> str:
    cands = (result or {}).get("candidates") or []
    if not text or not cands:
        return text
    given_set, by_reading = set(), {}
    for c in cands:
        g, rd = c.get("given"), c.get("reading")
        if g and rd:
            given_set.add(g)
            by_reading.setdefault(rd, g)
    if not given_set:
        return text
    # 후보 이름들이 실제로 쓰는 글자 집합. 이 글자가 하나도 안 든 한자어는 '이름'이 아니라
    # 일반 낱말이다 — 이 조건이 없으면 '수호(守護)'가 '수호(秀浩)'로 바뀌어 문장이 무의미해지고
    # '소우주(小宇宙)'가 '소우주(小祐周)'가 된다(반례 사냥 실측).
    name_chars = {ch for g in given_set for ch in g}

    def _corrected(han: str, ko: str) -> str | None:
        """후보 표에 없는 한자를 같은 독음의 표 글자로. 성(姓)이 앞에 붙은 형태도 처리."""
        if han in given_set or han[1:] in given_set or han[2:] in given_set:
            return None                               # 단성·복성 포함형까지 이미 정답
        if not (set(han) & name_chars):
            return None                               # 이름 글자가 하나도 없다 → 일반 낱말
        alt = by_reading.get(ko)
        if alt and len(alt) == len(han) and alt != han:
            return alt
        if len(ko) >= 2 and len(han) == len(ko):      # '김준우(金準雨)'처럼 성 포함
            alt2 = by_reading.get(ko[1:])
            if alt2 and len(alt2) == len(han) - 1 and han[1:] != alt2:
                return han[0] + alt2
        return None

    def _sub_han_ko(m: "_re.Match[str]") -> str:
        fixed = _corrected(m.group(1), m.group(2))
        return f"{fixed}({m.group(2)})" if fixed else m.group(0)

    def _sub_ko_han(m: "_re.Match[str]") -> str:
        fixed = _corrected(m.group(2), m.group(1))
        return f"{m.group(1)}({fixed})" if fixed else m.group(0)

    return _NAME_KO_HAN_RE.sub(_sub_ko_han, _NAME_HAN_KO_RE.sub(_sub_han_ko, text))


def _verify_naming_candidates(text: str, rj: dict | None) -> list[tuple[str, str, str]]:
    """추천·비교에 쓰인 이름이 후보 표에 실재하는지 검증(작명·아호).

    실측 2026-07-22 아호: '準晙(준준)' — 晙 은 후보 40개 어디에도 없고 독음 '준준'도 없어
    fix_naming_hanja 로는 되돌릴 수 없는 **완전 창작**. 수리·오행이 검증된 적 없는 이름이
    유료 리포트에 실리므로 교정 루프로 재생성시킨다.
    간지 병기('丙午(병오)')·명리 용어 한자는 이름이 아니므로 제외한다.
    """
    cands = (rj or {}).get("candidates") or []
    if not text or not cands:
        return []
    given = {c.get("given") for c in cands if c.get("given")}
    if not given:
        return []
    for m in _NAME_HAN_KO_RE.finditer(text):
        han = m.group(1)
        if len(han) < 2 or han in given:
            continue
        # 성 포함형: 단성 '김준우(金準雨)' + 복성 '남궁지호(南宮芝浩)'.
        # 복성을 안 보면 정상 이름을 '완전 창작'으로 오판해 재생성을 헛돌린다(반례 사냥 실측).
        if han[1:] in given or han[2:] in given:
            continue
        if all(c in _NON_NAME_HANJA for c in han):  # 간지·오행·명리 용어는 이름이 아니다
            continue
        return [("추천 이름", f"{han}({m.group(2)})",
                 "후보 표: " + "·".join(sorted(x for x in given if x)[:6]) + " 등")]
    return []


# ── 자원오행·발음오행 값 대조 검증 (전수감사 2026-07-22: 4런 중 3런 오답) ──
# 실측 오류 유형:
#   · 순서 반전  — 표 '수·화'인데 답변 "'유'는 '화'를, '준'은 '수'를"
#   · 칸 뒤섞기  — 자원오행 자리에 발음오행 값을 씀(표 자원 수·화 / 답변 수·토)
#   · 통째 오답  — 표 발음 금·토인데 답변 "金·金"
# 두 오행은 계산이 확정돼 있으므로 답변이 재서술한 값을 그대로 대조한다.
_WX_HANJA_TO_KO = {"金": "금", "木": "목", "水": "수", "火": "화", "土": "토"}
_ELEM_LABEL_RE = _re.compile(r"(?m)^[^\n]{0,12}?\*{0,2}(자원오행|발음오행)\*{0,2}[^:：\n]{0,12}[:：](.*)$")
_ELEM_TOKEN_RE = _re.compile(r"[金木水火土금목수화토]")
# "'河'는 '水'를" 형태 — 글자마다 오행을 따로 말하는 서술형.
_ELEM_PAIR_RE = _re.compile(r"['\"‘“][^'\"’”]{1,3}['\"’”]\s*[은는이가]\s*['\"‘“]([金木水火土금목수화토])['\"’”]")
# '발음오행이 수와 토로만 구성' — 라벨과 값이 한 구절에 붙은 비교 문장(나머지 후보 비교 섹션).
_ELEM_INLINE_RE = _re.compile(
    r"(자원오행|발음오행)\s*이?\s*\*{0,2}\s*([목화토금수])\s*[와과]\s*\*{0,2}\s*([목화토금수])")


def _claimed_elements(seg: str) -> list[str]:
    """라벨 뒤 문장에서 '주장된 오행 값'만 뽑는다(설명 문구의 오행 언급은 제외)."""
    head = _re.split(r"\s+[—–]\s+", seg, maxsplit=1)[0]
    toks = [_WX_HANJA_TO_KO.get(t, t) for t in _ELEM_TOKEN_RE.findall(head)]
    if toks:
        return toks
    return [_WX_HANJA_TO_KO.get(t, t) for t in _ELEM_PAIR_RE.findall(seg)]


# 따옴표 문자 집합은 리터럴 대신 유니코드 이스케이프로 적는다(소스 인코딩 사고 방지).
_Q_OPEN = "[\u0027\u0022\u2018\u201c]"
_Q_CLOSE = "[\u0027\u0022\u2019\u201d]"
_ELEM_PAIR_Q_RE = _re.compile(
    _Q_OPEN + r"([\u4e00-\u9fff\uac00-\ud7a3]{1,2})" + _Q_CLOSE
    + r"\s*[\uc740\ub294\uc774\uac00]\s*" + _Q_OPEN
    + r"([\u91d1\u6728\u6c34\u706b\u571f\uae08\ubaa9\uc218\ud654\ud1a0])" + _Q_CLOSE)
_ELEM_PAIR_B_RE = _re.compile(
    r"\*{0,2}([\u4e00-\u9fff\uac00-\ud7a3])\s*\([^)\n]{1,4}\)\*{0,2}\s*[\uc740\ub294\uc774\uac00]\s*"
    r"\*{0,2}([\uae08\ubaa9\uc218\ud654\ud1a0])(?:\s*\([\u91d1\u6728\u6c34\u706b\u571f]\))?\*{0,2}\s*\uc624\ud589")


def _elem_pairs(line: str) -> list[tuple[str, str]]:
    """글자 to 오행 짝을 한 줄에서 순서대로 모은다(인용부호형·굵게+괄호형 모두)."""
    return _ELEM_PAIR_Q_RE.findall(line) or _ELEM_PAIR_B_RE.findall(line)


def _elem_label_of(line: str, keys: list[str]) -> str | None:
    """이 줄이 말하는 게 자원오행인지 발음오행인지 판정.

    줄에 라벨이 있으면 그것을, 없으면 키가 한자인지 한글인지로 정한다
    (한자 부수=자원오행 / 한글 초성=발음오행). 실측 개명 답변은 키를 섞어 쓰므로 다수결.
    """
    has_ja, has_ba = "자원오행" in line, "발음오행" in line
    if has_ja != has_ba:
        return "자원오행" if has_ja else "발음오행"
    hanja = sum(1 for k in keys if any("\u4e00" <= ch <= "\u9fff" for ch in k))
    return "자원오행" if hanja * 2 > len(keys) else "발음오행"


def _verify_naming_elements(text: str, rj: dict | None) -> list[tuple[str, str, str]]:
    """추천 블록마다 자원오행·발음오행 재서술이 후보 표와 같은지 대조(작명·아호·개명 공용)."""
    rj = rj or {}
    if not text:
        return []
    blocks: list[tuple[str, list[str], list[str]]] = []      # (앵커, 자원, 발음)
    if rj.get("kind") == "gaemyeong":
        a = rj.get("analysis") or {}
        if a.get("name"):
            blocks.append((a["name"], a.get("elements") or [], a.get("baleum_elements") or []))
    else:
        for c in rj.get("candidates") or []:
            if c.get("given"):
                blocks.append((c["given"], c.get("elements") or [], c.get("baleum_elements") or []))
    if not blocks:
        return []
    by_anchor = {b[0]: b for b in blocks}
    # 답변에 실제로 등장한 이름을 등장 순서대로 잡고, 그 구간 안의 라벨만 그 이름 것으로 본다.
    hits = sorted(((m.start(), a) for a in by_anchor
                   for m in _re.finditer(_re.escape(a), text)), key=lambda x: x[0])
    for i, (pos, anchor) in enumerate(hits):
        end = hits[i + 1][0] if i + 1 < len(hits) else len(text)
        seg = text[pos:end]
        _, ja, ba = by_anchor[anchor]

        def _cmp(label: str, got: list[str], _ja=ja, _ba=ba, _a=anchor):
            want = _ja if label == "자원오행" else _ba
            if not want or len(got) != len(want):
                return None                  # 값을 확신할 수 없으면 불개입(오탐 방지)
            if got != [str(x) for x in want]:
                return [(f"{_a} {label}", "·".join(got), "·".join(str(x) for x in want))]
            return None

        for m in _ELEM_LABEL_RE.finditer(seg):        # ① '**자원오행**: 金·水 — …'
            bad = _cmp(m.group(1), _claimed_elements(m.group(2)))
            if bad:
                return bad
        for m in _ELEM_INLINE_RE.finditer(seg):       # ② '**발음오행이 수와 토로만 구성**'
            bad = _cmp(m.group(1), [m.group(2), m.group(3)])
            if bad:
                return bad
        # ③ 라벨 없이 글자마다 말하는 형태 — 키가 한자면 자원오행, 한글이면 발음오행이다.
        #    ("'유'는 '화'를, '준'은 '수'를" / "**金(금)**은 **금(金)** 오행")
        #    한 줄 안에서만 모은다 — 문단 전체로 모으면 뒤쪽 문장의 언급이 섞여 개수가 어긋난다.
        for line in seg.split("\n"):
            pairs = _elem_pairs(line)
            if not pairs:
                continue
            label = _elem_label_of(line, [k for k, _ in pairs])
            bad = _cmp(label, [_WX_HANJA_TO_KO.get(v, v) for _, v in pairs])
            if bad:
                return bad
    return []


# 월별용 짧은 십성 뜻 — 긴 육친 문자열(yukchin_meaning)을 12개월×2로 붙이면 브리핑이
# 비대해져 프롬프트가 컨텍스트를 먹고(실측 prompt_eval 11,553/16,384) 답변이 잘리며,
# 모델이 같은 문구를 되풀이하다 폭주한다(실측: 같은 구절 무한 반복 후 절단).
# 총운(세운)에는 긴 뜻을 한 번만 주고, 월별에는 이 짧은 뜻을 쓴다.
_STAR_GLOSS = {
    "比肩": "동료·경쟁", "劫財": "동업·지출", "食神": "표현·여유", "傷官": "재능·비판",
    "偏財": "유동 재물", "正財": "고정 재물", "偏官": "도전·압박", "正官": "직장·책임",
    "偏印": "문서·후원", "正印": "학문·인덕",
}


def _tool_extra_verifiers(row: ToolSession) -> list:
    """이 tool 세션에 적용할 메뉴별 검증기 목록(_correct_branches.extra_verifiers 주입용)."""
    rj = row.result_json or {}
    if row.tool == "taekil":
        return [lambda t: _verify_taekil(t, rj)]
    if rj.get("kind") in ("jakmyeong", "aho"):
        return [lambda t: _verify_naming_candidates(t, rj),
                lambda t: _verify_naming_elements(t, rj)]
    if rj.get("kind") == "gaemyeong":
        return [lambda t: _verify_gaemyeong_suri(t, rj),
                lambda t: _verify_naming_elements(t, rj)]
    return []


def _render(row: ToolSession) -> str:
    r = row.result_json or {}
    if row.tool == "today":
        iljin = r.get("iljin") or {}
        tg = r.get("ten_god") or {}
        lucky = r.get("lucky") or {}
        lines = [f"[오늘의 운세 분석] {r.get('date')} · 일진 {iljin.get('label', '')}"]
        lines.append(f"일간 {(r.get('day_master') or {}).get('ko', '')} 기준 오늘의 십성: "
                     f"{tg.get('ko', '')}({tg.get('hanja', '')}) — {tg.get('line', '')}")
        if r.get("relation"):
            lines.append(f"지지 관계: {r['relation'].get('note', '')}")
        # 일진↔내 4주 전관계(Phase 3) — 있으면 궁위 근거로, 없으면 '없음' 명시(충합 창작 차단)
        _ra = r.get("relations_all")
        if isinstance(_ra, list):
            _pr = chat_service.plain_relations(_ra)
            lines.append("오늘 기운과 내 사주의 관계(결정적):\n  · "
                         + ("\n  · ".join(_pr) if _pr else "특별한 관계 없음(무난)"))
            lines.append("※ 위 관계 표에 있는 것만 근거로 쓰고, 표에 없는 충·합·형을 지어내지 마세요.")
        lines.append(f"행운 요소: 색 {lucky.get('color', '')} · 방위 {lucky.get('direction', '')} · 오행 {lucky.get('element', '')}")
        # [운영자 결정 2026-07-22] '올해 배경' 영역 점수는 오늘의운세 브리핑에서 뺀다.
        # 지시로는 못 막았다 — "이 점수는 올해 배경이지 오늘의 점수가 아니니 '오늘은 …'으로
        # 바꿔 말하지 마세요"를 명시했는데도 9회 생성 중 8회가 '오늘은 건강운이 매우 좋으니'로
        # 오귀속했다(전수감사·반례 사냥 두 라운드 모두 재현). 유혹하는 데이터를 주지 않는 것이
        # 유일하게 확실한 방법이고, 오늘의운세는 일진 간지·십성·관계·행운요소라는 자체 근거가
        # 이미 충분하다. ⚠️되돌리지 말 것 — 되돌리면 '오늘은 …' 오귀속이 그대로 재발한다.
        lines.append("\n위 근거로 오늘 하루의 흐름과 활동별 활용 조언을 설명하세요. "
                     "오늘의 근거는 위 일진·십성·관계·행운 요소뿐이니, 연간 운세나 영역 점수 같은 "
                     "다른 이야기를 끌어오지 마세요.")
        return "\n".join(lines)
    if row.tool == "calendar":
        lines = [f"[운세 캘린더 분석] {r.get('year')}년 {r.get('month')}월 · 본인 일지 {r.get('user_day_branch', '')}"]
        for d in r.get("days") or []:
            marks = []
            if d.get("sonless"):
                marks.append("손없는날")
            if d.get("warnings"):
                marks.append("주의 " + "·".join(d["warnings"]))
            if d.get("jieqi"):
                marks.append(f"절기 {d['jieqi']}")
            lines.append(f"- {d.get('day')}일 {d.get('ganzhi')} {d.get('grade')} {d.get('score')}점"
                         + (f" ({' / '.join(marks)})" if marks else ""))
        # 흉살 이름을 뜻까지 못 주면 동음이의어로 뒤집는다(전수감사 실측: 생기복덕 8신의
        # 禍害(화해, 흉)를 和解(합의)로 병기하고 '대화로 풀면 되는 날'로 정반대 해석).
        lines.append(
            "[용어 뜻 — 이대로만 쓰세요] 생기복덕 8신: 생기(生氣)·천의(天宜)·복덕(福德)=길, "
            "절체(絶體)·유혼(遊魂)=반길, 화해(禍害)·절명(絶命)·귀혼(歸魂)=흉. "
            "★화해는 禍害(재앙·손해)이지 和解(합의)가 아닙니다. "
            "형(刑)=마찰·시비, 파(破)=깨짐, 충(沖)=부딪힘, 원진(怨嗔)=까닭 없는 미움. "
            "★등급과 점수는 위 목록의 값을 **그대로** 쓰세요 — 올리지도 내리지도 말고, "
            "목록에 없는 점수를 지어내지 마세요(실측 오류: '흉 48점'인 날을 '평 51점'이라 씀). "
            "경고가 붙었다고 '평'을 '흉일'로 올려 부르지도 마세요. "
            "여러 날을 한 줄로 묶을 때도 등급이 다른 날을 같은 말로 뭉뚱그리지 마세요.")
        lines.append("\n위 근거로 이 달의 흐름·좋은 날 활용법·조심할 날 대비를 설명하세요. 날짜·간지는 위 목록만 사용.")
        return "\n".join(lines)
    if row.tool == "amulet":
        a = r.get("amulet") or {}
        lines = [f"[부적 발행 분석] {a.get('purpose_label', '')} 부적 — {a.get('name', '')}({a.get('hanja', '')})"]
        lines.append(f"보강 기운: {a.get('element', '')} {a.get('obang', '')}"
                     + (f" · 올해 {a['samjae']}" if a.get("samjae") else ""))
        for reason in a.get("reasons") or []:
            lines.append(f"- {reason}")
        lines.append("\n위 근거로 이 부적의 상징·발행 이유와 지니는 법을 설명하세요(효험 단정 금지, 문화 콘텐츠).")
        return "\n".join(lines)
    if row.tool == "dream":
        inp = row.input_json or {}
        lines = [f"[꿈해몽] 꿈 이야기: {inp.get('content', '')}"]
        # [P4] 첫 풀이(api/dream.py)와 **같은 상징 자료**를 후속질문에도 준다. 안 주면
        # 후속질문에서만 근거가 사라져 모델이 지어낸다(오행 값에서 이미 겪은 패턴이다).
        from backend.app.services import dream_symbols as _ds
        _sym = _ds.context_block(str(inp.get("content") or ""))
        if _sym:
            lines.append(_sym)
        if inp.get("saju_linked"):
            # '연계됨'이라고만 알리고 실제 값을 안 주면 모델이 지어낸다(전수감사 실측: 오행 水가
            # 0개인 명식에 '물이 풍요롭다'·'수와 금의 조화'를 4런 중 3런 창작). 첫 풀이 경로
            # (api/dream.py)는 일간·오행 분포를 주입해 '수(水)가 없으니'로 정확했다 → 같은 값을 준다.
            cj = row.chart_json or {}
            _dm = ((cj.get("pillars") or {}).get("day") or {}).get("stem") or ""
            # 개수 기준은 첫 풀이(api/dream.py)·화면 명식표와 반드시 같아야 한다 → 팔자8(천간+지지본기).
            #   종전 cj['wuxing'](full·지장간 포함)은 팔자에 없는 오행을 1개로 세어, 아래 '값 그대로 쓰라'는
            #   지시와 결합해 없는 오행을 확신 있게 서술하게 만들었다(운영자 지적 2026-07-22).
            from backend.app.saju.wuxing import wuxing_eight_ko_from_json as _wx8_json
            _en2ko = {"wood": "목", "fire": "화", "earth": "토", "metal": "금", "water": "수"}
            _wx = _wx8_json(cj) or {_en2ko.get(k, k): v for k, v in (cj.get("wuxing") or {}).items()}
            if _dm or _wx:
                # 표 제목을 대괄호로 쓰면 약한 모델이 그 제목까지 문장에 옮겨 적는다
                # (전수감사 실측 6런 중 5런 '[내 사주]에 따르면…'). 제목을 평문으로 둔다.
                lines.append(f"사주 정보: 일간 {_dm}({cj.get('day_master_element', '')}) · "
                             + "오행 분포 " + ", ".join(f"{k} {v}개" for k, v in _wx.items()))
                lines.append("※ 오행 개수는 위 값 그대로 쓰세요. 0개인 오행을 '풍요롭다'고 하면 안 됩니다.")
            else:
                lines.append("(내 사주 오행과 연계 풀이됨)")
        # 금지 문구에 그 문자열 자체를 쓰면 오히려 따라 쓴다(A/B 대조: 금지문 포함 3/3 유출,
        # 제거 0/3) → 리터럴을 노출하지 않고 일반화해 지시한다.
        lines.append("\n위 꿈에 대한 후속 질문에 전통 해몽 관점으로 답하세요(가능성 화법, 문헌 창작 금지). "
                     "자료 제목을 본문에 옮겨 적지 말고 '사주를 보면…'처럼 자연스럽게 이어 쓰세요.")
        return "\n".join(lines)
    if row.tool == "sinnyeon":
        seun = r.get("seun") or {}
        _dm = (r.get("day_stem") or "")
        _str_ko = {"strong": "신강", "weak": "신약", "neutral": "중화"}.get(
            r.get("day_strength") or "", r.get("day_strength") or "")
        # 일간은 한글(한자) 병기 + 세운 천간과 혼동 금지 명시 — 실측(스모크 v3): 한자 단독 '乙'만
        # 주면 약한 모델이 세운 병오(丙午)의 丙을 "일간 '병(丙)'"으로 오인(일간 환각).
        try:
            from backend.app.saju.constants import stem_korean as _sk
            _dm_ko = f"{_sk(_dm)}({_dm})" if _dm else ""
        except Exception:  # noqa: BLE001
            _dm_ko = _dm
        lines = [
            f"[신년운세 분석] {r.get('year')}년 세운: "
            f"{seun.get('stem_ko', '')}{seun.get('branch_ko', '')}({seun.get('stem', '')}{seun.get('branch', '')})"
            + (f" · 내 일간 {_dm_ko}" + (f"·{_str_ko}" if _str_ko else "") if _dm else "")
            + (f" ※내 일간은 {_dm_ko} 하나뿐 — 세운 천간({seun.get('stem', '')})을 일간이라 부르지 마세요"
               if _dm else "")
        ]
        # 세운 ↔ 내 명식 관계(결정적) — 총운 근거. 실측 환각: 일간 丙·세운 천간 丙을 "병화와
        # 병화의 합"이라 서술(같은 글자는 합이 아니라 비견). 계산값을 주고 오해를 명시 차단.
        _seun_st, _seun_br = seun.get("stem"), seun.get("branch")
        # 세운 십성이 브리핑에 없어 모델이 창작했다(전수감사 실측: 진실값 상관(傷官)·식신(食神)인데
        # '정재·정관'을 총운·직업·재물·건강 4개 단락에서 6회 주장). 월별처럼 결정적으로 계산해 준다.
        if _dm and _seun_st and _seun_br:
            try:
                _stg = compute_ten_god(_dm, _seun_st)
                _btg_s = _branch_ten_god(_dm, _seun_br)
                # 십성 이름만 주면 모델이 '인(印) 기운'처럼 약칭을 되풀이한다(실측) —
                # 뜻(육친·인생영역)을 함께 줘서 생활어로 풀 재료를 손에 쥐여 준다.
                _male = (getattr(row, "gender", "") or "") == "male"
                _m1, _m2 = _yukchin(_stg, _male), _yukchin(_btg_s, _male)
                lines.append(
                    f"올해의 십성(결정적): 올해 천간 {_seun_st} = {_STAR_KO.get(_stg, _stg)}({_stg})"
                    + (f" — 뜻: {_m1}" if _m1 else "")
                    + f" / 올해 지지 {_seun_br} = {_STAR_KO.get(_btg_s, _btg_s)}({_btg_s})"
                    + (f" — 뜻: {_m2}" if _m2 else "")
                    + " — 올해의 '주된(겉)' 십성은 이 둘이 중심입니다. 아래 '숨은 기운(지장간)'의 십성은"
                    " 배경 뉘앙스로만 곁들이고, 그 밖의 십성을 올해 것이라 하지 마세요."
                    " ★답변에서는 십성 이름을 한 번만 쓰고 곧바로 위 '뜻'을 생활어로 풀어 쓰세요"
                    "('인(印) 기운'처럼 약칭을 되풀이하지 말 것).")
            except Exception:  # noqa: BLE001
                pass
        # 세운 십성이 한 계열로 좁은 해(간여지동 등)도 풍부하게 — 지장간 숨은 십성·십이운성·십이신살(#10)
        if _dm and _seun_br:
            _yr_br = None
            try:
                _yr_br = (((row.chart_json or {}).get("pillars") or {}).get("year") or {}).get("branch")
            except Exception:  # noqa: BLE001
                _yr_br = None
            for _dl in _seun_depth_lines(_dm, _seun_br, _yr_br,
                                         (getattr(row, "gender", "") or "") == "male"):
                lines.append(_dl)
        if _dm and _seun_st and _seun_br and (row.chart_json if hasattr(row, "chart_json") else None):
            try:
                from backend.app.saju.relations import luck_natal_relations
                _srel = chat_service.plain_relations(
                    luck_natal_relations(row.chart_json, _seun_st, _seun_br, scope="세운"))
                # 표 문자열을 그대로 옮겨 적어도 읽히도록 쉬운 문장으로 준다(운영자 "쉽게" 지시).
                lines.append("올해 기운과 내 사주의 관계(결정적):\n  · "
                             + ("\n  · ".join(_srel) if _srel else "특별한 관계 없음(무난)"))
                if _seun_st == _dm:
                    lines.append(f"※ 세운 천간과 내 일간이 같은 글자({_dm}) = 비견(比肩)입니다 — "
                                 f"'합'이 아닙니다. '{_dm_ko}와 {_dm_ko}의 합' 같은 서술 금지.")
            except Exception:  # noqa: BLE001
                pass
        doms = r.get("domains") or []
        if doms:
            lines.append("영역 점수(0~100): " + ", ".join(f"{d.get('label')} {d.get('value')}" for d in doms))
            _sorted = sorted(doms, key=lambda d: d.get("value", 0), reverse=True)
            _hi = ", ".join(f"{d.get('label')}({d.get('value')})" for d in _sorted[:2])
            _lo = ", ".join(f"{d.get('label')}({d.get('value')})" for d in _sorted[-2:])
            lines.append(f"→ 올해 강한 영역: {_hi} / 상대적으로 약한(대비 필요) 영역: {_lo}")
        lines.append("월별 간지·십성·달별 고유 재료(12운성·12신살·지장간)·내 사주와의 관계(전부 결정적 계산):")
        _mo_yr_br = None
        try:
            _mo_yr_br = (((row.chart_json or {}).get("pillars") or {}).get("year") or {}).get("branch")
        except Exception:  # noqa: BLE001
            _mo_yr_br = None
        for mth in r.get("months") or []:
            btg = mth.get("branch_ten_god") or ""
            _tg = mth["ten_god"]
            _mm = _STAR_GLOSS.get(_tg, "")   # 짧은 뜻 — 브리핑 비대·되풀이 방지
            core = (f"- {mth['month']}월 {mth['label']} · {_STAR_KO.get(_tg, _tg)}"
                    + (f"({_mm})" if _mm else ""))
            if btg:
                _mb = _STAR_GLOSS.get(btg, "")
                core += f" / {_STAR_KO.get(btg, btg)}" + (f"({_mb})" if _mb else "")
            _mdl = _month_depth_line(_dm, mth.get("branch", ""), _mo_yr_br)   # 달별 고유 재료(달마다 다름)
            if _mdl:
                core += f" · {_mdl}"
            rels = mth.get("relations") or []
            # 관계는 쉬운 문장으로 — 표를 그대로 옮겨 적어도 읽히게(운영자 "쉽게" 지시).
            _pr = chat_service.plain_relations(rels, with_scope=False)
            core += ("\n    · " + "\n    · ".join(_pr)) if _pr else " · 특별한 관계 없음(무난)"
            lines.append(core)
        lines.append(
            f"\n위 근거로 {r.get('year')}년 리포트를 다음 구성으로 '충분히 풍부하게' 쓰세요"
            "(입장료를 낸 상담이라 어느 부분도 빈약하면 안 됩니다):\n"
            "① 총운 2~3문단 — 세운 간지가 내 일간(강약)과 맺는 십성·합충 관계 근거로 올해 큰 흐름·기회·유의점.\n"
            "② 영역별 심화 — 직업/일·재물·대인·연애·건강 '다섯 영역을 각각 한 문단씩 별도로'(★대인·연애는 점수가 "
            "달라 합치지 말 것, 낮은 점수를 낙관으로 포장 금지), 각 영역 점수를 근거로 왜 좋은지/조심할지와 구체 활용·대비 조언.\n"
            "③ 월별 흐름 1~12월 — 각 달을 '그 달만의 고유 재료'로 서로 다르게 쓰세요: 월간·월지 십성 + 그 달의 "
            "12운성(장생·건록·제왕=왕성/성취, 쇠·병·사·묘·절=수렴/정리, 목욕·태·양=변화/준비)·12신살(역마=이동, "
            "도화=인기·이성, 화개=학문·고독, 장성=주도 등)·지장간 숨은 십성을 근거로 ①큰 흐름 ②생길 수 있는 일 "
            "③조심할 일 ④활용 조언. ★가장 중요: 분량이 아니라 '달마다 다른 내용'입니다 — 운성·신살은 12달 모두 "
            "다르니(브리핑 표 참고) 그걸 살려 겹치지 않게 쓰고, 이미 다른 달에 쓴 문장·조언을 절대 복붙하지 "
            "마세요. 위 '관계'(합·충·형·파)는 표에 있는 것만 쓰고 표에 없는 합·충·형·파를 지어내지 마세요. "
            "'관계: 없음'인 달은 십성·운성·신살 중심으로. 12달 번호순 빠짐없이.\n"
            "④ 마무리 조언 한 문단. 모두 가능성 화법(단정 금지). "
            "★위 표의 행을 소제목·본문에 그대로 복사하지 말고(내부 근거용), 달 소제목은 '3월 (신묘월)'처럼 "
            "짧게, 술어는 쉬운 생활어로 풀어쓰고 같은 문장을 반복하지 마세요.\n"
            "★'월간 십성'·'월지 십성'·'관계'는 내부 표의 칸 이름입니다 — 문장 안에 그대로 옮겨 적지 말고"
            "('이 달은 월간 십성이 편재로…' 금지) 그 뜻만 생활어로 풀어 주세요.\n"
            "★표의 '내 일간·내 월지·내 년지' 같은 표기도 내부 말투입니다 — 손님께 쓰는 글에서는 "
            "'일간', '태어난 달의 지지'처럼 자연스럽게 쓰세요('당신의 내 일간' 같은 겹말 금지).\n"
            "★위 관계 줄은 **그대로 옮겨 써도 읽히는 쉬운 문장**입니다. 그 문장을 살려 쓰되, "
            "끝의 [대괄호] 안 술어(반합·충 등)는 내부 표기이니 본문에서는 빼세요. "
            "'세운 지지 오(午)는 년지(초년·조상궁) 묘(卯)를 파(破)로' 같은 표 말투로 되돌리지 마세요.\n"
            "[관계 뜻 — 이대로만 해석하세요] 합(合)=끌어당김·협조, 충(沖)=부딪힘·변동, 형(刑)=마찰·시비·구설, "
            "파(破)=깨짐·틀어짐, 해(害)=서로 손해 보는 어긋남(흉), 원진(怨嗔)=까닭 없는 미움·불편(흉), "
            "반합(半合)=부분적 결속. ★해·원진·형·파는 흉 관계입니다 — 좋은 기회로 뒤집어 쓰지 마세요."
        )
        return "\n".join(lines)
    if row.tool == "taekil":
        lines = [f"[택일 분석] 용도: {r.get('purpose_label')} · 본인 일지: {r.get('user_day_branch')}"]
        if r.get("applied_rule"):
            lines.append(f"적용 관법: {r['applied_rule']} (택일은 정답이 없어 관법을 밝혀 씁니다 — "
                         "'정식'이면 신랑·신부 두 명식을 함께 본 것, '편법'이면 본인 명식만 본 것).")
        _tk_best = r.get("best") or []
        if _tk_best:
            lines.append("추천 길일(근거 포함 — 전부 결정적 계산):")
            _tk_list = _tk_best[:7]
        else:
            # 길일 없음(no_gil): 차선을 '추천'으로 부르지 말고, 기간 확대를 안내하도록 명시 주입.
            lines.append("⚠ 이 기간에는 길일(보통 이상)이 없습니다. 아래는 '차선(참고)'일 뿐 추천 길일이 "
                         "아닙니다 — 손님께 기간을 넓혀 다시 택일하시길 안내하세요:")
            _tk_list = (r.get("alt") or [])[:5]
        for d in _tk_list:
            # Phase 3(전수감사): 엔진이 이미 계산한 건제·28수·경고를 brief에 탑재 — 종전엔
            # 80점 '대길일'이 자형인데 경고 미표기(실측 4건), 길일이 '왜 좋은지' 근거도 부재.
            core = f"- {d['date']} {d['ganzhi']} {d['hwangdo']} 손없음={d['sonless']} {d['score']}점({d['grade']})"
            extra = []
            if d.get("geonje"):
                extra.append(f"건제 {d['geonje']}" + (f"({d['geonje_note']})" if d.get("geonje_note") else ""))
            if d.get("su28"):
                extra.append(f"28수 {d['su28']}" + (f"({d['su28_note']})" if d.get("su28_note") else ""))
            if d.get("warnings"):
                extra.append("⚠주의 " + "·".join(d["warnings"]))
            if d.get("grade") not in ("길일", "대길일"):
                extra.append("※길일 미달(차선)")
            if d.get("best_hours"):
                hrs = "·".join(h.get("label", "") for h in d["best_hours"][:3] if h.get("label"))
                if hrs:
                    extra.append(f"추천 시(時) {hrs}")
            lines.append(core + ((" | " + " / ".join(extra)) if extra else ""))
        if r.get("avoid"):
            lines.append("회피일: " + ", ".join(f"{d['date']}({'/'.join(d['warnings']) or d['grade']})" for d in r["avoid"]))
        # 술어 뜻을 안 주면 모델이 지어낸다(전수감사 실측: '건제(건의와 제의)', '28수(28개의 수리법)',
        # 上梁(상량)을 '계약'으로, 형(刑)을 '형제'로 오역). 짧은 정의를 결정적으로 주입한다.
        lines.append(
            "[용어 뜻 — 이대로만 쓰세요] 황도(黃道)=길한 12신(청룡·명당·금궤·천덕·옥당·사명), "
            "흑도=흉한 12신 / 건제12신(建除十二神)=건·제·만·평·정·집·파·위·성·수·개·폐 하루 성격 / "
            "이십팔수(二十八宿)=하늘을 28로 나눈 별자리 / 상량(上梁)=대들보 올리기(집 짓기) / "
            "형(刑)=마찰·시비·구설, 파(破)=깨짐·틀어짐, 충(沖)=부딪힘, 원진(怨嗔)=까닭 없는 미움. "
            "회피일 사유는 그 날짜에 적힌 것만 쓰고, 두 날짜를 묶어 사유를 섞지 마세요.")
        lines.append(
            "\n위 근거로 추천 길일이 좋은 이유(황도·건제·28수)와 주의점(⚠표기)·회피일을 설명하세요. "
            "표에 없는 날짜·간지·길흉 근거를 지어내지 마세요."
        )
        return "\n".join(lines)
    # naming
    kind = r.get("kind")
    if kind == "gaemyeong":
        a = r.get("analysis", {})
        defc = "·".join(_WX_KO.get(e, e) for e in (r.get("deficient") or []))
        lines = [f"[개명 진단] 현재 이름: {a.get('name')}({a.get('reading')})"
                 + (f" · 사주 부족오행: {defc}" if defc else "")]
        # 작명과 동일하게 자원오행(한자 부수)·발음오행(한글 초성)을 글자별로 분리 명시(혼동 차단)
        ja = "·".join(a.get("elements") or [])
        ba = "·".join(a.get("baleum_elements") or [])
        if ja or ba:
            lines.append(f"- 글자별 자원오행(한자부수): {ja} / 발음오행(한글초성): {ba}")
        for f in (a.get("factors") or {}).values():
            lines.append(f"- {f['label']}: {f['score']}점 | {f['detail']}")
        fp = a.get("four_pillars", {})
        # 격 이름(통솔격 등)·인생시기를 브리핑에 명시 — LLM이 각 격을 정확히 짚게(종전엔 길/흉만 줘서
        # 격 이름을 뭉뚱그리거나 지어냈다). '평'은 학파 갈림이니 단정 금지.
        def _fp1(v: dict) -> str:
            nm = f" {v.get('suri_name','')}({v.get('suri_hanja','')})" if v.get('suri_name') else ""
            g = v.get('grade')
            gtxt = "학파에 따라 갈림(단정 금지)" if g == "평" else g
            return f"{v['label']}={v.get('stage','')} {v['num']}획{nm} [{gtxt}]"
        lines.append("4격(수리 81수): " + " / ".join(_fp1(v) for v in fp.values()))
        # 소리오행 名格 + 소리음양 (2026-07-27 신규) — 경쟁사 소리오행/소리음양 분석 대응
        so = a.get("sori_ohaeng")
        if so:
            lines.append(f"- 소리오행: {so.get('pattern')} — {so.get('grade')}({so.get('note')})")
        se = a.get("sori_eumyang")
        if se:
            lines.append(f"- 소리음양: {se.get('pattern')} — {se.get('grade')}({se.get('note')})")
        lines.append(
            "\n위 근거로 현재 이름의 강점·유의점과 개명 필요 여부를 설명하세요. "
            "★발음오행(한글 초성 소리 기준)과 자원오행(한자 부수 뜻 기준)은 서로 다른 값이니, "
            "위 표의 각 값을 그대로 쓰고 뒤섞거나 지어내지 마세요. '불명'은 판별 불가라는 뜻이니 "
            "오행을 억지로 붙이지 마세요.")
        return "\n".join(lines)
    if kind == "aho":
        return _render_aho(r)
    # jakmyeong
    defc = "·".join(_WX_KO.get(e, e) for e in (r.get("deficient") or []))
    label = "작명"
    # 외자/돌림자 조건 — 후보가 왜 한 글자이거나 특정 글자를 공유하는지 LLM이 알고 설명하도록.
    _cond = []
    if int(r.get("name_len") or 2) <= 1:
        _cond.append("외자 이름(성+한 글자)")
    if r.get("dollimja"):
        _pos = "앞자리(성 다음)" if r.get("dollimja_pos") == "front" else "끝자리"
        _cond.append(f"돌림자(항렬자) '{r['dollimja']}' {_pos} 고정 — 나머지 한 글자만 지음")
    cond_txt = (" · 조건: " + " / ".join(_cond)) if _cond else ""
    lines = [f"[{label} 추천] 성: {r.get('surname') or '(없음)'} · 사주 부족오행: {defc}{cond_txt}"]
    for c in (r.get("candidates") or [])[:8]:
        # 자원오행(한자 부수)과 발음오행(한글 초성)은 다른 개념 — 각각 명시해 LLM이 혼동/환각 못하게.
        ja = "·".join(c.get("elements") or [])
        ba = "·".join(c.get("baleum_elements") or [])
        lines.append(
            f"- {c['given']}({c['reading']}) {c['score']}점 81수[{c['suri_grade']}] "
            f"자원오행(한자부수){ja} 발음오행(한글초성){ba} : {c['meaning']}")
    lines.append(
        f"\n위 후보 중 추천작을 골라 {label} 원리와 함께 설명하세요. "
        "★발음오행(한글 초성 소리 기준)과 자원오행(한자 부수 뜻 기준)은 서로 다른 값이니, "
        "위 표의 각 값을 그대로 쓰고 뒤섞거나 지어내지 마세요. '불명'은 판별 불가라는 뜻이니 오행을 억지로 붙이지 마세요.")
    return "\n".join(lines)


# ── 아호 브리핑 (P4) ─────────────────────────────────────────────────
# 작명과 브리핑을 나눈다. 아호는 성(姓)도 81수 4격도 없고, 대신 **작호 유형**과 실존 호 사례가
# 해설의 뼈대다. 종전에는 작명 브리핑을 그대로 써서 "성: (없음)"과 의미 없는 '길·길·길·길'이
# 실렸다. 사례는 검증된 것만 싣고, 유래가 확인 안 된 항목(origin_story=null)은 아예 안 싣는다.
def _render_aho(r: dict) -> str:
    defc = "·".join(_WX_KO.get(e, e) for e in (r.get("deficient") or []))
    lines = [f"[아호 추천] 사주 부족오행: {defc}", "",
             "후보(값은 그대로 쓰고 지어내지 마세요):"]
    for c in (r.get("candidates") or [])[:8]:
        ja = "·".join(c.get("elements") or [])
        ba = "·".join(c.get("baleum_elements") or [])
        tl = naming_engine.aho_type_label(c.get("aho_type") or "")
        st = c.get("strokes") or []
        lines.append(
            f"- {c['given']}({c['reading']}) {c.get('score', 0)}점 [{tl}] "
            f"자원오행(한자부수){ja} 발음오행(한글초성){ba} 획수{'·'.join(str(x) for x in st)} : {c.get('meaning','')}")
    types = naming_engine.aho_types()
    if types.get("types"):
        lines += ["", "작호(作號) 유형 — 이 넷 중 후보가 어디에 해당하는지로 설명하세요:"]
        for t in types["types"]:
            lines.append(f"  · {t['name_ko']}({t['name_hanja']}): {t['desc']}")
        # ⚠️출전 사칭 방지 — 데이터의 origin 필드를 프롬프트에도 그대로 옮긴다.
        lines.append("  ※ 이 네 유형 구분은 현대 연구의 정리입니다. '고전이 정한 4법'이라고 쓰지 마세요.")
    ex = [e for e in naming_engine.aho_examples() if e.get("origin_story") and e.get("hanja")]
    if ex:
        lines += ["", "실존 호 사례(이 표에 있는 것만 인용하고, 다른 인물의 호 유래를 지어내지 마세요):"]
        for e in ex[:6]:
            lines.append(f"  · {e['ho']}({e['hanja']}) {e['person']} — {e['origin_story']}")
    for rule in (types.get("rules") or []):
        lines.append(f"※ {rule}")
    lines.append(
        "\n위 후보 중 추천작을 골라 아호 원리와 함께 설명하세요. "
        "★발음오행(한글 초성 소리 기준)과 자원오행(한자 부수 뜻 기준)은 서로 다른 값이니 "
        "표의 값을 그대로 쓰세요. '불명'은 부수표에서 판별되지 않는다는 뜻이니 오행을 억지로 붙이지 마세요.")
    return "\n".join(lines)


# ── RAG 검색 쿼리 (P3-A2) ────────────────────────────────────────────
# [전수감사 2026-07-22] 예전에는 rag_query = brief[:600] 이었다. 그런데 작명·아호 브리핑은
# 후보 8줄이 95%를 차지하고, 그 줄 끝의 c['meaning'] 은 **Unihan kDefinition = 영문**이다
# (naming.py:791). 실측 결과 검색 쿼리의 **34.8~36.7%가 라틴 문자**, 완전한 한글 산문 줄은
# **0개**였다(코퍼스는 한글 54%·라틴 1%). 유일한 한글 지시문은 맨 끝이라 600자 컷에 전량 잘렸다.
# 그 결과 작명·아호 회수는 1.33~1.40/4 로 전 메뉴 최하위였고, 올라온 것은 남의 사주 풀이였다.
# → 검색어는 '무엇을 묻는지'로 만든다. 후보표·영문 훈은 프롬프트(brief)에는 그대로 남는다.
#
# ⚠️kind별 분기 필수 — **작명 메뉴 전체로 일반화하면 멀쩡한 것을 망친다**:
#   · gaemyeong 브리핑은 384~450자로 절단 자체가 없고(20건 전수) 라틴 0.00%, 한글 49.1% — 정상.
#   · taekil·calendar·sinnyeon 은 형태가 표여도 실측 회수 4.00/4·0건률 0%(신년 max 0.708로 최고).
#   따라서 여기서 쿼리를 갈아끼우는 대상은 **jakmyeong·aho 둘뿐**이다.
#
# ⛔⛔ 승인 없이 이 dict 에 메뉴를 추가하지 마세요 ⛔⛔
#   "다른 메뉴도 표를 쓰니 같이 바꾸자"가 가장 위험한 발상이다. 개명·택일·캘린더·신년은
#   실측으로 이미 정상이며(회수 4.00/4·0건률 0%), 바꾸면 개선인지 개악인지 확인할 지표도 없다.
#   먼저 retrieval_logs(menu 컬럼)로 그 메뉴의 실측을 확보한 뒤 운영자 승인을 받을 것.
#   관련: docs/rag_hallucination_audit_2026-07-22.md 4장
#   테스트: backend/tests/test_p3_rag_coverage.py::test_gaemyeong_query_unchanged / test_other_menus_query_unchanged
_INTENT_QUERY = {
    "jakmyeong": ("작명 성명학 원리 — 수리 81수 길흉(원형이정 사격), 자원오행과 발음오행 배합, "
                  "음양 조화, 사주 부족 오행을 보완하는 이름 짓는 법, 인명용 한자 선택"),
    "aho": ("아호(雅號) 짓는 법 — 호(號)의 유래와 종류, 자연물·성품·거처에서 호를 취하는 방식, "
            "사주 용신과 부족 오행을 보완하는 작호 원리"),
}


def _rag_query(row: ToolSession, brief: str, message: str | None = None) -> str:
    """검색 쿼리. jakmyeong·aho 만 의도 산문으로 대체하고 나머지는 기존 동작 유지."""
    intent = _INTENT_QUERY.get(row.kind or "")
    if intent:
        r = row.result_json or {}
        defc = "·".join(_WX_KO.get(e, e) for e in (r.get("deficient") or []))
        body = intent + (f"\n이 사람의 부족 오행: {defc}" if defc else "")
    else:
        body = brief
    return (f"{message}\n{body}" if message else body)[:600]


_TOOL_SYSTEM = {
    "sinnyeon": SINNYEON_SYSTEM, "taekil": TAEKIL_SYSTEM,
    "today": TODAY_SYSTEM, "calendar": CALENDAR_SYSTEM,
    "amulet": AMULET_SYSTEM, "dream": DREAM_SYSTEM,
}


_NAMING_SYSTEM_BY_KIND = {
    "jakmyeong": NAMING_SYSTEM, "aho": AHO_SYSTEM, "gaemyeong": GAEMYEONG_SYSTEM,
}


def _system_for(row: ToolSession) -> str:
    if row.tool == "naming":                      # 종류별 지시가 서로 새지 않도록 분기(전수감사)
        return _NAMING_SYSTEM_BY_KIND.get(row.kind, NAMING_SYSTEM)
    return _TOOL_SYSTEM.get(row.tool, NAMING_SYSTEM)


# ── 스트리밍 해설 / 추가질문 ──────────────────────────────────
def stream_message(
    db: Session, tool_id: str, message: str, user: User | None = None,
    depth: str = "deep", explain_level: str = "normal",
):
    """공개 진입점 — 내부 스트림을 감싸 '예상 밖 예외'에서도 선차감을 보상한다.

    [버그 2026-07-23] 이 서비스는 free-ride 차단을 위해 답변 생성 '전'에 차감을 확정 커밋한다
    (끝에서 커밋하면 클라 이탈 시 롤백돼 무한 무료가 된다 — 옳은 설계). 대신 실패하면 반드시
    보상해야 하는데, 내부에서 이미 방어한 분기(LLM 장애·빈 답변·저장 실패) **밖**에서 예외가 나면
    api/tools.py 의 포괄 except 가 그대로 삼켜 error 만 내보내고 환불하지 않았다.
    → 답변을 못 받은 채 실포인트(기본 1,330P/심화)가 사라졌다. dream.py:253 은 이미 이 구조를 갖고 있다.

    이중환불 방지: 내부가 스스로 환불한 지점에서는 receipt 를 비운다(_receipt.clear()).
    여기서는 receipt 에 아직 미정산 청구가 남아 있을 때만 보상한다.
    ⚠️ GeneratorExit(클라 이탈)은 환불하지 않고 그대로 올린다 — 그게 free-ride 차단 규약이다.
    """
    receipt: dict[str, Any] = {}
    try:
        yield from _stream_message_inner(
            db, tool_id, message, user=user, depth=depth, explain_level=explain_level, _receipt=receipt)
    except GeneratorExit:
        raise                       # 클라 이탈 — 정상 종료 경로(과금 유지)
    except Exception as e:  # noqa: BLE001
        if receipt.get("bill") is not None:
            try:
                db.rollback()
                chat_service.refund_followup(
                    db, user, receipt["bill"], receipt.get("pre_charged", 0),
                    reason="tool_q", ref_id=tool_id)
            except Exception:  # noqa: BLE001 — 보상 실패가 에러 전달을 막지 않는다
                pass
        import logging
        logging.getLogger("saju.tools").warning("tool stream failed(refunded): %s", e)
        yield ("error", {"detail": "답변 처리 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.",
                         "code": "internal_error"})


# ─────────────────────────────────────────────────────────────────────────────
# 신년운세 ② 월 팩트헤더 결정적 렌더 + ③ 중국어 제거 + ⑤ 어휘 교정 (운영자 승인 전체수정)
#   약모델이 브리핑의 정확한 값을 재서술하며 훼손(丑 숨은 편재→겁재)하고, 배치마다 형식이 제각각
#   (불릿 vs 산문)이며 마지막 달을 통째 빠뜨렸다. 팩트는 코드가 결정적으로 렌더하고 모델은 '서술'만
#   쓰게 하면 A1(완결)·A2(형식통일)·C(사실훼손)를 한 번에 잡는다.
_MONTH_MARK = _re.compile(r"\[\[\s*(\d{1,2})\s*월\s*\]\]")
_CLOSING_MARK = _re.compile(r"\[\[\s*마무리\s*\]\]")
# 줄머리가 '월 서술 시작'(마커 없는) — 약모델이 마무리·다른 달 뒤에 마커 없이 이어 쓴 월 서술이 그 섹션
#   본문에 딸려오는 것을 잘라낸다. 숫자월(2월)·한자수월(삼월·시월)·서수(두 번째 달)를 모두 잡는다.
_SINO_MONTH = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9,
               "십": 10, "시": 10, "십일": 11, "십이": 12}
_NATIVE_MONTH = {"첫": 1, "한": 1, "두": 2, "둘": 2, "세": 3, "셋": 3, "네": 4, "넷": 4, "다섯": 5,
                 "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10, "열한": 11, "열두": 12}
_MONTH_LINE_START = _re.compile(
    r"(?m)^\s*(?:"
    r"(\d{1,2})\s*월(?=[\s에은은는이가을를도의\(（:：]|$)"          # 그룹1: 숫자월
    r"|(십[일이]|[일이삼사오육칠팔구십시])\s*월(?=[\s에은는이가을를도의]|$)"  # 그룹2: 한자수월(삼월·시월·십이월)
    r"|(첫|한|둘|두|셋|세|넷|네|다섯|여섯|일곱|여덟|아홉|열\s*두|열\s*한|열두|열한|열)\s*번째\s*(?:달|월)"  # 그룹3: 서수 번째 달
    r")")


def _month_line_num(m: "_re.Match[str]") -> int | None:
    """_MONTH_LINE_START 매치에서 월 번호를 뽑는다(숫자·한자수·서수 공통)."""
    if m.group(1):
        return int(m.group(1))
    if m.group(2):
        return _SINO_MONTH.get(m.group(2))
    if m.group(3):
        return _NATIVE_MONTH.get(m.group(3).replace(" ", ""))
    return None
# 코드가 이미 렌더하는 '팩트 라벨' 줄 — 모델 서술에 섞여 오면 제거(중복·오염 방지). '큰 흐름' 등 서술은 보존.
_FACT_LABEL = _re.compile(
    r"^\s*[·•\-*#>]*\s*(월간\s*십성|월지\s*십성|12\s*운성|십이운성|12\s*신살|십이신살|지장간|"
    r"숨은\s*(천간|십성)|관계\s*분석|關係|关系|月支|運性|运性|12運性|12运性)\b")
# ⑤ 약모델 한국어 깨짐 결정적 교정(신년운세 전용, 고신뢰만).
_SINNYEON_VOCAB_FIXES = [
    (_re.compile(r"무분비"), "무분별"),
    (_re.compile(r"내일간(?=[\s의은는이가을를과와인에도만로])"), "내 일간"),   # '내일간인 정' 붙여쓴 오기(≠내일 간다)
    (_re.compile(r"지지원하는"), "지지가 작용하는"),
    (_re.compile(r"지지원견"), "지지 비견"),           # 약모델이 '지지 비견'을 '지지원견'으로 뭉갬
    (_re.compile(r"지지원기"), "지지 정기"),
    (_re.compile(r"지지원(?![하진])"), "지지"),        # 잔여 '지지원 오행/에서'→'지지 …'(원진·지지원하 보호)
    (_re.compile(r"기운들께서"), "기운들이"),
    (_re.compile(r"싱크로율"), "궁합"),                # '싱크로율이 맞아'→'궁합이 맞아'(받침ㅂ→조사 정상·명리 용어)
    (_re.compile(r"싱크(?=\s|를|가|는|이|$)"), "기운"),   # '편재 싱크' 등 정체불명어
    (_re.compile(r"동僚"), "동료"), (_re.compile(r"或者是"), "또는"),   # 한자혼입 흔한 케이스
    (_re.compile(r"펜치(?=이)"), "편"),                # '낮은 펜치이며'→'낮은 편이며'(약모델이 '편'을 '펜치'로 뭉갬)
]
# 중국어 구두점 → 한국어/표준(약모델이 열거에 、, 문장부호에 ，。 등을 씀).
_ZH_PUNCT = str.maketrans({"、": "·", "，": ", ", "。": ". ", "？": "?", "！": "!", "：": ": ", "；": "; "})
# 영어 코드스위칭 절 — 4+ 연속 영단어(앞 em-dash/구분자, 내부 em-dash·쉼표 허용). 신년운세 서술에 영문
#   4단어↑는 약모델이 중간에 영어로 설명해버린 오염뿐이라 통째로 제거한다(원포인트 교정, 재생성 아님).
_ENG_CLAUSE = _re.compile(r"\s*[—–\-]?\s*(?:[A-Za-z][A-Za-z'’\-]*[ ,—–]+){3,}[A-Za-z][A-Za-z'’\-]*[ .]*")


def _has_chinese_only(line: str) -> bool:
    """한글 없이 CJK 한자만인 줄 = 중국어 오염(3월 '要注意与午的冲突关系' 등). 한자 병기(정재(正財))는 한글이 있어 통과."""
    s = line.strip()
    if not s:
        return False
    han = sum(1 for ch in s if "가" <= ch <= "힣")   # 한글 음절
    cjk = sum(1 for ch in s if "一" <= ch <= "鿿")   # CJK 한자
    return cjk >= 4 and han == 0


def _sinnyeon_month_header(mth: dict, day_stem: str, year_branch: str | None) -> str:
    """그 달의 '결정적 팩트 헤더' — 십성·12운성·12신살·숨은십성·관계를 코드가 확정 출력(모델 훼손 차단)."""
    m = mth.get("month"); label = mth.get("label", "")
    tg = mth.get("ten_god", ""); btg = mth.get("branch_ten_god", "")
    _star = lambda c: (f"{_STAR_KO.get(c, c)}({c})" if c else "")
    lines = [f"#### {m}월 ({label})"]
    _sib = "월간 " + _star(tg) + (f", 월지 {_star(btg)}" if btg else "")
    lines.append(f"· 십성 — {_sib}")
    _flow = _month_depth_line(day_stem, mth.get("branch", ""), year_branch)   # 운성·신살·숨은십성(결정적)
    if _flow:
        lines.append(f"· 기운 — {_flow}")
    _pr = chat_service.plain_relations(mth.get("relations") or [], with_scope=False)
    lines.append("· 관계 — " + (" / ".join(_pr) if _pr else "특별한 관계 없음(무난)"))
    return "\n".join(lines)


_HEADER_MIMIC = _re.compile(r"^\s*[·•]\s*(십성|기운|관계)\s*[—–-]")   # 모델이 코드 헤더 형식을 흉내 낸 줄


def _clean_month_narrative(body: str) -> str:
    """배치 서술에서 코드가 렌더하는 팩트 라벨 줄·헤더 흉내 줄·중국어 전용 줄·소제목(#, ③)을 제거하고 서술만 남긴다."""
    out: list[str] = []
    for ln in body.splitlines():
        s = ln.strip()
        if not s:
            out.append("")
            continue
        if _has_chinese_only(s) or _FACT_LABEL.match(s) or _HEADER_MIMIC.match(s):
            continue
        if s.startswith("#") or s.startswith("③") or s.startswith("###"):
            continue
        out.append(ln)
    return "\n".join(out).strip()


def _parse_month_narratives(raw: str) -> tuple[dict[int, str], str]:
    """배치 원문에서 '[[N월]] 서술' 블록과 '[[마무리]]' 블록을 파싱. 코드가 삽입한 마커 구분자만 신뢰
    (본문 속 'N월' 언급에 안 흔들림). 없는 달은 폴백으로 대체돼 완결이 보장된다.

    ★[운영자 실측 2026-08-05] '위치 기반' 파싱 — 각 마커 본문은 '다음 마커 직전'까지다. 종전엔 [[마무리]]를
    먼저 찾아 그 '뒤 전체'를 마무리로 잘랐는데, 약모델이 마무리를 달들 중간에 쓰면(1·2·마무리·3~12)
    3~12월이 통째로 마무리에 딸려가 폴백 처리 + raw '[[3월]]' 마커가 화면에 새어나왔다(재현 확정).
    이제 [[마무리]]도 다음 마커까지만 본문으로 삼아, 뒤에 오는 달들을 삼키지 않는다."""
    result: dict[int, str] = {}
    closing = ""
    if not raw:
        return result, closing
    # [[N월]] 과 [[마무리]] 를 한 번에, 등장 순서대로 스캔(마커 사이 = 본문)
    _MARK = _re.compile(r"\[\[\s*(\d{1,2})\s*월\s*\]\]|\[\[\s*마무리\s*\]\]")
    marks = [(mt.start(), mt.end(), mt.group(1)) for mt in _MARK.finditer(raw)]  # group(1)=월번호 or None(=마무리)
    for i, (_st, en, num) in enumerate(marks):
        nxt = marks[i + 1][0] if i + 1 < len(marks) else len(raw)
        body = _clean_month_narrative(raw[en:nxt])
        if not body:
            continue
        if num is None:            # [[마무리]] — 다음 마커까지만(뒤 달 안 삼킴). 여러 개면 마지막 우선.
            # 모델이 마무리 뒤에 '마커 없이' 쓴 월 서술(6월에는…)이 마무리 본문에 딸려오는 것 차단 —
            #   줄머리가 'N월…'인 지점부터 잘라낸다(마무리 요약이 그런 줄로 시작하는 일은 없음).
            _ml = _MONTH_LINE_START.search(body)
            closing = body[:_ml.start()].strip() if _ml else body
        else:
            n = int(num)
            if 1 <= n <= 12:
                # 마커 없이 딸려온 '다른 달' 서술을 잘라낸다(자기 달 'n월에는…' 인트로는 번호 같아 보존).
                for _ml in _MONTH_LINE_START.finditer(body):
                    if _month_line_num(_ml) != n:
                        body = body[:_ml.start()].strip()
                        break
                # 같은 달이 두 번 나오면(모델 중복 생성) '더 긴 서술'을 채택 — 중복 마커 누출·짧은 폴백 방지.
                if body and len(body) > len(result.get(n, "")):
                    result[n] = body
    return result, closing


def _assemble_sinnyeon_months(row: ToolSession, raw: str) -> str:
    """③ 월별 흐름을 '결정적 헤더(코드) + 서술(모델)'로 조립. 12달 헤더는 항상 존재해 완결을 보장한다."""
    r = row.result_json or {}
    day_stem = r.get("day_stem") or ""
    year_branch = None
    try:
        year_branch = (((row.chart_json or {}).get("pillars") or {}).get("year") or {}).get("branch")
    except Exception:  # noqa: BLE001
        year_branch = None
    narr, closing = _parse_month_narratives(raw)
    out: list[str] = ["### ③ 월별 흐름", ""]
    for mth in r.get("months") or []:
        n = mth.get("month")
        out.append(_sinnyeon_month_header(mth, day_stem, year_branch))
        body = (narr.get(n) or "").strip()
        if not body:   # 서술 누락 달도 빈칸 아님(완결 보장·재생성 아님)
            body = ("이 달은 위 지표(십성·운성·신살)의 흐름을 따릅니다. 무리한 확장보다 컨디션과 "
                    "주변 관계를 살피며 차분히 운영하시길 바랍니다.")
        out.append(body)
        out.append("")
    result = "\n".join(out).strip()
    if closing:
        result += "\n\n### 마무리 조언\n\n" + closing
    return result


# ⑥ 영역별 심화도 결정적 헤더(점수 포함)로 — 약모델이 ①스트림에서 5영역 중 하나(특히 연애)를 통째로
#   빠뜨리던 문제(실측 연애 누락) 해결 + 점수-서술 정합(헤더가 실제 점수를 박아 저점 낙관포장 차단).
#   (result_json domains label, 배치 마커 키, 표시 제목)
_SINNYEON_DOMAINS = [
    ("직업운", "직업", "직업 · 일"),
    ("재물운", "재물", "재물"),
    ("대인운", "대인", "대인 관계"),
    ("연애운", "연애", "연애 · 결혼"),
    ("건강운", "건강", "건강"),
]


def _parse_keyed_narratives(raw: str, keys: list[str]) -> dict[str, str]:
    """'[[키]] 서술' 블록을 파싱({키: 서술}). 코드가 삽입한 [[키]] 구분자만 신뢰."""
    result: dict[str, str] = {}
    if not raw or not keys:
        return result
    pat = _re.compile(r"\[\[\s*(" + "|".join(_re.escape(k) for k in keys) + r")\s*\]\]")
    marks = [(m.start(), m.end(), m.group(1)) for m in pat.finditer(raw)]
    for i, (_st, en, k) in enumerate(marks):
        nxt = marks[i + 1][0] if i + 1 < len(marks) else len(raw)
        body = _clean_month_narrative(raw[en:nxt])
        if body:
            result[k] = body
    return result


def _assemble_sinnyeon_domains(row: ToolSession, raw: str) -> str:
    """② 영역별 심화를 '결정적 헤더(제목+실제 점수) + 서술(모델)'로 조립. 다섯 영역 항상 존재."""
    r = row.result_json or {}
    scores = {d.get("label"): d.get("value") for d in (r.get("domains") or [])}
    narr = _parse_keyed_narratives(raw, [k for _, k, _ in _SINNYEON_DOMAINS])
    out: list[str] = []
    for label, key, title in _SINNYEON_DOMAINS:
        val = scores.get(label)
        out.append(f"### {title}" + (f" ({val}점)" if val is not None else ""))
        body = (narr.get(key) or "").strip()
        if not body:   # 서술 누락 영역도 빈칸 아님(완결 보장)
            _lv = ("올해 특히 조심스럽게 다뤄야 할 영역입니다." if (val is not None and val < 40)
                   else "올해 무난하게 흐르는 영역입니다." if (val is not None and val < 70)
                   else "올해 비교적 힘을 받는 영역입니다.")
            body = f"{_lv} 위 점수를 참고해 무리하지 말고 균형 있게 운영하시길 바랍니다."
        out.append(body)
        out.append("")
    return "\n".join(out).strip()


def _fix_sinnyeon_vocab(text: str) -> str:
    """③ 중국어 전용 줄 제거 + ⑤ 약모델 한국어 깨짐 결정적 교정 + 영어/중국어 코드스위칭 오염 제거(최종본)."""
    if not text:
        return text
    kept = [ln for ln in text.splitlines() if not _has_chinese_only(ln)]
    text = "\n".join(kept)
    text = text.translate(_ZH_PUNCT)          # 중국어 구두점 정규화
    text = _ENG_CLAUSE.sub(" ", text)          # 영어 코드스위칭 절 제거
    for pat, rep in _SINNYEON_VOCAB_FIXES:
        text = pat.sub(rep, text)
    # 한글에 '붙어 있는' 인라인 한자(순간抓住·동僚 등 코드스위칭) 제거 — 괄호 병기(正財·丑)는 '(' 뒤라 안 걸림.
    text = _re.sub(r"(?<=[가-힣])[一-鿿]+", "", text)
    text = _re.sub(r"(?m)^[ \t]+", "", text)          # 줄머리 공백 제거(' 3월은…'·공백만 줄 정리 — 신년운세엔 들여쓰기 없음)
    text = _re.sub(r"[ \t]{2,}", " ", text)          # 잔여 이중 공백(줄바꿈은 보존)
    text = _re.sub(r"[ \t]+([,.])", r"\1", text)     # ★공백 뒤 쉼표·마침표만(줄바꿈·중점 '·'은 절대 안 건드림 —
    #   종전 \s+([,.·]) 가 '#### 1월\n· 십성'의 줄바꿈을 먹어 헤더를 한 줄로 뭉갠 버그 수정)
    return text


def _start_sinnyeon_batches(sys_content: str, brief: str, rag_ctx: str | None, s):
    """신년운세 ②영역 + ③월별 + ④마무리를 백그라운드 '병렬' 스레드로 착수하고 join(→dict) 함수를 반환.

    스트리밍 호환 배치(Phase B 재설계). 첫 해설의 ①총운만 메인 루프가 '라이브로 스트리밍'해 첫 청크를
    ~1s에 내보내고(프론트 60s 첫-청크 워치독 통과), 그 스트림이 도는 동안 여기서 시작한 영역·월별 배치가
    '동시에' 생성된다. 스트림이 끝나면 _join()으로 모아 결정적 헤더와 함께 조립·이어붙인다(무음 구간은
    호출부가 _bg_with_heartbeat 로 감싸 ping 유지). 영역·월별 팩트(점수·십성·운성·신살)는 코드가 결정적
    헤더로 붙이고 모델은 '서술만' 써서, 약모델이 영역/달을 빠뜨리거나 사실을 훼손해도 완결·정확이 보장된다.
    배치별 결과를 dict로 반환 → 일부 실패해도 나머지는 조립(옛 'all-or-nothing None'보다 견고).
    동시 4배치 + ①스트림 = 5콜, OLLAMA_NUM_PARALLEL(6) 이내."""
    _u = brief + (f"\n\n[참고자료]\n{rag_ctx}" if rag_ctx else "")
    _COMMON = (
        " 각 달은 반드시 '[[N월]]' 형태(예: [[5월]])로 시작하고 그 뒤에 2~4문장 '서술만' 쓰세요. "
        "★십성·12운성·12신살·간지·합충관계 같은 표의 값이나 소제목·번호목록·불릿은 쓰지 마세요 — 시스템이 "
        "정확한 값을 헤더로 따로 붙입니다. 오직 그 달에 '생길 수 있는 일·조심할 점·활용 조언'을 쉬운 생활어 "
        "문장으로만 쓰면 됩니다. ★반드시 한국어 문장만(중국어·간체자 문장 절대 금지), 한자는 꼭 필요할 때만 "
        "괄호 병기. 이미 다른 달에 쓴 문장·조언을 복붙하지 말고 달마다 다르게, 가능성 화법으로.")
    _DOMAIN_INSTR = (
        "다섯 영역을 각각 '[[직업]]' · '[[재물]]' · '[[대인]]' · '[[연애]]' · '[[건강]]' 마커로 시작해 그 아래 "
        "2~3문장 '서술만' 쓰세요. ★다섯 개를 하나도 빠짐없이 모두 쓰세요(특히 연애·대인을 합치거나 빠뜨리지 "
        "말 것). 점수·표값·소제목은 쓰지 마세요 — 시스템이 실제 점수를 헤더로 붙입니다. 각 영역의 점수(위 "
        "'영역 점수')를 참고하되, 점수가 낮은 영역(예: 25점)은 낙관으로 포장하지 말고 조심스럽게 쓰세요. "
        "반드시 한국어 문장만(중국어 금지).")
    # (배치 키, 지시, num_predict)
    _TASKS = [
        ("domain", _DOMAIN_INSTR, 3072),
        ("m1", "'1·2·3·4월' 네 달을 하나도 빠짐없이 번호순으로 쓰세요." + _COMMON, 3072),
        ("m2", "'5·6·7·8월' 네 달을 하나도 빠짐없이 번호순으로 쓰세요." + _COMMON, 3072),
        ("m3", "'9·10·11·12월' 네 달을 하나도 빠짐없이 번호순으로 쓰세요." + _COMMON
         + " 열두 달 뒤에 '[[마무리]]'로 시작하는 마무리 조언 한 문단(손님을 주어로, '제가~하겠습니다' 같은 1인칭 다짐 금지)도 쓰세요.", 3072),
    ]
    results: dict[str, str | None] = {k: None for k, _, _ in _TASKS}

    def _one(key: str, instr: str, npred: int) -> None:
        try:
            results[key] = chat_service._call_ollama(
                [{"role": "system", "content": sys_content},
                 {"role": "user", "content": f"{_u}\n\n[이번에 쓸 부분만] {instr}"}],
                num_predict=npred)
        except Exception:  # noqa: BLE001 — 한 배치 실패 → 그 섹션만 폴백(나머지·헤더는 정상)
            results[key] = None

    ths = [threading.Thread(target=_one, args=(k, i, n), daemon=True) for k, i, n in _TASKS]
    for t in ths:
        t.start()

    def _join() -> dict[str, str | None]:
        for t in ths:
            t.join(timeout=s.ollama_timeout_sec + 60)
        return results

    return _join


# ########################## DO NOT MODIFY (guard) - 신년운세 1.0 ##########################
#  운영자 orion0321(orion0321@gmail.com) 승인 없이 아래 단일패스/스캐폴드/1차보존 로직을
#  수정·제거·우회하지 말 것. 금지 목록(전부 실측 회귀로 확정된 것):
#   1) 배치(동시 다중콜) 재도입 금지 - TTFT 31s·크롤·멈춤->쾅 회귀 (Phase-B 실측)
#   2) 누락 판정 기준 변경 금지 - 반드시 '원문(raw) 기준'. 클리너/마커존재 기준으로 되돌리면
#      멀쩡히 보이는 답을 결측 오판 -> 불필요 보강 -> "전체 재실행" 회귀 (운영자 실측 2회)
#   3) 정상 런에 전문교체(정본 스왑·문장 dedupe·분량바닥 재작성) 재도입 금지 -
#      "2차가 1차보다 못한" 삭감 회귀. 정상 런은 결정적 원포인트 교정만 통과한다.
#  변경 필요 시: 운영자 보고 -> 승인 -> 실측 게이트(TTFT<=7s·12/12 완결·정상런 교체 0회) 재통과 후.
# ##########################################################################################
# ── 옵션 D(2026-08-04 운영자 승인): 신년운세 단일패스 + 결정적 스캐폴드 ───────────────────────────
# 실측 진단: 구 배치(5동시콜)는 ~13.5k tok 프롬프트 5벌 동시 프리필(67.5k tok)로 TTFT 31s·가시 스트림
# 20~27tok/s 크롤·종료 후 15~25s 무음 → 75~80% 일괄 출현. 단일패스는 콜 1개(TTFT ~6s·전속 스트림·멈춤 0),
# 정형·완결은 90496399의 파서·어셈블러(결정적 헤더+폴백)를 그대로 재사용해 코드가 보장한다.

_SCAF_ANY = _re.compile(r"\[\[\s*([^\[\]\n]{1,12}?)\s*\]\]")


def _norm_ws(t: str) -> str:
    """공백 정규화 비교용 — 화면=DB 동기화가 '공백 차이'만으로 전문 교체를 쏘지 않게."""
    return _re.sub(r"\s+", " ", t or "").strip()


_SINNYEON_SINGLE_INSTR = (
    "\n\n[작성 형식 — 마커 필수] 아래 순서대로 '마커 + 서술'만 쓰세요. 소제목·번호목록·표·점수·헤딩(#)은 절대 "
    "쓰지 마세요 — 시스템이 정확한 제목·점수·표(십성·운성·신살)를 자동으로 붙입니다. 각 섹션은 반드시 대괄호 "
    "두 겹 마커(예: [[총운]])로만 시작하세요.\n"
    "[[총운]] {TARGET_YEAR} 한 해 '전체' 흐름 2~3문단 — 그 해 세운 간지가 내 일간(강약)과 맺는 십성·합충 "
    "관계를 근거로 기회·유의점을. ★대상 연도는 {TARGET_YEAR}입니다(다른 해로 쓰지 마세요). '이번 달' 같은 "
    "특정 월 표현 금지, '여러분'이 아니라 '당신(손님)'을 주어로.\n"
    "[[직업]] [[재물]] [[대인]] [[연애]] [[건강]] — 다섯 영역을 하나도 빠짐없이 각각 2~3문장 '서술만'(연애·"
    "대인을 합치거나 빠뜨리지 말 것). 각 영역의 점수(위 '영역 점수')를 참고하되 점수가 낮은 영역은 낙관으로 "
    "포장하지 말고 조심스럽게.\n"
    "[[1월]] [[2월]] … [[12월]] — 열두 달을 하나도 빠짐없이 번호순으로, 각 달 2~4문장 '서술만'. ★각 달의 "
    "'월간 십성'은 달마다 다릅니다(브리핑의 월별 표 참고 — 예: 1월 겁재, 2월 식신, 3월 상관…). 그 달 십성의 "
    "'뜻'을 근거로 달마다 '완전히 다른' 생길 일·조심할 점·활용 조언을 쓰세요 — 십성·운성·신살·간지의 값 자체는 "
    "문장에 옮기지 말고(시스템이 헤더로 붙임) 그 '의미'만 쉬운 생활어로 풀어. ★★이미 앞선 달에 쓴 문장·표현·"
    "조언을 절대 복붙·재탕하지 마세요 — 예컨대 '학문·문서·후원' 같은 테마를 여러 달에 반복하지 말고, 열두 달이 "
    "서로 겹치지 않게 각 달 십성에 맞춰 다르게 쓰세요.\n"
    "[[마무리]] 마무리 조언 한 문단(손님을 주어로, '제가 ~하겠습니다' 같은 1인칭 다짐 금지).\n"
    "★반드시 한국어 문장만(중국어·간체자 문장 절대 금지), 한자는 꼭 필요할 때만 괄호 병기. 가능성 화법으로.\n"
    "★★마커는 총 19개([[총운]] 1 + 영역 5 + 달 12 + [[마무리]] 1)입니다 — 19개를 하나도 빠짐없이 모두 쓴 "
    "뒤에만 답을 끝내세요. [[12월]]을 쓰기 전에 [[마무리]]나 결론을 먼저 쓰지 마세요(중간에 멈추면 유료 "
    "리포트 결손입니다).")


# 모델의 '자연스러운 영역 서술 시작'(마커를 빠뜨렸을 때) — 줄머리 키워드로 영역을 인식한다.
_SINNYEON_DOMAIN_PATTERNS = [
    ("직업", _re.compile(r"^(직업|직무|일자리|직장|커리어|사업)")),
    ("재물", _re.compile(r"^(재물|재산|금전|자산|재정)")),
    ("대인", _re.compile(r"^(대인|인간관계|사회생활|사회적|사회\s*및|사람들과의|교류|사회\s*생활)")),
    ("연애", _re.compile(r"^(연애|사랑|이성|애정|결혼)")),
    ("건강", _re.compile(r"^(건강|신체|체력|컨디션)")),
]


class _SinnyeonScaffold:
    """단일패스 스트림 변환기 — 모델의 [[마커]]뿐 아니라 '마커 없는 평문 섹션 시작'(삼월·직업 운은…)도 줄
    단위로 감지해 결정적 헤더(제목·점수·팩트라인)를 실시간으로 꽂는다 → 모델이 마커를 빠뜨려도 1차가 깨끗.

    동시에 '정규화 raw'(감지한 섹션에 [[마커]] 주입한 원문)를 쌓아 둔다 — 호출부가 결측판정·canon 입력으로
    쓰면, 모델이 순서대로 다 쓴 경우(마커 없어도) 결측 0·순서 정상 → canon 교체 0회(1차=최종, 핀포인트만).
    [운영자 실측 2026-08-06] 약모델이 마커를 5회 중 4회 빠뜨려(특히 영역) 1차가 지저분하던 것을 해결."""

    MAXLINE = 400   # \n 없이 이 이상 쌓이면 흘린다(스트리밍 정지 방지). 마커 꼬리는 별도 보류.

    def __init__(self, row: ToolSession):
        r = row.result_json or {}
        day_stem = r.get("day_stem") or ""
        try:
            year_branch = (((row.chart_json or {}).get("pillars") or {}).get("year") or {}).get("branch")
        except Exception:  # noqa: BLE001
            year_branch = None
        scores = {d.get("label"): d.get("value") for d in (r.get("domains") or [])}
        self.headers: dict[str, str] = {"총운": "### ① 총운", "마무리": "### 마무리 조언"}
        for label, key, title in _SINNYEON_DOMAINS:
            v = scores.get(label)
            self.headers[key] = f"### {title}" + (f" ({v}점)" if v is not None else "")
        self.month_headers: dict[int, str] = {}
        for mth in r.get("months") or []:
            try:
                n = int(mth.get("month"))
            except Exception:  # noqa: BLE001
                continue
            self.month_headers[n] = _sinnyeon_month_header(mth, day_stem, year_branch)
        self.buf = ""
        self.norm: list[str] = []          # 정규화 raw(마커 주입) 누적
        self.headed: set[str] = set()      # 헤더 삽입 완료 섹션('총운','직업'..,'1월'..'12월','마무리')
        self._domains_opened = False
        self._months_opened = False
        self._at_line_start = True

    # ── 섹션 키 → 결정적 헤더(중복 방지: 이미 headed면 None) ──
    def _month_header(self, n: int) -> str | None:
        h = self.month_headers.get(n)
        if h is None:
            return None
        pre = "" if self._months_opened else "### ③ 월별 흐름\n\n"
        self._months_opened = True
        return pre + h

    def _domain_header(self, key: str) -> str | None:
        h = self.headers.get(key)
        if h is None:
            return None
        if not self._domains_opened:
            self._domains_opened = True
            h = "### ② 영역별 심화\n\n" + h
        return h

    def _header_for_key(self, key: str) -> str | None:
        mm = _re.fullmatch(r"(\d{1,2})\s*월", key)
        if mm:
            k = f"{int(mm.group(1))}월"
            if k in self.headed:
                return None
            h = self._month_header(int(mm.group(1)))
            if h:
                self.headed.add(k)
            return h
        if key in self.headed:
            return None
        if key in ("총운", "마무리"):
            self.headed.add(key)
            return self.headers.get(key)
        h = self._domain_header(key)
        if h:
            self.headed.add(key)
        return h

    def _xform_markers(self, text: str) -> str:
        def _rep(m: "_re.Match[str]") -> str:
            h = self._header_for_key(m.group(1).strip())
            return f"\n\n{h}\n\n" if h else ""   # 이미 헤딩됐거나 모르는 마커 → 제거(화면 오염 방지)
        return _SCAF_ANY.sub(_rep, text)

    def _plain_section(self, seg: str) -> tuple[str, str] | None:
        """마커 없는 '줄 시작' seg 에서 섹션(월/영역/총운/마무리) 감지 → (헤더, 키) or None."""
        s = seg.strip()
        if len(s) < 6:
            return None
        m = _MONTH_LINE_START.match(s)          # 1) 월 시작(숫자·한자수·서수)
        if m:
            n = _month_line_num(m)
            if n and f"{n}월" not in self.headed:
                h = self._month_header(n)
                if h:
                    self.headed.add(f"{n}월")
                    return h, f"{n}월"
            return None                          # 이미 헤딩된 월/인식실패 → 헤더 없이 통과
        if "총운" in self.headed and not self._months_opened:   # 2) 영역 시작(총운 뒤·월 시작 전에만 — 오탐 최소)
            for key, pat in _SINNYEON_DOMAIN_PATTERNS:
                if key not in self.headed and pat.match(s):
                    h = self._domain_header(key)
                    if h:
                        self.headed.add(key)
                        return h, key
        if not self.headed:                      # 3) 첫 실질 줄 = 총운 리드
            self.headed.add("총운")
            return self.headers["총운"], "총운"
        if "마무리" not in self.headed and s.startswith("마무리"):   # 4) 마무리
            self.headed.add("마무리")
            return self.headers["마무리"], "마무리"
        return None

    def _emit(self, seg: str, line_start: bool) -> str:
        """seg 를 화면용으로 변환 + 정규화 raw 누적. line_start=True 면 섹션 감지 수행."""
        if _SCAF_ANY.search(seg):               # 마커 있는 줄
            self.norm.append(seg)
            return self._xform_markers(seg)
        if line_start:
            ps = self._plain_section(seg)
            if ps:
                hdr, key = ps
                self.norm.append(f"\n\n[[{key}]]\n{seg}")   # 정규화: 감지 섹션에 마커 주입
                return f"\n\n{hdr}\n\n{seg}"
        self.norm.append(seg)
        return seg

    def feed(self, tok: str) -> str:
        self.buf += tok
        out: list[str] = []
        while True:
            nl = self.buf.find("\n")
            if nl >= 0:
                line, self.buf = self.buf[:nl], self.buf[nl + 1:]
                out.append(self._emit(line, self._at_line_start))
                out.append("\n"); self.norm.append("\n")
                self._at_line_start = True
            elif len(self.buf) > self.MAXLINE and "[[" not in self.buf[-16:]:
                seg, self.buf = self.buf, ""     # \n 없이 길어진 줄 — 앞을 흘리고 다음은 연속줄
                out.append(self._emit(seg, self._at_line_start))
                self._at_line_start = False
            else:
                break
        return "".join(out)

    def flush(self) -> str:
        rest, self.buf = self.buf, ""
        return self._emit(rest, self._at_line_start) if rest.strip() else ""

    def normalized_raw(self) -> str:
        """감지한 섹션에 [[마커]]가 주입된 원문 — 결측판정·canon 입력용(모델의 서술 보존)."""
        return "".join(self.norm)


def _scaf_split(raw: str) -> tuple[str, str, str] | None:
    """마커 원문을 (총운, 영역만 담긴 원문, 월별·마무리만 담긴 원문)으로 세그먼트 분할.

    영역/월별을 각자의 어셈블러에 '자기 마커만 담긴 원문'으로 넘기기 위함(전체 원문을 그대로 주면
    [[건강]] 본문이 다음 영역 마커가 없어 월별 전체를 삼키는 함정 방지). 마커가 없으면 None."""
    if not raw or not _SCAF_ANY.search(raw):
        return None
    marks = [(m.start(), m.end(), m.group(1).strip()) for m in _SCAF_ANY.finditer(raw)]
    lead = raw[:marks[0][0]]
    segs: list[tuple[str, str]] = []
    for i, (_st, en, k) in enumerate(marks):
        nxt = marks[i + 1][0] if i + 1 < len(marks) else len(raw)
        segs.append((k, raw[en:nxt]))
    _dom_keys = {k for _, k, _ in _SINNYEON_DOMAINS}
    chong = ""
    dom_raw: list[str] = []
    mon_raw: list[str] = []
    for k, body in segs:
        if k == "총운":
            chong = _clean_month_narrative(body)
        elif k in _dom_keys:
            dom_raw.append(f"[[{k}]]\n{body}")
        elif _re.fullmatch(r"\d{1,2}\s*월", k) or k == "마무리":
            mon_raw.append(f"[[{k}]]\n{body}")
    if not chong:
        chong = _clean_month_narrative(lead)   # [[총운]] 누락 시 첫 마커 전 텍스트가 총운
    return chong, "\n".join(dom_raw), "\n".join(mon_raw)


def _sinnyeon_missing(raw: str) -> tuple[list[int], list[str]]:
    """[GUARD 신년운세 1.0 — 판정기준 변경 금지] '화면에 실제 텍스트가 없는' 영역/달 — 마커 뒤 '원문' 기준.

    ★1차 보존(운영자 실측 2026-08-04 "전체 재실행"): 클리너가 깎은 본문도 화면엔 그대로 보인다.
    클리너-기준으로 결측 오판하면 멀쩡히 보이는 달에 보강+전문교체를 쏴 좋은 1차를 다시 그린다.
    → 원문에 텍스트가 있으면 '있음'. 진짜 빈 곳(마커 없음/마커 뒤 공백뿐)만 보강 대상."""
    if not raw or not _SCAF_ANY.search(raw):
        return [], []
    marks = [(m.start(), m.end(), m.group(1).strip()) for m in _SCAF_ANY.finditer(raw)]
    have_m: set[int] = set()
    have_d: set[str] = set()
    _dom_keys = {k for _, k, _ in _SINNYEON_DOMAINS}
    for i, (_st, en, k) in enumerate(marks):
        nxt = marks[i + 1][0] if i + 1 < len(marks) else len(raw)
        if not raw[en:nxt].strip():
            continue
        mm = _re.fullmatch(r"(\d{1,2})\s*월", k)
        if mm and 1 <= int(mm.group(1)) <= 12:
            have_m.add(int(mm.group(1)))
        elif k in _dom_keys:
            have_d.add(k)
    missing_m = [m for m in range(1, 13) if m not in have_m]
    missing_d = [k for _, k, _ in _SINNYEON_DOMAINS if k not in have_d]
    return missing_m, missing_d


def _assemble_sinnyeon_full(row: ToolSession, raw: str) -> str | None:
    """단일패스 마커 원문(①~④ 전체)을 결정적 어셈블러로 재조립 — 5영역·12달·마무리 완결 보장(누락=폴백).
    마커가 하나도 없으면 None(모델이 형식 무시 — 원문 유지가 안전)."""
    sp = _scaf_split(raw)
    if sp is None:
        return None
    chong, dom_raw, mon_raw = sp
    out: list[str] = []
    if chong:
        out.append("### ① 총운\n\n" + chong)
    out.append("### ② 영역별 심화\n\n" + _assemble_sinnyeon_domains(row, dom_raw))
    out.append(_assemble_sinnyeon_months(row, mon_raw))
    return "\n\n".join(p for p in out if p and p.strip()).strip()


def _sinnyeon_backfill(brief: str, sys_content: str, s, missing_m: list[int], missing_d: list[str]) -> str:
    """누락된 달·영역을 '항목별 병렬'로 표적 생성하고, [[마커]]는 코드가 확정 부착해 반환.

    [운영자 실측 2026-08-05] 배치 백필(여러 달을 한 콜로 + 프롬프트에 '[[N월]] 마커 붙여라')은 약모델이
    마커를 무시하고 'N월에는…' 평문으로 써 파싱 실패 → 폴백 + 평문이 마무리 뒤로 누출됐다. 각 콜을 '한
    항목'으로 좁히면 준수율↑, 마커는 코드가 붙이므로 파싱이 100% 된다. 항목별 스레드 병렬(NUM_PARALLEL 내)."""
    _titles = {k: t for _l, k, t in _SINNYEON_DOMAINS}
    items: list[tuple[str, str]] = [("month", str(m)) for m in missing_m] + [("dom", k) for k in missing_d]
    results: dict[tuple[str, str], str] = {}

    def _one(kind: str, key: str) -> None:
        if kind == "month":
            instr = (f"{key}월 한 달만, 그 달에 '생길 수 있는 일·조심할 점·활용 조언'을 2~4문장 순수 서술로만 "
                     "쓰세요. 십성·운성·신살·간지 같은 표 값이나 소제목·마커·번호목록은 쓰지 말고, 한국어 문장만.")
            marker = f"[[{key}월]]"
        else:
            instr = (f"'{_titles.get(key, key)}' 영역만, 올 한 해 그 영역의 흐름과 활용 조언을 2~3문장 순수 "
                     "서술로만 쓰세요(점수·표값·소제목·마커 금지). 한국어 문장만.")
            marker = f"[[{key}]]"
        try:
            out = chat_service._call_ollama(
                [{"role": "system", "content": sys_content},
                 {"role": "user", "content": f"{brief}\n\n[이번에 쓸 부분만] {instr}"}],
                num_predict=768)
        except Exception:  # noqa: BLE001 — 한 항목 실패 → 그 항목만 폴백 문장 유지
            out = None
        body = _clean_month_narrative(out or "")
        if body:
            results[(kind, key)] = f"{marker}\n{body}"

    ths = [threading.Thread(target=_one, args=it, daemon=True) for it in items]
    for t in ths:
        t.start()
    for t in ths:
        t.join(timeout=s.ollama_timeout_sec + 30)
    return "\n\n".join(results[it] for it in items if it in results)   # 원 순서 유지


# ── 신년운세 월별 '교차 중복' 표적 재생성(운영자 승인 2026-08-06) ─────────────────────────────
#   [배경·실측] 印(편인·정인) 압도 명식은 약모델(qwen3)이 총운 테마(학문·문서·후원)에 고착해 여러 달에 같은
#   서술을 복붙한다(단독 1회 11/12달 반복 실측). 프롬프트 강화(A)만으론 심각 회차가 계속 났고, '문장단위 삭제'는
#   심한 달을 통째로 비워(9월 3→0문장) 탈락 확인. → '앞달과 겹쳐 삭제하면 붕괴(≤1문장)하는 달'만 골라, 그 달
#   십성 뜻으로 '앞달과 다르게' 서술만 재생성하고 splice. 코드 헤더(십성·기운·관계)는 불변, 겹칠 때만 추가 LLM
#   (평소 지연 0), 1라운드 한정. [GUARD 신년운세 1.0 준수] _sinnyeon_missing·canon 스왑게이트 불변 — canon 뒤
#   '별도 dedup 패스'로 서술만 교체(전면 재생성/판정기준 변경 아님).
_SENT_SPLIT = _re.compile(r"(?<=[.。!?])\s+")
_MONTH_HEAD_RE = _re.compile(r"####\s*(\d{1,2})\s*월")


def _sinnyeon_norm_sent(sent: str) -> str:
    """문장 비교용 정규화 — 한글만 남겨 앞 40자(구두점·공백·한자 차이 무시)."""
    return _re.sub(r"[^가-힣]", "", sent)[:40]


_SINNYEON_GRAM_K = 15   # 재활용 감지 단위 — 15자+ 공통 '클로즈'(부분문자열)면 같은 문구 재탕으로 본다.


def _sinnyeon_15grams(text: str) -> set[str]:
    """한글만 남긴 뒤 15자 슬라이딩 시그니처 집합 — 문장 '앞부분'이 아니라 '어디에 있든' 공통 클로즈를 잡는다.
    [운영자 실측 2026-08-06] 약모델이 도입부만 바꾸고('일곱 번째 달에는…') 뒤 문구를 재탕해, 앞40자 비교가
    못 잡던 교차 반복('…자기 성장을 위해 다양한 경험들을 쌓아보는 것도 좋겠습니다' 3·7·12월)을 시그니처로 검출."""
    t = _re.sub(r"[^가-힣]", "", text)
    k = _SINNYEON_GRAM_K
    return {t[i:i + k] for i in range(len(t) - k + 1)} if len(t) >= k else set()


def _sinnyeon_month_narr_map(answer: str) -> dict[int, str]:
    """완성 답에서 {월번호: 서술본문} 추출 — '· 관계 —' 팩트라인 이후가 서술(코드 헤더 제외)."""
    out: dict[int, str] = {}
    for m in _re.finditer(r"####\s*(\d{1,2})\s*월.*?(?=####\s*\d{1,2}\s*월|\n###\s|\Z)", answer, _re.S):
        n = int(m.group(1))
        if not (1 <= n <= 12):
            continue
        parts = _re.split(r"·\s*관계\s*[—–\-][^\n]*\n", m.group(0), maxsplit=1)
        out[n] = (parts[1] if len(parts) > 1 else "").strip()
    return out


def _sinnyeon_dup_months(answer: str) -> list[int]:
    """앞선 달과 '15자+ 공통 클로즈'(같은 문구 재탕)를 가진 달을 반환 — 표적 재생성 대상.

    [운영자 실측 2026-08-06] 종전 '앞40자 문장' 비교는 도입부만 바꾼 재탕('일곱 번째 달에는…' + 뒤 문구 복붙)을
    통째로 놓쳤다(사용자 출력에서 3·7·11·12월 재활용을 0개로 오판). 시그니처(15-gram) 교집합으로 '어디에 있든'
    공통 클로즈를 검출 — 전면 문장 복붙(붕괴)도 15-gram을 공유하므로 함께 잡힌다(종전 기준의 상위 집합)."""
    narrs = _sinnyeon_month_narr_map(answer)
    seen: set[str] = set()
    dup: list[int] = []
    for n in sorted(narrs):
        g = _sinnyeon_15grams(narrs[n])
        if g and (g & seen):        # 앞선 달과 15자+ 공통 클로즈 = 문구 재탕
            dup.append(n)
        seen |= g
    return dup


# 재생성 표류 감지 — 그 달이 아니라 '올해/세운/총운'을 다시 쓰거나 일생 운운하면 폐기(원본 유지).
_REGEN_DRIFT = _re.compile(r"세운|올 한 해|올해\s*전반|올해는|2026\s*년|총운|일생|한 해를")


def _sinnyeon_regen_gate(body: str) -> str:
    """재생성 서술 품질 게이트 — 앞 4문장으로 절단 후 (연간 표류·과다길이·문장부족)이면 빈 문자열(원본 유지).

    [운영자 실측 2026-08-06] 재생성이 그 달을 벗어나 '올해 세운·총운'을 5문단으로 다시 쓰는 실패(17%)를
    이 게이트가 걸러 원본(짧은 1차)만 유지 — '길고 틀린 재생성'이 화면에 나가는 것을 원천 차단."""
    if not body:
        return ""
    sents = [x for x in _SENT_SPLIT.split(body) if x.strip()]
    trimmed = " ".join(sents[:4]).strip()               # 4문장 초과 절단(폭주 방지)
    ok_sents = [x for x in _SENT_SPLIT.split(trimmed) if len(_sinnyeon_norm_sent(x)) >= 8]
    if len(ok_sents) < 2 or len(trimmed) > 400 or _REGEN_DRIFT.search(trimmed):
        return ""                                        # 표류·과다·부족 → 폐기
    return trimmed


def _sinnyeon_regen_months(brief: str, sys_content: str, s, targets: list[int],
                           row: ToolSession, avoid: dict[int, str],
                           avoid_grams: set[str] | None = None) -> dict[int, str]:
    """지정한 달들의 서술을 '그 달 십성 뜻으로, 앞달과 다르게' 재생성 → {월: 서술}. 항목별 스레드 병렬.
    코드가 마커 없이 '순수 서술'만 받아 호출부가 splice(헤더 불변)한다. 실패 항목은 원본 유지(빈 결과).
    avoid_grams(다른 달 15-gram 집합)와 15자+ 겹치는 후보는 거부·재시도 — 재생성이 같은 클로즈를 재탕 못 함."""
    r = row.result_json or {}
    day_stem = r.get("day_stem") or ""
    try:
        year_branch = (((row.chart_json or {}).get("pillars") or {}).get("year") or {}).get("branch")
    except Exception:  # noqa: BLE001
        year_branch = None
    by_n: dict[int, dict] = {}
    star: dict[int, str] = {}
    for mth in r.get("months") or []:
        try:
            n = int(mth.get("month"))
        except Exception:  # noqa: BLE001
            continue
        by_n[n] = mth
        tg = mth.get("ten_god", ""); btg = mth.get("branch_ten_god", "")
        star[n] = ("월간 " + (_STAR_KO.get(tg, tg) if tg else "")
                   + (f", 월지 {_STAR_KO.get(btg, btg)}" if btg else "")).strip(", ")
    results: dict[int, str] = {}

    def _one(n: int) -> None:
        mth = by_n.get(n)
        if not mth:
            return
        sg = star.get(n, "")
        _av = "\n".join(f"- ({k}월) {v[:100]}" for k, v in sorted(avoid.items()) if k != n)[:400]
        # [운영자 실측 2026-08-06] 재생성이 full brief를 받아 '올해 세운·총운'을 다시 쓰거나(그 달 십성 무시)
        #   5문단으로 폭주하는 실패(17%). 근본수정: full brief 대신 '그 달 미니 컨텍스트'(월 헤더+일간)만 줘
        #   연간 데이터 자체를 안 보여준다(표류원 제거) + 이 달 국한 강화 + num_predict 축소 + 게이트 + 재시도.
        mini = (f"[내 사주 일간(나 자신)] {day_stem}\n[{n}월 이 달 정보]\n"
                + _sinnyeon_month_header(mth, day_stem, year_branch))
        instr = (
            f"위 [{n}월 이 달 정보]만 보고, 이 한 달의 운을 짧게 씁니다. 이 달의 십성은 '{sg}'입니다. 이 십성의 "
            "'뜻'만 근거로 그 달에 '생길 수 있는 일·조심할 점·활용 조언'을 2~3문장(200자 내외)으로 간결하게 "
            "쓰세요. ★올해 전체·세운·총운·다른 달 이야기는 절대 쓰지 말고 오직 이 달에만 국한하세요. "
            "십성·운성·신살·간지·점수·소제목·마커·번호·연도·인용부호 금지, 한국어 서술 문장만. "
            "다른 달과 겹치지 않게 이 달 십성에 맞는 소재로. 이미 다른 달에 쓴 문장(겹치면 안 됨):\n" + _av
        )
        _ag = avoid_grams or set()
        _last = ""                                  # 게이트는 통과했으나 겹친 후보(전부 실패 시 최후 채택)
        for _try in range(3):                      # 게이트 폐기·클로즈 재탕 시 최대 3회 재시도(폐기율↓·불량 0)
            try:
                out = chat_service._call_ollama(
                    [{"role": "system", "content": sys_content},
                     {"role": "user", "content": f"{mini}\n\n[이번에 쓸 부분만] {instr}"}],
                    num_predict=320)
            except Exception:  # noqa: BLE001 — 한 항목 실패 → 재시도, 끝내 실패면 원본 유지
                out = None
            body = _sinnyeon_regen_gate(_clean_month_narrative(out or ""))
            if not body:
                continue
            if _sinnyeon_15grams(body) & _ag:      # 다른 달과 15자+ 겹침 = 또 재탕 → 재시도
                _last = body
                continue
            results[n] = body
            return
        if _last:                                   # 3회 다 겹쳤으면 그나마 게이트 통과본 채택(원본 재탕보다 나음)
            results[n] = _last

    ths = [threading.Thread(target=_one, args=(n,), daemon=True) for n in targets]
    for t in ths:
        t.start()
    for t in ths:
        t.join(timeout=s.ollama_timeout_sec + 30)
    return results


def _sinnyeon_splice_month(answer: str, n: int, new_narr: str) -> str:
    """월 N 블록에서 '· 관계 —' 팩트라인 '이후 서술'만 new_narr 로 교체(헤더·팩트라인 불변). 못 찾으면 원본."""
    pat = _re.compile(
        r"(####\s*" + str(n) + r"\s*월.*?·\s*관계\s*[—–\-][^\n]*\n)(.*?)(?=####\s*\d{1,2}\s*월|\n###\s|\Z)",
        _re.S)
    new_answer, cnt = pat.subn(lambda m: m.group(1) + "\n" + new_narr.strip() + "\n\n", answer, count=1)
    return new_answer if cnt else answer


def _stream_message_inner(
    db: Session, tool_id: str, message: str, user: User | None = None,
    depth: str = "deep", explain_level: str = "normal",
    _receipt: dict[str, Any] | None = None,
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
    # [교차검증 2026-07-22] 꿈해몽 브리핑에는 정적 상징 사전이 실린다(_render → dream 블록).
    # 그런데 has_sources 를 rag_ctx 로만 판정하면, 해몽 RAG 가 실질 0건이라 거의 항상
    # "이번 답변에는 참고자료가 없습니다"가 시스템 프롬프트에 붙는다 — **브리프에는 자료가
    # 있는데** 없다고 지시하는 자기모순이다(실 세션 재현). 첫 풀이(api/dream.py)는 맞게
    # 처리했는데 후속질문만 빠져 있었다. 브리프에 자료가 실렸는지도 함께 본다.
    _brief_has_sources = "[전통 해몽 자료" in brief
    dialect = (getattr(user, "answer_dialect", None) or "standard") if user else "standard"
    di = chat_service._dialect_instruction(dialect)
    locale = getattr(row, "locale", "ko")   # 세션 확정 로케일 — 응답 언어·모델 선택(chat 미러)
    has_assistant = any(m.role == "assistant" for m in row.messages)
    is_explain = not has_assistant

    # ---- 내부 RAG(학습 코퍼스) — 사주와 동일하게 기본·심화 모두 활용 ----
    rag_query = _rag_query(row, brief, message)
    chunks = chat_service.retrieve_for_menu(
        rag_query, depth, session_id=tool_id, question=(message or None),
        menu=f"{row.tool}/{row.kind}",
    )
    # [옵션 D 동반, 2026-08-04] 신년운세 첫 해설 RAG 컷(→4청크) — 십성·운성·신살 팩트는 brief(결정적 분석표)가
    # 전담하고 RAG는 톤 기여인데, 쿼리가 질문이 아닌 brief 요약이라 표적성도 낮다. 8청크 ≈ 유저 프롬프트의
    # 38~40%(프리필 세금)라 절반으로 — 첫 글자 단축. 추가질문(질문 기반 쿼리)은 기존 top_k 유지.
    if row.tool == "sinnyeon" and not any(m.role == "assistant" for m in row.messages) and len(chunks) > 4:
        chunks = chunks[:4]
    rag_ctx = chat_service.rag_context_block(chunks)

    # 신년운세 첫 해설: ①총운+영역은 라이브 스트림 + ②③월별은 백그라운드 병렬(스트리밍 호환 배치).
    _sinnyeon_stream_batched = False
    _sinnyeon_single = False
    if is_explain:
        is_preview = row.is_preview
        billing_mode = "tool_explain"; credits = 0
        use_free = use_daily = use_mem = False
        sys_content = chat_service._compose_sys_content(
            _system_for(row), dialect, explain_level,
            has_sources=bool(rag_ctx or _brief_has_sources), locale=locale)
        ucontent = brief if not rag_ctx else f"{brief}\n\n[참고자료]\n{rag_ctx}"
        # P1-4: 자료에 남의 명식이 섞여 와도 본인 명식으로 쓰지 않게(종전 chat 전용 가드를 이식).
        # 신년운세는 RAG 가 사용자 프롬프트의 38~40%, 무료 메뉴는 84~86%를 차지하는데 가드가 없었다.
        _cr = chat_service.chart_reconfirm_block(getattr(row, "chart_json", None))
        if rag_ctx and _cr:
            ucontent += f"\n\n{_cr}"
        # 신년운세 첫 해설 경로 분기(옵션 D, 2026-08-04 운영자 승인):
        #   단일패스(기본) = 콜 1개가 [[마커]]+서술 전체를 스트림 → _SinnyeonScaffold 가 실시간 헤더 치환.
        #   배치(롤백)    = ①총운 스트림 + ②③④ 백그라운드 4배치(구 구조, SINNYEON_SINGLE_PASS=false).
        _sinnyeon_expl = row.tool == "sinnyeon" and not is_preview
        _sinnyeon_single = _sinnyeon_expl and s.sinnyeon_single_pass
        _sinnyeon_stream_batched = _sinnyeon_expl and not s.sinnyeon_single_pass
        if _sinnyeon_single:
            # 대상 연도 명시 주입 — UI에서 '내년' 선택 시 지시문의 '올 한 해' 표현이 모델을 올해로
            # 끌던 소지 제거(운영자 확인 2026-08-04). 연도별 간지·점수는 result_json(생성 시 계산)이 전담.
            _yy = (row.result_json or {}).get("year") or (row.input_json or {}).get("year")
            ucontent += _SINNYEON_SINGLE_INSTR.replace(
                "{TARGET_YEAR}", f"{_yy}년" if _yy else "대상 연도")
        elif _sinnyeon_stream_batched:
            ucontent += (
                "\n\n[이번에 쓸 부분만] ① 총운(2~3문단)만 쓰세요 — 세운 간지가 내 일간(강약)과 맺는 십성·"
                "합충 관계를 근거로 올 한 해 '전체' 흐름·기회·유의점을. ★'올 한 해 전체' 흐름이니 '이번 달' 같은 "
                "특정 월 표현을 쓰지 말고, '여러분'이 아니라 '당신(손님)'을 주어로 하세요. ② 영역별 심화·③ 월별 "
                "흐름·④ 마무리 조언은 절대 쓰지 마세요 — 다른 파트에서 이어 씁니다.")
        msgs = [{"role": "system", "content": sys_content}, {"role": "user", "content": ucontent}]
        save_user = None
    else:
        if not message:
            # [운영자 승인 2026-08-04] 해설이 이미 저장된 세션에 빈 메시지(=복원 화면의 '설명' 클릭,
            #   캐시된 구프론트 포함)가 오면 에러 대신 저장 해설을 '재전송'(멱등·무과금). 종전엔
            #   "질문을 입력해 주세요." 에러 → 청크 0개 → 프론트가 "해설 생성이 지연"으로 오표시(실측 재현).
            _prev = next((m for m in reversed(row.messages) if m.role == "assistant"), None)
            if _prev and (_prev.content or "").strip():
                _locked = _prev.is_preview and not _prev.preview_revealed
                _content = chat_service._make_preview(_prev.content) if _locked else _prev.content
                _content = fix_naming_hanja(chat_service.fix_term_hanja(_content), row.result_json)
                yield ("meta", {"billing_mode": "explain_replay", "is_preview": _locked,
                                "mode": "explain", "will_refine": False})
                for _seg in _content.split("\n\n"):
                    if _seg.strip():
                        yield ("chunk", {"text": _seg + "\n\n"})
                yield ("done", {"assistant_message_id": _prev.id, "is_preview": _locked,
                                "preview_revealed": not _locked, "full_length": len(_content),
                                "preview_length": len(_content), "credits_charged": 0,
                                "balance_after": (auth_service.get_balance(db, user.id) if user else None),
                                "billing_mode": "explain_replay", "refined": False, "flash": False})
                return
            yield ("error", {"detail": "질문을 입력해 주세요."}); return
        # 프리미엄 메뉴 추가질문: 무료한도 미적용(항상 1,000/3,000P 차감)
        bill = chat_service._decide_billing(db, user, depth, allow_free_quota=False, claim=True)
        is_preview = bill["is_preview"]; credits = bill["credits_to_charge"]
        billing_mode = bill["billing_mode"]
        use_free = bill["use_free_quota"]; use_daily = bill["use_daily_free"]; use_mem = bill["use_membership"]
        # free-ride 차단: 추가질문 유료차감·멤버십 선점을 '생성 전' 확정 커밋(끝 커밋은 disconnect 시 롤백됨).
        _pre_charged = chat_service.precharge_followup(db, user, bill, reason="tool_q", ref_id=tool_id)
        # 미정산 청구 등록 — 아래 방어 분기를 벗어난 예외가 나면 래퍼(stream_message)가 이걸 보고 보상한다.
        if _receipt is not None and not is_explain:
            _receipt.update(bill=bill, pre_charged=_pre_charged)
        # [2026-07-25] 후속질문 경로(else=has_assistant)에 question·is_followup 전달 — 종전엔 미전달이라
        # 주제집중 라우팅/추가질문 규칙이 통째로 빠지고 종합템플릿이 주입돼 동문서답 재발원이었다(chat과 동일 결함).
        sys_content = chat_service._compose_sys_content(
            _system_for(row), dialect, explain_level,
            question=message, is_followup=True,
            has_sources=bool(rag_ctx or _brief_has_sources), locale=locale)
        analysis = f"[분석]\n{brief}" + (f"\n\n[참고자료]\n{rag_ctx}" if rag_ctx else "")
        _cr = chat_service.chart_reconfirm_block(getattr(row, "chart_json", None))
        if rag_ctx and _cr:
            analysis += f"\n\n{_cr}"          # P1-4 명식 가드
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
    # ★[운영자 실측 2026-08-06] 단일패스는 qwen/claude '보정(전문 재작성)'을 건너뛴다. 설계 원칙은
    #   "단일패스 정상 런 = 교체 0회, 결정적 원포인트 교정만"(e517fc80)인데, dedup·분량 게이트는 not
    #   _sinnyeon_single 로 막혀 있었으나 이 보정 게이트만 가드가 빠져 1차를 통째로 다시 그렸다 —
    #   그 2차 재작성이 양식(월 헤더)을 뭉개고 문장을 반복시켜 "2차가 1차보다 못한" 열화를 냈다.
    do_qwen = (not is_preview) and s.deep_local_refine_enabled and not _sinnyeon_single   # 1차 내부 보강(기본·심화)
    # 심화 외부(미국) 보강은 국외이전 별도 동의(H4, 제28조의8) 회원만.
    do_claude = (depth == "deep" and (not is_preview) and _claude_avail
                 and getattr(user, "overseas_transfer_opt_in", False) and not _sinnyeon_single)
    will_refine = do_qwen or do_claude
    yield ("meta", {"billing_mode": billing_mode, "is_preview": is_preview,
                    "mode": "explain" if is_explain else "followup", "will_refine": will_refine})

    parts: list[str] = []
    tok_q: "_queue.Queue[Any]" = _queue.Queue()
    SENT = object()
    err: dict[str, Exception] = {}
    stop_event = threading.Event()  # 클라 이탈 시 메인 Ollama producer 조기 종료

    # 스트리밍 호환 배치: ②영역·③월별·④마무리를 '지금' 백그라운드 병렬로 착수 → 아래 ①총운 라이브
    #   스트림과 동시에 굴러가, 스트림이 끝날 즈음 이미 완료돼 있다. join(조립·이어붙임)은 스트림 종료 직후.
    _batch_join = (_start_sinnyeon_batches(sys_content, brief, rag_ctx, s)
                   if _sinnyeon_stream_batched else None)

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
    # 옵션 D: 단일패스 스캐폴드 — 스트림을 실시간 변환(마커→결정적 헤더), 원문은 최종 재조립용으로 별도 보관.
    _scaf = _SinnyeonScaffold(row) if _sinnyeon_single else None
    _raw_parts: list[str] = []
    _pmax = settings_service.get_cached_int("preview_max_chars", s.preview_max_chars)  # 관리자 설정 반영(사주 chat 과 통일)
    pchars = 0; cut = False
    _dg_since = 0   # 반복 퇴행 조기중단 카운터
    _degen_aborted = False   # 조기중단 발동 여부 — 발동 시 최종본 강제 재생성(잘린 답 저장 방지)
    # 클라 이탈(GeneratorExit) 시 finally 가 stop_event 를 set → 고아 추론 차단.
    try:
        while True:
            try:
                item = tok_q.get(timeout=s.sse_heartbeat_sec)
            except _queue.Empty:
                yield ("ping", {}); continue
            if item is SENT:
                break
            if _scaf is not None:
                _raw_parts.append(item)
                item = _scaf.feed(item)
                if not item:
                    continue    # 홀드백 중(마커 경계 보류) — 내보낼 텍스트 없음
            parts.append(item)
            # 반복 퇴행 조기중단 — 최근 꼬리가 폭주하면 생성을 끊는다(최종본은 _correct_degenerate 가 교정/환불)
            _dg_since += 1
            if _dg_since >= 40:
                _dg_since = 0
                _acc = "".join(parts)
                if len(_acc) >= 240 and chat_service._stream_is_degenerating(_acc[-400:]):
                    _degen_aborted = True; stop_event.set(); break
            if is_preview:
                if not cut:
                    rem = _pmax - pchars
                    if rem > 0:
                        snd = item[:rem]; pchars += len(snd)
                        if snd:
                            yield ("chunk", {"text": snd})
                    if pchars >= _pmax:
                        cut = True; yield ("cut", {"reason": "preview_limit"})
            else:
                yield ("chunk", {"text": item})
    finally:
        stop_event.set()

    # 옵션 D: 홀드백 잔여분 방출(마커 노출 없이 변환) — 에러 시엔 폴백 경로가 parts 를 대체하므로 생략.
    if _scaf is not None and "e" not in err:
        _tail = _scaf.flush()
        if _tail:
            parts.append(_tail)
            yield ("chunk", {"text": _tail})

    # ---- 1차 로컬(qwen3:14b) 실패 → 외부(Claude) 폴백 (사주와 동일) ----
    local_ok = "e" not in err
    if not local_ok:
        e = err["e"]
        fb = None
        if not is_preview:
            # [2026-08-04 퀵윈] 외부폴백(최대 ~25s) 동기 대기 무음 → 하트비트 랩('무음사망' 차단).
            def _fb_call():
                return chat_service.external_fallback_answer(
                    question=(message or "해설"), evidence=brief, rag_context=rag_ctx,
                    dialect_instruction=di or None, locale=locale,
                    allow_overseas=(settings_service.get_bool(db, "overseas_llm_fallback_enabled", False)
                                    and getattr(user, "overseas_transfer_opt_in", False)),
                )
            for _fev in chat_service._bg_with_heartbeat(s, _fb_call, progress_phase="refining"):
                if _fev[0] == "result":
                    fb = _fev[1]
                else:
                    yield _fev
        if fb:
            parts = [fb]
            yield ("refine", {"text": fb, "reason": "로컬 엔진 불가 — 외부 AI 폴백"})
        else:
            if not is_explain:   # explain 은 입장료 커버(precharge 안 함) — bill/_pre_charged 미정의라 환불도 하지 않음
                chat_service.refund_followup(db, user, bill, _pre_charged, reason="tool_q", ref_id=tool_id)
                if _receipt is not None: _receipt.clear()   # 자체 환불 완료 — 래퍼의 이중환불 차단
            code = "service_unavailable" if isinstance(e, chat_service.ServiceUnavailableError) else None
            yield ("error", {"detail": str(e), **({"code": code} if code else {})}); return

    # ── 스트리밍 호환 배치: ①총운 라이브 스트림이 끝났으니 동시에 굴러온 ②영역·③월별·④마무리를 이어붙인다 ──
    #   배치 스레드는 스트림과 병렬로 이미 거의 완료. _bg_with_heartbeat 로 감싸 join 대기 중에도 ping 을
    #   흘려 무음 프록시 타임아웃(524)을 막는다. 영역·월별 팩트(점수·십성·운성·신살)는 코드가 결정적 헤더로
    #   붙이고 모델 서술만 채운다 → 약모델이 영역/달을 빠뜨려도 5영역·12달 완결·정확 보장(누락은 폴백 문장).
    if _batch_join is not None and local_ok and "".join(parts).strip():
        _batch: dict = {}
        for ev in chat_service._bg_with_heartbeat(s, _batch_join, progress_phase="generating"):
            if ev[0] == "result":
                _batch = ev[1] or {}
            else:
                yield ev
        if any(_batch.values()):
            _domains = _assemble_sinnyeon_domains(row, _batch.get("domain") or "")
            _months_raw = "\n\n".join(v.strip() for k in ("m1", "m2", "m3")
                                      for v in [_batch.get(k)] if v and v.strip())
            _months = _assemble_sinnyeon_months(row, _months_raw)
            _combined = (_domains + "\n\n" + _months).strip()
            parts.append("\n\n"); yield ("chunk", {"text": "\n\n"})
            for _seg in _combined.split("\n\n"):
                if _seg.strip():
                    _seg2 = _seg + "\n\n"
                    parts.append(_seg2)
                    yield ("chunk", {"text": _seg2})

    answer = "".join(parts)
    refined = False
    _q = message or "해설"
    # ── 옵션 D: 마커 원문을 결정적 어셈블러로 재조립 — 5영역·12달·마무리 '완결'을 코드가 보장(누락=폴백 문장,
    #    순서 뒤섞임=정순 재배열). 스트림 표시본과 실질 같으면 화면 유지, 다르면(누락 보충 등) 1회만 교체 알림.
    if _sinnyeon_single and local_ok and not _degen_aborted and answer.strip():
        # 스캐폴드가 '평문 섹션 시작'을 감지해 [[마커]]를 주입한 '정규화 raw' — 모델이 마커를 빠뜨려도
        #   결측판정·canon 이 그 섹션을 '있음'으로 보고, 순서 정상이면 canon 교체 0회(1차=최종). [운영자 승인]
        _raw_all = _scaf.normalized_raw() if _scaf is not None else "".join(_raw_parts)
        # 표적 보강(실측 게이트 r1형: 모델이 3달 쓰고 조기종료) — 마커는 썼는데 일부 영역/달이 빠졌으면
        # '빠진 것만' 소형 콜 1회로 채운다(전면 재생성 아님 — 잘 나온 본문 불변, 폴백 문장 대신 실서술).
        _had_gap = False
        _bad_order = False
        if _SCAF_ANY.search(_raw_all):
            _missing_m, _missing_d = _sinnyeon_missing(_raw_all)   # '본문 있는지' 기준(마커만으론 오탐)
            _mm_seq = [int(mt.group(1)) for mt in _MONTH_MARK.finditer(_raw_all)
                       if 1 <= int(mt.group(1)) <= 12]
            _bad_order = _mm_seq != sorted(_mm_seq)
            # [DO-NOT-MODIFY 준수 — 되돌림 2026-08-05] '마무리 위치' 트리거는 스왑게이트 완화라 제거.
            #   정상 런은 교체 0회 원칙 유지 — 마무리가 달 사이에 끼는 드문 케이스는 파서(위치기반)가
            #   누출 없이 처리하므로 canon 전문교체를 새로 유발하지 않는다(품질 역전 방지).
            _had_gap = bool(_missing_m or _missing_d)
            # 표적 보강 '재시도 루프'(최대 3회) — [운영자 실측 2026-08-05] 약모델이 단일패스에서 달을 심하게
            #   빠뜨린다(3~6달만 쓰고 조기종료가 잦음). ★마커는 코드가 붙이는 '항목별 병렬 백필'(_sinnyeon_backfill)
            #   로 채운다 — 배치 백필은 모델이 마커를 무시하고 평문으로 써 파싱 실패→폴백+평문 누출됐다(재현 확정).
            #   남은 결측만 다시 요청하며 12달·5영역 완결로 수렴(빈 결과면 중단·무한루프 방지). 전면 재생성 아님.
            _bf_round = 0
            while (_missing_m or _missing_d) and _bf_round < 3:
                _bf_round += 1
                _wrapped = None
                for ev in chat_service._bg_with_heartbeat(
                        s, lambda mm=list(_missing_m), md=list(_missing_d):
                        _sinnyeon_backfill(brief, sys_content, s, mm, md),
                        progress_phase="generating"):
                    if ev[0] == "result":
                        _wrapped = ev[1]
                    else:
                        yield ev
                if not (_wrapped and _wrapped.strip()):
                    break                                      # 진전 없음 → 무한루프 방지
                _raw_all += "\n\n" + _wrapped
                _missing_m, _missing_d = _sinnyeon_missing(_raw_all)   # 남은 결측 재판정 후 다음 라운드
        # [GUARD 신년운세 1.0 — 조건 완화 금지] ★1차 생성물 보존 원칙 — 정본 '전문 교체'는 완결이 깨진 런(달·영역 누락,
        #   순서 뒤섞임)에만 한다. 멀쩡한 런까지 매번 재조립본으로 갈아끼우니 클리너가 모델의 부가 구조
        #   (분기 요약 등)를 깎아 "2차가 1차보다 못한" 품질 역전이 났다(운영자 실측). 멀쩡한 런은 화면
        #   그대로 두고, 오타·독음·한자·세운간지·양식은 아래 '결정적 원포인트 교정'만 지나간다.
        if _had_gap or _bad_order:
            _canon = _assemble_sinnyeon_full(row, _raw_all)
            if _canon and _norm_ws(_canon) != _norm_ws(answer):
                answer = _canon
                refined = True
                yield ("refine", {"text": answer, "reason": "섹션 완결 정리(누락 보강·순서 정렬)"})
        # 표적 dedup 재생성 — 앞달과 겹쳐 붕괴(고유 ≤1문장)하는 달만 '앞달과 다르게' 서술 재생성 후 splice.
        #   [운영자 승인 2026-08-06] 印 고착 명식(무토+병오 등)의 월별 복붙 해소. 겹칠 때만 추가 LLM(평소
        #   지연 0), 1라운드. 코드 헤더·팩트라인 불변, canon/판정기준 불변(별도 패스에서 '서술만' 교체).
        _dups = _sinnyeon_dup_months(answer)
        if _dups:
            _narr_all = _sinnyeon_month_narr_map(answer)
            _avoid = {k: v[:120] for k, v in _narr_all.items() if k not in _dups}
            # 재생성이 '다른 달과 겹치지 않게' — 재생성 안 하는 달들의 15-gram 을 거부셋으로(재탕 차단)
            _av_grams: set[str] = set()
            for _k, _v in _narr_all.items():
                if _k not in _dups:
                    _av_grams |= _sinnyeon_15grams(_v)
            _regen = None
            for ev in chat_service._bg_with_heartbeat(
                    s, lambda tg=list(_dups): _sinnyeon_regen_months(
                        brief, sys_content, s, tg, row, _avoid, _av_grams),
                    progress_phase="generating"):
                if ev[0] == "result":
                    _regen = ev[1]
                else:
                    yield ev
            if _regen:
                _changed = False
                for _n, _nb in _regen.items():
                    # 재생성본이 최소 2문장 이상일 때만 채택(1줄로 더 얇아지는 것 방지)
                    _cnt = sum(1 for x in _SENT_SPLIT.split(_nb) if len(_sinnyeon_norm_sent(x)) >= 12)
                    if _cnt < 2:
                        continue
                    _spliced = _sinnyeon_splice_month(answer, _n, _nb)
                    if _spliced != answer:
                        answer = _spliced; _changed = True
                if _changed:
                    refined = True
                    yield ("refine", {"text": answer, "reason": "월별 중복 해소(표적 재서술)"})
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

    # ---- 월별 완결성 '재생성' 백스톱 — [제거 2026-08-04, 운영자 지시] ----
    # 실측(운영자): '월별만 다시 생성해 교체(splice)'하는 이 재생성이 '잘 나온 첫 답변'을 오히려 망쳤다.
    #   첫 답변이 '#### N월' 형식이 아니면 파서가 못 찾아 교체 대신 '덧붙여' 12개월이 중복되고, 재생성된
    #   월별 자체가 순서뒤섞임·빈칸·독음오류(을미→으미)·한자혼입으로 열화됐다. "재생성하면서 좋은 걸
    #   틀지 말고, 문장을 전체적으로 읽어 오류를 보완하는 방향으로" 지시에 따라 월별 재생성을 제거한다.
    #   완결성은 SINNYEON_SYSTEM 프롬프트 지시로 유도하고, 아래 정리 체인이 첫 답변을 다듬어 내보낸다.
    #   대신 결정적 정리: 혹시 남은 '중복 월 섹션'을 읽어서 제거(재생성 아님, 오류 보완).
    # [2026-08-04 운영자 지시] 단일패스 경로는 문장 dedupe 생략 — 스캐폴드가 월 중복을 구조적으로 차단하고,
    #   문장 단위 삭제가 '비슷하지만 유효한' 조언까지 깎아 1차 품질을 역전시키던 삭감원이었다(배치 경로만 유지).
    if is_explain and row.tool == "sinnyeon" and not _sinnyeon_single and answer.strip():
        _clean = chat_service._dedupe_repeated_sentences(
            chat_service._dedupe_month_sections(answer))
        if _clean and _clean != answer:
            answer = _clean
            refined = True
            yield ("refine", {"text": answer, "reason": "중복 문장·월별 정리"})

    # ---- 분량 백스톱(유료 메뉴 첫 해설 — 운영자 지시: 돈 받는 메뉴가 빈약하면 안 됨) ----
    # 실측: 약한 모델이 프롬프트 최소 분량을 무시(궁합 889자·택일 972자·작명 913자). 미달 시 1회만
    # 같은 구성·같은 사실로 확장 재생성(환각 가드: brief 재주입 + '표에 없는 값 추가 금지' 명시).
    # [2026-07-31] 유료 메뉴 빈약 해소(운영자 지시). 첫 해설(is_explain, 종합)은 taekil/naming 1300→2500
    #  상향(심화 +500). [패딩 검수 반영] 추가질문(is_explain=False)은 단일주제라 낮은 안전바닥(1,500/1,800)만
    #  — 강제 재생성 패딩 방지. 확장 시 '새 내용만'(부연·복붙 금지) 요구.
    if is_explain:
        _MIN_EXPLAIN = {"sinnyeon": 3000, "taekil": 2500, "naming": 2500}
        _min_chars = _MIN_EXPLAIN.get(row.tool)
        if _min_chars and depth == "deep":
            _min_chars += 500
    else:
        _min_chars = 1800 if depth == "deep" else 1500
    # [GUARD 신년운세 1.0 — 게이트 제거 금지] 신년운세 단일패스는 분량바닥 '전문 재작성'을 건너뛴다 —
    #   완결·풍부는 스캐폴드(결정적 헤더+팩트) + 표적 보강이 전담하고, 전문 재작성은 1차 보존 원칙 위반.
    if local_ok and _min_chars and not _sinnyeon_single and answer.strip() and len(answer) < _min_chars:
        yield ("stage", {"phase": "refining"})
        _exp = None
        _expand_user = (
            f"{brief}\n\n[이전 답변]\n{answer}\n\n"
            f"[지시] 이전 답변이 {len(answer)}자로 너무 짧습니다(유료 리포트 최소 {_min_chars}자). "
            "같은 구성과 같은 사실을 유지한 채, 각 섹션(각 이름/각 날짜/각 영역·각 달)을 훨씬 풍부하게 "
            "다시 작성하세요 — 구체적 장면·활용 조언으로 채우되, 이전 답변의 문장·논점을 반복·부연·복붙하지 "
            "말고 아직 다루지 않은 새 내용만 더하세요(도입·결론 복붙 금지). "
            "★[분석]에 없는 간지·십성·합충·날짜·획수·점수는 절대 추가하지 마세요."
        )
        def _expand_call(_u=_expand_user, _sc=sys_content, _mc=_min_chars):
            try:
                return chat_service._call_ollama(
                    [{"role": "system", "content": _sc}, {"role": "user", "content": _u}],
                    num_predict=max(5120, _mc + 1500))
            except Exception:  # noqa: BLE001 — 확장 실패 시 원본 유지(부가 기능)
                return None
        for ev in chat_service._bg_with_heartbeat(s, _expand_call):
            if ev[0] == "result":
                _exp = ev[1]
            else:
                yield ev
        _expc = chat_service._safe_replace(answer, _exp, min_ratio=1.0, hard_floor=True)  # 더 길고 완결일 때만
        if _expc and len(_expc) > len(answer):
            answer = chat_service.fix_term_hanja(_expc)
            refined = True
            yield ("refine", {"text": answer, "reason": "분량 보강(유료 리포트 기준)"})
        yield ("stage", {"phase": "refine_done"})

    # ---- 명식 정합성 검증·교정 (절대규칙) — 답변의 4주 지지가 본인 명식과 다르면 교정 ----
    if not is_preview and answer.strip():
        _cj = getattr(row, "chart_json", None)
        _allow = chat_service._allowed_from_charts(_cj)
        # 날짜 문맥 오탐 방지: 택일('그날 일지') + 오늘운세('오늘 일지 巳가…') + 캘린더('6일은 일지가…').
        # 실측: today/calendar가 미적용이라 정답 일진 해설이 본인 일지와 대조돼 오탐·교정 오염됐다.
        # amulet 추가(2026-08-04 전수감사): 부적 시드의 '올해 연지' 문구가 본인 명식과 대조돼 오탐
        #   → 전문 재생성으로 1차 훼손 소지(실측 11건 중 2건 해당 문구). 날짜문맥 제외로 차단.
        _no_date = row.tool in ("taekil", "today", "calendar", "amulet")
        # 지지(날짜문맥 제외는 택일만) + 일간(천간) 동시 검증 — 둘은 독립
        _branch_bad = chat_service._verify_branches(answer, _allow, exclude_date_ctx=_no_date)
        _stem_bad = chat_service._verify_day_stem(answer, _cj)
        _extra = _tool_extra_verifiers(row)   # 택일 황도·개명 수리 등 메뉴별 결정값 검증
        _tool_bad = any(vf(answer) for vf in _extra)
        if _branch_bad or _stem_bad or _tool_bad:
            yield ("stage", {"phase": "verifying"})
            _fixed = None
            for ev in chat_service._bg_with_heartbeat(s, lambda af=answer: chat_service._correct_branches(
                    af, allowed=_allow, truth=chat_service._myeongsik_truth(_cj), question=_q,
                    sys_content=sys_content, saju_summary=brief, exclude_date_ctx=_no_date,
                    chart_json=_cj, extra_verifiers=_extra)):
                if ev[0] == "result":
                    _fixed = ev[1]
                else:
                    yield ev
            if _fixed and _fixed.strip() and _fixed.strip() != answer:
                answer = _fixed.strip(); refined = True
                yield ("refine", {"text": answer, "reason": "명식 정합성 자동 교정"})
        # 자료 인용 말투 제거(전문가 화법)
        _scrubbed = chat_service._scrub_self_reference(chat_service._scrub_source_refs(answer))
        if _scrubbed and _scrubbed != answer:
            answer = _scrubbed; refined = True
            yield ("refine", {"text": answer, "reason": "표현 정리"})
        # 십성 등 한자 병기 정자(正字) 교정(전문가 지적)
        _h = chat_service.fix_term_hanja(answer)
        if _h != answer:
            answer = _h; refined = True
            yield ("refine", {"text": answer, "reason": "한자 표기 정정"})

    # ── 화면=DB 일치(운영자 승인 2026-08-04 Q3) — 아래 '무음 교정'들이 이벤트 없이 answer 만 바꿔
    #    새로고침 전까지 화면과 저장본이 달랐다. 진입 시점 표시본을 기억해 끝에서 달라졌으면 1회 동기화.
    _pre_silent = answer
    _degen_refined = False
    # 미리보기 등 위 분기를 안 탄 경로까지 저장/재로드본 일관 교정(멱등).
    # 이름 한자는 후보 표 대조까지 — 이체자로 바뀌면 '다른 글자의 이름'이 나가므로 생성·읽기 대칭 적용.
    answer = fix_naming_hanja(chat_service.fix_term_hanja(answer), row.result_json)
    # 신년운세 세운 간지 환각 교정(#10) — 답변의 '세운/그해 간지'가 실제 세운과 다르면(예: 병오를 갑오로)
    #   결정적 교정. 월운(월 간지)·명식 간지는 앵커가 달라 불변. 미리보기 포함 항상·멱등.
    if row.tool == "sinnyeon" and answer.strip():
        # ③ 중국어 전용 줄 제거 + ⑤ 약모델 한국어 깨짐 교정(무분비→무분별, 내일간→내 일간 등).
        _sv = _fix_sinnyeon_vocab(answer)
        if _sv != answer:
            answer = _sv; refined = True
        try:
            _sy = (row.result_json or {}).get("year") or (row.input_json or {}).get("year")
            if _sy:
                answer = chat_service._fix_sinnyeon_seun_ganji(answer, int(_sy))
                # 월별 흐름 'N월 (으미월)' 등 무효 독음·섹션헤딩 한자환각을 그 달 실제 월간지 독음으로 교정.
                answer = chat_service._fix_sinnyeon_month_reading(answer, int(_sy))
        except Exception:  # noqa: BLE001
            pass
    # 구분선(---)·과다 빈줄 정리 — 상담(chat)과 통일(운영자 지적: tool 메뉴엔 미적용이라 '---' 누출).
    #   무손실·헤딩(#### N월) 보존 → 신년운세 월별 헤더 안전. fix_naming_hanja 뒤라 이름 한자 교정 불변.
    answer = chat_service._tidy_markdown(answer)

    # 반복 퇴행(같은 구절 폭주) 최종 가드 — 구제되면 정상본, 구제 실패면 ''(→ 아래 빈답변 경로로 미저장·환불/재시도)
    # 조기중단(_degen_aborted)으로 끊긴 잘린 답은 보수적 판정에 안 걸려도 강제 재생성(force)한다.
    if answer.strip() and (_degen_aborted or chat_service._looks_degenerate(answer)):
        # [2026-08-04] 동기 호출 → 하트비트 랩: 교정 재생성이 1~4분 걸리는 동안 SSE 완전 무음이었다
        # (3b2a3f94 를 죽인 60s 워치독과 같은 계열의 장애 리스크 — 진단 §4-2).
        _fixed = None
        for ev in chat_service._bg_with_heartbeat(s, lambda af=answer: chat_service._correct_degenerate(
                af, sys_content=sys_content, base_user=msgs[1]["content"], force=_degen_aborted),
                progress_phase="verifying"):
            if ev[0] == "result":
                _fixed = (ev[1] or "").strip() if ev[1] is not None else None
            else:
                yield ev
        if _fixed is not None and _fixed != answer:
            answer = _fixed
            if answer:
                _degen_refined = True
                yield ("refine", {"text": answer, "reason": "반복 정리"})

    # 빈 응답(무내용 또는 구제 불가 퇴행) — 유료 followup 이면 precharge 보상, explain 은 저장하지 않고 에러(재시도 유도).
    # ⚠️ explain 은 입장료가 create 에서 차감됨 — 재시도(is_explain·무과금)로 정상본을 받으므로 여기서 환불하지 않는다
    #    (재환불은 이중환불 위험). 퇴행 저장·노출만 확실히 차단한다.
    if not answer.strip():
        if not is_explain:
            chat_service.refund_followup(db, user, bill, _pre_charged, reason="tool_q", ref_id=tool_id)
            if _receipt is not None: _receipt.clear()   # 자체 환불 완료 — 래퍼의 이중환불 차단
        yield ("error", {"detail": "답변을 생성하지 못했어요. 잠시 후 다시 시도해 주세요.", "code": "internal_error"}); return

    # ── 화면=DB 최종 동기화(Q3) — 무음 교정으로 표시본과 저장본이 실질(공백 무시) 달라졌으면 최종본을 1회 푸시.
    #    미리보기는 컷 정책상 전문을 밀면 안 되므로 제외. degen 교정이 이미 밀었으면 그게 최신 표시본.
    if not is_preview and answer.strip():
        _shown = answer if _degen_refined else _pre_silent
        if _norm_ws(_shown) != _norm_ws(answer):
            yield ("refine", {"text": answer, "reason": "최종 정리"})

    # 잔액 조회 (차감·선점은 precharge_followup 에서 '생성 전' 완료됨 — 이중차감 금지)
    balance_after = auth_service.get_balance(db, user.id) if user is not None else None

    now = datetime.utcnow()
    try:
        if save_user is not None:
            db.add(ToolMessage(tool_id=tool_id, role="user", content=save_user, created_at=now,
                               is_preview=False, preview_revealed=True, credits_charged=0))
        asst = ToolMessage(tool_id=tool_id, role="assistant", content=answer, created_at=datetime.utcnow(),
                           is_preview=is_preview, preview_revealed=not is_preview, credits_charged=credits)
        db.add(asst); db.flush()
        aid = asst.id
        if not is_explain:                       # 유료 추가질문만 영수증 대상 — EOF 완결 마킹(persist 커밋에 합류)
            from backend.app.services import receipt_service
            receipt_service.finalize_receipt(db, bill.get("receipt_id"), message_id=aid)
        db.commit()
    except Exception:  # noqa: BLE001 — 저장/커밋 실패 시 생성 전 확정한 과금을 보상 원복.
        db.rollback()
        if not is_explain:
            chat_service.refund_followup(db, user, bill, _pre_charged, reason="tool_q", ref_id=tool_id)
            if _receipt is not None: _receipt.clear()   # 자체 환불 완료 — 래퍼의 이중환불 차단
        yield ("error", {"detail": "저장 중 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", "code": "internal_error"}); return

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
    # 신년운세(B-1) — kind에는 연도("2026")가 들어가므로 tool 키로 직접 매칭할 것
    "sinnyeon": ["올해 가장 조심할 달은?", "재물운이 좋은 달은 언제예요?", "이직·사업 시작은 언제가 좋나요?",
                 "연애·결혼 운은 어떤가요?", "건강에서 조심할 점은?", "올해 운을 살리려면 뭘 해야 하나요?"],
    # 무료 4메뉴 — tool 키 매칭
    "today": ["오늘 조심할 시간대가 있나요?", "오늘 중요한 약속이 있는데 어때요?", "행운의 색은 어떻게 활용하죠?",
              "오늘 재물운은 어떤가요?", "오늘 만나는 사람과의 궁합은?", "이번 주 전체 흐름도 궁금해요"],
    "calendar": ["이번 달 최고의 날은 언제예요?", "계약하기 좋은 날을 골라주세요", "이사하기 좋은 날은요?",
                 "가장 조심할 날은 언제인가요?", "손없는날엔 뭘 하면 좋나요?", "절기가 운세에 영향을 주나요?"],
    "amulet": ["부적은 어디에 지니면 좋나요?", "얼마나 오래 지니면 되나요?", "보관할 때 주의할 점은?",
               "다른 목적 부적과 같이 지녀도 되나요?", "부적 문양은 무슨 뜻인가요?", "새해에 새로 발행해야 하나요?"],
    "dream": ["이 꿈이 재물과 관련이 있나요?", "길몽인가요, 흉몽인가요?", "같은 꿈을 반복해서 꾸면요?",
              "꿈에 나온 사람은 누구를 뜻하죠?", "꿈과 내 사주는 어떤 관계인가요?", "오늘 조심할 일이 있을까요?"],
}
_NAMING_TOPIC = {"jakmyeong": "작명 상담", "gaemyeong": "개명 상담", "aho": "아호 상담"}
_TOOL_TOPIC = {"taekil": "택일 상담", "sinnyeon": "신년운세 상담", "today": "오늘의 운세 상담",
               "calendar": "운세 캘린더 상담", "amulet": "부적·개운 상담", "dream": "꿈해몽 상담"}


def _tool_fallback(row: ToolSession) -> list[str]:
    # tool 키 우선(taekil·sinnyeon·무료4메뉴 — sinnyeon의 kind는 연도 문자열), 작명류만 kind
    if row.tool in _TOOL_FALLBACK:
        return _TOOL_FALLBACK[row.tool]
    return _TOOL_FALLBACK.get(row.kind or "jakmyeong") or _TOOL_FALLBACK["taekil"]


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
    topic = _TOOL_TOPIC.get(row.tool) or _NAMING_TOPIC.get(row.kind or "", "작명 상담")
    return chat_service.suggestions_from_convo("\n".join(parts), n, topic=topic, fallback=fb)
