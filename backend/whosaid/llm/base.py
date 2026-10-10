from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class ProposedToolCall(BaseModel):
    """A tool call as the model proposed it. Arguments are untrusted until the loop vets them."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatResult(BaseModel):
    content: str = ""
    tool_calls: list[ProposedToolCall] = Field(default_factory=list)
    # The assistant message in OpenAI wire format, to append to the conversation verbatim.
    assistant_message: dict[str, Any] = Field(default_factory=dict)
    finish_reason: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached: bool = False
    latency_ms: float = 0.0
    malformed_tool_calls: int = 0


class LLMClient(Protocol):
    model: str

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ChatResult: ...
