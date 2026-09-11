"use client";

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, History, ShieldAlert, Timer, TrendingUp } from "lucide-react";
import { selectV2RecoveryStrategy, startV2Recovery, verifyV2Recovery, type V2RecoveryCase, type V2RecoveryStrategy } from "@/lib/api";
import { useV2Formatting } from "../V2Formatting";

function Strategy({row,recommended,selected,onSelect,busy}:{row:V2RecoveryStrategy;recommended:boolean;selected:boolean;onSelect:()=>void;busy:boolean}){
 const format=useV2Formatting();
 return <article className={`v2-recovery-strategy ${recommended?"recommended":""} ${selected?"selected":""}`}>
  <header><div><span>{recommended?"Recommended":row.status.replaceAll("_"," ")}</span><h3>{row.title}</h3></div><strong>{row.recovery_score==null?"—":`${Math.round(row.recovery_score)} / 100`}</strong></header>
  <p>{row.description}</p><div className="v2-strategy-metrics"><span><TrendingUp/> {format.number(row.expected_recovered_units??0)} units</span><span><Timer/> {Math.round((row.implementation_time_seconds??0)/60)} min</span><span><History/> {row.historical_sample_size?`${Math.round((row.historical_effectiveness_score??0)*100)}% (${row.historical_sample_size})`:"Insufficient history"}</span><span><ShieldAlert/> Quality risk {Math.round((row.quality_risk_score??0)*100)}%</span></div>
  <small>{row.reasoning_summary}</small>{row.required_authorities.length>0&&<em>Approval: {row.required_authorities.join(", ").replaceAll("_"," ")}</em>}
  {row.unavailable_reason?<div className="v2-strategy-unavailable">Unavailable: {row.unavailable_reason}</div>:!selected&&<button onClick={onSelect} disabled={busy}>Select this strategy</button>}
 </article>
}

export function RecoveryOptions({recovery}:{recovery:V2RecoveryCase}){
 const client=useQueryClient(); const [reason,setReason]=useState(""); const [pending,setPending]=useState<V2RecoveryStrategy|null>(null);
 const refresh=()=>{void client.invalidateQueries({queryKey:["recovery"]});void client.invalidateQueries({queryKey:["deviation"]});void client.invalidateQueries({queryKey:["my-work"]})};
 const select=useMutation({mutationFn:(row:V2RecoveryStrategy)=>selectV2RecoveryStrategy(recovery.id,row.id,row.id===recovery.recommended_strategy_id?undefined:reason),onSuccess:()=>{setPending(null);refresh()}});
 const start=useMutation({mutationFn:()=>startV2Recovery(recovery.id),onSuccess:refresh});
 const verify=useMutation({mutationFn:()=>verifyV2Recovery(recovery.id),onSuccess:refresh});
 const sorted=[...recovery.strategies].sort((a,b)=>(a.ranking_position??99)-(b.ranking_position??99));
 return <section className="v2-panel v2-recovery-options"><div className="v2-panel-heading"><div><p>Recovery options</p><h2>Choose how to recover the objective</h2></div><span className={`v2-state ${recovery.status}`}>{recovery.status.replaceAll("_"," ")}</span></div>
  <div className="v2-recovery-strategies">{sorted.map(row=><Strategy key={row.id} row={row} recommended={row.id===recovery.recommended_strategy_id} selected={row.id===recovery.selected_strategy_id} busy={select.isPending} onSelect={()=>{if(row.id===recovery.recommended_strategy_id)select.mutate(row);else setPending(row)}}/>)}</div>
  {pending&&<div className="v2-override-reason"><strong>Why are you choosing an alternative?</strong><p>This is captured as learning—not treated as a failure.</p><textarea value={reason} onChange={event=>setReason(event.target.value)} placeholder="Operational reason for the override"/><button disabled={reason.trim().length<3||select.isPending} onClick={()=>select.mutate(pending)}>Confirm alternative</button><button className="secondary" onClick={()=>setPending(null)}>Cancel</button></div>}
  {recovery.status==="strategy_selected"&&<button onClick={()=>start.mutate()} disabled={start.isPending}><CheckCircle2/> Start coordinated recovery</button>}
  {["executing","monitoring","recovered","partially_recovered"].includes(recovery.status)&&<button onClick={()=>verify.mutate()} disabled={verify.isPending}><CheckCircle2/> Verify from observed plant state</button>}
  {(select.error||start.error||verify.error)&&<p className="v2-form-error">{String((select.error||start.error||verify.error) instanceof Error?(select.error||start.error||verify.error)?.message:"Recovery command failed")}</p>}
 </section>
}
