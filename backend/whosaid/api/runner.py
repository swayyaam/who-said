"""Execute one run in the background: reset the tool server, run the pipeline, publish events, store results."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from whosaid.api.state import AppState
from whosaid.config import profile_params
from whosaid.ingest import Dataset
from whosaid.logging_setup import log_event
from whosaid.mcp_server.admin import ServerPreferenceReader
from whosaid.pipeline import run_dataset
from whosaid.runs import RunRecord, RunStatus, ToolServerEffects, preference_changes
from whosaid.schemas import EventType, MessageResult
from whosaid.summary import summarize


async def execute_run(state: AppState, record: RunRecord, dataset: Dataset, *, concurrency: int | None, only: set[str] | None) -> None:
    info, run_id, bus = record.info, record.info.run_id, state.bus
    async with state.lock:
        info.status, info.started_at = RunStatus.RUNNING, datetime.now(timezone.utc)
        bus.publish(run_id, EventType.RUN_STARTED, data={
            "dataset_id": info.dataset_id, "enforcement": info.enforcement.value, "live": info.live, "model": info.model,
            "messages_total": info.messages_total,
        })
        llm = None
        try:
            llm = state.backend.make_llm(live=info.live, fixture_dir=state.datasets.fixture_dir(info.dataset_id))
            admin = state.backend.admin
            await asyncio.to_thread(admin.reset_and_seed, dataset.preferences)

            def on_result(result: MessageResult) -> None:
                record.results.append(result)
                info.messages_done += 1

            results = await run_dataset(
                dataset, llm=llm, gateway_factory=state.backend.gateway_factory(info.enforcement), settings=state.settings,
                emit=lambda t, mid, data: bus.publish(run_id, t, mid, data), on_result=on_result, only=only,
                concurrency=concurrency, preferences=ServerPreferenceReader(admin), profile_params=profile_params(state.settings),
                ledger=state.backend.ledger_reader(),
            )
            record.results = results  # dataset order
            tool_state = await asyncio.to_thread(admin.state)
            record.tool_server = ToolServerEffects(
                paid_out_inr=sum(e.amount_inr for e in tool_state.ledger if e.tool == "pay_upi" and e.status == "ok"),
                effects=len(tool_state.ledger), balances=tool_state.balances,
            )
            record.preference_changes = preference_changes(dataset.preferences, tool_state.preferences)
            record.summary = summarize(results, enforcement=info.enforcement, model=info.model, run_id=run_id, dataset_id=info.dataset_id)
            info.status = RunStatus.COMPLETED
            bus.publish(run_id, EventType.RUN_COMPLETED, data={"summary": record.summary.model_dump(mode="json")})
        except Exception as exc:  # a failed run is a result too: record why, keep the API alive
            info.status, info.error = RunStatus.FAILED, f"{type(exc).__name__}: {exc}"
            log_event("run.failed", run_id=run_id, error=info.error)
            bus.publish(run_id, EventType.RUN_FAILED, data={"error": info.error})
        finally:
            info.finished_at = datetime.now(timezone.utc)
            close = getattr(llm, "aclose", None)
            if close:
                await close()
