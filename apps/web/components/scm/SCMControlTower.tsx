"use client";

import Link from "next/link";
import { AlertTriangle, ArrowDown, ArrowRight, Boxes, Clock3, Database, PackageCheck, Play, RefreshCw, ShieldCheck, Truck } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getSCMTower, loadSCMMock, runSCMPlanning, type SCMTower } from "@/lib/scm-api";
import { SCMFrame } from "./SCMShell";

const fmt = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const pretty = (value: string) => value.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());

function Kpis({ data }: { data: SCMTower }) {
  const cards = [
    ["Materials monitored", data.kpis.materials, Boxes, "green", "Canonical material scope"],
    ["Critical materials", data.kpis.critical, AlertTriangle, "red", "Production exposure"],
    ["Shortages ≤ 30 days", data.kpis.shortages_30_days, Clock3, "amber", "Requires planner review"],
    ["Pull-in candidates", data.kpis.pull_in, ArrowDown, "blue", "Movable confirmed supply"],
    ["Excess candidates", data.kpis.excess, PackageCheck, "violet", "Defer or reduce supply"],
  ] as const;
  return <section className="scm-kpi-strip">{cards.map(([label, value, Icon, tone, note]) => <article key={label} className={tone}><span className="scm-kpi-icon"><Icon/></span><div><small>{label}</small><strong>{fmt.format(value)}</strong><em>{note}</em></div><i className="scm-spark"><b/><b/><b/><b/><b/></i></article>)}</section>;
}

function RiskTable({ data }: { data: SCMTower }) {
  return <section className="scm-dashboard-panel scm-critical-panel"><header><div><h2>Critical risks</h2><p>Highest-priority material exposures in the active plan.</p></div><Link href="/scm/exceptions">View all <ArrowRight/></Link></header>
    {!data.risks.length ? <div className="scm-empty"><ShieldCheck/><h3>No planning results yet</h3><p>Load mock ERP data, then run planning.</p></div> : <div className="scm-critical-table"><div className="head"><span>Material</span><span>Severity</span><span>Stockout date</span><span>Exposure</span><span>Recommended action</span></div>
      {data.risks.slice(0, 6).map(risk => <Link href={`/scm/materials/${risk.material.id}`} key={risk.id}><span><strong>{risk.material.code}</strong><small>{risk.material.description}</small></span><span className={`scm-badge ${risk.severity.toLowerCase()}`}>{risk.severity}</span><span><strong>{risk.stockout_date ?? "Unknown"}</strong><small>{risk.first_breach_date ? `Breach ${risk.first_breach_date}` : "Timing unavailable"}</small></span><span><strong>{risk.affected_finished_goods_count} products</strong><small>{fmt.format(risk.shortage_qty)} units short</small></span><span className="scm-action-cell"><strong>{risk.recommendations[0] ? pretty(risk.recommendations[0].action_type) : "Review supply"}</strong><small>{risk.supplier?.name ?? "No supplier mapped"}</small></span></Link>)}
    </div>}
  </section>;
}

function HealthMap({ data }: { data: SCMTower }) {
  return <section className="scm-dashboard-panel scm-health-panel"><header><div><h2>Supply risk evidence</h2><p>Counts from the persisted planning result. Categories may overlap.</p></div><Link href="/scm/horizon">210-day projections <ArrowRight/></Link></header><div className="scm-action-summary"><p><AlertTriangle/><span>Critical materials</span><b>{fmt.format(data.kpis.critical)}</b></p><p><Clock3/><span>Shortages within 30 days</span><b>{fmt.format(data.kpis.shortages_30_days)}</b></p><p><Boxes/><span>Materials monitored</span><b>{fmt.format(data.kpis.materials)}</b></p></div><footer>Open Supply Horizon for dated projections and their source evidence.</footer></section>;
}

function Tower() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["scm-tower"], queryFn: getSCMTower, refetchInterval: 15000 });
  const refresh = () => client.invalidateQueries({ queryKey: ["scm-tower"] });
  const mock = useMutation({ mutationFn: loadSCMMock, onSuccess: refresh });
  const run = useMutation({ mutationFn: runSCMPlanning, onSuccess: () => setTimeout(refresh, 300) });
  if (query.isLoading) return <div className="scm-state"><RefreshCw className="spin"/><h2>Loading time-phased material risk</h2></div>;
  if (query.error) return <div className="scm-state error"><AlertTriangle/><h2>Planning results are unavailable</h2><p>{query.error.message}</p><button onClick={() => query.refetch()}>Retry</button></div>;
  const data = query.data!;
  return <><header className="scm-page-head"><div><span className="scm-eyebrow">NETWORK CONTROL / ACTIVE PLAN</span><h1>What becomes a problem next?</h1><p>Projected inventory, downstream exposure, and the actions worth reviewing across the planning horizon.</p></div><div className="scm-head-actions">{!data.latest_run && <button className="secondary" onClick={() => mock.mutate()} disabled={mock.isPending}><Database/>Load mock ERP</button>}<button onClick={() => run.mutate()} disabled={run.isPending}><Play/>{run.isPending ? "Starting planning…" : "Run planning"}</button></div></header>
    {data.sources.some(row => row.stale) && <div className="scm-banner"><AlertTriangle/><div><strong>Source data is stale</strong><span>Green status is suppressed where planning inputs cannot be trusted.</span></div><Link href="/scm/imports">View data quality <ArrowRight/></Link></div>}
    <Kpis data={data}/><div className="scm-dashboard-grid"><HealthMap data={data}/><RiskTable data={data}/></div>
    <div className="scm-dashboard-bottom"><section className="scm-dashboard-panel"><header><div><h2>Actions required</h2><p>Interventions grouped for planner review.</p></div><Link href="/scm/actions">View all <ArrowRight/></Link></header><div className="scm-action-summary"><p><ArrowDown/><span><strong>Pull in supply</strong><small>Bring confirmed receipts forward</small></span><b>{data.kpis.pull_in}</b></p><p><Truck/><span><strong>Supplier follow-up</strong><small>Resolve confirmation and delay risk</small></span><b>{data.kpis.shortages_30_days}</b></p><p><PackageCheck/><span><strong>Reduce excess</strong><small>Push out or resize open supply</small></span><b>{data.kpis.excess}</b></p></div></section>
      <section className="scm-dashboard-panel scm-readiness-card"><header><div><h2>Production readiness</h2><p>Requires pegged component coverage, not a material-count percentage.</p></div><Link href="/scm/readiness">Inspect readiness <ArrowRight/></Link></header><div className="scm-plan-status"><Boxes/><strong>Review production requirements</strong><span>A non-critical material is not proof that an order is ready. Inspect required quantities, dates and blocking components.</span></div></section>
      <section className="scm-dashboard-panel"><header><div><h2>Planning status</h2><p>Latest deterministic calculation.</p></div></header><div className="scm-plan-status">{data.latest_run ? <><ShieldCheck/><strong>Plan completed</strong><span>{data.latest_run.materials_processed} materials processed</span><span>{data.latest_run.exceptions_generated} exceptions generated</span><small>Engine {data.latest_run.engine_version} · Policy v{data.latest_run.policy_version}</small></> : <><Clock3/><strong>Waiting for first run</strong><span>Load source data to begin.</span></>}</div></section></div>
  </>;
}

export function SCMControlTower() { return <SCMFrame><Tower/></SCMFrame>; }
