// Mock mode: serves fixtures recorded from the backend's committed demo cache
// (backend/whosaid/data/demo + LLM fixture). No network, no LLM calls.
import offFixture from "../fixtures/off.json";
import onFixture from "../fixtures/on.json";
import type {
  Dataset, Enforcement, EventType, MessageResult, Preferences, PreferenceChange, RunComparison, RunDetail, RunEvent,
} from "../types";
import { findTamper, revert } from "../lib/prefs";
import { buildComparison } from "../lib/compare";
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

function revertFor(r: MessageResult, after: Preferences): Preferences {
  const t = findTamper([r]);
  return t ? revert(after, t) : after;
}

function buildEvents(runId: string, detail: RunDetail): Omit<RunEvent, "seq" | "ts">[] {
  const ev = (type: EventType, message_id: string | null, data: Record<string, unknown> = {}) =>
    ({ run_id: runId, type, message_id, data });
  const out = [ev("run.started", null, { messages_total: detail.results.length })];
  detail.results.forEach((r, i) => {
    out.push(ev("message.started", r.message_id, { user_id: r.user_id }));
    out.push(ev("message.routed", r.message_id, { action: r.routing.action, driver: r.routing.driver }));
    r.agent.attempts.forEach((a) => {
      out.push(ev("tool.attempted", r.message_id, { tool: a.call.tool }));
      out.push(ev("authz.decision", r.message_id, { ...a.decision }));
      if (a.executed) out.push(ev("tool.executed", r.message_id, { tool: a.call.tool, result: a.result }));
    });
    void i;
    out.push(ev("message.completed", r.message_id, { ...r }));
  });
  out.push(ev("run.completed", null, { summary: detail.summary }));
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
    const changes: PreferenceChange[] = [];
    for (const r of src.results) {
      const p = lastPreferences(r);
      if (p && enforcement === "off") {
        const before = revertFor(r, p.prefs);
        (Object.keys(p.prefs) as (keyof Preferences)[]).forEach((k) => {
          if (JSON.stringify(p.prefs[k]) !== JSON.stringify(before[k])) changes.push({ user_id: p.user, key: k, before: before[k], after: p.prefs[k] });
        });
      }
    }
    const detail: RunDetail = {
      status: "completed",
      preference_changes: changes,
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
        if (e.type === "run.started") await sleep(300);
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
    const a = runs.get(offId)?.detail, b = runs.get(onId)?.detail;
    if (!a || !b) throw new Error("Both runs are required to compare.");
    return buildComparison(a, b);
  },

  async reset() { await sleep(200); runs.clear(); prefs.clear(); },

  async getPreferences(userId) { return prefs.get(userId) ?? EMPTY_PREFS; },
  async putPreferences(userId, p) { prefs.set(userId, p); return p; },
};
