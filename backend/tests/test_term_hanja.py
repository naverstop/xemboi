"""명리 용어 한자(漢字) 병기 정자(正字) 교정 — fix_term_hanja (전문가 지적 대응).

배경: 시스템 프롬프트가 '한글(한자)' 병기를 지시하지만 모델에 전체 한자를 주지 않아, LLM 이
한자를 환각(劫財→劫才, 正印→正寅, 正→政)하는 일이 있다. 출력의 '용어(한자)' 괄호가 한자로만
채워졌을 때 정자로 결정적 교정하고, 괄호 안에 한글 설명이 섞이면 손대지 않는다(설명 보존).
"""
from __future__ import annotations

from backend.app.saju.constants import TEN_GODS_KO, TERM_HANJA, fix_term_hanja


def test_corrects_wrong_sipsin_hanja():
    assert fix_term_hanja("겁재(劫才) 기운") == "겁재(劫財) 기운"   # 才 → 財
    assert fix_term_hanja("정인(正寅)") == "정인(正印)"             # 寅 → 印
    assert fix_term_hanja("정관(政官)·정재(正才)") == "정관(正官)·정재(正財)"  # 政→正, 才→財


def test_preserves_korean_paren_explanation():
    # 괄호 안이 한글 설명이면 교정 대상 아님(설명 손실 방지)
    assert fix_term_hanja("겁재(재물 분산 주의)") == "겁재(재물 분산 주의)"
    # 한자+한글 혼합 괄호도 클로버하지 않음
    assert fix_term_hanja("정인(正印, 모친 인연)") == "정인(正印, 모친 인연)"


def test_idempotent_on_correct():
    s = "정관(正官)과 정인(正印), 일간(日干) 기준 용신(用神)은 庚."
    assert fix_term_hanja(s) == s
    assert fix_term_hanja(fix_term_hanja(s)) == s


def test_all_ten_gods_have_correct_mapping():
    # 십성 10개가 TERM_HANJA 에 정자로 모두 존재(겁재=劫財, 정인=正印 …)
    for han, koname in TEN_GODS_KO.items():
        assert TERM_HANJA[koname] == han


def test_empty_and_none_safe():
    assert fix_term_hanja("") == ""
    assert fix_term_hanja("한자 없는 일반 문장") == "한자 없는 일반 문장"


# ── 간지(干支) 병기 교정 — 유효성 우선 규칙 (전문가 지적 2026-07-03/04) ──
# 케이스 #1: 癸巳→'귀사' 독음 환각(한글 무효 → 한자 신뢰, 독음 교정)
# 케이스 #2: '무술'→戊辰 한자 환각(한글 유효 → 한글 신뢰, 한자 교정)

def test_corrects_wrong_ganji_reading():
    assert fix_term_hanja("귀사(癸巳) 년주와 갑자(甲子) 월주") == "계사(癸巳) 년주와 갑자(甲子) 월주"
    assert fix_term_hanja("귀수(癸水)의 영향") == "계수(癸水)의 영향"      # 천간+오행
    assert fix_term_hanja("갑슬(甲戌) 일주") == "갑술(甲戌) 일주"
    assert fix_term_hanja("신자친(申子辰) 삼합") == "신자진(申子辰) 삼합"   # 3글자 조합


def test_corrects_wrong_ganji_hanja_when_reading_valid():
    # 케이스 #2 실측: 10월 월운은 戊戌인데 한자를 戊辰으로 환각 — 한글('무술')이 유효하므로 한자 교정
    assert fix_term_hanja("10월 무술(戊辰): 사업적인 면") == "10월 무술(戊戌): 사업적인 면"
    assert fix_term_hanja("계수(癸火) 일간") == "계수(癸水) 일간"          # 천간+오행 한자 환각
    assert fix_term_hanja("인오술(寅午巳) 삼합") == "인오술(寅午戌) 삼합"   # 삼합 한자 환각


def test_ambiguous_singeum_untouched():
    # '신금'은 辛金/申金 중의적 — 한글신뢰 교정 제외(정상 표기 둘 다 보존)
    assert fix_term_hanja("신금(辛金) 일간") == "신금(辛金) 일간"
    assert fix_term_hanja("신금(申金) 지지") == "신금(申金) 지지"


def test_ganji_reading_idempotent_on_correct():
    s = "계사(癸巳) 년주, 갑술(甲戌) 일주, 경오(庚午) 시주, 계수(癸水)"
    assert fix_term_hanja(s) == s


def test_ganji_reading_no_false_positive():
    # ① 간지 외 한자 혼합 괄호 불개입
    assert fix_term_hanja("무계합화(戊癸合火)") == "무계합화(戊癸合火)"
    # ② 1글자 간지 불개입 (띠·시각 표기 보존)
    assert fix_term_hanja("말띠(午)와 자(子)시") == "말띠(午)와 자(子)시"
    # ③ 정독과 한 음절도 안 겹치는 딴 단어 불개입
    assert fix_term_hanja("물뱀(癸巳)의 해") == "물뱀(癸巳)의 해"
    # ③ 둘 다 유효하나 한 음절도 안 겹침 — 판단 불가라 불개입
    assert fix_term_hanja("갑자(庚午) 시주") == "갑자(庚午) 시주"


def test_term_correction_preserves_real_ganji_paren():
    # 용어 뒤 괄호가 '실제 간지'면 용어 한자로 덮어쓰지 않음(간지 정보 소실 방지)
    assert fix_term_hanja("년주(癸巳)와 월주(甲子)") == "년주(癸巳)와 월주(甲子)"
    assert fix_term_hanja("용신(庚金)이 핵심") == "용신(庚金)이 핵심"
    assert fix_term_hanja("용신(庚)과 희신(丁)") == "용신(庚)과 희신(丁)"
    assert fix_term_hanja("용신(庚·丁)") == "용신(庚·丁)"                  # 천간 나열
    # 반면 간지가 아닌 환각 한자는 기존대로 정자 교정
    assert fix_term_hanja("년주(年主)") == "년주(年柱)"
    assert fix_term_hanja("정인(丁寅)") == "정인(正印)"                    # 음차 환각(丁寅은 무효 조합)


def test_insu_hanja_correction():
    # 실측 케이스: 인수(印綬)의 綬를 綠/緣으로 환각 — 십성 10엔 총칭 '인수'가 없어 통과되던 갭
    assert fix_term_hanja("시험 당일 운은 인수(印綠)로 판단됩니다") == "시험 당일 운은 인수(印綬)로 판단됩니다"
    assert fix_term_hanja("인수(印緣)") == "인수(印綬)"
    assert fix_term_hanja("인수(印綬)와 재성(財星)") == "인수(印綬)와 재성(財星)"   # 정답 유지


def test_branch_unit_hanja_correction():
    # 실측(택일): '축월(子月)' — 지지 한글 축은 맞고 한자 子가 틀림(丑月 정답)
    assert fix_term_hanja("축월(子月)과 축일(丑日)") == "축월(丑月)과 축일(丑日)"
    assert fix_term_hanja("축시(子時) 태생") == "축시(丑時) 태생"
    assert fix_term_hanja("자월(丑月)에는") == "자월(子月)에는"        # 한글 자 기준 교정
    # 정답 병기는 보존
    for ok in ["인시(寅時)", "묘일(卯日)", "오월(午月)", "미년(未年)", "축일(丑日)"]:
        assert fix_term_hanja(ok) == ok
    # 오탐 방지: 바레 지지(단위가 괄호 뒤)·60갑자 병기 불개입
    assert fix_term_hanja("자(子)시에 태어나") == "자(子)시에 태어나"
    assert fix_term_hanja("계축(癸丑) 일주") == "계축(癸丑) 일주"


def test_sinsal_unseong_term_hanja():
    # 선제 보강 세트: 신살·운성·용신법 한자 환각 교정
    assert fix_term_hanja("도화(桃火)가 강해") == "도화(桃花)가 강해"        # 火→花
    assert fix_term_hanja("역마(易馬)") == "역마(驛馬)"                       # 易→驛
    assert fix_term_hanja("제왕(帝王)의 기운") == "제왕(帝旺)의 기운"          # 十二運星 帝旺(帝王 아님)
    assert fix_term_hanja("원진(元嗔)") == "원진(怨嗔)"                       # 정본 怨嗔
    assert fix_term_hanja("조후(調喉)") == "조후(調候)"                       # 喉→候
    # 정답은 그대로 유지
    assert fix_term_hanja("양인(羊刃)과 괴강(魁罡)") == "양인(羊刃)과 괴강(魁罡)"


def test_excluded_terms_not_overcorrected():
    # 제외 원칙 검증: 단일글자·상용어 동음은 건드리지 않음(오탐 방지)
    assert fix_term_hanja("병(丙) 일간") == "병(丙) 일간"              # 병=丙(천간), 病 아님
    assert fix_term_hanja("사(巳)월생") == "사(巳)월생"                # 사=巳(지지), 死 아님
    assert fix_term_hanja("관대(寬大)한 성품") == "관대(寬大)한 성품"    # 寬大(너그러움) 보존


def test_gungwi_term_hanja():
    # 궁위 용어 한자 교정 (실측 케이스 #3: '월간(月支)' 오기)
    assert fix_term_hanja("월간(月支)의 갑자(甲子)") == "월간(月干)의 갑자(甲子)"
    assert fix_term_hanja("년지(年支)의 계사(癸巳)") == "년지(年支)의 계사(癸巳)"  # 정상 유지
    assert fix_term_hanja("월지(月支)와 일지(日支)") == "월지(月支)와 일지(日支)"  # 정상 유지


def test_ganji_reading_preserves_attached_prefix():
    # 띄어쓰기 없이 붙은 앞말은 보존하고 독음만 교정
    assert fix_term_hanja("바로귀사(癸巳)입니다") == "바로계사(癸巳)입니다"
