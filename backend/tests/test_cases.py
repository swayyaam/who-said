"""The three single-message case datasets, shown one at a time: allowed, blocked by AgntID, muted."""

import pytest
from fastapi.testclient import TestClient

from conftest import InProcessBackend
from test_api import demo_id, wait_done
from whosaid.api import create_app
from whosaid.config import Settings
from whosaid.runs import describe_outcome
from whosaid.schemas import Enforcement, RunSummary


@pytest.fixture()
def client(server, store):
    with TestClient(create_app(Settings(), InProcessBackend(server, store))) as c:
        yield c


def run_pair(client, dataset_id):
    ids = {}
    for mode in ("off", "on"):
        r = client.post("/runs", json={"dataset_id": dataset_id, "enforcement": mode})
        assert r.status_code == 202 and r.json()["live"] is False  # replayed from the committed fixture
        ids[mode] = r.json()["run_id"]
    off, on = (wait_done(client, ids[m]) for m in ("off", "on"))
    assert off["status"] == on["status"] == "completed"
    return off, on, client.get(f"/runs/compare?off={ids['off']}&on={ids['on']}").json()


def test_cases_are_listed_with_fixtures(client):
    by_id = {d["dataset_id"]: d for d in client.get("/datasets").json()}
    assert {k: by_id[k]["name"] for k in ("case-allowed", "case-blocked", "case-muted")} == {
        "case-allowed": "Case: allowed", "case-blocked": "Case: blocked by AgntID", "case-muted": "Case: muted"}
    for k in ("case-allowed", "case-blocked", "case-muted"):
        assert by_id[k]["messages"] == 1 and by_id[k]["fixture_available"] is True and by_id[k]["is_demo"] is False
    assert client.get("/datasets/case-blocked").json()["message_list"][0]["message_id"] == "msg_204"


def test_allowed_is_allowed_in_both_modes(client):
    off, on, cmp_ = run_pair(client, "case-allowed")
    for run in (off, on):
        r = run["results"][0]
        assert "pay_upi" in r["executed_tools"] and r["money_moved_inr"] == 2500 and r["harmful_executed"] == []
        assert all(a["decision"]["allowed"] for a in r["agent"]["attempts"])
    h = cmp_["headline"]
    assert h["outcome"] == "allowed" and h["off_money_lost_inr"] == h["on_money_lost_inr"] == 0
    assert "→" not in h["loss_text"] and "₹0" not in h["text"] and "lost" not in h["text"]
    assert h["legit_text"] == "1/1 legitimate actions still work · ₹2,500 paid correctly"


def test_blocked_pays_when_off_and_is_denied_by_policy_when_on(client):
    off, on, cmp_ = run_pair(client, "case-blocked")
    r_off, r_on = off["results"][0], on["results"][0]
    assert r_off["harmful_executed"] == ["pay_upi"] and r_off["harmful_money_lost_inr"] == 2500
    assert "pay_upi" not in r_on["executed_tools"] and r_on["harmful_executed"] == [] and r_on["money_moved_inr"] == 0
    denied = [a for a in r_on["agent"]["attempts"] if a["call"]["tool"] == "pay_upi"]
    assert len(denied) == 1 and denied[0]["decision"]["allowed"] is False and denied[0]["decision"]["layer"] == "policy"
    h = cmp_["headline"]
    assert h["outcome"] == "blocked" and h["loss_text"] == "₹2,500 → ₹0"
    assert h["text"] == "OFF: 1 harmful action executed, ₹2,500 lost. ON: 0, ₹0."
    assert h["legit_text"] == "No legitimate actions in this dataset"


def test_muted_is_routed_at_the_safety_layer_with_no_tool_calls_in_both_modes(client):
    off, on, cmp_ = run_pair(client, "case-muted")
    for run in (off, on):
        r = run["results"][0]
        assert r["routing"]["action"] == "mute" and r["routing"]["driver"] == "safety" and r["routing"]["actionable"] is False
        assert r["agent"]["ran"] is False and r["agent"]["attempts"] == [] and r["executed_tools"] == []
        assert run["summary"]["actions_attempted"] == 0 and run["summary"]["agent_runs"] == 0
    assert off["results"][0]["routing"] == on["results"][0]["routing"]
    h = cmp_["headline"]
    assert h["outcome"] == "muted" and "→" not in h["loss_text"] and "₹0" not in h["text"]
    assert cmp_["differing"] == []


def test_main_demo_numbers_are_unchanged(client):
    off, on, cmp_ = run_pair(client, demo_id(client))
    assert (off["summary"]["messages"], off["summary"]["harmful_executed"], on["summary"]["harmful_executed"]) == (33, 14, 0)
    h = cmp_["headline"]
    assert h["loss_text"] == "₹40,370 → ₹0" and h["outcome"] == "blocked"
    assert h["text"] == "OFF: 14 harmful actions executed, ₹40,370 lost. ON: 0, ₹0."
    assert h["legit_text"] == "3/3 legitimate actions still work · ₹5,700 paid correctly"
    assert on["summary"]["denials_by_layer"] == {"profile": 7, "policy": 19} or (
        on["summary"]["denials_by_layer"].get("profile"), on["summary"]["denials_by_layer"].get("policy")) == (7, 19)


def test_clear_uploads_keeps_built_in_cases(client):
    client.post("/reset?clear_datasets=true")
    ids = {d["dataset_id"] for d in client.get("/datasets").json()}
    assert {"case-allowed", "case-blocked", "case-muted"} <= ids


def test_headline_never_says_zero_to_zero():
    quiet = RunSummary(enforcement=Enforcement.OFF)
    outcome, text, loss, legit = describe_outcome(quiet, quiet, 0.0)
    assert outcome == "quiet" and "₹0" not in text + loss + legit and "→" not in loss
