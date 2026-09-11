"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, ArrowRight, CheckCircle2, Database, FileSpreadsheet, Link2,
  LockKeyhole, Plus, RefreshCw, ShieldCheck, SlidersHorizontal, X,
} from "lucide-react";
import { useMemo, useState } from "react";
import {
  createV2Integration, getV2IntegrationCatalog, getV2Integrations, syncV2Integration,
  testV2Integration, type V2Integration, updateV2IntegrationMapping,
} from "@/lib/api";
import { V2QueryFrame } from "./V2QueryFrame";
import { useV2Formatting } from "./V2Formatting";

const SYNC_DATASETS = [
  { value: "production_plan", label: "Production plan", requires: ["read_production_plan"] },
  { value: "production_actual", label: "Production actual", requires: ["read_production_actual"] },
  { value: "downtime", label: "Downtime", requires: ["read_downtime"] },
  { value: "inventory", label: "Inventory", requires: ["read_inventory"] },
  { value: "supplier_commitments", label: "Supplier commitments", requires: ["read_supplier_commitments"] },
  { value: "quality_events", label: "Quality events", requires: ["read_inspections", "read_quality"] },
  { value: "machine_events", label: "Machine events", requires: ["read_machine_events"] },
  { value: "maintenance_work", label: "Maintenance work", requires: ["read_maintenance_work"] },
  { value: "material_needs", label: "Material needs", requires: ["read_requirements"] },
  { value: "open_purchase_orders", label: "Open purchase orders", requires: ["read_purchase_orders"] },
  { value: "receipts", label: "Receipts", requires: ["read_receipts"] },
] as const;

function ConnectionCard({ item }: { item: V2Integration }) {
  const format = useV2Formatting();
  const client = useQueryClient();
  const syncOptions = useMemo(
    () => SYNC_DATASETS.filter(option => option.requires.every(capability => item.enabled_capabilities.includes(capability))),
    [item.enabled_capabilities],
  );
  const [syncType, setSyncType] = useState<string>(() => syncOptions[0]?.value ?? "");
  const [mappingOpen, setMappingOpen] = useState(false);
  const [mappingDraft, setMappingDraft] = useState(() => JSON.stringify(item.mappings[0]?.mappings ?? {}, null, 2));
  const [mappingError, setMappingError] = useState("");
  const test = useMutation({
    mutationFn: () => testV2Integration(item.id),
    onSuccess: () => client.invalidateQueries({ queryKey: ["v2-integrations"] }),
  });
  const sync = useMutation({
    mutationFn: () => syncV2Integration(item.id, syncType),
    onSuccess: () => client.invalidateQueries({ queryKey: ["v2-integrations"] }),
  });
  const saveMapping = useMutation({
    mutationFn: () => {
      let mappings: Record<string, unknown>;
      try { mappings = JSON.parse(mappingDraft) as Record<string, unknown>; }
      catch { throw new Error("Mapping must be valid JSON"); }
      const current = item.mappings[0];
      return updateV2IntegrationMapping(item.id, {
        name: current?.name ?? "Canonical operations", mappings,
        transforms: current?.transforms ?? {}, ownership: current?.ownership ?? {},
      });
    },
    onSuccess: () => {
      setMappingOpen(false);
      setMappingError("");
      void client.invalidateQueries({ queryKey: ["v2-integrations"] });
    },
    onError: error => setMappingError(error instanceof Error ? error.message : "Mapping could not be saved"),
  });

  return <article className="v2-connector-card">
    <header>
      <div className="v2-connector-icon">{item.provider === "excel_csv" ? <FileSpreadsheet/> : <Database/>}</div>
      <div><span>{item.provider.replaceAll("_", " ")} · adapter {item.provider_version}</span><h2>{item.name}</h2></div>
      <span className={`v2-state ${item.health.state}`}>{item.health.state}</span>
    </header>
    <div className="v2-connector-truth">
      <div><ShieldCheck/><span>Customer verified</span><strong>{item.live_customer_verified ? "Yes" : "Not yet"}</strong></div>
      <div><LockKeyhole/><span>External writes</span><strong>{item.writes_enabled ? "Enabled" : "Disabled"}</strong></div>
      <div><RefreshCw/><span>Last source update</span><strong>{item.health.last_observed_at ? format.dateTime(item.health.last_observed_at) : "Never"}</strong></div>
    </div>
    {["stale", "error", "unknown"].includes(item.health.state) && <div className="v2-source-impact">
      <AlertTriangle/><div><strong>Dependent operational views are degraded</strong><p>Forecast and readiness precision must not be trusted until this source recovers.</p></div>
    </div>}
    <section className="v2-capabilities"><h3>Enabled canonical reads</h3><div>{item.enabled_capabilities.map(value => <span key={value}>{value}</span>)}</div></section>
    <section className="v2-mapping-preview">
      <div><h3>Data mapping</h3><span>{item.mappings[0] ? `Version ${item.mappings[0].version}` : "Not mapped"}</span></div>
      {item.mappings[0] && Object.entries(item.mappings[0].mappings).map(([target, source]) => <div className="v2-map-row" key={target}><span>{String(source)}</span><ArrowRight/><strong>{target.replaceAll("_", " ")}</strong></div>)}
    </section>
    {item.health.last_sync && <section className="v2-sync-receipt">
      <header><h3>Latest reconciliation</h3><span className={`v2-state ${item.health.last_sync.status}`}>{item.health.last_sync.status}</span></header>
      <dl>{Object.entries((item.health.last_sync.summary.counts ?? {}) as Record<string, unknown>).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{String(value)}</dd></div>)}</dl>
      {item.health.last_sync.error && <p>{item.health.last_sync.error}</p>}
    </section>}
    <footer>
      <button onClick={() => test.mutate()} disabled={test.isPending}><Link2/> Test connection</button>
      <button onClick={() => setMappingOpen(true)}><SlidersHorizontal/> Edit mapping</button>
      <label className="v2-sync-picker"><span>Dataset</span><select value={syncType} onChange={event => setSyncType(event.target.value)} disabled={!syncOptions.length}>{syncOptions.length ? syncOptions.map(option => <option value={option.value} key={option.value}>{option.label}</option>) : <option value="">No enabled sync</option>}</select></label>
      <button className="primary" onClick={() => sync.mutate()} disabled={sync.isPending || !syncType}><RefreshCw/> Sync now</button>
    </footer>
    {mappingOpen && <div className="v2-mapping-editor">
      <header><div><small>Versioned mapping</small><h3>{item.name}</h3></div><button onClick={() => setMappingOpen(false)} aria-label="Close mapping editor"><X/></button></header>
      <p>Create a new immutable mapping version. Existing versions remain available for audit and rollback.</p>
      <label>Canonical target to source mapping<textarea value={mappingDraft} onChange={event => setMappingDraft(event.target.value)} spellCheck={false}/></label>
      {mappingError && <span className="v2-form-error">{mappingError}</span>}
      <footer><button onClick={() => setMappingOpen(false)}>Cancel</button><button className="primary" onClick={() => saveMapping.mutate()} disabled={saveMapping.isPending}>Save new version</button></footer>
    </div>}
  </article>;
}

function IntegrationContent() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["v2-integrations"], queryFn: getV2Integrations, refetchInterval: 30_000 });
  const catalog = useQuery({ queryKey: ["v2-integration-catalog"], queryFn: getV2IntegrationCatalog, retry: false });
  const [setupOpen,setSetupOpen]=useState(false);
  const [provider,setProvider]=useState("");
  const [name,setName]=useState("");
  const [secretRef,setSecretRef]=useState("");
  const [enabled,setEnabled]=useState<string[]>([]);
  const selected=catalog.data?.find(row=>row.provider===provider);
  const create=useMutation({mutationFn:()=>createV2Integration({provider,name,mode:"read_only",secret_ref:secretRef||null,enabled_capabilities:enabled}),onSuccess:()=>{setSetupOpen(false);setName("");setSecretRef("");setEnabled([]);void client.invalidateQueries({queryKey:["v2-integrations"]})}});
  const chooseProvider=(value:string)=>{setProvider(value);const item=catalog.data?.find(row=>row.provider===value);setEnabled(item?.tested_capabilities.filter(capability=>capability.startsWith("read_"))??[])};
  return <>
    <div className="v2-page-heading"><div><p>Integrations</p><h1>Plant data connections</h1><span>Source health, freshness, mappings and controlled capabilities without hidden credentials or unverified claims.</span></div>{catalog.data&&<button className="v2-page-action" onClick={()=>setSetupOpen(value=>!value)}><Plus/> Add connection</button>}</div>
    <div className="v2-integration-principle"><CheckCircle2/><div><strong>Read-only by default</strong><p>External writes remain disabled until explicit authority, UAT evidence and deployment controls are satisfied.</p></div></div>
    {setupOpen&&<form className="v2-connector-setup" onSubmit={event=>{event.preventDefault();create.mutate()}}><header><div><span>Governed connector setup</span><h2>Add a read-only plant source</h2></div><button type="button" onClick={()=>setSetupOpen(false)} aria-label="Close connection setup"><X/></button></header><div className="v2-connector-fields"><label>Adapter<select value={provider} onChange={event=>chooseProvider(event.target.value)} required><option value="">Choose tested adapter</option>{catalog.data?.map(item=><option value={item.provider} key={item.provider}>{item.display_name}</option>)}</select></label><label>Connection name<input value={name} onChange={event=>setName(event.target.value)} placeholder="Plant production source" required minLength={2}/></label><label>Secret reference<input value={secretRef} onChange={event=>setSecretRef(event.target.value)} placeholder="vault://plant/source"/><small>Reference only; credentials are never stored here.</small></label></div>{selected&&<section><div><strong>Contract-tested read capabilities</strong><span>{selected.protocols.join(" · ")}</span></div><div className="v2-capability-picker">{selected.tested_capabilities.filter(capability=>capability.startsWith("read_")).map(capability=><label key={capability}><input type="checkbox" checked={enabled.includes(capability)} onChange={event=>setEnabled(current=>event.target.checked?[...current,capability]:current.filter(value=>value!==capability))}/><span>{capability.replaceAll("_"," ")}</span></label>)}</div></section>}<footer>{create.error&&<span className="v2-form-error">{create.error instanceof Error?create.error.message:"Connection could not be created"}</span>}<button disabled={!provider||!name||create.isPending}>Create read-only connection</button></footer></form>}
    {query.isLoading ? <div className="v2-loading-region">Checking connector health…</div> : query.error ? <div className="v2-degraded"><AlertTriangle/><div><strong>Connection health is unavailable.</strong><p>Dependent forecasts and readiness must be treated as degraded until source state can be verified.</p></div><button onClick={()=>query.refetch()}>Retry</button></div> : !query.data?.length ? <div className="v2-empty-compact"><Database/><strong>No plant source is connected</strong><p>Add one contract-tested read-only adapter. Excel can be used as the first governed data path.</p></div> : <div className="v2-connector-grid">{query.data.map(item => <ConnectionCard item={item} key={item.id}/>)}</div>}
  </>;
}

export function IntegrationsV2() { return <V2QueryFrame>{() => <IntegrationContent/>}</V2QueryFrame>; }
