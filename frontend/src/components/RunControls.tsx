import { useEffect, useRef } from "react";
import type { Enforcement } from "../types";
import type { Finished, Progress } from "../hooks/useDashboard";
import { Button, Eyebrow } from "./ui";
import ThoughtLine from "./ThoughtLine";
import { ToolChip } from "./ToolChip";
import type { CallStatus } from "./CallChip";

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

export function RunControls({ enforcement, setEnforcement, onRun, onReset, progress, finished, hasDataset, hasRuns }: {
  enforcement: Enforcement; setEnforcement: (v: Enforcement) => void; onRun: () => void; onReset: () => void;
  progress: Progress | null; finished: Finished | null; hasDataset: boolean; hasRuns: boolean;
}) {
  const running = !!progress;
  const scroller = useRef<HTMLDivElement>(null);
  const traceLen = progress?.trace.length ?? 0;
  // keep the newest step in view inside the fixed-height trace box
  useEffect(() => { const el = scroller.current; if (el && running) el.scrollTop = el.scrollHeight; }, [traceLen, running]);
  const shown = progress ?? finished;
  const pct = shown && shown.total ? Math.min(100, (shown.done / shown.total) * 100) : 0;
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

      {/* fixed-height progress area so nothing jumps; the trace scrolls inside it */}
      <div className="mt-5 flex h-[312px] flex-col" aria-live="polite">
        {shown ? (
          <>
            <div className="flex items-baseline justify-between">
              <div className="t-strong"><span className="tabular">{shown.done}</span> / <span className="tabular">{shown.total}</span> messages</div>
              <div className="t-eyebrow">AgntID {shown.mode}</div>
            </div>
            <div className="mt-2 h-2 shrink-0 overflow-hidden rounded-pill bg-hairline-soft"><div className="h-full rounded-pill bg-ink transition-[width] duration-200" style={{ width: `${pct}%` }} /></div>
            <div ref={scroller} className="mt-3 min-h-0 flex-1 overflow-y-auto">
              <ThoughtLine
                fontSize={16}
                color="var(--color-ink)"
                working={running}
                label={progress?.current?.messageId ? `Processing ${progress.current.messageId}` : "Starting…"}
                doneLabel="Run finished in"
                elapsed={finished?.seconds}
                steps={progress ? progress.trace : finished?.trace}
                glyph="sparkle"
              />
            </div>
            {/* the current message's tool calls: running, then AgntID's verdict. Fixed height so nothing jumps. */}
            <div className="mt-2 flex h-[72px] shrink-0 flex-wrap content-start gap-2 overflow-hidden" aria-label="Tool calls for the current message">
              {progress?.current?.result?.agent.attempts.map((a, k): { a: typeof a; k: number; s: CallStatus } => {
                const n = progress.trace.length;
                return { a, k, s: n > 3 + 2 * k ? (a.decision.allowed ? "done" : "error") : n > 2 + 2 * k ? "running" : "idle" };
              }).filter((c) => c.s !== "idle").map(({ a, k, s }) => (
                <ToolChip key={`${progress.current?.messageId}-${k}`} attempt={a} status={s} showTimer={!progress.replay} />
              ))}
            </div>
            <div className="mt-2 shrink-0 text-[13px]">
              <span className="tabular">{shown.harmful}</span> harmful ran · <span className="tabular">{shown.denied}</span> denied
              {!running && finished?.replay ? " · replayed from recorded answers" : ""}
            </div>
          </>
        ) : (
          <div className="text-[14px]">{hasDataset ? "Pick a mode and run. Run OFF first to see the damage, then ON." : "Load a dataset to enable runs."}</div>
        )}
      </div>
    </div>
  );
}
