from __future__ import annotations

from typing import Any

from whosaid.store import Store


def finish(store: Store, *, tool: str, user_id: str, message_id: str, sender_id: str,
           status: str, result: dict[str, Any], amount_inr: float = 0.0) -> dict[str, Any]:
    """Write the ledger row and shape the tool result: {status, ...result}."""
    store.record({
        "user_id": user_id, "message_id": message_id, "sender_id": sender_id, "tool": tool,
        "status": status, "amount_inr": amount_inr if status == "ok" else 0.0, "details": result,
    })
    return {"status": status, **result}
