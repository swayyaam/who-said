import type { ReactNode } from "react";
import type { DecisionLayer, Driver, RouteAction, TrustLevel } from "../types";
import { DRIVER_LABEL, TRUST_LABEL } from "../lib/format";

export function Eyebrow({ children }: { children: ReactNode }) {
  return <div className="t-eyebrow">{children}</div>;
}

type BtnProps = { children: ReactNode; onClick?: () => void; disabled?: boolean; variant?: "primary" | "secondary"; className?: string; title?: string };
export function Button({ children, onClick, disabled, variant = "primary", className = "", title }: BtnProps) {
  const base = "inline-flex items-center justify-center gap-2 rounded-pill px-6 min-h-11 text-[17px] font-[480] tracking-[-0.1px] transition-transform active:scale-[0.98]";
  const look = variant === "primary" ? "bg-ink text-canvas" : "bg-canvas text-ink border border-ink";
  return <button title={title} onClick={onClick} disabled={disabled} className={`${base} ${look} ${className}`}>{children}</button>;
}

const TRUST_BG: Record<TrustLevel, string> = {
  unknown: "bg-coral",
  known_contact: "bg-lime",
  group_admin: "bg-lilac",
  verified_business: "bg-mint",
};
export function TrustBadge({ level }: { level: TrustLevel }) {
  return <span className={`inline-block whitespace-nowrap rounded-pill px-3 py-0.5 text-[13px] font-[540] ${TRUST_BG[level]}`}>{TRUST_LABEL[level]}</span>;
}

export function ActionPill({ action }: { action: RouteAction }) {
  const fill = action === "notify" ? "bg-ink text-canvas" : action === "digest" ? "bg-cream" : "bg-soft border border-hairline";
  return <span className={`inline-block rounded-pill px-3 py-0.5 text-[13px] font-[540] capitalize ${fill}`}>{action}</span>;
}

export function DriverTag({ driver }: { driver: Driver }) {
  return <span className="t-eyebrow whitespace-nowrap">via {DRIVER_LABEL[driver]}</span>;
}

export type ChipKind = "allowed" | "denied" | "harm";
export function DecisionChip({ tool, kind, layer }: { tool: string; kind: ChipKind; layer?: DecisionLayer }) {
  const style = kind === "denied" ? "bg-lilac" : kind === "harm" ? "bg-coral" : "bg-mint";
  const mark = kind === "denied" ? "✕" : kind === "harm" ? "!" : "✓";
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-pill px-2.5 py-0.5 text-[12px] font-[540] ${style}`}>
      <span aria-hidden>{mark}</span>
      <span className="font-mono text-[12px]">{tool}</span>
      {kind === "denied" && layer && layer !== "none" && <span className="t-eyebrow !text-[10px]">{layer}</span>}
      <span className="sr-only">{kind === "denied" ? "denied" : kind === "harm" ? "harmful, executed" : "allowed"}</span>
    </span>
  );
}

export function Section({ eyebrow, title, children, right, id }: { eyebrow: string; title: string; children: ReactNode; right?: ReactNode; id?: string }) {
  return (
    <section id={id} className="mt-section first:mt-0">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <Eyebrow>{eyebrow}</Eyebrow>
          <h2 className="t-display-lg mt-2">{title}</h2>
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

export function Empty({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border border-dashed border-hairline bg-soft px-6 py-10 text-center">
      <div className="t-headline">{title}</div>
      <div className="mt-1 max-w-md">{body}</div>
    </div>
  );
}
