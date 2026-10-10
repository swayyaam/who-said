import { useRef, useState } from "react";
import type { Dataset } from "../types";
import { Button, Eyebrow } from "./ui";

export function DatasetPanel({ dataset, busy, onDemo, onUpload, locked }: {
  dataset: Dataset | null; busy: boolean; onDemo: () => void; onUpload: (f: File[]) => void; locked: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const pick = (list: FileList | null) => { if (list?.length) onUpload(Array.from(list)); };

  return (
    <div className="flex h-full min-h-[300px] flex-col rounded-lg border border-hairline p-6">
      <Eyebrow>1 · Dataset</Eyebrow>
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
