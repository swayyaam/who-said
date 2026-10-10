"""The only way the agent loop touches tools.

``ToolGateway`` hides *where* a tool call goes. ``DirectGateway`` (AgntID OFF) is an MCP
client straight to our tool server; ``AgntIDGateway`` (AgntID ON, phase c) is an MCP client
to the AgntID runtime, which enforces policy before forwarding to the same server. Both
return a ``GatewayResult`` carrying an ``AuthzDecision``.
"""

from __future__ import annotations

import json
from typing import Any, Protocol

from fastmcp import Client
from pydantic import BaseModel, Field

from whosaid.errors import GatewayError
from whosaid.logging_setup import log_event
from whosaid.schemas import AuthzDecision, ToolCall


class ToolDescriptor(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    # False when the enforcement point hides the tool (e.g. AgntID's protection profile excludes it).
    exposed: bool = True
    excluded_reason: str = ""


class TaskInfo(BaseModel):
    """What a gateway may need to correlate calls to one unit of work (AgntID tasks)."""

    message_id: str
    user_id: str
    intent: str  # the user's instruction to the agent; never contains message content


class GatewayResult(BaseModel):
    decision: AuthzDecision
    result: dict[str, Any] | None = None
    error: str | None = None


class ToolGateway(Protocol):
    enforced: bool

    async def __aenter__(self) -> "ToolGateway": ...
    async def __aexit__(self, *exc: object) -> None: ...
    async def list_tools(self) -> list[ToolDescriptor]: ...
    async def open_task(self, task: TaskInfo) -> None: ...
    async def call_tool(self, call: ToolCall) -> GatewayResult: ...
    async def close_task(self, task: TaskInfo) -> None: ...


def parse_tool_result(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    """Extract (result dict, error text) from a fastmcp CallToolResult."""
    structured = getattr(raw, "structured_content", None)
    if getattr(raw, "is_error", False):
        text = " ".join(getattr(c, "text", "") for c in getattr(raw, "content", []) or []).strip()
        return None, text or "tool error"
    if isinstance(structured, dict):
        return structured, None
    for block in getattr(raw, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed, None
            except ValueError:
                return {"status": "ok", "text": text}, None
    return {"status": "ok"}, None


class DirectGateway:
    """AgntID OFF: calls go straight to our MCP server with no authorization check."""

    enforced = False

    def __init__(self, target: Any, secret: str = "") -> None:
        """``target`` is the tool server's MCP URL, or an in-process FastMCP server (tests)."""
        self._url = target if isinstance(target, str) else "<in-process server>"
        self._client = Client(target, auth=secret or None)

    async def __aenter__(self) -> "DirectGateway":
        try:
            await self._client.__aenter__()
        except Exception as exc:  # fastmcp raises a variety of transport errors
            raise GatewayError(f"cannot reach the tool server at {self._url}: {type(exc).__name__}: {exc}") from exc
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.__aexit__(*exc)

    async def list_tools(self) -> list[ToolDescriptor]:
        tools = await self._client.list_tools()
        return [ToolDescriptor(name=t.name, description=t.description or "", input_schema=t.inputSchema) for t in tools]

    async def open_task(self, task: TaskInfo) -> None:
        return None

    async def close_task(self, task: TaskInfo) -> None:
        return None

    async def call_tool(self, call: ToolCall) -> GatewayResult:
        try:
            raw = await self._client.call_tool(call.tool, call.arguments, raise_on_error=False)
        except Exception as exc:
            raise GatewayError(f"tool call {call.tool} failed to reach the server: {type(exc).__name__}: {exc}") from exc
        result, error = parse_tool_result(raw)
        decision = AuthzDecision(
            allowed=True,
            tool=call.tool,
            reason=f"ALLOWED {call.tool}: AgntID enforcement is off, no authorization check was made",
            source="direct",
            enforced=False,
        )
        log_event("authz.decision", tool=call.tool, allowed=True, enforced=False, source="direct")
        return GatewayResult(decision=decision, result=result, error=error)
