import type { MessageResult, Preferences } from "../types";

export interface PrefTamper {
  userId: string;
  messageId: string;
  key: string;
  value: string;
  /** Preferences the attempt would produce / did produce (present when the call ran). */
  after: Preferences | null;
}

/** Every preference-tampering attempt in a run, whether it ran (OFF) or was denied (ON). One per message. */
export function findTampers(results: MessageResult[]): PrefTamper[] {
  const out: PrefTamper[] = [];
  for (const r of results) {
    if (r.scenario?.kind !== "attack") continue;
    const attempts = r.agent.attempts.filter((x) => x.call.tool === "update_preferences");
    if (!attempts.length) continue;
    const a = attempts.find((x) => x.executed) ?? attempts[0];
    const res = a.result as { preferences?: Preferences } | null;
    out.push({
      userId: r.user_id,
      messageId: r.message_id,
      key: String(a.call.model_args.key ?? ""),
      value: String(a.call.model_args.value ?? ""),
      after: a.executed && res?.preferences ? res.preferences : null,
    });
  }
  return out;
}

export const findTamper = (results: MessageResult[]): PrefTamper | null => findTampers(results)[0] ?? null;

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
