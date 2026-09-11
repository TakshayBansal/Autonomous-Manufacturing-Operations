"use client";
import Link from "next/link";
import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Building2, CheckCircle2, CloudUpload, Database, Download, FileSpreadsheet, Network, Settings2, ShieldCheck, Users } from "lucide-react";
import { ProductShell } from "@/components/platform/ProductShell";
import { apiUrl, commitFactoryImport, createWorkspace, listFactoryImports, listWorkspaces, loadFactoryDemo, previewFactoryImport, selectWorkspace } from "@/lib/api";

const areas = [
  { title:"Connections & ingestion",href:"/procurement/integrations",description:"ERP connections, validation and import receipts.",icon:Network,section:"Data" },
  { title:"Supply planning data",href:"/scm/imports",description:"Material, inventory, demand and confirmed supply.",icon:Database,section:"Data" },
  { title:"Production sources",href:"/operations/integrations",description:"Production signals and source configuration.",icon:Settings2,section:"Data" },
  { title:"Canonical governance",href:"/platform",description:"Shared identities, policies and governed actions.",icon:ShieldCheck,section:"Governance" },
  { title:"People and access",href:"/procurement/admin",description:"Users, roles, permissions and reporting structure.",icon:Users,section:"Governance" },
  { title:"Audit evidence",href:"/procurement/audit",description:"Trace changes and inspect governance evidence.",icon:FileSpreadsheet,section:"Governance" },
];

export default function Administration(){
  const client=useQueryClient();
  const imports=useQuery({queryKey:["factory-imports"],queryFn:listFactoryImports,retry:false});
  const workspaces=useQuery({queryKey:["workspaces"],queryFn:listWorkspaces,retry:false});
  const [file,setFile]=useState<File|null>(null);
  const [showCreate,setShowCreate]=useState(false);
  const [form,setForm]=useState({workspace_name:"Unified Automotive Demo",company_name:"GenuineGigs Automotive Components",plant_name:"Plant A",plant_code:"PLANT-A",agent_enabled:true});
  const preview=useMutation({mutationFn:()=>previewFactoryImport(file!),onSuccess:()=>client.invalidateQueries({queryKey:["factory-imports"]})});
  const commit=useMutation({mutationFn:commitFactoryImport,onSuccess:()=>client.invalidateQueries({queryKey:["factory-imports"]})});
  const demo=useMutation({mutationFn:loadFactoryDemo,onSuccess:async()=>{await client.invalidateQueries();}});
  const changeWorkspace=useMutation({mutationFn:selectWorkspace,onSuccess:result=>{localStorage.setItem("gg_csrf",result.csrf_token);window.location.assign("/admin")}});
  const create=useMutation({mutationFn:createWorkspace,onSuccess:async result=>{const selected=await selectWorkspace(result.membership.id);localStorage.setItem("gg_csrf",selected.csrf_token);window.location.assign("/admin")}});
  function submitWorkspace(event:FormEvent){event.preventDefault();create.mutate(form)}
  const navigation=areas.map(item=>({label:item.title,href:item.href,section:item.section,icon:item.icon}));
  return <ProductShell module="platform" title="Administration" navigation={navigation}>
    <main className="gg-home gg-admin-home">
      <header className="gg-home-head"><div><p>WORKSPACE ADMINISTRATION</p><h1>Configure the factory once.</h1></div><span>Manage workspaces, people, policies, connections and governed factory data from one shared control point.</span></header>
      <section className="gg-home-panel gg-workspace-panel"><header><div><h2>Workspaces</h2><p>Each workspace is an isolated company dataset. Module screens read the currently selected workspace.</p></div><button className="gg-button primary" onClick={()=>setShowCreate(value=>!value)}><Building2/>{showCreate?"Cancel":"Create clean workspace"}</button></header>
        <div className="gg-workspace-body">
          {showCreate&&<form className="gg-workspace-form" onSubmit={submitWorkspace}><div><label>Workspace name<input value={form.workspace_name} onChange={e=>setForm({...form,workspace_name:e.target.value})} required/></label><label>Company name<input value={form.company_name} onChange={e=>setForm({...form,company_name:e.target.value})} required/></label><label>First plant<input value={form.plant_name} onChange={e=>setForm({...form,plant_name:e.target.value})} required/></label><label>Plant code<input value={form.plant_code} onChange={e=>setForm({...form,plant_code:e.target.value})} required/></label></div><label className="gg-check"><input type="checkbox" checked={form.agent_enabled} onChange={e=>setForm({...form,agent_enabled:e.target.checked})}/>Enable Gigi for this workspace</label><button className="gg-button primary" disabled={create.isPending}>{create.isPending?"Creating isolated workspace…":"Create and switch"}<ArrowRight/></button>{create.error&&<p className="gg-inline-alert error">{create.error.message}</p>}</form>}
          <div className="gg-workspace-list">{workspaces.isPending?<p className="gg-panel-message">Loading account workspaces…</p>:workspaces.isError?<p className="gg-panel-message">Workspace access is unavailable.</p>:workspaces.data.map(row=><article key={row.membership_id} className={row.selected?"selected":""}><Building2/><div><strong>{row.workspace_name}</strong><span>{row.plant_name} · {row.role.replaceAll("_"," ")} · {row.workspace_kind??"workspace"}</span></div>{row.selected?<b>Current workspace</b>:<button className="gg-button compact" disabled={changeWorkspace.isPending} onClick={()=>changeWorkspace.mutate(row.membership_id)}>Switch</button>}</article>)}</div>
          <p className="gg-workspace-note"><strong>For the connected demonstration:</strong> create or select an empty workspace named “Unified Automotive Demo”, then load the MAT-182 workbook below. Avoid legacy demo workspaces if you want an isolated dataset.</p>
        </div>
      </section>
      <section className="gg-home-panel gg-import-panel"><header><div><h2>Unified factory workbook</h2><p>Preview once, validate across every domain, then commit atomically.</p></div><a className="gg-button secondary" href={apiUrl("/api/v1/platform/factory-imports/template")}><Download/>Download template</a></header><div className="gg-import-body"><form onSubmit={event=>{event.preventDefault();preview.mutate()}}><label className="gg-file-drop"><input type="file" accept=".xlsx" required onChange={event=>setFile(event.target.files?.[0]??null)}/><CloudUpload/><span><strong>{file?.name??"Choose a factory workbook"}</strong><small>{file?"Ready for validation":"XLSX · Procurement, SCM and Operations"}</small></span><b>{file?"Change file":"Browse"}</b></label><div className="gg-import-actions"><button className="gg-button primary" disabled={!file||preview.isPending}>{preview.isPending?"Validating workbook…":"Preview and validate"}<ArrowRight/></button><button className="gg-button secondary" type="button" disabled={demo.isPending} onClick={()=>demo.mutate()}><FileSpreadsheet/>{demo.isPending?"Loading demo…":"Load 20-SKU connected factory"}</button></div></form>{preview.error&&<p className="gg-inline-alert error" role="alert">{preview.error.message}</p>}{demo.data&&<p className="gg-inline-alert success"><CheckCircle2/>{demo.data.case_count} calculated material-risk cases loaded. <Link href={demo.data.case_href}>Open the highest-exposure case</Link></p>}{demo.error&&<p className="gg-inline-alert error" role="alert">{demo.error.message}</p>}<div className="gg-import-history"><header><strong>Import history</strong><span>Current workspace and plant</span></header><div className="gg-attention-list">{imports.isPending?<p className="gg-panel-message">Loading import history…</p>:imports.isError?<p className="gg-panel-message">Import history is unavailable.</p>:!imports.data.length?<p className="gg-panel-message">No unified workbooks have been imported here.</p>:imports.data.map(row=><article key={row.id}><i/><div><strong>{row.filename}</strong><small>{row.version} · {row.summary.row_count??0} rows · {row.status}</small></div>{row.status==="previewed"&&!row.summary.errors?.length?<button className="gg-button compact" disabled={commit.isPending} onClick={()=>commit.mutate(row.id)}>Commit import</button>:<span>{row.status}</span>}</article>)}</div></div></div></section>
      <section className="gg-home-modules gg-data-areas">{areas.map(item=>{const Icon=item.icon;return <Link className="gg-home-module" key={item.href} href={item.href}><Icon/><h2>{item.title}</h2><p>{item.description}</p><span>Open workspace <ArrowRight/></span></Link>})}</section>
    </main>
  </ProductShell>;
}
