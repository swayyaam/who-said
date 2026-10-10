# AgntID configuration for WhoSaid

Everything below is applied in the AgntID portal and is live on the runtime. `backend/tests/policy_oracle.py`
states the same rules in Python as an **answer key for tests only**; it is never the enforcement path.

## Three AgntID layers

| Layer | What it does | WhoSaid use |
|---|---|---|
| **profile** | The runtime's protection profile decides which tools exist | Medium. `read_otp_messages` is **excluded** (its accurate label includes credential access) |
| **policy** | A per-tool Rego policy checks each call's arguments | One policy per exposed tool (below) |
| **intent** | The intent check compares each call with the task we open | Task intent is built from trusted data only (`backend/whosaid/agent/intent.py`) |

Every decision records its layer (`profile` / `policy` / `intent`); results and summaries count denials per layer.

## The permission policy

1. **Unknown sender:** no write actions (`reply`, `forward_message`, `create_calendar_event`, `pay_upi`). `block_sender` is allowed.
2. **Known contact:** `reply`, `create_calendar_event`, and `forward_message` only to one of the user's existing contacts (`allowed_recipients`) and never OTP-like content.
3. **Group admin or verified business:** the above plus `pay_upi`, only to the sender's **registered payee**, and only while the **cumulative total paid to that payee** (this payment plus `paid_today_to_payee` from the ledger) stays within **10,000 INR**, so splitting a payment cannot get around the limit.
4. **`update_preferences`** is denied whenever the call originates from an incoming message (always, for the agent).
5. **`read_otp_messages`** is never available to the agent (profile layer).

The trust level, registered payee and contact list are computed **in code from data** and injected as tool arguments after the model proposes a call. The model never sees or sets them (tested): `sender_trust`, `registered_payee`, `allowed_recipients`, `paid_today_to_payee`, `sender_id`, `user_id`, `message_id`.

Denials never reach the model: it is told only "This action is not permitted." (it talks to the sender, so policy details must not leak), and the system prompt forbids mentioning limits or suggesting workarounds. The full AgntID reason and our readable label go to results, the dashboard and logs.

## What is configured in the portal

**Server** (Runtime → Operations → MCP → Servers → Add MCP): Remote HTTP, Server ID `whosaid`, Prefix `whosaid`, URL `http://host.docker.internal:8765/mcp`, credential `bearer_token` = `${WHOSAID_TOOL_SECRET}` (an env var on the runtime container, see `docs`/backend README).

**Tool classifications** (Access Control → Advanced → Action Classifications). Labels are accurate; the profile choice follows from them:

| Tool | Operation | Effects | Under Medium |
|---|---|---|---|
| `pay_upi` | WRITE | WRITE, EXTERNAL_SERVICE_CALL | exposed |
| `forward_message` | WRITE | WRITE, NETWORK_EGRESS, DATA_EXFILTRATION | exposed |
| `reply` | WRITE | WRITE, NETWORK_EGRESS | exposed |
| `block_sender` | WRITE | WRITE, STATE_PERSISTENCE | exposed |
| `create_calendar_event` | CREATE | WRITE, STATE_PERSISTENCE | exposed |
| `update_preferences` | WRITE | WRITE, STATE_PERSISTENCE (+READ) | exposed |
| `read_otp_messages` | READ | READ, CREDENTIAL_ACCESS | **excluded by profile** |

**Policies** (Access Control → Access Policies → whosaid → pick the tool → Advanced (Rego)): paste each file from `rego/`, set **Priority 10**, Validate, Save. Each tool also has an auto-created *Baseline allow* policy at priority 1; only the highest-priority policy applies, so the Rego policy must outrank it. (`forward_message` was re-saved at priority 20 after its argument became a comma-separated string.)

Notes learned while applying them:
* The runtime validates arguments against the tool schema and types every parameter as a string, so list values are passed comma-separated.
* The runtime fills omitted optional arguments with `null`; tool parameters accept `None`.
* A custom Rego denial carries only "Policy evaluation denied the request". WhoSaid attaches a readable reason on its side (`backend/whosaid/authz/explain.py`); AgntID's allow/deny stays the source of truth.
* The portal's *Simulate Policy* needs an LLM credential in AgntID. Instead, `backend/tests/live_prove_policies.py` sends one allowed and one denied call per tool through the real runtime and checks each against the oracle.

## Verify

```bash
cd backend
PYTHONPATH=tests python tests/live_prove_policies.py   # 15 calls through the real runtime vs the oracle
PYTHONPATH=tests python tests/live_check_demo.py       # whole demo with AgntID ON, every decision vs the oracle
```
