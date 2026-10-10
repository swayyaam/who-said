from __future__ import annotations

from whosaid.mcp_server.tools._common import finish
from whosaid.store import Store


def forward_message(store: Store, *, to: str, content: str, user_id: str, message_id: str, sender_id: str, **_ignored) -> dict:
    """Forward text to any contact or number."""
    result = store.send(user_id, "forward", to, content)
    return finish(store, tool="forward_message", user_id=user_id, message_id=message_id, sender_id=sender_id, status="ok", result=result)
