"use client";

import Link from "next/link";
import { AlertTriangle, ArrowLeft, ArrowRight, CircleCheck, Clock3, PackageCheck, UserRoundCheck } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { getV2Procurement } from "@/lib/api";
import { V2QueryFrame } from "./V2QueryFrame";

const internalOwners = new Set(["procurement", "approver", "quality", "stores"]);

function ProcurementContent() {
  const query = useQuery({ queryKey: ["procurement-v2"], queryFn: getV2Procurement });
  const cycles = query.data ?? [];
  const waitingSupplier = cycles.filter(cycle => cycle.waiting_on === "supplier").length;
  const waitingInternal = cycles.filter(cycle => internalOwners.has(cycle.waiting_on)).length;
  const onTrack = cycles.filter(cycle => cycle.current_stage === "Ready").length;
  return <>
    <div className="v2-page-heading"><div><p>Materials · Procurement</p><h1>Protect production continuity</h1><span>Sourcing is shown as a material-to-ready lifecycle, with existing V1 records retained as canonical detail.</span></div><Link className="v2-page-link" href="/v2/materials"><ArrowLeft/> Material readiness</Link></div>
    {query.isLoading ? <div className="v2-loading-region">Loading linked procurement lifecycles…</div> : query.error ? <div className="v2-degraded"><AlertTriangle/><div><strong>Procurement lifecycle context is unavailable.</strong><p>Material readiness remains separate from sourcing progress until the canonical V1 records can be read.</p></div><button onClick={() => query.refetch()}>Retry</button></div> : !cycles.length ? <div className="v2-empty-compact"><PackageCheck/><strong>No production sourcing cycle needs attention</strong><p>New material requirements will appear here when they are linked to the canonical procurement workflow.</p></div> : <>
    <div className="v2-procurement-buckets">
      <div><strong>{cycles.filter(cycle => cycle.current_stage !== "Ready").length}</strong><span>Needs attention</span></div>
      <div><strong>{waitingSupplier}</strong><span>Waiting supplier</span></div>
      <div><strong>{waitingInternal}</strong><span>Waiting internal</span></div>
      <div><strong>{onTrack}</strong><span>Ready</span></div>
    </div>
    {cycles.map(cycle => <section className="v2-procurement-cycle" key={cycle.id}>
      <header><div><span>{cycle.number}</span><h2>Production material sourcing lifecycle</h2></div><Link href="/procurement">Open canonical workbench <ArrowRight/></Link></header>
      <div className="v2-procurement-focus"><div><Clock3/><span>Current stage</span><strong>{cycle.current_stage}</strong></div><div><UserRoundCheck/><span>Waiting on</span><strong>{cycle.waiting_on}</strong></div><div><span>Elapsed in stage</span><strong>{cycle.wait_minutes < 1 ? "Just entered" : `${cycle.wait_minutes} min`}</strong><small>{cycle.next_action}</small></div></div>
      <div className="v2-stage-flow">{cycle.stages.map((stage, index) => {
        const done = !["not_started", "waiting", "pending_approval"].includes(stage.state);
        return <div key={stage.label} className={done ? "done" : stage.label === cycle.current_stage ? "active" : "waiting"}><i>{done ? <CircleCheck/> : <Clock3/>}</i><span>{stage.label}</span><small>{stage.state.replaceAll("_", " ")} · {stage.owner}</small>{stage.dependency && <em>Depends on {stage.dependency}</em>}{index < cycle.stages.length - 1 && <b/>}</div>;
      })}</div>
    </section>)}
    </>}
  </>;
}

export function ProcurementV2() { return <V2QueryFrame>{() => <ProcurementContent/>}</V2QueryFrame>; }
