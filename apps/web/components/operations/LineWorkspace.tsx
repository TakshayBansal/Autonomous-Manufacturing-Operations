"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, Clock3, Wrench, X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getV2LineWorkspace } from "@/lib/api";
import { V2QueryFrame } from "./V2QueryFrame";
import { useV2Formatting } from "./V2Formatting";
import { PlanActualForecastChart } from "./PlanActualForecastChart";

function LineContent({ lineId, shiftId }: { lineId: string; shiftId?: string }) {
  const format=useV2Formatting();
  const [selectedEvent,setSelectedEvent]=useState<NonNullable<import("@/lib/api").V2LineWorkspace["timeline"]>[number]|null>(null);
  const query = useQuery({ queryKey: ["line-workspace", lineId, shiftId], queryFn: () => getV2LineWorkspace(lineId, shiftId), refetchInterval: 60_000 });
  if (query.isLoading) return <div className="v2-loading-region">Loading line state…</div>;
  if (query.error || !query.data?.work_order || !query.data.forecast) return <div className="v2-degraded"><AlertTriangle/><strong>This line has no active work order data.</strong></div>;
  const data = query.data, forecast = data.forecast!, workOrder = data.work_order!;
  return <><div className="v2-line-hero"><div><p>{data.line.code} · Active production</p><h1>{data.line.name}</h1><span>{workOrder.number} · {workOrder.product_code} · {workOrder.product_name}</span></div><div className="v2-line-hero-numbers"><div><span>Target</span><strong>{forecast.target_quantity}</strong></div><div><span>Actual</span><strong>{forecast.actual_quantity}</strong></div><div><span>Forecast</span><strong>{forecast.forecast_quantity}</strong></div><div><span>Gap</span><strong className="negative">{forecast.gap_quantity}</strong></div></div></div>
    <div className="v2-line-workspace-grid">
      <section className="v2-panel v2-line-state-dimensions"><div className="v2-panel-heading"><div><p>Operational state</p><h2>Separate facts, one interpretation</h2></div></div><dl><div><dt>Execution</dt><dd>{data.execution_state}</dd></div><div><dt>Performance</dt><dd>{data.performance_state}</dd></div><div><dt>Machine health</dt><dd>{data.machine_health_state}</dd></div><div><dt>Quality</dt><dd>{data.quality_state}</dd></div><div><dt>Material</dt><dd>{data.material_readiness_state}</dd></div><div><dt>Recovery</dt><dd>{data.recovery_state}</dd></div></dl></section>
      <section className="v2-panel v2-trajectory-panel"><div className="v2-panel-heading"><div><p>Production trajectory</p><h2>Plan, actual and recovery forecast</h2></div><span className={`v2-state ${data.state}`}>{data.state?.replace("_", " ")}</span></div><PlanActualForecastChart points={data.trajectory ?? []}/><div className="v2-chart-legend"><span><i className="plan"/>Plan</span><span><i className="actual"/>Actual</span><span><i className="forecast"/>Forecast</span><b>Confidence: {forecast.confidence}</b></div></section>
      <section className="v2-panel v2-current-recovery"><div className="v2-panel-heading"><div><p>Current recovery</p><h2>{data.current_action?.title ?? "No active action"}</h2></div><Wrench/></div>{data.current_action && <><span className={`v2-state ${data.current_action.priority}`}>{data.current_action.status.replace("_", " ")}</span><p>Owner: {data.current_action.owner_role?.replaceAll("_", " ")}</p><Link href={`/v2/deviations/${data.current_action.deviation_id}`}>Open recovery <ArrowRight/></Link></>}</section>
      {data.recovery&&<section className="v2-panel v2-recovery-status"><div className="v2-panel-heading"><div><p>Recovery status</p><h2>{data.recovery.strategy??"Options under assessment"}</h2></div></div><dl><div><dt>Production gap</dt><dd>{forecast.gap_quantity}</dd></div><div><dt>Expected recovered</dt><dd>+{data.recovery.expected_recovered_units??0}</dd></div><div><dt>Remaining expected gap</dt><dd>-{data.recovery.remaining_expected_gap}</dd></div><div><dt>State</dt><dd>{data.recovery.status.replaceAll("_"," ")}</dd></div></dl><Link href={`/v2/deviations/${data.deviations?.[0]?.id}`}>Open recovery plan <ArrowRight/></Link></section>}
      <section className="v2-panel v2-timeline-panel"><div className="v2-panel-heading"><div><p>Shift timeline</p><h2>What interrupted production</h2></div><Clock3/></div><div className="v2-timeline-track"><span className="run">Running</span>{data.timeline?.map(item => <button type="button" onClick={()=>setSelectedEvent(item)} key={item.id} className={item.type}><strong>{item.type.replaceAll("_", " ")}</strong><small>{item.duration_minutes} min · {item.reason}</small></button>)}<span className="run">Running</span></div>{selectedEvent&&<div className="v2-timeline-detail"><header><div><small>{selectedEvent.type.replaceAll("_"," ")}</small><strong>{selectedEvent.reason}</strong></div><button onClick={()=>setSelectedEvent(null)} aria-label="Close event detail"><X/></button></header><dl><div><dt>Start</dt><dd>{format.time(selectedEvent.start)}</dd></div><div><dt>End</dt><dd>{selectedEvent.end?format.time(selectedEvent.end):"Ongoing"}</dd></div><div><dt>Duration</dt><dd>{selectedEvent.duration_minutes} minutes</dd></div><div><dt>Impact</dt><dd>{selectedEvent.impact}</dd></div></dl>{selectedEvent.deviation_id&&<Link href={`/v2/deviations/${selectedEvent.deviation_id}`}>Open linked deviation <ArrowRight/></Link>}</div>}</section>
      <section className="v2-panel v2-loss-tree"><div className="v2-panel-heading"><div><p>Lost output</p><h2>Loss tree</h2></div></div>{data.loss_tree?.map(item => <div key={item.category}><span>{item.category}</span><strong>{format.number(item.lost_units)} units</strong></div>)}</section>
      <section className="v2-panel v2-recovery-flow"><div className="v2-panel-heading"><div><p>Recovery flow</p><h2>Real action progression</h2></div></div>{data.deviations?.map(item => <Link href={`/v2/deviations/${item.id}`} key={item.id}><i/><div><strong>{item.title}</strong><span>{item.status.replaceAll("_", " ")}</span></div></Link>)}</section>
    </div></>;
}

export function LineWorkspace({ lineId }: { lineId: string }) { return <V2QueryFrame>{(_, shiftId) => <LineContent lineId={lineId} shiftId={shiftId}/>}</V2QueryFrame>; }
