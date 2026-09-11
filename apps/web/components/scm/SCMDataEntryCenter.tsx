"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CheckCircle2, ClipboardList, Plus, RefreshCw, ShieldCheck, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { FormEvent, useMemo, useState } from "react";
import { createSCMDataEntry, getSCMDataConflicts, getSCMDataEntries, getSCMDataEntryOptions, resolveSCMDataConflict, voidSCMDataEntry } from "@/lib/scm-api";
import { SCMFrame } from "./SCMShell";

const labels:Record<string,string>={EXPECTED_DELIVERY_CREATED:"New expected delivery",SUPPLY_SCHEDULE_CHANGED:"Change delivery date",SUPPLY_QUANTITY_CHANGED:"Change delivery quantity",GOODS_RECEIPT_RECORDED:"Record goods receipt",INVENTORY_CORRECTION_RECORDED:"Correct inventory",DEMAND_CREATED:"Add demand",DEMAND_CHANGED:"Change demand"};
const today=()=>new Date().toISOString().slice(0,10);

export function SCMDataEntryCenter(){
  const params=useSearchParams(), client=useQueryClient();
  const options=useQuery({queryKey:["scm-data-options"],queryFn:getSCMDataEntryOptions});
  const entries=useQuery({queryKey:["scm-data-entries"],queryFn:getSCMDataEntries,refetchInterval:5000});
  const conflicts=useQuery({queryKey:["scm-data-conflicts"],queryFn:getSCMDataConflicts});
  const [open,setOpen]=useState(params.get("new")==="1");
  const [type,setType]=useState(params.get("type")??"EXPECTED_DELIVERY_CREATED");
  const [material,setMaterial]=useState(params.get("material_id")??"");
  const [supplier,setSupplier]=useState(""); const [schedule,setSchedule]=useState("");
  const [demand,setDemand]=useState("");
  const [quantity,setQuantity]=useState(""); const [entryDate,setEntryDate]=useState(today());
  const [reason,setReason]=useState(""); const [message,setMessage]=useState("");
  const selectedMaterial=options.data?.materials.find(row=>row.id===material);
  const filteredSchedules=useMemo(()=>options.data?.schedules.filter(row=>!material||row.material_id===material)??[],[options.data,material]);
  const filteredDemands=useMemo(()=>options.data?.demands.filter(row=>!material||row.material_id===material)??[],[options.data,material]);
  const mutation=useMutation({mutationFn:createSCMDataEntry,onSuccess:async result=>{setMessage(`Saved. Planning run ${result.planning_run?.id?.slice(0,8)??"queued"} started automatically.`);setOpen(false);setQuantity("");setReason("");await client.invalidateQueries({queryKey:["scm-data-entries"]});},onError:error=>setMessage(error instanceof Error?error.message:"Unable to save")});
  function submit(event:FormEvent){event.preventDefault();const values:Record<string,unknown>={uom:selectedMaterial?.uom};let target_entity_type:string|undefined,target_entity_id:string|undefined;
    if(type==="EXPECTED_DELIVERY_CREATED")Object.assign(values,{quantity,delivery_date:entryDate});
    if(type==="GOODS_RECEIPT_RECORDED")Object.assign(values,{quantity,receipt_date:entryDate});
    if(type==="DEMAND_CREATED")Object.assign(values,{quantity,required_date:entryDate,demand_reference:`MANUAL-${Date.now()}`});
    if(type==="INVENTORY_CORRECTION_RECORDED")Object.assign(values,{available_qty:quantity,on_hand_qty:quantity});
    if(type==="SUPPLY_SCHEDULE_CHANGED"||type==="SUPPLY_QUANTITY_CHANGED"){target_entity_type="scm_supply_schedule_line";target_entity_id=schedule;if(type==="SUPPLY_SCHEDULE_CHANGED")values.delivery_date=entryDate;else values.quantity=quantity;}
    if(type==="DEMAND_CHANGED"){target_entity_type="scm_material_requirement";target_entity_id=demand;Object.assign(values,{quantity,required_date:entryDate});}
    mutation.mutate({entry_type:type,material_id:material,supplier_id:supplier||null,target_entity_type,target_entity_id,values,reason,evidence:[]});
  }
  async function refresh(){await Promise.all([client.invalidateQueries({queryKey:["scm-data-entries"]}),client.invalidateQueries({queryKey:["scm-data-conflicts"]})])}
  return <SCMFrame><div className="scm-data-center">
    <header className="scm-page-head"><div><span className="scm-eyebrow">PLANNING INPUT CONTROL</span><h1>Update supply-chain data without returning to Excel.</h1><p>Record an operational fact, preserve its audit trail, and automatically rebuild the supply plan.</p></div><button onClick={()=>setOpen(true)}><Plus/>Add data</button></header>
    {message&&<div className={`data-entry-message ${message.startsWith("Saved")?"success":""}`}><CheckCircle2/>{message}<button onClick={()=>setMessage("")}><X/></button></div>}
    <section className="data-entry-flow"><article><ClipboardList/><strong>1. Record a change</strong><small>Delivery, receipt, stock or demand</small></article><ArrowRight/><article><ShieldCheck/><strong>2. Validate & audit</strong><small>Identity, UOM and authority checks</small></article><ArrowRight/><article><RefreshCw/><strong>3. Replan automatically</strong><small>Horizon and risks refresh</small></article></section>
    <div className="data-entry-grid"><section className="scm-dashboard-panel"><header><div><h2>Recent planning inputs</h2><p>Manual values remain authoritative until reconciled or voided.</p></div><button className="secondary" onClick={refresh}><RefreshCw/>Refresh</button></header><div className="data-entry-ledger">{entries.isLoading&&<p>Loading entries…</p>}{entries.data?.map(row=><article key={row.id}><i className={row.status.toLowerCase()}/><div><strong>{labels[row.entry_type]??row.entry_type}</strong><span>{row.material.code} · {row.reason}</span><small>{new Date(row.created_at).toLocaleString()} · {row.correlation_id}</small></div><div><b>{row.status}</b><small>Plan: {row.planning_status??"queued"}</small>{row.status==="ACTIVE"&&<button onClick={()=>voidSCMDataEntry(row.id,"Planner voided superseded information").then(refresh)}>Void</button>}</div></article>)}{!entries.isLoading&&!entries.data?.length&&<p>No manual planning inputs yet.</p>}</div></section>
      <section className="scm-dashboard-panel"><header><div><h2>Source conflicts</h2><p>Excel imports never silently overwrite an active manual value.</p></div><b className="conflict-count">{conflicts.data?.length??0}</b></header><div className="conflict-list">{conflicts.data?.map(row=><article key={row.id}><AlertTriangle/><div><strong>{row.message}</strong><small>Review imported and manual values before choosing authority.</small><span><button onClick={()=>resolveSCMDataConflict(row.id,"KEEP_MANUAL","Manual operational observation remains authoritative").then(refresh)}>Keep manual</button><button className="secondary" onClick={()=>resolveSCMDataConflict(row.id,"ACCEPT_IMPORTED","Imported source has been verified as authoritative").then(refresh)}>Accept import</button></span></div></article>)}{!conflicts.isLoading&&!conflicts.data?.length&&<div className="empty-conflicts"><CheckCircle2/><strong>No unresolved conflicts</strong><small>Imported and manual sources are aligned.</small></div>}</div></section></div>
    {open&&<div className="data-entry-overlay" onMouseDown={event=>{if(event.target===event.currentTarget)setOpen(false)}}><form className="data-entry-form" onSubmit={submit}><header><div><span className="scm-eyebrow">GOVERNED MANUAL INPUT</span><h2>Add planning data</h2><p>This saves immediately and starts a new immutable planning run.</p></div><button type="button" onClick={()=>setOpen(false)}><X/></button></header><label>What changed?<select value={type} onChange={e=>setType(e.target.value)}>{Object.entries(labels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><label>Material<select required value={material} onChange={e=>{setMaterial(e.target.value);setSchedule("");setDemand("")}}><option value="">Select material</option>{options.data?.materials.map(row=><option key={row.id} value={row.id}>{row.code} — {row.description}</option>)}</select></label>
      {(type==="EXPECTED_DELIVERY_CREATED"||type==="GOODS_RECEIPT_RECORDED")&&<label>Supplier (optional)<select value={supplier} onChange={e=>setSupplier(e.target.value)}><option value="">Not specified</option>{options.data?.suppliers.map(row=><option key={row.id} value={row.id}>{row.code} — {row.name}</option>)}</select></label>}
      {(type==="SUPPLY_SCHEDULE_CHANGED"||type==="SUPPLY_QUANTITY_CHANGED")&&<label>Purchase-order schedule<select required value={schedule} onChange={e=>setSchedule(e.target.value)}><option value="">Select open schedule</option>{filteredSchedules.map(row=><option key={row.id} value={row.id}>{row.order_number} · {row.quantity} due {row.due_date}</option>)}</select></label>}
      {type==="DEMAND_CHANGED"&&<label>Demand record<select required value={demand} onChange={e=>setDemand(e.target.value)}><option value="">Select existing demand</option>{filteredDemands.map(row=><option key={row.id} value={row.id}>{row.reference} · {row.quantity} due {row.required_date}</option>)}</select></label>}
      {type!=="SUPPLY_SCHEDULE_CHANGED"&&<label>Quantity ({selectedMaterial?.uom??"UOM"})<input required min="0.0001" step="any" type="number" value={quantity} onChange={e=>setQuantity(e.target.value)}/></label>}
      {type!=="INVENTORY_CORRECTION_RECORDED"&&type!=="SUPPLY_QUANTITY_CHANGED"&&<label>{type==="GOODS_RECEIPT_RECORDED"?"Receipt date":type==="DEMAND_CREATED"?"Required date":"Expected delivery date"}<input required type="date" value={entryDate} onChange={e=>setEntryDate(e.target.value)}/></label>}
      <label>Reason<textarea required minLength={3} value={reason} onChange={e=>setReason(e.target.value)} placeholder="What changed, and how was it confirmed?"/></label><aside><AlertTriangle/><span><strong>Manual precedence</strong><small>This value overrides overlapping imported planning data until it is reconciled or voided.</small></span></aside><footer><button type="button" className="secondary" onClick={()=>setOpen(false)}>Cancel</button><button disabled={mutation.isPending}>{mutation.isPending?<RefreshCw className="spin"/>:<Plus/>}{mutation.isPending?"Saving & replanning…":"Save & replan"}</button></footer></form></div>}
  </div></SCMFrame>
}
