"use client";

import Link from "next/link";
import { useState } from "react";
import { AlertTriangle, ArrowUpRight, CheckCircle2, Factory } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { getV2Operations } from "@/lib/api";
import { V2QueryFrame } from "./V2QueryFrame";

function OperationsContent({ plantId, shiftId }: { plantId: string; shiftId?: string }) {
  const [filter,setFilter]=useState<"all"|"at_risk"|"blocked"|"on_plan">("all");
  const query = useQuery({ queryKey: ["operations-overview", plantId, shiftId], queryFn: () => getV2Operations(plantId, shiftId), refetchInterval: 60_000 });
  const lines=(query.data?.lines??[]).filter(item=>filter==="all"||item.state===filter||filter==="at_risk"&&["watch","high","critical","at_risk"].includes(item.state));
  return <><div className="v2-page-heading"><div><h1>Operations</h1><span>Live line state, active constraints and recovery work.</span></div></div>
    <div className="v2-filter-row" aria-label="Filter production lines">{[["all","All"],["at_risk","At Risk"],["blocked","Blocked"],["on_plan","On Plan"]].map(([value,label])=><button key={value} className={filter===value?"active":""} aria-pressed={filter===value} onClick={()=>setFilter(value as typeof filter)}>{label}</button>)}</div>
    {query.isLoading ? <div className="v2-skeleton-grid"><i/><i/><i/></div> : query.error ? <div className="v2-degraded"><AlertTriangle/><div><strong>Line state could not be loaded.</strong><p>Do not interpret missing line cards as normal operation.</p></div><button onClick={() => query.refetch()}>Retry</button></div> : !query.data?.lines.length ? <div className="v2-empty-compact"><CheckCircle2/><strong>No active production lines</strong><p>Activate a work order or review the selected plant and shift.</p></div> : !lines.length?<div className="v2-empty-compact"><CheckCircle2/><strong>No lines match this status</strong><p>Choose another operational filter; source records remain unchanged.</p></div>:<section className="v2-line-grid">{lines.map((item) => <Link href={`/v2/operations/lines/${item.line.id}`} key={item.line.id} className="v2-line-card">
      <div className="v2-line-card-head"><div><span>{item.line.code}</span><h2>{item.line.name}</h2></div><span className={`v2-state ${item.state}`}>{item.state.replace("_", " ")}</span></div>
      <div className="v2-line-order"><Factory/><div><strong>{item.work_order.number}</strong><span>{item.work_order.product}</span></div></div>
      <div className="v2-line-trajectory"><span style={{ width: `${Math.min(item.actual / Math.max(item.target, 1) * 100, 100)}%` }}/><i style={{ left: `${Math.min(item.forecast / Math.max(item.target, 1) * 100, 100)}%` }}/></div>
      <dl><div><dt>Target</dt><dd>{item.target}</dd></div><div><dt>Actual</dt><dd>{item.actual}</dd></div><div><dt>Forecast</dt><dd>{item.forecast}</dd></div></dl>
      <div className="v2-line-blocker">{item.top_blocker ? <><AlertTriangle/><span>{item.top_blocker.title}</span></> : <span>No active blocker</span>}<ArrowUpRight/></div>
    </Link>)}</section>}
  </>;
}

export function OperationsOverview() { return <V2QueryFrame>{(context, shiftId) => <OperationsContent plantId={context.plant!.id} shiftId={shiftId}/>}</V2QueryFrame>; }
