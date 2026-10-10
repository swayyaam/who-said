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
