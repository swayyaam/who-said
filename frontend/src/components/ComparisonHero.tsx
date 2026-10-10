import type { Enforcement, RunComparison, RunDetail } from "../types";
import { inr, runStats } from "../lib/format";
import { Empty, Eyebrow } from "./ui";

type Runs = Partial<Record<Enforcement, RunDetail>>;

function Row({ label, off, on, offBad, hasOn }: { label: string; off: string; on: string; offBad?: boolean; hasOn: boolean }) {
  return (
    <div className="grid grid-cols-[1.4fr_1fr_1fr] items-center gap-4 border-b border-hairline-soft py-4 last:border-0">
      <div className="t-strong">{label}</div>
      <div className={`tabular text-[22px] font-[540] ${offBad ? "rounded-md bg-coral px-3 py-1" : ""}`}>{off}</div>
      <div className={`tabular text-[22px] font-[540] ${hasOn ? "rounded-md bg-mint px-3 py-1" : ""}`}>{hasOn ? on : "—"}</div>
    </div>
  );
}

function Layers({ run, empty }: { run?: RunDetail; empty?: boolean }) {
  const layers = ["profile", "policy", "intent"] as const;
  return (
    <div className="flex gap-2">
      {layers.map((l) => (
        <div key={l} className="min-w-16 rounded-md bg-soft px-3 py-1.5 text-center">
          <div className="tabular text-[22px] font-[540]">{empty || !run ? "—" : run.summary.denials_by_layer[l] ?? 0}</div>
          <div className="t-eyebrow !text-[10px]">{l}</div>
        </div>
      ))}
    </div>
  );
}

export function ComparisonHero({ runs, mock, comparison }: { runs: Runs; mock: boolean; comparison: RunComparison | null }) {
  const { off, on } = runs;
  if (!off && !on) {
    return <Empty title="No runs yet" body="Run the dataset with AgntID OFF, then flip the toggle and run it again with AgntID ON." />;
  }
  const both = !!off && !!on;
  const lost = off?.summary.harmful_money_lost_inr ?? 0;
  const lostOn = on?.summary.harmful_money_lost_inr ?? 0;
  const h = comparison?.headline;
  const so = off && runStats(off), sn = on && runStats(on);

  return (
    <div className="fade-in">
      {/* The demo moment */}
      <div className={`rounded-lg p-8 md:p-12 ${both ? "bg-navy text-canvas" : "bg-coral"}`}>
        <div className="flex items-center justify-between">
          <Eyebrow>{both ? "Money lost to scams" : off ? "AgntID OFF · money lost to scams" : "AgntID ON · money lost to scams"}</Eyebrow>
          {mock && <span className="t-eyebrow rounded-pill border border-current px-3 py-0.5">Recorded demo data</span>}
        </div>
        <div className="t-display-xl tabular mt-4 flex flex-wrap items-baseline gap-x-6">
          {both ? (
            h?.loss_text ? (
              <span>{h.loss_text.split(" → ").map((part, i) => i === 0
                ? <span key={i} className="line-through decoration-[6px] decoration-magenta">{part}</span>
                : <span key={i}><span aria-hidden> → </span>{part}</span>)}</span>
            ) : (
              <>
                <span className="line-through decoration-[6px] decoration-magenta">{inr(lost)}</span>
                <span aria-hidden>→</span>
                <span>{inr(lostOn)}</span>
              </>
            )
          ) : (
            <span>{inr(off ? lost : lostOn)}</span>
          )}
        </div>
        {both && (
          <div className="mt-5 inline-flex flex-wrap items-center gap-x-3 rounded-pill bg-mint px-5 py-2 text-[18px] font-[540] text-ink">
            <span aria-hidden className="text-success">✓</span>
            <span className="tabular">{h?.legit_text ?? `${on!.summary.controls_ok}/${on!.summary.controls_total} legitimate actions still work · ${inr(on!.summary.total_money_moved_inr - on!.summary.harmful_money_lost_inr)} paid correctly`}</span>
          </div>
        )}
        <p className="t-subhead mt-4 max-w-2xl">
          {both
            ? `With AgntID ON every attack was stopped: ${sn!.attacksBlocked} of ${sn!.attacks} attacks blocked.`
            : off
              ? `${off.summary.harmful_executed} harmful actions ran: money paid out, OTPs leaked, preferences rewritten. Flip the toggle and run again.`
              : "Nothing harmful ran. Run with AgntID OFF to see what it prevents."}
        </p>
      </div>

      {/* Side by side */}
      <div className="mt-6 rounded-lg border border-hairline p-6 md:px-8">
        <div className="grid grid-cols-[1.4fr_1fr_1fr] gap-4 pb-2">
          <div />
          <div className="t-eyebrow">AgntID OFF</div>
          <div className="t-eyebrow">AgntID ON</div>
        </div>
        <Row label="Harmful actions executed" off={off ? String(off.summary.harmful_executed) : "—"} on={String(on?.summary.harmful_executed ?? 0)} offBad={!!off && off.summary.harmful_executed > 0} hasOn={!!on} />
        <Row label="Money lost" off={off ? inr(lost) : "—"} on={inr(lostOn)} offBad={lost > 0} hasOn={!!on} />
        <Row label="Messages acted on" off={so ? `${so.messagesActedOn} of ${off!.summary.messages}` : "—"} on={sn ? `${sn.messagesActedOn} of ${on!.summary.messages}` : ""} hasOn={!!on} />
        <Row label="Preferences rewritten by a message" off={off ? String(off.summary.preference_changes_executed) : "—"} on={String(on?.summary.preference_changes_executed ?? 0)} offBad={!!off && off.summary.preference_changes_executed > 0} hasOn={!!on} />
        <Row label="Legitimate actions that worked" off={off ? `${off.summary.controls_ok} / ${off.summary.controls_total}` : "—"} on={on ? `${on.summary.controls_ok} / ${on.summary.controls_total}` : ""} hasOn={!!on} />
        <div className="grid grid-cols-[1.4fr_1fr_1fr] items-center gap-4 pt-4">
          <div className="t-strong">Denials by AgntID layer</div>
          <Layers run={off} />
          <Layers run={on} />
        </div>
      </div>
    </div>
  );
}
