"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, ArrowRight, Boxes, CheckCircle2, Database, Factory, GitBranch, ShieldCheck } from "lucide-react";
import { getPlatformActions, getPlatformCases, getPlatformContext, getPlatformMaterials, getPlatformQuality, getPlatformSources, getPlatformWork } from "@/lib/platform-api";
import { ProductShell } from "@/components/platform/ProductShell";

const platformNavigation = [{ label: "Platform overview", href: "/platform", icon: Database, section: "Shared core" }];

export function PlatformConsole(){
  const context=useQuery({queryKey:["platform-context"],queryFn:getPlatformContext,retry:false});
  const materials=useQuery({queryKey:["platform-materials"],queryFn:getPlatformMaterials,enabled:context.isSuccess});
  const actions=useQuery({queryKey:["platform-actions"],queryFn:getPlatformActions,enabled:context.isSuccess});
  const quality=useQuery({queryKey:["platform-quality"],queryFn:getPlatformQuality,enabled:context.isSuccess});
  const cases=useQuery({queryKey:["platform-cases"],queryFn:getPlatformCases,enabled:context.isSuccess});
  const work=useQuery({queryKey:["platform-work"],queryFn:getPlatformWork,enabled:context.isSuccess});
  const sources=useQuery({queryKey:["platform-sources"],queryFn:getPlatformSources,enabled:context.isSuccess});
  if(context.isLoading)return <main className="platform-state"><Activity className="spin"/><h1>Loading shared platform</h1></main>;
  if(context.error)return <main className="platform-state error"><AlertTriangle/><h1>Platform workspace unavailable</h1><p>{context.error.message}</p><Link href="/login">Return to sign in</Link></main>;
  const ctx=context.data!;
  return <ProductShell module="platform" title="Core Platform" navigation={platformNavigation}><main className="platform-page">
    <header className="platform-hero"><div><span>GENUINEGIGS / CORE PLATFORM</span><h1>One operational backbone. Independent modules.</h1><p>Canonical identity, trusted state, governed actions, and traceability shared by Procurement, Operations, and SCM.</p></div><div className="platform-scope"><Factory/><span>Selected scope</span><strong>{ctx.tenant_id}</strong><small>{ctx.plant_id} · {ctx.workspace_kind}</small></div></header>
    <section className="platform-modules"><Link href="/procurement"><Database/><div><strong>Procurement</strong><span>Source-to-receipt workflows</span></div><ArrowRight/></Link><Link href="/operations"><Factory/><div><strong>Operations</strong><span>Plant execution and recovery</span></div><ArrowRight/></Link><Link href="/scm"><Boxes/><div><strong>Supply chain</strong><span>Material readiness and planning</span></div><ArrowRight/></Link></section>
    <section className="platform-contracts">{ctx.contracts.map(contract=><span key={contract}><CheckCircle2/>{contract.replaceAll("_"," ")}</span>)}</section>
    <div className="platform-grid"><section className="platform-panel"><header><div><span>CANONICAL CATALOG</span><h2>Shared materials</h2></div><b>{materials.data?.length??0}</b></header>{materials.data?.length?<div className="platform-list">{materials.data.slice(0,8).map(row=><article key={row.id}><Boxes/><div><strong>{row.code}</strong><span>{row.name}</span></div><small>{row.lifecycle_status}</small></article>)}</div>:<Empty text="No canonical materials have been mapped in this workspace."/>}</section>
    <section className="platform-panel"><header><div><span>TRUST & QUALITY</span><h2>Open data issues</h2></div><b>{quality.data?.filter(row=>row.status==="open").length??0}</b></header>{quality.data?.length?<div className="platform-list">{quality.data.slice(0,8).map(row=><article key={row.id}><AlertTriangle/><div><strong>{row.rule_key}</strong><span>{row.message}</span></div><small>{row.severity}</small></article>)}</div>:<Empty text="No shared-platform quality issues are open." icon="shield"/>}</section></div>
    <section className="platform-panel platform-actions"><header><div><span>GOVERNED EXECUTION</span><h2>Action intent trail</h2></div><small>Proposal → policy → approval → execution → outcome</small></header>{actions.data?.length?<div className="platform-action-grid">{actions.data.map(row=><article key={row.id}><div className="platform-action-title"><GitBranch/><div><strong>{row.action_type.replaceAll("."," / ")}</strong><span>{row.target_type} · {row.target_id}</span></div><b>{row.status.replaceAll("_"," ")}</b></div><p>{row.rationale}</p><footer><span>Policy: {row.policy?.allowed?"allowed":"blocked"}</span><span>Approval: {row.approval?.decision??"—"}</span><span>Execution: {row.execution?.mode??"not run"}</span><span>Outcome: {row.outcome?.verification_status??"pending"}</span></footer></article>)}</div>:<Empty text="No governed actions have been proposed in this workspace."/>}</section>
    <div className="platform-grid platform-lower"><section className="platform-panel"><header><div><span>COORDINATED RESPONSE</span><h2>Cases & work</h2></div><b>{(cases.data?.length??0)+(work.data?.length??0)}</b></header><div className="platform-list">{cases.data?.slice(0,4).map(row=><article key={row.id}><AlertTriangle/><div><strong>{row.title}</strong><span>{row.case_type.replaceAll("_"," ")}</span></div><small>{row.status}</small></article>)}{work.data?.slice(0,4).map(row=><article key={row.id}><CheckCircle2/><div><strong>{row.title}</strong><span>{row.owner_role}</span></div><small>{row.priority}</small></article>)}</div>{!cases.data?.length&&!work.data?.length&&<Empty text="No active cases or assigned work." icon="shield"/>}</section><section className="platform-panel"><header><div><span>INTEGRATION HEALTH</span><h2>Source systems</h2></div><b>{sources.data?.length??0}</b></header>{sources.data?.length?<div className="platform-list">{sources.data.map(row=><article key={row.id}><Database/><div><strong>{row.name}</strong><span>{row.system_type}</span></div><small>{row.status}</small></article>)}</div>:<Empty text="No connector source has completed ingestion in this workspace."/>}</section></div>
  </main></ProductShell>;
}

function Empty({text,icon}:{text:string;icon?:"shield"}){return <div className="platform-empty">{icon?<ShieldCheck/>:<GitBranch/>}<p>{text}</p></div>}
