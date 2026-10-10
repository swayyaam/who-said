# AgntID policies for WhoSaid

**Status: draft.** These were written before the AgntID docs were available locally. Phase c
aligns them with the portal's real formats.

What is here:

| File | What it is |
|---|---|
| `whosaid.rego` | The permission policy as OPA Rego (custom rule). Logic final, syntax/`input` shape provisional. |
| `input-constraints.md` | The per-tool input constraints to set in the portal. |
| `../backend/tests/policy_oracle.py` | The same policy in plain Python. Tests only: it is the answer key, never the enforcement path. |

## The policy

1. **Unknown sender:** no write actions (`reply`, `forward_message`, `create_calendar_event`, `pay_upi`). `block_sender` is allowed.
2. **Known contact:** `reply`, `create_calendar_event`, and `forward_message` -- but only to one of the user's existing contacts (`allowed_recipients`) and never OTP-like content.
3. **Group admin or verified business** (with an existing relationship): the above plus `pay_upi`, only to the sender's **registered payee** and only up to **10,000 INR**.
4. **`update_preferences`** is denied whenever the call originates from an incoming message (always, for the agent). The user changes preferences through their own API, which is not an MCP tool.
5. **`read_otp_messages`** is denied for everyone. **Forwarding OTP-looking content** is denied for everyone.

Every decision carries a human-readable reason, e.g. `DENIED pay_upi: sender unknown, write actions not permitted`.

## Where the trust values come from

The sender's trust level and payee are computed **in code from data** (`backend/whosaid/trust/`) and
injected as tool arguments by the agent loop *after* the model proposes a call. The model never
sees or sets them (tested in `backend/tests/test_agent_loop.py`). Tool arguments the policies can read:

`sender_trust`, `registered_payee`, `allowed_recipients`, `sender_id`, `user_id`, `message_id`.

## Applying in the AgntID portal

To be completed in phase c once the runtime is connected:

1. Attach the WhoSaid MCP server (`http://host.docker.internal:8765/mcp`) to the runtime.
2. Set the per-tool input constraints from `input-constraints.md`.
3. Add `whosaid.rego` as a custom Rego rule.
4. Check **Reporting** for a decision on each call.
