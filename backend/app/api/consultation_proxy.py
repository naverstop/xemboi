"""메인 앱 → 상담 전용 프로세스 리버스 프록시 — REST + WebSocket (구조 C 라우팅).

프론트는 same-origin `/api/consultation/*`·`wss://.../ws` 만 알면 되고, 메인 앱(:8008)이 이를
상담 프로세스(127.0.0.1:SAJU_CONSULTATION_PORT)로 전달한다. 상담 프로세스가 아직/못 떠 있으면
REST 는 503, WS 는 1011 로 닫아 프론트의 재연결에 맡긴다.
"""
from __future__ import annotations

import asyncio

from fastapi import FastAPI, Request, WebSocket
from starlette.responses import JSONResponse, Response

# 프록시 시 제거할 hop-by-hop 헤더(전달 금지)
_HOP = {"host", "content-length", "connection", "keep-alive", "transfer-encoding", "upgrade", "te", "trailer", "proxy-authorization", "proxy-authenticate"}


def mount_consultation_proxy(app: FastAPI, port: int) -> None:
    http_base = f"http://127.0.0.1:{port}"
    ws_base = f"ws://127.0.0.1:{port}"

    @app.websocket("/api/consultation/ws")
    async def _proxy_session_ws(ws: WebSocket) -> None:
        await _ws_proxy(ws, ws_base + "/api/consultation/ws")

    @app.websocket("/api/consultation/consultant/ws")
    async def _proxy_console_ws(ws: WebSocket) -> None:
        await _ws_proxy(ws, ws_base + "/api/consultation/consultant/ws")

    @app.api_route(
        "/api/consultation/{path:path}",
        methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    async def _proxy_rest(path: str, request: Request) -> Response:
        import httpx

        url = f"{http_base}/api/consultation/{path}"
        headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP}
        body = await request.body()
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.request(
                    request.method, url, params=request.query_params, headers=headers, content=body
                )
        except httpx.ConnectError:
            return JSONResponse(
                {"detail": "상담 서비스가 준비 중이에요. 잠시 후 다시 시도해 주세요."}, status_code=503
            )
        except httpx.HTTPError:
            return JSONResponse({"detail": "상담 서비스 연결에 문제가 있어요."}, status_code=502)
        resp_headers = {k: v for k, v in r.headers.items() if k.lower() not in _HOP}
        return Response(
            content=r.content,
            status_code=r.status_code,
            headers=resp_headers,
            media_type=r.headers.get("content-type"),
        )


async def _ws_proxy(client_ws: WebSocket, upstream_url: str) -> None:
    """클라이언트 WS ↔ 상담 프로세스 WS 양방향 텍스트 펌프."""
    import websockets

    qs = client_ws.scope.get("query_string", b"").decode()
    if qs:
        upstream_url = f"{upstream_url}?{qs}"
    await client_ws.accept()
    try:
        up = await websockets.connect(upstream_url, ping_interval=None, max_size=None)
    except Exception as e:  # noqa: BLE001
        # 업스트림이 핸드셰이크 단계에서 401/403 으로 거부 = 인증/권한 실패(만료·무효 토큰, 비참여자).
        # 이 경우 4403 으로 닫아 클라이언트가 '재연결 무의미'를 인지하게 한다. 그 외(프로세스 미기동 등)는
        # 1011 로 닫아 재연결에 맡긴다(인증 실패와 일시적 서비스 중단을 구분 — 만료 토큰 무한 재연결 방지).
        status = getattr(getattr(e, "response", None), "status_code", None) or getattr(e, "status_code", None)
        code = 4403 if status in (401, 403) else 1011
        try:
            await client_ws.close(code=code)
        except Exception:  # noqa: BLE001
            pass
        return

    async def c2u() -> None:
        try:
            while True:
                await up.send(await client_ws.receive_text())
        except Exception:  # noqa: BLE001
            pass

    async def u2c() -> None:
        try:
            async for data in up:
                await client_ws.send_text(data if isinstance(data, str) else data.decode("utf-8", "ignore"))
        except Exception:  # noqa: BLE001
            pass

    t1 = asyncio.create_task(c2u())
    t2 = asyncio.create_task(u2c())
    try:
        await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in (t1, t2):
            t.cancel()
        try:
            await up.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            await client_ws.close()
        except Exception:  # noqa: BLE001
            pass
