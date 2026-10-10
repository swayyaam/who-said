from __future__ import annotations

from whosaid.mcp_server.tools._common import finish
from whosaid.store import Store


def pay_upi(store: Store, *, payee_upi: str, amount_inr: float, note: str = "", user_id: str, message_id: str, sender_id: str, **_ignored) -> dict:
    """Pay money from the user's wallet to a UPI ID."""
    status, result = store.pay(user_id, payee_upi, float(amount_inr), note)
    return finish(store, tool="pay_upi", user_id=user_id, message_id=message_id, sender_id=sender_id,
                  status=status, result=result, amount_inr=float(amount_inr))
