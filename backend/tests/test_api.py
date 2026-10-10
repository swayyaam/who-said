"""Every API endpoint, through FastAPI's TestClient, against in-process doubles (demo fixture, no model, no network)."""

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import InProcessBackend
from whosaid.api import create_app
from whosaid.config import DEMO_DATA_DIR, Settings


@pytest.fixture()
def client(server, store):
    app = create_app(Settings(), InProcessBackend(server, store))
    with TestClient(app) as c:
        yield c


def wait_done(client, run_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        detail = client.get(f"/runs/{run_id}").json()
        if detail["status"] in ("completed", "failed"):
            return detail
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def demo_id(client):
    return next(d["dataset_id"] for d in client.get("/datasets").json() if d["is_demo"])


def test_health_and_cors(client):
    body = client.get("/health").json()
    assert body["ok"] and body["agntid"]["reachable"] and body["llm"]["model"]
    pre = client.options("/runs", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert pre.headers["access-control-allow-origin"] == "http://localhost:5173"
    other = client.options("/runs", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in other.headers


def test_list_and_get_datasets(client):
    datasets = client.get("/datasets").json()
    demo = next(d for d in datasets if d["is_demo"])
    assert demo["name"] == "demo" and demo["messages"] == 33 and demo["attacks"] == 10 and demo["controls"] == 3
    assert demo["fixture_available"] is True
    full = client.get(f"/datasets/{demo['dataset_id']}").json()
    assert len(full["message_list"]) == 33 and full["message_list"][-1]["scenario"]
    assert client.get("/datasets/nope").status_code == 404


def test_upload_dataset_ok_and_errors(client):
    files = [("files", (p.name, p.read_bytes(), "text/csv")) for p in Path(DEMO_DATA_DIR).glob("*.csv")]
    ok = client.post("/datasets", files=files, data={"name": "my-upload"})
    assert ok.status_code == 201
    assert ok.json()["dataset_id"] == demo_id(client)   # identical content is recognised as the demo, not duplicated
    bad = client.post("/datasets", files=[("files", ("messages.csv", b"message_id,user_id\nm1,u1\n", "text/csv"))])
    assert bad.status_code == 422
    detail = bad.json()["detail"]
    assert detail["problems"] and any("required file is missing" in p for p in detail["problems"])


def test_run_off_streams_events_and_returns_layered_results(client):
    did = demo_id(client)
    start = client.post("/runs", json={"dataset_id": did, "enforcement": "off"})
    assert start.status_code == 202
    body = start.json()
    assert body["live"] is False and body["messages_total"] == 33
    detail = wait_done(client, body["run_id"])
    assert detail["status"] == "completed"

    s = detail["summary"]
    assert (s["messages"], s["harmful_executed"], s["controls_ok"]) == (33, 13, 3)
    assert s["denials_by_layer"] == {"profile": 0, "policy": 0, "intent": 0}
    assert detail["tool_server"]["paid_out_inr"] == s["total_money_moved_inr"]
    assert [c["user_id"] for c in detail["preference_changes"]] == ["u_101"]   # the tampering attack, visible

    # model-proposed and code-injected arguments are separate fields; the deciding layer is on every routing decision
    msg = next(r for r in detail["results"] if r["message_id"] == "msg_204")
    attempt = next(a for a in msg["agent"]["attempts"] if a["call"]["tool"] == "pay_upi")
    assert set(attempt["call"]["model_args"]) <= {"payee_upi", "amount_inr", "note"}
    assert attempt["call"]["trusted_args"]["sender_trust"] == "group_admin"
    assert attempt["call"]["trusted_args"]["registered_payee"] == "maple.rwa@okhdfc"
    assert msg["routing"]["driver"] in {"safety", "preference", "learned", "default"}
    assert all("denials_by_layer" in r for r in detail["results"])


def test_run_on_blocks_attacks_and_counts_layers(client):
    did = demo_id(client)
    rid = client.post("/runs", json={"dataset_id": did, "enforcement": "on"}).json()["run_id"]
    detail = wait_done(client, rid)
    s = detail["summary"]
    assert s["harmful_executed"] == 0 and s["harmful_money_lost_inr"] == 0 and s["controls_ok"] == 3
    assert s["denials_by_layer"]["profile"] >= 1 and s["denials_by_layer"]["policy"] >= 1
    otp = next(r for r in detail["results"] if r["message_id"] == "msg_201")
    layers = {a["call"]["tool"]: a["decision"]["layer"] for a in otp["agent"]["attempts"]}
    assert layers["read_otp_messages"] == "profile" and layers["forward_message"] == "policy"
    assert otp["denials_by_layer"] == {"profile": 1, "policy": 1}
    assert detail["preference_changes"] == []


def test_sse_replays_the_whole_run_in_order(client):
    did = demo_id(client)
    rid = client.post("/runs", json={"dataset_id": did, "enforcement": "off", "only": ["msg_203", "msg_205"]}).json()["run_id"]
    wait_done(client, rid)
    with client.stream("GET", f"/runs/{rid}/events") as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        raw = "".join(resp.iter_text())
    events = [json.loads(block.split("data: ", 1)[1]) for block in raw.split("\n\n") if "data: " in block]
    types = [e["type"] for e in events]
    assert types[0] == "run.started" and types[-1] == "run.completed"
    assert [e["seq"] for e in events] == list(range(len(events)))
    for t in ("message.started", "message.routed", "agent.step", "tool.attempted", "authz.decision", "tool.executed", "message.completed"):
        assert t in types
    assert f"event: {types[0]}" in raw and "id: 0" in raw
    # resume: only events after seq 5
    with client.stream("GET", f"/runs/{rid}/events?after=5") as resp:
        resumed = [json.loads(b.split("data: ", 1)[1]) for b in "".join(resp.iter_text()).split("\n\n") if "data: " in b]
    assert resumed[0]["seq"] == 6 and resumed[-1]["type"] == "run.completed"


def test_compare_headline_includes_legitimate_outcomes(client):
    did = demo_id(client)
    off = client.post("/runs", json={"dataset_id": did, "enforcement": "off"}).json()["run_id"]
    on = client.post("/runs", json={"dataset_id": did, "enforcement": "on"}).json()["run_id"]
    wait_done(client, off)
    wait_done(client, on)
    cmp_ = client.get(f"/runs/compare?off={off}&on={on}").json()
    h = cmp_["headline"]
    assert (h["off_harmful_executed"], h["on_harmful_executed"]) == (13, 0)
    assert h["loss_text"] == "₹37,370 → ₹0"
    assert h["legit_text"] == "3/3 legitimate actions still work · ₹5,700 paid correctly"
    assert h["on_controls_ok"] == 3 and h["on_legit_paid_inr"] == 5700
    assert cmp_["off"]["enforcement"] == "off" and cmp_["on"]["enforcement"] == "on"
    row = next(d for d in cmp_["differing"] if d["message_id"] == "msg_204")
    assert row["off"]["harmful_executed"] == ["pay_upi"] and row["on"]["denied"][0]["layer"] == "policy"
    # argument errors
    assert client.get(f"/runs/compare?off={on}&on={off}").status_code == 422
    assert client.get(f"/runs/compare?off={off}&on=nope").status_code == 404


def test_run_validation_errors(client):
    did = demo_id(client)
    assert client.post("/runs", json={"dataset_id": "nope", "enforcement": "on"}).status_code == 404
    assert client.post("/runs", json={"dataset_id": did, "enforcement": "maybe"}).status_code == 422
    assert client.post("/runs", json={"dataset_id": did, "enforcement": "on", "only": ["msg_nope"]}).status_code == 422
    assert client.get("/runs/nope").status_code == 404
    assert client.get("/runs/nope/events").status_code == 404


def test_on_run_refused_when_the_runtime_is_unreachable(server, store):
    app = create_app(Settings(), InProcessBackend(server, store, agntid_reachable=False))
    with TestClient(app) as c:
        resp = c.post("/runs", json={"dataset_id": demo_id(c), "enforcement": "on"})
        assert resp.status_code == 503 and "AgntID runtime" in resp.json()["detail"]
        assert c.post("/runs", json={"dataset_id": demo_id(c), "enforcement": "off", "only": ["msg_205"]}).status_code == 202


def test_preferences_get_put_and_reset(client):
    prefs = client.get("/users/u_109/preferences").json()
    assert prefs["mute_promotions"] is False and prefs["never_mute_groups"] == []
    body = {**prefs, "mute_promotions": True, "never_mute_groups": ["g_104"], "dnd_window": "22:00-07:00"}
    put = client.put("/users/u_109/preferences", json=body)
    assert put.status_code == 200 and put.json()["never_mute_groups"] == ["g_104"]
    assert client.get("/users/u_109/preferences").json()["dnd_window"] == "22:00-07:00"
    assert client.put("/users/u_109/preferences", json={**body, "mute_promotions": "banana"}).status_code == 422
    assert client.put("/users/u_109/preferences", json={**body, "dnd_window": "late"}).status_code in (200, 422)

    rid = client.post("/runs", json={"dataset_id": demo_id(client), "enforcement": "off", "only": ["msg_205"]}).json()["run_id"]
    wait_done(client, rid)
    assert client.post("/reset").status_code == 204
    assert client.get("/runs").json() == []
    assert client.get(f"/runs/{rid}").status_code == 404
    assert client.get("/users/u_109/preferences").json()["mute_promotions"] is False   # the store was wiped


def test_a_run_changes_preferences_back_to_the_seed(client):
    client.put("/users/u_109/preferences", json={"mute_promotions": False, "never_mute_senders": ["u_999"]})
    rid = client.post("/runs", json={"dataset_id": demo_id(client), "enforcement": "off", "only": ["msg_205"]}).json()["run_id"]
    wait_done(client, rid)
    prefs = client.get("/users/u_109/preferences").json()
    assert prefs["mute_promotions"] is True and prefs["never_mute_senders"] == []   # reseeded from the dataset at run start
