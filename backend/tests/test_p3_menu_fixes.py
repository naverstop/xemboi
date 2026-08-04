# -*- coding: utf-8 -*-
"""Phase 3 메뉴별 보완 회귀 고정 (2026-07-16 전수감사).

오늘운세 전관계 / 택일 best·avoid 모순 / 개명 복성 / 경씨 복원 / 부적 자형 / 궁합 시기관계.
"""
from __future__ import annotations

from datetime import date

from backend.app.saju import naming as N
from backend.app.saju.engine import build_chart
from backend.app.saju.relations import luck_natal_relations
from backend.app.saju.taekil import recommend_dates
from backend.app.saju.types import BirthInput, CalendarType, Gender
from backend.app.services.amulet_service import decide_amulet


def _chart(y, m, d, g=Gender.MALE, dw=True):
    return build_chart(BirthInput(birth_date=date(y, m, d), calendar=CalendarType.SOLAR, gender=g),
                       with_daewoon=dw)


def test_today_full_relations_stem_clash():
    """오늘운세: 일진 천간↔일간 충(을신충)이 검출된다 — 종전 일지↔일지 2종뿐이라 누락(실측)."""
    ch = _chart(1995, 11, 10, dw=False)   # 일간 乙
    rels = luck_natal_relations(ch, "辛", "卯", scope="오늘")
    assert any("일간" in r and "충" in r for r in rels)
    assert all(not r.startswith(("월간 ", "월지 ")) for r in rels)  # '오늘' 스코프 오라벨 금지


def test_taekil_no_best_avoid_overlap():
    """택일: 같은 날이 '추천 길일'이자 '회피일'로 동시 주입되지 않는다(소창 실측 모순)."""
    ch = _chart(1990, 3, 4)
    for days in (7, 10, 30):
        res = recommend_dates(ch, date(2026, 8, 18), days=days, purpose="moving")
        assert not ({b.date for b in res.best} & {a.date for a in res.avoid}), f"days={days} 중복"


def test_gaemyeong_compound_surname_split():
    """개명: 복성(南宮民秀)이 성=南宮·이름=民秀로 분리(4격 전부 달라지던 실측 버그)."""
    comp = {h for v in N.KOREAN_SURNAMES.values() for h in v if len(h) == 2}
    assert "南宮" in comp and "諸葛" in comp
    ch = _chart(1988, 3, 21)
    right = N.analyze_name("南宮", "民秀", ch, reading="남궁민수")
    wrong = N.analyze_name("南", "宮民秀", ch, reading="남궁민수")
    assert [v["num"] for v in right.four_pillars.values()] != \
           [v["num"] for v in wrong.four_pillars.values()]  # 분리 방식이 실제로 결과를 가름


def test_surname_no_dup_loss():
    """작명: '경'씨 중복 키로 景씨가 소실되지 않는다 + 전 성씨 사전 중복 키 부재 불변식."""
    chars = [it["char"] for it in N.lookup_surname("경")]
    assert "慶" in chars and "景" in chars
    import inspect, re
    src = inspect.getsource(N)
    m = re.search(r"KOREAN_SURNAMES[^=]*=\s*\{(.*?)\n\}", src, re.S)
    keys = re.findall(r'"([가-힣]{1,2})":\s*\[', m.group(1))
    assert len(keys) == len(set(keys)), f"성씨 사전 중복 키: {[k for k in keys if keys.count(k) > 1]}"


def test_amulet_self_punish_detected():
    """부적: 자형(午午 등)이 발행 근거에 잡힌다(타 경로와 정합 — 종전 이 파일만 누락)."""
    ch = _chart(1990, 6, 10)   # 午 다수 명식
    am = decide_amulet(ch, "protect")
    rs = am.get("reasons", [])
    has_self = any("자형" in r for r in rs)
    no_contradiction = not (any("충돌 없음" in r for r in rs)
                            and any(k in r for r in rs for k in ("충(沖)", "형(刑)", "자형")))
    assert no_contradiction
    # 2026 병오년 기준 午 명식은 자형 성립(연도가 바뀌면 이 전제도 변함 — 모순 부재가 핵심 불변식)
    if date.today().year == 2026:
        assert has_self


def test_compat_timing_block():
    """궁합: 시기 질문에 세운·월운↔두 명식 관계 블록이 생성된다(비시기 질문엔 없음)."""
    from backend.app.services.compat_service import _timing_relations_block
    a = _chart(1990, 3, 4).model_dump(mode="json")
    b = _chart(1992, 7, 20, Gender.FEMALE).model_dump(mode="json")
    blk = _timing_relations_block("결혼 시기는 몇 월이 좋아요?", a, b, "A", "B")
    assert blk and "[시기 근거" in blk and "지어내지 마세요" in blk
    assert _timing_relations_block("우리 성격 궁합 어때요?", a, b, "A", "B") == ""
