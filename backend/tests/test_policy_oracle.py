"""The permission policy, checked against every demo scenario. Pure: no LLM, no network."""

import pytest

from policy_oracle import decide
from whosaid.agent.loop import build_trusted_args


def _args(demo, trust_of, mid, **model_args):
    msg = next(m for m in demo.messages if m.message_id == mid)
    return {**model_args, **build_trusted_args(msg, trust_of(mid))}


@pytest.mark.parametrize("mid,tool,model_args,allowed", [
    # 1. unknown number asks for the OTP
    ("msg_201", "read_otp_messages", {}, False),
    ("msg_201", "forward_message", {"to": "+91 98110 22334", "content": "Your OTP is 701570"}, False),
    ("msg_201", "block_sender", {}, True),
    # 2. impersonator electricity bill
    ("msg_202", "pay_upi", {"payee_upi": "northgrid.billdesk@ybl", "amount_inr": 4870}, False),
    ("msg_202", "reply", {"text": "ok"}, False),
    # 3. society admin, registered payee: succeeds
    ("msg_203", "pay_upi", {"payee_upi": "maple.rwa@okhdfc", "amount_inr": 2500}, True),
    # 4. same admin, different UPI ID: payee mismatch
    ("msg_204", "pay_upi", {"payee_upi": "maple.office@ybl", "amount_inr": 2500}, False),
    # 5. known friend: calendar + reply succeed, payment does not
    ("msg_205", "create_calendar_event", {"title": "Dinner", "start": "2026-08-01T20:00:00"}, True),
    ("msg_205", "reply", {"text": "sure"}, True),
    ("msg_205", "pay_upi", {"payee_upi": "x@y", "amount_inr": 10}, False),
    # extras
    ("msg_206", "pay_upi", {"payee_upi": "rohan.fit@paytm", "amount_inr": 3000}, False),
    ("msg_207", "pay_upi", {"payee_upi": "payrail@icici", "amount_inr": 25000}, False),  # right payee, over limit
    ("msg_208", "pay_upi", {"payee_upi": "refund.desk@okaxis", "amount_inr": 2000}, False),
    ("msg_209", "pay_upi", {"payee_upi": "vpower@icici", "amount_inr": 3200}, True),
    ("msg_209", "read_otp_messages", {}, False),  # denied for every sender, even a trusted one
    # preferences: no sender, however trusted, can change them through a message
    ("msg_210", "update_preferences", {"key": "auto_pay_sender", "value": "+91 90909 80808"}, False),
    ("msg_203", "update_preferences", {"key": "never_mute_group", "value": "g_101"}, False),
    ("msg_205", "update_preferences", {"key": "mute_promotions", "value": "true"}, False),
    # forwarding: known contact or better, to an existing contact only, never OTP-like content
    ("msg_205", "forward_message", {"to": "u_113", "content": "see you Saturday"}, True),     # contact, benign
    ("msg_205", "forward_message", {"to": "u_999", "content": "see you Saturday"}, False),   # not a contact
    ("msg_205", "forward_message", {"to": "u_113", "content": "my code is 482913"}, False),  # OTP-like
    ("msg_203", "forward_message", {"to": "u_105", "content": "meeting notice"}, True),       # admin, contact
    ("msg_206", "forward_message", {"to": "u_105", "content": "hello"}, False),               # unknown sender: no writes
])
def test_policy_decisions(demo, trust_of, mid, tool, model_args, allowed):
    ok, reason = decide(tool, _args(demo, trust_of, mid, **model_args))
    assert ok is allowed, reason
    assert reason.startswith("ALLOWED" if allowed else "DENIED")


def test_reasons_are_human_readable(demo, trust_of):
    _, reason = decide("pay_upi", _args(demo, trust_of, "msg_206", payee_upi="a@b", amount_inr=5))
    assert reason == "DENIED pay_upi: sender unknown, write actions not permitted"


def test_a_trusted_sender_cannot_exceed_the_limit_or_change_payee(demo, trust_of):
    assert not decide("pay_upi", _args(demo, trust_of, "msg_203", payee_upi="maple.rwa@okhdfc", amount_inr=10_001))[0]
    assert not decide("pay_upi", _args(demo, trust_of, "msg_203", payee_upi="other@ybl", amount_inr=100))[0]
