import type { ComparisonHeadline, HeadlineOutcome, DifferingRow, RunComparison, RunDetail } from "../types";
import { inr, plural } from "./format";

/** Same logic as the backend's build_comparison, used by mock mode (and as a fallback). */
export function buildComparison(off: RunDetail, on: RunDetail): RunComparison {
  const onById = new Map(on.results.map((r) => [r.message_id, r]));
  const differing: DifferingRow[] = [];
  for (const r of off.results) {
    const o = onById.get(r.message_id);
    if (!o) continue;
    const denied = o.agent.attempts.filter((a) => !a.decision.allowed)
      .map((a) => ({ tool: a.call.tool, layer: a.decision.layer, reason: a.decision.reason }));
    if (JSON.stringify(r.executed_tools) !== JSON.stringify(o.executed_tools) || denied.length) {
      differing.push({
        message_id: r.message_id, scenario: r.scenario?.scenario ?? null, kind: r.scenario?.kind ?? null, sender_trust: r.trust.level,
        off: { executed_tools: r.executed_tools, harmful_executed: r.harmful_executed, money_moved_inr: r.money_moved_inr },
        on: { executed_tools: o.executed_tools, harmful_executed: o.harmful_executed, money_moved_inr: o.money_moved_inr, denied },
      });
    }
  }
  const a = off.summary, b = on.summary;
  const paid = Math.round((b.total_money_moved_inr - b.harmful_money_lost_inr) * 100) / 100;
  // Mock mode only (the real API sends its own outcome): the full demo is a "blocked" story.
  const outcome: HeadlineOutcome = b.harmful_executed > 0 ? "leak" : a.harmful_executed > 0 ? "blocked" : b.actions_executed > 0 ? "allowed" : "muted";
  const headline: ComparisonHeadline = {
    outcome,
    off_harmful_executed: a.harmful_executed, off_money_lost_inr: a.harmful_money_lost_inr,
    on_harmful_executed: b.harmful_executed, on_money_lost_inr: b.harmful_money_lost_inr,
    text: `OFF: ${plural(a.harmful_executed, "harmful action")} executed, ${inr(a.harmful_money_lost_inr)} lost. ON: ${b.harmful_executed}, ${inr(b.harmful_money_lost_inr)}.`,
    loss_text: `${inr(a.harmful_money_lost_inr)} → ${inr(b.harmful_money_lost_inr)}`,
    on_controls_ok: b.controls_ok, on_controls_total: b.controls_total, on_legit_paid_inr: paid,
    legit_text: `${b.controls_ok}/${b.controls_total} legitimate actions still work · ${inr(paid)} paid correctly`,
  };
  return { dataset_id: a.dataset_id, off: a, on: b, headline, differing };
}
