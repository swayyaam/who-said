"""The FastAPI app. Endpoints (all JSON unless noted; see backend/README.md for request/response examples):

    GET    /health
    GET    /datasets                      POST /datasets (multipart upload of CSVs)       GET /datasets/{id}
    POST   /runs {dataset_id, enforcement, live?, concurrency?, only?}   GET /runs   GET /runs/{id}
    GET    /runs/{id}/events              (Server-Sent Events: run.started ... run.completed)
    GET    /runs/compare?off=&on=
    POST   /reset
    GET    /users/{id}/preferences        PUT /users/{id}/preferences
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from whosaid import __version__
from whosaid.api.backend import Backend, LiveBackend
from whosaid.api.runner import execute_run
from whosaid.api.state import AppState
from whosaid.config import Settings, load_settings
from whosaid.datasets import DatasetRegistry, preview
from whosaid.errors import DatasetError
from whosaid.logging_setup import setup_logging
from whosaid.profile import Preferences
from whosaid.runs import RunStatus, build_comparison
from whosaid.schemas import Enforcement

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SSE_KEEPALIVE_SECONDS = 15


class RunRequest(BaseModel):
    dataset_id: str
    enforcement: Enforcement
    live: bool | None = Field(None, description="True calls the model. False replays the committed demo fixture (demo dataset only). "
                                                "Omitted: the server's DEFAULT_LIVE setting (false unless started with demo.sh --live).")
    concurrency: int | None = Field(None, ge=1, le=8)
    only: list[str] | None = Field(None, description="Run just these message ids")


def _sse(event) -> str:
    return f"id: {event.seq}\nevent: {event.type.value}\ndata: {event.model_dump_json()}\n\n"


def create_app(settings: Settings | None = None, backend: Backend | None = None) -> FastAPI:
    settings = settings or load_settings()
    backend = backend or LiveBackend(settings)
    state = AppState(settings=settings, backend=backend, datasets=DatasetRegistry())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await asyncio.to_thread(backend.start)
        try:
            yield
        finally:
            for task in list(state.tasks):
                task.cancel()
            await asyncio.to_thread(backend.stop)

    app = FastAPI(title="WhoSaid API", version=__version__, lifespan=lifespan)
    app.state.whosaid = state
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"], allow_headers=["*"],
    )

    # ---- health ----------------------------------------------------------------------------

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__, **await asyncio.to_thread(backend.health)}

    # ---- datasets --------------------------------------------------------------------------

    @app.get("/datasets")
    async def list_datasets() -> list[dict[str, Any]]:
        return [i.model_dump() for i in state.datasets.infos()]

    @app.post("/datasets", status_code=201)
    async def upload_dataset(files: Annotated[list[UploadFile], File(description="the dataset's CSV files")],
                             name: Annotated[str | None, Form()] = None) -> dict[str, Any]:
        blobs: dict[str, bytes] = {}
        for f in files:
            data = await f.read()
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, detail=f"{f.filename} is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
            blobs[f.filename or f"file{len(blobs)}.csv"] = data
        try:
            dataset = state.datasets.add_upload(blobs, name=name)
        except DatasetError as exc:
            raise HTTPException(422, detail={"message": str(exc), "problems": exc.problems}) from exc
        return state.datasets.info(dataset).model_dump()

    @app.get("/datasets/{dataset_id}")
    async def get_dataset(dataset_id: str) -> dict[str, Any]:
        dataset = state.datasets.get(dataset_id)
        if dataset is None:
            raise HTTPException(404, detail=f"no dataset {dataset_id!r}")
        info = state.datasets.info(dataset).model_dump()
        return {**info, "message_list": [m.model_dump() for m in preview(dataset)]}

    # ---- runs ------------------------------------------------------------------------------

    @app.post("/runs", status_code=202)
    async def start_run(req: RunRequest) -> dict[str, Any]:
        dataset = state.datasets.get(req.dataset_id)
        if dataset is None:
            raise HTTPException(404, detail=f"no dataset {req.dataset_id!r}")
        has_fixture = state.datasets.fixture_dir(req.dataset_id) is not None
        requested = settings.default_live if req.live is None else req.live
        live = requested or not has_fixture  # only the built-in datasets have a fixture; anything else needs the model
        if req.enforcement is Enforcement.ON:
            health_ = await asyncio.to_thread(backend.health)
            if not health_.get("agntid", {}).get("reachable", True):
                raise HTTPException(503, detail=f"the AgntID runtime is not reachable at {health_['agntid']['endpoint']}")
        only = set(req.only) if req.only else None
        unknown = (only or set()) - {m.message_id for m in dataset.messages}
        if unknown:
            raise HTTPException(422, detail=f"unknown message ids: {sorted(unknown)}")
        total = len(only) if only else len(dataset.messages)
        record = state.runs.create(dataset_id=req.dataset_id, dataset_name=dataset.name, enforcement=req.enforcement,
                                   live=live, model=settings.llm_model, total=total)
        task = asyncio.create_task(execute_run(state, record, dataset, concurrency=req.concurrency, only=only))
        state.tasks.add(task)
        task.add_done_callback(state.tasks.discard)
        return {"run_id": record.info.run_id, "status": record.info.status, "live": live, "messages_total": total}

    @app.get("/runs")
    async def list_runs() -> list[dict[str, Any]]:
        return [i.model_dump(mode="json") for i in state.runs.list()]

    # NOTE: /runs/compare must be declared before /runs/{run_id}
    @app.get("/runs/compare")
    async def compare_runs(off: str = Query(..., description="run id of the AgntID OFF run"),
                           on: str = Query(..., description="run id of the AgntID ON run")) -> dict[str, Any]:
        off_run, on_run = state.runs.get(off), state.runs.get(on)
        for rid, rec in ((off, off_run), (on, on_run)):
            if rec is None:
                raise HTTPException(404, detail=f"no run {rid!r}")
            if rec.info.status != RunStatus.COMPLETED or rec.summary is None:
                raise HTTPException(409, detail=f"run {rid} is {rec.info.status}; compare needs completed runs")
        assert off_run and on_run
        if off_run.info.enforcement is not Enforcement.OFF or on_run.info.enforcement is not Enforcement.ON:
            raise HTTPException(422, detail="'off' must be an enforcement=off run and 'on' an enforcement=on run")
        if off_run.info.dataset_id != on_run.info.dataset_id:
            raise HTTPException(422, detail="the two runs used different datasets")
        return build_comparison(off_run, on_run)

    @app.get("/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        record = state.runs.get(run_id)
        if record is None:
            raise HTTPException(404, detail=f"no run {run_id!r}")
        return record.detail()

    @app.get("/runs/{run_id}/events")
    async def run_events(run_id: str, request: Request, after: int | None = Query(None, description="resume after this seq")) -> StreamingResponse:
        if state.runs.get(run_id) is None:
            raise HTTPException(404, detail=f"no run {run_id!r}")
        last_event_id = request.headers.get("last-event-id")
        after_seq = after if after is not None else (int(last_event_id) if last_event_id and last_event_id.isdigit() else -1)

        async def stream():
            backlog, queue, finished = state.bus.connect(run_id, after_seq)
            try:
                for event in backlog:
                    yield _sse(event)
                if finished:
                    return
                while True:
                    try:
                        item = await asyncio.wait_for(queue.get(), SSE_KEEPALIVE_SECONDS)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    if item is None:
                        return
                    yield _sse(item)
            finally:
                state.bus.disconnect(run_id, queue)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})

    # ---- reset -----------------------------------------------------------------------------

    @app.post("/reset", status_code=204)
    async def reset(clear_datasets: bool = Query(False, description="also forget uploaded datasets (the demo always stays)")) -> Response:
        if state.lock.locked():
            raise HTTPException(409, detail="a run is in progress; wait for it to finish")
        for run_id in state.runs.clear():
            state.bus.drop(run_id)
        await asyncio.to_thread(backend.admin.reset)
        if clear_datasets:
            state.datasets.clear_uploads()
        return Response(status_code=204)

    # ---- explicit preferences (the user's own path; the agent cannot reach it) -------------------

    @app.get("/users/{user_id}/preferences")
    async def get_preferences(user_id: str) -> dict[str, Any]:
        try:
            return (await asyncio.to_thread(backend.admin.get_preferences, user_id)).model_dump()
        except Exception as exc:
            raise HTTPException(503, detail=f"tool server unavailable: {type(exc).__name__}") from exc

    @app.put("/users/{user_id}/preferences")
    async def put_preferences(user_id: str, prefs: Preferences) -> dict[str, Any]:
        try:
            return (await asyncio.to_thread(backend.admin.put_preferences, user_id, prefs)).model_dump()
        except Exception as exc:
            raise HTTPException(503, detail=f"tool server unavailable: {type(exc).__name__}") from exc

    return app


def run() -> None:  # python -m whosaid.api
    import uvicorn

    settings = load_settings()
    setup_logging(settings.log_level)
    uvicorn.run(create_app(settings), host=settings.api_host, port=settings.api_port, log_level="info")
