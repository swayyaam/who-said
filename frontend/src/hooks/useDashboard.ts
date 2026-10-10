import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { Dataset, Enforcement, MessageResult, RunComparison, RunDetail, RunEvent } from "../types";
import { buildComparison } from "../lib/compare";
import { buildSteps, type TraceStep } from "../lib/trace";

export interface Progress {
  mode: Enforcement;
  done: number;
  total: number;
  current: { messageId: string; text: string; userId: string } | null;
  harmful: number;
  denied: number;
  /** the current message's pipeline, revealed step by step */
  trace: TraceStep[];
  /** answers replay from the fixture, so timing is paced and not real latency */
  replay: boolean;
}

export interface Finished {
  mode: Enforcement; seconds: number; done: number; total: number; harmful: number; denied: number;
  messageId: string; trace: TraceStep[]; replay: boolean;
}

// Pacing for fixture replays: ~25 s for the 33-message demo. Live runs pass straight through.
const STEP_MS = 120;
const MIN_SLOT_MS = 380;

export type Filters = { attacksOnly: boolean; deniedOnly: boolean; changedOnly: boolean; trust: string | "all" };
const NO_FILTERS: Filters = { attacksOnly: false, deniedOnly: false, changedOnly: false, trust: "all" };
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function useDashboard() {
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [datasetBusy, setDatasetBusy] = useState(false);
  const [enforcement, setEnforcement] = useState<Enforcement>("off");
  const [runs, setRuns] = useState<Partial<Record<Enforcement, RunDetail>>>({});
  const [progress, setProgress] = useState<Progress | null>(null);
  const [finished, setFinished] = useState<Finished | null>(null);
  const progressRef = useRef<Progress | null>(null);
  progressRef.current = progress;
  const [comparison, setComparison] = useState<RunComparison | null>(null);
  const runIds = useRef<Partial<Record<Enforcement, string>>>({});
  const [view, setView] = useState<Enforcement>("off");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const [error, setError] = useState<string | null>(null);
  const unsub = useRef<(() => void) | null>(null);

  useEffect(() => () => unsub.current?.(), []);

  const guard = useCallback(async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    try { setError(null); return await fn(); }
    catch (e) { setError((e as Error).message); return undefined; }
  }, []);

  const loadDemo = useCallback(async () => {
    setDatasetBusy(true);
    const d = await guard(() => api.useDemoDataset());
    if (d) setDataset(d);
    setDatasetBusy(false);
  }, [guard]);

  const upload = useCallback(async (files: File[]) => {
    setDatasetBusy(true);
    const d = await guard(() => api.uploadDataset(files));
    if (d) setDataset(d);
    setDatasetBusy(false);
  }, [guard]);

  const run = useCallback(async () => {
    if (!dataset || progress) return;
    const mode = enforcement;
    setSelectedId(null);
    setFinished(null);
    const startedAt = performance.now();
    setProgress({ mode, done: 0, total: dataset.messages, current: null, harmful: 0, denied: 0, trace: [], replay: api.mock });
    const handle = await guard(() => api.startRun(dataset.dataset_id, mode));
    if (!handle) { setProgress(null); return; }
    const replay = api.mock || handle.live === false;
    setProgress((p) => p && { ...p, replay });

    // Events go through a queue so a fixture replay (which finishes in under a second)
    // is still visible; a live run's events arrive slower than the pace and pass straight through.
    const queue: RunEvent[] = [];
    let draining = false, closed = false, finished = false;
    const finish = async () => {
      if (finished) return;
      finished = true; closed = true;
      unsub.current?.(); unsub.current = null;
      const detail = await guard(() => api.getRun(handle.run_id));
      if (detail) {
        runIds.current[mode] = handle.run_id;
        setRuns((r) => ({ ...r, [mode]: detail }));
        setView(mode);
        setFilters(NO_FILTERS);
      }
      const p = progressRef.current;
      if (p && detail) {
        setFinished({ mode, seconds: (performance.now() - startedAt) / 1000, done: detail.summary.messages, total: detail.summary.messages, harmful: detail.summary.harmful_executed, denied: detail.summary.actions_denied,
          messageId: p.current?.messageId ?? "", trace: p.trace, replay });
      }
      setProgress(null);
    };

    const apply = async (e: RunEvent) => {
      if (e.type === "run.started") {
        const total = Number(e.data.messages_total ?? e.data.messages ?? 0);
        if (total) setProgress((p) => p && { ...p, total });
      } else if (e.type === "message.started") {
        setProgress((p) => p && { ...p, current: { messageId: e.message_id ?? "", text: "", userId: String(e.data.user_id ?? "") } });
      } else if (e.type === "authz.decision" && e.data.allowed === false) {
        setProgress((p) => p && { ...p, denied: p.denied + 1 });
      } else if (e.type === "message.completed") {
        const r = e.data as unknown as MessageResult;
        const steps = buildSteps(r);
        setProgress((p) => p && { ...p, current: { messageId: e.message_id ?? "", text: r.text ?? "", userId: r.user_id ?? "" } });
        if (replay) {
          const slot = Math.max(MIN_SLOT_MS, steps.length * STEP_MS);
          const gap = Math.min(STEP_MS * 2, slot / steps.length);
          for (let i = 1; i <= steps.length && !finished; i++) {
            setProgress((p) => p && { ...p, trace: steps.slice(0, i) });
            await sleep(gap);
          }
          if (slot > gap * steps.length) await sleep(slot - gap * steps.length);
        } else {
          setProgress((p) => p && { ...p, trace: steps });
        }
        setProgress((p) => p && { ...p, done: p.done + 1, harmful: p.harmful + (r.harmful_executed?.length ?? 0) });
      } else if (e.type === "run.failed") {
        setError(String(e.data.error ?? "The run failed."));
        closed = true; finished = true; unsub.current?.(); setProgress(null);
      }
    };

    const drain = async () => {
      if (draining) return;
      draining = true;
      while (queue.length) {
        const e = queue.shift()!;
        if (finished) break;
        await apply(e);
        if (e.type === "run.completed") { await finish(); break; }
      }
      draining = false;
      if (closed && !finished && !queue.length) await finish();
    };

    unsub.current = api.streamEvents(handle.run_id, (e) => { queue.push(e); void drain(); }, (err) => {
      // Stream dropped: let queued events play out, then fetch the final result.
      if (!finished) { closed = true; if (!queue.length && !draining) { setError(err.message); void finish(); } else void drain(); }
    });
  }, [dataset, enforcement, guard, progress]);

  const reset = useCallback(async () => {
    unsub.current?.(); unsub.current = null;
    await guard(() => api.reset());
    setRuns({}); setFinished(null); setComparison(null); runIds.current = {}; setProgress(null); setSelectedId(null); setView("off"); setEnforcement("off");
    setFilters(NO_FILTERS);
  }, [guard]);

  useEffect(() => {
    const off = runIds.current.off, on = runIds.current.on;
    if (!runs.off || !runs.on || !off || !on) { setComparison(null); return; }
    let ok = true;
    api.compareRuns(off, on).then((c) => ok && setComparison(c)).catch(() => ok && setComparison(buildComparison(runs.off!, runs.on!)));
    return () => { ok = false; };
  }, [runs]);

  const active = runs[view] ?? null;
  const selected = useMemo(() => active?.results.find((r) => r.message_id === selectedId) ?? null, [active, selectedId]);

  return {
    dataset, datasetBusy, loadDemo, upload,
    enforcement, setEnforcement, run, reset, progress, finished,
    runs, comparison, view, setView, active, selected, selectedId, setSelectedId,
    filters, setFilters, error, clearError: () => setError(null),
  };
}
