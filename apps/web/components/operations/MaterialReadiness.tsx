"use client";

import Link from "next/link";
import { AlertTriangle, ArrowRight, Box, Clock3, PackageCheck, Truck } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getV2MaterialReadiness, type V2Material } from "@/lib/api";
import { V2QueryFrame } from "./V2QueryFrame";
import { useV2Formatting } from "./V2Formatting";

function MaterialDetail({ item }: { item: V2Material }) {
  const format=useV2Formatting();
  const available = item.usable_now + item.confirmed_inbound;
  const width = Math.min(available / Math.max(item.required, 1) * 100, 100);
  return <article className="v2-material-detail"><header><div><span>{item.material}</span><h3>{item.description}</h3></div><span className={`v2-state ${item.state.toLowerCase()}`}>{item.state.replace("_", " ")}</span></header>{item.freshness!=="fresh"&&<div className="v2-source-impact"><AlertTriangle/><div><strong>Data stale</strong><p>Readiness precision is suppressed until the source recovers.</p></div></div>}<div className="v2-readiness-meter"><span style={{ width: `${width}%` }}/><i style={{ left: "100%" }}/></div><dl><div><dt>Required</dt><dd>{format.number(item.required)}</dd></div><div><dt>Usable now</dt><dd>{format.number(item.usable_now)}</dd></div><div><dt>Confirmed inbound</dt><dd>{format.number(item.confirmed_inbound)}</dd></div><div><dt>Unconfirmed</dt><dd>{format.number(item.unconfirmed_inbound)}</dd></div></dl><div className="v2-material-owner"><span>Owner</span><strong>{item.owner}</strong><p>{item.next_action}</p></div><footer><span><Clock3/> Need by {format.time(item.need_by)}</span>{item.v1_requirement_line_id && <Link href="/procurement">Open sourcing record <ArrowRight/></Link>}</footer></article>;
}

function MaterialContent() {
  const format=useV2Formatting();
  const [horizon,setHorizon]=useState(1);
  const query = useQuery({ queryKey: ["material-readiness", horizon], queryFn: () => getV2MaterialReadiness(horizon) });
  return <><div className="v2-page-heading"><div><p>Materials</p><h1>Will production have usable material?</h1><span>Inventory, supplier commitments, inbound timing and quality holds in one readiness view.</span></div><Link className="v2-page-link" href="/v2/materials/procurement">Open Procurement V2 <ArrowRight/></Link></div><div className="v2-filter-row">{[[1,"Today"],[2,"Tomorrow"],[7,"7 Days"]] .map(([value,label])=><button className={horizon===value?"active":""} onClick={()=>setHorizon(Number(value))} key={value}>{label}</button>)}</div>{query.isLoading ? <div className="v2-loading-region">Calculating work-order readiness…</div> : query.error ? <div className="v2-degraded"><AlertTriangle/><strong>Readiness cannot be calculated from the current sources.</strong></div> : <div className="v2-readiness-board">{query.data?.work_orders.map(group => <section className="v2-readiness-order" key={group.work_order.id}><header><div><span>{group.work_order.number}</span><h2>{group.work_order.product}</h2><p><Clock3/> Starts {format.time(group.work_order.start)} · {group.risky_materials} risky material{group.risky_materials===1?"":"s"}{group.biggest_risk?` · biggest ${group.biggest_risk}`:""}</p></div><div className="v2-readiness-summary"><strong>{group.readiness_pct}%</strong><span>ready</span><span className={`v2-state ${group.state.toLowerCase()}`}>{group.state.replace("_", " ")}</span></div></header><div className="v2-order-materials">{group.materials.map(item => <MaterialDetail item={item} key={item.requirement_id}/>)}</div></section>)}</div>}</>;
}
export function MaterialReadiness() { return <V2QueryFrame>{() => <MaterialContent/>}</V2QueryFrame>; }
