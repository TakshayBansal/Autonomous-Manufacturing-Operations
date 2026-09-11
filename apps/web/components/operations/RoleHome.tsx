"use client";

import Link from "next/link";
import { Activity, AlertTriangle, ArrowRight, Database, Factory, Gauge, ShieldCheck, Wrench } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { getV2Context, getV2RoleHome } from "@/lib/api";
import { V2AppShell } from "./V2AppShell";

const titles:Record<string,{title:string;subtitle:string}>={
  plant_manager:{title:"Chakan, in one operational view",subtitle:"Trajectory, losses, decisions and verified recovery."},
  production_manager:{title:"Hold the shift to plan",subtitle:"Line constraints, schedule exposure and supervisor response."},
  supervisor:{title:"Your lines, current shift",subtitle:"Orders, changeovers, staffing and recovery actions in scope."},
  operator:{title:"Run the next good part",subtitle:"Your current line, checks, holds and immediate actions."},
  maintenance:{title:"Restore constrained assets",subtitle:"Active faults, assigned work, spares and repair history."},
  quality:{title:"Protect flow and conformity",subtitle:"Inspection signals, containment and quality recovery."},
  purchase:{title:"Secure production readiness",subtitle:"Material exposure, supplier commitments and approvals."},
  stores:{title:"Stage what production needs",subtitle:"Inventory exceptions, inbound material and critical spares."},
  gate:{title:"Clear today’s arrivals",subtitle:"Expected vehicles, challan checks and pending gate entries."},
  admin:{title:"Keep the operating system healthy",subtitle:"Integration freshness, mappings, ingestion and simulation state."},
  corporate:{title:"Two plants, shared learning",subtitle:"Systemic loss patterns, comparison and practice transfers."},
};

function listFor(home:Awaited<ReturnType<typeof getV2RoleHome>>){
  return home.decisions??home.supervisor_actions??home.recovery_tasks??home.immediate_actions??home.assets??home.material_risks??home.expected_arrivals??home.plants??home.attention;
}

function rowTitle(row:Record<string,unknown>){
  const nested=(row.asset??row.plant??row.work_order) as Record<string,unknown>|undefined;
  return String(row.title??row.decision??nested?.name??nested?.product??row.summary??"Operational item");
}

export function RoleHome(){
  const context=useQuery({queryKey:["v2-context"],queryFn:getV2Context});
  const home=useQuery({queryKey:["v2-role-home"],queryFn:getV2RoleHome,refetchInterval:60_000});
  if(context.isLoading||home.isLoading)return <div className="v2-loading">Loading your shift workspace…</div>;
  if(!context.data||!home.data)return <div className="v2-error"><AlertTriangle/><h1>Home is unavailable</h1><p>Check your workspace session and source health.</p></div>;
  const copy=titles[home.data.kind]??titles.operator;
  const work=listFor(home.data).slice(0,6);
  const pulse=home.data.trajectory;
  return <V2AppShell context={context.data}>
    <main className="v2-role-home">
      <header className="v2-role-hero">
        <div><p>{context.data.plant?.name} · {home.data.role.replaceAll("_"," ")}</p><h1>{copy.title}</h1><span>{copy.subtitle}</span></div>
        <div className="v2-live-marker"><Activity size={16}/>{home.data.simulation?"Live simulation":"Live operations"}</div>
      </header>
      <section className="v2-role-metrics" aria-label="Shift pulse">
        {pulse?<><article><Gauge/><span>Actual now</span><strong>{Math.round(pulse.actual).toLocaleString()}</strong></article><article><Factory/><span>Shift target</span><strong>{Math.round(pulse.target).toLocaleString()}</strong></article><article><Activity/><span>End forecast</span><strong>{Math.round(pulse.forecast).toLocaleString()}</strong></article></>:<>
          <article><ShieldCheck/><span>Attention</span><strong>{home.data.attention.length}</strong></article><article><Wrench/><span>Owned work</span><strong>{work.length}</strong></article><article><Database/><span>Sources observed</span><strong>{home.data.data_health.length}</strong></article>
        </>}
      </section>
      <section className="v2-role-grid">
        <div className="v2-panel"><div className="v2-panel-heading"><div><p>Owned by your role</p><h2>Act next</h2></div><Link href="/v2/my-work">Open My Work <ArrowRight size={15}/></Link></div>
          <div className="v2-role-list">{work.length?work.map((row,index)=><article key={String(row.id??index)}><span>{index+1}</span><div><strong>{rowTitle(row)}</strong><p>{String(row.status??row.priority??row.state??"Ready for review").replaceAll("_"," ")}</p></div></article>):<p className="v2-empty-copy">No immediate work is waiting in your scope.</p>}</div>
        </div>
        <aside className="v2-panel v2-role-attention"><div className="v2-panel-heading"><div><p>Exceptions</p><h2>Watch closely</h2></div></div>
          {home.data.attention.slice(0,4).map((row,index)=><article key={String(row.id??index)}><AlertTriangle size={17}/><div><strong>{rowTitle(row)}</strong><p>{String(row.severity??row.status??"Needs attention")}</p></div></article>)}
          {!home.data.attention.length&&<div className="v2-role-clear"><ShieldCheck/><strong>No critical exceptions</strong><p>Your scoped operation is stable.</p></div>}
        </aside>
      </section>
    </main>
  </V2AppShell>;
}
