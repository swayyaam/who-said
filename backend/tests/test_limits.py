"""The pay_upi limit is cumulative per payee, so splitting a payment cannot get around it; and denials do not leak to the model."""

import json

import pytest

from conftest import InProcessAdmin, OracleGateway, ScriptedLLM, final, tool_calls
from policy_oracle import decide
from whosaid.agent.loop import GENERIC_DENIAL, run_agent
from whosaid.authz.explain import explain_denial
from whosaid.mcp_server.admin import ServerLedgerReader
from whosaid.store import Store

PAYEE = "payrail@icici"  # b_102, a verified business with a registered payee


def _args(paid, amount):
    return {"sender_trust": "verified_business", "registered_payee": PAYEE, "payee_upi": PAYEE, "amount_inr": amount, "paid_today_to_payee": f"{paid:.2f}"}


@pytest.mark.parametrize("paid,amount,allowed", [(0, 10_000, True), (0, 10_001, False), (6_000, 4_000, True), (6_000, 4_001, False), (9_999, 1, True), (9_999, 2, False)])
def test_oracle_limit_is_cumulative(paid, amount, allowed):
    ok, reason = decide("pay_upi", _args(paid, amount))
    assert ok is allowed, reason


def test_explanation_names_the_cumulative_rule():
    reason = explain_denial("pay_upi", _args(8_000, 4_000))
    assert "already paid today to this payee" in reason and "daily limit" in reason


def test_ledger_sums_only_this_users_successful_payments_to_this_payee():
    store = Store()
    store.record({"user_id": "u1", "message_id": "m", "sender_id": "s", "tool": "pay_upi", "status": "ok", "amount_inr": 100.0, "details": {"paid_to": "a@b"}})
    store.record({"user_id": "u1", "message_id": "m", "sender_id": "s", "tool": "pay_upi", "status": "ok", "amount_inr": 50.0, "details": {"paid_to": "a@b"}})
    store.record({"user_id": "u1", "message_id": "m", "sender_id": "s", "tool": "pay_upi", "status": "error", "amount_inr": 0.0, "details": {"paid_to": "a@b"}})
    store.record({"user_id": "u1", "message_id": "m", "sender_id": "s", "tool": "pay_upi", "status": "ok", "amount_inr": 70.0, "details": {"paid_to": "c@d"}})
    store.record({"user_id": "u2", "message_id": "m", "sender_id": "s", "tool": "pay_upi", "status": "ok", "amount_inr": 9.0, "details": {"paid_to": "a@b"}})
    store.record({"user_id": "u1", "message_id": "m", "sender_id": "s", "tool": "reply", "status": "ok", "amount_inr": 0.0, "details": {}})
    assert store.paid_to("u1", "a@b") == 150.0 and store.paid_to("u1", "c@d") == 70.0 and store.paid_to("u1", "zz") == 0.0


async def test_three_split_payments_are_denied_once_the_total_exceeds_the_limit(demo, server, store, trust_of, settings):
    """Four thousand rupees, three times, to the same payee: the third would take the total to 12,000 and is denied."""
    msg = next(m for m in demo.messages if m.message_id == "msg_207")   # verified business, registered payee payrail@icici
    assert trust_of("msg_207").registered_payee == PAYEE
    llm = ScriptedLLM(lambda m, t: tool_calls(*[("pay_upi", {"payee_upi": PAYEE, "amount_inr": 4000, "note": f"part {i}"}) for i in (1, 2, 3)])
                      if m[-1]["role"] == "user" else final())
    async with OracleGateway(server) as gw:
        trace = await run_agent(llm=llm, gateway=gw, message=msg, trust=trust_of("msg_207"), nonce_secret="s",
                                ledger=ServerLedgerReader(InProcessAdmin(store)))

    attempts = trace.attempts
    assert [a.decision.allowed for a in attempts] == [True, True, False]
    assert [a.call.trusted_args["paid_today_to_payee"] for a in attempts] == ["0.00", "4000.00", "8000.00"]   # code-computed, never the model's
    assert attempts[2].decision.layer.value == "policy" and "daily limit" in attempts[2].decision.reason
    assert store.paid_to("u_101", PAYEE) == 8000.0   # only the two allowed payments moved money


async def test_a_denial_shows_the_model_nothing_about_the_rule(demo, server, store, trust_of):
    msg = next(m for m in demo.messages if m.message_id == "msg_207")
    seen = []

    def script(messages, tools):
        seen.append(messages)
        return tool_calls(("pay_upi", {"payee_upi": PAYEE, "amount_inr": 25_000})) if messages[-1]["role"] == "user" else final()

    async with OracleGateway(server) as gw:
        await run_agent(llm=ScriptedLLM(script), gateway=gw, message=msg, trust=trust_of("msg_207"), nonce_secret="s",
                        ledger=ServerLedgerReader(InProcessAdmin(store)))
    tool_msg = next(m for m in seen[-1] if m["role"] == "tool")
    assert json.loads(tool_msg["content"]) == {"status": "denied", "reason": GENERIC_DENIAL}
    text = tool_msg["content"].lower()
    for leak in ("limit", "10,000", "payee", "policy", "split", "registered"):
        assert leak not in text
