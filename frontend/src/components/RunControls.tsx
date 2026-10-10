import type { Enforcement } from "../types";
import type { Progress } from "../hooks/useDashboard";
import { Button, Eyebrow } from "./ui";

function Toggle({ value, onChange, disabled }: { value: Enforcement; onChange: (v: Enforcement) => void; disabled: boolean }) {
  const seg = (v: Enforcement, label: string) => (
    <button
      role="radio" aria-checked={value === v} disabled={disabled} onClick={() => onChange(v)}
      className={`flex-1 rounded-pill px-6 py-3 text-[20px] font-[540] transition-colors ${value === v ? "bg-ink text-canvas" : "bg-canvas text-ink"}`}
    >{label}</button>
  );
  return (
    <div role="radiogroup" aria-label="AgntID enforcement" className="flex gap-1 rounded-pill border border-ink p-1">
      {seg("off", "AgntID OFF")}{seg("on", "AgntID ON")}
    </div>
  );
}

export function RunControls({ enforcement, setEnforcement, onRun, onReset, progress, hasDataset, hasRuns }: {
  enforcement: Enforcement; setEnforcement: (v: Enforcement) => void; onRun: () => void; onReset: () => void;
  progress: Progress | null; hasDataset: boolean; hasRuns: boolean;
}) {
  const running = !!progress;
  const pct = progress && progress.total ? Math.min(100, (progress.done / progress.total) * 100) : 0;
  return (
    <div className="flex h-full min-h-[300px] flex-col rounded-lg border border-hairline p-6">
      <Eyebrow>2 · Run</Eyebrow>
      <div className="mt-3"><Toggle value={enforcement} onChange={setEnforcement} disabled={running} /></div>
      <div className="mt-4 flex gap-3">
        <Button onClick={onRun} disabled={!hasDataset || running} className="flex-1" title={hasDataset ? "" : "Load a dataset first"}>
          {running ? "Running…" : `Run with AgntID ${enforcement.toUpperCase()}`}
        </Button>
        <Button variant="secondary" onClick={onReset} disabled={running || (!hasRuns && !hasDataset)}>Reset</Button>
      </div>

      {/* fixed-height progress area so nothing jumps */}
      <div className="mt-5 min-h-[88px]" aria-live="polite">
        {running ? (
          <div className="fade-in">
            <div className="flex items-baseline justify-between">
              <div className="t-strong"><span className="tabular">{progress.done}</span> / <span className="tabular">{progress.total}</span> messages</div>
              <div className="t-eyebrow">AgntID {progress.mode}</div>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-pill bg-hairline-soft"><div className="h-full rounded-pill bg-ink transition-[width] duration-200" style={{ width: `${pct}%` }} /></div>
            <div className="mt-2 flex items-center gap-2 text-[14px]">
              <span className="pulse inline-block h-2 w-2 shrink-0 rounded-full bg-ink" />
              <span className="truncate">{progress.current ? `${progress.current.messageId} · ${progress.current.text}` : "Starting…"}</span>
            </div>
            <div className="mt-1 text-[13px]">
              <span className="tabular">{progress.harmful}</span> harmful ran · <span className="tabular">{progress.denied}</span> denied
            </div>
          </div>
        ) : (
          <div className="text-[14px]">{hasDataset ? "Pick a mode and run. Run OFF first to see the damage, then ON." : "Load a dataset to enable runs."}</div>
        )}
      </div>
    </div>
  );
}
