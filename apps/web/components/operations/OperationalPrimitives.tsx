import type { ReactNode } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, Cable, CheckCircle2, Factory, Upload } from "lucide-react";

function humanize(value: string) {
  return value.replaceAll("_", " ");
}

export function StatusBadge({ status }: { status: string }) {
  return <span className={`v2-state ${status}`}>{humanize(status)}</span>;
}

export function SeverityBadge({ severity }: { severity: string }) {
  return <span className={`v2-state ${severity}`}>{humanize(severity)}</span>;
}

export function OwnerChip({ role, name }: { role?: string | null; name?: string | null }) {
  return <span className="v2-owner-chip">{name ?? (role ? humanize(role) : "Owner pending")}</span>;
}

export function EntityChip({ type, label }: { type?: string; label: string }) {
  return <span className="v2-entity-chip">{type ? `${humanize(type)} · ` : ""}{label}</span>;
}

export function EvidenceChip({ children }: { children: ReactNode }) {
  return <span className="v2-evidence-chip">{children}</span>;
}

export function EmptyOperationalState({ title, detail, icon }: {
  title: string; detail: string; icon?: ReactNode;
}) {
  return <div className="v2-empty-compact">{icon ?? <CheckCircle2/>}<strong>{title}</strong><p>{detail}</p></div>;
}

export function DegradedDataBanner({ title, detail, onRetry }: {
  title: string; detail: string; onRetry?: () => void;
}) {
  return <div className="v2-degraded" role="alert"><AlertTriangle/><div><strong>{title}</strong><p>{detail}</p></div>{onRetry&&<button onClick={onRetry}>Retry</button>}</div>;
}

export function PlantActivationState({ compact = false }: { compact?: boolean }) {
  return <section className={`v2-activation-state ${compact ? "compact" : ""}`}>
    <div className="v2-activation-copy">
      <span className="v2-eyebrow"><i/> Plant workspace ready</span>
      <h2>{compact ? "Your work queue will appear here" : "Bring the first production line online"}</h2>
      <p>{compact
        ? "Actions are created automatically when a shift, production plan, or operational deviation is active."
        : "The operating surface is configured, but no active shift is supplying production context yet. Start with one line or connect an existing source."}</p>
      <div className="v2-activation-actions">
        <Link className="primary" href="/v2/setup"><Factory/> Configure plant <ArrowRight/></Link>
        <Link href="/v2/integrations"><Cable/> Connect a source</Link>
      </div>
    </div>
    {!compact && <div className="v2-activation-steps" aria-label="Plant activation progress">
      <div className="done"><span><CheckCircle2/></span><div><small>01</small><strong>Workspace</strong><p>Plant and team are ready</p></div></div>
      <div><span><Factory/></span><div><small>02</small><strong>Operating model</strong><p>Add a line, shift and target</p></div></div>
      <div><span><Upload/></span><div><small>03</small><strong>Production signal</strong><p>Connect or import actuals</p></div></div>
    </div>}
  </section>;
}

export function openContextualGigi(context: string, question: string) {
  window.dispatchEvent(new CustomEvent("v2:open-gigi", { detail: { context, question } }));
}
