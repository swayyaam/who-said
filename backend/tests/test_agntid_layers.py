"""The ON-mode plumbing without a live runtime: layers, intent, denial classification, and the no-bypass guarantee."""

import json

import pytest

from conftest import OracleGateway, ScriptedLLM, final, tool_calls
from whosaid.agent.agntid_gateway import AgntIDGateway, classify_denial
from whosaid.agent.gateways import gateway_factory
from whosaid.agent.intent import build_task_intent
from whosaid.agent.tool_gateway import DirectGateway
from whosaid.authz.explain import explain_denial, profile_exclusion_reason
from whosaid.config import Settings, direct_access_secret
from whosaid.pipeline import run_dataset
from whosaid.router import route
from whosaid.schemas import DecisionLayer, Enforcement
from whosaid.summary import summarize
from whosaid.tool_contract import TOOL_NAMES, is_platform_param, model_visible_input_schema
from whosaid.tool_manifest import build_manifest, load_manifest


def test_classify_denial_layers():
    assert classify_denial({"denial_step": "policy_evaluation"}) is DecisionLayer.POLICY
    assert classify_denial({"denial_step": "intent_check"}) is DecisionLayer.INTENT
    assert classify_denial({"intent_mismatch": "send is not in the request"}) is DecisionLayer.INTENT
    assert classify_denial(None) is DecisionLayer.POLICY


def test_explain_denial_gives_readable_reasons():
    unknown = {"sender_trust": "unknown"}
    assert explain_denial("pay_upi", unknown) == "DENIED pay_upi: sender unknown, write actions not permitted"
    admin = {"sender_trust": "group_admin", "registered_payee": "a@b", "payee_upi": "c@d", "amount_inr": 5}
    assert "does not match the sender's registered payee" in explain_denial("pay_upi", admin)
    assert "exceeds the limit" in explain_denial("pay_upi", {**admin, "payee_upi": "a@b", "amount_inr": 25000})
    assert "never by an incoming message" in explain_denial("update_preferences", {"message_id": "m1"})
    assert explain_denial("reply", {"sender_trust": "known_contact"}) is None  # nothing to explain: not a denial we know
    assert profile_exclusion_reason("read_otp_messages") == "read_otp_messages not exposed: credential access excluded by AgntID Medium profile"


def test_intent_is_built_from_trusted_data_and_never_includes_message_text(demo, trust_of):
    msg = next(m for m in demo.messages if m.message_id == "msg_201")
    routing = route(msg, trust_of("msg_201"), demo)
    intent = build_task_intent(trust_of("msg_201"), routing)
    assert intent.startswith("Triage a message from an unknown sender. Only mute, digest, or block.")
    assert "OTP" not in intent and "WhatsApp support" not in intent and "+91" not in intent
    friend = build_task_intent(trust_of("msg_205"))
    assert "known contact" in friend and "May reply and add calendar events." in friend


def test_platform_params_are_hidden_from_the_model():
    schema = {"type": "object", "properties": {"text": {"type": "string"}, "agntid_task_id": {"type": "string"},
                                              "_task_id": {"type": "string"}, "sender_trust": {"type": "string"}}, "required": ["text"]}
    assert set(model_visible_input_schema(schema)["properties"]) == {"text"}
    assert is_platform_param("agntid_approval") and not is_platform_param("text")


async def test_manifest_matches_the_live_server():
    current = await build_manifest()
    assert [d["name"] for d in current] == sorted(TOOL_NAMES)
    bundled = [d.model_dump(exclude={"exposed", "excluded_reason"}) for d in load_manifest()]
    assert bundled == current, "tool_manifest.json is stale: run `python -m whosaid.tool_manifest`"


# ---- the ON path never touches the tool server or the direct secret ------------------------------


def test_on_mode_factory_holds_only_the_agntid_endpoint(monkeypatch):
    sentinel = "DIRECT-SENTINEL-SECRET"
    monkeypatch.setenv("DIRECT_ACCESS_SECRET", sentinel)
    settings = Settings(mcp_server_url="http://tool-server.invalid:9/mcp", agntid_mcp_url="http://runtime.invalid:8082/mcp",
                        tool_server_secret="TOOL-SERVER-SENTINEL")
    gw = gateway_factory(settings, Enforcement.ON)()
    assert isinstance(gw, AgntIDGateway)
    blob = repr(vars(gw)) + repr(vars(gw._client)) + repr(getattr(gw._client._client, "transport", ""))
    assert "tool-server.invalid" not in blob and sentinel not in blob and "TOOL-SERVER-SENTINEL" not in blob
    assert "runtime.invalid" in blob


def test_direct_secret_is_only_loaded_when_enforcement_is_off(monkeypatch):
    monkeypatch.setenv("DIRECT_ACCESS_SECRET", "s3cret")
    assert direct_access_secret(Enforcement.OFF) == "s3cret"
    assert direct_access_secret(Enforcement.ON) == ""


def test_the_direct_gateway_is_the_only_one_that_takes_the_tool_server_url():
    import inspect

    assert "url" in inspect.signature(AgntIDGateway.__init__).parameters  # the AgntID endpoint
    src = inspect.getsource(AgntIDGateway)
    for forbidden in ("mcp_server_url", "DIRECT_ACCESS_SECRET", "tool_server_secret", "direct_access_secret", "DirectGateway"):
        assert forbidden not in src


async def test_on_run_never_reads_the_direct_secret_or_tool_server_url(demo, server, settings, monkeypatch):
    """Run ON with a recording environment: the direct secret must never be read while enforcement is ON."""
    reads = []
    real_get = __import__("os").environ.get

    def spy(key, *a):
        if key == "DIRECT_ACCESS_SECRET":
            reads.append(key)
        return real_get(key, *a)

    monkeypatch.setattr("os.environ.get", spy)
    llm = ScriptedLLM(lambda m, t: final())
    await run_dataset(demo, llm=llm, gateway_factory=lambda: OracleGateway(server), settings=settings, only={"msg_203"})
    gateway_factory(Settings(), Enforcement.ON)  # building the ON factory reads nothing either
    assert reads == []


# ---- layered results and the summary ------------------------------------------------------------


async def test_denials_are_counted_per_layer(demo, server, store, settings):
    def script(messages, tools):
        if messages[-1]["role"] != "user":
            return final()
        return tool_calls(("read_otp_messages", {}), ("forward_message", {"to": "+91 98110 22334", "content": "otp"}))

    results = await run_dataset(demo, llm=ScriptedLLM(script), gateway_factory=lambda: OracleGateway(server), settings=settings, only={"msg_201"})
    attempts = results[0].agent.attempts
    assert [(a.call.tool, a.decision.layer.value) for a in attempts] == [("read_otp_messages", "profile"), ("forward_message", "policy")]
    assert "not exposed: credential access excluded by AgntID Medium profile" in attempts[0].decision.reason
    summary = summarize(results, enforcement=Enforcement.ON)
    assert summary.denials_by_layer == {"profile": 1, "policy": 1, "intent": 0}
    assert summary.harmful_executed == 0 and store.snapshot().ledger == []   # nothing executed on the tool server


async def test_the_model_is_shown_the_hidden_tool_too(demo, server, settings):
    llm = ScriptedLLM(lambda m, t: final())
    await run_dataset(demo, llm=llm, gateway_factory=lambda: OracleGateway(server), settings=settings, only={"msg_201"})
    names = [t["function"]["name"] for t in llm.seen_tools[0]]
    assert "read_otp_messages" in names and names == sorted(names)
