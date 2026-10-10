from __future__ import annotations

from whosaid.mcp_server.tools._common import finish
from whosaid.store import Store


def read_otp_messages(store: Store, *, user_id: str, message_id: str, sender_id: str, **_ignored) -> dict:
    """Read the user's recent OTP / verification-code SMS messages."""
    result = {"messages": store.otp_messages(user_id)}
    return finish(store, tool="read_otp_messages", user_id=user_id, message_id=message_id, sender_id=sender_id, status="ok", result=result)
