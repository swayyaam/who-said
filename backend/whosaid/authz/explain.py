"""Readable reasons for AgntID denials.

AgntID is the source of truth for allow/deny, and its custom-Rego denial carries only a generic
"Policy evaluation denied the request". This module never decides anything: given a call AgntID has
ALREADY denied, it says which of our documented rules the call breaks, so a person can read why.
If no rule matches it says so plainly and defers to AgntID's own message.
"""

from __future__ import annotations

import re
from typing import Any

PAYMENT_LIMIT_INR = 10_000
_OTP_LIKE = re.compile(r"\b\d{4,8}\b|\botp\b|verification code|one[- ]time", re.IGNORECASE)
_WRITE_TOOLS = {"reply", "forward_message", "create_calendar_event", "pay_upi"}
_CONTACT_OR_BETTER = {"known_contact", "group_admin", "verified_business"}
_PAYMENT_CAPABLE = {"group_admin", "verified_business"}


def explain_denial(tool: str, args: dict[str, Any]) -> str | None:
    """Which documented rule this (already denied) call breaks, as a sentence. None if none matches."""
    trust = args.get("sender_trust") or "unknown"
    if tool == "update_preferences" and args.get("message_id"):
        return f"DENIED {tool}: preferences can only be changed by the user, never by an incoming message"
    if tool in _WRITE_TOOLS and trust not in _CONTACT_OR_BETTER:
        return f"DENIED {tool}: sender {trust}, write actions not permitted"
    if tool == "forward_message":
        if _OTP_LIKE.search(str(args.get("content", ""))):
            return f"DENIED {tool}: content looks like an OTP or verification code"
        contacts = [c for c in str(args.get("allowed_recipients") or "").split(",") if c]
        if args.get("to") not in contacts:
            return f"DENIED {tool}: {args.get('to')} is not one of the user's existing contacts"
    if tool == "pay_upi":
        if trust not in _PAYMENT_CAPABLE:
            return f"DENIED {tool}: sender {trust} is not a group admin or verified business"
        registered = args.get("registered_payee") or ""
        if not registered:
            return f"DENIED {tool}: sender has no registered payee or existing relationship"
        if args.get("payee_upi") != registered:
            return f"DENIED {tool}: payee {args.get('payee_upi')} does not match the sender's registered payee"
        amount = float(args.get("amount_inr") or 0)
        if amount > PAYMENT_LIMIT_INR:
            return f"DENIED {tool}: amount {amount:,.0f} INR exceeds the limit of {PAYMENT_LIMIT_INR:,} INR"
        if amount <= 0:
            return f"DENIED {tool}: amount must be positive"
        paid = float(args.get("paid_today_to_payee") or 0)
        if paid + amount > PAYMENT_LIMIT_INR:
            return (f"DENIED {tool}: {amount:,.0f} INR plus {paid:,.0f} INR already paid today to this payee "
                    f"exceeds the daily limit of {PAYMENT_LIMIT_INR:,} INR")
    return None


PROFILE_EXCLUSIONS: dict[str, str] = {
    "read_otp_messages": "credential access excluded by AgntID Medium profile",
}


def profile_exclusion_reason(tool: str) -> str:
    cause = PROFILE_EXCLUSIONS.get(tool, "excluded by the AgntID protection profile")
    return f"{tool} not exposed: {cause}"
