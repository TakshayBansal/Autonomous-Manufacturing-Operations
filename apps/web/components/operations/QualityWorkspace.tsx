"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Activity, AlertTriangle, ArrowRight, BadgeCheck, CheckCheck, ClipboardCheck, ShieldAlert } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { closeV2QualityCase, getV2QualityWorkspace, updateV2QualityCase, verifyV2QualityCase, type V2QualityCase } from "@/lib/api";
import { V2QueryFrame } from "./V2QueryFrame";
import { useV2Formatting } from "./V2Formatting";

const percent = (value: number) => `${(value * 100).toFixed(1)}%`;

const nextCaseStatus: Record<string,string> = { open: "investigating", investigating: "action_in_progress", action_in_progress: "effectiveness_review" };

function RecoveryCase({row}:{row:V2QualityCase}) {
  const format=useV2Formatting();
  const client=useQueryClient();
  const [rootCause,setRootCause]=useState(row.root_cause??"");
  const [correctiveAction,setCorrectiveAction]=useState(row.corrective_action??"");
  const [criteria,setCriteria]=useState(row.effectiveness_criteria??"");
  const [result,setResult]=useState(row.effectiveness_result??"");
  useEffect(()=>{setRootCause(row.root_cause??"");setCorrectiveAction(row.corrective_action??"");setCriteria(row.effectiveness_criteria??"");setResult(row.effectiveness_result??"")},[row]);
  const refresh=()=>client.invalidateQueries({queryKey:["quality-workspace"]});
  const advance=useMutation({mutationFn:()=>updateV2QualityCase(row.id,{version:row.version,status:nextCaseStatus[row.status]??row.status,containment_summary:row.containment_summary,root_cause:rootCause,corrective_action:correctiveAction,effectiveness_criteria:criteria,effectiveness_result:result,evidence:row.evidence}),onSuccess:refresh});
  const verify=useMutation({mutationFn:()=>verifyV2QualityCase(row.id,row.version,result),onSuccess:refresh});
  const close=useMutation({mutationFn:()=>closeV2QualityCase(row.id,row.version),onSuccess:refresh});
  const error=(advance.error||verify.error||close.error) as Error|null;
  return <article className="v2-quality-case"><header><div><span>{row.case_type.toUpperCase()} · {row.number}</span><h3>{row.title}</h3></div><span className={`v2-state ${row.status}`}>{row.status.replaceAll("_"," ")}</span></header><p>{row.problem_statement}</p><dl><div><dt>Containment</dt><dd>{row.containment_summary??"Not recorded"}</dd></div><div><dt>Due</dt><dd>{row.due_at?format.date(row.due_at):"Not set"}</dd></div></dl>{!["verified","closed"].includes(row.status)&&<div className="v2-quality-investigation"><label>Confirmed root cause<textarea value={rootCause} onChange={event=>setRootCause(event.target.value)} placeholder="Human-confirmed root cause"/></label><label>Corrective action<textarea value={correctiveAction} onChange={event=>setCorrectiveAction(event.target.value)} placeholder="Action that removes the cause"/></label><label>Effectiveness criteria<textarea value={criteria} onChange={event=>setCriteria(event.target.value)} placeholder="Observable recurrence check"/></label>{row.status==="effectiveness_review"&&<label>Effectiveness result<textarea value={result} onChange={event=>setResult(event.target.value)} placeholder="Evidence that the action worked"/></label>}</div>}<footer>{nextCaseStatus[row.status]&&<button onClick={()=>advance.mutate()} disabled={advance.isPending}>{row.status==="open"?"Start investigation":row.status==="investigating"?"Start corrective action":"Send for effectiveness review"}<ArrowRight/></button>}{row.status==="effectiveness_review"&&<button onClick={()=>verify.mutate()} disabled={!rootCause||!correctiveAction||!criteria||result.length<5||verify.isPending}><CheckCheck/> Verify effectiveness</button>}{row.status==="verified"&&<button onClick={()=>close.mutate()} disabled={close.isPending}><ClipboardCheck/> Close case</button>}{row.status==="closed"&&<span><BadgeCheck/> Closed with verified effectiveness</span>}</footer>{error&&<p className="v2-form-error" role="alert">{error.message}</p>}</article>;
}

function QualityContent() {
  const format=useV2Formatting();
  const query = useQuery({ queryKey: ["quality-workspace"], queryFn: getV2QualityWorkspace });
  if (query.isLoading) return <div className="v2-loading-region">Calculating quality loss and containment…</div>;
  if (query.error || !query.data) return <div className="v2-degraded"><AlertTriangle/><strong>Quality consequence data is unavailable.</strong></div>;
  const data = query.data;
  const maxValue = Math.max(...data.pareto.map(row => row.value??0), 1);
  return <>
    <div className="v2-page-heading"><div><p>Quality</p><h1>Contain defects before they become production loss.</h1><span>First-pass yield, value-weighted defects and recovery ownership in one operating view.</span></div></div>
    <section className="v2-domain-pulse">
      <div><span>Rejection rate</span><strong className={data.pulse.rejection_rate > data.pulse.target_rejection_rate ? "negative" : ""}>{percent(data.pulse.rejection_rate)}</strong><small>Target {percent(data.pulse.target_rejection_rate)}</small></div>
      <div><span>First-pass yield</span><strong>{percent(data.pulse.fpy)}</strong><small>Current event window</small></div>
      <div><span>Active holds</span><strong>{data.pulse.active_holds}</strong><small>Containment required</small></div>
      <div><span>Scrap / rework impact</span><strong>{data.pulse.scrap_rework_impact==null?"Restricted":format.money(data.pulse.scrap_rework_impact)}</strong><small>{data.pulse.scrap_rework_impact==null?"Financial role required":"Estimated exposure"}</small></div>
    </section>
    <div className="v2-domain-grid">
      <section className="v2-panel v2-domain-primary"><div className="v2-panel-heading"><div><p>Loss Pareto</p><h2>Defects ranked by business value</h2></div></div><div className="v2-pareto-list">{data.pareto.map(row => <div key={row.defect}><header><strong>{row.defect.replaceAll("_", " ")}</strong><span>{row.quantity} rejected · {row.value==null?"value restricted":format.money(row.value)}</span></header><i><b style={{ width: `${(row.value??row.quantity) / maxValue * 100}%` }}/></i></div>)}</div></section>
      <section className="v2-panel"><div className="v2-panel-heading"><div><p>Containment</p><h2>Lots under control</h2></div><ShieldAlert/></div><div className="v2-containment-list">{data.containments.map(row => <article key={row.id}><span className={`v2-state ${row.status}`}>{row.status}</span><strong>{row.affected_lot ?? "Affected production"}</strong><p>{row.type.replaceAll("_", " ")} · {row.disposition ?? "Disposition pending"}</p>{row.deviation_id && <Link href={`/v2/deviations/${row.deviation_id}`}>Open recovery <ArrowRight/></Link>}</article>)}</div></section>
      <section className="v2-panel v2-domain-wide"><div className="v2-panel-heading"><div><p>Statistical process control</p><h2>Measurements against control limits</h2></div><Activity/></div><div className="v2-spc-signals">{data.spc_signals.map(row=><article key={row.id}><span className={`v2-state ${row.state}`}>{row.state}</span><div><strong>{row.measurement_name??"Process measurement"}</strong><small>{row.material_lot_id??"No lot reference"} · {format.dateTime(row.occurred_at)}</small></div><b>{row.measurement_value}</b><span>{row.lower_control_limit??"—"}–{row.upper_control_limit??"—"}</span></article>)}</div></section>
      <section className="v2-panel v2-domain-wide"><div className="v2-panel-heading"><div><p>Governed recovery</p><h2>NCR and CAPA effectiveness</h2></div><ClipboardCheck/></div><div className="v2-quality-cases">{data.recovery_cases.map(row=><RecoveryCase row={row} key={row.id}/>)}</div></section>
      <section className="v2-panel v2-domain-wide"><div className="v2-panel-heading"><div><p>Active deviations</p><h2>Quality losses needing action</h2></div><BadgeCheck/></div><div className="v2-domain-deviations">{data.deviations.map(row => <Link href={`/v2/deviations/${row.id}`} key={row.id}><span className={`v2-state ${row.severity}`}>{row.severity}</span><div><strong>{row.title}</strong><small>{row.status.replaceAll("_", " ")} · {row.lost_units} units exposed</small></div><b>{row.financial_impact==null?"Restricted":format.money(row.financial_impact,row.currency)}</b><ArrowRight/></Link>)}</div></section>
    </div>
  </>;
}

export function QualityWorkspace() { return <V2QueryFrame>{() => <QualityContent/>}</V2QueryFrame>; }
