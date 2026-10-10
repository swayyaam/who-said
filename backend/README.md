# WhoSaid backend

Sender-trust-aware message routing and action agent, with every tool call gated by AgntID. (Full README in phase e.)

## Security model: no bypass

* In **ON** mode the agent talks only to the AgntID runtime endpoint (`AGNTID_MCP_URL`, default `http://localhost:8082/mcp`).
  `AgntIDGateway` never receives the tool server's URL or secret, and `DIRECT_ACCESS_SECRET` is read only when enforcement is OFF
  (tests: `tests/test_agntid_layers.py`).
* The tool server's `/mcp` endpoint requires a bearer secret. The AgntID runtime sends `TOOL_SERVER_SECRET`
  (portal credential `bearer_token = ${WHOSAID_TOOL_SECRET}`, an environment variable on the runtime container, set via
  a Compose override). A caller without it gets 401, so the tool server cannot be reached around AgntID.
* The **OFF** demo path uses a separate `DIRECT_ACCESS_SECRET`, honoured by the tool server **only** when `DEMO_ALLOW_DIRECT=true`.
  **Production requirement:** leave `DEMO_ALLOW_DIRECT` unset (and `DIRECT_ACCESS_SECRET` empty) so the only way in is through AgntID.
* Deployment requirement: bind the tool server to loopback or a private network; `/_admin/*` (reset, state, preferences) is the user's
  own API, is not an MCP tool, and is not covered by the secret, so do not expose that port publicly.

See `../policies/README.md` for the AgntID configuration.
