"""The tool-calling agent loop. EVERY tool call goes through the gateway.

Per message: show the model the tools (trusted parameters removed from their schemas),
let it propose calls, strip any trusted parameter it tried to supply, inject the real ones
from data, send the call through the gateway, and feed the result (or the denial reason)
back. Nothing here is channel-specific: it sees a Message, a SenderTrust and a gateway.
"""

from __future__ import annotations

import json
import time
from typing import Any

from whosaid.agent.intent import build_task_intent
from whosaid.agent.prompts import SYSTEM_PROMPT, build_user_prompt, derive_nonce
from whosaid.agent.tool_gateway import GatewayResult, TaskInfo, ToolDescriptor, ToolGateway
from whosaid.errors import GatewayError, LLMError
from whosaid.events import Emitter, noop_emit
from whosaid.ledger import NoLedger, PaidReader
from whosaid.llm.base import LLMClient, ProposedToolCall
from whosaid.logging_setup import log_event
from whosaid.schemas import AgentTrace, AuthzDecision, EventType, Message, RoutingDecision, SenderTrust, ToolAttempt, ToolCall
from whosaid.tool_contract import model_visible_input_schema, strip_trusted


def to_openai_tools(tools: list[ToolDescriptor]) -> list[dict[str, Any]]:
    """The tool list the model sees: trusted parameters removed from every schema."""
    return [
        {"type": "function", "function": {
            "name": t.name,
            "description": t.description,
            "parameters": model_visible_input_schema(t.input_schema),
        }}
        for t in sorted(tools, key=lambda t: t.name)  # a stable order: the same prompt (and cache key) in every mode
    ]


def build_trusted_args(message: Message, trust: SenderTrust, paid_today_to_payee: float = 0.0) -> dict[str, Any]:
    # paid_today_to_payee is a decimal string ("4000.00"): the AgntID runtime types every parameter as a string.
    """Trust context for a call, computed from data. The model never supplies any of it."""
    return {
        "paid_today_to_payee": f"{paid_today_to_payee:.2f}",
        "user_id": message.user_id,
        "message_id": message.message_id,
        "sender_id": trust.sender.sender_id,
        "sender_trust": trust.level.value,
        "registered_payee": trust.registered_payee or "",
        "allowed_recipients": ",".join(trust.allowed_recipients),  # comma-separated: AgntID types it as a string
    }


def task_intent(trust: SenderTrust, routing: RoutingDecision | None = None) -> str:
    """What the user asked of the agent, from trusted data only. Never contains message content."""
    return build_task_intent(trust, routing)


# What the model is told when a call is denied. The real reason (AgntID's decision and our readable label) goes to the
# results, dashboard and logs only: the model's replies reach the sender, so policy details must not reach the model.
GENERIC_DENIAL = "This action is not permitted."


def _tool_message_for_model(call_id: str, attempt: ToolAttempt, gw: GatewayResult) -> dict[str, Any]:
    if not gw.decision.allowed:
        body: dict[str, Any] = {"status": "denied", "reason": GENERIC_DENIAL}
    elif gw.result is not None:
        body = gw.result
    else:
        body = {"status": "error", "error": gw.error or "tool failed"}
    return {"role": "tool", "tool_call_id": call_id, "content": json.dumps(body, ensure_ascii=False)}


async def _execute(
    proposed: ProposedToolCall,
    *,
    message: Message,
    trust: SenderTrust,
    gateway: ToolGateway,
    known_tools: set[str],
    emit: Emitter,
    ledger: PaidReader,
) -> tuple[ToolAttempt, GatewayResult]:
    model_args, dropped = strip_trusted(proposed.arguments)
    if dropped:
        log_event("agent.trusted_param_stripped", message_id=message.message_id, tool=proposed.name, dropped=dropped)
    # The cumulative-limit input: what this user already paid THIS payee. Computed from the ledger, hidden from the model.
    paid = await ledger.paid_to(message.user_id, str(model_args.get("payee_upi", ""))) if proposed.name == "pay_upi" else 0.0
    call = ToolCall(tool=proposed.name, model_args=model_args, trusted_args=build_trusted_args(message, trust, paid))

    if proposed.name not in known_tools:
        decision = AuthzDecision(allowed=False, tool=proposed.name, source="agent", enforced=False,
                                 reason=f"DENIED {proposed.name}: no such tool")
        gw = GatewayResult(decision=decision)
        return ToolAttempt(call=call, decision=decision), gw

    emit(EventType.TOOL_ATTEMPTED, message.message_id, {"tool": call.tool, "arguments": call.model_args})
    gw = await gateway.call_tool(call)
    d = gw.decision
    log_event("authz.decision", message_id=message.message_id, tool=d.tool, allowed=d.allowed, enforced=d.enforced,
              source=d.source, policy=d.policy, reason=d.reason, sender_trust=trust.level.value)
    emit(EventType.AUTHZ_DECISION, message.message_id, d.model_dump(mode="json"))

    executed = d.allowed and gw.result is not None and gw.result.get("status") == "ok"
    money = float(gw.result.get("amount_inr", 0.0)) if executed and call.tool == "pay_upi" and gw.result else 0.0
    attempt = ToolAttempt(call=call, decision=d, executed=executed, result=gw.result, money_moved_inr=money)
    if executed:
        emit(EventType.TOOL_EXECUTED, message.message_id, {"tool": call.tool, "result": gw.result})
    return attempt, gw


async def run_agent(
    *,
    llm: LLMClient,
    gateway: ToolGateway,
    message: Message,
    trust: SenderTrust,
    nonce_secret: str,
    media_description: str | None = None,
    max_turns: int = 4,
    emit: Emitter = noop_emit,
    routing: RoutingDecision | None = None,
    ledger: PaidReader | None = None,
) -> AgentTrace:
    """Run the agent on one message. Never raises for LLM or gateway failure: the error is recorded."""
    started = time.perf_counter()
    trace = AgentTrace(ran=True)
    task = TaskInfo(message_id=message.message_id, user_id=message.user_id, intent=task_intent(trust, routing))
    try:
        tools = await gateway.list_tools()
        known = {t.name for t in tools}
        openai_tools = to_openai_tools(tools)
        nonce = derive_nonce(nonce_secret, message.message_id)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(message, nonce, media_description)},
        ]
        await gateway.open_task(task)
        try:
            for turn in range(max_turns):
                result = await llm.chat(messages, openai_tools)
                trace.turns = turn + 1
                trace.llm_calls += 1
                trace.llm_cache_hits += int(result.cached)
                emit(EventType.AGENT_STEP, message.message_id, {
                    "turn": turn + 1, "content": result.content,
                    "proposed_tools": [c.name for c in result.tool_calls],
                    "cached": result.cached, "latency_ms": result.latency_ms,
                })
                log_event("agent.step", message_id=message.message_id, turn=turn + 1, cached=result.cached,
                          proposed=[c.name for c in result.tool_calls], content=result.content[:200])
                if not result.tool_calls:
                    trace.final_text = result.content
                    break
                messages.append(result.assistant_message)
                for proposed in result.tool_calls:
                    attempt, gw = await _execute(proposed, message=message, trust=trust, gateway=gateway,
                                                 known_tools=known, emit=emit, ledger=ledger or NoLedger())
                    trace.attempts.append(attempt)
                    messages.append(_tool_message_for_model(proposed.id, attempt, gw))
        finally:
            await gateway.close_task(task)
    except (LLMError, GatewayError) as exc:
        trace.error = f"{type(exc).__name__}: {exc}"
        log_event("agent.error", message_id=message.message_id, error=trace.error)
    trace.latency_ms = round((time.perf_counter() - started) * 1000, 1)
    return trace
