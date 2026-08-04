"""사주 명리학 상수 (천간/지지/오행/십성/지장간)."""
from __future__ import annotations

import re

# ============================================================
# 천간 (天干) — 10개
# ============================================================
HEAVENLY_STEMS: tuple[str, ...] = (
    "甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸",
)
STEM_KOREAN: tuple[str, ...] = (
    "갑", "을", "병", "정", "무", "기", "경", "신", "임", "계",
)

# 천간 → 오행
STEM_TO_WUXING: dict[str, str] = {
    "甲": "木", "乙": "木",
    "丙": "火", "丁": "火",
    "戊": "土", "己": "土",
    "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

# 천간 → 음양 (양=True, 음=False)
STEM_IS_YANG: dict[str, bool] = {
    "甲": True, "乙": False,
    "丙": True, "丁": False,
    "戊": True, "己": False,
    "庚": True, "辛": False,
    "壬": True, "癸": False,
}

# ============================================================
# 지지 (地支) — 12개
# ============================================================
EARTHLY_BRANCHES: tuple[str, ...] = (
    "子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥",
)
BRANCH_KOREAN: tuple[str, ...] = (
    "자", "축", "인", "묘", "진", "사", "오", "미", "신", "유", "술", "해",
)
BRANCH_ZODIAC: tuple[str, ...] = (
    "쥐", "소", "호랑이", "토끼", "용", "뱀", "말", "양", "원숭이", "닭", "개", "돼지",
)

# 지지 → 오행
BRANCH_TO_WUXING: dict[str, str] = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木",
    "辰": "土", "巳": "火", "午": "火", "未": "土",
    "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

# 지지 → 음양
BRANCH_IS_YANG: dict[str, bool] = {
    "子": True, "丑": False, "寅": True, "卯": False,
    "辰": True, "巳": False, "午": True, "未": False,
    "申": True, "酉": False, "戌": True, "亥": False,
}

# ============================================================
# 지장간 (地藏干) — 지지 안의 천간
# (餘氣, 中氣, 正氣) 순. 일부 지지는 중기 없음.
# ============================================================
HIDDEN_STEMS: dict[str, tuple[str, ...]] = {
    "子": ("壬", "癸"),
    "丑": ("癸", "辛", "己"),
    "寅": ("戊", "丙", "甲"),
    "卯": ("甲", "乙"),
    "辰": ("乙", "癸", "戊"),
    "巳": ("戊", "庚", "丙"),
    "午": ("丙", "己", "丁"),
    "未": ("丁", "乙", "己"),
    "申": ("戊", "壬", "庚"),
    "酉": ("庚", "辛"),
    "戌": ("辛", "丁", "戊"),
    "亥": ("戊", "甲", "壬"),
}

# ============================================================
# 오행 상생/상극
# ============================================================
WUXING_LIST: tuple[str, ...] = ("木", "火", "土", "金", "水")
WUXING_KOREAN: dict[str, str] = {
    "木": "목", "火": "화", "土": "토", "金": "금", "水": "수",
}

# 상생 (生): 어떤 오행이 어떤 오행을 생하는가
WUXING_GENERATES: dict[str, str] = {
    "木": "火", "火": "土", "土": "金", "金": "水", "水": "木",
}
# 상극 (剋): 어떤 오행이 어떤 오행을 극하는가
WUXING_OVERCOMES: dict[str, str] = {
    "木": "土", "土": "水", "水": "火", "火": "金", "金": "木",
}


# ============================================================
# 십성 (十星) — 일간(日干) 기준 다른 천간의 관계
# 같은 오행: 비견(같은 음양)/겁재(다른 음양)
# 내가 생하는 오행: 식신(같은 음양)/상관(다른 음양)
# 내가 극하는 오행: 편재(같은 음양)/정재(다른 음양)
# 나를 극하는 오행: 편관(같은 음양)/정관(다른 음양)
# 나를 생하는 오행: 편인(같은 음양)/정인(다른 음양)
# ============================================================
TEN_GODS_KO: dict[str, str] = {
    "比肩": "비견", "劫財": "겁재",
    "食神": "식신", "傷官": "상관",
    "偏財": "편재", "正財": "정재",
    "偏官": "편관", "正官": "정관",  # 偏官=七殺
    "偏印": "편인", "正印": "정인",
}

# 십성(十星) → 육친(六親)·인생영역. 성격·가족/인연 해석의 근거.
# 성별에 따라 재성=배우자(남)·관성=배우자(여)/자식 의미가 갈린다.
TEN_GODS_YUKCHIN: dict[str, str] = {
    "比肩": "형제·동료·경쟁자(자존·독립심)",
    "劫財": "형제·친구·동업(경쟁·재물분산 주의)",
    "食神": "표현·의식주·여유·낙천 / 여성에겐 자식",
    "傷官": "재능·표현·비판력 / 여성에겐 자식",
    "偏財": "유동재물·사업수완·부친 / 남성에겐 애인·이성",
    "正財": "고정재물·성실·알뜰 / 남성에겐 배우자(처)",
    "偏官": "도전·추진·명예(압박) / 여성에겐 배우자, 남성에겐 자식",
    "正官": "직장·명예·규범·책임 / 여성에겐 배우자, 남성에겐 자식",
    "偏印": "학문·문서·후원(편업·재치) / 모친",
    "正印": "학문·문서·후원(정통·인덕) / 모친",
}

# 성별로 갈리는 육친(자식·배우자 등)을 '확정'하기 위한 구조: (공통 의미, 남성 관계, 여성 관계).
# 남성=자식은 관성(정관/편관), 여성=자식은 식상(식신/상관); 남성=처는 재성, 여성=남편은 정관 등.
# 관계 문자열이 비면 성별 무관(비견/겁재/인성). LLM 이 성별을 잘못 적용하던 버그(식신=자식을 남성에게)
# 를 막기 위해 프롬프트에 '해당 성별의 관계'만 주입한다.
TEN_GODS_YUKCHIN_G: dict[str, tuple[str, str, str]] = {
    "比肩": ("형제·동료·경쟁자(자존·독립심)", "", ""),
    "劫財": ("형제·친구·동업(경쟁·재물분산 주의)", "", ""),
    "食神": ("표현·의식주·여유·낙천", "장모·손자(자식 아님)", "자식"),
    "傷官": ("재능·표현·비판력", "조모·손녀(자식 아님)", "자식"),
    "偏財": ("유동재물·사업수완·부친", "애인·이성", "부친·시가"),
    "正財": ("고정재물·성실·알뜰", "배우자(처)", "부친·시가"),
    "偏官": ("도전·추진·명예(압박)", "자식", "애인·정부"),
    "正官": ("직장·명예·규범·책임", "자식", "배우자(남편)"),
    "偏印": ("학문·문서·후원(편업·재치)·모친(계모)", "", ""),
    "正印": ("학문·문서·후원(정통·인덕)·모친", "", ""),
}


def yukchin_meaning(hanja: str, is_male: bool | None) -> str:
    """십성(한자) → 성별을 반영한 육친 의미(확정). is_male=None(성별미상)이면 공통 의미만.

    남성: 자식=관성(정관·편관), 처=재성 / 여성: 자식=식상(식신·상관), 남편=정관.
    이 확정 문자열을 프롬프트에 넣어, LLM 이 '식신=자식'(여성용)을 남성에게 붙이던 오적용을 차단한다."""
    t = TEN_GODS_YUKCHIN_G.get(hanja)
    if not t:
        return TEN_GODS_YUKCHIN.get(hanja, "")
    common, male_rel, fem_rel = t
    if is_male is None:
        return common
    rel = male_rel if is_male else fem_rel
    return f"{common} · {rel}" if rel else common


# ── LLM 출력 한자(漢字) 교정 ────────────────────────────────────────
# 시스템 프롬프트가 '한글(한자)' 병기를 지시하지만 모델에 전체 한자를 주지 않아, 모델이 한자를
# 환각(예: 劫財→劫才, 正印→正寅, 正→政)하는 일이 있다(전문가 지적). 정자(正字)는 아래가 정답이며,
# 출력의 '용어(한자…)' 괄호가 '한자'로만 채워졌을 때 그 한자를 정자로 결정적 교정한다.
# (괄호 안에 한글 설명이 섞이면 건드리지 않아 설명 손실을 막는다.)
TERM_HANJA: dict[str, str] = {
    **{ko: han for han, ko in TEN_GODS_KO.items()},  # 십성 10: 겁재→劫財, 정인→正印 …
    "일간": "日干", "일주": "日柱", "월주": "月柱", "년주": "年柱", "시주": "時柱",
    # 궁위(宮位) 용어 — 실측: '월간(月支)' 오기(케이스 #3). '시간'은 일반어 時間과 충돌해 제외,
    # '연간'도 일반어(年間)와 충돌해 제외(년간만 수록).
    "월간": "月干", "년간": "年干",
    "년지": "年支", "연지": "年支", "월지": "月支", "일지": "日支", "시지": "時支",
    "대운": "大運", "세운": "歲運", "월운": "月運", "년운": "年運",
    "용신": "用神", "희신": "喜神", "기신": "忌神",
    "오행": "五行", "천간": "天干", "지지": "地支", "지장간": "地藏干",
    "신강": "身強", "신약": "身弱",
    "비겁": "比劫", "인성": "印星", "식상": "食傷", "재성": "財星", "관성": "官星",
    # 육친 총칭·별칭 — 실측: '인수(印綠/印緣)' 환각(십성 10엔 정인/편인만 있고 총칭 인수가 누락돼
    # 통과됨). 印綬(인수)=인성의 별칭. '비견/겁재'는 십성에서, '인수'만 여기 보강.
    "인수": "印綬", "구설": "口舌", "자형": "自刑", "오방색": "五方色",
    # 명리 용어 한자 선제 보강(전수 점검 2026-07) — 답변에 '용어(한자)' 병기 시 환각 차단.
    # 정본 한자는 엔진 상수 기준(원진=怨嗔·귀문=鬼門·도화=桃花). ⚠️제외 원칙:
    #   ① 단일 글자 운성(쇠·병·사·묘·절·태·양)=천간/지지/음양과 충돌(병丙·사巳·묘卯…) → 제외
    #   ② 상용어 동음(관대=寬大·중기=中期·정기=精氣·여기=here) → 제외
    #   ③ 정/속자 변이(천살 天煞/天殺, 겁살 등)=정답 변이도 오교정 → 제외
    "삼합": "三合", "육합": "六合", "방합": "方合", "반합": "半合",
    # 충 정자=沖(엔진·전문가 표기). 실측(2026-07-21 오늘운세): LLM이 '충(衝)'로 오병기.
    # 단일 글자지만 '충(한자)' 병기 패턴만 교정하므로 일반어(충분·충성)와 충돌 없음.
    "충": "沖",
    "원진": "怨嗔", "귀문": "鬼門", "도화": "桃花", "역마": "驛馬", "화개": "華蓋",
    "장성": "將星", "반안": "攀鞍", "공망": "空亡", "양인": "羊刃", "괴강": "魁罡", "백호": "白虎",
    "장생": "長生", "목욕": "沐浴", "제왕": "帝旺", "건록": "建祿",
    "조후": "調候", "억부": "抑扶", "통관": "通關", "득령": "得令", "실령": "失令", "통근": "通根",
}

# '용어(한자[·한자 …])' — 괄호 안이 한자(+가운뎃점/공백)로만 이뤄질 때만 매칭(한글 설명 괄호는 보존).
_TERM_PAREN_RE: dict[str, "re.Pattern[str]"] = {
    ko: re.compile(rf"{re.escape(ko)}\s*\(\s*([一-鿿][一-鿿·\s]*)\)")
    for ko in TERM_HANJA
}

# '용어(용어)' — 약한 LLM이 한자 병기 대신 같은 한글을 반복하는 오표기(실측 2026-07-21:
# '정재(정재), 정인(정인)' 신년운세 노출). 같은 한글 반복일 때만 정자 병기로 교정(설명 괄호 보존).
_TERM_SELF_PAREN_RE: dict[str, "re.Pattern[str]"] = {
    ko: re.compile(rf"{re.escape(ko)}\s*\(\s*{re.escape(ko)}\s*\)")
    for ko in TERM_HANJA
}

# 한 글자 관계어의 자기반복 병기(실측 2026-07-22 신년운세: '형(형)' 4·'파(파)' 3·'합(합)' 3·'해(해)' 1).
# TERM_HANJA 에 넣으면 _TERM_PAREN_RE 가 '올해(丙午)'·'삼형(三刑)' 같은 정상 괄호까지 훑어 위험하므로,
# **같은 한글 반복일 때만** 정자로 바꾸는 이 맵으로 분리한다(다른 병기·설명 괄호는 절대 건드리지 않음).
_REL_TERM_HANJA: dict[str, str] = {"형": "刑", "파": "破", "해": "害", "합": "合", "극": "剋", "생": "生",
                                   # 부적 오방색 — '적(적)' 자기반복 병기 실측(2026-07-22)
                                   "적": "赤", "청": "靑", "황": "黃", "백": "白", "흑": "黑"}
_REL_SELF_PAREN_RE: dict[str, "re.Pattern[str]"] = {
    ko: re.compile(rf"(?<![가-힣]){re.escape(ko)}\s*\(\s*{re.escape(ko)}\s*\)")
    for ko in _REL_TERM_HANJA
}

# 관계어 괄호 안이 '같은 한글'이 아니라 **다른 낱말·다른 한자**로 깨진 경우(실측 2026-07-22 신년운세
# '파(상충)' 6건 — 破를 '상충'으로 옮겨 뜻까지 뒤집었다 / 궁합 '형(形)' — 刑 대신 모양 形).
# 아무 한글이나 바꾸면 '해(올해)' 같은 정상 표현을 깨뜨리므로 **알려진 오기 목록만** 교정한다.
_REL_WRONG_INNER: dict[str, set[str]] = {
    "형": {"형", "刑살", "상형", "형벌", "형제", "형살", "形", "型"},
    "파": {"파", "상파", "상충", "충", "깨짐", "波", "派"},
    "해": {"해", "상해", "해로움", "해침"},
    "합": {"합", "상합", "화합"},
    "충": {"충", "상충", "충돌", "衝"},
}
_REL_WRONG_PAREN_RE: dict[str, "re.Pattern[str]"] = {
    ko: re.compile(
        rf"(?<![가-힣]){re.escape(ko)}\s*\(\s*("
        + "|".join(re.escape(x) for x in sorted(v, key=len, reverse=True))
        + r")\s*\)")
    for ko, v in _REL_WRONG_INNER.items()
}

# 한자(한자) 병기 — '庚(庚)'·'乙(乙)' 처럼 한글 독음 대신 한자를 두 번 쓴 형태(실측 2026-07-22
# 신년운세 2회차 6건). 시스템 규칙은 '항상 한글(한자)'이므로 앞을 정독으로 바꾼다.
_HANJA_SELF_PAREN_RE = re.compile(r"(?<![一-鿿])([一-鿿])\s*\(\s*\1\s*\)")

# 간지월 병기의 '월'만 한글로 남은 형태(실측 2026-07-22 상담: '정미월(丁未월)'·'경술월(庚戌월)').
# 괄호 앞뒤가 같은 간지를 가리키므로 뒤쪽 '월'을 정자 月 로 맞춘다(년·일도 동일).
_GANJI_UNIT_PAREN_RE = re.compile(r"([가-힣]{2}(?:월|년|일))\s*\(\s*([一-鿿]{2})\s*(월|년|일)\s*\)")
_UNIT_HANJA = {"월": "月", "년": "年", "일": "日"}

# 용어 병기가 '한자+한글 혼합'으로 깨진 오표기(실측 2026-07-21 오늘운세: '원진(原진)') —
# 괄호 안 길이가 용어와 같고 한자·한글이 섞였으면 깨진 병기로 보고 정자로 교정(한글 설명 괄호는
# 순한글이라 미매칭, 순한자는 _TERM_PAREN_RE 관할).
_TERM_MIXED_PAREN_RE: dict[str, "re.Pattern[str]"] = {
    ko: re.compile(rf"{re.escape(ko)}\s*\(\s*((?=[가-힣一-鿿]*[一-鿿])(?=[가-힣一-鿿]*[가-힣])[가-힣一-鿿]{{{len(ko)}}})\s*\)")
    for ko in TERM_HANJA
}

# 십성 '한자 단독' 표기(실측 2026-07-21: "'劫財'나 '傷官'와의 충돌") → '겁재(劫財)' 한글(한자)로.
# 십성 10종만 대상(2자 고정·동음 충돌 없음 — 일반 용어로 확대하면 오탐 위험). 이미 '겁재(劫財)'
# 병기의 괄호 안이거나 다른 한자와 붙은 경우는 제외.
_TEN_GOD_KO_BY_HANJA = {"比肩": "비견", "劫財": "겁재", "食神": "식신", "傷官": "상관",
                        "偏財": "편재", "正財": "정재", "偏官": "편관", "正官": "정관",
                        "偏印": "편인", "正印": "정인"}
_BARE_TEN_GOD_RE = re.compile(
    r"(?<![一-鿿(（])(" + "|".join(_TEN_GOD_KO_BY_HANJA) + r")(?![一-鿿)）])"
)


# 마크다운 구분선(---·***·___) 단독 줄 — 프론트 렌더러(renderRich)가 소제목/굵게/불릿만 지원해
# 원문 '---'가 그대로 노출됐다(실측 2026-07-21 신년운세). 내용이 아닌 줄이라 무조건 제거해도 안전.
_MD_HR_LINE_RE = re.compile(r"^[ \t]*[-*_][-*_ \t]{2,}[ \t]*$", re.M)


def _strip_md_rules(text: str) -> str:
    """단독 구분선 줄 제거 + 헤딩 '#' 뒤 공백 보장 + 남는 3연속 빈 줄 축약(결정적·멱등)."""
    out = _MD_HR_LINE_RE.sub("", text)
    # [P5-c 2026-07-29] '####9월' → '#### 9월' — 공통 체인(fix_term_hanja)에 넣어 tool/compat/tarot 도
    #   저장본 헤딩 공백을 보장(종전엔 chat _tidy_markdown 전용이라 다른 메뉴 저장본이 '####9월'로 남았다).
    #   프론트 렌더는 이미 공백무관이나, 저장본·PDF·복사 일관성을 위해 백엔드도 통일. 레벨(#개수) 보존.
    out = re.sub(r"(?m)^([ \t]*#{1,6})(?=[^\s#])", r"\1 ", out)
    return re.sub(r"\n{3,}", "\n\n", out)


# '### 내일 운세 풀이 시작'처럼 '이제 풀이를 시작' 예고를 소제목으로 단 것(실측 2026-07-28 신년운세).
# 내용 없는 안내인데 시간어(오늘·내일)까지 환각해 붙어 연운 답변에 '내일'이 튀어나왔다. 프롬프트엔
# 이 문구가 없다 — 전 메뉴에서 무해한 예고 줄이므로 통째 제거한다.
# 오탐 가드: '운세 풀이' 뒤가 '시작/들어가'일 때만(‘운세를 풀이하면…’·‘운세 풀이하면…’ 정상 서술 보존).
_READING_START_LINE_RE = re.compile(
    r"(?m)^[ \t]*#{0,6}[ \t]*(?:오늘|내일|모레|올해|금일|명일|금년)?\s*(?:의|은|는)?\s*"
    r"운세\s*풀이(?:를)?\s*(?:시작|들어가)[^\n]*\n?"
)


def _strip_reading_start_filler(text: str) -> str:
    """'(오늘/내일) 운세 풀이 시작' 예고 줄 제거 — 연운·사주에 '내일' 오출력 차단(결정적·멱등)."""
    return _READING_START_LINE_RE.sub("", text) if text else text


# 내부 근거표를 그대로 베낀 불릿 줄(실측 2026-07-22: 월별마다 '- 월간 십성: …', '- 관계: …'를
# 머리에 달아 어려움). 프롬프트로 12회 금지해도 약한 모델이 반복 → 출력단에서 결정적으로 제거.
# 서술 본문('- 흐름:', '- 활용 조언:')은 보존 — 표 라벨 3종만 정확히 지목.
_COPIED_TABLE_LINE_RE = re.compile(
    r"^[ \t]*[-•·*][ \t]*\*{0,2}[ \t]*(?:월간[ \t]*십성|월지[ \t]*십성|관계)[ \t]*\*{0,2}[ \t]*[:：].*$",
    re.M,
)
# [P5-b 2026-07-29] '- **십성**: 정관(正官)/겁재(劫財)'처럼 값이 '십성명(±한자)·구분자'뿐인 근거표
# 라벨덤프 행(실측 chat #1045·#1006). 값에 십성명 외 다른 한글(서술)이 있으면 미매칭 → '십성: 재물을
# 뜻하는 정재'·'- **관계:** 새로운 인연이…' 같은 정상 문장은 보존(오삭제 방지가 P5-b의 핵심).
_TEN_GOD_NAMES_RE = r"(?:비견|겁재|식신|상관|편재|정재|편관|정관|편인|정인|인수|인성)"
_TENGOD_DUMP_RE = re.compile(
    r"(?m)^[ \t]*(?:[-•·*][ \t]*)?\*{0,2}[ \t]*(?:십성|십신)[ \t]*\*{0,2}[ \t]*[:：][ \t]*"
    r"(?:" + _TEN_GOD_NAMES_RE + r"(?:\s*\([一-鿿]{1,3}\))?[ \t]*[/·,]?[ \t]*)+\s*\*{0,2}[ \t]*$"
)


# [P5-a 2026-07-29] 쉬운풀이 결정적 병기 — 십성이 '나열(2개+ 구분자 연결)'로 뜻풀이 없이 나오면
# 각 항목에 생활어 뜻을 1회 괄호 병기(예: '정관, 겁재' → '정관(직장·책임), 겁재(동업·지출)').
# ⛔산문 중 단독 십성('정관이 강해…')은 건드리지 않는다(모델이 곧 풀이 → 과잉병기 방지, 실측 캘리브레이션:
#   tool 198건 중 196건 무개입). ⛔이미 뜻(한글괄호)이 붙은 런은 통째 skip(멱등). 뜻 재료는 tool_service
#   _STAR_GLOSS 와 동일. P5-b(_strip_copied_table_lines) 로 순수 덤프행이 먼저 제거된 뒤 남은 나열에만 작동.
_STAR_GLOSS_KO = {
    "비견": "동료·경쟁", "겁재": "동업·지출", "식신": "표현·여유", "상관": "재능·비판",
    "편재": "유동 재물", "정재": "고정 재물", "편관": "도전·압박", "정관": "직장·책임",
    "편인": "문서·후원", "정인": "학문·인덕",
}
_STAR_NAMES_RE = "|".join(_STAR_GLOSS_KO)
# 항목 = 십성명 + (선택)한자병기 + (선택)이미붙은 한글뜻괄호. 뒤의 한글뜻괄호까지 '항목'으로 흡수해야
# '정관, 겁재(동업·지출)'의 나열 런이 그 괄호를 포함 → 아래 스킵가드가 걸려 이중병기('(뜻)(뜻)')를 막는다.
_STAR_ITEM_RE = rf"(?:{_STAR_NAMES_RE})(?:\([一-鿿]{{1,3}}\))?(?:\([가-힣][가-힣·\s]{{1,11}}\))?"
# 나열 구분자는 명확한 열거만(/ , 、). '·'(가운뎃점)은 복합 지칭('정관·정재'=정관과 정재)에 흔해
# 병기하면 오히려 어수선 → 제외(보수적). 순수 덤프 '정관/겁재'는 P5-b가 먼저 제거하므로 여기 안 옴.
# 좌측 경계 (?<![가-힣(（]) — ①'부정관…' 처럼 앞이 한글이면 선두항 mid-word 오병기 방지 ②'(정관, 편관)'
#   처럼 괄호 라벨 안 나열은 병기 시 괄호 중첩되므로 미개입(시각 어수선 방지). (순환검증 잠복결함 하드닝)
_STAR_LIST_RE = re.compile(rf"(?<![가-힣(（]){_STAR_ITEM_RE}(?:[ \t]*[/,、][ \t]*{_STAR_ITEM_RE})+")
_STAR_ONE_RE = re.compile(rf"({_STAR_NAMES_RE})(\([一-鿿]{{1,3}}\))?")


def enforce_easy_gloss(text: str) -> str:
    """십성 나열에 생활어 뜻을 결정적으로 1회 병기(산문 단독은 미개입). 멱등·모델 왕복 없음."""
    if not text:
        return text

    def _run(m: "re.Match[str]") -> str:
        run = m.group(0)
        if re.search(r"[(（]\s*[가-힣]", run):   # 이미 한글 뜻 병기가 있으면 통째 skip(멱등)
            return run

        def _one(mm: "re.Match[str]") -> str:
            name, hanja = mm.group(1), (mm.group(2) or "")
            g = _STAR_GLOSS_KO[name]
            if hanja:                            # '(正官)' → '(正官, 직장·책임)' (이중괄호 방지)
                return f"{name}{hanja[:-1]}, {g})"
            return f"{name}({g})"
        return _STAR_ONE_RE.sub(_one, run)
    return _STAR_LIST_RE.sub(_run, text)


# 십성 '뜻' 병기가 한자/중국어로 오염된 경우(예: 비견(동僚·競争)) 정본 한글 뜻으로 교체.
#   ⛔ 보존: 그 십성의 정자만 든 괄호 — '비견(比肩)'·'정관(正官, 직장·책임)'(enforce_easy_gloss 산출형).
#   ✅ 교정: 그 십성의 정자가 아닌 다른 한자가 섞인 괄호(동僚·競争 등) → 정본 한글 뜻으로.
_STAR_GLOSS_CORRUPT_RE = re.compile(rf"({_STAR_NAMES_RE})[(（]([^)）]*[一-鿿][^)）]*)[)）]")
# 십성 한글 → 그 십성의 정자 집합(比肩→{比,肩}, 偏官→{偏,官} …). 괄호 속 한자가 이 집합에 속하면 정상 병기.
_STAR_VALID_HANJA: dict[str, set] = {}
for _hj, _ko in _TEN_GOD_KO_BY_HANJA.items():
    _STAR_VALID_HANJA.setdefault(_ko, set()).update(_hj)


def _fix_corrupted_star_gloss(text: str) -> str:
    if not text:
        return text

    def _sub(m: "re.Match[str]") -> str:
        name, inner = m.group(1), m.group(2)
        inner_hanja = set(re.findall(r"[一-鿿]", inner))
        if inner_hanja and inner_hanja <= _STAR_VALID_HANJA.get(name, set()):
            return m.group(0)                     # 괄호 속 한자가 전부 그 십성의 정자 → 정상 병기 보존
        return f"{name}({_STAR_GLOSS_KO[name]})"   # 다른 한자 섞임(오염) → 정본 한글 뜻으로 교체

    return _STAR_GLOSS_CORRUPT_RE.sub(_sub, text)


def _strip_copied_table_lines(text: str) -> str:
    """근거표 복사 불릿 제거. 단, 그 달에 서술이 하나도 없으면(표만 있는 달) 남겨 빈칸 방지."""
    if not text or not (_COPIED_TABLE_LINE_RE.search(text) or _TENGOD_DUMP_RE.search(text)):
        return text
    out_blocks: list[str] = []
    # 달 헤딩(#### 1월 … / **1월 (기축월)**) 단위로 잘라 '서술이 남는지' 확인 후 제거
    for block in re.split(r"(?m)(?=^[ \t]*(?:#{2,6}[ \t]*)?\*{0,2}\d{1,2}월[ \t*(])", text):
        kept = _TENGOD_DUMP_RE.sub("", _COPIED_TABLE_LINE_RE.sub("", block))
        # 남은 줄 중 실질 서술(불릿/문장)이 있으면 제거 적용, 없으면 원본 유지
        body = [ln for ln in kept.split("\n")[1:] if ln.strip() and not ln.strip().startswith("#")]
        out_blocks.append(kept if body else block)
    out = "".join(out_blocks)
    return re.sub(r"\n{3,}", "\n\n", out)


# ── 거짓 '합(合)' 주장 결정적 중화 (실측 2026-07-22: "병(丙)은 을(乙)와의 합", "병화와 병화의 합") ──
# 천간합(갑기·을경·병신·정임·무계)·지지육합(자축·인해·묘술·진유·사신·오미)은 고정표라 명식 없이
# 판정 가능. 두 간지 글자가 '합'으로 묶였는데 실제 합이 아니면 '관계'로 중화(거짓 단정 제거).
_STEM_HAP = {frozenset(p) for p in ("甲己", "乙庚", "丙辛", "丁壬", "戊癸")}
_BRANCH_HAP = {frozenset(p) for p in ("子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未")}
# 'X(漢)…Y(漢)…합' — 한글(한자) 병기 사이 최대 24자, 뒤에 '합'. 삼합/반합/방합은 3자 관계라 제외.
_GANJI_CHARS = "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥"
# 'A(漢[漢])' … 'B(漢[漢])' … '합' + 조사. 앞에 삼/반/방/육이 붙은 3자·정식 합은 제외.
_HAP_CLAIM_RE = re.compile(
    r"([一-鿿]{1,2})\)([^.。\n]{0,24}?)([一-鿿]{1,2})\)([^.。\n]{0,12}?)(?<![삼반방육])합(으로|이|은|을|과|와|에|의)?"
)
# '합→관계' 치환 시 조사 교정(받침 유무가 바뀜): 합으로→관계로, 합이→관계가 …
_HAP_JOSA = {"으로": "로", "이": "가", "은": "는", "을": "를", "과": "와", "와": "와", "에": "에", "의": "의",
             # 종결형은 그대로 붙여 쓴다 — '합입니다'→'관계입니다'. '합니다'(용언)는 앞 경계로 이미 배제.
             "입니다": "입니다", "이다": "이다", "이며": "이며", "이고": "이고", "이라": "라"}
# 병기 괄호 안의 간지 — '을(乙)'·'병화(丙火)' 모두 여기서 잡힌다.
_GANJI_IN_PAREN_RE = re.compile(r"\(\s*([一-鿿]{1,2})\s*\)")
# '합' + 조사 — **낱말로 홀로 선 '합'만** 잡는다.
# 앞뒤가 한글이면 '합'은 관계어가 아니라 다른 낱말의 일부다(실측 회귀: '형성합니다'→'형성관계니다'
# 5회 노출, '결합합니다'→'결관계관계니다', '종합하면'→'종관계하면'). 이 두 경계 검사만으로
# 삼합·반합·방합·육합·천간합 같은 복합어도 자동으로 제외된다.
# 뒤 경계 검사는 '합이다'의 계사 '이'를 조사로 오인해 '관계가다'를 만들던 비문도 함께 막는다.
# '합(合)'처럼 한자 병기가 붙은 형태도 통째로 잡는다 — 안 그러면 중화 후 '관계(合)'라는
# 정체불명 표기가 남는다(운영 DB 실측 잔존 1건).
# 마크다운 강조는 **먹지 말고 그대로 되돌려 놓는다**(group 1) — 안 그러면 '**합**을'이
# '**관계를'이 되어 굵게 표시가 깨진다(감사 실측).
_HAP_WORD_RE = re.compile(
    r"(?<![가-힣])합(?:\s*\(\s*合\s*\))?(\**\s*)"
    r"(입니다|이다|이며|이고|이라|으로|이|은|을|과|와|에|의)?(?![가-힣])")
# '합' 뒤에 오는 부정 서술 — 여기 걸리면 원문이 이미 옳으므로 중화하지 않는다.
# '아닌'은 '아니'의 축약이라 따로 적어야 한다(감사 반례에서 이 한 글자 때문에 가드가 샜다).
_NEG_HAP_RE = re.compile(
    r"\s*(?:이|은|을|과|와)?\s*\**\s*(?:아니|아닌|아님|아냐|아닙|이루지\s*않|되지\s*않|하지\s*않)")
_DUP_RELATION_RE = re.compile(r"관계(?:의|와|과)\s*관계")
# 이미 저장된 답변에 남은 파괴 흔적 복구 — 중화기가 낱말 속 '합'을 '관계'로 바꿔 만든 비문.
# ('관계니다'·'종관계'·'결관계'는 한국어에 없는 형태라 오탐 없이 되돌릴 수 있다.)
# 생성·읽기 공통 체인이라 기존 리포트도 재열람하는 순간 스스로 고쳐진다.
_HAP_CORRUPT_FIX: tuple[tuple[str, str], ...] = (
    # '관계(合)'·'관계가나'처럼 중화가 남긴 흔적을 원래 '합'으로 되돌린다. 이 복구는 아래 판정보다
    # 먼저 돌아가므로, 되돌린 '합'은 개선된 알고리즘으로 **다시 판정**된다(진짜 합이면 그대로 남는다).
    ("관계(合)", "합(合)"), ("관계가나", "합이나"),
    ("관계관계니다", "합합니다"), ("관계니다", "합니다"), ("관계가다", "합이다"),
    ("관계가라", "합이라"), ("관계충", "합충"),
    # ⚠️'적관계·부관계·조관계' 류는 '우호적관계'→'우호적합'처럼 정상 표현을 파괴한다(감사 실측) — 제외.
    ("종관계", "종합"), ("결관계", "결합"),
)


# 오행 상극 방향은 고정표(목극토·토극수·수극화·화극금·금극목)라 출력단에서 결정적으로 판정된다.
# 실측(2026-07-22 궁합): 근거 줄을 두 번 주입해도 3회 중 2회 '금은 화를 극한다'로 뒤집었다
# ('화는 금을 극하지 않습니다'처럼 참인 사실을 부정하는 형태로도 나온다) — 프롬프트로는 못 잡는다.
_WX_KO_TO_HANJA = {"목": "木", "화": "火", "토": "土", "금": "金", "수": "水"}
_WX_SUBJ = {"목": "은", "화": "는", "토": "는", "금": "은", "수": "는"}
_WX_NOM = {"목": "이", "화": "가", "토": "가", "금": "이", "수": "가"}
_WX_OBJ = {"목": "을", "화": "를", "토": "를", "금": "을", "수": "를"}
_WX_OVERCOME_RE = re.compile(
    r"(?<![가-힣])([목화토금수])(?:\([木火土金水]\))?\s*(은|는|이|가)\s*"
    r"([목화토금수])(?:\([木火土金水]\))?\s*(을|를)\s*(극|剋|억제)"
    r"(?:하지\s*않(습니다|아요|어요|는다|고|으며|지만)?)?"
)
# '…극하지 않습니다' → '…극합니다' 처럼 부정을 긍정으로 되돌릴 때 붙일 어미(그냥 지우면 '극습니다' 비문).
_NEG_TO_AFFIRM = {"습니다": "합니다", "아요": "해요", "어요": "해요", "는다": "한다",
                  "고": "하고", "으며": "하며", "지만": "하지만", None: "하"}


# '干支(한글)' 순서 병기에서 독음을 지어내는 오류(실측 2026-07-22 부적: '丑(구)' — 축인데 구,
# '월지(月支)는 丑(구)'). 정독은 결정적으로 알 수 있으므로 괄호 안 한글을 정독으로 바로잡는다.
# 반대 순서('한글(干支)')는 기존 _fix_ganji_reading 관할.
# ⚠️[실측 2026-07-28] DB #1057 '‘乙亥’(음해)' — 乙(을)을 '음'으로 환각. 한자와 '(' 사이에 닫는
#    따옴표(‘’'“”"」』)가 끼면 정규식이 미스했다. 따옴표를 선택적으로 흡수(캡처해 보존)한다.
_CLOSE_Q = "’‘'\"”“」』"
_HANJA_READING_PAREN_RE = re.compile(
    r"(?<![一-鿿])([一-鿿]{1,2})([" + _CLOSE_Q + r"]?)\s*\(\s*([가-힣]{1,2})\s*\)")


def _fix_hanja_reading_paren(text: str) -> str:
    if not text:
        return text

    def _sub(m: "re.Match[str]") -> str:
        hanja, quote, ko = m.group(1), m.group(2), m.group(3)
        if any(c not in _GANJI_READING for c in hanja):
            return m.group(0)                       # 간지·오행이 아니면 불개입(이름 한자 등)
        right = "".join(_GANJI_READING[c] for c in hanja)
        return m.group(0) if right == ko else f"{hanja}{quote}({right})"
    return _HANJA_READING_PAREN_RE.sub(_sub, text)


# 순수 한자 간지+단위('庚子月'·'乙亥년') → 한글('경자월'·'을해년'). 위 병기 교정기들은 괄호/한글이
# 있어야 걸리는데, 12월을 '庚子月'처럼 통째로 한자로 쓰면(실측 2026-07-28 신년운세 헤딩) 안 걸린다.
# 干支 2자 + 월/년/일/시 단위는 사실상 항상 간지라 오탐이 거의 없다(명식표는 '한글(乙亥)' 꼴이라 뒤에
# 단위가 안 붙어 미매칭 — 안전). 앞뒤가 다른 한자면 4자 숙어 오손 방지로 불개입.
_BARE_GANJI_UNIT_RE = re.compile(
    r"(?<![一-鿿])([甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥])([月年日時]|[월년일시])(?![一-鿿])")
_HJ_UNIT_TO_KO = {"月": "월", "年": "년", "日": "일", "時": "시"}


def _fix_bare_ganji_unit(text: str) -> str:
    if not text:
        return text

    def _sub(m: "re.Match[str]") -> str:
        gz, unit = m.group(1), m.group(2)
        ko = _GANJI_READING[gz[0]] + _GANJI_READING[gz[1]] + _HJ_UNIT_TO_KO.get(unit, unit)
        # 병기 '한글간지(한자간지…)' 안이면 불개입 — 직전이 '(' 이고 그 앞이 같은 한글 간지면
        # 명식표·'정미월(丁未月)' 같은 정상 병기다(괄호를 '한글(한글)'로 뭉개면 안 된다).
        s = m.start()
        if s >= 1 and text[s - 1] in "(（":
            head = text[:s - 1]
            if head.endswith(ko) or head.endswith(ko[:-1]):
                return m.group(0)
        return ko
    return _BARE_GANJI_UNIT_RE.sub(_sub, text)


# 오행 상생도 방향이 있다(목→화→토→금→수→목). 실측(궁합): '금(金)은 토(土)를 생하며' — 정답은 토생금.
_WX_GENERATE_RE = re.compile(
    r"(?<![가-힣])([목화토금수])(?:\([木火土金水]\))?\s*(은|는|이|가)\s*"
    r"([목화토금수])(?:\([木火土金水]\))?\s*(을|를)\s*(생)"
)


def _fix_wuxing_generate_direction(text: str) -> str:
    if not text or "생" not in text:
        return text

    def _sub(m: "re.Match[str]") -> str:
        a, b = m.group(1), m.group(3)
        ha, hb = _WX_KO_TO_HANJA[a], _WX_KO_TO_HANJA[b]
        if WUXING_GENERATES.get(ha) == hb:
            return m.group(0)
        if WUXING_GENERATES.get(hb) != ha:
            return m.group(0)                       # 상생 짝이 아니면 불개입
        subj = _WX_SUBJ[b] if m.group(2) in ("은", "는") else _WX_NOM[b]
        return f"{b}({hb}){subj} {a}({ha}){_WX_OBJ[a]} {m.group(5)}"
    return _WX_GENERATE_RE.sub(_sub, text)


# 내부 자료 제목이 본문에 그대로 새는 것(실측: '[내 사주]에 따르면…' 6런 중 5런, 리터럴 제거 후에도
# 3런 중 2런). 프롬프트로는 못 막으니 출력단에서 지운다.
_INTERNAL_LABEL_RE = re.compile(r"\[\s*(내\s*사주|분석|꿈해몽|상담맥락|사주명식)\s*\]\s*(?:에|의)?\s*(?:따르면|의하면)?\s*,?\s*")


def _strip_internal_labels(text: str) -> str:
    return _INTERNAL_LABEL_RE.sub("", text) if text and "[" in text else text


def _fix_wuxing_overcome_direction(text: str) -> str:
    """'A는 B를 극한다'가 상극표와 어긋나면 바로잡는다(조사는 받침에 맞춰 교정).

    ① 방향이 반대면 두 오행을 맞바꾼다.
    ② 방향은 맞는데 부정형이면('화는 금을 극하지 않습니다') 참인 사실을 부정한 것이라 긍정으로.
       — 실측 문장은 두 오류가 한 문장에 같이 나와, ①만 고치면 자기모순이 남는다.
    """
    if not text or ("극" not in text and "억제" not in text):
        return text

    def _sub(m: "re.Match[str]") -> str:
        a, b, verb = m.group(1), m.group(3), m.group(5)
        negated = "않" in m.group(0)
        ha, hb = _WX_KO_TO_HANJA[a], _WX_KO_TO_HANJA[b]
        if WUXING_OVERCOMES.get(ha) == hb:
            if not negated:
                return m.group(0)                   # 방향도 맞고 부정도 없다 — 그대로
            return f"{a}{m.group(2)} {b}{m.group(4)} {verb}{_NEG_TO_AFFIRM[m.group(6)]}"
        if WUXING_OVERCOMES.get(hb) != ha:
            return m.group(0)                       # 아예 상극 관계가 아니면 불개입(생·비화 등)
        if negated:
            return m.group(0)                       # 틀린 방향의 부정은 결과적으로 참 — 불개입
        subj = _WX_SUBJ[b] if m.group(2) in ("은", "는") else _WX_NOM[b]
        return f"{b}({hb}){subj} {a}({ha}){_WX_OBJ[a]} {verb}"
    return _WX_OVERCOME_RE.sub(_sub, text)


def _fix_false_hap(text: str) -> str:
    """두 간지의 '합' 주장이 실제 합표(천간합·지지육합)에 없으면 '관계'로 중화(결정적·멱등).

    실측(2026-07-22): "병(丙)은 을(乙)와의 합"(乙丙은 합 아님), "병화(丙火)와 병화(丙火)의 합"
    (같은 글자는 비견). 근거를 주입해도 LLM이 '합'을 지어내 결정적 교정이 필요.

    판정 기준은 '그 합 앞에 가장 가까운 간지 병기 두 개'다. 종전에는 24자 창 안에서 정규식이
    왼쪽 피연산자를 엉뚱한 병기로 물어(전수감사 실측) 庚·乙 천간합, 辰·酉 육합 같은 **진짜 합까지
    '관계'로 지워 근거가 소실**되고 '관계의 관계' 비문이 남았다. 반대로 창을 좁히면 사이에 '목(木)'
    같은 병기가 끼는 거짓 합을 놓친다 — 두 문제를 함께 없애려면 창이 아니라 '직전 두 간지'로 본다.
    """
    if not text:
        return text
    if "관계" in text:                     # 과거 파괴 흔적 복구(저장본 재열람 시 자가 치유)
        for bad, good in _HAP_CORRUPT_FIX:
            if bad in text:
                text = text.replace(bad, good)
    if "합" not in text:
        return text
    out: list[str] = []
    for chunk in re.split(r"([.。\n])", text):      # 문장 경계 유지하며 분할
        if not chunk or chunk in ".。\n" or "합" not in chunk:
            out.append(chunk)
            continue
        # 괄호 안 간지를 **전부** 후보로 넣는다. 종전엔 첫 글자만 뽑아 '갑술(甲戌)년의 술토는
        # 묘(卯)와 합'에서 甲만 보고 진짜 육합(卯戌)을 지웠다(운영 DB 답변 33%가 2자 병기).
        ganji: list[tuple[int, str]] = [
            (m.end(), c)
            for m in _GANJI_IN_PAREN_RE.finditer(chunk)
            for c in m.group(1) if c in _GANJI_CHARS
        ]

        def _sub(m: "re.Match[str]", _g: list = ganji, _c: str = chunk) -> str:
            mark, josa = m.group(1) or "", m.group(2) or ""
            if any(k in _c[max(0, m.start() - 2):m.start()] for k in ("삼", "반", "방", "육")):
                return m.group(0)
            # 부정 서술('합이 아니라 충입니다'·'합을 이루지 않습니다')은 원문이 이미 옳다 —
            # 중화하면 '관계가 아니라'가 되어 자기모순이 된다(충도 관계다). 불개입.
            if _NEG_HAP_RE.match(_c[m.end():m.end() + 14]):
                return m.group(0)
            # '앞의 간지 여러 개 중 **어느 한 쌍이라도** 진짜 합이면 보존'.
            # 직전 두 글자만 보면 '유(酉)는 … 축(丑)과 반합, 진(辰)과 합' 같은 나열 문장에서
            # 짝을 {丑,辰}으로 오인해 진짜 육합(酉辰)을 지운다(실측). 근거를 지우는 해악이
            # 거짓 합을 한둘 놓치는 것보다 크므로 보수적으로 판정한다.
            prev = [c for pos, c in _g if pos <= m.start()][-6:]
            if len(prev) < 2:
                return m.group(0)                  # 판단 근거 부족 — 불개입
            for i in range(len(prev)):
                for j in range(i + 1, len(prev)):
                    pair = frozenset((prev[i], prev[j]))
                    if len(pair) == 2 and (pair in _STEM_HAP or pair in _BRANCH_HAP):
                        return m.group(0)          # 실제 합이 섞여 있다 — 보존
            return f"관계{mark}{_HAP_JOSA.get(josa, josa)}"
        out.append(_HAP_WORD_RE.sub(_sub, chunk))
    # '합의 관계' → '관계의 관계' 로 굳어지던 비문 정리(중화 판단 자체는 옳으나 문장이 깨졌다).
    return _DUP_RELATION_RE.sub("관계", "".join(out))


# 항목/제목 줄 — 중복 제거로 통째로 비더라도 원문을 유지할 줄(불릿·번호·헤딩·굵은 라벨).
_STRUCT_LINE_RE = re.compile(r"^\s*(?:[-•·*+]|\d{1,2}[.)]|#{1,6}|\*\*|\|)")
# '- **라벨**: 값 — 긴 설명' 형태에서 라벨+값만 떼어내기 위한 패턴.
_STRUCT_LABEL_VALUE_RE = re.compile(r"^(\s*(?:[-•·*+]|\d{1,2}[.)])\s*\**[^:：\n]{1,24}\**\s*[:：]\s*)(.+)$")
# 값과 설명을 가르는 자리: 줄표, 문장 끝, 그리고 '…길·길·길·길로,' 처럼 값 뒤에 붙는 연결 조사.
_VALUE_TAIL_RE = re.compile(r"\s*[—–]\s*|(?<=[.。])\s+|(?<=[가-힣\]\)*·])(?:으로|로|이며|이라)\s*,\s*")


def _shorten_struct_dup(line: str) -> str:
    """되풀이되는 항목 줄을 '라벨: 값'까지만 남기고 뒤의 설명 절을 덜어낸다.

    이름 3개가 모두 같은 결과(예: 수리 4격 전부 길)이면 그 줄은 정당한 '각 이름의 값'이라
    지우면 구멍이 생긴다. 그렇다고 긴 설명까지 3번 되풀이하면 읽는 사람에게는 그냥 중복이다
    (전수감사 실측 아호 4런 4건) — 값은 남기고 수식어만 줄여 둘 다 피한다.
    """
    m = _STRUCT_LABEL_VALUE_RE.match(line)
    if not m:
        return line
    val = m.group(2)
    head = _VALUE_TAIL_RE.split(val, maxsplit=1)[0].strip()
    # 값이 쉼표로 나열돼 있으면('원격 25 길, 형격 12 흉, 이격 21 길로, 정격 33 길입니다.')
    # '로,'를 설명 시작점으로 오인해 값 자체가 잘린다 — 그럴 땐 줄이지 않는다(감사 실측).
    if "," in head:
        return line
    return (m.group(1) + head) if head and len(head) < len(val) else line
# 빈 줄 3개 이상(= 눈에 보이는 큰 공백) → 2개로. 공백만 있는 줄도 빈 줄로 본다.
_BLANK_RUN_RE = re.compile(r"\n(?:[ \t]*\n){2,}")
# 같은 구절이 마침표 없이 끝없이 되풀이되는 생성 폭주(실측 2026-07-22: '인연에 대한 기회가
# 생길 때까지는'이 컨텍스트 한계까지 반복된 뒤 절단). 문장 단위 중복 제거는 종결부호가 없어
# 못 잡으므로, '같은 구절 3회 이상 연속'을 통째로 한 번으로 접는다(결정적·멱등).
_RUNAWAY_RE = re.compile(r"(.{6,60}?)\1{2,}")


def _collapse_runaway(text: str) -> str:
    return _RUNAWAY_RE.sub(r"\1", text) if text else text
# '#### 7월 (정미월)' 같은 달 소제목 — 중복 제거의 문맥 판정용(chat_service 쪽 패턴과 별개로 둔다).
_MONTH_SECTION_RE = re.compile(r"(?:#{2,6}\s*)?\*{0,2}(\d{1,2})월[\s*(:]")


def _dedupe_repeated_sentences(text: str) -> str:
    """'완전히 동일한 문장'(15자 이상)이 답변 어디서든 반복되면 첫 번째만 남긴다(결정적·멱등).

    실측 2건(2026-07-21 신년운세): ①같은 문단 안 2회 연속('정재(正財)의 강한 기운은 …') ②서로
    다른 달 단락 간 복붙('이 달에는 감정적인 갈등이 …' 3월↔7월) — 약한 LLM의 템플릿 반복.
    의미 판단 없이 '15자+ 동일 문자열' 반복만 제거하므로 오탐 없음(정당한 장문 완전 반복은 없음).
    """
    seen: set[str] = set()
    out_paras: list[str] = []
    in_month = False          # 지금 줄이 '월별 흐름'의 어느 달 안에 있는가
    for para in text.split("\n"):
        # 같은 '항목 줄 완전중복'이라도 문맥에 따라 뜻이 정반대다 —
        #   · 월별 섹션: 달마다 같은 문장 = 템플릿 복붙(운영 DB 12건 실측) → 지워야 한다
        #   · 작명·아호: 이름마다 같은 값 = 각 이름의 사실 → 지우면 그 이름에 구멍이 난다
        _st = para.lstrip()
        if _MONTH_SECTION_RE.match(_st):
            in_month = True
        elif _st.startswith("#"):
            in_month = False
        # 문장 경계: 종결부호 뒤 공백. 마지막 조각(종결부호 없음)도 보존.
        parts = re.split(r"(?<=[.!?다요])\s+", para)
        kept: list[str] = []
        for p in parts:
            key = p.strip()
            if len(key) >= 15 and key in seen:
                continue
            if len(key) >= 15:
                seen.add(key)
            kept.append(p)
        if len(kept) == len(parts):
            out_paras.append(para)
            continue
        if any(p.strip() for p in kept):
            out_paras.append(" ".join(kept))
            continue
        # 줄 전체가 중복이라 통째로 비는 경우(실측 2026-07-22 작명·아호: 이름마다 반복되는
        # '- **수리 4격**: …' 불릿이 삭제돼 본문 구멍 + 빈 줄이 남았다).
        # 항목/제목 줄은 각 이름·각 달에 속한 고유 내용이므로 지우지 않고 원문 유지하고,
        # 평문 줄만 줄째로 없앤다(빈 줄을 남기지 않는다 — 운영자 지적 '중간중간 공백').
        if _STRUCT_LINE_RE.match(para) and not in_month:
            out_paras.append(_shorten_struct_dup(para))
    # 줄을 없앤 자리에서 빈 줄이 맞붙어 생기는 과다 공백을 접는다(운영자 반복 지적 '중간중간 공백').
    # 마크다운 표시상 빈 줄 2개 이상은 1개와 동일하므로 손실 없음.
    return _collapse_runaway(_BLANK_RUN_RE.sub("\n\n", "\n".join(out_paras)).strip())


# '명리 용어(한자+한글 뒤섞임)' — 알려진 용어가 아니라 정자를 특정할 수 없는 깨진 병기
# (실측 2026-07-22 택일: '황도(金궤)' 3회 — 엔진이 준 값은 한글 '금궤'인데 모델이 한자를 섞었다).
# 괄호 안 한자를 오행·간지 독음표로 한글화해 읽을 수 있게 만든다. 성씨 오교정(金=김≠금)을 피하려
# **앞 용어가 명리 문맥어일 때만** 적용하고, 독음을 모르는 한자가 하나라도 있으면 손대지 않는다.
_MIXED_CTX_TERMS = ("황도", "흑도", "건제", "이십팔수", "일지", "월지", "년지", "시지",
                    "일간", "월간", "년간", "시간", "세운", "대운", "용신", "희신", "기신", "십성")
_MIXED_CTX_PAREN_RE = re.compile(
    r"(" + "|".join(_MIXED_CTX_TERMS) + r")\s*\(\s*"
    r"((?=[가-힣一-鿿]*[一-鿿])(?=[가-힣一-鿿]*[가-힣])[가-힣一-鿿]{1,4})\s*\)"
)


def _mixed_ctx_sub(m: "re.Match[str]") -> str:
    inner = m.group(2)
    if any(c not in _GANJI_READING for c in inner if "一" <= c <= "鿿"):
        return m.group(0)
    ko = "".join(_GANJI_READING.get(c, c) for c in inner)
    return f"{m.group(1)}({ko})"


def fix_term_hanja(text: str) -> str:
    """LLM 답변의 '용어(한자)' 병기에서 한자를 정자(正字)로, 간지 독음을 정독으로 교정.

    + '정재(정재)' 한글(한글) 오병기 교정 + 문단 내 완전 동일 문장 반복 제거(전 메뉴 공통 체인).
    """
    if not text:
        return text
    # 용어 병기 교정보다 먼저 — '일간(을木)'처럼 간지가 섞여 깨진 병기를 한글 간지로 살려 둔다.
    # (뒤의 _TERM_MIXED_PAREN_RE 에는 간지 보호 가드가 없어 '일간(日干)'으로 덮여 간지가 소실됐다.)
    text = _MIXED_CTX_PAREN_RE.sub(_mixed_ctx_sub, text)
    for ko, han in TERM_HANJA.items():
        def _term_sub(m: "re.Match[str]", ko: str = ko, han: str = han) -> str:
            inner = re.sub(r"[·\s]", "", m.group(1))
            # '년주(癸巳)'·'용신(庚金)'·'용신(庚·丁)'처럼 괄호가 실제 간지·오행이면 용어
            # 한자로 덮어쓰지 않는다(간지 정보 소실 방지 — 전문가 지적 케이스 #2 인접 리스크).
            if inner in _VALID_GANJI_HANJA or all(c in STEM_TO_WUXING for c in inner):
                return m.group(0)
            return f"{ko}({han})"
        text = _TERM_PAREN_RE[ko].sub(_term_sub, text)
        text = _TERM_SELF_PAREN_RE[ko].sub(f"{ko}({han})", text)   # '정재(정재)' → '정재(正財)'
        text = _TERM_MIXED_PAREN_RE[ko].sub(f"{ko}({han})", text)  # '원진(原진)' → '원진(怨嗔)'
    for ko, han in _REL_TERM_HANJA.items():                        # '형(형)' → '형(刑)'
        text = _REL_SELF_PAREN_RE[ko].sub(f"{ko}({han})", text)
    for ko, rx in _REL_WRONG_PAREN_RE.items():                     # '파(상충)' → '파(破)'
        text = rx.sub(f"{ko}({_REL_TERM_HANJA.get(ko) or TERM_HANJA[ko]})", text)
    # '庚(庚)' → '경(庚)' — 독음을 아는 간지·오행만(모르면 불개입)
    text = _HANJA_SELF_PAREN_RE.sub(
        lambda m: (f"{_GANJI_READING[m.group(1)]}({m.group(1)})"
                   if m.group(1) in _GANJI_READING else m.group(0)), text)
    # '정미월(丁未월)' → '정미월(丁未月)' — 괄호 안 단위만 한글로 남은 병기
    text = _GANJI_UNIT_PAREN_RE.sub(
        lambda m: f"{m.group(1)}({m.group(2)}{_UNIT_HANJA[m.group(3)]})", text)
    # 십성 한자 단독('劫財') → '겁재(劫財)' — 한글 병기 강제(실측: 인용부호 속 한자 단독 노출)
    text = _BARE_TEN_GOD_RE.sub(lambda m: f"{_TEN_GOD_KO_BY_HANJA[m.group(1)]}({m.group(1)})", text)
    return _fix_corrupted_star_gloss(enforce_easy_gloss(_dedupe_repeated_sentences(
        _strip_internal_labels(_fix_hanja_reading_paren(_fix_wuxing_generate_direction(
            _fix_wuxing_overcome_direction(
                _fix_false_hap(_strip_copied_table_lines(
                    _strip_md_rules(_fix_ganji_reading(
                        _fix_bare_ganji_unit(_strip_reading_start_filler(text)))))))))))))


# ── LLM 출력 간지(干支) 병기 교정 ────────────────────────────────
# 프롬프트에 정독('계사(癸巳)')·정간지를 주입해도 1차 로컬모델이 본문 재서술 중 어느 한쪽을
# 환각한다(전문가 지적 실측 2건: 癸巳→'귀사' 독음 환각, '무술'→戊辰 한자 환각). 괄호 안이
# 천간·지지·오행 글자로만 이뤄진 '한글(干支)' 병기에서 **유효성 우선 규칙**으로 교정한다:
#   한글 독음이 유효한 조합(60갑자·간지+오행·삼합)이면 → 한글 신뢰, 한자를 교정
#   무효한 독음(예: '귀사')이면 → 한자 신뢰, 독음을 교정
#   (근거: 한국어 특화 로컬모델은 한글이 강하고 한자가 약함 — 실측 2건 모두 부합)
# 오탐 가드:
#   ① 다른 한자가 섞이면 불개입 — '무계합화(戊癸合火)'·'정관(正官)' 보존
#   ② 1글자 간지는 제외 — '말띠(午)'·'자(子)시' 같은 정상 표기 보존
#   ③ 한글·한자 독음이 한 음절도 안 겹치면 판단 불가로 불개입 — '년주(癸巳)'·'물뱀(癸巳)' 보존
_GANJI_READING: dict[str, str] = {
    **dict(zip(HEAVENLY_STEMS, STEM_KOREAN)),
    **dict(zip(EARTHLY_BRANCHES, BRANCH_KOREAN)),
    **WUXING_KOREAN,
}

# 유효한 간지 병기 조합: 한글 정독 → 정간지. 60갑자 + 천간+오행 + 지지+오행 + 삼합.
_VALID_GANJI_KO_TO_HANJA: dict[str, str] = {
    **{
        STEM_KOREAN[i % 10] + BRANCH_KOREAN[i % 12]:
        HEAVENLY_STEMS[i % 10] + EARTHLY_BRANCHES[i % 12]
        for i in range(60)
    },
    **{
        STEM_KOREAN[HEAVENLY_STEMS.index(s)] + WUXING_KOREAN[w]: s + w
        for s, w in STEM_TO_WUXING.items()
    },
    **{
        BRANCH_KOREAN[EARTHLY_BRANCHES.index(b)] + WUXING_KOREAN[w]: b + w
        for b, w in BRANCH_TO_WUXING.items()
    },
    "신자진": "申子辰", "인오술": "寅午戌", "사유축": "巳酉丑", "해묘미": "亥卯未",
}
_VALID_GANJI_KO_TO_HANJA.pop("신금", None)  # '신금'은 辛金/申金 중의적 — 한글신뢰 교정 제외

# 유효한 간지 병기 한자(용어 교정 보호용): 위 조합들 + 단글자(천간·지지·오행) + 辛金/申金.
_VALID_GANJI_HANJA: frozenset[str] = frozenset(
    set(_VALID_GANJI_KO_TO_HANJA.values())
    | {"辛金", "申金"}
    | set(HEAVENLY_STEMS) | set(EARTHLY_BRANCHES) | set(WUXING_LIST)
)

_GANJI_PAREN_RE = re.compile(r"([가-힣]{2,4})\s*\(\s*([一-鿿]{2,4})\s*\)")


def _fix_ganji_reading(text: str) -> str:
    def _sub(m: "re.Match[str]") -> str:
        hangul, hanja = m.group(1), m.group(2)
        if any(c not in _GANJI_READING for c in hanja):
            return m.group(0)
        n = len(hanja)
        if len(hangul) < n:
            return m.group(0)
        expected = "".join(_GANJI_READING[c] for c in hanja)
        head, tail = hangul[:-n], hangul[-n:]
        if tail == expected:
            return m.group(0)
        if not any(a == b for a, b in zip(tail, expected)):
            return m.group(0)  # 판단 불가(둘 다 유효 가능) — 안전하게 불개입
        fixed_hanja = _VALID_GANJI_KO_TO_HANJA.get(tail)
        if fixed_hanja:
            return f"{head}{tail}({fixed_hanja})"  # 한글 유효('무술') → 한자 교정 戊辰→戊戌
        return f"{head}{expected}({hanja})"        # 한글 무효('귀사') → 독음 교정 귀사→계사

    return _fix_branch_unit_hanja(_GANJI_PAREN_RE.sub(_sub, text))


# ── 지지+시간단위 병기 교정 ('축월(子月)'→'축월(丑月)') ─────────────
# 실측(택일): 지지 한글 '축'은 맞는데 한자를 子로 오표기(丑月이 정답). 위 _fix_ganji_reading은
# 괄호에 月(간지 아님)이 섞여 불개입한다. '지지한글+월/일/시/년(지지한자+月/日/時/年)' 병기에서
# 한글 지지(결정적 헤드라인 — 예: 축 일지 대상의 '축월/축일' 추천)를 기준으로 한자 지지·단위를
# 교정한다. 한글·한자가 일치하면 불개입(정상 '축일(丑日)' 보존).
_BRANCH_KO_TO_HJ: dict[str, str] = dict(zip(BRANCH_KOREAN, EARTHLY_BRANCHES))
_UNIT_KO_TO_HJ: dict[str, str] = {"월": "月", "일": "日", "시": "時", "년": "年", "연": "年"}
_BRANCH_UNIT_RE = re.compile(
    r"([자축인묘진사오미신유술해])(월|일|시|년|연)\s*\(\s*"
    r"([子丑寅卯辰巳午未申酉戌亥])\s*([月日時年])\s*\)"
)


def _fix_branch_unit_hanja(text: str) -> str:
    def _sub(m: "re.Match[str]") -> str:
        ko_br, ko_unit, ha_br, ha_unit = m.groups()
        want_br = _BRANCH_KO_TO_HJ[ko_br]
        want_unit = _UNIT_KO_TO_HJ[ko_unit]
        if ha_br == want_br and ha_unit == want_unit:
            return m.group(0)  # 일치 → 보존
        return f"{ko_br}{ko_unit}({want_br}{want_unit})"  # 한글 지지 기준 한자 교정

    return _BRANCH_UNIT_RE.sub(_sub, text)


def compute_ten_god(day_stem: str, other_stem: str) -> str:
    """일간(day_stem)을 기준으로 other_stem의 십성(한자)을 반환."""
    if day_stem not in STEM_TO_WUXING or other_stem not in STEM_TO_WUXING:
        raise ValueError(f"invalid stem: {day_stem}, {other_stem}")
    d_elem = STEM_TO_WUXING[day_stem]
    o_elem = STEM_TO_WUXING[other_stem]
    same_yy = STEM_IS_YANG[day_stem] == STEM_IS_YANG[other_stem]

    if d_elem == o_elem:                          # 같은 오행
        return "比肩" if same_yy else "劫財"
    if WUXING_GENERATES[d_elem] == o_elem:        # 내가 생함 (식상)
        return "食神" if same_yy else "傷官"
    if WUXING_OVERCOMES[d_elem] == o_elem:        # 내가 극함 (재성)
        return "偏財" if same_yy else "正財"
    if WUXING_OVERCOMES[o_elem] == d_elem:        # 나를 극함 (관성)
        return "偏官" if same_yy else "正官"
    if WUXING_GENERATES[o_elem] == d_elem:        # 나를 생함 (인성)
        return "偏印" if same_yy else "正印"
    raise RuntimeError("unreachable")  # 오행은 5개라 위 5분기로 완전 분류됨


# ============================================================
# 합/충 (간단판; 추후 확장)
# ============================================================
# 천간합 (天干合): 갑기합토, 을경합금, 병신합수, 정임합목, 무계합화
STEM_COMBINATIONS: dict[frozenset[str], str] = {
    frozenset({"甲", "己"}): "土",
    frozenset({"乙", "庚"}): "金",
    frozenset({"丙", "辛"}): "水",
    frozenset({"丁", "壬"}): "木",
    frozenset({"戊", "癸"}): "火",
}

# 천간충 (天干沖): 갑경, 을신, 병임, 정계
STEM_CONFLICTS: tuple[frozenset[str], ...] = (
    frozenset({"甲", "庚"}),
    frozenset({"乙", "辛"}),
    frozenset({"丙", "壬"}),
    frozenset({"丁", "癸"}),
)

# 지지육합 (地支六合): 자축, 인해, 묘술, 진유, 사신, 오미
BRANCH_SIX_COMBINATIONS: dict[frozenset[str], str] = {
    frozenset({"子", "丑"}): "土",
    frozenset({"寅", "亥"}): "木",
    frozenset({"卯", "戌"}): "火",
    frozenset({"辰", "酉"}): "金",
    frozenset({"巳", "申"}): "水",
    frozenset({"午", "未"}): "火",   # 일부 학설은 土
}

# 지지충 (地支沖): 자오, 축미, 인신, 묘유, 진술, 사해
BRANCH_CONFLICTS: tuple[frozenset[str], ...] = (
    frozenset({"子", "午"}),
    frozenset({"丑", "未"}),
    frozenset({"寅", "申"}),
    frozenset({"卯", "酉"}),
    frozenset({"辰", "戌"}),
    frozenset({"巳", "亥"}),
)

# 삼합 (三合): 신자진(水), 인오술(火), 사유축(金), 해묘미(木)
BRANCH_TRIPLE_COMBINATIONS: dict[frozenset[str], str] = {
    frozenset({"申", "子", "辰"}): "水",
    frozenset({"寅", "午", "戌"}): "火",
    frozenset({"巳", "酉", "丑"}): "金",
    frozenset({"亥", "卯", "未"}): "木",
}


# ============================================================
# 신살(神煞) — 궁합용 지지 관계 (리서치 확정 2026-06)
# ============================================================
# 원진(怨嗔): 애증·원망. 궁합 강한 부정 신호.
BRANCH_WONJIN: tuple[frozenset[str], ...] = (
    frozenset({"子", "未"}),
    frozenset({"寅", "酉"}),
    frozenset({"丑", "午"}),
    frozenset({"卯", "申"}),
    frozenset({"辰", "亥"}),
    frozenset({"巳", "戌"}),
)

# 귀문(鬼門): 예민·직관·심리작용. 원진과 4쌍 겹침(子酉·寅未만 다름).
BRANCH_GWIMUN: tuple[frozenset[str], ...] = (
    frozenset({"子", "酉"}),
    frozenset({"寅", "未"}),
    frozenset({"丑", "午"}),
    frozenset({"卯", "申"}),
    frozenset({"辰", "亥"}),
    frozenset({"巳", "戌"}),
)

# 해(害): 방해·서운함.
BRANCH_HARM: tuple[frozenset[str], ...] = (
    frozenset({"子", "未"}),
    frozenset({"丑", "午"}),
    frozenset({"寅", "巳"}),
    frozenset({"卯", "辰"}),
    frozenset({"申", "亥"}),
    frozenset({"酉", "戌"}),
)

# 파(破): 깨짐·분리.
BRANCH_BREAK: tuple[frozenset[str], ...] = (
    frozenset({"子", "酉"}),
    frozenset({"卯", "午"}),
    frozenset({"寅", "亥"}),
    frozenset({"巳", "申"}),
    frozenset({"丑", "辰"}),
    frozenset({"戌", "未"}),
)

# 형(刑): 마찰·구설. 삼형(寅巳申·丑戌未)의 2글자 조합 + 상형(子卯) + 자형(辰午酉亥, 같은 글자 2개).
# 두 사람 일지 비교용이라 삼형은 2-조합으로 분해해 수록.
BRANCH_PUNISH: tuple[frozenset[str], ...] = (
    # 삼형 寅巳申
    frozenset({"寅", "巳"}),
    frozenset({"巳", "申"}),
    frozenset({"寅", "申"}),
    # 삼형 丑戌未
    frozenset({"丑", "戌"}),
    frozenset({"戌", "未"}),
    frozenset({"丑", "未"}),
    # 상형
    frozenset({"子", "卯"}),
)
# 자형(自刑): 같은 글자가 만날 때(frozenset은 동일원소 중복불가라 별도 집합).
BRANCH_SELF_PUNISH: frozenset[str] = frozenset({"辰", "午", "酉", "亥"})

# 도화(桃花/咸池): 삼합국 장생지의 다음 글자(목욕지). 자기 삼합 그룹 → 도화 글자.
#   (⚠️ 왕지 아님 — 왕지로 '교정'하면 子午卯酉 그대로가 되어 전 결과가 깨진다. 값은 정답.)
#   상대 일지가 내 도화 글자이면 '도화 작용'(이성적 끌림, 길흉 양면).
DOHWA_BY_TRINE: dict[frozenset[str], str] = {
    frozenset({"申", "子", "辰"}): "酉",
    frozenset({"寅", "午", "戌"}): "卯",
    frozenset({"巳", "酉", "丑"}): "午",
    frozenset({"亥", "卯", "未"}): "子",
}


# ============================================================
# 헬퍼
# ============================================================
def stem_by_index(i: int) -> str:
    return HEAVENLY_STEMS[i % 10]


def branch_by_index(i: int) -> str:
    return EARTHLY_BRANCHES[i % 12]


def stem_korean(s: str) -> str:
    return STEM_KOREAN[HEAVENLY_STEMS.index(s)]


def branch_korean(b: str) -> str:
    return BRANCH_KOREAN[EARTHLY_BRANCHES.index(b)]


def ganji_allowed_elements(stem: str, branch: str) -> set[str]:
    """간지 한 기둥이 품은 오행(한자) — 천간·지지 표면 + 지장간.

    'X기(氣)가 강한 간지' 류 오행 속성 주장의 검증 기준(케이스 #3: 甲子에 화기 없음).
    지장간을 포함해 '갑술(甲戌)의 화기'(지장간 丁 근거) 같은 정상 해석은 통과시킨다."""
    out = {STEM_TO_WUXING[stem], BRANCH_TO_WUXING[branch]}
    out |= {STEM_TO_WUXING[h] for h in HIDDEN_STEMS.get(branch, ())}
    return out
