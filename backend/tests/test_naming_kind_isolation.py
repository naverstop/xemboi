# -*- coding: utf-8 -*-
"""작명·개명·아호 종류별 지시 분리 + 이름 한자 표 대조 교정 (전수감사 2026-07-22).

실측 결함:
  ① 개명 브리핑에는 후보 이름이 아예 없는데(현재 이름 진단 전용) 공용 프롬프트가 '추천 이름'을
     요구해 이름·한자·획수를 통째로 창작했다(현재 이름의 획수를 창작한 이름에 붙이기까지).
  ② 작명·아호 답변에 존재하지도 않는 '현재 이름 분석'·'개명 필요성' 섹션이 생겼다.
  ③ 후보 표는 '準雨'인데 답변은 '准雨', 표는 '澔優'인데 답변은 '濬優' — 이체자로 바뀌면
     유료 상품이 '다른 글자의 이름'으로 나간다.
"""
from types import SimpleNamespace

from backend.app.services import tool_service as T


def _row(kind):
    return SimpleNamespace(tool="naming", kind=kind)


def test_naming_systems_are_kind_specific():
    jak, aho, gae = (T._system_for(_row(k)) for k in ("jakmyeong", "aho", "gaemyeong"))
    assert jak != aho != gae and jak != gae

    # 개명: 새 이름 창작 금지가 명시되고, 추천 요구는 없어야 한다
    assert "새 이름을 지어내지 마세요" in gae
    assert "추천 상위 3개" not in gae

    # 작명·아호: 후보 표 밖 글자 금지 + '현재 이름' 섹션 금지
    for s in (jak, aho):
        assert "후보 표" in s
        assert "'현재 이름 분석'" in s and "섹션을 만들지 마세요" in s

    # 아호: 성을 붙이지 않는 이름이라는 점 명시(신생아 작명 오인 차단)
    assert "성(姓)을 붙이지" in aho
    # [P4] 아호에는 수리 81수·4격이 성립하지 않는다 — 성이 없어 원격==정격으로 축퇴하고
    # 브리핑에도 값이 없으므로, 프롬프트가 그 서술 자체를 금지해야 한다.
    assert "81수" in aho and "쓰지 마세요" in aho
    # 자(字)·시호(諡號)는 호와 다른 범주다 — 섞어 쓰면 살아 있는 사람에게 시호를 지어 준다.
    assert "자(字)" in aho and "시호" in aho

    # 알 수 없는 kind 는 작명 프롬프트로 폴백(무회귀)
    assert T._system_for(_row("unknown")) is T.NAMING_SYSTEM


RESULT = {"candidates": [{"given": "準雨", "reading": "준우"},
                         {"given": "澔優", "reading": "호우"},
                         {"given": "準都", "reading": "준도"}]}


def test_fix_naming_hanja_restores_table_characters():
    F = T.fix_naming_hanja
    assert F("추천 이름 2: 准雨(준우) 92점", RESULT) == "추천 이름 2: 準雨(준우) 92점"
    assert F("준우(准雨)를 권합니다", RESULT) == "준우(準雨)를 권합니다"
    assert F("김준우(金准雨)씨", RESULT) == "김준우(金準雨)씨"      # 성이 앞에 붙은 형태
    assert "澔優" in F("**濬優 (호우)**", RESULT)


def test_fix_naming_hanja_leaves_everything_else_alone():
    F = T.fix_naming_hanja
    for keep in ("準雨(준우)는 좋습니다", "표밖(엉뚱)한 글자", "올해(丙午)", "丙午(병오)"):
        assert F(keep, RESULT) == keep, keep
    # 후보가 없는 개명 결과에는 아무 것도 하지 않는다
    assert F("准雨(준우)", {"kind": "gaemyeong", "analysis": {}}) == "准雨(준우)"
    assert F("准雨(준우)", None) == "准雨(준우)"
    # 멱등
    for t in ("准雨(준우)", "준우(准雨)", "김준우(金准雨)"):
        assert F(F(t, RESULT), RESULT) == F(t, RESULT)
