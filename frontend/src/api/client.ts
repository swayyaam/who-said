import type {
  Dataset, Enforcement, Preferences, RunComparison, RunDetail, RunEvent, RunHandle,
} from "../types";
import type { WhoSaidApi } from "./types";

const BASE = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: init?.body instanceof FormData ? init.headers : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body.message ?? detail;
    } catch { /* non-JSON error body */ }
    throw new Error(`${res.status} ${typeof detail === "string" ? detail : JSON.stringify(detail)}`);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export const realApi: WhoSaidApi = {
  mock: false,

  listDatasets: () => http<Dataset[]>("/datasets"),

  uploadDataset(files: File[]) {
    const form = new FormData();
    files.forEach((f) => form.append("files", f, f.name));
    return http<Dataset>("/datasets", { method: "POST", body: form });
  },

  async useDemoDataset() {
    const all = await http<Dataset[]>("/datasets");
    const demo = all.find((d) => d.is_demo || d.name === "demo");
    if (!demo) throw new Error("The backend has no demo dataset registered.");
    return demo;
  },

  startRun: (dataset_id: string, enforcement: Enforcement) =>
    http<RunHandle>("/runs", { method: "POST", body: JSON.stringify({ dataset_id, enforcement }) }),

  streamEvents(runId, onEvent, onError) {
    const es = new EventSource(`${BASE}/runs/${runId}/events`);
    const types = [
      "run.started", "message.started", "message.routed", "agent.step", "tool.attempted",
      "authz.decision", "tool.executed", "message.completed", "run.completed", "run.failed",
    ];
    const handle = (m: MessageEvent) => {
      try { onEvent(JSON.parse(m.data) as RunEvent); } catch (e) { onError(e as Error); }
    };
    types.forEach((t) => es.addEventListener(t, handle as EventListener));
    es.onmessage = handle; // servers that send unnamed events
    es.onerror = () => { onError(new Error("Progress stream disconnected")); es.close(); };
    return () => es.close();
  },

  getRun: (id) => http<RunDetail>(`/runs/${id}`),
  compareRuns: (off, on) => http<RunComparison>(`/runs/compare?off=${off}&on=${on}`),
  reset: () => http<void>("/reset", { method: "POST" }),
  getPreferences: (u) => http<Preferences>(`/users/${u}/preferences`),
  putPreferences: (u, p) => http<Preferences>(`/users/${u}/preferences`, { method: "PUT", body: JSON.stringify(p) }),
};
