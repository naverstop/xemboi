# -*- coding: utf-8 -*-
"""무료 메뉴 brief 근거 누락으로 생기던 환각 (전수감사 2026-07-22).

① 꿈해몽 추가질문: '(내 사주 오행과 연계 풀이됨)' 한 줄만 주고 실제 값을 안 줘서,
   水가 0개인 명식에 '물이 풍요롭다'·'수와 금의 조화'를 창작했다(4런 중 3런). 첫 풀이 경로
   (api/dream.py)는 일간·오행 분포를 주입해 '수(水)가 없으니'로 정확했다 — 같은 값을 준다.
② 운세캘린더: 생기복덕 8신의 禍害(화해, 흉살)를 和解(합의)로 병기하고
   '대화로 풀면 되는 날'로 뜻을 정반대로 뒤집었다.
"""
from datetime import date
from types import SimpleNamespace

from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput
from backend.app.services.tool_service import _render

CHART = build_chart(BirthInput(birth_date=date(1990, 3, 21))).model_dump(mode="json")


def test_dream_followup_brief_carries_wuxing_counts():
    row = SimpleNamespace(tool="dream", kind="dream", chart_json=CHART, result_json={},
                          input_json={"content": "물에 빠지는 꿈", "saju_linked": True})
    brief = _render(row)
    assert "일간 乙(木)" in brief
    assert "수 0개" in brief                       # 없는 오행이 '0개'로 명시된다
    assert "'풍요롭다'고 하면 안" in brief
    # 표 제목을 대괄호로 두면 모델이 그대로 옮겨 적는다(A/B 대조 3:3 vs 0:3) → 평문 제목 + 일반화 지시
    assert "[내 사주]" not in brief
    assert "자료 제목을 본문에 옮겨 적지 말고" in brief

    # 명식이 없으면 종전 문구로 되돌아간다(무회귀)
    row2 = SimpleNamespace(tool="dream", kind="dream", chart_json=None, result_json={},
                           input_json={"content": "꿈", "saju_linked": True})
    assert "(내 사주 오행과 연계 풀이됨)" in _render(row2)


def test_calendar_brief_defines_hwahae_as_misfortune():
    row = SimpleNamespace(
        tool="calendar", kind="calendar", chart_json=CHART, input_json={},
        result_json={"year": 2026, "month": 7, "user_day_branch": "酉",
                     "days": [{"day": 10, "ganzhi": "갑진", "grade": "평",
                               "score": 55, "warnings": ["화해"]}]})
    brief = _render(row)
    assert "화해(禍害)" in brief and "和解(합의)가 아닙니다" in brief
    assert "'흉일'로 올려 부르지도 마세요" in brief
    # 내려 부르기·점수 창작도 함께 막는다(실측: '흉 48점' → '평 51점')
    assert "올리지도 내리지도 말고" in brief
    assert "목록에 없는 점수를 지어내지 마세요" in brief
