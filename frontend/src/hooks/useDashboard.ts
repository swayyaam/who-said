import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type { Dataset, Enforcement, RunDetail, RunEvent } from "../types";

export interface Progress {
  mode: Enforcement;
  done: number;
  total: number;
  current: { messageId: string; text: string; userId: string } | null;
  harmful: number;
  denied: number;
}

export type Filters = { attacksOnly: boolean; deniedOnly: boolean; trust: string | "all" };

export function useDashboard() {
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [datasetBusy, setDatasetBusy] = useState(false);
  const [enforcement, setEnforcement] = useState<Enforcement>("off");
  const [runs, setRuns] = useState<Partial<Record<Enforcement, RunDetail>>>({});
  const [progress, setProgress] = useState<Progress | null>(null);
  const [view, setView] = useState<Enforcement>("off");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>({ attacksOnly: false, deniedOnly: false, trust: "all" });
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
    setProgress({ mode, done: 0, total: dataset.messages, current: null, harmful: 0, denied: 0 });
    const handle = await guard(() => api.startRun(dataset.dataset_id, mode));
    if (!handle) { setProgress(null); return; }

    const finish = async () => {
      unsub.current?.(); unsub.current = null;
      const detail = await guard(() => api.getRun(handle.run_id));
      if (detail) {
        setRuns((r) => ({ ...r, [mode]: detail }));
        setView(mode);
      }
      setProgress(null);
    };

    const onEvent = (e: RunEvent) => {
      if (e.type === "run.started") {
        const total = Number(e.data.messages ?? 0);
        if (total) setProgress((p) => p && { ...p, total });
      } else if (e.type === "message.started") {
        setProgress((p) => p && { ...p, current: { messageId: e.message_id ?? "", text: String(e.data.text ?? ""), userId: String(e.data.user_id ?? "") } });
      } else if (e.type === "authz.decision" && e.data.allowed === false) {
        setProgress((p) => p && { ...p, denied: p.denied + 1 });
      } else if (e.type === "tool.executed" && e.data.harmful) {
        setProgress((p) => p && { ...p, harmful: p.harmful + 1 });
      } else if (e.type === "message.completed") {
        setProgress((p) => p && { ...p, done: p.done + 1 });
      } else if (e.type === "run.completed") {
        void finish();
      } else if (e.type === "run.failed") {
        setError(String(e.data.error ?? "The run failed."));
        unsub.current?.(); setProgress(null);
      }
    };
    unsub.current = api.streamEvents(handle.run_id, onEvent, (err) => {
      // Stream dropped: the run may still have finished, so try fetching the result once.
      setError(err.message);
      void finish();
    });
  }, [dataset, enforcement, guard, progress]);

  const reset = useCallback(async () => {
    unsub.current?.(); unsub.current = null;
    await guard(() => api.reset());
    setRuns({}); setProgress(null); setSelectedId(null); setView("off"); setEnforcement("off");
    setFilters({ attacksOnly: false, deniedOnly: false, trust: "all" });
  }, [guard]);

  const active = runs[view] ?? null;
  const selected = useMemo(() => active?.results.find((r) => r.message_id === selectedId) ?? null, [active, selectedId]);

  return {
    dataset, datasetBusy, loadDemo, upload,
    enforcement, setEnforcement, run, reset, progress,
    runs, view, setView, active, selected, selectedId, setSelectedId,
    filters, setFilters, error, clearError: () => setError(null),
  };
}
