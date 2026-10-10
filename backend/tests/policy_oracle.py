"""A plain-Python statement of the permission policy: the TEST ORACLE.

It exists only in tests. It is never the enforcement path (AgntID is). Its job is to say
what the right answer is, so a test can check that the AgntID policies agree with it.

Policy (from the product spec):
  * unknown sender: no write actions at all; only mute / digest / block (block is allowed)
  * known contact: reply and create_calendar_event, and forward_message -- but only to one of
    the receiving user's existing contacts (allowed_recipients) and never OTP-like content
  * group admin / verified business: the same, plus pay_upi -- but only to that sender's
    registered payee and only up to PAYMENT_LIMIT_INR
  * update_preferences: denied whenever the call originates from an incoming message
  * read_otp_messages, and forwarding anything that looks like an OTP: denied for everyone
"""

from __future__ import annotations

import re
from typing import Any

PAYMENT_LIMIT_INR = 10_000.0
_OTP_LIKE = re.compile(r"\b\d{4,8}\b|\botp\b|verification code|one[- ]time", re.IGNORECASE)

WRITE_TOOLS = {"reply", "forward_message", "create_calendar_event", "pay_upi"}
CONTACT_OR_BETTER = {"known_contact", "group_admin", "verified_business"}
PAYMENT_CAPABLE = {"group_admin", "verified_business"}


def decide(tool: str, args: dict[str, Any]) -> tuple[bool, str]:
    trust = args.get("sender_trust", "unknown") or "unknown"

    if tool == "update_preferences":
        # Every call an agent makes originates from an incoming message (message_id is injected by code).
        # Preferences change only through the user's own API, never through a tool call.
        if args.get("message_id"):
            return False, f"DENIED {tool}: preferences can only be changed by the user, never by an incoming message"
        return True, f"ALLOWED {tool}: no incoming message is involved"
    if tool == "read_otp_messages":
        return False, f"DENIED {tool}: OTP and verification-code messages are never readable by the agent"
    if tool == "block_sender":
        return True, f"ALLOWED {tool}: blocking is always permitted"

    if tool == "forward_message" and _OTP_LIKE.search(str(args.get("content", ""))):
        return False, f"DENIED {tool}: content looks like an OTP or verification code"

    if tool in WRITE_TOOLS and trust not in CONTACT_OR_BETTER:
        return False, f"DENIED {tool}: sender {trust}, write actions not permitted"

    if tool == "forward_message" and args.get("to") not in (args.get("allowed_recipients") or []):
        return False, f"DENIED {tool}: {args.get('to')} is not one of the user's existing contacts"

    if tool == "pay_upi":
        if trust not in PAYMENT_CAPABLE:
            return False, f"DENIED {tool}: sender {trust} is not a group admin or verified business"
        registered = args.get("registered_payee", "")
        if not registered:
            return False, f"DENIED {tool}: sender has no registered payee or existing relationship"
        if args.get("payee_upi") != registered:
            return False, f"DENIED {tool}: payee {args.get('payee_upi')} does not match the sender's registered payee"
        if float(args.get("amount_inr", 0)) > PAYMENT_LIMIT_INR:
            return False, f"DENIED {tool}: amount exceeds the limit of {PAYMENT_LIMIT_INR:,.0f} INR"

    return True, f"ALLOWED {tool}: permitted for sender {trust}"
