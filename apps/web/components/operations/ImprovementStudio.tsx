"use client";

import { AlertTriangle, Beaker, CircleDollarSign, FlaskConical, TrendingUp } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { getV2ImprovementWorkspace } from "@/lib/api";
import { V2QueryFrame } from "./V2QueryFrame";
import { useV2Formatting } from "./V2Formatting";

function StudioContent() {
  const format=useV2Formatting();
  const query = useQuery({ queryKey: ["improvement-workspace"], queryFn: getV2ImprovementWorkspace });
  if (query.isLoading) return <div className="v2-loading-region">Discovering recurring, addressable losses…</div>;
  if (query.error || !query.data) return <div className="v2-degraded"><AlertTriangle/><strong>Improvement evidence is unavailable.</strong></div>;
  const financialAccess = query.data.opportunities.every(row=>row.annualized_value!=null);
  const total = query.data.opportunities.reduce((sum, row) => sum + (row.annualized_value??0), 0);
  return <><div className="v2-page-heading"><div><p>Improvement Studio</p><h1>Turn recurring loss into measured experiments.</h1><span>Investigate evidence, test a countermeasure, and separate estimated opportunity from verified benefit.</span></div></div>
    <section className="v2-improvement-hero"><div><TrendingUp/><span>Addressable annualized opportunity</span><strong>{financialAccess?format.money(total):"Restricted"}</strong><small>{financialAccess?"Modelled from current evidence—not claimed savings":"Financial role required"}</small></div><div><Beaker/><span>Active experiments</span><strong>{query.data.experiments.filter(row => row.status === "running").length}</strong><small>With explicit baselines and targets</small></div></section>
    <section className="v2-panel"><div className="v2-panel-heading"><div><p>Recurring recovery failures</p><h2>Stop fighting the same loss reactively</h2></div><AlertTriangle/></div>{query.data.recurring_recovery_failures.length?<div className="v2-opportunity-list">{query.data.recurring_recovery_failures.map(row=><article key={row.signature}><b>{row.incidents}</b><div><span>{Math.round(row.recurrence_rate*100)}% recurrence · {row.failed_recoveries} failed recoveries</span><strong>{row.title}</strong><small>{row.recommendation}</small></div><em>{row.estimated_monthly_loss==null?"Restricted":format.money(row.estimated_monthly_loss)}<small>observed loss</small></em></article>)}</div>:<p>No recovery pattern has crossed the recurrence threshold yet. Verified outcomes will populate this view.</p>}</section>
    <div className="v2-improvement-grid"><section className="v2-panel"><div className="v2-panel-heading"><div><p>Opportunity queue</p><h2>Ranked by addressable value</h2></div><CircleDollarSign/></div><div className="v2-opportunity-list">{query.data.opportunities.map((row, index) => <article key={row.key}><b>{String(index + 1).padStart(2,"0")}</b><div><span>{row.category} · {row.occurrences} occurrences</span><strong>{row.title}</strong><small>{row.evidence.length} evidence records</small></div><em>{row.annualized_value==null?"Restricted":format.money(row.annualized_value)}<small>annualized</small></em></article>)}</div></section>
      <section className="v2-experiment-stack">{query.data.experiments.map(row => <article className="v2-panel v2-experiment" key={row.id}><header><div><p>Experiment</p><h2>{row.title}</h2></div><span className={`v2-state ${row.status}`}>{row.status}</span></header><blockquote>{row.hypothesis}</blockquote><dl><div><dt>Baseline</dt><dd>{String(row.baseline.value)} <small>{String(row.baseline.metric ?? "")}</small></dd></div><div><dt>Target</dt><dd>{String(row.target.value)} <small>{String(row.target.metric ?? "")}</small></dd></div></dl><div className="v2-intervention"><FlaskConical/><div><span>Intervention</span><p>{row.intervention}</p></div></div>{row.benefits.map(item => <footer key={item.id}><div><span>Annualized benefit</span><strong>{item.annualized_value==null?"Restricted":format.money(item.annualized_value)}</strong></div><span className={`v2-state ${item.confidence_state}`}>{item.confidence_state}</span></footer>)}</article>)}</section>
    </div></>;
}
export function ImprovementStudio() { return <V2QueryFrame>{() => <StudioContent/>}</V2QueryFrame>; }
