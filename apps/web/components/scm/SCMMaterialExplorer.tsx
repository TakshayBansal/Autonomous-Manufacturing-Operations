"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Boxes, Download, Filter, Search, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { getSCMMaterials } from "@/lib/scm-api";
import { apiUrl } from "@/lib/api";
import { SCMFrame } from "./SCMShell";

export function SCMMaterialExplorer() {
  const [search, setSearch] = useState("");
  const [risk, setRisk] = useState("");
  const query = useQuery({ queryKey: ["scm-materials", search], queryFn: () => getSCMMaterials(search) });
  const sourceRows = query.data ?? [];
  const rows = risk ? sourceRows.filter(row => (row.severity ?? "HEALTHY").toUpperCase() === risk) : sourceRows;
  const critical = rows.filter(row => row.severity?.toLowerCase() === "critical").length;
  const unknown = rows.filter(row => !row.severity || row.severity.toLowerCase() === "unknown").length;
  return <SCMFrame>
    <header className="scm-page-head scm-explorer-head"><div><span className="scm-eyebrow">MATERIAL CONTROL / 210-DAY PROJECTION</span><h1>Materials Explorer</h1><p>Search and inspect persisted material projections without losing planning context.</p></div><div className="scm-explorer-tools"><label><Search/><input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search materials, suppliers, products…"/></label><label className="scm-risk-select"><Filter/><select value={risk} onChange={event => setRisk(event.target.value)}><option value="">All risk states</option><option value="CRITICAL">Critical</option><option value="WATCH">Watch</option><option value="HEALTHY">Healthy</option><option value="EXCESS">Excess</option><option value="UNKNOWN">Unknown</option></select></label><a className="export-link" href={apiUrl("/scm/exports/materials.csv")}><Download/>Export CSV</a></div></header>
    <section className="scm-material-kpis"><article><Boxes/><span><small>Materials monitored</small><strong>{rows.length}</strong></span></article><article className="critical"><AlertTriangle/><span><small>Critical materials</small><strong>{critical}</strong></span></article><article><ShieldCheck/><span><small>Healthy or watch</small><strong>{Math.max(rows.length - critical - unknown, 0)}</strong></span></article><article className="unknown"><AlertTriangle/><span><small>Data requiring review</small><strong>{unknown}</strong></span></article></section>
    {(search || risk) && <div className="scm-filter-chips"><Filter/><span>Search: {search || "Any"}</span><span>Risk: {risk || "All"}</span><button onClick={() => { setSearch(""); setRisk(""); }}>Clear filters</button></div>}
    <section className="scm-table scm-material-table"><div className="scm-table-head readiness"><span>Material</span><span>Category</span><span>Projected stockout</span><span>Risk</span><span>Open</span></div>
      {query.isLoading && <div className="scm-table-loading">Loading canonical material projections…</div>}
      {rows.map(row => <div className="scm-table-row readiness" key={row.id}><div><strong><i className={`material-dot ${(row.severity ?? "healthy").toLowerCase()}`}/>{row.code}</strong><small>{row.description}</small></div><span>{row.type}</span><span className={row.stockout_date ? "danger-text" : ""}>{row.stockout_date ?? "No projected stockout"}</span><span className={`scm-badge ${(row.severity ?? "healthy").toLowerCase()}`}>{row.severity ?? "HEALTHY"}</span><Link href={`/scm/materials/${row.id}`} aria-label={`Open ${row.code}`}>↗</Link></div>)}
      {!query.isLoading && !rows.length && <div className="scm-table-loading">No materials match this view.</div>}
      <footer className="scm-table-footer"><span>Showing {rows.length} materials</span><span>Live canonical planning read model</span></footer>
    </section>
  </SCMFrame>;
}
