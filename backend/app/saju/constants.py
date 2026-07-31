"""사주 명리학 상수 (천간/지지/오행/십성/지장간)."""
from __future__ import annotations

import re
from typing import Literal

# 로케일 축(ko=한국어/한글 독음, vi=베트남어/한월음 라틴). 기본은 ko(한국 서비스 불변).
Locale = Literal["ko", "vi"]

# ============================================================
# 천간 (天干) — 10개
# ============================================================
HEAVENLY_STEMS: tuple[str, ...] = (
    "甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸",
)
STEM_KOREAN: tuple[str, ...] = (
    "갑", "을", "병", "정", "무", "기", "경", "신", "임", "계",
)
# 天干 한월음(Hán-Việt) — 베트남 로케일 독음. HEAVENLY_STEMS 와 위치 병렬.
STEM_VI: tuple[str, ...] = (
    "Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý",
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
# 地支 한월음 — 卯 정칙 "Mão"(남부 변이 "Mẹo"). EARTHLY_BRANCHES 위치 병렬.
BRANCH_VI: tuple[str, ...] = (
    "Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi", "Thân", "Dậu", "Tuất", "Hợi",
)
# 十二生肖(베트남) — 丑=Trâu(물소, not 소), 卯=Mèo(고양이, not 토끼), 未=Dê(염소). ★한국과 갈림.
BRANCH_ZODIAC_VI: tuple[str, ...] = (
    "Chuột", "Trâu", "Hổ", "Mèo", "Rồng", "Rắn", "Ngựa", "Dê", "Khỉ", "Gà", "Chó", "Lợn",
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
# 五行 한월음
WUXING_VI: dict[str, str] = {
    "木": "Mộc", "火": "Hỏa", "土": "Thổ", "金": "Kim", "水": "Thủy",
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
# 十神 한월음(Thập Thần) — VN Bát Tự 관용 라벨. 偏官=七殺 Thất sát.
TEN_GODS_VI: dict[str, str] = {
    "比肩": "Tỷ kiên", "劫財": "Kiếp tài",
    "食神": "Thực thần", "傷官": "Thương quan",
    "偏財": "Thiên tài", "正財": "Chính tài",
    "偏官": "Thiên quan", "正官": "Chính quan",
    "偏印": "Thiên ấn", "正印": "Chính ấn",
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
}

# '용어(한자[·한자 …])' — 괄호 안이 한자(+가운뎃점/공백)로만 이뤄질 때만 매칭(한글 설명 괄호는 보존).
_TERM_PAREN_RE: dict[str, "re.Pattern[str]"] = {
    ko: re.compile(rf"{re.escape(ko)}\s*\(\s*([一-鿿][一-鿿·\s]*)\)")
    for ko in TERM_HANJA
}


def fix_term_hanja(text: str) -> str:
    """LLM 답변의 '용어(한자)' 병기에서 한자를 정자(正字)로, 간지 독음을 정독으로 교정."""
    if not text:
        return text
    for ko, han in TERM_HANJA.items():
        def _term_sub(m: "re.Match[str]", ko: str = ko, han: str = han) -> str:
            inner = re.sub(r"[·\s]", "", m.group(1))
            # '년주(癸巳)'·'용신(庚金)'·'용신(庚·丁)'처럼 괄호가 실제 간지·오행이면 용어
            # 한자로 덮어쓰지 않는다(간지 정보 소실 방지 — 전문가 지적 케이스 #2 인접 리스크).
            if inner in _VALID_GANJI_HANJA or all(c in STEM_TO_WUXING for c in inner):
                return m.group(0)
            return f"{ko}({han})"
        text = _TERM_PAREN_RE[ko].sub(_term_sub, text)
    return _fix_ganji_reading(text)


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

    return _GANJI_PAREN_RE.sub(_sub, text)


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

# 도화(桃花/咸池): 삼합국의 왕지. 자기 삼합 그룹 → 도화 글자.
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


# ── 로케일별 독음 셀렉터 ─────────────────────────────────────────
# ko=한글 독음 / vi=한월음(Hán-Việt). stem_korean·branch_korean 은 ko 전용 래퍼로 보존
# (기존 호출부 무파손). 신규 코드는 아래 *_reading(x, locale) 을 쓴다.
_STEM_READING: dict[str, tuple[str, ...]] = {"ko": STEM_KOREAN, "vi": STEM_VI}
_BRANCH_READING: dict[str, tuple[str, ...]] = {"ko": BRANCH_KOREAN, "vi": BRANCH_VI}
_ZODIAC_READING: dict[str, tuple[str, ...]] = {"ko": BRANCH_ZODIAC, "vi": BRANCH_ZODIAC_VI}
_WUXING_READING: dict[str, dict[str, str]] = {"ko": WUXING_KOREAN, "vi": WUXING_VI}
_TEN_GODS_READING: dict[str, dict[str, str]] = {"ko": TEN_GODS_KO, "vi": TEN_GODS_VI}


def stem_reading(s: str, locale: Locale = "ko") -> str:
    """天干 한 글자 → 로케일 독음(ko 한글 / vi 한월음)."""
    return _STEM_READING[locale][HEAVENLY_STEMS.index(s)]


def branch_reading(b: str, locale: Locale = "ko") -> str:
    """地支 한 글자 → 로케일 독음."""
    return _BRANCH_READING[locale][EARTHLY_BRANCHES.index(b)]


def zodiac_reading(b: str, locale: Locale = "ko") -> str:
    """地支 → 십이지 동물명(ko 토끼 / vi Mèo=고양이 등). ★卯·丑 로케일 갈림."""
    return _ZODIAC_READING[locale][EARTHLY_BRANCHES.index(b)]


def wuxing_reading(w: str, locale: Locale = "ko") -> str:
    """五行 한자 → 로케일 독음(木→목 / Mộc)."""
    return _WUXING_READING[locale][w]


def ten_god_reading(hanja: str, locale: Locale = "ko") -> str:
    """十神 한자 → 로케일 독음(比肩→비견 / Tỷ kiên)."""
    return _TEN_GODS_READING[locale][hanja]


def ganji_allowed_elements(stem: str, branch: str) -> set[str]:
    """간지 한 기둥이 품은 오행(한자) — 천간·지지 표면 + 지장간.

    'X기(氣)가 강한 간지' 류 오행 속성 주장의 검증 기준(케이스 #3: 甲子에 화기 없음).
    지장간을 포함해 '갑술(甲戌)의 화기'(지장간 丁 근거) 같은 정상 해석은 통과시킨다."""
    out = {STEM_TO_WUXING[stem], BRANCH_TO_WUXING[branch]}
    out |= {STEM_TO_WUXING[h] for h in HIDDEN_STEMS.get(branch, ())}
    return out
