"""성명학 엔진 — 작명/개명/아호 공용.

요소(관법 중립 점수, 다관법은 가중치만 다름):
  ① 수리(數理) 81수    — 성+이름 획수 → 4격(원형이정) → 81수리 길흉
  ② 자원오행(字源五行) — 한자 부수의 오행 → 사주 부족오행 보완
  ③ 발음오행(發音五行) — 한글 초성 오행 → 성+이름 상생 배치
  ④ 음양(陰陽)         — 획수 홀짝 조화

데이터: data/naming/hanja_dict.json (Unihan 8,525자: ko·strokes·radical·defn)
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from .constants import WUXING_GENERATES, WUXING_KOREAN, WUXING_OVERCOMES
from .types import SajuChart

_DICT_PATH = Path(__file__).resolve().parents[3] / "data" / "naming" / "hanja_dict.json"


@lru_cache(maxsize=1)
def _hanja() -> dict[str, dict]:
    try:
        with _DICT_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


_HUN_PATH = Path(__file__).resolve().parents[3] / "data" / "naming" / "hanja_hun.json"


@lru_cache(maxsize=1)
def _hun_table() -> dict[str, str]:
    """한자 → 한국어 훈음('보배 진' 등). 대법원 인명용 한자 네이버 훈음(8,090자).

    [2026-07-24] 종전엔 뜻이 영어(Unihan defn 'precious, valuable')뿐이라 화면에 음만 나왔다.
    한자는 '뜻+음'이 함께 보여야 한다는 운영자 지시로 한국어 훈음을 정본으로 둔다.
    """
    try:
        raw = json.loads(_HUN_PATH.read_text(encoding="utf-8"))
        return raw.get("table") or {}
    except Exception:  # noqa: BLE001
        return {}


def hun_of(ch: str) -> str:
    """글자의 한국어 훈음('보배 진'). 없으면 빈 문자열."""
    return _hun_table().get(ch, "")


_POPULAR_PATH = Path(__file__).resolve().parents[3] / "data" / "naming" / "popular_names.json"


@lru_cache(maxsize=1)
def _popular() -> dict[str, dict]:
    """성별별 인기 이름 음절 가중치(대법원/네임차트 통계). {'male':{음절:가중치}, 'female':{...}}"""
    try:
        with _POPULAR_PATH.open(encoding="utf-8") as f:
            d = json.load(f)
        return {"male": d.get("male", {}), "female": d.get("female", {})}
    except Exception:  # noqa: BLE001
        return {"male": {}, "female": {}}


def _popularity(reading: str, gender: str) -> int:
    """이름 읽기(한글)의 인기 음절 가중치 합 — 클수록 현대 인기 이름에 가깝다(성별 반영)."""
    key = "female" if "female" in str(gender).lower() else "male"
    table = _popular().get(key, {})
    return sum(table.get(ch, 0) for ch in (reading or ""))


@lru_cache(maxsize=1)
def _top_names() -> dict[str, frozenset[str]]:
    """성별 실제 인기 이름 Top30(대법원/네임차트) — 읽기 전체가 일치하면 강하게 가산."""
    try:
        with _POPULAR_PATH.open(encoding="utf-8") as f:
            d = json.load(f).get("top_names", {})
        return {"male": frozenset(d.get("male", [])), "female": frozenset(d.get("female", []))}
    except Exception:  # noqa: BLE001
        return {"male": frozenset(), "female": frozenset()}


def _is_top_name(reading: str, gender: str) -> bool:
    key = "female" if "female" in str(gender).lower() else "male"
    return reading in _top_names().get(key, frozenset())


_DATED_PATH = Path(__file__).resolve().parents[3] / "data" / "naming" / "dated_names.json"


@lru_cache(maxsize=1)
def _dated() -> tuple[frozenset[str], int]:
    """촌스러운(구세대) 이름 음절 denylist + 패널티 크기.

    옥·숙·자·봉·순 등 1940~70년대 흔했던 음절은 상용한자라 상용가산(×100)을 받아 동점(score)
    그룹에서 살아남아 상위에 노출됐다(실측: 아숙·옥준·도옥). 이 음절이 읽기에 있으면 점수 자체를
    크게 깎아 하위로 보낸다. 데이터 파일이라 관리자가 조정 가능(하드코딩 금지).
    """
    try:
        with _DATED_PATH.open(encoding="utf-8") as f:
            d = json.load(f)
        return frozenset(d.get("syllables", [])), int(d.get("penalty", 1000))
    except Exception:  # noqa: BLE001
        return frozenset(), 1000


def _dated_count(reading: str) -> int:
    """이름 읽기(한글)에 포함된 촌스 음절 개수(0~2)."""
    syl, _ = _dated()
    return sum(1 for ch in (reading or "") if ch in syl)


_COMMON_PATH = Path(__file__).resolve().parents[3] / "data" / "naming" / "common_hanja.json"


@lru_cache(maxsize=1)
def _common_set() -> frozenset[str]:
    """상용 인명용 한자(교육용 기초한자 1,800) — 한국인이 친숙하게 인지하는 글자 집합.

    같은 음·자원오행이면 이 집합의 글자를 우선해 벽자(洮·玗 등) 대신 친숙한 글자(潤·河 등)를 쓴다.
    """
    try:
        with _COMMON_PATH.open(encoding="utf-8") as f:
            return frozenset(json.load(f).get("chars", ""))
    except Exception:  # noqa: BLE001
        return frozenset()


def _is_common(ch: str) -> bool:
    return ch in _common_set()


def _common_count(given: str) -> int:
    """이름(한자 2자)에 포함된 상용 한자 개수(0~2) — 친숙도 가산점용."""
    return sum(1 for c in (given or "") if c in _common_set())


# ── 발음오행: 한글 초성 → 오행(한자) ───────────────────────────
# ㄱㄲㅋ=木, ㄴㄷㄸㄹㅌ=火, ㅇㅎ=土, ㅅㅆㅈㅉㅊ=金, ㅁㅂㅃㅍ=水
_CHOSUNG = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
_CHO_ELEM = {
    "ㄱ": "木", "ㄲ": "木", "ㅋ": "木",
    "ㄴ": "火", "ㄷ": "火", "ㄸ": "火", "ㄹ": "火", "ㅌ": "火",
    "ㅇ": "土", "ㅎ": "土",
    "ㅅ": "金", "ㅆ": "金", "ㅈ": "金", "ㅉ": "金", "ㅊ": "金",
    "ㅁ": "水", "ㅂ": "水", "ㅃ": "水", "ㅍ": "水",
}


def _chosung_element(syllable: str) -> str | None:
    if not syllable:
        return None
    c = syllable[0]
    if "가" <= c <= "힣":
        idx = (ord(c) - 0xAC00) // 588
        return _CHO_ELEM.get(_CHOSUNG[idx])
    return None


# ── 소리오행 名格 (2026-07-27 워크플로 확보) ──────────────────────────────
# 초성오행(_CHO_ELEM, 술가오행)이 名格 리서치와 100% 일치 → 그 위에 상생/상극 판정만 얹는다.
# 규칙(결정적): 인접 오행쌍이 상생=+ / 비화(동일)=중립 / 상극=−.
#   상생+상생=매우좋음, 상생 포함=좋음, 비화만=보통, 상극 포함=나쁨, 상극 다수=매우나쁨.
# data/naming/sori_ohaeng_namgyeok.staging.json 에 125조합 표(감수용). 규칙 자체는 표준 오행 상생상극.
_SAENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}   # A生B


def _ohaeng_rel(a: str, b: str) -> str:
    if a == b:
        return "비화"
    if _SAENG.get(a) == b or _SAENG.get(b) == a:
        return "상생"
    return "상극"


def sori_ohaeng_namgyeok(reading: str) -> dict | None:
    """이름 한글 음 → 소리오행 배열 + 名格 등급(경쟁사 '부귀공명격/매우좋음' 계열).

    반환: {pattern: '金水金', elements: ['金','水','金'], grade: '매우좋음', rels: ['상생','상생'], note}
    """
    els = [e for e in (_chosung_element(c) for c in reading) if e]
    if len(els) < 2:
        return None
    rels = [_ohaeng_rel(els[i], els[i + 1]) for i in range(len(els) - 1)]
    n_geuk = rels.count("상극")
    n_saeng = rels.count("상생")
    if n_geuk >= 2:
        grade, note = "매우나쁨", "이웃 글자 소리오행이 서로 극(克)하는 배열이 많아요."
    elif n_geuk == 1:
        grade, note = "나쁨", "이웃 글자 소리오행에 상극이 있어요."
    elif n_saeng == len(rels):
        grade, note = "매우좋음", "이웃 글자 소리오행이 서로 상생(相生)해 흐름이 순조로워요."
    elif n_saeng >= 1:
        grade, note = "좋음", "이웃 글자 소리오행이 상생으로 이어져요."
    else:
        grade, note = "보통", "같은 소리오행이 이어져 무난해요(비화)."
    return {"pattern": "".join(WUXING_KOREAN.get(e, e) for e in els),
            "hanja_pattern": "".join(els), "elements": [WUXING_KOREAN.get(e, e) for e in els],
            "grade": grade, "rels": rels, "note": note}


# ── 소리음양 (모음 기반, 2026-07-27 워크플로 확보) ────────────────────────
# 종전 '음양' 축은 획수 홀짝(=수리음양)이라, 이건 신규 '소리음양' 축이다.
# ⚠️ ㅡ·ㅣ 처리는 학파 갈림(제자원리 ㅡ=음·ㅣ=중성 / 정해만세력 전부 음) — 원전 근거인
#    제자원리를 채택(ㅡ=음, ㅣ=중성). data/naming/sori_eumyang.staging.json 의 이견 참조.
_VOWEL_YY = {  # 중성 index(0~20) 기준. 훈민정음 제자원리.
    0: "양",   # ㅏ
    1: "양",   # ㅐ
    2: "양",   # ㅑ
    3: "양",   # ㅒ
    4: "음",   # ㅓ
    5: "음",   # ㅔ
    6: "음",   # ㅕ
    7: "음",   # ㅖ
    8: "양",   # ㅗ
    9: "양",   # ㅘ
    10: "양",  # ㅙ
    11: "양",  # ㅚ
    12: "양",  # ㅛ
    13: "음",  # ㅜ
    14: "음",  # ㅝ
    15: "음",  # ㅞ
    16: "음",  # ㅟ
    17: "음",  # ㅠ
    18: "음",  # ㅡ (제자원리 地=陰; 정해만세력도 음 — 이견 없이 음 채택)
    19: "음",  # ㅢ
    20: "중성",  # ㅣ (제자원리 人=중성; 정해만세력은 음으로 봄 — 이견)
}


def _jungseong_yy(syllable: str) -> str | None:
    """한 글자의 중성(모음) 음양('양'/'음'/'중성'). 한글이 아니면 None."""
    if not syllable:
        return None
    c = syllable[0]
    if "가" <= c <= "힣":
        jung = ((ord(c) - 0xAC00) % 588) // 28
        return _VOWEL_YY.get(jung)
    return None


def sori_eumyang(reading: str) -> dict | None:
    """이름 한글 음 → 소리음양 배열 + 조화 판정(순양·순음 기피, 섞임 선호)."""
    seq = [y for y in (_jungseong_yy(c) for c in reading) if y]
    if not seq:
        return None
    yang = seq.count("양")
    eum = seq.count("음")
    neu = seq.count("중성")
    # 중성(ㅣ)은 순양/순음 판정에서 완충 — 양·음 둘 다 있으면 조화.
    if yang and eum:
        grade, note = "좋음", "밝은 소리(양)와 낮은 소리(음)가 어우러져 균형이 좋아요."
    elif (yang and not eum) or (eum and not yang):
        if len(seq) - neu >= 2:
            grade = "재고"
            note = ("소리가 " + ("양(밝은 모음)" if yang else "음(낮은 모음)") + "으로 치우쳐 있어요.")
        else:
            grade, note = "보통", "소리 음양이 단조로워요."
    else:
        grade, note = "보통", "중성 위주라 음양이 뚜렷하지 않아요."
    return {"pattern": "".join(seq), "yang": yang, "eum": eum, "neutral": neu,
            "grade": grade, "note": note}


# ── 자원오행: 강희부수 번호 → 오행 (확실한 부수만; 불명은 None) ──
_RADICAL_ELEM: dict[int, str] = {}
for _no in (85, 15, 173, 195):  # 水氵 冫 雨 魚
    _RADICAL_ELEM[_no] = "水"
for _no in (86, 72):            # 火灬 日
    _RADICAL_ELEM[_no] = "火"
for _no in (75, 140, 118, 115):  # 木 艸艹 竹 禾
    _RADICAL_ELEM[_no] = "木"
for _no in (167, 96):           # 金 玉王
    _RADICAL_ELEM[_no] = "金"
for _no in (32, 46, 102, 170, 112):  # 土 山 田 阜阝 石
    _RADICAL_ELEM[_no] = "土"

# ── 확장 자원오행: 214 부수 표준 분류(data/naming/radical_element.json) ──
# 위 16개 부수만으론 道(辶)·俊(亻)·宇(宀)·書(曰) 등 인기 이름자가 후보에서 빠진다.
# 표준 부수 자원오행표(122/214 부수)를 외부 파일로 두고 _char_element가 우선 적용.
# 파일이 없으면 위 기본 16부수로 폴백(= 구(舊) 동작, 안전 롤백).
_RADICAL_ELEM_PATH = Path(__file__).resolve().parents[3] / "data" / "naming" / "radical_element.json"


@lru_cache(maxsize=1)
def _radical_element_ext() -> dict[int, str]:
    try:
        with _RADICAL_ELEM_PATH.open(encoding="utf-8") as f:
            raw = json.load(f).get("radical_element", {})
        return {int(k): v for k, v in raw.items()}
    except Exception:  # noqa: BLE001
        return {}


# 실제 성씨로 쓰이는 한자(조회 우선 정렬용)
_SURNAME_HANJA = set(
    "金李朴崔鄭姜趙尹張林吳韓申徐權黃安宋全洪柳高文梁孫裵白許南沈河郭成車朱禹具"
    "羅閔陳池嚴蔡元千方孔玄咸卞盧呂秋都石薛宣馬吉魏表明奇王潘玉陸印孟丁曺康辛愼"
    "任異劉兪蔣牟睦魚陰葛邕"  # 일부 희귀 성 포함
)


# 한국 성씨 전용 테이블 (한글 → 한자 변형). 단성 + 복성(2글자).
# Unihan 일반음과 분리한 성씨 전용 매핑. 金은 김(대부분)·금(일부 가문) 둘 다 읽혀
# 김→金, 금→琴·金 으로 분기. 단성/복성(황/황보 등)은 정확음 매칭으로 구분.
KOREAN_SURNAMES: dict[str, list[str]] = {
    "김": ["金"], "이": ["李", "異"], "박": ["朴"], "최": ["崔"], "정": ["鄭", "丁", "程"],
    "강": ["姜", "康", "強"], "조": ["趙", "曺"], "윤": ["尹"], "장": ["張", "蔣", "莊"],
    "한": ["韓"], "오": ["吳"], "서": ["徐"], "신": ["申", "辛", "愼"],
    "권": ["權"], "황": ["黃"], "안": ["安"], "송": ["宋"], "전": ["全", "田"], "홍": ["洪"],
    "유": ["柳", "劉", "兪"], "고": ["高"], "문": ["文"], "손": ["孫"],
    "배": ["裵"], "백": ["白"], "허": ["許"], "남": ["南"], "심": ["沈"], "하": ["河"],
    "곽": ["郭"], "성": ["成"], "차": ["車"], "주": ["朱", "周"], "우": ["禹"], "구": ["具", "丘"],
    "나": ["羅"], "민": ["閔"], "진": ["陳", "秦", "晉"], "지": ["池"], "엄": ["嚴"], "채": ["蔡"],
    "원": ["元", "袁"], "천": ["千"], "방": ["方"], "공": ["孔"], "현": ["玄"], "함": ["咸"],
    "변": ["卞", "邊"], "여": ["呂", "余"], "추": ["秋"], "도": ["都"], "석": ["石"],
    "설": ["薛"], "선": ["宣"], "마": ["馬"], "길": ["吉"], "연": ["延"], "위": ["魏"], "표": ["表"],
    "명": ["明"], "기": ["奇"], "반": ["潘"], "왕": ["王"], "금": ["琴", "金"], "옥": ["玉"], "육": ["陸"],
    "인": ["印"], "맹": ["孟"], "제": ["諸"], "모": ["牟"], "탁": ["卓"], "국": ["鞠"], "어": ["魚"],
    "라": ["羅"], "노": ["盧", "魯"], "양": ["梁", "楊", "樑"], "임": ["林", "任"],
    "은": ["殷"], "편": ["片"], "용": ["龍"], "예": ["芮"], "경": ["慶", "景"], "봉": ["奉"],
    "사": ["史"], "부": ["夫"], "가": ["賈"], "복": ["卜"], "태": ["太"], "피": ["皮"], "두": ["杜"],
    # '경' 키는 위(慶·景)에 이미 있음 — 종전 중복 '경' 키(값 慶 단독)가 dict 리터럴에서 앞 항목을
    # 덮어써 景(경)씨가 선택 불가였다(전수감사 실측). 중복 키 재발 시 test_surname_no_dup_loss가 잡음.
    "감": ["甘"], "음": ["陰"], "빈": ["賓"], "동": ["董"], "온": ["溫"],
    # 복성(複姓)
    "남궁": ["南宮"], "황보": ["皇甫"], "제갈": ["諸葛"], "선우": ["鮮于"], "독고": ["獨孤"],
    "사공": ["司空"], "서문": ["西門"], "동방": ["東方"], "을지": ["乙支"],
}


def lookup_surname(reading: str) -> list[dict]:
    """한국 성씨 전용 조회(단성·복성). reading 예: '금'→琴, '사공'→司空."""
    reading = (reading or "").strip()
    if reading not in KOREAN_SURNAMES:
        return []
    out = []
    for han in KOREAN_SURNAMES[reading]:
        strokes = sum(_strokes(c) or 0 for c in han)
        defn = " ".join((_hanja().get(c, {}).get("defn", "")[:24]) for c in han).strip()
        hun = " ".join(hun_of(c) for c in han).strip()   # 한국어 훈음('성 송' 등)
        out.append({"char": han, "strokes": strokes, "defn": defn, "hun": hun,
                    "is_surname": True, "is_compound": len(han) > 1})
    return out


def _name_allow_set() -> frozenset[str]:
    """작명 allowlist(name_hanja.json syllables)의 전체 한자 — 실제 이름에 쓰는 글자."""
    s: set[str] = set()
    for v in (_name_hanja().get("syllables") or {}).values():
        s |= set(v)
    return frozenset(s)


def _bad_meaning(ch: str) -> bool:
    """이름에 부적절한 뜻(더러울·미워할·우거질·숯 등) — 추천 생성과 동일 기준(_BAD_DEFN/_BAD_WORD_RE)."""
    defn = (_hanja().get(ch, {}).get("defn") or "").lower()
    if not defn:
        return False
    return any(b in defn for b in _BAD_DEFN) or bool(_BAD_WORD_RE.search(defn))


# 좋은 뜻 한글 훈 — 영어 defn 이 없는 인명용 길자(旿 밝을·晛 햇살·潾 맑을 등)를 picker 에 살린다.
_GOOD_HUN = (
    "밝", "빛", "맑", "아름", "고울", "옥", "구슬", "보배", "슬기", "지혜", "어질", "착",
    "클", "큰", "넓", "높", "귀", "복", "별", "봄", "꽃", "향", "노래", "기쁘", "기쁠",
    "즐거", "편안", "편할", "이룰", "성할", "빼어", "뛰어", "은혜", "도울", "사랑", "참",
    "바를", "곧", "하늘", "해", "달", "강", "뫼", "산", "샘", "못", "바다", "봉황", "용",
    "학", "소나무", "잣", "매화", "난초", "빛날", "우뚝", "상서", "복될", "밝힐", "진주",
    "구름", "이슬", "은", "금", "빛나", "화할", "따뜻", "온화", "곱", "예쁠", "맵시",
)
# 나쁜/천한 한글 훈 — 영어 defn 없이도 컷(까마귀·거만할·그르칠·아이·되돌릴 등).
# ⚠️ 오탐 방지로 '울·짝·종·병' 같은 짧은 단독어는 넣지 않는다(서울·매울 등 오배제 위험).
_BAD_HUN = (
    "더러", "미워", "우거", "숯", "까마귀", "거만", "그르칠", "게으", "죽을", "병들",
    "흉", "근심", "슬플", "원수", "도둑", "어두", "재앙", "허물", "거짓", "미혹",
    "어리석", "천할", "노예", "시끄", "오만", "성낼", "두려", "마귀", "귀신", "벌레",
    "되돌", "바디", "아이", "그물", "거스를", "에돌", "함부로",
)


def _hun_word(ch: str) -> str:
    """훈음('밝을 오')에서 훈(뜻) 부분('밝을')만."""
    h = hun_of(ch)
    return h.rsplit(" ", 1)[0] if " " in h else h


def _name_worthy(ch: str) -> bool:
    """picker 노출 가치 — 상용/allowlist 이거나, 인명용이면서 훈이 '좋은 뜻'인 길자."""
    if _is_common(ch) or ch in _name_allow_set():
        return True
    if not hun_of(ch):
        return False            # 대법원 인명용 아님 → 벽자
    hw = _hun_word(ch)
    if any(b in hw for b in _BAD_HUN):
        return False
    return any(g in hw for g in _GOOD_HUN)


def lookup_by_reading(reading: str, surname_first: bool = True, limit: int = 40) -> list[dict]:
    """한글 음(예 '이')에 해당하는 '이름에 쓸 만한' 한자 후보. 벽자·부적절한 뜻은 제외.

    [운영자 지적 2026-07-27] 종전엔 사전 8,525자 전체에서 음만 맞으면 다 노출 → '우거질 진'·
    '숯 많고 검을 진' 같은 벽자·흉자가 잔뜩 나왔다. 대법원 인명용(훈음 보유)이 아니거나 뜻이 나쁜
    글자는 빼고, 친숙도 순(작명 allowlist → 상용 1800 → 그 외 인명용)으로 정렬한다.
    ※ 개명은 '기존 이름' 입력이라 인명용은 남겨 찾을 수 있게 하되(벽자만 컷), 좋은 글자를 위로.
    """
    reading = (reading or "").strip()
    if not reading:
        return []
    allow = _name_allow_set()
    rows = []
    for ch, info in _hanja().items():
        if reading not in (info.get("ko") or []):
            continue
        in_allow = ch in allow
        is_sur = ch in _SURNAME_HANJA
        common = _is_common(ch)             # 교육용 1800 상용(한국인이 아는 글자)
        # 영어 defn + 한글 훈 양쪽으로 흉자 컷(상용이어도 까마귀·거만할·그르칠은 이름에 부적). allowlist·성씨는 유지.
        _hw = _hun_word(ch)
        if (_bad_meaning(ch) or any(b in _hw for b in _BAD_HUN)) and not (in_allow or is_sur):
            continue
        # 상용/allowlist/성씨, 또는 '좋은 뜻' 인명용 길자만(旿 밝을·潾 맑을 등). 벽자·천자는 컷.
        if not (is_sur or _name_worthy(ch)):
            continue
        # 친숙도 tier: 0 allowlist, 1 성씨, 2 상용, 3 좋은뜻 인명용
        tier = 0 if in_allow else 1 if (is_sur and surname_first) else 2 if common else 3
        rows.append((tier, info.get("strokes") or 99, ch, info))
    rows.sort(key=lambda t: (t[0], t[1]))
    return [
        {"char": ch, "strokes": info.get("strokes"),
         "defn": (info.get("defn") or "")[:60],
         "hun": hun_of(ch),                 # 한국어 훈음('보배 진') — 화면에 뜻+음 표시용
         "is_surname": ch in _SURNAME_HANJA}
        for _, _, ch, info in rows[:limit]
    ]


def _char_element(ch: str) -> str | None:
    """한자의 자원오행(부수 기준). 확장표(214 부수) 우선 → 기본 16부수 폴백. 불명이면 None."""
    info = _hanja().get(ch)
    if not info:
        return None
    rad = info.get("radical")
    ext = _radical_element_ext()
    if rad in ext:
        return ext[rad]
    return _RADICAL_ELEM.get(rad)


def _strokes(ch: str) -> int | None:
    info = _hanja().get(ch)
    return info.get("strokes") if info else None


# ── 원획법(原劃法) 획수 — 수리(81수 4격) 전용 (2026-07-27 워크플로 확보) ────────────
# 성명학 81수는 옥편 필획이 아니라 원획법(변형부수를 원래 부수 획수로 환원)으로 센다.
#   data/naming/wonhoek_radicals.staging.json (변형부수 14 + 숫자특수획 10, 검증완료).
# ⚠️ 4격(_four_pillars)에만 적용 — 자원오행·발음오행 등 다른 계산은 옥편획 유지.
#    격 결과가 바뀌는 근본 수정이므로 회귀 실측 후 반영(감수 대기 데이터).
@lru_cache(maxsize=1)
def _wonhoek_data() -> dict:
    """원획 보정: {radical_delta:{강희부수번호:추가획}, number:{숫자한자:획수}}."""
    try:
        p = Path(__file__).resolve().parents[3] / "data" / "naming" / "wonhoek_radicals.staging.json"
        raw = json.loads(p.read_text(encoding="utf-8"))
        # 강희부수 번호 → delta(원획 - 통상). 변형부수 원본→부수번호 매핑이 필요.
        # radicals 항목의 original(원래 부수 글자)로 강희번호를 역참조하기 어려우니,
        # variant 부수 글자 자체를 키로 쓰고, _char 의 radical 번호로 매칭한다.
        by_rad = {}
        for r in raw.get("radicals", []):
            delta = int(r["orig_strokes"]) - int(r.get("common_strokes", r["orig_strokes"]))
            if delta:
                by_rad[r.get("original", "")] = delta       # 원래 부수 글자 기준
        number = {r["char"]: int(r["counted_as"]) for r in raw.get("number_special", [])}
        return {"by_original": by_rad, "number": number}
    except Exception:  # noqa: BLE001
        return {"by_original": {}, "number": {}}


# 강희부수 번호 → 원래 부수 글자(원획 보정 대상만). 부수번호로 변형부수 여부를 판정.
_RAD_NO_TO_CHAR = {
    85: "水", 61: "心", 64: "手", 94: "犬", 96: "玉", 113: "示", 145: "衣",
    130: "肉", 140: "艸", 122: "网", 125: "老", 162: "辵", 163: "邑", 170: "阜",
}
# 원형(full-form) 부수 글자 자체는 이미 완전형이라 보정하지 않는다(示=5지 6이 아님).
#   변형부수(礻·氵…)를 쓴 파생 글자만 +delta. 王(임금왕)도 玉이 아니므로 제외(관법 이견 회피).
_WONHOEK_EXCLUDE = {"水", "心", "手", "犬", "玉", "王", "示", "衣", "肉", "月",
                    "艸", "网", "老", "辵", "邑", "阜"}


def _strokes_wonhoek(ch: str) -> int | None:
    """원획법 획수 — 4격(수리) 전용. 변형부수 보정 + 숫자 특수획. 그 외는 옥편획."""
    data = _wonhoek_data()
    if ch in data["number"]:
        return data["number"][ch]
    base = _strokes(ch)
    if base is None:
        return None
    if ch in _WONHOEK_EXCLUDE:
        return base
    rad = _hanja().get(ch, {}).get("radical")
    orig = _RAD_NO_TO_CHAR.get(rad)
    if orig:
        delta = data["by_original"].get(orig, 0)
        return base + delta
    return base


def _reading(ch: str) -> str:
    info = _hanja().get(ch)
    return (info.get("ko") or [""])[0] if info else ""


# 성(姓) 자리의 한자는 한자사전 대표음과 통용 성씨음이 다르다(실측: 金→'금'(김), 李→'리'(이),
# 車→'거'(차), 복성 南宮→''). 사용자가 reading 을 안 보내면 이 오독이 화면·PDF에 그대로 찍히고,
# 초성이 달라져 **발음오행까지 오염**된다(李: 리=ㄹ 화 vs 이=ㅇ 토). 성씨 사전으로 보정한다.
_SURNAME_PREFERRED = {"金": "김", "羅": "나"}     # 중의적 성씨 — 통용 표기를 쓴다
_SUR_RD_CACHE: dict[str, str] | None = None


def _surname_reading_map() -> dict[str, str]:
    global _SUR_RD_CACHE
    if _SUR_RD_CACHE is None:
        rev: dict[str, set[str]] = {}
        for ko, hanjas in KOREAN_SURNAMES.items():
            for h in hanjas:
                rev.setdefault(h, set()).add(ko)
        _SUR_RD_CACHE = {h: (_SURNAME_PREFERRED.get(h) or sorted(kos)[0])
                         for h, kos in rev.items()}
    return _SUR_RD_CACHE


def surname_reading(surname: str) -> str:
    """성(한자) → 통용 한글 성. 사전에 없으면 한자 대표음으로 폴백(복성도 처리)."""
    m = _surname_reading_map()
    if surname in m:
        return m[surname]
    return "".join(m.get(c) or _reading(c) for c in surname)


# ── 81수리 길흉·격 이름 (data/naming/suri_81.json) ─────────────────────────
# [2026-07-23] 격 이름(통솔격 등)·길흉을 5출처 다수결 교차검증 데이터로 교체.
#   근거·감수표: data/naming/suri_81.review.md. 종전엔 길/평/흉만 있고 격 이름이 없었다.
#   '평'은 학파 갈림(논쟁) 또는 중립 — 억지로 길/흉 판정하지 않는다(관법 단정 금지 원칙).
# ⚠️ 아래 하드셋은 데이터 파일 로드 실패 시 폴백일 뿐 — 정본은 JSON이다.
_SURI_GOOD_FALLBACK = {1, 3, 5, 6, 7, 8, 11, 13, 15, 16, 17, 18, 21, 23, 24, 25, 29, 31, 32, 33,
                       35, 37, 38, 39, 41, 45, 47, 48, 52, 57, 58, 61, 63, 65, 67, 68, 71, 73,
                       75, 77, 81}


@lru_cache(maxsize=1)
def _suri_table() -> dict[int, dict]:
    """번호(1~81) → {name_ko, name_hanja, fortune(길/평/흉), agreement}. 실패 시 빈 dict."""
    try:
        p = Path(__file__).resolve().parents[3] / "data" / "naming" / "suri_81.json"
        raw = json.loads(p.read_text(encoding="utf-8"))
        return {int(k): v for k, v in (raw.get("table") or {}).items()}
    except Exception:  # noqa: BLE001
        return {}


def _suri_grade(n: int) -> str:
    n = ((n - 1) % 81) + 1 if n > 81 else n
    row = _suri_table().get(n)
    if row:
        return row.get("fortune", "평")
    return "길" if n in _SURI_GOOD_FALLBACK else "흉"   # 데이터 유실 시 최소 동작


def _suri_name(n: int) -> dict:
    """번호 → {name_ko, name_hanja, agreement}. 격 이름(통솔격 등). 없으면 빈 값."""
    n = ((n - 1) % 81) + 1 if n > 81 else n
    row = _suri_table().get(n) or {}
    return {"name_ko": row.get("name_ko", ""), "name_hanja": row.get("name_hanja", ""),
            "agreement": row.get("agreement", "")}


# ── 출력 모델 ─────────────────────────────────────────────────
class NameFactor(BaseModel):
    key: str
    label: str
    score: int
    detail: str


class NamePerspective(BaseModel):
    key: str
    label: str
    total: int
    grade: str


class NameAnalysis(BaseModel):
    name: str                       # 한자 이름(성+이름)
    reading: str                    # 한글 음
    factors: dict[str, NameFactor]
    perspectives: dict[str, NamePerspective]
    four_pillars: dict[str, dict]   # 원형이정 격: {획수, 81수, 길흉}
    # 작명(NameCandidate)과 동일하게 글자별 두 오행을 분리 노출 — LLM 혼동 차단(전문가 지적:
    # '도하 발음오행은 목수가 아니라 화토'). 이름 전체(성+이름) 기준.
    elements: list[str] = []         # 자원오행(한자 부수) — 불명은 '불명'
    baleum_elements: list[str] = []  # 발음오행(한글 초성)
    hun: list[str] = []              # 글자별 한국어 훈음('성 송'·'보배 진') — 화면에 뜻+음 표시
    sori_ohaeng: dict | None = None  # 소리오행 名格(金水金 → 매우좋음 등) — 2026-07-27
    sori_eumyang: dict | None = None # 소리음양(모음 기반 조화) — 2026-07-27


class NameCandidate(BaseModel):
    given: str                      # 이름(한자)
    reading: str
    score: int
    suri_grade: str
    elements: list[str]             # 자원오행(한자 부수) — 불명은 '불명'
    baleum_elements: list[str]      # 발음오행(한글 초성) — 자원오행과 다른 개념(혼동 방지)
    meaning: str
    hun: list[str] = []             # 글자별 한국어 훈음('보배 진') — 뜻+음 표시


# 다관법 가중치 (합 100). 수리/오행/발음 강조 차이.
# [2026-07-10 전문가 결정] 발음오행은 **참고 수준**으로 가중치를 낮춘다(20~25 → 10~13).
#   근거: 발음오행 관법(초성=부족오행)과 현대 인기 이름이 구조적으로 충돌한다 — 인기 음절
#   (준·우·이·도·윤·호·시·지·하·현)의 초성이 ㅇㅎㅅㅈ(토·금) 지배적이라, 목(ㄱㅋ) 초성 인기
#   음절이 사실상 없다. 발음을 세게 걸면 민강·범민처럼 덜 자연스런 조합이 상위로 온다.
#   → 자연스러운 인기 이름 우선. 발음오행은 점수에 약하게 반영하고 값은 그대로 표시(참고).
#   낮춘 몫은 결정적 근거인 수리(81수)·자원오행에 재배분.
PERSPECTIVES = {
    "S": {"label": "수리 중시", "weights": {"suri": 50, "jawon": 25, "baleum": 10, "eumyang": 15}},
    "B": {"label": "균형", "weights": {"suri": 35, "jawon": 38, "baleum": 12, "eumyang": 15}},
    "O": {"label": "사주보완 중시", "weights": {"suri": 22, "jawon": 55, "baleum": 13, "eumyang": 10}},
}


def _deficient_elements(chart: SajuChart) -> list[str]:
    """사주에서 부족한 오행(평균 미만)을 보완 대상으로. 적은 순."""
    w = chart.wuxing
    counts = {"木": w.wood, "火": w.fire, "土": w.earth, "金": w.metal, "水": w.water}
    avg = sum(counts.values()) / 5
    def_ = sorted([e for e, c in counts.items() if c < avg], key=lambda e: counts[e])
    return def_ or [min(counts, key=counts.get)]


def _naming_targets(chart: SajuChart | None) -> tuple[list[str], list[str]]:
    """작명 목표 오행 (전문가 관법 2026-07): (발음오행 목표, 자원오행 목표).

    - 발음오행 = 부족 오행만(비겁=일간오행은 제외). 예: 목·수 부족 → 발음 수·목.
    - 자원오행 = 부족 오행 + (신약이면 비겁=일간오행도 보강 대상).
    """
    if chart is None:
        allf = ["木", "火", "土", "金", "水"]
        return allf, allf
    deficient = _deficient_elements(chart)
    bigyeop = chart.day_master_element                       # 일간 오행 = 비겁
    is_weak = chart.day_master_strength == "weak"            # 신약
    baleum = [e for e in deficient if e != bigyeop] or deficient   # 비겁 제외(없으면 부족 전체)
    jawon = list(deficient)
    if is_weak and bigyeop not in jawon:
        jawon = [bigyeop] + jawon                            # 신약 → 비겁 우선 보강
    return baleum, jawon


def _four_pillars(surname: str, given: str) -> dict[str, dict]:
    """4격(원형이정) + 격 이름 + 인생시기. 성 1자 + 이름 2자 기준(이름 1자는 허수 1 보정).

    [인생시기 2026-07-23] 표준 배정(RAG u00677·경쟁사·웹 3중 확증):
      원격=초년 / 형격=청년 / 이격=중년 / 정격=말년.
      (종전 주석은 형격=중년·이격=장년으로 잘못 적혀 있었으나 출력엔 없던 값 — 여기서 정본화.)
    """
    # ★원획법(原劃法) 적용 — 수리 4격은 옥편획이 아니라 원획으로 센다(성명학 표준, 2026-07-27).
    s = sum(_strokes_wonhoek(c) or 0 for c in surname)
    gs = [_strokes_wonhoek(c) or 0 for c in given]
    g1 = gs[0] if gs else 0
    g2 = gs[1] if len(gs) > 1 else 1  # 외자 이름 허수
    won = (g1 + g2)            # 元 원격 = 초년
    hyung = (s + g1)           # 亨 형격 = 청년(주격)
    i = (s + g2)               # 利 이격 = 중년
    jeong = (s + g1 + g2)      # 貞 정격 = 말년(총격)
    out = {}
    for k, label, stage, n in (("won", "원격(元)", "초년", won), ("hyung", "형격(亨)", "청년", hyung),
                               ("i", "이격(利)", "중년", i), ("jeong", "정격(貞)", "말년", jeong)):
        nm = _suri_name(n)
        out[k] = {"label": label, "stage": stage, "num": n, "grade": _suri_grade(n),
                  "suri_name": nm["name_ko"], "suri_hanja": nm["name_hanja"]}
    return out


def _score_suri(fp: dict[str, dict]) -> NameFactor:
    g2s = {"길": 100, "평": 60, "흉": 20}
    vals = [g2s[v["grade"]] for v in fp.values()]
    score = round(sum(vals) / len(vals))
    good = [v["label"] for v in fp.values() if v["grade"] == "길"]
    bad = [v["label"] for v in fp.values() if v["grade"] == "흉"]
    detail = f"4격 중 길 {len(good)}개" + (f", 흉 {len(bad)}개({'·'.join(bad)})" if bad else "")
    return NameFactor(key="suri", label="수리(81수)", score=score, detail=detail)


def _score_jawon(given: str, targets: list[str]) -> NameFactor:
    elems = [(_char_element(c)) for c in given]
    named = [e for e in elems if e]
    primary = set(targets[:2])
    hit = sum(1 for e in named if e in primary)
    if not named:
        return NameFactor(key="jawon", label="자원오행", score=55,
                          detail="자원오행 판별 가능한 글자 없음")
    score = round(40 + 60 * (hit / len(given)))
    tk = "·".join(WUXING_KOREAN[t] for t in targets[:2])
    detail = f"보완 대상({tk}) 중 {hit}/{len(given)}자 충족 · 글자오행 {'·'.join(WUXING_KOREAN[e] for e in named)}"
    return NameFactor(key="jawon", label="자원오행", score=min(100, score), detail=detail)


def _score_baleum(surname: str, given: str, targets: list[str] | None = None,
                  reading: str | None = None) -> NameFactor:
    """발음오행(한글 초성) 점수. 전문가 관법: **부족 오행 채우기**가 핵심(비겁 제외 targets).

    이름 글자의 초성오행이 목표(부족)오행을 얼마나 채우는지를 주점수로, 이름 흐름의 상극 배열은
    부차 감점으로 반영(종전엔 상생/상극 조화만 보고 부족오행을 안 봐서 '발음오행 목수'처럼 사주와
    무관하게 나왔음).

    reading: 성+이름 전체의 실제 한글 음(개명 등 사용자 입력). 주어지면 사전 독음 대신 이 음으로
    초성오행을 산출한다 — 稲처럼 사전 독음이 비어 글자가 통째로 누락되거나, 辰(신/진) 같은 다음(多音)
    한자에서 점수가 왜곡되던 실측 버그 차단."""
    full = surname + given
    if reading and len(reading) == len(full):
        full_src = list(reading)
        given_src = list(reading[len(surname):])
    else:
        full_src = [_reading(c) for c in full]
        given_src = [_reading(c) for c in given]
    given_seq = [e for e in (_chosung_element(r) for r in given_src) if e]
    if not given_seq:
        return NameFactor(key="baleum", label="발음오행", score=55, detail="발음오행 판별 불가")
    tset = set(targets or [])
    hit = sum(1 for e in given_seq if e in tset) if tset else 0
    base = 40 + 60 * (hit / len(given)) if tset else 55
    # 이름 전체 초성 배열의 상극(부차 감점 — 흐름 조화)
    seq = [e for e in (_chosung_element(r) for r in full_src) if e]
    clash = sum(1 for a, b in zip(seq, seq[1:])
                if WUXING_OVERCOMES.get(a) == b or WUXING_OVERCOMES.get(b) == a)
    score = round(max(0, min(100, base - 8 * clash)))
    tk = "·".join(WUXING_KOREAN[t] for t in (targets or [])[:2])
    detail = (f"초성오행 {'→'.join(WUXING_KOREAN[e] for e in given_seq)}"
              + (f" · 보완({tk}) {hit}/{len(given)}자" if tset else "")
              + (f" · 상극 {clash}" if clash else ""))
    return NameFactor(key="baleum", label="발음오행", score=score, detail=detail)


def _score_eumyang(surname: str, given: str) -> NameFactor:
    # 수리음양 = 획수 홀짝. 수리 계열이므로 4격과 동일하게 원획법 획수를 쓴다(2026-07-27).
    par = [(_strokes_wonhoek(c) or 0) % 2 for c in (surname + given)]  # 1=양(홀) 0=음(짝)
    if not par:
        return NameFactor(key="eumyang", label="수리음양", score=55, detail="획수 불명")
    yang = sum(par)
    eum = len(par) - yang
    # 한쪽으로 완전히 치우치면 감점, 섞이면 가점
    score = 100 if (yang and eum) else 50
    if len(par) >= 3 and (yang == len(par) or eum == len(par)):
        score = 40
    detail = f"양(홀){yang} 음(짝){eum}"
    return NameFactor(key="eumyang", label="수리음양", score=score, detail=detail)


def _perspectives(factors: dict[str, NameFactor]) -> dict[str, NamePerspective]:
    out = {}
    for k, cfg in PERSPECTIVES.items():
        w = cfg["weights"]
        total = round(sum(factors[fk].score * w[fk] / 100 for fk in w))
        grade = "대길" if total >= 80 else "길" if total >= 65 else "보통" if total >= 50 else "재고"
        out[k] = NamePerspective(key=k, label=cfg["label"], total=total, grade=grade)
    return out


def analyze_name(
    surname: str, given: str, chart: SajuChart | None = None, reading: str | None = None
) -> NameAnalysis:
    """이름(한자) 분석 — 개명 진단/이름풀이용.

    reading: 사용자가 입력한 한글 음(예 '송진수'). 다음(多音) 한자(辰=신/진 등)에서
    사전 대표음과 달라질 수 있으므로, 주어지면 표시 음이자 **발음오행 산출 기준**으로 우선 사용.
    """
    baleum_t, jawon_t = _naming_targets(chart)   # 발음=부족(비겁제외), 자원=부족+신약시 비겁
    fp = _four_pillars(surname, given)
    rd = (reading or "").strip()
    full = surname + given
    # 성은 성씨 사전 독음, 이름은 한자 대표음 — 사용자가 reading 을 안 보낸 경로에서
    # '金民秀'가 '금민수'로 찍히고 발음오행까지 어긋나던 실측 결함(전수감사 2026-07-22).
    reading = (rd if len(rd) == len(full)
               else surname_reading(surname) + "".join(_reading(c) for c in given))
    factors = {
        "suri": _score_suri(fp),
        "jawon": _score_jawon(given, jawon_t),
        # 실제 독음 기준(사전 독음이 빈 글자·다음자에서 점수 왜곡되던 실측 버그 차단)
        "baleum": _score_baleum(surname, given, baleum_t, reading=reading),
        "eumyang": _score_eumyang(surname, given),
    }
    return NameAnalysis(
        name=full, reading=reading,
        factors=factors, perspectives=_perspectives(factors), four_pillars=fp,
        # 작명과 동일하게 두 오행을 글자별로 분리 제공(혼동 차단)
        elements=[WUXING_KOREAN.get(_char_element(c) or "", "불명") for c in full],
        baleum_elements=[WUXING_KOREAN.get(_chosung_element(r) or "", "불명") for r in reading],
        hun=[hun_of(c) for c in full],   # 글자별 훈음(뜻+음) — 개명 화면 표시용
        sori_ohaeng=sori_ohaeng_namgyeok(reading),   # 소리오행 名格(경쟁사 소리오행 분석 대응)
        sori_eumyang=sori_eumyang(reading),          # 소리음양(경쟁사 소리음양 분석 대응)
    )


# 이름에 부적절한 뜻/이체자 필터(영문 정의 기준, v1 휴리스틱).
# ※ 정밀 품질은 대법원 인명용한자 + 한글 길자 큐레이션(후속 정제)에서 보강.
_BAD_DEFN = (
    # ※ end/die/ill 는 send·recommend(薦致賀)·soldier(士)·skill·brilliant(技) 를 substring 오탐 →
    #   아래 _BAD_WORD_RE(단어경계)로 이설. 여기 남은 항목은 오탐 위험이 낮은 것만.
    "not ", "no ", "none", "death", "dead", "evil", "bad", "ugly",
    "sick", "disease", "slave", "stupid", "fool", "poor", "lowly", "mourn",
    "corpse", "demon", "ghost", "devil", "thief", "criminal", "lazy", "wicked",
    # 실측(怠=게으를 태): 'lazy'만 있어 idle/negligent/remiss 가 통과했다. 동의어 보강.
    "idle", "negligent", "remiss", "indolent", "slack", "neglect",
    "curse", "blame", "angry", "fear", "weep", "cry", "dirty", "rotten", "waste",
    "weed", "overgrown", "oak", "hemp", "barren", "withered", "decay", "stink",
    "humble", "vulgar", "coarse", "wild grass", "thorn", "swamp", "mud", "dung",
    "(same as", "non-classical", "variant", "old form", "dialect", "surname",
    # 후보 확장(자원오행 보강)으로 새로 유입되는 의미 약한 글자 차단(부분문자열 충돌 회피)
    "entice", "lure", "seduce", "scheme", "plot", "conspire", "deceiv", "cheat",
    "tooth", "molar", "tusk", "fang", "beggar", "prison", "punish", "fight",
    "warfare", "weapon", "drunk", "vomit", "feces", "worm", "insect", "snake",
    "louse", "tomb", "kneel", "spy", "robber", "slaughter",
    # 대명사·관직·재물·술 등 이름에 부적합한 채움자(특정 어휘로 충돌 회피): 我吾 吏 貨 酒酉
    "i, me", "i, my", "magistrate", "commodit", "wine", "liquor",
    # ※ 사용성 테스트 발굴분(도박/무기/시험/도피 등)은 substring 오탐(present⊃resent, narrow⊃arrow,
    #   'examine, test'⊃test)으로 우량 인명자(博·飛·獻·考·逸 등)를 오배제 → 단어경계 매칭 _BAD_WORD_RE 로 분리(아래).
)
# 부적합 의미 '단어' 차단 — 단어경계(\b)로 매칭해 present/narrow/represent 등 substring 오탐 없이.
#  gamble/dart/test/escape 등은 賭/矢/試/逃 처럼 우량자(博/飛/考/逸)와 뜻을 공유해 정의로는 구분 불가 →
#  그 특정 글자는 아래 _BAD_CHARS(코드포인트 직접차단)로만 처리하고, 여기선 충돌 없는 부정어만.
_BAD_WORD_RE = re.compile(
    r"\b(?:hatred|resent|enmity|dislike|grief|grieve|melancholy|sorrow|distress|"
    r"wager|arrow|particle|abscond|dodge|talkative|quarrel|"
    r"end|die|ill|kill|sword|knife|dagger|blade)\b"
)
# 영문 정의가 중립·긍정으로 보이나 한국 인명에 부적합한 글자(정의 필터를 우회) — 코드포인트로 직접 차단.
#  到(도착)·右(방위)·賭(도박)·矢(화살)·試(시험)·逃(도피) 등은 뜻이 나쁘거나 이름자로 부적합.
# 鍍(도금): 벽자(D3) 하드차단. + 실측 유출(耳귀·油기름·而말이을·夷오랑캐·偶짝·駘둔한말·挑돋울·
# 徒무리·態모양·孟맏·嘸·沛·溥·嘸): 상용이라 뜻 blocklist를 통과하던 비(非)이름 글자 — 폴백 풀 방어.
_BAD_CHARS = frozenset("到右矢賭試恨怨憂誰呀逃倒叨忉鍍耳油而夷偶駘挑徒態孟嘸沛溥只")
_GOOD_HINT = (
    "bright", "clear", "beautiful", "wise", "virtue", "noble", "talent", "elegant",
    "auspicious", "lucky", "prosper", "abundant", "gem", "jade", "pure", "gentle",
    "brave", "strong", "great", "flourish", "shine", "light", "good", "joy", "peace",
    "grow", "rise", "honor", "grace", "refined", "excellent", "harmon",
)


def _good_count(given: str) -> int:
    """이름(한자)에 '좋은 뜻'(_GOOD_HINT) 글자 개수(0~2) — 동점 재랭킹 가산용."""
    return sum(
        1 for c in (given or "")
        if any(g in (_hanja().get(c, {}).get("defn") or "").lower() for g in _GOOD_HINT)
    )


def _filler_count(given: str) -> int:
    """상용(교육용)도 아니고 '좋은 뜻'도 아닌 순수 채움자(벽자, 예 鍍 '도금') 개수 — 추천 하위로 밀기 위한 감점용.
    부족오행에 마땅한 상용·길자가 적을 때 인기 음절만 맞아 상위에 오는 벽자를 억제한다(인명용한자 화이트리스트 도입 전 완화책)."""
    hj = _hanja()
    return sum(
        1 for c in (given or "")
        if not _is_common(c)
        and not any(g in (hj.get(c, {}).get("defn") or "").lower() for g in _GOOD_HINT)
    )


def _candidate_pool(target: str, limit: int = 90, good_only: bool = False) -> list[str]:
    """자원오행==target, 이름에 적합한 뜻을 가진 한자 풀.

    good_only=True(추천용): '좋은 뜻' 글자만. 풀이 너무 적으면(<24) 중립글자로 보충.
    """
    good, neutral = [], []
    for ch, info in _hanja().items():
        if _char_element(ch) != target:
            continue
        st = info.get("strokes") or 0
        defn = (info.get("defn") or "").lower()
        if not (2 <= st <= 18) or not defn:
            continue
        if any(b in defn for b in _BAD_DEFN) or _BAD_WORD_RE.search(defn):
            continue
        if ch in _BAD_CHARS:
            continue
        # 상용 한자(교육용 기초한자) 우선 → 같은 뜻·획수면 친숙한 글자가 앞에 오게 (0=상용)
        rank = (0 if _is_common(ch) else 1, st)
        (good if any(g in defn for g in _GOOD_HINT) else neutral).append((rank, ch))
    good.sort(); neutral.sort()
    if good_only:
        pool = good if len(good) >= 24 else good + neutral
    else:
        pool = good + neutral
    return [c for _, c in pool[:limit]]


_NAME_HANJA_PATH = Path(__file__).resolve().parents[3] / "data" / "naming" / "name_hanja.json"


@lru_cache(maxsize=1)
def _name_hanja() -> dict:
    """실제 한국 이름에 쓰이는 한자 allowlist(data/naming/name_hanja.json). 없으면 빈 dict(폴백)."""
    try:
        return json.loads(_NAME_HANJA_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 파일 부재 시 기존 인기풀로 폴백
        return {}


def _name_hanja_pool(element: str, gender: str, limit: int = 60) -> list[str]:
    """★ 이름 한자 allowlist 풀 — 실제 이름에 쓰는 한자 중 자원오행==element (2026-07-10).

    근본 해결: 종전엔 blocklist(_BAD_DEFN·_BAD_CHARS)로 나쁜 글자를 막으려 했으나 구멍이 무한해
    耳(귀)·油(기름)·而(말이을)·夷(오랑캐)·怠(게으를) 같은 글자가 계속 새어 이름에 올라왔다
    (전부 상용한자라 통과). allowlist로 뒤집어 '실제 이름에 쓰는 한자'에서만 후보를 만든다."""
    data = _name_hanja()
    syl_map = data.get("syllables") or {}
    allowed = data.get("female" if "female" in str(gender).lower() else "male") or []
    if not syl_map or not allowed:
        return []
    key = "female" if "female" in str(gender).lower() else "male"
    weights = _popular().get(key, {})
    h = _hanja()
    out: list[tuple[int, int, int, str]] = []
    for syl in allowed:
        for ch in syl_map.get(syl, ""):
            if ch not in h or _char_element(ch) != element:
                continue
            st = h[ch].get("strokes") or 0
            if not (2 <= st <= 18):
                continue
            defn = (h[ch].get("defn") or "").lower()
            good = 1 if any(g in defn for g in _GOOD_HINT) else 0
            out.append((good, weights.get(syl, 0), st, ch))
    out.sort(key=lambda x: (-x[0], -x[1], x[2]))   # 좋은뜻↓ → 인기음절↓ → 획수↑
    return [c for *_, c in out[:limit]]


def _name_hanja_pool_any(gender: str, limit: int = 120) -> list[str]:
    """오행 무관 이름 한자 allowlist 전체(인기음절·좋은뜻 순).

    부족오행이 1개뿐이면 _naming_targets 의 자원 목표가 단일 오행으로 collapse 돼, 종전엔 이름 두
    글자를 모두 그 오행 부수로 강제했다 → 木 부수 이름한자는 23자(17음절)뿐이라 준·호·윤 같은 인기
    음절이 구조적으로 불가능, 素祉(소지)·祉桃(지도)·荷芝(하지)만 남았다(전문가 격노 실측).
    전문가 결정(2026-07-12): **한 글자만 부족오행 보완, 나머지는 자연스러운 이름 음절**. 이때
    둘째 글자를 오행 필터 없이 이 풀에서 뽑는다(첫 글자는 여전히 부족오행 → 자원 보완 1자 유지)."""
    data = _name_hanja()
    syl_map = data.get("syllables") or {}
    key = "female" if "female" in str(gender).lower() else "male"
    allowed = data.get(key) or []
    if not syl_map or not allowed:
        return []
    weights = _popular().get(key, {})
    h = _hanja()
    out: list[tuple[int, int, int, str]] = []
    for syl in allowed:
        for ch in syl_map.get(syl, ""):
            if ch not in h:
                continue
            st = h[ch].get("strokes") or 0
            if not (2 <= st <= 18):
                continue
            defn = (h[ch].get("defn") or "").lower()
            good = 1 if any(g in defn for g in _GOOD_HINT) else 0
            out.append((good, weights.get(syl, 0), st, ch))
    out.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return [c for *_, c in out[:limit]]


def _popular_hanja_pool(element: str, gender: str, limit: int = 40) -> list[str]:
    """target 오행이면서 읽기가 '인기 이름 음절'인 한자 풀(인기도 높은 순).

    기존 사전(8천여 자)에서 도·서·준·윤 등 현대 인기 음절로 읽히는 한자를 뽑아
    작명 후보 앞쪽에 배치 → 도윤·서준처럼 현대적으로 읽히는 이름을 만든다.
    뜻이 나쁜 글자(_BAD_DEFN)는 제외하되, 평범한 뜻도 허용(현대 이름은 음 위주).
    """
    key = "female" if "female" in str(gender).lower() else "male"
    weights = _popular().get(key, {})
    out: list[tuple[int, int, int, str]] = []
    for ch, info in _hanja().items():
        if _char_element(ch) != element:
            continue
        st = info.get("strokes") or 0
        defn = (info.get("defn") or "").lower()
        if not (2 <= st <= 18) or not defn:
            continue
        if any(b in defn for b in _BAD_DEFN) or _BAD_WORD_RE.search(defn):
            continue
        if ch in _BAD_CHARS:
            continue
        # 벽자(비상용·비길자) 제외(D3) — 인기음절만 맞는 도금(鍍) 류가 추천 앞자리에 오는 것 근본 차단.
        if not _is_common(ch) and not any(g in defn for g in _GOOD_HINT):
            continue
        w = weights.get(_reading(ch), 0)
        if w > 0:
            # 좋은 뜻(_GOOD_HINT) 글자를 최우선 — 상용이라도 뜻이 밋밋/부정적인 글자(徒·態)가
            # 앞자리를 차지하는 것을 구조적으로 억제(실측 徒稻·態稻).
            good = 1 if any(g in defn for g in _GOOD_HINT) else 0
            out.append((good, 1 if _is_common(ch) else 0, w, st, ch))
    # 좋은뜻↓ → 상용여부↓ → 인기도↓ → 획수↑ : 같은 음이면 뜻 좋고 친숙한 글자를 앞에
    out.sort(key=lambda x: (-x[0], -x[1], -x[2], x[3]))
    return [c for *_, c in out[:limit]]


def recommend_names(
    surname: str, chart: SajuChart, count: int = 2, top: int = 40, gender: str = "male",
    fixed_char: str | None = None, fixed_pos: int = 1,
) -> list[NameCandidate]:
    """작명/아호 추천 — 사주 부족오행 보완 + 길한 81수 조합. 점수→인기도 순 상위 N.

    점수(오행 보완·수리)는 그대로 두고, 동점 후보는 **인기 이름 음절(대법원/네임차트 통계)**
    가중치로 재랭킹해 도윤·서준처럼 현대적으로 읽히는 이름을 우선 노출한다(성별 반영).
    선택지가 좁지 않게 충분히(기본 40개) 반환(프론트 '더 보기'로 단계 노출).

    count: 이름 글자 수. 2=두 자 이름(구○○), 1=외자 이름(구본式). 외자는 _four_pillars가
      허수 1 보정으로 4격을 계산한다(성명학 표준).
    fixed_char/fixed_pos: 돌림자(항렬자) 고정. fixed_char(한자 1자)가 주어지면 이름 count==2에서
      그 글자를 fixed_pos(0=성 다음 앞자리, 1=끝자리)에 고정하고 **나머지 한 자만** 부족오행·수리로
      최적화한다(예: 구+本+○ 또는 구+○+本). count==1(외자)엔 적용 안 함(고정=생성 여지 없음).
    """
    fixed_char = (fixed_char or "").strip() or None
    if count <= 1:
        fixed_char = None          # 외자엔 돌림자 고정 무의미(단일 글자가 곧 고정)
    fixed_pos = 0 if fixed_pos == 0 else 1
    baleum_t, jawon_t = _naming_targets(chart)   # 발음=부족(비겁제외), 자원=부족+신약시 비겁
    targets = jawon_t                            # 자원(한자) 후보 생성·점수 기준(신약이면 비겁 포함)
    primary = targets[0]
    base = _candidate_pool(primary, good_only=True)
    if not base:
        return []
    sec_target = targets[1] if len(targets) > 1 else primary
    sec_base = _candidate_pool(sec_target, good_only=False) or base
    # ★ 이름 품질 하드 게이트(2026-07-10, 전문가 격노 '공맹·무무·방맹' 실측):
    #   종전엔 인기음절 한자를 풀 '앞쪽'에만 놓고 전체풀도 함께 조합했다. 이름 품질(상용·인기·좋은뜻)이
    #   정렬의 **동점 tiebreaker**에 불과해, 점수(오행·수리)가 조금이라도 분화되는 순간 오행만 맞는
    #   기괴한 이름(功孟·茂嘸·芳孟)이 1위로 올라왔다 — 이게 '고쳐도 재발'의 구조적 원인.
    #   → 후보 생성 자체를 '인기 이름 음절 한자'로 **제한**한다(게이트). 오행·수리는 그 안에서 최적화.
    #   게이트로 후보가 안 나오는 사주에서만 단계적으로 넓힌다(아래 폴백).
    #  1순위: 이름 한자 allowlist(실제 이름에 쓰는 글자) → 2순위: 인기음절 풀 → 3순위: 전체 풀
    pp = _name_hanja_pool(primary, gender) or _popular_hanja_pool(primary, gender)
    # ★ 단일 부족오행 붕괴 차단(전문가 결정 2026-07-12): 부족오행이 1개면 둘째 글자는 오행 강제
    #   없이 '자연스러운 이름 음절' allowlist 전체에서 뽑는다(첫 글자만 그 오행 → 자원 보완 1자 유지).
    #   종전엔 둘 다 그 오행이라 木 23자로 붕괴 → 소지·지도·하지 실측. 다중 부족이면 종전대로.
    if len(jawon_t) == 1:
        sp = _name_hanja_pool_any(gender)
    else:
        sp = _name_hanja_pool(sec_target, gender) or _popular_hanja_pool(sec_target, gender)
    pool = pp or base
    secondary = sp or sec_base

    def _make_cand(given: str) -> NameCandidate:
        fp = _four_pillars(surname or "", given)
        factors = {
            "suri": _score_suri(fp),
            "jawon": _score_jawon(given, jawon_t),
            "baleum": _score_baleum(surname or "", given, baleum_t),
            "eumyang": _score_eumyang(surname or "", given),
        }
        total = _perspectives(factors)["B"].total
        return NameCandidate(
            given=given,
            reading="".join(_reading(c) for c in given),
            score=total,
            suri_grade="·".join(v["grade"] for v in fp.values()),
            elements=[WUXING_KOREAN.get(_char_element(c) or "", "불명") for c in given],   # 자원오행(부수)
            baleum_elements=[WUXING_KOREAN.get(_chosung_element(_reading(c)) or "", "불명")  # 발음오행(초성)
                             for c in given],
            # 한국어 훈음('보배 진') 우선 — 없으면 영어 defn 폴백. 화면에 뜻+음 표시.
            meaning=" / ".join(
                (hun_of(c) or (_hanja().get(c, {}).get("defn", "")[:40])) for c in given),
            hun=[hun_of(c) for c in given],
        )

    def _gen(p1: list[str], p2: list[str]) -> list[NameCandidate]:
        out: list[NameCandidate] = []
        seen: set[str] = set()
        for c1 in p1[:60]:
            for c2 in p2[:90]:
                if c1 == c2:
                    continue
                # 같은 음절 반복 금지(民敏=민민, 徒稻=도도 실측) — 한국 이름으로 쓰지 않는다.
                if _reading(c1) == _reading(c2):
                    continue
                given = c1 + c2
                if given in seen:
                    continue
                seen.add(given)
                out.append(_make_cand(given))
        return out

    def _gen_single(p: list[str]) -> list[NameCandidate]:
        """외자 이름(count==1) — 성 + 한 글자. 4격은 _four_pillars가 허수 1로 보정한다."""
        out: list[NameCandidate] = []
        seen: set[str] = set()
        for c in p[:150]:
            if not c or c in seen:
                continue
            seen.add(c)
            out.append(_make_cand(c))
        return out

    def _gen_fixed(free_pool: list[str]) -> list[NameCandidate]:
        """돌림자 고정(count==2) — fixed_char를 fixed_pos에 두고 나머지 한 자만 생성."""
        out: list[NameCandidate] = []
        seen: set[str] = set()
        fr = _reading(fixed_char)
        for f in free_pool[:200]:
            if not f or f == fixed_char or _reading(f) == fr:   # 같은 글자·같은 음절 반복 금지
                continue
            given = (fixed_char + f) if fixed_pos == 0 else (f + fixed_char)
            if given in seen:
                continue
            seen.add(given)
            out.append(_make_cand(given))
        return out

    if count <= 1:
        # 외자 이름 — 성 + 한 글자. 부족오행 primary 풀 우선, 없으면 단계적 완화.
        cands = (_gen_single(pool)
                 or _gen_single(pp + [c for c in base if c not in set(pp)])
                 or _gen_single(base))
    elif fixed_char:
        # 돌림자 고정 — 자유 자리는 부족오행을 최대한 채우게 primary+secondary 풀 합집합에서 점수로 랭킹.
        free = pool + [c for c in secondary if c not in set(pool)]
        cands = (_gen_fixed(free)
                 or _gen_fixed(pp + sp + [c for c in base if c not in set(pp)])
                 or _gen_fixed(base))
    else:
        cands = _gen(pool, secondary)
        if not cands:   # 게이트로 후보 0 → 단계적 완화(인기풀 + 전체풀). 실제 이름 우선은 정렬이 유지.
            cands = _gen(pp + [c for c in base if c not in set(pp)],
                         sp + [c for c in sec_base if c not in set(sp)])
    # [2026-07-10 전문가 결정] '자연스러운 인기 이름 우선'. 정렬 구조를 뒤집는다.
    #   종전: (점수, 이름품질) — 품질이 동점 tiebreaker라 점수가 분화되면 무력화(공맹·명범·민강 실측).
    #   현재: ① 수리(81수) 4격에 '흉' 없는 후보만 남기고(길격 하드 보장)
    #         ② 자연스러움(실제 인기 이름 ≫ 인기 음절 > 좋은 뜻 > 친숙 글자)을 **1순위**로
    #         ③ 오행 점수(자원·발음 포함)는 **2순위** 동점 정렬.
    #   자원오행 보완은 후보 풀이 목표 오행 글자로만 구성돼 이미 구조적으로 만족된다.
    _pen = _dated()[1]
    _clean = [c for c in cands if "흉" not in c.suri_grade] or cands   # 길격 보장(없으면 폴백)

    def _natural(x) -> int:
        return (
            1000 * _is_top_name(x.reading, gender)   # 실제 인기 이름(예준·서준·지호) 압도적 1순위
            + 10 * _popularity(x.reading, gender)    # 인기 음절 가중치 합
            + 5 * _good_count(x.given)               # 좋은 뜻
            + 3 * _common_count(x.given)             # 친숙한 글자
            - 200 * _filler_count(x.given)           # 벽자 강한 감점
            - _pen * _dated_count(x.reading)         # 촌스러운 음절(봉·숙·자…) 강한 감점
            - 30 * x.suri_grade.count("흉")          # 흉격 감점 — 외자/폴백에서 수리 나쁜 이름을 뒤로
        )                                            #   (2자 정상경로는 _clean이 흉을 이미 제거 → 영향 0)

    cands = _clean
    cands.sort(
        key=lambda x: (
            _natural(x),   # 1순위: 자연스러운 인기 이름
            x.score,       # 2순위: 오행·수리 점수(발음오행은 참고 수준 가중치)
        ),
        reverse=True,
    )
    # ★ 중복 제거(전문가 지적 '지도↔도지·하지↔지하'): 같은 발음(荷準/荷埈=하준)이나 같은 글자쌍을
    #   순서만 바꾼 것(桃秀/秀桃=도수/수도)은 최상위 랭크 1개만 노출. 종전 seen 집합은 한자 표기가
    #   다르면 통과시켜(83% 사주에서 상위 중복) 같은 이름이 두 번 보였다.
    out: list[NameCandidate] = []
    seen_reading: set[str] = set()
    seen_charset: set = set()
    for c in cands:
        cs = frozenset(c.given)
        if c.reading in seen_reading or cs in seen_charset:
            continue
        seen_reading.add(c.reading)
        seen_charset.add(cs)
        out.append(c)
        if len(out) >= top:
            break
    return out


# ============================================================
# 아호(雅號) 전용 — 신생아 작명 엔진과 완전히 분리
# ============================================================
# [P4 2026-07-22] 종전 아호는 recommend_names 를 그대로 쓰고 성(姓)만 빈 문자열로 두었다
# (tool_service.py 의 단 한 줄 차이). 그런데 이 엔진은 후보를 **실제 아기 이름 allowlist**로
# 하드 게이트하고(_name_hanja_pool) 2024 신생아 Top30 에 1000점을 준다(_is_top_name).
# 결과: 라이브 아호 세션 15건의 1순위가 전부 시우·하준·유준·지호·서윤·서지였다.
# AHO_SYSTEM 이 "신생아처럼 쓰지 마세요"라고 지시해도 **표 자체가 신생아 이름이라** 못 고친다.
# → 아호 전용 글자 풀에서만 조합한다. recommend_names 는 한 줄도 건드리지 않아 작명·개명 회귀 0.
#
# 수리 81수 4격은 아호에 쓰지 않는다(운영자 결정 2026-07-22):
#   4격은 성+이름 구조를 전제하는데 아호는 성이 없어 원격==정격으로 축퇴한다 —
#   라이브 15건이 전부 '길·길·길·길'로 정보량이 0이었다. 전통 작호에 81수를 적용한 근거도
#   고전에 없고(현대 성명학) 프롬프트에서도 4격 서술을 뺀다.
#
# ⛔⛔ 승인 없이 수정 금지 — 아래를 되돌리면 아호에 신생아 이름이 다시 나옵니다 ⛔⛔
#   · recommend_aho 를 recommend_names 로 되돌리는 것: **금지**. 그게 이 코드가 생긴 이유다.
#   · 아호에 수리 81수·4격을 넣는 것: **금지**(운영자 결정 2026-07-22). 성이 없어 축퇴한다.
#   · aho_lexicon.json 의 독음·획수·자원오행을 손으로 고치는 것: **금지**. 사전 산출값이다.
#   · _AHO_BAD_READING 를 '불필요해 보인다'며 지우는 것: **금지**. 국자·창자·서자가 다시 나온다.
#   바꾸려면 docs/rag_hallucination_audit_2026-07-22.md 5장을 읽고 운영자 승인을 받을 것.
#   테스트: backend/tests/test_aho_engine.py (10건) — 테스트만 지우고 코드를 바꾸지 말 것.
#
_AHO_LEXICON_PATH = Path(__file__).resolve().parents[3] / "data" / "naming" / "aho_lexicon.json"
_AHO_TYPES_PATH = Path(__file__).resolve().parents[3] / "data" / "naming" / "aho_types.json"
_AHO_EXAMPLES_PATH = Path(__file__).resolve().parents[3] / "data" / "naming" / "aho_examples.json"


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 데이터 부재 시 호출부가 빈 결과로 폴백
        return {}


@lru_cache(maxsize=1)
def aho_lexicon() -> list[dict]:
    """아호 글자 풀. 독음·획수·자원오행은 생성 시 사전에서 산출해 박아 둔 값이다."""
    return _load_json(_AHO_LEXICON_PATH).get("chars") or []


@lru_cache(maxsize=1)
def aho_types() -> dict:
    return _load_json(_AHO_TYPES_PATH)


@lru_cache(maxsize=1)
def aho_examples() -> list[dict]:
    return _load_json(_AHO_EXAMPLES_PATH).get("examples") or []


@lru_cache(maxsize=1)
def _aho_group_type() -> dict[str, str]:
    """글자 group → 작호 유형 code. 결정적 매핑(LLM 판단 금지)."""
    out: dict[str, str] = {}
    for t in (aho_types().get("types") or []):
        for g in (t.get("groups") or []):
            out[g] = t["code"]
    return out


def aho_type_label(code: str | None) -> str:
    for t in (aho_types().get("types") or []):
        if t.get("code") == code:
            return f"{t.get('name_ko','')}({t.get('name_hanja','')})"
    return ""


@lru_cache(maxsize=1)
def _aho_attested_suffixes() -> frozenset[str]:
    """실존 **2자 호**에서 뒷자리에 쓰인 한자 집합.

    ⛔길이 조건을 빼지 마세요 — 3~4자 호의 마지막 글자는 접미가 아닙니다.
      백운거사(白雲居士)에서 '士'만 떼면 居士가 한 단위인 걸 무시하는 것이고,
      그 결과 士가 +20 가산을 받아 **목사·석사·동사·정사·상사** 같은 조합이
      후보표 상단을 점거했다(감수 재확인 2026-07-22 실측).
      여유당(與猶堂)의 堂도 같은 이유로 제외된다.
    """
    return frozenset(
        h[-1] for e in aho_examples()
        if (h := (e.get("hanja") or "")) and len(h) == 2
    )


# 아호 독음이 일상어와 겹치면 유료 리포트에 올릴 수 없다 — 작명 엔진이 '공맹·무무·방맹'으로
# 겪은 것과 같은 종류의 사고다.
#
# ⚠️[감수 재확인 2026-07-22] 이 방식의 한계가 실측으로 드러났다.
#   · 현재 글자 풀로 만들 수 있는 독음은 **1,824가지**다. 손으로 나열해 막는 방식은 원리상
#     따라갈 수 없다 — 1차 목록 61개 중 **48개는 생성조차 불가능한 허수**였고, 반대로
#     중풍(中風)·사악(沙岳)·야옹·목사·동사(凍死) 같은 위험 조합 **67개가 뚫려 있었다**.
#   · 아래 목록은 그 67개를 메우고 허수 대신 '접미 子 복원 대비 방어선'으로 정리한 것이지만,
#     **여전히 완전하지 않다.** 글자를 풀에 추가하면 충돌이 다시 생기므로 반드시 전 조합을
#     재검사할 것(1,824가지는 전수 열거가 가능한 규모다).
#   · 근본 해법은 '나쁜 독음 목록'이 아니라 **'국어사전 표제어면 배제'**인데 저장소에 한국어
#     사전 데이터가 없다 → 운영자 결정 대기.
#   · 반대로 靑山·白露·中山은 부정적 동음어가 없어 **차단을 풀었다**(표준국어대사전 확인).
_AHO_BAD_READING = frozenset({
    # ── 질병·죽음·비속 연상(가장 위험) ──
    "중풍", "사악", "야옹", "노루", "암담", "난산", "동사", "설사", "상해", "추악",
    "악운", "악성", "암초", "암호", "야설", "야호", "초상", "중상", "심각",
    # ── 감정·사건 일상어 ──
    "우산", "상심", "심란", "심야", "춘심", "추심", "야심", "백해", "고사", "난사",
    "정사", "동정", "사정", "매정", "강도", "매도", "추도", "설정", "하야", "중매",
    # ── 직업·학위·사무 ──
    "목사", "석사", "상사", "송사", "노사", "심사", "설계", "해설", "연설", "운송",
    "연봉", "일상", "일정", "일당", "성당", "현재", "중심", "청각", "목성",
    # ── 사물·고유명사 ──
    "중국", "계란", "양초", "단추", "남매", "남성", "해초", "목재", "목석", "산란",
    "난국", "백성", "북송", "호송", "운석", "우매", "하천", "추석", "단풍",
    # ── 접미 子 계열(현재 子는 풀에서 빠졌지만 되살릴 때를 대비한 방어선) ──
    "국자", "창자", "노자", "성자", "주자", "감자", "모자", "부자", "사자", "자자",
    "구자", "동자", "선자", "무자", "미자", "소자", "이자", "장자", "일자", "월자",
    "산자", "석자", "심자", "정자", "해자", "화자", "가자", "고자", "간자", "남자",
    "여자", "서자", "단자", "단지",
})


class AhoCandidate(BaseModel):
    given: str                      # 아호(한자 2자)
    reading: str                    # 한글 독음
    score: int
    elements: list[str]             # 자원오행 — 부수표 미매핑이면 '불명'
    baleum_elements: list[str]      # 발음오행(초성)
    meaning: str                    # 두 글자의 짧은 뜻
    aho_type: str                   # 작호 유형 code
    strokes: list[int]              # 글자별 획수(참고 표시용)


def recommend_aho(chart: SajuChart, top: int = 12) -> list[AhoCandidate]:
    """아호 후보 — 아호 전용 글자 풀에서 '앞자 + 뒷자' 2자 조합. 부족 오행 보완 순.

    수리 81수는 쓰지 않는다(위 주석 참조). 점수는 ①자원오행이 부족오행을 채우는가
    ②발음오행이 부족오행과 맞는가 ③유형이 뚜렷한가로만 매긴다.
    """
    lex = aho_lexicon()
    if not lex:
        return []
    baleum_t, jawon_t = _naming_targets(chart)
    g2t = _aho_group_type()
    heads = [c for c in lex if c["role"] in ("head", "both")]
    tails = [c for c in lex if c["role"] in ("suffix", "both")]

    out: list[AhoCandidate] = []
    seen: set[str] = set()
    for a in heads:
        for b in tails:
            if a["char"] == b["char"]:
                continue
            given = a["char"] + b["char"]
            if given in seen:
                continue
            # ⛔두음법칙 — 露·蓮·蘭·樓 는 앞자리와 뒷자리 독음이 다르다. 고정 독음을 쓰면
            #   蓮露 를 '련노'로 적는다(정답 '연로'). 蓮 은 **발음오행까지 바뀐다**
            #   (연=土 / 련=火) — 표기 사고에 그치지 않고 판정 근거가 틀어진다.
            #   reading_tail 이 없는 옛 데이터는 reading 으로 폴백한다.
            reading = (a["reading"] or "") + (b.get("reading_tail") or b["reading"] or "")
            if not reading or len(reading) != 2:
                continue          # 독음 미상 글자는 후보에서 제외(표기 사고 방지)
            els = [a["element"] or "불명", b["element"] or "불명"]
            bal = [_chosung_element(reading[0]) or "불명", _chosung_element(reading[1]) or "불명"]
            # 점수: 자원오행이 목표를 채운 글자 수 ×30, 발음오행 일치 ×8,
            #       유형이 서로 다른 두 group 이면 조합이 밋밋하지 않아 소폭 가산.
            if reading in _AHO_BAD_READING:
                continue          # 일상어와 동음 — 유료 리포트에 올릴 수 없다
            sc = 30 * sum(1 for e in els if e in jawon_t)
            sc += 8 * sum(1 for e in bal if e in baleum_t)
            sc += 5 if a["group"] != b["group"] else 0
            sc -= 12 * sum(1 for e in els if e == "불명")   # 불명은 근거가 약하니 약한 감점(배제는 아님)
            # 실존 호에서 실제로 쓰인 접미(퇴계의 溪, 화담의 潭, 다산의 山, 여유당의 堂,
            # 삼은의 隱…)를 우대한다. 근거 있는 형태가 먼저 보이게 하려는 것이다.
            if b["char"] in _aho_attested_suffixes():
                sc += 20
            # 유형: 뒷자(접미)가 성격을 정하는 경우가 많아 뒷자 group 우선.
            code = g2t.get(b["group"]) or g2t.get(a["group"]) or ""
            out.append(AhoCandidate(
                given=given, reading=reading, score=sc, elements=els, baleum_elements=bal,
                meaning=f"{a['gloss_ko']} + {b['gloss_ko']}",
                aho_type=code,
                strokes=[a.get("strokes") or 0, b.get("strokes") or 0],
            ))
            seen.add(given)
    # 유형이 한쪽으로 쏠리지 않게 상위에서 유형별로 고르게 뽑는다(라운드로빈).
    out.sort(key=lambda x: (x.score, -len(x.given)), reverse=True)
    by_type: dict[str, list[AhoCandidate]] = {}
    for c in out:
        by_type.setdefault(c.aho_type, []).append(c)
    picked: list[AhoCandidate] = []
    used: dict[str, int] = {}
    _MAX_PER_CHAR = 2       # 한 글자가 후보표를 독식하지 못하게
    for limit in (_MAX_PER_CHAR, 99):    # 1차는 반복 제한, 못 채우면 완화해 재시도
        pools = {k: list(v) for k, v in by_type.items()}
        while len(picked) < top:
            progressed = False
            for code in list(pools):
                while pools[code]:
                    c = pools[code].pop(0)
                    if any(p.given == c.given for p in picked):
                        continue
                    # 한자가 달라도 **읽으면 같은 이름**이면 표에 나란히 둘 수 없다
                    # (실측 東溪(동계)·東桂(동계) — 40건 중 1건 발생).
                    if any(p.reading == c.reading for p in picked):
                        continue
                    if max(used.get(c.given[0], 0), used.get(c.given[1], 0)) >= limit:
                        continue
                    picked.append(c)
                    used[c.given[0]] = used.get(c.given[0], 0) + 1
                    used[c.given[1]] = used.get(c.given[1], 0) + 1
                    progressed = True
                    break
                if len(picked) >= top:
                    break
            if not progressed:
                break
        if len(picked) >= top:
            break
    return picked
