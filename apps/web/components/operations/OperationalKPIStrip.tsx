"use client";

import type { V2KPIBoard } from "@/lib/api";
import { useV2Formatting } from "./V2Formatting";

export function OperationalKPIStrip({ board }: { board: V2KPIBoard }) {
  const format=useV2Formatting();
  const preferred=["forecast_attainment","fpy","unplanned_downtime","readiness","time_to_acknowledge","verified_recovery"];
  const metrics=board.groups.flatMap(group=>group.metrics.map(metric=>({...metric,group:group.label}))).filter(metric=>preferred.includes(metric.key)).sort((a,b)=>preferred.indexOf(a.key)-preferred.indexOf(b.key));
  const value=(metric:typeof metrics[number])=>metric.value==null?"Restricted":metric.unit==="ratio"?format.percent(metric.value):metric.unit==="currency"?format.money(metric.value):`${format.number(metric.value)}${metric.unit==="minutes"?" min":""}`;
  return <section className="v2-kpi-strip" aria-label="Current shift operating indicators">{metrics.map(metric=><article key={metric.key}><header><span>{metric.group}</span><i className={metric.state}/></header><strong>{value(metric)}</strong><p>{metric.label}</p></article>)}</section>;
}
