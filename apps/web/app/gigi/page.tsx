"use client";
import Link from "next/link";

import {useQuery} from "@tanstack/react-query";
import {ArrowRight,BriefcaseBusiness,CheckCircle2,Clock3,MessageSquare,RadioTower,ShieldCheck,Sparkles} from "lucide-react";
import {ProductShell} from "@/components/platform/ProductShell";

import {getGigiBrief,getGigiCommitments,getGigiInsights} from "@/lib/api";

export default function GigiWorkspace(){
 const insights=useQuery({queryKey:["gigi-insights"],queryFn:getGigiInsights,refetchInterval:30000}),brief=useQuery({queryKey:["gigi-brief"],queryFn:getGigiBrief}),commitments=useQuery({queryKey:["gigi-commitments"],queryFn:getGigiCommitments});
 const active=insights.data?.filter(row=>!["ACKNOWLEDGED","DISMISSED","RESOLVED","SNOOZED"].includes(row.delivery_state))??[];
 const acknowledged=insights.data?.filter(row=>row.delivery_state==="ACKNOWLEDGED")??[];
 return <ProductShell module="home" navigation={[]}><main className="gigi-command-workspace">
  <header><div><p>GIGI / ACTIVE COMPANION</p><h1>Already watching. Ready when you need me.</h1><span>Gigi monitors operational change, prepares grounded recovery work, and follows commitments through verified outcomes.</span></div><button onClick={()=>window.dispatchEvent(new CustomEvent("genuinegigs:open-gigi",{detail:{view:"ask"}}))}><MessageSquare/> Ask a follow-up</button></header>
  <section className="gigi-command-status"><RadioTower/><div><small>AMBIENT STATUS</small><strong>{active.length?`${active.length} active signal${active.length===1?"":"s"}`:insights.isError?"Monitoring unavailable":insights.isPending?"Checking operational signals":"No signals returned"}</strong><span>Monitoring continues across cases, decision deadlines, actions and recovery evidence.</span></div><i className={active.some(row=>row.delivery_state==="POPUP")?"urgent":"stable"}/></section>
  <div className="gigi-command-grid"><section><header><Sparkles/><div><small>WHAT I NOTICED</small><h2>Operational attention</h2></div></header>{active.length?active.slice(0,6).map(item=><Link href={item.case_id?`/cases/${item.case_id}`:"/cases"} key={item.id}><i className={item.severity}/><div><strong>{item.title.replace(/^Gigi noticed:\s*/,"")}</strong><span>{item.summary}</span><small>{item.evidence.length} evidence references · {item.delivery_state.toLowerCase()}</small></div><ArrowRight/></Link>):<Empty text={insights.isError?"Could not load attention. Please retry.":insights.isPending?"Loading attention…":"No attention items returned."}/>}</section>
   <section><header><ShieldCheck/><div><small>CURRENT BRIEF</small><h2>{brief.data?.title??"Operational briefing"}</h2></div></header>{brief.data?.items.slice(0,6).map(item=><Link href={item.href.replace("/platform/cases/","/cases/")} key={`${item.kind}-${item.id}`}><i className={item.severity}/><div><strong>{item.title}</strong><small>{item.kind} · evidence linked</small></div><ArrowRight/></Link>)}{!brief.data?.items.length&&<Empty text={brief.isError?"Briefing unavailable.":brief.isPending?"Loading briefing…":"No briefing items returned."}/>}</section>
   <section><header><BriefcaseBusiness/><div><small>FOLLOW-THROUGH</small><h2>Durable commitments</h2></div></header>{commitments.data?.slice(0,6).map(item=><Link href={item.case_id?`/cases/${item.case_id}`:"/operations/my-work"} key={item.id}><Clock3/><div><strong>{item.deliverable}</strong><span>{item.dependency_state??"Operational"}</span><small>Due {new Date(item.due_at).toLocaleString()}</small></div><ArrowRight/></Link>)}{!commitments.data?.length&&<Empty text={commitments.isError?"Commitments unavailable.":commitments.isPending?"Loading commitments…":"No commitments returned."}/>}</section>
   <section><header><CheckCircle2/><div><small>ACKNOWLEDGED · STILL OPEN</small><h2>Current problems</h2></div></header>{acknowledged.length?acknowledged.slice(0,10).map(item=><Link href={item.case_id?`/cases/${item.case_id}`:"/cases"} key={item.id}><i className={item.severity}/><div><strong>{item.title.replace(/^Gigi noticed:\s*/,"")}</strong><span>{item.summary}</span><small>Acknowledged {item.acknowledged_at?new Date(item.acknowledged_at).toLocaleString():""} · remains tracked</small></div><ArrowRight/></Link>):<Empty text="No acknowledged open problems."/>}</section>
  </div>
 </main></ProductShell>;
}
function Empty({text}:{text:string}){return <div className="gigi-command-empty"><ShieldCheck/><span>{text}</span></div>}
