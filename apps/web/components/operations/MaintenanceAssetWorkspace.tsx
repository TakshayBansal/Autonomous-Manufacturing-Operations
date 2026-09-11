"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AlertTriangle, ArrowLeft, ArrowRight, CircleDot, PackageCheck, PauseCircle, Play, Repeat2, Wrench, CheckCheck } from "lucide-react";
import { getV2MaintenanceAsset, transitionV2MaintenanceWork, type V2MaintenanceAsset } from "@/lib/api";
import { V2QueryFrame } from "./V2QueryFrame";
import { useV2Formatting } from "./V2Formatting";

type Work = V2MaintenanceAsset["work"][number];

function RecoveryWork({ work, assetId }: { work: Work; assetId: string }) {
  const client = useQueryClient();
  const [note, setNote] = useState(work.resolution ?? "");
  const [error, setError] = useState("");
  const transition = useMutation({
    mutationFn: (command: "start" | "wait" | "complete") => transitionV2MaintenanceWork(work.id, command, work.version, note, work.spare_available ?? undefined),
    onSuccess: () => {
      setError("");
      void client.invalidateQueries({ queryKey: ["maintenance-asset", assetId] });
      void client.invalidateQueries({ queryKey: ["maintenance-workspace"] });
      void client.invalidateQueries({ queryKey: ["v2-command-center"] });
    },
    onError: failure => setError(failure instanceof Error ? failure.message : "Recovery transition failed"),
  });
  return <article>
    <header><span className={`v2-state ${work.status}`}>{work.status.replaceAll("_", " ")}</span><small>{work.spare_code ?? "No spare"}</small></header>
    <strong>{work.title}</strong>
    <p>{work.spare_code ? work.spare_available ? "Required spare is available and must be issued against the work record." : "Recovery is blocked until the required spare is available." : "No material dependency is recorded."}</p>
    <label className="v2-recovery-note"><span>{work.status === "in_progress" ? "Resolution or blocker evidence" : "Work note"}</span><textarea value={note} onChange={event => setNote(event.target.value)} placeholder="Record the observed condition and work performed"/></label>
    <div className="v2-recovery-actions">
      {["open", "waiting"].includes(work.status) && <button onClick={() => transition.mutate("start")} disabled={transition.isPending}><Play/> Start work</button>}
      {["open", "in_progress"].includes(work.status) && <button onClick={() => transition.mutate("wait")} disabled={transition.isPending || note.trim().length < 3}><PauseCircle/> Record blocker</button>}
      {work.status === "in_progress" && <button className="primary" onClick={() => transition.mutate("complete")} disabled={transition.isPending || note.trim().length < 5}><CheckCheck/> Complete recovery</button>}
    </div>
    {error && <span className="v2-form-error" role="alert">{error}</span>}
    {work.deviation_id && <Link href={`/v2/deviations/${work.deviation_id}`}>Open linked operational deviation <ArrowRight/></Link>}
  </article>;
}

function AssetContent({ assetId }: { assetId: string }) {
  const format = useV2Formatting();
  const query = useQuery({ queryKey: ["maintenance-asset", assetId], queryFn: () => getV2MaintenanceAsset(assetId) });
  if (query.isLoading) return <div className="v2-loading-region">Hydrating asset, fault and recovery context…</div>;
  if (query.error || !query.data) return <div className="v2-degraded"><AlertTriangle/><strong>Asset context is unavailable.</strong></div>;
  const row = query.data;
  return <>
    <div className="v2-page-heading"><div><p>Maintenance · {row.asset.code}</p><h1>{row.asset.name}</h1><span>Reliability consequence and governed recovery—not CMMS administration.</span></div><Link className="v2-page-link" href="/v2/maintenance"><ArrowLeft/> Maintenance board</Link></div>
    <section className="v2-asset-detail-hero">
      <div><span className={`v2-state ${row.state}`}>{row.state}</span><small>{row.asset.criticality} criticality</small><strong>{row.production_impact} units</strong><p>Current production exposure</p></div>
      {row.current_fault ? <div className="v2-current-fault"><header><CircleDot/><span>Active fault {row.current_fault.code}</span></header><h2>{row.current_fault.message}</h2><p>Observed {format.dateTime(row.current_fault.occurred_at)}</p><strong><Repeat2/> {row.current_fault.repeat_count} occurrences in the available history</strong></div> : <div className="v2-no-fault"><PackageCheck/> No active fault</div>}
    </section>
    <div className="v2-asset-detail-grid">
      <section className="v2-panel"><div className="v2-panel-heading"><div><p>Recovery work</p><h2>Restore output safely</h2></div><Wrench/></div>{row.work.length ? <div className="v2-maintenance-work-list">{row.work.map(work => <RecoveryWork work={work} assetId={assetId} key={work.id}/>)}</div> : <p>No open maintenance recovery is linked to this asset.</p>}</section>
      <section className="v2-panel"><div className="v2-panel-heading"><div><p>Reliability interpretation</p><h2>What the history supports</h2></div></div><div className="v2-reliability-note"><strong>{row.current_fault && row.current_fault.repeat_count > 1 ? "Recurring condition requires permanent countermeasure" : "No proven recurring condition"}</strong><p>Fault recurrence is evidence of repetition, not proof of physical root cause. Inspection and maintenance evidence remain authoritative.</p></div><dl className="v2-reliability-facts"><div><dt>Asset state</dt><dd>{row.state}</dd></div><div><dt>Repeat count</dt><dd>{row.current_fault?.repeat_count ?? 0}</dd></div><div><dt>Output exposed</dt><dd>{row.production_impact} units</dd></div><div><dt>Open work</dt><dd>{row.work.length}</dd></div></dl></section>
    </div>
  </>;
}

export function MaintenanceAssetWorkspace({ assetId }: { assetId: string }) { return <V2QueryFrame>{() => <AssetContent assetId={assetId}/>}</V2QueryFrame>; }
