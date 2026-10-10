// Mock mode: serves fixtures recorded from the backend's committed demo cache
// (backend/whosaid/data/demo + LLM fixture). No network, no LLM calls.
import offFixture from "../fixtures/off.json";
import onFixture from "../fixtures/on.json";
import type {
  Dataset, Enforcement, EventType, MessageResult, Preferences, RunComparison, RunDetail, RunEvent, RunSummary,
} from "../types";
import type { WhoSaidApi } from "./types";

const off = offFixture as unknown as RunDetail;
const on = onFixture as unknown as RunDetail;

const DEMO: Dataset = {
  dataset_id: off.summary.dataset_id,
  name: "demo",
  messages: off.summary.messages,
  users: 8,
  attacks: off.results.filter((r) => r.scenario?.kind === "attack").length,
  controls: off.results.filter((r) => r.scenario?.kind === "control").length,
  is_demo: true,
};

const EMPTY_PREFS: Preferences = {
  never_mute_senders: [], never_mute_groups: [], never_mute_businesses: [],
  mute_promotions: false, dnd_window: null, auto_pay_senders: [],
};

interface StoredRun { detail: RunDetail; enforcement: Enforcement }
const runs = new Map<string, StoredRun>();
const prefs = new Map<string, Preferences>();
let counter = 0;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function lastPreferences(r: MessageResult): { user: string; prefs: Preferences } | null {
  const a = r.agent.attempts.find((x) => x.call.tool === "update_preferences" && x.executed);
  const p = a?.result && (a.result as { preferences?: Preferences }).preferences;
  return p ? { user: r.user_id, prefs: p } : null;
}

function buildEvents(runId: string, detail: RunDetail): Omit<RunEvent, "seq" | "ts">[] {
  const ev = (type: EventType, message_id: string | null, data: Record<string, unknown> = {}) =>
    ({ run_id: runId, type, message_id, data });
  const out = [ev("run.started", null, { messages: detail.results.length })];
  detail.results.forEach((r, i) => {
    out.push(ev("message.started", r.message_id, { index: i + 1, total: detail.results.length, text: r.text, user_id: r.user_id }));
    out.push(ev("message.routed", r.message_id, { action: r.routing.action, driver: r.routing.driver }));
    r.agent.attempts.forEach((a) => {
      out.push(ev("tool.attempted", r.message_id, { tool: a.call.tool }));
      out.push(ev("authz.decision", r.message_id, { tool: a.call.tool, allowed: a.decision.allowed, layer: a.decision.layer }));
      if (a.executed) out.push(ev("tool.executed", r.message_id, { tool: a.call.tool, money_moved_inr: a.money_moved_inr, harmful: a.harmful }));
    });
    out.push(ev("message.completed", r.message_id, { index: i + 1, total: detail.results.length }));
  });
  out.push(ev("run.completed", null, {}));
  return out;
}

export const mockApi: WhoSaidApi = {
  mock: true,

  async listDatasets() { await sleep(150); return [DEMO]; },
  async uploadDataset(files) {
    await sleep(600);
    if (!files.some((f) => f.name.toLowerCase().endsWith(".csv"))) throw new Error("Upload at least one .csv file.");
    // Mock mode has one dataset; an upload resolves to it so the flow can be exercised.
    return { ...DEMO, name: `upload (${files.length} file${files.length === 1 ? "" : "s"}) · demo data` };
  },
  async useDemoDataset() { await sleep(250); return DEMO; },

  async startRun(_datasetId, enforcement) {
    await sleep(200);
    prefs.clear(); // each real run reseeds the tool server, so preferences start clean
    const run_id = `mock_${enforcement}_${++counter}`;
    const src = enforcement === "on" ? on : off;
    const detail: RunDetail = {
      status: "completed",
      results: src.results,
      summary: { ...src.summary, run_id },
    };
    runs.set(run_id, { detail, enforcement });
    return { run_id };
  },

  streamEvents(runId, onEvent, onError) {
    const stored = runs.get(runId);
    if (!stored) { queueMicrotask(() => onError(new Error("Unknown run"))); return () => {}; }
    let cancelled = false;
    (async () => {
      const events = buildEvents(runId, stored.detail);
      for (let i = 0; i < events.length; i++) {
        if (cancelled) return;
        const e = events[i];
        onEvent({ ...e, seq: i, ts: new Date().toISOString() });
        // pace per message, not per event, so 33 messages play in ~5s
        if (e.type === "message.completed") await sleep(140);
        else if (e.type === "run.started") await sleep(300);
      }
      // OFF run really rewrites preferences; remember it so the preferences view shows it.
      if (stored.enforcement === "off") {
        for (const r of stored.detail.results) { const p = lastPreferences(r); if (p) prefs.set(p.user, p.prefs); }
      }
    })();
    return () => { cancelled = true; };
  },

  async getRun(runId) {
    const s = runs.get(runId);
    if (!s) throw new Error(`Unknown run ${runId}`);
    return s.detail;
  },

  async compareRuns(offId, onId): Promise<RunComparison> {
    const a = runs.get(offId)?.detail.summary as RunSummary, b = runs.get(onId)?.detail.summary as RunSummary;
    if (!a || !b) throw new Error("Both runs are required to compare.");
    return { off: a, on: b };
  },

  async reset() { await sleep(200); runs.clear(); prefs.clear(); },

  async getPreferences(userId) { return prefs.get(userId) ?? EMPTY_PREFS; },
  async putPreferences(userId, p) { prefs.set(userId, p); return p; },
};
