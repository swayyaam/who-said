from __future__ import annotations

from whosaid.mcp_server.tools._common import finish
from whosaid.store import Store


def block_sender(store: Store, *, user_id: str, message_id: str, sender_id: str, **_ignored) -> dict:
    """Block the sender of the message being handled."""
    result = store.block(user_id, sender_id)
    return finish(store, tool="block_sender", user_id=user_id, message_id=message_id, sender_id=sender_id, status="ok", result=result)
