"""1:1 상담 실시간(WebSocket) 연결관리자 — in-memory 연결풀 + 브로드캐스트.

구조 C: 상담 전용 단일 프로세스에서 동작하므로 프로세스-로컬 in-memory 로 충분(Redis 불필요).
순수 연결 부기(bookkeeping)만 담당 — DB/과금 로직은 api/서비스 계층(consultation_session_service)이 소유.
세션당 진행감시 드라이버(no-show·카운트다운) 태스크 핸들도 여기서 보관한다.
설계: [[consultation-1on1-plan]].
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._session_socks: dict[str, set[WebSocket]] = {}   # session_id -> 참여자 소켓
        self._console_socks: dict[int, set[WebSocket]] = {}   # consultant_id -> 콘솔 소켓
        self._drivers: dict[str, asyncio.Task] = {}           # session_id -> 진행감시 태스크
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None  # sync 엔드포인트→async 브리지용

    def capture_loop(self) -> None:
        """실행 중인 이벤트 루프 참조 저장(WS 핸들러 최초 연결 시 호출) — sync REST→WS 알림 브리지."""
        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

    def notify_console_threadsafe(self, consultant_id: int, message: dict[str, Any]) -> None:
        """sync 컨텍스트(REST 스레드풀)에서 콘솔로 실시간 알림 — 루프에 코루틴 예약."""
        loop = self._loop
        if loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(self.notify_console(consultant_id, message), loop)
        except Exception:  # noqa: BLE001
            pass

    # ── 세션 채팅 소켓 ──
    async def join_session(self, session_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._session_socks.setdefault(session_id, set()).add(ws)

    async def leave_session(self, session_id: str, ws: WebSocket) -> None:
        async with self._lock:
            socks = self._session_socks.get(session_id)
            if socks:
                socks.discard(ws)
                if not socks:
                    self._session_socks.pop(session_id, None)

    def session_count(self, session_id: str) -> int:
        return len(self._session_socks.get(session_id, ()))

    async def broadcast_session(self, session_id: str, message: dict[str, Any]) -> None:
        for ws in list(self._session_socks.get(session_id, ())):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 — 끊긴 소켓은 무시(정리는 수신루프 finally 담당)
                pass

    # ── 상담사 콘솔 소켓(presence·접수 알림) ──
    async def join_console(self, consultant_id: int, ws: WebSocket) -> None:
        async with self._lock:
            self._console_socks.setdefault(consultant_id, set()).add(ws)

    async def leave_console(self, consultant_id: int, ws: WebSocket) -> None:
        async with self._lock:
            socks = self._console_socks.get(consultant_id)
            if socks:
                socks.discard(ws)
                if not socks:
                    self._console_socks.pop(consultant_id, None)

    def console_online(self, consultant_id: int) -> bool:
        return bool(self._console_socks.get(consultant_id))

    async def notify_console(self, consultant_id: int, message: dict[str, Any]) -> None:
        for ws in list(self._console_socks.get(consultant_id, ())):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                pass

    # ── 세션 진행감시 드라이버 태스크 ──
    def driver_running(self, session_id: str) -> bool:
        t = self._drivers.get(session_id)
        return t is not None and not t.done()

    def set_driver(self, session_id: str, task: asyncio.Task) -> None:
        self._drivers[session_id] = task

    def clear_driver(self, session_id: str) -> None:
        self._drivers.pop(session_id, None)


# 프로세스-로컬 싱글턴
manager = ConnectionManager()
