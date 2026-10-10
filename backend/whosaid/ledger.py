"""The ledger view the agent loop needs: how much has a user already paid a payee. Generic: no channel logic."""

from __future__ import annotations

from typing import Protocol


class PaidReader(Protocol):
    async def paid_to(self, user_id: str, payee: str) -> float: ...


class NoLedger:
    """Used when no ledger is available (tests, dry runs): nothing has been paid."""

    async def paid_to(self, user_id: str, payee: str) -> float:
        return 0.0
