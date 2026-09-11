"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ProductShell } from "@/components/platform/ProductShell";
import { getPlatformHome } from "@/lib/api";

export default function UnifiedHomePage() {
  const home = useQuery({ queryKey: ["platform-home"], queryFn: getPlatformHome, retry: false });
  const data = home.data;
  return <ProductShell module="home" navigation={[]}><main className="gg-home">
    <header className="gg-home-head"><div><p>GENUINEGIGS · COMMAND CENTER</p><h1>Protect production. Coordinate recovery.</h1></div><span>Shared cases connect supply, purchasing and production. Execution is not proof of recovery.</span></header>
    {home.isPending ? <p role="status">Loading operational priorities…</p> : home.isError ? <section role="alert" className="gg-home-panel"><h2>Operational state unavailable</h2><p>We cannot determine whether production is protected. Previously loaded data may be stale.</p><button onClick={() => void home.refetch()}>Retry operational data</button></section> : data && <>
      <section className="gg-home-modules" aria-label="Operational priorities">
        <Link className="gg-home-module procurement" href="/decisions"><h2>Decisions required</h2><strong>{data.decision_count ?? "Unknown"}</strong><p>Review constraints, recommendation and accountable approval.</p></Link>
        <Link className="gg-home-module scm" href="/cases"><h2>Active case priorities</h2><strong>{data.operational_cases?.length ?? "Unknown"}</strong><p>Shown cases ranked by consequence and decision deadline.</p></Link>
        <Link className="gg-home-module operations" href="/cases"><h2>Recovery monitoring</h2><strong>{data.recovery_count ?? "Unknown"}</strong><p>Awaiting fresh evidence across the stability window.</p></Link>
      </section>
      <section className="gg-home-panel"><header><h2>What needs a coordinated response?</h2><Link href="/cases">All cases →</Link></header><div className="gg-attention-list">{data.operational_cases?.length ? data.operational_cases.slice(0, 8).map(item => <article key={item.id}><i className={item.severity}/><div><Link href={`/cases/${item.id}`}><strong>{item.title}</strong></Link><small>{item.responsible_team ?? "Shared response"} · priority {Math.round(item.priority_score)} · {item.recovery_state.replaceAll("_", " ")}</small></div><span>{item.decision_deadline ? `Decide by ${new Date(item.decision_deadline).toLocaleString()}` : "Decision deadline unknown"}</span></article>) : <p>No active cases were returned. This alone does not establish healthy source data.</p>}</div></section>
      <section className="gg-home-grid">
        <section className="gg-home-panel"><header><h2>Reported exposure</h2><span>Per calculation · not additive</span></header>{data.exposure?.length ? data.exposure.map((row, index) => <div className="gg-health-row" key={index}><span>{row.metric.replaceAll("_", " ")}</span><b>{row.delta == null ? "Unknown" : row.delta.toLocaleString()} {row.unit} {row.currency}</b></div>) : <p>No quantified exposure is available. Unknown is not zero.</p>}<p>Overlapping cases may describe the same commitment. Units, money and hours are never combined.</p></section>
        <section className="gg-home-panel"><header><h2>Work requiring follow-through</h2><Link href="/operations/my-work">My Work →</Link></header>{data.attention.length ? data.attention.map(item => <div className="gg-health-row" key={item.id}><span>{item.title}<small> · {item.owner_role?.replaceAll("_", " ")}</small></span><b>{item.due_at ? new Date(item.due_at).toLocaleString() : "No deadline"}</b></div>) : <p>No work items returned for this scope.</p>}</section>
      </section>
      <section className="gg-home-panel"><header><h2>Verified outcomes</h2><Link href="/cases">Review evidence →</Link></header>{data.verified_value?.length ? data.verified_value.map((row, index) => <div className="gg-health-row" key={index}><span>{row.metric.replaceAll("_", " ")}</span><b>{row.value == null ? "Unknown" : row.value.toLocaleString()} {row.unit} {row.currency}</b></div>) : <p>No verified value reported. Completing a task does not establish a protected outcome.</p>}</section>
      <footer><small>Retrieved {new Date(data.generated_at).toLocaleString()} · Source freshness must be checked in case evidence. <Link href="/admin">Administration</Link></small></footer>
    </>}
  </main></ProductShell>;
}
