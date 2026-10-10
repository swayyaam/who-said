"""The contract between the agent and the tools, shared by both sides.

``TRUSTED_PARAMS`` are tool arguments that carry trust context. They exist in the MCP tool
schemas (so AgntID policies can inspect them) but are REMOVED from the schemas the LLM sees,
and the agent loop fills them from data after the model proposes a call. The model can
never set them.
"""

from __future__ import annotations

import copy
from typing import Any

TRUSTED_PARAMS: tuple[str, ...] = (
    "user_id",  # the receiving user
    "message_id",  # the message being acted on
    "sender_id",  # who sent it
    "sender_trust",  # TrustLevel value, computed in code
    "registered_payee",  # the sender's registered UPI ID, if any ("" when none)
    "allowed_recipients",  # the receiving user's existing contacts (the only valid forward targets)
)

TOOL_NAMES: tuple[str, ...] = (
    "reply",
    "forward_message",
    "create_calendar_event",
    "pay_upi",
    "read_otp_messages",
    "block_sender",
)


def model_visible_input_schema(input_schema: dict[str, Any]) -> dict[str, Any]:
    """A tool's JSON schema with every trusted parameter removed."""
    schema = copy.deepcopy(input_schema)
    props = schema.get("properties", {})
    for name in TRUSTED_PARAMS:
        props.pop(name, None)
    schema["required"] = [r for r in schema.get("required", []) if r not in TRUSTED_PARAMS]
    return schema


def strip_trusted(arguments: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Drop any trusted parameter the model tried to supply. Returns (clean, dropped names)."""
    dropped = [k for k in arguments if k in TRUSTED_PARAMS]
    return {k: v for k, v in arguments.items() if k not in TRUSTED_PARAMS}, dropped
