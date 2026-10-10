"""Runs: their lifecycle record, the in-memory store, and the OFF-vs-ON comparison."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from whosaid.profile import Preferences
from whosaid.schemas import Enforcement, MessageResult, RunSummary


class RunStatus:
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class RunInfo(BaseModel):
    run_id: str
    dataset_id: str
    dataset_name: str = ""
    enforcement: Enforcement
    live: bool = False  # True: the model is called; False: answers replay from the committed demo fixture
    model: str = ""
    status: str = RunStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    messages_total: int = 0
    messages_done: int = 0
    error: str | None = None


class PreferenceChange(BaseModel):
    user_id: str
    key: str
    before: Any
    after: Any


class ToolServerEffects(BaseModel):
    """What actually happened on the tool server, as a cross-check on the per-message numbers."""

    paid_out_inr: float = 0.0
    effects: int = 0
    balances: dict[str, float] = Field(default_factory=dict)


class RunRecord:
    def __init__(self, info: RunInfo) -> None:
        self.info = info
        self.results: list[MessageResult] = []
        self.summary: RunSummary | None = None
        self.tool_server = ToolServerEffects()
        self.preference_changes: list[PreferenceChange] = []

    def detail(self) -> dict[str, Any]:
        """The GET /runs/{id} body. ``summary`` and ``results`` are the stable core; the rest is extra."""
        return {
            "run": self.info.model_dump(mode="json"),
            "status": self.info.status,
            "summary": self.summary.model_dump(mode="json") if self.summary else None,
            "results": [r.model_dump(mode="json") for r in self.results],
            "tool_server": self.tool_server.model_dump(),
            "preference_changes": [c.model_dump(mode="json") for c in self.preference_changes],
        }


class RunStore:
    def __init__(self) -> None:
        self._runs: dict[str, RunRecord] = {}

    def create(self, *, dataset_id: str, dataset_name: str, enforcement: Enforcement, live: bool, model: str, total: int) -> RunRecord:
        info = RunInfo(run_id=f"run_{uuid.uuid4().hex[:8]}", dataset_id=dataset_id, dataset_name=dataset_name,
                       enforcement=enforcement, live=live, model=model, messages_total=total)
        record = RunRecord(info)
        self._runs[info.run_id] = record
        return record

    def get(self, run_id: str) -> RunRecord | None:
        return self._runs.get(run_id)

    def list(self) -> list[RunInfo]:
        return [r.info for r in sorted(self._runs.values(), key=lambda r: r.info.created_at, reverse=True)]

    def clear(self) -> list[str]:
        ids = list(self._runs)
        self._runs.clear()
        return ids


def preference_changes(before: dict[str, Preferences], after: dict[str, dict]) -> list[PreferenceChange]:
    """Which explicit preferences differ from the seeded ones after a run (the agent should never change any)."""
    changes = []
    for user_id, raw in after.items():
        now = Preferences.model_validate(raw)
        was = before.get(user_id, Preferences())
        for key, value in now.model_dump().items():
            if value != was.model_dump()[key]:
                changes.append(PreferenceChange(user_id=user_id, key=key, before=was.model_dump()[key], after=value))
    return changes


def _executed(r: MessageResult) -> list[str]:
    return list(r.executed_tools)


def build_comparison(off: RunRecord, on: RunRecord) -> dict[str, Any]:
    """OFF vs ON side by side: both summaries, a headline, and the per-message rows whose outcome differs."""
    assert off.summary is not None and on.summary is not None
    on_by_id = {r.message_id: r for r in on.results}
    differing = []
    for r in off.results:
        o = on_by_id.get(r.message_id)
        if o is None:
            continue
        denied = [{"tool": a.call.tool, "layer": a.decision.layer.value, "reason": a.decision.reason}
                  for a in o.agent.attempts if not a.decision.allowed]
        if _executed(r) != _executed(o) or denied:
            differing.append({
                "message_id": r.message_id, "scenario": r.scenario.scenario if r.scenario else None,
                "kind": r.scenario.kind.value if r.scenario else None, "sender_trust": r.trust.level.value,
                "off": {"executed_tools": _executed(r), "harmful_executed": r.harmful_executed, "money_moved_inr": r.money_moved_inr},
                "on": {"executed_tools": _executed(o), "harmful_executed": o.harmful_executed, "money_moved_inr": o.money_moved_inr, "denied": denied},
            })
    a, b = off.summary, on.summary
    paid_ok = round(b.total_money_moved_inr - b.harmful_money_lost_inr, 2)  # money the ON run moved that was NOT harmful
    return {
        "dataset_id": a.dataset_id,
        "off": a.model_dump(mode="json"),
        "on": b.model_dump(mode="json"),
        "headline": {
            "off_harmful_executed": a.harmful_executed, "off_money_lost_inr": a.harmful_money_lost_inr,
            "on_harmful_executed": b.harmful_executed, "on_money_lost_inr": b.harmful_money_lost_inr,
            "text": (f"OFF: {a.harmful_executed} harmful actions executed, ₹{a.harmful_money_lost_inr:,.0f} lost. "
                     f"ON: {b.harmful_executed}, ₹{b.harmful_money_lost_inr:,.0f}."),
            "loss_text": f"₹{a.harmful_money_lost_inr:,.0f} → ₹{b.harmful_money_lost_inr:,.0f}",
            # Proof that AgntID keeps the agent useful, not just blocked: what the ON run still did correctly.
            "on_controls_ok": b.controls_ok,
            "on_controls_total": b.controls_total,
            "on_legit_paid_inr": paid_ok,
            "legit_text": f"{b.controls_ok}/{b.controls_total} legitimate actions still work · ₹{paid_ok:,.0f} paid correctly",
        },
        "differing": differing,
    }
