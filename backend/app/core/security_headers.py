"""보안 응답 헤더 미들웨어 (M3 — 전송구간·클릭재킹·MIME 스니핑 방어).

순수 ASGI 로 http.response.start 헤더에만 추가 → 스트리밍(SSE) 응답도 안전.
※ CSP(Content-Security-Policy)는 결제(토스)·카카오/구글 SDK·웹폰트 등 외부 로드와 충돌 위험이 있어
   별도 정책 수립·테스트 후 도입 권장(여기선 미포함). HSTS 는 HTTP 에선 브라우저가 무시하므로 무해.
"""
from __future__ import annotations

_HEADERS = [
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"SAMEORIGIN"),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"cross-origin-opener-policy", b"same-origin"),
]


class SecurityHeadersMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(message) -> None:
            if message.get("type") == "http.response.start":
                headers = message.setdefault("headers", [])
                existing = {k.lower() for k, _ in headers}
                for k, v in _HEADERS:
                    if k not in existing:
                        headers.append((k, v))
            await send(message)

        await self.app(scope, receive, send_wrapper)
