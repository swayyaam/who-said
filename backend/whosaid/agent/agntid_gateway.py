"""AgntID ON: an MCP client to the AgntID runtime, which enforces before it forwards to our tool server.

This gateway knows only the AgntID endpoint. It never receives the tool server's URL or secret.
The runtime adds three layers, and each decision records which one made it:

* profile  the protection profile decides which tools exist. A tool the runtime does not expose
           (``read_otp_messages`` under Medium) is recorded as a profile-layer denial here.
* policy   a per-tool Rego/constraint policy on the call's arguments.
* intent   the intent check compares the call with the task we opened (built from trusted data only).

AgntID is the source of truth for allow/deny. Its custom-Rego denials carry only a generic message, so a
readable reason is attached on our side by ``authz.explain`` (explanation only, never a decision).
"""

from __future__ import annotations

import json
from typing import Any

import agntid
from agntid.denial import is_denial_error, parse_denial_from_exception
from agntid.mcp_wrapper import strip_platform_fields
from fastmcp.exceptions import ToolError

from whosaid.agent.tool_gateway import GatewayResult, TaskInfo, ToolDescriptor
from whosaid.authz.explain import explain_denial, profile_exclusion_reason
from whosaid.errors import GatewayError
from whosaid.logging_setup import log_event
from whosaid.schemas import AuthzDecision, DecisionLayer, ToolCall
from whosaid.tool_manifest import load_manifest

RUNTIME_PREFIX = "whosaid_"  # the Prefix we gave the server in the portal; the runtime names tools <prefix>_<tool>
AGENT_ID = "whosaid-agent"


def classify_denial(info: dict[str, Any] | None) -> DecisionLayer:
    """Which AgntID layer denied, from the parsed denial."""
    if not info:
        return DecisionLayer.POLICY
    step = str(info.get("denial_step") or "").lower()
    if info.get("intent_mismatch") or "intent" in step or str(info.get("intent_status") or "").lower() in {"mismatch", "denied", "blocked"}:
        return DecisionLayer.INTENT
    return DecisionLayer.POLICY


class AgntIDGateway:
    enforced = True

    def __init__(self, url: str, access_token: str = "", agent_id: str = AGENT_ID) -> None:
        self._url = url
        self._agent_id = agent_id
        self._client = agntid.AgntidMCPClient(url, access_token=access_token or None)
        self._task_id: str | None = None
        self._exposed: set[str] = set()
        self._excluded: set[str] = set()
        self.task_open: Any = None  # the runtime's intent snapshot for the current task

    async def __aenter__(self) -> "AgntIDGateway":
        try:
            await self._client.__aenter__()
        except Exception as exc:
            raise GatewayError(f"cannot reach the AgntID runtime at {self._url}: {type(exc).__name__}: {exc}") from exc
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._client.__aexit__(*exc)

    async def list_tools(self) -> list[ToolDescriptor]:
        """Tools AgntID exposes, plus the ones it hides (from the bundled manifest), marked not exposed."""
        raw = await agntid.get_tools_list(self._client)
        exposed: list[ToolDescriptor] = []
        for t in raw:
            if not t.name.startswith(RUNTIME_PREFIX):
                continue  # the runtime's own task tools (agntid_task_open, ...)
            exposed.append(ToolDescriptor(name=t.name.removeprefix(RUNTIME_PREFIX), description=t.description or "", input_schema=t.inputSchema))
        self._exposed = {d.name for d in exposed}
        hidden = [
            ToolDescriptor(name=m.name, description=m.description, input_schema=m.input_schema, exposed=False,
                           excluded_reason=profile_exclusion_reason(m.name))
            for m in load_manifest() if m.name not in self._exposed
        ]
        self._excluded = {d.name for d in hidden}
        for d in hidden:
            log_event("authz.profile_exclusion", tool=d.name, reason=d.excluded_reason)
        return [*exposed, *hidden]

    async def open_task(self, task: TaskInfo) -> None:
        self._task_id = agntid.create_task(agent_id=self._agent_id, user_id=task.user_id, prompt=task.intent)
        try:
            self.task_open = await agntid.send_task_open_details(self._client, self._task_id, self._agent_id, task.user_id, task.intent)
        except Exception as exc:
            raise GatewayError(f"could not open an AgntID task: {type(exc).__name__}: {exc}") from exc
        if not self.task_open.ok:
            raise GatewayError(f"AgntID refused the task: {self.task_open.reason}")
        snap = self.task_open.snapshot
        log_event("agntid.task_open", message_id=task.message_id, task_id=self._task_id, intent=task.intent,
                  engine=getattr(snap, "engine_id", ""), relevant=list(getattr(snap, "relevant_tool_names", ())))

    async def close_task(self, task: TaskInfo) -> None:
        if self._task_id is None:
            return
        try:
            await agntid.send_task_close(self._client, self._task_id)
        except Exception as exc:  # closing is best-effort: the call decisions are already recorded
            log_event("agntid.task_close_failed", task_id=self._task_id, error=str(exc)[:200])
        self._task_id = None

    async def call_tool(self, call: ToolCall) -> GatewayResult:
        if call.tool in self._excluded:
            decision = AuthzDecision(allowed=False, tool=call.tool, reason=f"DENIED {profile_exclusion_reason(call.tool)}",
                                     source="agntid", enforced=True, layer=DecisionLayer.PROFILE, code="profile_exclusion")
            log_event("authz.decision", tool=call.tool, allowed=False, layer="profile", reason=decision.reason)
            return GatewayResult(decision=decision)
        if call.tool not in self._exposed:
            raise GatewayError(f"{call.tool} is not a tool AgntID exposes; call list_tools() first")

        args = {**call.arguments, "_task_id": self._task_id}
        try:
            raw = await self._client.call_tool(RUNTIME_PREFIX + call.tool, args)
        except ToolError as exc:
            if is_denial_error(exc):
                return self._denied(call, exc)
            # AgntID allowed it; the tool itself failed (bad argument, upstream error).
            decision = AuthzDecision(allowed=True, tool=call.tool, reason=f"ALLOWED {call.tool}: AgntID checks passed",
                                     source="agntid", enforced=True)
            return GatewayResult(decision=decision, error=str(exc)[:300])
        except Exception as exc:
            raise GatewayError(f"tool call {call.tool} failed to reach the AgntID runtime: {type(exc).__name__}: {exc}") from exc

        clean = strip_platform_fields(raw)
        result = dict(clean) if isinstance(clean, dict) else {"status": "ok", "value": str(clean)}
        decision = AuthzDecision(allowed=True, tool=call.tool, reason=f"ALLOWED {call.tool}: AgntID checks passed",
                                 source="agntid", enforced=True)
        log_event("authz.decision", tool=call.tool, allowed=True, layer="none", source="agntid")
        return GatewayResult(decision=decision, result=result)

    def _denied(self, call: ToolCall, exc: BaseException) -> GatewayResult:
        message, info = parse_denial_from_exception(exc)
        layer = classify_denial(info)
        readable = explain_denial(call.tool, call.arguments)
        if layer is DecisionLayer.INTENT:
            mismatch = (info or {}).get("intent_mismatch") or "the call does not match the task"
            reason = f"DENIED {call.tool}: intent check: {mismatch}"
        else:
            reason = readable or f"DENIED {call.tool}: {(info or {}).get('reason') or message}"
        decision = AuthzDecision(allowed=False, tool=call.tool, reason=reason, source="agntid", enforced=True, layer=layer,
                                 policy=(info or {}).get("policy_name") or None, code=(info or {}).get("reason") or message[:200])
        log_event("authz.decision", tool=call.tool, allowed=False, layer=layer.value, policy=decision.policy,
                  agntid_reason=decision.code, reason=reason)
        return GatewayResult(decision=decision)
