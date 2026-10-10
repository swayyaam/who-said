from __future__ import annotations

from typing import Any, Callable

import pytest

from whosaid.agent.tool_gateway import DirectGateway, GatewayResult, TaskInfo, ToolDescriptor
from whosaid.config import DEMO_DATA_DIR, Settings
from whosaid.ingest import load_dataset_dir
from whosaid.llm.base import ChatResult, ProposedToolCall
from whosaid.mcp_server.server import build_server
from whosaid.schemas import AuthzDecision, Channel, ToolCall
from whosaid.store import Store
from whosaid.trust import get_trust_provider


@pytest.fixture(scope="session")
def demo():
    return load_dataset_dir(DEMO_DATA_DIR, name="demo")


@pytest.fixture()
def trust_of(demo):
    provider = get_trust_provider(Channel.WHATSAPP, demo)
    by_id = {m.message_id: m for m in demo.messages}
    return lambda mid: provider.assess(by_id[mid])


@pytest.fixture()
def settings() -> Settings:
    return Settings(agent_max_turns=4)


@pytest.fixture()
def store() -> Store:
    return Store()


@pytest.fixture()
def server(store):
    return build_server(store)


class ScriptedLLM:
    """A fake LLM: ``script`` maps the conversation so far to the next ChatResult."""

    model = "scripted"

    def __init__(self, script: Callable[[list[dict[str, Any]], list[dict[str, Any]]], ChatResult]) -> None:
        self._script = script
        self.seen_tools: list[list[dict[str, Any]]] = []
        self.seen_messages: list[list[dict[str, Any]]] = []

    async def chat(self, messages, tools):
        self.seen_tools.append(tools)
        self.seen_messages.append([dict(m) for m in messages])
        return self._script(messages, tools)


def tool_calls(*calls: tuple[str, dict[str, Any]]) -> ChatResult:
    proposed = [ProposedToolCall(id=f"c{i}", name=n, arguments=a) for i, (n, a) in enumerate(calls)]
    raw = [{"id": c.id, "type": "function", "function": {"name": c.name, "arguments": "{}"}} for c in proposed]
    return ChatResult(tool_calls=proposed, assistant_message={"role": "assistant", "content": "", "tool_calls": raw})


def final(text: str = "done") -> ChatResult:
    return ChatResult(content=text, assistant_message={"role": "assistant", "content": text})


class RecordingGateway:
    """A gateway that records calls and applies a decision function. No network."""

    enforced = True

    def __init__(self, tools: list[ToolDescriptor], decide: Callable[[ToolCall], AuthzDecision] | None = None) -> None:
        self._tools = tools
        self._decide = decide or (lambda c: AuthzDecision(allowed=True, tool=c.tool, reason="ok", source="test", enforced=True))
        self.calls: list[ToolCall] = []
        self.tasks: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def list_tools(self):
        return self._tools

    async def open_task(self, task: TaskInfo):
        self.tasks.append(f"open:{task.message_id}")

    async def close_task(self, task: TaskInfo):
        self.tasks.append(f"close:{task.message_id}")

    async def call_tool(self, call: ToolCall) -> GatewayResult:
        self.calls.append(call)
        d = self._decide(call)
        return GatewayResult(decision=d, result={"status": "ok", "amount_inr": call.model_args.get("amount_inr", 0)} if d.allowed else None)


@pytest.fixture()
def pay_tool_descriptors() -> list[ToolDescriptor]:
    full = {
        "type": "object",
        "properties": {
            "payee_upi": {"type": "string"}, "amount_inr": {"type": "number"}, "note": {"type": "string"},
            "user_id": {"type": "string"}, "message_id": {"type": "string"}, "sender_id": {"type": "string"},
            "sender_trust": {"type": "string"}, "registered_payee": {"type": "string"},
        },
        "required": ["payee_upi", "amount_inr"],
    }
    return [ToolDescriptor(name="pay_upi", description="pay", input_schema=full),
            ToolDescriptor(name="reply", description="reply", input_schema={"type": "object", "properties": {"text": {"type": "string"}, "user_id": {"type": "string"}}, "required": ["text"]})]


class OracleGateway:
    """A test double for AgntIDGateway: the oracle decides, the in-process tool server executes.

    Reasons are produced exactly as AgntIDGateway produces them (profile reason / explain_denial), so the model
    sees the same text and the recorded LLM fixture replays. Tests only: AgntID decides in production.
    """

    enforced = True

    def __init__(self, server) -> None:
        self._direct = DirectGateway(server)

    async def __aenter__(self):
        await self._direct.__aenter__()
        return self

    async def __aexit__(self, *exc):
        await self._direct.__aexit__(*exc)

    async def list_tools(self):
        from policy_oracle import HIDDEN_BY_PROFILE
        from whosaid.authz.explain import profile_exclusion_reason

        return [t.model_copy(update={"exposed": t.name not in HIDDEN_BY_PROFILE,
                                     "excluded_reason": profile_exclusion_reason(t.name) if t.name in HIDDEN_BY_PROFILE else ""})
                for t in await self._direct.list_tools()]

    async def open_task(self, task):
        return None

    async def close_task(self, task):
        return None

    async def call_tool(self, call):
        from policy_oracle import decide_layered
        from whosaid.authz.explain import explain_denial, profile_exclusion_reason
        from whosaid.schemas import DecisionLayer

        allowed, _, layer = decide_layered(call.tool, call.arguments)
        if not allowed:
            reason = f"DENIED {profile_exclusion_reason(call.tool)}" if layer == "profile" else (
                explain_denial(call.tool, call.arguments) or f"DENIED {call.tool}")
            return GatewayResult(decision=AuthzDecision(allowed=False, tool=call.tool, reason=reason, source="agntid", enforced=True,
                                                        layer=DecisionLayer(layer)))
        out = await self._direct.call_tool(call)
        out.decision = AuthzDecision(allowed=True, tool=call.tool, reason=f"ALLOWED {call.tool}: AgntID checks passed", source="agntid", enforced=True)
        return out


class InProcessAdmin:
    """ToolServerAdmin look-alike over an in-process Store (no HTTP): the API tests' tool server."""

    def __init__(self, store) -> None:
        self._store = store

    def healthy(self) -> bool:
        return True

    def reset(self) -> None:
        self._store.reset()

    def reset_and_seed(self, preferences) -> None:
        self._store.reset()
        for user_id, prefs in preferences.items():
            self._store.set_preferences(user_id, prefs)

    def state(self):
        return self._store.snapshot()

    def get_preferences(self, user_id):
        return self._store.get_preferences(user_id)

    def paid_to(self, user_id, payee):
        return self._store.paid_to(user_id, payee)

    def put_preferences(self, user_id, prefs):
        return self._store.set_preferences(user_id, prefs)


class InProcessBackend:
    """A Backend for API tests: in-process tool server, the demo fixture (no model), the oracle standing in for AgntID."""

    def __init__(self, server, store, *, agntid_reachable: bool = True) -> None:
        self._server = server
        self.admin = InProcessAdmin(store)
        self._reachable = agntid_reachable

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def gateway_factory(self, enforcement):
        from whosaid.schemas import Enforcement

        return (lambda: DirectGateway(self._server)) if enforcement is Enforcement.OFF else (lambda: OracleGateway(self._server))

    def make_llm(self, *, live: bool, is_demo: bool):
        from whosaid.config import DEMO_FIXTURE_DIR
        from whosaid.llm.factory import FixtureOnlyClient
        from whosaid.cache import ContentCache
        from whosaid.llm.cached import CachedLLM
        import tempfile
        from pathlib import Path

        cache = ContentCache(Path(tempfile.mkdtemp()), read_only_fallbacks=(DEMO_FIXTURE_DIR,))
        return CachedLLM(FixtureOnlyClient("qwen3.5:2b-mlx"), cache, provider="ollama", reasoning_effort="none")

    def ledger_reader(self):
        from whosaid.mcp_server.admin import ServerLedgerReader

        return ServerLedgerReader(self.admin)

    def health(self):
        return {"tool_server": {"healthy": True}, "agntid": {"endpoint": "test://agntid", "reachable": self._reachable},
                "llm": {"provider": "ollama", "model": "qwen3.5:2b-mlx", "reasoning_effort": "none"}, "demo_fixture": {"entries": 1}}
