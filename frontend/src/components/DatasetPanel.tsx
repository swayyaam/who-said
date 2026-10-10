import { useRef, useState } from "react";
import type { Dataset } from "../types";
import { Button, Eyebrow } from "./ui";

const isBuiltIn = (d: Dataset) => !!d.is_demo || d.dataset_id.startsWith("case-");

export function DatasetPanel({ dataset, datasets, busy, onDemo, onSelect, onUpload, locked }: {
  dataset: Dataset | null; datasets: Dataset[]; busy: boolean; onDemo: () => void; onSelect: (d: Dataset) => void;
  onUpload: (f: File[]) => void; locked: boolean;
}) {
  const builtIns = [...datasets.filter(isBuiltIn)].sort((a, b) => Number(!!b.is_demo) - Number(!!a.is_demo));
  const current = dataset && builtIns.some((d) => d.dataset_id === dataset.dataset_id) ? dataset.dataset_id : (dataset ? "" : builtIns.find((d) => d.is_demo)?.dataset_id ?? "");
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const pick = (list: FileList | null) => { if (list?.length) onUpload(Array.from(list)); };

  return (
    <div className="flex h-full min-h-[300px] flex-col rounded-lg border border-hairline p-6">
      <Eyebrow>1 · Dataset</Eyebrow>
      {builtIns.length > 1 && (
        <select
          aria-label="Built-in dataset"
          value={current}
          disabled={locked || busy}
          onChange={(e) => { const d = builtIns.find((x) => x.dataset_id === e.target.value); if (d) onSelect(d); }}
          className="mt-3 w-full rounded-md border border-hairline bg-canvas px-3.5 py-2.5 text-[16px] text-ink"
        >
          {!current && <option value="" disabled>Uploaded dataset</option>}
          {builtIns.map((d) => <option key={d.dataset_id} value={d.dataset_id}>{d.is_demo ? "Full demo" : d.name}</option>)}
        </select>
      )}
      {dataset ? (
        <div className="mt-3 flex flex-1 flex-col fade-in">
          <div className="t-headline">{dataset.name}</div>
          <div className="mt-4 grid grid-cols-3 gap-3">
            {[["Messages", dataset.messages], ["Attacks", dataset.attacks], ["Controls", dataset.controls]].map(([k, v]) => (
              <div key={String(k)} className="rounded-md bg-soft px-3 py-2">
                <div className="tabular text-[26px] font-[540] leading-none">{v ?? "—"}</div>
                <div className="t-eyebrow mt-1 !text-[10px]">{k}</div>
              </div>
            ))}
          </div>
          <div className="mt-auto pt-4">
            <Button variant="secondary" onClick={() => input.current?.click()} disabled={locked || busy} className="!min-h-9 !px-4 !text-[15px]">Replace dataset</Button>
          </div>
        </div>
      ) : (
        <div
          onDragOver={(e) => { e.preventDefault(); setOver(true); }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files); }}
          className={`mt-3 flex flex-1 flex-col items-center justify-center rounded-md border border-dashed px-4 py-6 text-center transition-colors ${over ? "border-ink bg-lime" : "border-hairline bg-soft"}`}
        >
          <div className="t-strong">Drop the dataset CSVs here</div>
          <div className="mt-1 text-[14px]">messages, users, groups, businesses, payees…</div>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            <Button onClick={onDemo} disabled={busy}>{busy ? "Loading…" : "Use demo dataset"}</Button>
            <Button variant="secondary" onClick={() => input.current?.click()} disabled={busy}>Browse files</Button>
          </div>
        </div>
      )}
      <input ref={input} type="file" accept=".csv" multiple hidden onChange={(e) => { pick(e.target.files); e.target.value = ""; }} />
    </div>
  );
}
