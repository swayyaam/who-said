import type { Enforcement, MessageResult, TrustLevel } from "../types";
import type { Filters } from "../hooks/useDashboard";
import { TRUST_LABEL, TRUST_ORDER, deniedCount, inr, isAttack, isControl } from "../lib/format";
import { ActionPill, DecisionChip, DriverTag, Empty, TrustBadge } from "./ui";

function Pill({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button aria-pressed={on} onClick={onClick}
      className={`rounded-pill px-4 py-1.5 text-[15px] font-[480] ${on ? "bg-ink text-canvas" : "bg-canvas text-ink border border-hairline"}`}>{children}</button>
  );
}

export function applyFilters(rs: MessageResult[], f: Filters, changed: Set<string> | null) {
  return rs.filter((r) => (!f.changedOnly || !changed || changed.has(r.message_id)) && (!f.attacksOnly || isAttack(r)) && (!f.deniedOnly || deniedCount(r) > 0) && (f.trust === "all" || r.trust.level === f.trust));
}

export function MessagesTable({ results, filters, setFilters, selectedId, onSelect, view, setView, available, changed }: {
  results: MessageResult[]; filters: Filters; setFilters: (f: Filters) => void; selectedId: string | null;
  onSelect: (id: string) => void; view: Enforcement; setView: (v: Enforcement) => void; available: Enforcement[];
  /** message ids whose outcome differs between OFF and ON (null until both runs exist) */
  changed: Set<string> | null;
}) {
  const rows = applyFilters(results, filters, changed);
  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        {available.length > 1 && (
          <div className="mr-3 flex gap-1 rounded-pill border border-ink p-1">
            {(["off", "on"] as const).filter((m) => available.includes(m)).map((m) => (
              <button key={m} aria-pressed={view === m} onClick={() => setView(m)} className={`rounded-pill px-4 py-1 text-[15px] font-[540] ${view === m ? "bg-ink text-canvas" : ""}`}>AgntID {m.toUpperCase()}</button>
            ))}
          </div>
        )}
        {changed && <Pill on={filters.changedOnly} onClick={() => setFilters({ ...filters, changedOnly: !filters.changedOnly })}>What changed ({changed.size})</Pill>}
        <Pill on={filters.attacksOnly} onClick={() => setFilters({ ...filters, attacksOnly: !filters.attacksOnly })}>Attacks only</Pill>
        <Pill on={filters.deniedOnly} onClick={() => setFilters({ ...filters, deniedOnly: !filters.deniedOnly })}>Denied only</Pill>
        <span className="mx-1 h-5 w-px bg-hairline" />
        <Pill on={filters.trust === "all"} onClick={() => setFilters({ ...filters, trust: "all" })}>All senders</Pill>
        {TRUST_ORDER.map((t: TrustLevel) => (
          <Pill key={t} on={filters.trust === t} onClick={() => setFilters({ ...filters, trust: filters.trust === t ? "all" : t })}>{TRUST_LABEL[t]}</Pill>
        ))}
        <span className="t-eyebrow ml-auto">{rows.length} of {results.length}</span>
      </div>

      <div className="overflow-x-auto rounded-lg border border-hairline">
        <table className="w-full min-w-[980px] border-collapse text-left text-[15px]">
          <thead>
            <tr className="border-b border-hairline">
              {["Message", "Sender", "Trust", "Routing", "Actions attempted", "Money moved"].map((h) => (
                <th key={h} className="t-eyebrow px-4 py-3 font-normal">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const selected = r.message_id === selectedId;
              return (
                <tr key={r.message_id} onClick={() => onSelect(r.message_id)} tabIndex={0}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(r.message_id); } }}
                  className={`cursor-pointer border-b border-hairline-soft align-top last:border-0 hover:bg-soft ${selected ? "bg-soft" : ""}`}>
                  <td className="max-w-[320px] px-4 py-3">
                    <div className="flex items-center gap-2">
                      <span className="t-mono">{r.message_id}</span>
                      {isAttack(r) && <span className="rounded-pill bg-ink px-2 py-0.5 text-[11px] font-[540] text-canvas">ATTACK</span>}
                      {isControl(r) && <span className="rounded-pill border border-ink px-2 py-0.5 text-[11px] font-[540]">CONTROL</span>}
                    </div>
                    <div className="mt-1 line-clamp-2">{r.text}</div>
                  </td>
                  <td className="px-4 py-3"><div className="t-mono">{r.sender.display_name || r.sender.sender_id}</div><div className="t-eyebrow !text-[10px]">{r.sender.kind}</div></td>
                  <td className="px-4 py-3"><TrustBadge level={r.trust.level} /></td>
                  <td className="px-4 py-3"><ActionPill action={r.routing.action} /><div className="mt-1"><DriverTag driver={r.routing.driver} /></div></td>
                  <td className="px-4 py-3">
                    {r.agent.attempts.length === 0 ? <span className="text-[14px]">No actions</span> : (
                      <div className="flex flex-wrap gap-1.5">
                        {r.agent.attempts.map((a, i) => (
                          <DecisionChip key={i} tool={a.call.tool} layer={a.decision.layer}
                            kind={!a.decision.allowed ? "denied" : a.harmful ? "harm" : "allowed"} />
                        ))}
                      </div>
                    )}
                  </td>
                  <td className="tabular px-4 py-3">{r.money_moved_inr > 0 ? <span className={r.harmful_money_lost_inr > 0 ? "rounded-md bg-coral px-2 py-0.5 font-[540]" : "font-[540]"}>{inr(r.money_moved_inr)}</span> : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {rows.length === 0 && <div className="p-6"><Empty title="No messages match" body="Loosen a filter to see more." /></div>}
      </div>
    </div>
  );
}
