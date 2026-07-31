"""SSE 스트림 서버측 중단(abort) — 클라 이탈 시 메인 Ollama producer 조기 종료 검증 (A1).

배경: 스트리밍 도중 클라가 이탈하면 Starlette 가 소비 제너레이터를 close → finally 가 stop_event 를
set → `_stream_ollama` 가 iter_lines 루프에서 즉시 break(고아 추론·GPU 점유 차단). 본 테스트는
httpx.stream 을 가짜로 대체해 stop_event set 시 토큰 소비가 즉시 멎는지 결정적으로 검증한다.
"""
from __future__ import annotations

import json
import threading

from backend.app.services import chat_service


class _FakeResp:
    status_code = 200

    def __init__(self, lines):
        self._lines = lines

    def iter_lines(self):
        for ln in self._lines:
            yield ln


class _FakeCM:
    def __init__(self, lines):
        self._r = _FakeResp(lines)

    def __enter__(self):
        return self._r

    def __exit__(self, *a):
        return False


def test_stream_ollama_stops_on_event(monkeypatch):
    # done=False 인 토큰 라인 200개 — stop_event 없으면 전량 소비됨.
    lines = [json.dumps({"message": {"content": f"tok{i}"}, "done": False}) for i in range(200)]
    monkeypatch.setattr(chat_service.httpx, "stream", lambda *a, **k: _FakeCM(lines))

    ev = threading.Event()
    out = []
    for i, chunk in enumerate(
        chat_service._stream_ollama([{"role": "user", "content": "x"}], stop_event=ev)
    ):
        out.append(chunk)
        if i == 2:
            ev.set()  # 3개 받은 뒤 이탈(중단) 신호

    # set 직후 루프 상단 체크에서 break → 전량(200) 소비하지 않고 곧 멈춘다.
    assert len(out) == 3, f"기대 3, 실제 {len(out)}"


def test_stream_ollama_no_event_consumes_all(monkeypatch):
    # 회귀: stop_event 미전달 시 기존대로 done 까지 전량 소비.
    lines = [json.dumps({"message": {"content": f"t{i}"}, "done": (i == 4)}) for i in range(5)]
    monkeypatch.setattr(chat_service.httpx, "stream", lambda *a, **k: _FakeCM(lines))
    out = list(chat_service._stream_ollama([{"role": "user", "content": "x"}]))
    assert out == ["t0", "t1", "t2", "t3", "t4"]
