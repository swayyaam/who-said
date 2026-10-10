import { useEffect } from "react";
import type { MessageResult, ToolAttempt } from "../types";
import { humanize, inr } from "../lib/format";
import { ActionPill, DriverTag, Eyebrow, TrustBadge } from "./ui";

function Args({ title, note, data, tone }: { title: string; note: string; data: Record<string, unknown>; tone: string }) {
  const entries = Object.entries(data);
  return (
    <div className={`rounded-md p-3 ${tone}`}>
      <div className="t-eyebrow">{title}</div>
      <div className="mb-2 text-[13px] font-[540]">{note}</div>
      {entries.length === 0 ? <div className="text-[13px]">none</div> : (
        <dl className="space-y-1">
          {entries.map(([k, v]) => (
            <div key={k} className="grid grid-cols-[110px_1fr] gap-2 text-[13px]">
              <dt className="t-mono truncate">{k}</dt>
              <dd className="t-mono break-all">{typeof v === "string" ? (v === "" ? "(empty)" : v) : JSON.stringify(v)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function ToolCallCard({ a, index }: { a: ToolAttempt; index: number }) {
  const d = a.decision;
  const verdict = !d.allowed ? "DENIED" : a.harmful ? "ALLOWED · HARMFUL" : "ALLOWED";
  const head = !d.allowed ? "bg-lilac" : a.harmful ? "bg-coral" : "bg-mint";
  return (
    <li className="overflow-hidden rounded-md border border-hairline">
      <div className={`flex items-center justify-between gap-3 px-4 py-2 ${head}`}>
        <div className="flex items-center gap-2"><span className="t-eyebrow">Step {index + 1}</span><span className="font-mono text-[15px] font-[540]">{a.call.tool}</span></div>
        <span className="t-eyebrow">{verdict}</span>
      </div>
      <div className="space-y-3 p-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Args title="Proposed by the model" note="Chosen by the LLM" data={a.call.model_args} tone="bg-soft" />
          <Args title="Trusted arguments" note="Set by code, not the model" data={a.call.trusted_args} tone="bg-cream" />
        </div>
        <div className="rounded-md border border-hairline p-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="t-eyebrow">AgntID decision</span>
            <span className="rounded-pill bg-ink px-2.5 py-0.5 text-[12px] font-[540] text-canvas">{d.enforced ? `layer: ${d.layer === "none" && d.allowed ? "passed all" : d.layer}` : "not enforced"}</span>
            {d.policy && <span className="t-mono text-[12px]">{d.policy}</span>}
            {d.code && <span className="t-mono text-[12px]">{d.code}</span>}
          </div>
          <p className="mt-1 text-[14px]">{d.reason}</p>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 text-[14px]">
          <span>{a.executed ? "Executed" : "Did not execute"}</span>
          {a.money_moved_inr > 0 && <span className="tabular rounded-md bg-coral px-2 py-0.5 font-[540]">{inr(a.money_moved_inr)} moved</span>}
        </div>
      </div>
    </li>
  );
}

export function MessageDetail({ r, onClose }: { r: MessageResult; onClose: () => void }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const signals = Object.entries(r.trust.signals);
  return (
    <>
      <div className="fixed inset-0 z-30 bg-ink/40" onClick={onClose} aria-hidden />
      <aside role="dialog" aria-label={`Message ${r.message_id}`} className="fixed right-0 top-0 z-40 h-full w-full max-w-[600px] overflow-y-auto bg-canvas p-6 shadow-[0_4px_16px_rgba(0,0,0,0.06)] md:p-8">
        <div className="flex items-start justify-between gap-4">
          <div>
            <Eyebrow>{r.message_id} · user {r.user_id}{r.scenario ? ` · ${humanize(r.scenario.scenario)}` : ""}</Eyebrow>
            <h3 className="t-headline mt-2">{r.text}</h3>
          </div>
          <button onClick={onClose} aria-label="Close" className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-soft text-xl">×</button>
        </div>
        {r.scenario?.note && <p className="mt-3 rounded-md bg-soft p-3 text-[14px]"><span className="t-eyebrow mr-2">Scenario</span>{r.scenario.note}</p>}

        <Block title="Who sent it">
          <div className="flex flex-wrap items-center gap-3"><span className="t-mono">{r.sender.display_name || r.sender.sender_id}</span><span className="t-eyebrow">{r.sender.kind}</span><TrustBadge level={r.trust.level} /></div>
          <div className="mt-3 text-[14px] font-[540]">Trust is computed by code from data. The model never sees or sets it.</div>
          <ul className="mt-2 space-y-1 text-[14px]">{r.trust.reasons.map((x) => <li key={x}>• {x}</li>)}</ul>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1">
            {signals.map(([k, v]) => (<div key={k} className="contents text-[13px]"><dt className="t-eyebrow !text-[10px] self-center">{humanize(k)}</dt><dd className="t-mono">{String(v)}</dd></div>))}
            {r.trust.registered_payee && <><dt className="t-eyebrow !text-[10px] self-center">registered payee</dt><dd className="t-mono">{r.trust.registered_payee}</dd></>}
          </dl>
        </Block>

        <Block title="Routing decision">
          <div className="flex items-center gap-3"><ActionPill action={r.routing.action} /><DriverTag driver={r.routing.driver} /><span className="t-mono">{r.routing.rule}</span></div>
          <p className="mt-2 text-[14px]">{r.routing.reason}</p>
        </Block>

        <Block title={`Agent steps${r.agent.ran ? ` · ${r.agent.llm_calls} LLM call${r.agent.llm_calls === 1 ? "" : "s"}` : ""}`}>
          {!r.agent.ran ? <p className="text-[14px]">The agent did not run for this message (routed {r.routing.action}, nothing to act on).</p> : r.agent.attempts.length === 0 ? <p className="text-[14px]">The agent ran and chose no tool calls.</p> : (
            <ol className="space-y-4">{r.agent.attempts.map((a, i) => <ToolCallCard key={i} a={a} index={i} />)}</ol>
          )}
          {r.agent.error && <p className="mt-3 rounded-md bg-pink p-3 text-[14px]">Agent error: {r.agent.error}</p>}
        </Block>

        <div className={`mt-6 rounded-lg p-5 ${r.harmful_money_lost_inr > 0 ? "bg-coral" : "bg-soft"}`}>
          <Eyebrow>Money moved</Eyebrow>
          <div className="t-display-lg tabular mt-1">{inr(r.money_moved_inr)}</div>
          {r.harmful_executed.length > 0 && <p className="mt-1 text-[14px]">Harmful and executed: {r.harmful_executed.join(", ")}</p>}
          {r.legit_actions_ok !== null && <p className="mt-1 text-[14px]">{r.legit_actions_ok ? "✓ The legitimate actions for this control message worked." : "✕ The legitimate action for this control message failed."}</p>}
        </div>
      </aside>
    </>
  );
}

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return <section className="mt-6 border-t border-hairline pt-5"><Eyebrow>{title}</Eyebrow><div className="mt-3">{children}</div></section>;
}
