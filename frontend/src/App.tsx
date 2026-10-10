import { api } from "./api";
import { useDashboard } from "./hooks/useDashboard";
import { ComparisonHero } from "./components/ComparisonHero";
import { DatasetPanel } from "./components/DatasetPanel";
import { MessageDetail } from "./components/MessageDetail";
import { MessagesTable } from "./components/MessagesTable";
import { PreferencesView } from "./components/PreferencesView";
import { RunControls } from "./components/RunControls";
import { Empty, Section } from "./components/ui";
import type { Enforcement } from "./types";

export default function App() {
  const d = useDashboard();
  const available = (["off", "on"] as Enforcement[]).filter((m) => d.runs[m]);
  const running = !!d.progress;

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-hairline bg-canvas px-6 md:px-12">
        <div className="flex items-center gap-3">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-ink"><span className="h-2 w-2 rounded-full bg-canvas" /></span>
          <span className="text-[18px] font-[700] tracking-[-0.3px]">WhoSaid</span>
        </div>
        <div className="flex items-center gap-3">
          {api.mock && <span className="t-eyebrow rounded-pill bg-lilac px-3 py-1">Mock mode</span>}
          <span className="t-eyebrow hidden sm:inline">Powered by AgntID</span>
        </div>
      </header>

      <main className="mx-auto max-w-[1280px] px-6 pb-section md:px-12">
        <div className="pb-12 pt-16 md:pt-24">
          <div className="t-eyebrow">WhoSaid · message routing agent</div>
          <h1 className="t-display-xl mt-4 max-w-5xl">It’s not what the message says. It’s who said it.</h1>
          <p className="t-subhead mt-6 max-w-2xl">The agent routes every message and acts on your behalf. AgntID decides what it may do, based on who sent the message.</p>
        </div>

        {d.error && (
          <div role="alert" className="mb-6 flex items-center justify-between gap-4 rounded-md bg-pink px-5 py-3">
            <span>{d.error}</span><button onClick={d.clearError} className="t-strong underline">Dismiss</button>
          </div>
        )}

        <div className="grid gap-6 md:grid-cols-2">
          <DatasetPanel dataset={d.dataset} busy={d.datasetBusy} onDemo={d.loadDemo} onUpload={d.upload} locked={running} />
          <RunControls enforcement={d.enforcement} setEnforcement={d.setEnforcement} onRun={d.run} onReset={d.reset}
            progress={d.progress} finished={d.finished} hasDataset={!!d.dataset} hasRuns={available.length > 0} />
        </div>

        <div className="mt-section">
          <Section eyebrow="Headline" title="What AgntID changes">
            <ComparisonHero runs={d.runs} mock={api.mock} comparison={d.comparison} />
          </Section>
        </div>

        <Section eyebrow="Messages" title="Every message, and who sent it">
          {d.active ? (
            <MessagesTable results={d.active.results} filters={d.filters} setFilters={d.setFilters} selectedId={d.selectedId}
              onSelect={d.setSelectedId} view={d.view} setView={d.setView} available={available} changed={d.comparison?.differing ? new Set(d.comparison.differing.map((x) => x.message_id)) : null} />
          ) : <Empty title="No results yet" body="Run the dataset to see each message, its sender trust level, routing and tool calls." />}
        </Section>

        <Section eyebrow="Preferences" title="Can a message rewrite your preferences?">
          <PreferencesView runs={d.runs} />
        </Section>

        <footer className="mt-section border-t border-hairline pt-8 t-eyebrow">WhoSaid · AgntID hackathon · Sender trust is computed by code, never by the model</footer>
      </main>

      {d.selected && <MessageDetail r={d.selected} onClose={() => d.setSelectedId(null)} />}
    </div>
  );
}
