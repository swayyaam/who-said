"""Shared-secret check for the tool server's MCP endpoint.

When AgntID is the enforcement point, the only caller of ``/mcp`` should be the AgntID runtime,
which sends the secret as a bearer credential (configured in the portal as an environment
reference). Anyone who can reach this port but lacks the secret cannot bypass AgntID. The
``/_admin`` routes are the user's own API and are deliberately not covered here.
"""

from __future__ import annotations

import hmac
import json

from starlette.types import ASGIApp, Receive, Scope, Send


class BearerSecretMiddleware:
    """Pure-ASGI middleware: 401 unless ``Authorization: Bearer <one of the secrets>`` on /mcp."""

    def __init__(self, app: ASGIApp, secrets: list[str], protected_prefix: str = "/mcp") -> None:
        self.app = app
        self._secrets = [s.encode() for s in secrets if s]
        self._prefix = protected_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(self._prefix) or not self._secrets:
            await self.app(scope, receive, send)
            return
        header = dict(scope["headers"]).get(b"authorization", b"")
        token = header[7:] if header.lower().startswith(b"bearer ") else b""
        if any(hmac.compare_digest(token, s) for s in self._secrets):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"error": "unauthorized: this tool server only accepts calls from its enforcement point"}).encode()
        await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})
