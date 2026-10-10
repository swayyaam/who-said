import type { MessageResult, Preferences } from "../types";

export interface PrefTamper {
  userId: string;
  messageId: string;
  key: string;
  value: string;
  /** Preferences the attempt would produce / did produce (present when the call ran). */
  after: Preferences | null;
}

/** Find the preference-tampering attempt in a run, whether it ran (OFF) or was denied (ON). */
export function findTamper(results: MessageResult[]): PrefTamper | null {
  for (const r of results) {
    const a = r.agent.attempts.find((x) => x.call.tool === "update_preferences" && r.scenario?.kind === "attack");
    if (!a) continue;
    const res = a.result as { preferences?: Preferences } | null;
    return {
      userId: r.user_id,
      messageId: r.message_id,
      key: String(a.call.model_args.key ?? ""),
      value: String(a.call.model_args.value ?? ""),
      after: a.executed && res?.preferences ? res.preferences : null,
    };
  }
  return null;
}

/** Undo the tamper to recover the preferences from before the run (the field it touched). */
export function revert(after: Preferences, t: PrefTamper): Preferences {
  const copy: Preferences = JSON.parse(JSON.stringify(after));
  const field = t.key.endsWith("s") ? t.key : `${t.key}s`;
  const cur = (copy as unknown as Record<string, unknown>)[field];
  if (Array.isArray(cur)) (copy as unknown as Record<string, unknown>)[field] = cur.filter((v) => v !== t.value);
  return copy;
}

export const PREF_LABEL: Record<keyof Preferences, string> = {
  never_mute_senders: "Never mute senders",
  never_mute_groups: "Never mute groups",
  never_mute_businesses: "Never mute businesses",
  mute_promotions: "Mute promotions",
  dnd_window: "Do-not-disturb window",
  auto_pay_senders: "Auto-pay senders",
};

export function prefValue(p: Preferences, k: keyof Preferences): string {
  const v = p[k];
  if (Array.isArray(v)) return v.length ? v.join(", ") : "None";
  if (typeof v === "boolean") return v ? "On" : "Off";
  return v ?? "None";
}
