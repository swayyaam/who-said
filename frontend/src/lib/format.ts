import type { MessageResult, RunDetail, TrustLevel } from "../types";

export const inr = (n: number) => `₹${Math.round(n).toLocaleString("en-IN")}`;

export const TRUST_LABEL: Record<TrustLevel, string> = {
  unknown: "Unknown",
  known_contact: "Known contact",
  group_admin: "Group admin",
  verified_business: "Verified business",
};

export const TRUST_ORDER: TrustLevel[] = ["unknown", "known_contact", "group_admin", "verified_business"];

export const DRIVER_LABEL = { safety: "Safety", preference: "Preference", learned: "Learned", default: "Default" } as const;

export const isAttack = (r: MessageResult) => r.scenario?.kind === "attack";
export const isControl = (r: MessageResult) => r.scenario?.kind === "control";
export const deniedCount = (r: MessageResult) => r.agent.attempts.filter((a) => !a.decision.allowed).length;
export const actedOn = (r: MessageResult) => r.executed_tools.length > 0;

export function runStats(d: RunDetail) {
  const attacks = d.results.filter(isAttack);
  return {
    attacks: attacks.length,
    attacksBlocked: attacks.filter((r) => r.harmful_executed.length === 0).length,
    messagesActedOn: d.results.filter(actedOn).length,
  };
}

export const humanize = (s: string) => s.replace(/_/g, " ");

/** "1 harmful action" / "2 harmful actions" */
export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
