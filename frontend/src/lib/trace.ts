import type { MessageResult, ToolCall } from "../types";
import { DRIVER_LABEL, TRUST_LABEL, inr } from "./format";

export type Tone = "ok" | "bad";
export interface TraceStep { text: string; tone?: Tone }

const clip = (s: string, n = 44) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

/** The one argument worth showing for a tool call, e.g. "₹25,000 → payrail@icici". */
export function keyArg(call: ToolCall): string {
  const a = call.model_args;
  switch (call.tool) {
    case "pay_upi": return `${inr(Number(a.amount_inr ?? 0))} → ${clip(String(a.payee_upi ?? "?"), 28)}`;
    case "forward_message": return `to ${clip(String(a.to ?? "?"), 20)}`;
    case "reply": return a.text ? `“${clip(String(a.text), 28)}”` : "";
    case "create_calendar_event": return clip(String(a.title ?? ""), 32);
    case "update_preferences": return clip(`${a.key ?? ""} = ${a.value ?? ""}`, 36);
    default: return "";
  }
}

/** The pipeline for one message, from data we already receive (the message.completed payload). */
export function buildSteps(r: MessageResult): TraceStep[] {
  const steps: TraceStep[] = [
    { text: `Sender trust: ${TRUST_LABEL[r.trust.level].toLowerCase()}` },
    { text: `Routed: ${r.routing.action} (${DRIVER_LABEL[r.routing.driver].toLowerCase()})` },
  ];
  for (const a of r.agent.attempts) {
    const arg = keyArg(a.call);
    steps.push({ text: `Agent proposed ${a.call.tool}${arg ? ` ${arg}` : ""}` });
    if (!a.decision.enforced) steps.push({ text: a.harmful ? "AgntID off: ran unchecked, harmful" : "AgntID off: ran unchecked", tone: a.harmful ? "bad" : "ok" });
    else if (a.decision.allowed) steps.push({ text: "AgntID: allowed", tone: "ok" });
    else steps.push({ text: `AgntID: denied (${a.decision.layer})`, tone: "bad" });
  }
  return steps;
}
