"""Run the tool server as its own process:  python -m whosaid.mcp_server"""

from __future__ import annotations

from whosaid.config import load_settings
from whosaid.logging_setup import setup_logging
from whosaid.mcp_server.server import build_server


def main() -> None:
    settings = load_settings()
    setup_logging(settings.log_level)
    # Docker Desktop reaches a host-loopback server via host.docker.internal. If your Docker
    # cannot, set MCP_SERVER_HOST=0.0.0.0 (this exposes the unauthenticated tool server).
    host = settings.mcp_server_host
    build_server().run(transport="http", host=host, port=settings.mcp_server_port, show_banner=False)


if __name__ == "__main__":
    main()
