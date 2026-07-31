"""조후용신(궁통보감) + 억부 월령보강 검증.

원칙(= test_saju_accuracy 와 동일):
  - 정조후용신 120칸은 권위 표(阿部泰山全集 第六卷 조후용신간법 / 갑술명리학연구소 일람표) 전사값.
    골든 칸을 박아 전사 회귀(오타)를 자동 차단한다.
  - 억부 강약은 '월령 득령/실령'이 결과에 반영됨을 검증한다.
"""
from __future__ import annotations

from datetime import date, time

from backend.app.saju.constants import STEM_TO_WUXING
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, FourPillars, Pillar
from backend.app.saju.wuxing import compute_wuxing, determine_strength
from backend.app.saju.yongsin import (
    JOHU_MONTHS,
    JOHU_TABLE,
    _table_is_complete,
    compute_johu_yongsin,
)


# ============================================================
# 1) 표 무결성 — 10천간 × 12월 = 120칸, 정용신은 모두 유효 천간
# ============================================================
def test_johu_table_complete():
    assert _table_is_complete()
    assert len(JOHU_TABLE) == 10
    cells = 0
    for stem, months in JOHU_TABLE.items():
        assert set(months) == set(JOHU_MONTHS), f"{stem} 월 누락"
        for primary, _sup in months.values():
            assert primary in STEM_TO_WUXING
            cells += 1
    assert cells == 120


# ============================================================
# 2) 골든 칸 — 권위 표 전사 정확성(회귀 차단)  [阿部泰山 조후용신간법]
# ============================================================
def test_johu_golden_cells():
    golden = {
        ("甲", "寅"): "丙", ("甲", "午"): "癸", ("甲", "子"): "丁",
        ("乙", "亥"): "丙", ("乙", "辰"): "癸",
        ("丙", "午"): "壬", ("丙", "子"): "壬", ("丙", "戌"): "甲",
        ("丁", "午"): "壬", ("丁", "卯"): "庚",
        ("戊", "午"): "壬", ("戊", "子"): "丙",
        ("己", "寅"): "丙", ("己", "卯"): "甲",
        ("庚", "寅"): "戊", ("庚", "丑"): "丙",
        ("辛", "寅"): "己", ("辛", "子"): "丙",
        ("壬", "午"): "癸", ("壬", "丑"): "丙",
        ("癸", "午"): "庚", ("癸", "申"): "丁",
        # 학파 이견 칸 — 운영 결정값으로 고정(2026-06-22). 대안 학파값은 보조에 병기되고
        # RAG 고서 인덱스·억부가 답변에서 보강한다(정용신 앵커는 환각차단용 단일값).
        ("甲", "酉"): "庚",   # 가을 갑목: 庚 채택(申·戌과 동일 계열). 보조 丙丁에 丁(정화단련설) 병기
        ("戊", "亥"): "甲",   # 초겨울 무토: 甲(소토) 채택. 보조 丙癸에 丙(온난설) 병기
    }
    for (stem, mb), expected in golden.items():
        assert compute_johu_yongsin(stem, mb).primary == expected, f"{stem}{mb} 조후용신"


# ============================================================
# 3) 조후 우선 — 겨울(亥子丑)·여름(巳午未)생은 조후 먼저, 봄·가을은 아님
# ============================================================
def test_johu_climate_priority():
    for mb in ("亥", "子", "丑", "巳", "午", "未"):
        assert compute_johu_yongsin("甲", mb).is_climate_priority is True, mb
    for mb in ("寅", "卯", "辰", "申", "酉", "戌"):
        assert compute_johu_yongsin("甲", mb).is_climate_priority is False, mb
    # 계절 라벨 일관성
    assert compute_johu_yongsin("甲", "子").season == "겨울"
    assert compute_johu_yongsin("甲", "午").season == "여름"


# ============================================================
# 4) 엔진 통합 — build_chart 가 조후용신을 채운다(교차검증 명식)
#    2026-06-09 10:48 → 甲午월·甲寅일 → 甲 일간·午월 = 癸 (여름→조후우선)
#    1972-02-28      → 壬寅월·己丑일 → 己 일간·寅월 = 丙 (봄→비우선)
# ============================================================
def test_johu_in_built_chart():
    c1 = build_chart(BirthInput(birth_date=date(2026, 6, 9), birth_time=time(10, 48)),
                     with_daewoon=False)
    assert c1.johu_yongsin is not None
    assert c1.johu_yongsin.primary == "癸"
    assert c1.johu_yongsin.is_climate_priority is True

    c2 = build_chart(BirthInput(birth_date=date(1972, 2, 28), birth_time=time(6, 0)),
                     with_daewoon=False)
    assert c2.johu_yongsin is not None
    assert c2.johu_yongsin.primary == "丙"
    assert c2.johu_yongsin.is_climate_priority is False


# ============================================================
# 5) 억부 월령 득령 보강 — 월지 본기가 강약 결과에 반영
# ============================================================
def _fp(y: str, m: str, d: str, h: str) -> FourPillars:
    return FourPillars(
        year=Pillar(stem=y[0], branch=y[1]), month=Pillar(stem=m[0], branch=m[1]),
        day=Pillar(stem=d[0], branch=d[1]), hour=Pillar(stem=h[0], branch=h[1]),
    )


def _strength(fp: FourPillars) -> str:
    full, _ = compute_wuxing(fp)
    return determine_strength(fp, full)


def test_strength_deukryeong_strong():
    # 甲木 일간, 월지 寅(木 비겁=득령) + 木·水 多 → 신강
    fp = _fp("甲寅", "丙寅", "甲寅", "乙亥")
    assert _strength(fp) == "strong"


def test_strength_silryeong_weak():
    # 甲木 일간, 월지 申(金 관=실령) + 金 多 → 신약
    fp = _fp("庚申", "甲申", "甲申", "庚午")
    assert _strength(fp) == "weak"
