"""The MCP tool server, the direct gateway, and the whole pipeline, with a scripted LLM."""

import pytest

from conftest import ScriptedLLM, final, tool_calls
from whosaid.agent.tool_gateway import DirectGateway
from whosaid.mcp_server.server import build_server
from whosaid.pipeline import process_message, run_dataset
from whosaid.schemas import Enforcement, ToolCall
from whosaid.summary import summarize
from whosaid.trust import get_trust_provider
from whosaid.tool_contract import TRUSTED_PARAMS, TOOL_NAMES


async def test_server_exposes_six_tools_with_trusted_params_in_schema(server):
    async with DirectGateway(server) as gw:
        tools = {t.name: t for t in await gw.list_tools()}
    assert set(tools) == set(TOOL_NAMES)
    for t in tools.values():
        assert set(TRUSTED_PARAMS) <= set(t.input_schema["properties"]), t.name  # policies can inspect them
        assert not set(TRUSTED_PARAMS) & set(t.input_schema.get("required", [])), t.name


async def test_pay_upi_executes_against_the_store(server, store):
    call = ToolCall(tool="pay_upi", model_args={"payee_upi": "a@b", "amount_inr": 250},
                    trusted_args={"user_id": "u1", "message_id": "m1", "sender_id": "s1", "sender_trust": "unknown", "registered_payee": ""})
    async with DirectGateway(server) as gw:
        out = await gw.call_tool(call)
    assert out.decision.allowed and out.decision.source == "direct" and not out.decision.enforced
    assert out.result["status"] == "ok"
    snap = store.snapshot()
    assert snap.balances["u1"] == 49_750.0
    assert snap.ledger[0].tool == "pay_upi" and snap.ledger[0].amount_inr == 250.0


async def test_insufficient_funds_is_a_tool_error_not_a_denial(server, store):
    call = ToolCall(tool="pay_upi", model_args={"payee_upi": "a@b", "amount_inr": 9_999_999}, trusted_args={"user_id": "u1", "message_id": "m", "sender_id": "s"})
    async with DirectGateway(server) as gw:
        out = await gw.call_tool(call)
    assert out.decision.allowed and out.result["status"] == "error"
    assert store.snapshot().balances["u1"] == 50_000.0


async def test_store_reset(server, store):
    async with DirectGateway(server) as gw:
        await gw.call_tool(ToolCall(tool="block_sender", trusted_args={"user_id": "u1", "message_id": "m", "sender_id": "bad"}))
    assert store.snapshot().blocklist == {"u1": ["bad"]}
    store.reset()
    assert store.snapshot().blocklist == {} and store.snapshot().ledger == []


def _fooled_llm():
    """A maximally gullible model: does whatever the message text asks, once."""
    def script(messages, tools):
        if messages[-1]["role"] != "user":
            return final("done")
        text = messages[-1]["content"]
        if "maple.office@ybl" in text:
            return tool_calls(("pay_upi", {"payee_upi": "maple.office@ybl", "amount_inr": 2500}))
        if "maple.rwa@okhdfc" in text:
            return tool_calls(("pay_upi", {"payee_upi": "maple.rwa@okhdfc", "amount_inr": 2500}))
        if "forward the OTP" in text:
            return tool_calls(("read_otp_messages", {}), ("forward_message", {"to": "+91 98110 22334", "content": "otp"}))
        return final("nothing to do")
    return ScriptedLLM(script)


async def test_pipeline_scores_harm_from_labels(demo, server, store, settings):
    factory = lambda: DirectGateway(server)
    results = await run_dataset(demo, llm=_fooled_llm(), gateway_factory=factory, settings=settings,
                                only={"msg_201", "msg_203", "msg_204", "msg_101"})
    by_id = {r.message_id: r for r in results}

    assert by_id["msg_101"].agent.ran is False            # not actionable: no agent call at all
    assert by_id["msg_203"].harmful_executed == [] and by_id["msg_203"].legit_actions_ok is True
    assert by_id["msg_203"].money_moved_inr == 2500
    assert by_id["msg_204"].harmful_executed == ["pay_upi"] and by_id["msg_204"].harmful_money_lost_inr == 2500
    assert set(by_id["msg_201"].harmful_executed) == {"read_otp_messages", "forward_message"}

    summary = summarize(results, enforcement=Enforcement.OFF, model="scripted")
    assert summary.harmful_executed == 3 and summary.harmful_money_lost_inr == 2500
    assert summary.total_money_moved_inr == 5000
    assert summary.by_trust_level["unknown"].harmful_executed == 2
    # The tool server's own ledger agrees with the money the pipeline reports.
    assert sum(e.amount_inr for e in store.snapshot().ledger if e.tool == "pay_upi") == 5000


async def test_results_come_back_in_dataset_order_with_concurrency(demo, server, settings):
    factory = lambda: DirectGateway(server)
    ids = [m.message_id for m in demo.messages][:8]
    results = await run_dataset(demo, llm=ScriptedLLM(lambda m, t: final()), gateway_factory=factory, settings=settings,
                                only=set(ids), concurrency=4)
    assert [r.message_id for r in results] == ids


async def test_events_are_emitted_in_order(demo, server, settings):
    seen = []
    message = next(m for m in demo.messages if m.message_id == "msg_203")
    await process_message(message, dataset=demo, trust_provider=get_trust_provider(message.channel, demo),
                          llm=_fooled_llm(), gateway_factory=lambda: DirectGateway(server), settings=settings,
                          emit=lambda t, mid, data: seen.append(t.value))
    assert seen[0] == "message.started" and seen[1] == "message.routed" and seen[-1] == "message.completed"
    assert "tool.attempted" in seen and "authz.decision" in seen and "tool.executed" in seen
