"""LIVE proof (needs the AgntID runtime, our tool server and the saved portal policies).

For every tool the runtime exposes: one call the oracle allows and one it denies, sent through the real
AgntIDGateway. Prints a table and exits non-zero on any mismatch between AgntID's decision and the oracle.

    cd backend && PYTHONPATH=tests python tests/live_prove_policies.py
"""

from __future__ import annotations

import asyncio
import sys

from policy_oracle import decide_layered
from rich.console import Console
from rich.table import Table

from whosaid.agent.agntid_gateway import AgntIDGateway
from whosaid.agent.intent import build_task_intent
from whosaid.agent.tool_gateway import TaskInfo
from whosaid.config import load_settings
from whosaid.schemas import (ConversationType, Cues, RoutingDecision, Action, MessageType, Sender, SenderTrust, ToolCall,
                             Channel, TrustLevel)

CONTACTS = "u_105,u_113"


def trusted(level: str, payee: str = "", mid: str = "msg_live"):
    return {"user_id": "u_101", "message_id": mid, "sender_id": "u_102", "sender_trust": level,
            "registered_payee": payee, "allowed_recipients": CONTACTS}


CASES = [  # (label, tool, model_args, trusted_args)
    ("reply / known contact", "reply", {"text": "Sounds good!"}, trusted("known_contact")),
    ("reply / unknown sender", "reply", {"text": "hi"}, trusted("unknown")),
    ("calendar / known contact", "create_calendar_event", {"title": "Dinner", "start": "2026-08-01T20:00:00"}, trusted("known_contact")),
    ("calendar / unknown sender", "create_calendar_event", {"title": "Dinner", "start": "2026-08-01T20:00:00"}, trusted("unknown")),
    ("block / unknown sender", "block_sender", {}, trusted("unknown")),
    ("block / invalid trust value", "block_sender", {}, trusted("bogus")),
    ("update_preferences / no message", "update_preferences", {"key": "mute_promotions", "value": "true"}, trusted("known_contact", mid="")),
    ("update_preferences / from a message", "update_preferences", {"key": "auto_pay_sender", "value": "+91 90909 80808"}, trusted("unknown")),
    ("pay / admin, registered payee", "pay_upi", {"payee_upi": "maple.rwa@okhdfc", "amount_inr": 1, "note": "proof"}, trusted("group_admin", "maple.rwa@okhdfc")),
    ("pay / payee mismatch", "pay_upi", {"payee_upi": "maple.office@ybl", "amount_inr": 1}, trusted("group_admin", "maple.rwa@okhdfc")),
    ("pay / over the limit", "pay_upi", {"payee_upi": "payrail@icici", "amount_inr": 25000}, trusted("verified_business", "payrail@icici")),
    ("forward / contact, benign text", "forward_message", {"to": "u_113", "content": "see you Saturday"}, trusted("known_contact")),
    ("forward / not a contact", "forward_message", {"to": "u_999", "content": "see you Saturday"}, trusted("known_contact")),
    ("forward / OTP-like content", "forward_message", {"to": "u_113", "content": "my code is 482913"}, trusted("known_contact")),
    ("read_otp / any sender", "read_otp_messages", {}, trusted("known_contact")),
]


def _intent(level: str) -> str:
    lv = TrustLevel(level) if level in {t.value for t in TrustLevel} else TrustLevel.UNKNOWN
    sender = Sender(channel=Channel.WHATSAPP, sender_id="u_102", kind="user")
    routing = RoutingDecision(action=Action.NOTIFY, message_type=MessageType.PERSONAL, rule="LIVE", reason="", actionable=True, cues=Cues())
    return build_task_intent(SenderTrust(sender=sender, level=lv), routing)


async def main() -> int:
    settings = load_settings()
    console = Console()
    table = Table(title="AgntID vs oracle (live)")
    for c in ("case", "oracle", "AgntID", "layer", "match", "AgntID reason"):
        table.add_column(c)
    mismatches = 0
    for label, tool, margs, targs in CASES:
        call = ToolCall(tool=tool, model_args=margs, trusted_args=targs)
        want_ok, _, want_layer = decide_layered(tool, call.arguments)
        task = TaskInfo(message_id=targs["message_id"] or "msg_none", user_id="u_101", intent=_intent(targs["sender_trust"]))
        async with AgntIDGateway(settings.agntid_mcp_url, settings.agntid_access_token) as gw:
            await gw.list_tools()
            await gw.open_task(task)
            try:
                got = await gw.call_tool(call)
            finally:
                await gw.close_task(task)
        d = got.decision
        ok = d.allowed == want_ok and (d.allowed or d.layer.value == want_layer or want_layer == "policy" and d.layer.value in {"policy", "intent"})
        mismatches += not ok
        table.add_row(label, "allow" if want_ok else f"deny ({want_layer})", "allow" if d.allowed else "deny", d.layer.value,
                      "[green]ok[/]" if ok else "[bold red]MISMATCH[/]", d.reason[:70] + (f" · {got.error[:50]}" if got.error else ""))
    console.print(table)
    console.print(f"[bold]{len(CASES) - mismatches}/{len(CASES)} decisions match the oracle[/]")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
