"""RAG 청크 신뢰성 태깅 — 출처 신뢰등급 / 예시명식 / 저품질(OCR 깨짐) 판정.

색인(ingest_rag)과 재태깅(retag_corpus) 양쪽에서 공용으로 쓰여, 검색 단계에서
저신뢰·예시·깨진 청크를 걸러내거나 감점하기 위한 payload 메타를 만든다.

- trust_tier: 1(고전·이론서) / 2(일반·스캔본 기본) / 3(유튜브·카톡 등 비공식)
- is_example: 교재의 '예시 명식'(타인 사주) 청크 → 사주상담 검색 오염 방지용 제외 대상
- low_quality: 한글+한자 비율이 낮은(OCR 깨짐) 청크 → 검색 제외 대상

신뢰등급 규칙은 data/rag/source_tiers.json 으로 조정 가능(하드코딩 최소화).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_RULES_PATH = PROJECT_ROOT / "data" / "rag" / "source_tiers.json"

# 출처명(파일 stem) 부분일치 규칙. tier3 우선 적용 후 tier1, 나머지는 default.
_DEFAULT_RULES = {
    # 고전·이론서(권위 높음) — 명리 원전/정통 이론 정리물
    "tier1_patterns": [
        "명리전", "적천수", "자평진전", "자평", "연해자평", "궁통보감", "삼명통회",
        "천간론", "지지론", "월령론", "일주론", "간지총론", "체용", "형상격국",
        "격국", "신살", "용신", "육친", "십성", "조후", "정신",
    ],
    # 비공식·요약(권위 낮음) — 대화/메모/요약
    "tier3_patterns": ["카톡", "대화", "채팅", "메모", "잡담", "톡정리", "요약정리"],
    # tier3 패턴에 걸려도 tier1으로 승격하는 예외 — '카톡정리'는 선생님(현명역학원) 강의
    # 대화 원본으로 매매·취업·승진 관법의 1차 출처(실측: tier3 강등 탓에 관법이 검색에서 밀림).
    "tier1_override_patterns": ["카톡정리"],
    "default_tier": 2,
    "low_quality_threshold": 0.5,  # 한글+한자 비율 미만이면 OCR 깨짐으로 간주
}


@lru_cache(maxsize=1)
def load_tier_rules() -> dict:
    rules = dict(_DEFAULT_RULES)
    if _RULES_PATH.exists():
        try:
            rules.update(json.loads(_RULES_PATH.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 — 규칙 파일 깨져도 기본값으로 동작
            pass
    return rules


def classify_trust_tier(source: str, category: str | None, rules: dict | None = None) -> int:
    """출처 신뢰등급 1/2/3. youtube=3, tier1승격예외 → tier3 패턴=3 → tier1 패턴=1 → 기본(2)."""
    r = rules or load_tier_rules()
    if (category or "") == "youtube":
        return 3
    s = source or ""
    if any(p in s for p in r.get("tier1_override_patterns", [])):
        return 1
    if any(p in s for p in r.get("tier3_patterns", [])):
        return 3
    if any(p in s for p in r.get("tier1_patterns", [])):
        return 1
    return int(r.get("default_tier", 2))


# 예시 명식(타인 사주 사례) 탐지 — 사주상담 검색 오염 방지
_EX_MARKERS = (
    "님 사주", "씨 사주", "예시 사주", "다음 사주", "아래 사주", "사주 예",
    "예를 들", "다음과 같은 사주", "사주를 보면", "사주를 살펴", "위 사주", "사례",
)
_GANJI = set("甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥")   # 낱글자 집합(현재 예시판정엔 미사용 — P3-O2 주석 참조)


# 마커 없는 '4주 그리드' — 교재·상담기록은 '예시' 같은 말 없이 표만 나열한다.
# [RAG 전수감사 2026-07-22] 검색 대상 11,002청크 중 타인 4주 그리드가 1,823건(16.6%)인데
# 마커를 요구한 탓에 현행 규칙이 잡은 건 172건(9.4%)뿐이었다. 실제 답변에 제공된 청크의
# 37~45%(도구·궁합 '해설' 경로는 67%)가 타인 명식이었고, "정유년에 이사하면 운영이 잘된다"
# 같은 **그 사람 전용 판정**이 사용자 답변에 그대로 옮겨진 사례가 재현됐다.
_STEM_CH = "甲乙丙丁戊己庚辛壬癸"
_BRANCH_CH = "子丑寅卯辰巳午未申酉戌亥"
# [교차검증 2026-07-22] 구분자에 **전각공백(U+3000)** 이 빠져 있었고 `$` 앵커라 **행끝 라벨**이
# 걸리면 매치가 깨졌다. 스캔 전사본(vision-transcribed)은 거의 전부 전각공백을 쓰고 줄 끝에
# '乾命'·'(남자사주)' 라벨을 단다 → 명백한 4주 그리드가 통째로 빠져나갔다.
#   실측: '丁　庚　甲　庚' → 매치 False,  '子 午 丑 巳 (남자사주)' → 매치 False.
# 그 결과 「공재와 사재의 구별」(乾命 2026년 67세)·「재다신약」(坤命 54세) 같은 **개인 감명문이
# 검색 1순위로 올라와** 오늘의운세·신년운세 답변 근거가 됐다(실측 3/3 세션).
# → 전각공백을 구분자에 넣고, 줄 끝 라벨(성별표기·괄호주석)을 허용한다.
# ⚠️열 수 하한 2를 3으로 올리지 말 것도 아니고 내리지도 말 것 — 2로 내리면 tier1 「간지와 육친」의
#   **오행 배치도**('丙　丁' / '巳　午　未')가 4주로 오탐된다. 지금의 {1,3}(=2~4열)은
#   아래 _grid_cols 동수 검사와 짝을 이뤄야 안전하다.
_SEP = r"[ \t　/·]"
_ROW_TAIL = r"(?:[ \t　]*(?:乾命|坤命|[（(][^)）\n]{0,12}[)）]))?[ \t　]*$"
_STEM_ROW_RE = re.compile(rf"(?m)^[ \t　]*[{_STEM_CH}](?:{_SEP}+[{_STEM_CH}]){{1,3}}{_ROW_TAIL}")
_BRANCH_ROW_RE = re.compile(rf"(?m)^[ \t　]*[{_BRANCH_CH}](?:{_SEP}+[{_BRANCH_CH}]){{1,3}}{_ROW_TAIL}")
# 한글 산문형 — "무오년 을묘월 갑술일 신미시"
_KO_PILLAR_RUN_RE = re.compile(r"[가-힣]{2}\s*년[\s,]+[가-힣]{2}\s*월[\s,]+[가-힣]{2}\s*일")


def has_four_pillar_grid(text: str) -> bool:
    """마커 없이도 '남의 4주'가 펼쳐진 청크인지.

    천간행만으로 판정하면 '甲 乙 丙 丁은 양간이다' 같은 이론 문장을 오탐하므로
    **천간행 + 그 직후 2줄 안의 지지행**을 함께 요구한다.
    """
    t = text or ""
    if _KO_PILLAR_RUN_RE.search(t):
        return True
    lines = t.splitlines()
    for i, ln in enumerate(lines):
        if not _STEM_ROW_RE.match(ln):
            continue
        ncols = len(re.findall(f"[{_STEM_CH}]", ln))
        for nxt in lines[i + 1:i + 3]:
            if not _BRANCH_ROW_RE.match(nxt):
                continue
            # 천간 열 수와 지지 열 수가 같아야 4주 표다. 이 동수 검사가 없으면
            # 오행 배치도('丙　丁' 2열 / '巳　午　未' 3열) 같은 이론 도표가 걸린다.
            if len(re.findall(f"[{_BRANCH_CH}]", nxt)) == ncols:
                return True
    return False


# 간지 '쌍'(甲子 꼴) — 낱글자와 달리 명식을 실제로 펼친 흔적이다.
_GANJI_PAIR_RE = re.compile(r"[甲乙丙丁戊己庚辛壬癸][子丑寅卯辰巳午未申酉戌亥]")

# ── 성별 라벨이 붙은 명식 (교차검증 2026-07-22) ─────────────────────────
# 사주첩경 낱장·명리요강 사례집은 '辛 辛 壬 丁 / 卯 亥 寅 酉 (남자사주)' 처럼 **행 분리형**이라
# 간지 '쌍'이 0개다 → 마커 분기(_EX_MARKERS + 쌍 3개)로는 172건 중 16건만 걸려 무력했다.
# 그래서 그리드 검사와 같은 층에 독립 분기로 둔다.
#
# ⚠️표본 정독으로 확정한 채택 범위(넓히지 말 것):
#   · 채택 (남자사주)·(여자사주) — 같은 줄 간지 3자 조건 시 오탐 0
#   · 채택 乾命·坤命 — 단 '성명사주학' 강의는 제외(지어낸 예시 인물로 원리를 가르치는 교재라
#     26건이 통째로 오탐된다. 실측: 세운육친·승재관·복음 항목 전량 보존)
#   · ⛔기각 男命·女命·(男)·(女) — 정밀도 20%. 117건 중 74건이 **60갑자 일주 사전**이고
#     tier1 「육친」 정의표('편관·정관: (女)남편 / (男)자식')까지 걸린다. 검역(미색인)이라
#     넣으면 앞으로 들어올 일주론 자료가 영구히 색인되지 않는다.
_GENDER_LABEL_RE = re.compile(r"乾命|坤命|[（(]\s*(?:남자|여자)\s*사주\s*[)）]")
_EX_EXEMPT_SOURCES = ("성명사주학",)
_GANJI_ANY = _STEM_CH + _BRANCH_CH


def has_labeled_chart(text: str, source: str | None = None) -> bool:
    """성별 라벨(乾命·坤命·(남자사주))이 **명식과 함께** 있는 청크인지."""
    t = text or ""
    if source and any(p in source for p in _EX_EXEMPT_SOURCES):
        return False
    for m in _GENDER_LABEL_RE.finditer(t):
        s0 = t.rfind("\n", 0, m.start()) + 1
        e0 = t.find("\n", m.end())
        line = t[s0:e0 if e0 != -1 else len(t)]
        # ①라벨과 같은 줄에 간지 낱글자 3자 이상(명식 헤더에 붙은 라벨)
        if sum(1 for c in line if c in _GANJI_ANY) >= 3:
            return True
    # ②라벨 + 청크 어딘가에 간지 쌍 3개 이상(붙여쓴 명식 표기)
    return bool(_GENDER_LABEL_RE.search(t)) and len(_GANJI_PAIR_RE.findall(t)) >= 3


# ⛔⛔ 승인 없이 이 판정을 완화·강화하지 마세요 — 검색 대상 전체가 흔들립니다 ⛔⛔
#   · 낱글자 기준(간지 8자)으로 되돌리면 교리 산문 244건이 다시 검색에서 사라진다(전수 대조).
#   · 반대로 조건을 더 풀면 남의 4주 명식이 검색 상위로 돌아온다 — P0에서 16.6%→0.00%로 내린 값이다.
#   바꾼 뒤에는 반드시 `python -m scripts.retag_corpus --dry-run` 으로 전수 영향을 먼저 재고,
#   표본을 눈으로 확인한 뒤 운영자 승인을 받을 것. 실행 전 trust_tier 무변경도 확인할 것
#   (피드백 학습으로 tier1이 된 검증 지식을 덮어쓸 수 있다).
#   관련: docs/rag_hallucination_audit_2026-07-22.md 1·4장
def is_example_chunk(text: str, source: str | None = None) -> bool:
    """교재의 '예시 명식'(특정 타인 사주를 펼친 사례) 청크면 True.

    ①예시 마커 + (4주 표기 또는 간지 쌍 3개 이상)
    ②마커가 없어도 4주 그리드/한글 산문형이 있으면 예시로 본다(전수감사로 추가).

    [P3-O2 2026-07-22] ①의 밀집 조건이 원래 '간지 한자 8자 이상'이었는데, 이건 **낱글자**를
    세는 바람에 교리 산문을 무더기로 예시로 오판했다 — 조후·통근·합화·신살론 설명은
    본문에 甲·子·壬 같은 글자가 자연히 10~45자씩 섞이고, '예를 들어'·'사례'는 설명문의
    일상 어휘다. 실제 오판 사례: u00693_성명사주학13 chunk#1(개명 고려사항 (6)~(9) 본문,
    간지 낱자 9개지만 **간지 쌍은 丙寅 하나뿐**)이 통째로 검색에서 배제돼 개명 교리 근거가
    1페이지로 쪼그라들었다.
    → 낱글자 대신 **간지 쌍 3개 이상**을 요구한다. 한 사람 명식을 펼치면 최소 3주(3쌍)가
      나오므로 진짜 예시는 그대로 걸리고, 산문에 낱자가 섞이는 경우와 확실히 갈린다.
    코퍼스 17,746청크 전수 대조: 배제 해제 244건(1.37%, 표본 8건 전부 교리 산문),
    새로 배제 3건. ⚠️되돌리면 교리 자료 244건이 다시 검색에서 사라진다.
    """
    t = text or ""
    if has_four_pillar_grid(t):
        return True
    if has_labeled_chart(t, source):     # 성별 라벨 + 명식(교차검증 2026-07-22)
        return True
    if not any(m in t for m in _EX_MARKERS):
        return False
    has_pillars = ("년주" in t and "월주" in t and "일주" in t)
    return has_pillars or len(_GANJI_PAIR_RE.findall(t)) >= 3


def korean_ratio(text: str) -> float:
    """한글+한자 비율(0~1). 낮을수록 OCR 깨짐/노이즈.

    [2026-07-22 재태깅 드라이런] 분모에 공백·숫자·구두점을 넣으면 **표 형식 정상 자료**가
    깨진 것으로 오판된다 — 작명 획수표('이 지 오 李 祉 昈 … 7 9 8 양양음 金土 木火'),
    괘도, 대운표가 전부 걸렸다. 작명은 이미 0건율 25~35%라 이걸 배제하면 더 굶는다.
    → 글자다운 글자(공백·숫자·구두점 제외)만 분모로 삼는다. 진짜 OCR 깨짐(라틴 난수열·
    기호 연속)은 아래 별도 규칙이 잡으므로 검출력은 유지된다.
    """
    t = text or ""
    meaningful = re.sub(r"[\s\d.,·:;()\[\]{}/\\|~\-—–'\"“”‘’•●○★☆]+", "", t)
    n = len(meaningful) or 1
    return len(re.findall(r"[가-힣一-龥]", meaningful)) / n


# 판독불가 OCR 신호(2026-07 전수진단 실측): 손글씨 오인식은 라틴 난수열('PPpopeerpopop…')·
# 기호 연속('++++$++')로, 스캔 인쇄물 오인식(PaddleOCR)은 '단어 파편'(줄당 평균 3~5자,
# '司人가⏎오면⏎촛水로')으로 나타난다. 종전 한글비율 기준만으론 '오인식된 한글'이 통과했다.
_LATIN_RUN_RE = re.compile(r"[A-Za-z]{18,}")
_LATIN_RUN10_RE = re.compile(r"[A-Za-z]{10,}")
_SYMBOL_RUN_RE = re.compile(r"[+$%=~^_]{6,}")


def is_low_quality(text: str, threshold: float | None = None) -> bool:
    """OCR 깨짐 등 저품질 청크면 True(검색 제외 대상)."""
    t = (text or "").strip()
    if len(t) < 50:
        return True
    thr = threshold if threshold is not None else load_tier_rules().get("low_quality_threshold", 0.5)
    if korean_ratio(t) < thr:
        return True
    # 라틴 난수열·기호 연속 — 판독불가 손글씨 OCR (영단어 1개 오탐 방지: 초장문 1회 또는 3회 이상)
    if _LATIN_RUN_RE.search(t) or len(_LATIN_RUN10_RE.findall(t)) >= 3 or _SYMBOL_RUN_RE.search(t):
        return True
    # 단어 파편 — 줄당 평균 글자수가 극단적으로 짧으면 스캔 오인식과 동행(실측 A급 평균 3~5자).
    # 정상 텍스트·유튜브 자막·비전 전사는 줄당 8자 이상이라 걸리지 않는다.
    lines = [ln for ln in t.splitlines() if ln.strip()]
    if len(lines) >= 8 and sum(len(ln) for ln in lines) / len(lines) < 6:
        return True
    return False


def tag_chunk(source: str, category: str | None, text: str, rules: dict | None = None) -> dict:
    """청크 1개의 신뢰성 메타(payload에 병합용)."""
    return {
        "trust_tier": classify_trust_tier(source, category, rules),
        "is_example": is_example_chunk(text, source),
        "low_quality": is_low_quality(text),
    }
