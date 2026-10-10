import { useEffect, useState } from "react";
import { api } from "../api";
import type { Enforcement, Preferences, RunDetail } from "../types";
import { findTampers, PREF_LABEL, prefValue, revert, type PrefTamper } from "../lib/prefs";
import { Empty, Eyebrow } from "./ui";

type Runs = Partial<Record<Enforcement, RunDetail>>;

function Col({ title, tag, prefs, changed, tone }: { title: string; tag: string; prefs: Preferences | null; changed?: keyof Preferences; tone: string }) {
  return (
    <div className={`rounded-lg p-5 ${tone}`}>
      <Eyebrow>{tag}</Eyebrow>
      <div className="t-card-title mt-1">{title}</div>
      <dl className="mt-3 space-y-2">
        {prefs ? (Object.keys(PREF_LABEL) as (keyof Preferences)[]).map((k) => (
          <div key={k} className={`grid grid-cols-[1fr_1fr] gap-3 rounded-md px-2 py-1 text-[14px] ${changed === k ? "bg-ink text-canvas" : ""}`}>
            <dt>{PREF_LABEL[k]}</dt><dd className="t-mono break-all">{prefValue(prefs, k)}</dd>
          </div>
        )) : <div className="text-[14px]">Run to see this state.</div>}
      </dl>
    </div>
  );
}

function Attack({ t, runs }: { t: PrefTamper; runs: Runs }) {
  const after = t.after;
  // Prefer the backend's own record (RunDetail.preference_changes); fall back to undoing the attempt.
  const changes = (runs.off?.preference_changes ?? []).filter((c) => c.user_id === t.userId);
  const before: Preferences | null = after
    ? changes.length
      ? changes.reduce((p, c) => ({ ...p, [c.key]: c.before }), { ...after } as Preferences)
      : revert(after, t)
    : null;
  const field = (changes[0]?.key ?? (t.key.endsWith("s") ? t.key : `${t.key}s`)) as keyof Preferences;
  const onAttempt = runs.on?.results.find((r) => r.message_id === t.messageId)?.agent.attempts.find((a) => a.call.tool === "update_preferences");
  return (
    <div>
      <div className="mb-4 max-w-3xl rounded-md bg-soft p-4">
        <Eyebrow>The attack · {t.messageId} · user {t.userId}</Eyebrow>
        <p className="mt-1">A message tries to save a standing instruction: <span className="t-mono break-all">{t.key} = {t.value}</span>. Only the user may change preferences, never an incoming message.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <Col tag="Before" title="Starting preferences" prefs={before} tone="border border-hairline" />
        <Col tag="AgntID OFF" title={after ? "Rewritten by the message" : "Not run yet"} prefs={after} changed={field} tone={after ? "bg-coral" : "border border-dashed border-hairline"} />
        <Col tag="AgntID ON" title={!runs.on ? "Not run yet" : onAttempt ? "Blocked, unchanged" : "Unchanged"} prefs={runs.on ? before : null} tone={runs.on ? "bg-mint" : "border border-dashed border-hairline"} />
      </div>
      {onAttempt && !onAttempt.decision.allowed && <p className="mt-3 text-[14px]">AgntID ON denied the <span className="t-mono">update_preferences</span> call at the {onAttempt.decision.layer} layer.</p>}
    </div>
  );
}

export function PreferencesView({ runs }: { runs: Runs }) {
  const offT = runs.off ? findTampers(runs.off.results) : [];
  const tampers = offT.length ? offT : runs.on ? findTampers(runs.on.results) : [];
  const [live, setLive] = useState<Record<string, Preferences>>({});
  const users = [...new Set(tampers.map((t) => t.userId))].join(",");
  useEffect(() => {
    let ok = true;
    Promise.all(users.split(",").filter(Boolean).map((u) => api.getPreferences(u).then((p) => [u, p] as const).catch(() => null)))
      .then((rows) => ok && setLive(Object.fromEntries(rows.filter((r): r is readonly [string, Preferences] => !!r))));
    return () => { ok = false; };
  }, [users, runs]);

  if (!tampers.length) return <Empty title="No preference-tampering attempt yet" body="Run the demo dataset: messages from unknown senders try to install standing instructions through message text." />;
  return (
    <div className="space-y-10">
      {tampers.map((t) => <Attack key={t.messageId} t={t} runs={runs} />)}
      {Object.entries(live).length > 0 && (
        <p className="text-[13px]">Live on server after the latest run: {Object.entries(live).map(([u, p]) => `${u} auto-pay ${prefValue(p, "auto_pay_senders")}, never-mute ${prefValue(p, "never_mute_senders")}`).join(" · ")}</p>
      )}
    </div>
  );
}
