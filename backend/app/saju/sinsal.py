"""십이운성(十二運星)·십이신살(十二神煞)·공망(空亡) — 명식 부가 정보.

모두 표준 도출 규칙(일간/년지/일주 기준). 검증: 하늘도마뱀 만세력 샘플 일치.
"""
from __future__ import annotations

from .constants import EARTHLY_BRANCHES, HEAVENLY_STEMS

# ── 십이운성(포태법) ─────────────────────────────────────────────
# 일간의 장생(長生) 지지 + 양간 순행/음간 역행.
_LIFE_NAMES = ["장생", "목욕", "관대", "건록", "제왕", "쇠", "병", "사", "묘", "절", "태", "양"]
_LIFE_START = {
    "甲": "亥", "乙": "午", "丙": "寅", "丁": "酉", "戊": "寅",
    "己": "酉", "庚": "巳", "辛": "子", "壬": "申", "癸": "卯",
}
_YANG_STEMS = set("甲丙戊庚壬")


def _bidx(b: str) -> int:
    return list(EARTHLY_BRANCHES).index(b)


def twelve_life_stage(day_stem: str, branch: str) -> str:
    """일간 대비 지지의 십이운성."""
    si = _bidx(_LIFE_START[day_stem])
    bi = _bidx(branch)
    idx = (bi - si) % 12 if day_stem in _YANG_STEMS else (si - bi) % 12
    return _LIFE_NAMES[idx]


# ── 십이신살 ─────────────────────────────────────────────────────
# 기준 지지(보통 년지)의 삼합 고지+1 = 겁살, 이후 순서대로 배당.
_SINSAL_NAMES = ["겁살", "재살", "천살", "지살", "년살", "월살",
                 "망신", "장성", "반안", "역마", "육해", "화개"]
_GEOPSAL = {  # 지지 → 그 지지가 속한 삼합국의 겁살 지지
    "申": "巳", "子": "巳", "辰": "巳",   # 申子辰 水
    "寅": "亥", "午": "亥", "戌": "亥",   # 寅午戌 火
    "巳": "寅", "酉": "寅", "丑": "寅",   # 巳酉丑 金
    "亥": "申", "卯": "申", "未": "申",   # 亥卯未 木
}


def twelve_sinsal(ref_branch: str, branch: str) -> str:
    """기준 지지(년지) 대비 지지의 십이신살."""
    gi = _bidx(_GEOPSAL[ref_branch])
    return _SINSAL_NAMES[(_bidx(branch) - gi) % 12]


# ── 사령(司令) / 월률분야(月律分野) ──────────────────────────────
# 월지의 지장간이 절입 후 며칠씩 사령(용사)하는지(연해자평 계열 표준).
#   사생지(寅巳申亥): 여기7·중기7·정기16  사고지(辰戌丑未): 여기9·중기3·정기18
#   사왕지(子午卯酉): 여기·정기(午만 己 중기 포함).  ※申·亥 여기 천간은 학파차(戊 채택).
_BUNYA: dict[str, list[tuple[str, int]]] = {
    "寅": [("戊", 7), ("丙", 7), ("甲", 16)],
    "卯": [("甲", 10), ("乙", 20)],
    "辰": [("乙", 9), ("癸", 3), ("戊", 18)],
    "巳": [("戊", 7), ("庚", 7), ("丙", 16)],
    "午": [("丙", 10), ("己", 9), ("丁", 11)],
    "未": [("丁", 9), ("乙", 3), ("己", 18)],
    "申": [("戊", 7), ("壬", 7), ("庚", 16)],
    "酉": [("庚", 10), ("辛", 20)],
    "戌": [("辛", 9), ("丁", 3), ("戊", 18)],
    "亥": [("戊", 7), ("甲", 7), ("壬", 16)],
    "子": [("壬", 10), ("癸", 20)],
    "丑": [("癸", 9), ("辛", 3), ("己", 18)],
}


def saryeong(month_branch: str, days_after_jeolip: float) -> str:
    """절입 후 경과일에 사령(司令)하는 천간. 절입 당일=1일째."""
    table = _BUNYA.get(month_branch)
    if not table:
        return ""
    d = int(days_after_jeolip) + 1   # 절입 당일을 1일째로
    acc = 0
    for stem, n in table:
        acc += n
        if d <= acc:
            return stem
    return table[-1][0]   # 구간 초과 → 정기


# ── 납음(納音) 60갑자 오행 ───────────────────────────────────────
# 표준 60갑자 납음표(30쌍). 오행은 대연수 공식으로 자가검증(테스트).
_NAPEUM_PAIRS = [
    ("甲子", "乙丑", "해중금", "금"), ("丙寅", "丁卯", "노중화", "화"),
    ("戊辰", "己巳", "대림목", "목"), ("庚午", "辛未", "노방토", "토"),
    ("壬申", "癸酉", "검봉금", "금"), ("甲戌", "乙亥", "산두화", "화"),
    ("丙子", "丁丑", "간하수", "수"), ("戊寅", "己卯", "성두토", "토"),
    ("庚辰", "辛巳", "백랍금", "금"), ("壬午", "癸未", "양류목", "목"),
    ("甲申", "乙酉", "천중수", "수"), ("丙戌", "丁亥", "옥상토", "토"),
    ("戊子", "己丑", "벽력화", "화"), ("庚寅", "辛卯", "송백목", "목"),
    ("壬辰", "癸巳", "장류수", "수"), ("甲午", "乙未", "사중금", "금"),
    ("丙申", "丁酉", "산하화", "화"), ("戊戌", "己亥", "평지목", "목"),
    ("庚子", "辛丑", "벽상토", "토"), ("壬寅", "癸卯", "금박금", "금"),
    ("甲辰", "乙巳", "복등화", "화"), ("丙午", "丁未", "천하수", "수"),
    ("戊申", "己酉", "대역토", "토"), ("庚戌", "辛亥", "채천금", "금"),
    ("壬子", "癸丑", "상자목", "목"), ("甲寅", "乙卯", "대계수", "수"),
    ("丙辰", "丁巳", "사중토", "토"), ("戊午", "己未", "천상화", "화"),
    ("庚申", "辛酉", "석류목", "목"), ("壬戌", "癸亥", "대해수", "수"),
]
_NAPEUM: dict[str, tuple[str, str]] = {}
for _a, _b, _nm, _wx in _NAPEUM_PAIRS:
    _NAPEUM[_a] = (_nm, _wx)
    _NAPEUM[_b] = (_nm, _wx)

# 대연수 공식(자가검증용): 천간/지지 수 합 → 오행
_NAPEUM_STEM_N = {"甲": 1, "乙": 1, "丙": 2, "丁": 2, "戊": 3, "己": 3, "庚": 4, "辛": 4, "壬": 5, "癸": 5}
_NAPEUM_BR_N = {"子": 1, "丑": 1, "午": 1, "未": 1, "寅": 2, "卯": 2, "申": 2, "酉": 2, "辰": 3, "巳": 3, "戌": 3, "亥": 3}
_NAPEUM_WX = {1: "목", 2: "금", 3: "수", 4: "화", 5: "토"}


def napeum_element_formula(stem: str, branch: str) -> str:
    """대연수 공식 납음오행(자가검증용)."""
    t = _NAPEUM_STEM_N[stem] + _NAPEUM_BR_N[branch]
    if t > 5:
        t -= 5
    return _NAPEUM_WX[t]


def napeum(stem: str, branch: str) -> tuple[str, str]:
    """(납음 한글명, 오행). 예: ('천하수','수')."""
    return _NAPEUM.get(stem + branch, ("", ""))


# ── 생기복덕(生氣福德) 변효 엔진 ──────────────────────────────────
# 검증: 변효 메커니즘은 조견표 앵커(남2세=본명괘 兌)로 4/4 확정.
#   ⚠️ 나이→본명괘 매핑(남/여 8값)은 신뢰 출처 확정 전까지 비움 → 엔진만 활성.
# 후천팔괘 비트(상효,중효,하효): 양효=1,음효=0
_GWAE_BITS = {"乾": 0b111, "兌": 0b011, "離": 0b101, "震": 0b001,
              "巽": 0b110, "坎": 0b010, "艮": 0b100, "坤": 0b000}
_BITS_GWAE = {v: k for k, v in _GWAE_BITS.items()}
# 괘 → 지지(들). 坎子·離午·震卯·兌酉(왕지) / 艮丑寅·巽辰巳·坤未申·乾戌亥(우괘)
_GWAE_BRANCHES = {
    "坎": ["子"], "離": ["午"], "震": ["卯"], "兌": ["酉"],
    "艮": ["丑", "寅"], "巽": ["辰", "巳"], "坤": ["未", "申"], "乾": ["戌", "亥"],
}
_BRANCH_GWAE = {b: g for g, bs in _GWAE_BRANCHES.items() for b in bs}
# 변효 누적마스크(상=4,중=2,하=1): 생기상·천의중·절체하·유혼중·화해상·복덕중·절명하·귀혼중
_SAENGGI_MASK = {  # 라벨 → (본명괘에 XOR할 마스크, 길흉)
    "생기": (0b100, "길"), "천의": (0b110, "길"), "절체": (0b111, "흉"),
    "유혼": (0b101, "반"), "화해": (0b001, "흉"), "복덕": (0b011, "길"),
    "절명": (0b010, "흉"), "귀혼": (0b000, "반"),
}
# 생기복덕 8라벨 한월음(Hán-Việt) — vi 로케일 표시용.
_SAENGGI_VI = {
    "생기": "Sinh khí", "천의": "Thiên y", "절체": "Tuyệt thể", "유혼": "Du hồn",
    "화해": "Họa hại", "복덕": "Phúc đức", "절명": "Tuyệt mệnh", "귀혼": "Quy hồn",
}
# 길흉(길/반/흉) → 로케일 무관 stable key(프론트 색상 분기용).
_SAENGGI_GIL_KEY = {"길": "gil", "반": "ban", "흉": "hyung"}


def saenggi_bokdeok(
    bonmyeong_gwae: str, day_branch: str, locale: str = "ko"
) -> tuple[str, str, str]:
    """본명괘 + 그날 지지 → (생기복덕 라벨, 길흉, stable 길흉키).

    locale='ko'(기본)은 한글 라벨(생기/복덕/절명…), 'vi'는 한월음(Sinh khí…).
    3번째 값은 로케일 무관 gil|ban|hyung 키. 본명괘 불명이면 ('','','').
    """
    bm = _GWAE_BITS.get(bonmyeong_gwae)
    g = _BRANCH_GWAE.get(day_branch)
    if bm is None or g is None:
        return ("", "", "")
    target = _GWAE_BITS[g]
    mask = target ^ bm
    for label, (m, gil) in _SAENGGI_MASK.items():
        if m == mask:
            disp = _SAENGGI_VI[label] if locale == "vi" else label
            return (disp, gil, _SAENGGI_GIL_KEY.get(gil, ""))
    return ("", "", "")


# 본명괘 = 구성(九星) 본명성(생년·성별 기준). 공개값 검증: 1990년생 남자=坎.
#   九星수 → 괘: 1坎 2坤 3震 4巽 5(中) 6乾 7兌 8艮 9離.
_GUSEONG_GWAE = {1: "坎", 2: "坤", 3: "震", 4: "巽", 6: "乾", 7: "兌", 8: "艮", 9: "離"}


def _digit_root(n: int) -> int:
    while n > 9:
        n = sum(int(c) for c in str(n))
    return n


def bonmyeong_gwae(year: int, is_male: bool) -> str:
    """생년·성별 → 본명괘(구성 본명성). 5(中宮)은 남=坤·여=艮."""
    s = _digit_root(year)            # 생년 각 자리 합을 한 자리로
    if is_male:
        num = 11 - s
        if num > 9:
            num -= 9                 # 10 → 1
    else:
        num = s + 4
        if num > 9:
            num -= 9
    if num == 5:                     # 中宮 → 남 坤(2)·여 艮(8)
        num = 2 if is_male else 8
    return _GUSEONG_GWAE[num]


# ── 공망(空亡, 旬空) ─────────────────────────────────────────────
def gongmang(day_stem: str, day_branch: str) -> list[str]:
    """일주 기준 공망 2지지."""
    si = list(HEAVENLY_STEMS).index(day_stem)
    bi = _bidx(day_branch)
    jia = (bi - si) % 12   # 旬의 머리(甲X)의 지지 인덱스
    bl = list(EARTHLY_BRANCHES)
    return [bl[(jia + 10) % 12], bl[(jia + 11) % 12]]


# ── 삼재(三災) ───────────────────────────────────────────────────
# 년지 삼합국 기준의 통설 산법(결정적): 삼합의 生지에서 沖하는 3개 연지가 삼재年.
#   申子辰(水局)생 → 寅卯辰년 / 巳酉丑(金局)생 → 亥子丑년
#   寅午戌(火局)생 → 申酉戌년 / 亥卯未(木局)생 → 巳午未년
# ⚠️ 감수 대기: B-4 부적 발행 룰 전용 초안 — 전문가 확인 후 고정(조후용신 120칸과 동일 절차).
_SAMJAE_TABLE: dict[frozenset[str], tuple[str, str, str]] = {
    frozenset({"申", "子", "辰"}): ("寅", "卯", "辰"),
    frozenset({"巳", "酉", "丑"}): ("亥", "子", "丑"),
    frozenset({"寅", "午", "戌"}): ("申", "酉", "戌"),
    frozenset({"亥", "卯", "未"}): ("巳", "午", "未"),
}
_SAMJAE_PHASE = ("들삼재", "눌삼재", "날삼재")


def samjae_phase(birth_year_branch: str, current_year_branch: str) -> str | None:
    """올해가 삼재면 단계(들/눌/날삼재), 아니면 None."""
    for group, years in _SAMJAE_TABLE.items():
        if birth_year_branch in group:
            if current_year_branch in years:
                return _SAMJAE_PHASE[years.index(current_year_branch)]
            return None
    return None
