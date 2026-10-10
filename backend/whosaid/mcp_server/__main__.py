"""Run the tool server as its own process:  python -m whosaid.mcp_server"""

from __future__ import annotations

import os

import uvicorn
from starlette.middleware import Middleware

from whosaid.config import load_settings
from whosaid.logging_setup import setup_logging
from whosaid.mcp_server.auth import BearerSecretMiddleware
from whosaid.mcp_server.server import build_server


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    # The runtime's secret always works. The direct (AgntID OFF) secret works only when the operator
    # explicitly allows the demo bypass; leave DEMO_ALLOW_DIRECT unset in production.
    secrets = [settings.tool_server_secret]
    if settings.demo_allow_direct:
        secrets.append(os.environ.get("DIRECT_ACCESS_SECRET", "").strip())
    # Stateless HTTP: no server-side MCP sessions to lose when the process restarts. The AgntID runtime
    # keeps its own session toward us, and a stale session id would otherwise fail every call.
    app = build_server().http_app(stateless_http=True, middleware=[Middleware(BearerSecretMiddleware, secrets=secrets)])
    # Docker Desktop reaches a host-loopback server via host.docker.internal. If your Docker cannot,
    # set MCP_SERVER_HOST=0.0.0.0 (this exposes the tool server; the shared secret then matters).
    uvicorn.run(app, host=settings.mcp_server_host, port=settings.mcp_server_port, log_level="warning")


if __name__ == "__main__":
    main()
