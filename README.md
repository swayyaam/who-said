<p align="center">
  <img src="frontend/public/banner.jpg" alt="WhoSaid: It's not what the message says. It's who said it." width="100%">
</p>

<p align="center">
  <img src="frontend/public/icon.png" alt="WhoSaid logo" width="96" height="96">
</p>

<h1 align="center">WhoSaid</h1>

<p align="center"><i>It's not what the message says. It's who said it.</i></p>

An AI agent for WhatsApp that acts on messages, with AgntID enforcing what each sender can make it do.

| Demo run | AgntID OFF | AgntID ON |
|---|---|---|
| Harmful actions executed | 14 | **0** |
| Money lost | ₹40,370 | **₹0** |
| Legitimate actions working | 3/3 | 3/3 (₹5,700 paid correctly) |
| Blocked by AgntID layer (profile / policy) | none | 7 / 19 |

**Quick start:** `./scripts/demo.sh` starts everything and opens the dashboard. Details in [Running the demo](#running-the-demo).

---

## Repository layout

- `backend/`: the agent, the MCP tool server and the API.
- `frontend/`: the dashboard.
- `policies/`: the AgntID Rego policies, matching what is applied in the portal.
- `scripts/`: the demo launcher (`demo.sh`, `stop.sh`).

## Running the demo

macOS, one command:

```bash
scripts/demo.sh            # start everything, reset demo state, open the dashboard
scripts/demo.sh --live     # demo runs use the live model instead of the recorded fixture
scripts/demo.sh --mock     # frontend only, on mock data (no Docker, runtime, tool server or API)
scripts/demo.sh --detach   # return once everything is up instead of staying in the foreground
scripts/demo.sh --no-open  # do not open the browser
scripts/stop.sh            # stop tool server, API and frontend
scripts/stop.sh --all      # also stop Ollama (if demo.sh started it) and the AgntID runtime
```

`demo.sh` starts Docker Desktop, the AgntID runtime (`~/agntid-runtime`), Ollama (warn only if
missing), the tool server (:8765), the API (:8000) and the frontend (:5173), checks each one,
resets demo state and prints a status table. It is idempotent: healthy services are reused, and
if a port is held by something unhealthy it names the process and stops. In the foreground,
Ctrl+C stops the tool server, API and frontend; the Docker runtime stays up.

Prerequisites: Docker Desktop, the AgntID runtime set up in `~/agntid-runtime`, `backend/.env`
filled in (see `backend/.env.example`), `backend/.venv`, and `npm install` in `frontend/`.

Logs and PID files are in `logs/` (gitignored). Set `DEMO_WEB_PORT` to use a different frontend
port. A frontend you started yourself is reused as-is (its data mode is not known to the script).
