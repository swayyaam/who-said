import { useEffect, useState } from "react";
import { api } from "../api";
import type { Enforcement, Preferences, RunDetail } from "../types";
import { findTamper, PREF_LABEL, prefValue, revert } from "../lib/prefs";
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

export function PreferencesView({ runs }: { runs: Runs }) {
  const offT = runs.off ? findTamper(runs.off.results) : null;
  const onT = runs.on ? findTamper(runs.on.results) : null;
  const t = offT ?? onT;
  const [live, setLive] = useState<Preferences | null>(null);
  const user = t?.userId;
  useEffect(() => {
    if (!user) { setLive(null); return; }
    let ok = true;
    api.getPreferences(user).then((p) => ok && setLive(p)).catch(() => ok && setLive(null));
    return () => { ok = false; };
  }, [user, runs]);

  if (!t) return <Empty title="No preference-tampering attempt yet" body="Run the demo dataset: one unknown sender tries to install a standing auto-pay instruction through message text." />;

  const after = offT?.after ?? null;
  const before = after ? revert(after, offT!) : live;
  const field = (t.key.endsWith("s") ? t.key : `${t.key}s`) as keyof Preferences;
  return (
    <div>
      <div className="mb-6 max-w-3xl rounded-md bg-soft p-4">
        <Eyebrow>The attack · {t.messageId} · user {t.userId}</Eyebrow>
        <p className="mt-1">An unknown sender asks the agent to save a standing instruction: <span className="t-mono">{t.key} = {t.value}</span>. Only the user may change preferences, never an incoming message.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <Col tag="Before" title="Starting preferences" prefs={before} tone="border border-hairline" />
        <Col tag="AgntID OFF" title={after ? "Rewritten by the message" : "Not run yet"} prefs={after} changed={field} tone={after ? "bg-coral" : "border border-dashed border-hairline"} />
        <Col tag="AgntID ON" title={runs.on ? "Unchanged" : "Not run yet"} prefs={runs.on ? before : null} tone={runs.on ? "bg-mint" : "border border-dashed border-hairline"} />
      </div>
      {runs.on && onT && !onT.after && <p className="mt-4 text-[14px]">AgntID ON denied the <span className="t-mono">update_preferences</span> call at the policy layer.</p>}
      {live && <p className="mt-2 text-[13px]">Live on server: auto-pay senders · <span className="t-mono">{prefValue(live, "auto_pay_senders")}</span></p>}
    </div>
  );
}
