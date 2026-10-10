import type { Enforcement, RunComparison, RunDetail } from "../types";
import { inr, runStats, plural } from "../lib/format";
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
  const pending = both && !comparison;
  const outcome = h?.outcome ?? (both ? "blocked" : undefined);
  // one run only, and nothing harmful in it
  const single0 = !both && (off ?? on)!.summary.harmful_executed === 0;
  // The big "₹X → ₹0" treatment is for stories where money was at risk (blocked) or still lost (leak).
  const big = both ? outcome === "blocked" || outcome === "leak" : !single0;
  const tone = both
    ? ({
        blocked: { bg: "bg-navy text-canvas", eyebrow: "Money lost to scams" },
        leak: { bg: "bg-coral", eyebrow: "Money still lost with AgntID ON" },
        allowed: { bg: "bg-mint", eyebrow: "Outcome · allowed" },
        muted: { bg: "bg-cream", eyebrow: "Outcome · muted" },
        quiet: { bg: "bg-cream", eyebrow: "Outcome · quiet" },
      }[outcome ?? "blocked"] ?? { bg: "bg-cream", eyebrow: "Outcome" })
    : single0
      ? { bg: "bg-cream", eyebrow: `AgntID ${off ? "OFF" : "ON"} · outcome` }
      : { bg: "bg-coral", eyebrow: off ? "AgntID OFF · money lost to scams" : "AgntID ON · money lost to scams" };

  return (
    <div className="fade-in">
      {/* The demo moment, styled by outcome */}
      {pending ? (
        <div className="flex min-h-[280px] items-center justify-center rounded-lg bg-soft p-8"><Eyebrow>Comparing runs…</Eyebrow></div>
      ) : (
        <div className={`rounded-lg p-8 md:p-12 ${tone.bg}`}>
          <div className="flex items-center justify-between">
            <Eyebrow>{tone.eyebrow}</Eyebrow>
            {mock && <span className="t-eyebrow rounded-pill border border-current px-3 py-0.5">Recorded demo data</span>}
          </div>
          {big ? (
            <div className="t-display-xl tabular mt-4 flex flex-wrap items-baseline gap-x-6">
              {!both ? (
                <span>{inr(off ? lost : lostOn)}</span>
              ) : h?.loss_text ? (
                <span>{h.loss_text.split(" → ").map((part, i) => i === 0
                  ? <span key={i} className={outcome === "leak" ? "" : "line-through decoration-[6px] decoration-magenta"}>{part}</span>
                  : <span key={i}><span aria-hidden> → </span>{part}</span>)}</span>
              ) : (
                <>
                  <span className="line-through decoration-[6px] decoration-magenta">{inr(lost)}</span>
                  <span aria-hidden>→</span>
                  <span>{inr(lostOn)}</span>
                </>
              )}
            </div>
          ) : (
            <div className="t-display-lg mt-4">{both ? h?.loss_text ?? "Nothing at risk" : single0 ? "Nothing at risk" : inr(off ? lost : lostOn)}</div>
          )}
          {both && h && (
            <div className={`mt-5 inline-flex flex-wrap items-center gap-x-3 rounded-pill px-5 py-2 text-[18px] font-[540] text-ink ${h.on_controls_total > 0 ? (outcome === "blocked" || outcome === "leak" ? "bg-mint" : "bg-canvas") : "bg-canvas"}`}>
              {h.on_controls_total > 0 && <span aria-hidden className="text-success">✓</span>}
              <span className="tabular">{h.legit_text}</span>
            </div>
          )}
          <p className="t-subhead mt-4 max-w-2xl">
            {both
              ? h?.text ?? ""
              : single0
                ? "No harmful action ran. Run the other mode to compare."
                : off
                  ? `${plural(off.summary.harmful_executed, "harmful action")} ran: money paid out, OTPs leaked, preferences rewritten. Flip the toggle and run again.`
                  : "Nothing harmful ran. Run with AgntID OFF to see what it prevents."}
          </p>
        </div>
      )}

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
