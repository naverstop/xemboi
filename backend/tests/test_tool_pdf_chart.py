# -*- coding: utf-8 -*-
"""신년운세 등 도구(tool) PDF에 사주명식 패널 포함 — _session_chart의 tool_sessions 폴백.

버그: chat 세션만 조회해 신년운세(tool) PDF에 명식이 빠졌다(답변만 출력). tool_sessions.chart_json
으로 명식 패널을 붙이되, 소유권(IDOR)은 chat과 동일하게 본인 회원만.
"""
from __future__ import annotations

from datetime import date, time
from types import SimpleNamespace

from backend.app.repositories import chat_repo
from backend.app.repositories.models import ToolSession
from backend.app.api.pdf import _session_chart
from backend.app.saju.engine import build_chart
from backend.app.saju.types import BirthInput


def _tool_session(user_id=7):
    ch = build_chart(BirthInput(birth_date=date(1990, 3, 15), birth_time=time(9, 30)))
    return ToolSession(
        tool_id="tool-abc", tool="sinnyeon", kind="2026", user_id=user_id,
        birth_date=date(1990, 3, 15), birth_time=time(9, 30), gender="male",
        chart_json=ch.model_dump(mode="json"),
    )


class _FakeDB:
    def __init__(self, row):
        self._row = row

    def get(self, model, key):
        return self._row if (model is ToolSession and key == self._row.tool_id) else None


def test_session_chart_falls_back_to_tool_session(monkeypatch):
    # chat 세션엔 없지만 tool 세션엔 있으면 명식이 붙어야 한다(본인 소유).
    monkeypatch.setattr(chat_repo, "get_session", lambda db, sid: None)
    ts = _tool_session(user_id=7)
    chart, cap, _ = _session_chart(_FakeDB(ts), "tool-abc", SimpleNamespace(id=7))
    assert chart is not None, "tool 세션 명식이 PDF에 붙지 않음"
    assert "건명" in cap and "1990" in cap


def test_session_chart_tool_idor_blocked(monkeypatch):
    # 미소유(다른 회원/익명)면 tool 명식도 조용히 생략(IDOR 차단).
    monkeypatch.setattr(chat_repo, "get_session", lambda db, sid: None)
    ts = _tool_session(user_id=7)
    assert _session_chart(_FakeDB(ts), "tool-abc", SimpleNamespace(id=99))[0] is None
    assert _session_chart(_FakeDB(ts), "tool-abc", None)[0] is None


def test_session_chart_chat_still_wins(monkeypatch):
    # chat 세션이 있으면 그걸 쓰고 tool 조회로 내려가지 않는다(기존 경로 불변).
    ch = build_chart(BirthInput(birth_date=date(1988, 5, 20), birth_time=time(12, 0)))
    chat_row = SimpleNamespace(user_id=7, created_at=None, chart_json=ch.model_dump(mode="json"),
                               birth_date=date(1988, 5, 20), birth_time=time(12, 0), gender="female")
    monkeypatch.setattr(chat_repo, "get_session", lambda db, sid: chat_row)

    class _Boom:
        def get(self, *a):
            raise AssertionError("chat 세션이 있는데 tool 조회로 내려감")

    chart, cap, _ = _session_chart(_Boom(), "chat-1", SimpleNamespace(id=7))
    assert chart is not None and "곤명" in cap
