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
    "임": ["林", "任"], "한": ["韓"], "오": ["吳"], "서": ["徐"], "신": ["申", "辛", "愼"],
    "권": ["權"], "황": ["黃"], "안": ["安"], "송": ["宋"], "전": ["全", "田"], "홍": ["洪"],
    "유": ["柳", "劉", "兪"], "고": ["高"], "문": ["文"], "양": ["梁", "楊"], "손": ["孫"],
    "배": ["裵"], "백": ["白"], "허": ["許"], "남": ["南"], "심": ["沈"], "하": ["河"],
    "곽": ["郭"], "성": ["成"], "차": ["車"], "주": ["朱", "周"], "우": ["禹"], "구": ["具", "丘"],
    "나": ["羅"], "민": ["閔"], "진": ["陳", "秦", "晉"], "지": ["池"], "엄": ["嚴"], "채": ["蔡"],
    "원": ["元", "袁"], "천": ["千"], "방": ["方"], "공": ["孔"], "현": ["玄"], "함": ["咸"],
    "변": ["卞", "邊"], "노": ["盧"], "여": ["呂", "余"], "추": ["秋"], "도": ["都"], "석": ["石"],
    "설": ["薛"], "선": ["宣"], "마": ["馬"], "길": ["吉"], "연": ["延"], "위": ["魏"], "표": ["表"],
    "명": ["明"], "기": ["奇"], "반": ["潘"], "왕": ["王"], "금": ["琴", "金"], "옥": ["玉"], "육": ["陸"],
    "인": ["印"], "맹": ["孟"], "제": ["諸"], "모": ["牟"], "탁": ["卓"], "국": ["鞠"], "어": ["魚"],
    "라": ["羅"], "노": ["盧", "魯"], "양": ["梁", "楊", "樑"], "임": ["林", "任"],
    "은": ["殷"], "편": ["片"], "용": ["龍"], "예": ["芮"], "경": ["慶", "景"], "봉": ["奉"],
    "사": ["史"], "부": ["夫"], "가": ["賈"], "복": ["卜"], "태": ["太"], "피": ["皮"], "두": ["杜"],
    "감": ["甘"], "음": ["陰"], "빈": ["賓"], "동": ["董"], "온": ["溫"], "경": ["慶"],
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
        out.append({"char": han, "strokes": strokes, "defn": defn,
                    "is_surname": True, "is_compound": len(han) > 1})
    return out


def lookup_by_reading(reading: str, surname_first: bool = True, limit: int = 24) -> list[dict]:
    """한글 음(예 '이')에 해당하는 한자 후보 목록. 성씨 한자 우선."""
    reading = (reading or "").strip()
    if not reading:
        return []
    rows = []
    for ch, info in _hanja().items():
        if reading in (info.get("ko") or []):
            rows.append((ch, info))

    def _key(t):
        ch, info = t
        is_sur = surname_first and ch in _SURNAME_HANJA
        return (0 if is_sur else 1, info.get("strokes") or 99)

    rows.sort(key=_key)
    return [
        {"char": ch, "strokes": info.get("strokes"),
         "defn": (info.get("defn") or "")[:60],
         "is_surname": ch in _SURNAME_HANJA}
        for ch, info in rows[:limit]
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


def _reading(ch: str) -> str:
    info = _hanja().get(ch)
    return (info.get("ko") or [""])[0] if info else ""


# ── 81수리 길흉 (표준 분류; v1) ───────────────────────────────
_SURI_GOOD = {1, 3, 5, 6, 7, 8, 11, 13, 15, 16, 17, 18, 21, 23, 24, 25, 29, 31, 32, 33,
              35, 37, 39, 41, 45, 47, 48, 52, 57, 61, 63, 65, 67, 68, 81}
_SURI_BAD = {2, 4, 9, 10, 12, 14, 19, 20, 22, 26, 27, 28, 30, 34, 36, 40, 42, 43, 44, 46,
             49, 50, 51, 53, 54, 55, 56, 58, 59, 60, 62, 64, 66, 69, 70, 71, 72, 73, 74,
             75, 76, 77, 78, 79, 80}


def _suri_grade(n: int) -> str:
    n = ((n - 1) % 81) + 1 if n > 81 else n
    if n in _SURI_GOOD:
        return "길"
    if n in _SURI_BAD:
        return "흉"
    return "평"


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


class NameCandidate(BaseModel):
    given: str                      # 이름(한자)
    reading: str
    score: int
    suri_grade: str
    elements: list[str]             # 자원오행
    meaning: str


# 다관법 가중치 (합 100). 수리/오행/발음 강조 차이.
PERSPECTIVES = {
    "S": {"label": "수리 중시", "weights": {"suri": 45, "jawon": 20, "baleum": 20, "eumyang": 15}},
    "B": {"label": "균형", "weights": {"suri": 30, "jawon": 30, "baleum": 25, "eumyang": 15}},
    "O": {"label": "사주보완 중시", "weights": {"suri": 22, "jawon": 45, "baleum": 23, "eumyang": 10}},
}


def _deficient_elements(chart: SajuChart) -> list[str]:
    """사주에서 부족한 오행(평균 미만)을 보완 대상으로. 적은 순."""
    w = chart.wuxing
    counts = {"木": w.wood, "火": w.fire, "土": w.earth, "金": w.metal, "水": w.water}
    avg = sum(counts.values()) / 5
    def_ = sorted([e for e, c in counts.items() if c < avg], key=lambda e: counts[e])
    return def_ or [min(counts, key=counts.get)]


def _four_pillars(surname: str, given: str) -> dict[str, dict]:
    """4격(원형이정). 성 1자 + 이름 2자 기준(이름 1자는 허수 1 보정)."""
    s = sum(_strokes(c) or 0 for c in surname)
    gs = [_strokes(c) or 0 for c in given]
    g1 = gs[0] if gs else 0
    g2 = gs[1] if len(gs) > 1 else 1  # 외자 이름 허수
    won = (g1 + g2)            # 元 초년
    hyung = (s + g1)           # 亨 중년(주격)
    i = (s + g2)               # 利 장년
    jeong = (s + g1 + g2)      # 貞 말년(총격)
    out = {}
    for k, label, n in (("won", "원격(元)", won), ("hyung", "형격(亨)", hyung),
                        ("i", "이격(利)", i), ("jeong", "정격(貞)", jeong)):
        out[k] = {"label": label, "num": n, "grade": _suri_grade(n)}
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


def _score_baleum(surname: str, given: str) -> NameFactor:
    seq = [_chosung_element(_reading(c)) for c in (surname + given)]
    seq = [e for e in seq if e]
    if len(seq) < 2:
        return NameFactor(key="baleum", label="발음오행", score=55, detail="발음오행 판별 불가")
    gen = clash = 0
    for a, b in zip(seq, seq[1:]):
        if a == b:
            continue
        if WUXING_GENERATES.get(a) == b or WUXING_GENERATES.get(b) == a:
            gen += 1
        elif WUXING_OVERCOMES.get(a) == b or WUXING_OVERCOMES.get(b) == a:
            clash += 1
    pairs = len(seq) - 1
    score = round(50 + 50 * (gen - clash) / pairs)
    detail = f"초성오행 {'→'.join(WUXING_KOREAN[e] for e in seq)} · 상생 {gen}/상극 {clash}"
    return NameFactor(key="baleum", label="발음오행", score=max(0, min(100, score)), detail=detail)


def _score_eumyang(surname: str, given: str) -> NameFactor:
    par = [(_strokes(c) or 0) % 2 for c in (surname + given)]  # 1=양(홀) 0=음(짝)
    if not par:
        return NameFactor(key="eumyang", label="음양", score=55, detail="획수 불명")
    yang = sum(par)
    eum = len(par) - yang
    # 한쪽으로 완전히 치우치면 감점, 섞이면 가점
    score = 100 if (yang and eum) else 50
    if len(par) >= 3 and (yang == len(par) or eum == len(par)):
        score = 40
    detail = f"양(홀){yang} 음(짝){eum}"
    return NameFactor(key="eumyang", label="음양", score=score, detail=detail)


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
    사전 대표음과 달라질 수 있으므로, 주어지면 표시 음으로 우선 사용.
    """
    targets = _deficient_elements(chart) if chart else ["木", "火", "土", "金", "水"]
    fp = _four_pillars(surname, given)
    factors = {
        "suri": _score_suri(fp),
        "jawon": _score_jawon(given, targets),
        "baleum": _score_baleum(surname, given),
        "eumyang": _score_eumyang(surname, given),
    }
    rd = (reading or "").strip()
    reading = rd if len(rd) == len(surname + given) else "".join(_reading(c) for c in (surname + given))
    return NameAnalysis(
        name=surname + given, reading=reading,
        factors=factors, perspectives=_perspectives(factors), four_pillars=fp,
    )


# 이름에 부적절한 뜻/이체자 필터(영문 정의 기준, v1 휴리스틱).
# ※ 정밀 품질은 대법원 인명용한자 + 한글 길자 큐레이션(후속 정제)에서 보강.
_BAD_DEFN = (
    "not ", "no ", "none", "end", "death", "dead", "die", "evil", "bad", "ugly",
    "sick", "disease", "ill", "slave", "stupid", "fool", "poor", "lowly", "mourn",
    "corpse", "demon", "ghost", "devil", "thief", "criminal", "lazy", "wicked",
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
)
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
        if any(b in defn for b in _BAD_DEFN):
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
        if any(b in defn for b in _BAD_DEFN):
            continue
        w = weights.get(_reading(ch), 0)
        if w > 0:
            out.append((1 if _is_common(ch) else 0, w, st, ch))
    # 상용여부↓ → 인기도↓ → 획수↑ : 같은 음이면 친숙한 글자(潤·河 등)를 벽자보다 앞에
    out.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return [c for *_, c in out[:limit]]


def recommend_names(
    surname: str, chart: SajuChart, count: int = 2, top: int = 40, gender: str = "male",
) -> list[NameCandidate]:
    """작명/아호 추천 — 사주 부족오행 보완 + 길한 81수 조합. 점수→인기도 순 상위 N.

    점수(오행 보완·수리)는 그대로 두고, 동점 후보는 **인기 이름 음절(대법원/네임차트 통계)**
    가중치로 재랭킹해 도윤·서준처럼 현대적으로 읽히는 이름을 우선 노출한다(성별 반영).
    선택지가 좁지 않게 충분히(기본 40개) 반환(프론트 '더 보기'로 단계 노출).
    """
    targets = _deficient_elements(chart)
    primary = targets[0]
    base = _candidate_pool(primary, good_only=True)
    if not base:
        return []
    sec_target = targets[1] if len(targets) > 1 else primary
    sec_base = _candidate_pool(sec_target, good_only=False) or base
    # 인기 이름 음절 한자(target 오행)를 풀 앞쪽에 우선 배치 → 도윤·서준 류 현대 이름 생성
    pp = _popular_hanja_pool(primary, gender)
    sp = _popular_hanja_pool(sec_target, gender)
    pool = pp + [c for c in base if c not in set(pp)]
    secondary = sp + [c for c in sec_base if c not in set(sp)]
    cands: list[NameCandidate] = []
    seen: set[str] = set()
    for c1 in pool[:60]:
        for c2 in secondary[:90]:
            if c1 == c2:
                continue
            given = c1 + c2
            if given in seen:
                continue
            seen.add(given)
            fp = _four_pillars(surname or "", given)
            factors = {
                "suri": _score_suri(fp),
                "jawon": _score_jawon(given, targets),
                "baleum": _score_baleum(surname or "", given),
                "eumyang": _score_eumyang(surname or "", given),
            }
            total = _perspectives(factors)["B"].total
            cands.append(NameCandidate(
                given=given,
                reading="".join(_reading(c) for c in given),
                score=total,
                suri_grade="·".join(v["grade"] for v in fp.values()),
                elements=[WUXING_KOREAN.get(_char_element(c) or "", "?") for c in given],
                meaning=" / ".join((_hanja().get(c, {}).get("defn", "")[:40]) for c in given),
            ))
    # 촌스러운(구세대) 음절은 점수 자체를 크게 깎아 하위로 — 옥·숙·자·봉·순 등은 상용한자라
    # 상용가산(×100)을 받아 동점 그룹에서 살아남았음(실측: 아숙·옥준). 감점(패널티)이 없던 게
    # '인기 우선'이 안 먹히던 근본 원인. 데이터 파일(dated_names.json)로 관리자 조정 가능.
    _pen = _dated()[1]
    # 점수(정확성) 우선(촌스 감점 반영) → 동점은 [상용 ≫ 실제 인기 이름 ≫ 인기 음절 > 좋은 뜻] 재랭킹.
    #  · 상용 글자 ×100(친숙) · 인기 이름 Top30 ×60(도윤·서준·하준) · 인기 음절 ×8 / 좋은 뜻 ×10
    cands.sort(
        key=lambda x: (
            x.score - _pen * _dated_count(x.reading),
            100 * _common_count(x.given)
            + 60 * _is_top_name(x.reading, gender)
            + 8 * _popularity(x.reading, gender)
            + 10 * _good_count(x.given),
        ),
        reverse=True,
    )
    return cands[:top]
