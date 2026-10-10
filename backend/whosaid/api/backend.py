"""What the API needs from the outside world, behind one interface so tests can swap it for in-process doubles.

``LiveBackend`` is the real thing: a tool-server process (started on demand), the Ollama/Sarvam model with the
committed demo fixture as a replay source, and the OFF/ON gateways. In ON mode the gateway knows only the AgntID
endpoint; ``admin`` (reset, state, preferences) talks to the tool server's own /_admin routes, which are the user's
API and are not reachable by the agent.
"""

from __future__ import annotations

import socket
from contextlib import ExitStack
from typing import Any, Protocol
from urllib.parse import urlparse

from whosaid.agent.gateways import gateway_factory
from whosaid.config import DEMO_FIXTURE_DIR, Settings
from whosaid.llm import build_llm
from whosaid.mcp_server.admin import ensure_tool_server
from whosaid.pipeline import GatewayFactory
from whosaid.schemas import Enforcement


class Backend(Protocol):
    admin: Any  # ToolServerAdmin-shaped: healthy, reset_and_seed, state, get_preferences, put_preferences

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def gateway_factory(self, enforcement: Enforcement) -> GatewayFactory: ...
    def make_llm(self, *, live: bool, is_demo: bool): ...
    def ledger_reader(self): ...
    def health(self) -> dict[str, Any]: ...


class LiveBackend:
    def __init__(self, settings: Settings, *, spawn_tool_server: bool = True) -> None:
        self._settings = settings
        self._spawn = spawn_tool_server
        self._stack = ExitStack()
        self.admin: Any = None

    def start(self) -> None:
        self.admin = self._stack.enter_context(ensure_tool_server(self._settings, spawn=self._spawn))

    def stop(self) -> None:
        self._stack.close()

    def gateway_factory(self, enforcement: Enforcement) -> GatewayFactory:
        return gateway_factory(self._settings, enforcement)

    def make_llm(self, *, live: bool, is_demo: bool):
        # The demo replays from the committed fixture unless live=true; anything else needs the model.
        return build_llm(self._settings, fixture_dir=DEMO_FIXTURE_DIR if is_demo else None, fixture_only=is_demo and not live)

    def ledger_reader(self):
        from whosaid.mcp_server.admin import ServerLedgerReader

        return ServerLedgerReader(self.admin)

    def health(self) -> dict[str, Any]:
        s = self._settings
        url = urlparse(s.agntid_mcp_url)
        try:
            with socket.create_connection((url.hostname or "localhost", url.port or 80), timeout=1.0):
                reachable = True
        except OSError:
            reachable = False
        entries = sum(1 for _ in DEMO_FIXTURE_DIR.rglob("*.json")) if DEMO_FIXTURE_DIR.exists() else 0
        return {
            "tool_server": {"healthy": bool(self.admin and self.admin.healthy())},
            "agntid": {"endpoint": s.agntid_mcp_url, "reachable": reachable},
            "llm": {"provider": s.llm_provider, "model": s.llm_model, "reasoning_effort": s.llm_reasoning_effort},
            "demo_fixture": {"entries": entries},
        }
