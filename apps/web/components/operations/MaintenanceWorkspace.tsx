"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, CircleDot, Cog, PackageCheck, Repeat2 } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { getV2MaintenanceWorkspace } from "@/lib/api";
import { V2QueryFrame } from "./V2QueryFrame";
import { useV2Formatting } from "./V2Formatting";

function MaintenanceContent() {
  const format=useV2Formatting();
  const query = useQuery({ queryKey: ["maintenance-workspace"], queryFn: getV2MaintenanceWorkspace });
  if (query.isLoading) return <div className="v2-loading-region">Calculating asset consequence and recovery…</div>;
  if (query.error || !query.data) return <div className="v2-degraded"><AlertTriangle/><strong>Maintenance consequence data is unavailable.</strong></div>;
  const data = query.data;
  return <>
    <div className="v2-page-heading"><div><p>Maintenance</p><h1>Recover the assets constraining production.</h1><span>Fault recurrence, lost output and recovery work—connected to the operating plan.</span></div></div>
    <section className="v2-domain-pulse">
      <div><span>Assets down</span><strong className={data.pulse.assets_down ? "negative" : ""}>{data.pulse.assets_down}</strong><small>Current production window</small></div>
      <div><span>Production impact</span><strong>{data.pulse.production_impact}</strong><small>Estimated units exposed</small></div>
      <div><span>Repeat faults</span><strong>{data.pulse.repeat_faults}</strong><small>Recurring asset / code pairs</small></div>
      <div><span>Waiting for spare</span><strong>{data.pulse.waiting_for_spare}</strong><small>Recovery work blocked</small></div>
    </section>
    <div className="v2-asset-grid">{data.assets.map(row => <article className={`v2-asset-card ${row.state}`} key={row.asset.id}>
      <header><div className="v2-asset-icon"><Cog/></div><div><span>{row.asset.code} · {row.asset.criticality} criticality</span><h2>{row.asset.name}</h2></div><span className={`v2-state ${row.state}`}>{row.state}</span></header>
      <div className="v2-asset-consequence"><span>Production consequence</span><strong>{row.production_impact} units</strong></div>
      {row.current_fault ? <div className="v2-fault-block"><div><CircleDot/><span>Fault {row.current_fault.code}</span></div><strong>{row.current_fault.message ?? "Equipment fault"}</strong><p>Observed {format.dateTime(row.current_fault.occurred_at)}</p>{row.current_fault.repeat_count > 1 && <em><Repeat2/> Repeated {row.current_fault.repeat_count} times</em>}</div> : <div className="v2-no-fault"><PackageCheck/> No active fault</div>}
      <footer>{row.work.length ? row.work.map(work => <div key={work.id}><span>{work.status.replaceAll("_", " ")}</span><strong>{work.title}</strong><small>{work.spare_code ? `${work.spare_code} · ${work.spare_available ? "spare available" : "waiting for spare"}` : "No spare required"}</small>{work.deviation_id && <Link href={`/v2/deviations/${work.deviation_id}`}>Open production recovery <ArrowRight/></Link>}</div>) : <span>No open recovery work</span>}<Link href={`/v2/maintenance/assets/${row.asset.id}`}>Open asset context <ArrowRight/></Link></footer>
    </article>)}</div>
  </>;
}

export function MaintenanceWorkspace() { return <V2QueryFrame>{() => <MaintenanceContent/>}</V2QueryFrame>; }
