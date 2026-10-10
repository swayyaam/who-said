"""Client for the tool server's /_admin routes (reset, state) and a launcher for the server.

Admin routes are plain HTTP on the same port as the MCP endpoint; they are not MCP tools, so
neither the agent nor the AgntID runtime can call them.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from contextlib import contextmanager
from typing import Iterator

import httpx

from whosaid.config import Settings
from whosaid.errors import GatewayError
from whosaid.profile.preferences import Preferences
from whosaid.store import StoreSnapshot


class ToolServerAdmin:
    def __init__(self, mcp_url: str) -> None:
        self._base = mcp_url.rstrip("/").removesuffix("/mcp")

    def healthy(self) -> bool:
        try:
            return httpx.get(f"{self._base}/_admin/health", timeout=1.5).status_code == 200
        except httpx.HTTPError:
            return False

    def reset(self) -> None:
        httpx.post(f"{self._base}/_admin/reset", timeout=5).raise_for_status()

    def get_preferences(self, user_id: str) -> Preferences:
        resp = httpx.get(f"{self._base}/_admin/preferences/{user_id}", timeout=5)
        resp.raise_for_status()
        return Preferences.model_validate(resp.json())

    def put_preferences(self, user_id: str, prefs: Preferences) -> Preferences:
        resp = httpx.put(f"{self._base}/_admin/preferences/{user_id}", json=prefs.model_dump(), timeout=5)
        resp.raise_for_status()
        return Preferences.model_validate(resp.json())

    def reset_and_seed(self, preferences: dict[str, Preferences]) -> None:
        """Start a run from a known state: wipe the store, then load the dataset's explicit preferences."""
        self.reset()
        for user_id, prefs in preferences.items():
            self.put_preferences(user_id, prefs)

    def state(self) -> StoreSnapshot:
        resp = httpx.get(f"{self._base}/_admin/state", timeout=5)
        resp.raise_for_status()
        return StoreSnapshot.model_validate(resp.json())


class ServerPreferenceReader:
    """Reads explicit preferences from the tool server, where they canonically live."""

    def __init__(self, admin: ToolServerAdmin) -> None:
        self._admin = admin

    async def get(self, user_id: str) -> Preferences:
        return await asyncio.to_thread(self._admin.get_preferences, user_id)


@contextmanager
def ensure_tool_server(settings: Settings, *, spawn: bool = True) -> Iterator[ToolServerAdmin]:
    """Yield an admin client for a running tool server, starting one as a subprocess if needed."""
    admin = ToolServerAdmin(settings.mcp_server_url)
    if admin.healthy():
        yield admin
        return
    if not spawn:
        raise GatewayError(f"no tool server at {settings.mcp_server_url}; start it with: python -m whosaid.mcp_server")
    proc = subprocess.Popen([sys.executable, "-m", "whosaid.mcp_server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise GatewayError("the tool server process exited during start-up")
            if admin.healthy():
                break
            time.sleep(0.3)
        else:
            raise GatewayError("timed out waiting for the tool server to start")
        yield admin
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
