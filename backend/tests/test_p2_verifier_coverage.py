# -*- coding: utf-8 -*-
"""P2 — 명식 검증기 사각지대 보강 회귀 테스트.

전수감사에서 '검증기가 16케이스 중 5개만 잡는다'로 드러난 구멍을 메운 뒤,
① 진성 오류는 반드시 잡고 ② 정상 문장은 절대 안 잡는지를 함께 고정한다.
오탐은 1~3분짜리 교정 재생성을 헛돌게 하고 정답을 파괴하므로 진양성만큼 중요하다.
"""
from __future__ import annotations

from datetime import date

import pytest

from backend.app.saju.constants import branch_korean, stem_korean
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput, CalendarType, Gender
from backend.app.services import chat_service as C


@pytest.fixture(scope="module")
def cj() -> dict:
    """1985-03-15 09:30 남 — 乙丑/己卯/癸丑/丁巳, 공망 寅卯, 신약 水."""
    chart = build_chart(BirthInput(birth_date=date(1985, 3, 15), birth_time="09:30",
                                   calendar=CalendarType.SOLAR, gender=Gender.MALE))
    return chart.model_dump(mode="json")


def _ko(p: dict) -> str:
    return stem_korean(p["stem"]) + branch_korean(p["branch"])


# ── P2-1 용신 ────────────────────────────────────────────────────────
def test_yongsin_general_anchor_catches_hallucination(cj):
    """'조후용신' 정확일치만 보던 탓에 놓치던 '용신은 X' 화법을 잡는다."""
    assert C._verify_yongsin("당신의 용신은 병(丙)입니다.", cj)


def test_yongsin_allows_eokbu_layer(cj):
    """조후(庚辛)와 다르더라도 억부 방향(신약 水 → 金水)에 맞으면 오류가 아니다.

    이 가드가 없으면 '신약하니 용신은 임수' 같은 정답을 재생성으로 파괴한다."""
    assert not C._verify_yongsin("당신의 용신은 임(壬)입니다.", cj)


@pytest.mark.parametrize("text", [
    "억부로 보면 용신은 계(癸)입니다.",
    "용신은 병(丙)이 아닙니다.",
    "용신은 화(火)입니다.",          # 오행 단위 — 천간 단정이 아니므로 불개입
    "희신과 용신은 신(辛)으로 봅니다.",
    "용신을 찾는 것이 명리의 핵심입니다.",
])
def test_yongsin_no_false_positive(cj, text):
    assert not C._verify_yongsin(text, cj)


# ── P2-2 천간 자리 ───────────────────────────────────────────────────
def test_pillar_stem_mismatch_detected(cj):
    assert C._verify_pillar_stems("월간 甲은 편재에 해당합니다.", cj)
    assert C._verify_pillar_stems("시간 癸(癸)는 상관입니다.", cj)


@pytest.mark.parametrize("text", [
    "3시간 정도 걸립니다.",
    "몇 시간 동안 고민했습니다.",
    "연간 매출이 3억 원입니다.",
    "세운 년간 丙이 들어옵니다.",
])
def test_pillar_stem_no_false_positive(cj, text):
    """'시간'은 time 과 동음이라 오탐 위험이 가장 큰 앵커다."""
    assert not C._verify_pillar_stems(text, cj)


def test_pillar_stem_month_flow_guard(cj):
    """월별 흐름 단락의 '월간'은 그 달 월운 천간이지 명식 월간이 아니다.

    운영 답변 실측 오탐(#### 3월 (신묘월) — 월간 십성 정재)에서 확인된 케이스."""
    from datetime import date as _d
    from backend.app.saju.pillars import compute_pillars
    y = _d.today().year
    fp, *_ = compute_pillars(BirthInput(birth_date=_d(y, 3, 15), calendar=CalendarType.SOLAR))
    txt = f"#### 3월 ({_ko({'stem': fp.month.stem, 'branch': fp.month.branch})}월)\n월간 {fp.month.stem}은 정재입니다."
    assert not C._verify_pillar_stems(txt, cj)


# ── P2-3 4주 통짜 ────────────────────────────────────────────────────
def test_whole_chart_prose_foreign(cj):
    assert C._verify_whole_chart("무오년 을묘월 갑술일 신미시 사주입니다.", cj)


def test_whole_chart_prose_own_ok(cj):
    p = cj["pillars"]
    txt = f"{_ko(p['year'])}년 {_ko(p['month'])}월 {_ko(p['day'])}일 {_ko(p['hour'])}시 사주입니다."
    assert not C._verify_whole_chart(txt, cj)


def test_whole_chart_grid_foreign(cj):
    assert C._verify_whole_chart("시  일  월  년\n辛  甲  乙  戊\n未  戌  卯  午\n", cj)


def test_whole_chart_grid_own_either_direction(cj):
    """명식표는 자료마다 년→시 / 시→년 방향이 달라 순서로 판정하면 안 된다."""
    p = cj["pillars"]
    fwd = ("년 월 일 시\n" + " ".join(p[k]["stem"] for k in ("year", "month", "day", "hour"))
           + "\n" + " ".join(p[k]["branch"] for k in ("year", "month", "day", "hour")) + "\n")
    rev = ("시 일 월 년\n" + " ".join(p[k]["stem"] for k in ("hour", "day", "month", "year"))
           + "\n" + " ".join(p[k]["branch"] for k in ("hour", "day", "month", "year")) + "\n")
    assert not C._verify_whole_chart(fwd, cj)
    assert not C._verify_whole_chart(rev, cj)


def test_whole_chart_daewoon_table_not_flagged(cj):
    """대운표(간지 8~10개)를 4주표로 오인하면 거의 모든 답변이 오탐된다."""
    assert not C._verify_whole_chart("대운\n甲 乙 丙 丁\n子 丑 寅 卯\n", cj)


def test_whole_chart_survives_missing_hour(cj):
    """'시 모름' 명식은 pillars.hour = None — 실측 크래시 지점."""
    cj2 = dict(cj)
    cj2["pillars"] = dict(cj["pillars"], hour=None)
    assert C._verify_whole_chart("무오년 을묘월 갑술일 사주입니다.", cj2) is not None


# ── P2-4 공망 ────────────────────────────────────────────────────────
def test_gongmang_single_branch_claim(cj):
    assert C._verify_gongmang("공망인 술토가 작용합니다.", cj)


def test_gongmang_particle_in_not_eaten_as_branch(cj):
    """'공망인'의 조사 '인'을 지지 寅으로 먹어 정답을 오답으로 뒤집던 실측 오탐."""
    gm = cj["gongmang"]
    ok = f"공망인 {branch_korean(gm[0])}토와 {branch_korean(gm[1])}수입니다."
    assert not C._verify_gongmang(ok, cj)


def test_gongmang_palace_claim(cj):
    """'일주와 시주가 공망' — 공망은 지지의 성질이지 자리의 성질이 아니다."""
    assert C._verify_gongmang("일주와 시주가 공망입니다.", cj)
    assert C._verify_gongmang("공망은 일주·시주입니다.", cj)


@pytest.mark.parametrize("text", [
    "공망은 사주에서 비어 있는 자리를 뜻합니다.",   # '사'를 巳로 오인하면 안 됨
    "일주가 공망이면 배우자 인연이 늦습니다.",       # 가정문
])
def test_gongmang_no_false_positive(cj, text):
    assert not C._verify_gongmang(text, cj)


def test_gongmang_reference_sentence_not_flagged(cj):
    """'일지 축(丑)은 공망 지지 인·묘와 다릅니다' — 자리를 공망이라 주장한 게 아니다."""
    gm = cj["gongmang"]
    d = cj["pillars"]["day"]["branch"]
    txt = (f"일지 {branch_korean(d)}({d})은 공망 지지 "
           f"{branch_korean(gm[0])}·{branch_korean(gm[1])}와 다릅니다.")
    assert not C._verify_gongmang(txt, cj)


# ── P2-5 십이운성 ────────────────────────────────────────────────────
def test_twelve_life_swap_detected(cj):
    tl = cj["twelve_life"]
    wrong = next(v for v in tl.values() if v != tl["월"])
    assert C._verify_twelve_life(f"월지는 십이운성으로 {wrong}입니다.", cj)


def test_twelve_life_correct_ok(cj):
    assert not C._verify_twelve_life(f"월지는 십이운성으로 {cj['twelve_life']['월']}입니다.", cj)


def test_twelve_life_uses_korean_keys(cj):
    """engine 은 twelve_life 를 한글 키('월')로 만든다 — 영문 키로 조회하면 검증기가 통째로 죽는다."""
    assert set(cj["twelve_life"]) == {"년", "월", "일", "시"}


@pytest.mark.parametrize("text", [
    "월지 묘(卯)가 자리합니다.",        # 지지 卯 — 십이운성 墓 아님
    "일지 병(丙)과 어울립니다.",        # 천간 丙 — 십이운성 病 아님
    "월지와 세운의 관대 기운이 만납니다.",
    "일지는 관대한 성품을 만듭니다.",     # '관대하다'(너그럽다) — 일상어
])
def test_twelve_life_no_false_positive(cj, text):
    assert not C._verify_twelve_life(text, cj)


# ── 게이트 배선 ──────────────────────────────────────────────────────
def test_new_verifiers_wired_into_gate(cj):
    """검증기를 만들어도 _verify_myeongsik 에 안 꽂으면 죽은 코드다(실측 전례 다수)."""
    tl = cj["twelve_life"]
    wrong = next(v for v in tl.values() if v != tl["월"])
    for txt in ("월간 甲은 편재입니다.",
                f"월지는 십이운성으로 {wrong}입니다.",
                "무오년 을묘월 갑술일 신미시 사주입니다."):
        assert C._verify_myeongsik(txt, cj), f"게이트가 놓침: {txt}"
