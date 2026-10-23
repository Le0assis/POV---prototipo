"""CORS conferido em cada pedido. Sem cookie: a senha vai no header."""

from __future__ import annotations

from .settings import get_settings

# O preflight não devolve o que o navegador pediu. Só estes nomes.
_ALLOWED_REQUEST_HEADERS = frozenset({
    "accept",
    "authorization",
    "content-type",
    "x-editor-password",
})
# O front no Pages lê Retry-After no 503. Sem isto o browser esconde o header.
_EXPOSE_HEADERS = b"Retry-After"


def _allow_headers(requested: str | None) -> str:
    if not requested:
        return "Content-Type, X-Editor-Password"
    chosen = []
    for part in requested.split(","):
        name = part.strip()
        if name.lower() in _ALLOWED_REQUEST_HEADERS:
            chosen.append(name)
    if not chosen:
        return "Content-Type, X-Editor-Password"
    return ", ".join(chosen)


def _header(scope, name: bytes) -> str | None:
    for key, value in scope.get("headers") or ():
        if key == name:
            return value.decode("latin-1")
    return None


class OriginCORSMiddleware:
    """Reflete só a origem permitida. Preflight permitido não abre o banco."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        origin = _header(scope, b"origin")
        allowed = origin is not None and origin in get_settings().allowed_origins()
        is_preflight = scope.get("method") == "OPTIONS" and _header(
            scope, b"access-control-request-method"
        ) is not None
        if is_preflight:
            if not allowed or origin is None:
                await self.app(scope, receive, send)
                return
            allow_headers = _allow_headers(_header(scope, b"access-control-request-headers"))
            encoded = origin.encode("latin-1")
            headers = [
                (b"access-control-allow-origin", encoded),
                (b"access-control-allow-methods", b"DELETE, GET, OPTIONS, PATCH, POST, PUT"),
                (b"access-control-allow-headers", allow_headers.encode("latin-1")),
                (b"access-control-expose-headers", _EXPOSE_HEADERS),
                (b"vary", b"Origin"),
                (b"content-length", b"2"),
            ]
            await send({"type": "http.response.start", "status": 200, "headers": headers})
            await send({"type": "http.response.body", "body": b"OK"})
            return
        if not allowed or origin is None:
            await self.app(scope, receive, send)
            return

        async def send_cors(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"access-control-allow-origin", origin.encode("latin-1")))
                headers.append((b"access-control-expose-headers", _EXPOSE_HEADERS))
                if not any(key.lower() == b"vary" for key, _value in headers):
                    headers.append((b"vary", b"Origin"))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_cors)
