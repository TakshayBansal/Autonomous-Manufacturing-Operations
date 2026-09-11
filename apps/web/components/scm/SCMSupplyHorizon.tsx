"use client";

import Link from "next/link";
import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import { AlertTriangle, ArrowRight, CalendarDays, Check, CircleDollarSign, Filter, Focus, Maximize2, PackageCheck, RefreshCw, ShieldCheck, SlidersHorizontal, TrendingUp, Truck, X, Zap } from "lucide-react";
import { createSCMAction, getSCMHorizon, type SCMHorizon, type SCMHorizonEvent, type SCMHorizonRow, type SCMHorizonSegment } from "@/lib/scm-api";
import { SCMFrame } from "./SCMShell";

const DAY = 86_400_000;
const MATERIAL_COLUMN_WIDTH = 220;
const SCALE_GUTTER_PERCENT = 3;
const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const parseDate = (date: string) => new Date(`${date.slice(0, 10)}T00:00:00Z`);
const dateLabel = (date: string, year = false) => new Intl.DateTimeFormat("en-US", { month: "short", day: "2-digit", ...(year ? { year: "numeric" } : {}) }).format(parseDate(date));
const isoDate = (date: Date) => date.toISOString().slice(0, 10);
const addDays = (date: string, days: number) => isoDate(new Date(parseDate(date).getTime() + days * DAY));
const dayDiff = (start: string, end: string) => Math.round((parseDate(end).getTime() - parseDate(start).getTime()) / DAY);

/** The shared proportional scale for every item drawn on the horizon. */
function dateToX(date: string, horizonStart: string, horizonEnd: string) {
  const ratio = Math.max(0, Math.min(1, dayDiff(horizonStart, date) / Math.max(1, dayDiff(horizonStart, horizonEnd))));
  return SCALE_GUTTER_PERCENT + ratio * (100 - SCALE_GUTTER_PERCENT * 2);
}

function buildAxis(start: string, end: string, days: number) {
  const startDate = parseDate(start), endDate = parseDate(end);
  const months: Array<{ label: string; start: number; end: number }> = [];
  let cursor = new Date(Date.UTC(startDate.getUTCFullYear(), startDate.getUTCMonth(), 1));
  while (cursor <= endDate) {
    const next = new Date(Date.UTC(cursor.getUTCFullYear(), cursor.getUTCMonth() + 1, 1));
    months.push({ label: cursor.toLocaleDateString("en-US", { month: "short", year: "2-digit", timeZone: "UTC" }), start: dateToX(isoDate(cursor < startDate ? startDate : cursor), start, end), end: dateToX(isoDate(next > endDate ? endDate : next), start, end) });
    cursor = next;
  }
  const step = days <= 30 ? 5 : days <= 90 ? 10 : days <= 210 ? 15 : 30;
  const ticks = [] as Array<{ date: string; x: number; label: string }>;
  for (let index = 0; index <= days; index += step) { const date = addDays(start, index); ticks.push({ date, x: dateToX(date, start, end), label: `${parseDate(date).getUTCDate()}` }); }
  return { months, ticks };
}

const severityRank = (state: string) => ({ CRITICAL: 0, WATCH: 1, EXCESS: 2, HEALTHY: 3, UNKNOWN: 4 }[state] ?? 5);

function Segment({ segment, start, end }: { segment: SCMHorizonSegment; start: string; end: string }) {
  const left = dateToX(segment.start_date, start, end), right = dateToX(addDays(segment.end_date, 1), start, end);
  return <span className={`sh-band sh-${segment.state.toLowerCase()}`} style={{ left: `${left}%`, width: `${Math.max(.25, right - left)}%` }} tabIndex={0} aria-label={`${segment.state}, ${dateLabel(segment.start_date)} to ${dateLabel(segment.end_date)}`}>
    {segment.state === "CRITICAL" && <b>!</b>}
    <span className="sh-tooltip"><strong>{dateLabel(segment.start_date)} — {dateLabel(segment.end_date, true)}</strong><em>{segment.state.replace("_", " ")}</em><dl><div><dt>Opening inventory</dt><dd>{number.format(segment.opening)}</dd></div><div><dt>Demand</dt><dd>{number.format(segment.demand)}</dd></div><div><dt>Receipts</dt><dd>{number.format(segment.receipts)}</dd></div><div><dt>Projected closing</dt><dd>{number.format(segment.closing)}</dd></div><div><dt>Safety stock</dt><dd>{number.format(segment.safety_stock)}</dd></div>{segment.maximum_shortage > 0 && <div><dt>Maximum shortage</dt><dd>{number.format(segment.maximum_shortage)}</dd></div>}</dl></span>
  </span>;
}

function EventMarker({ event, start, end }: { event: SCMHorizonEvent; start: string; end: string }) {
  return <span className={`sh-event sh-event-${event.type.toLowerCase()}`} style={{ left: `${dateToX(event.date, start, end)}%` }} tabIndex={0} aria-label={`${event.label ?? event.type} on ${dateLabel(event.date)}`}>
    {event.type === "PO_RECEIPT" ? <><Truck/><b>{event.quantity ? number.format(event.quantity) : ""}</b></> : event.type === "CANCELLATION_DEADLINE" ? <b>C</b> : event.type === "FORECAST_CHANGE" ? <TrendingUp/> : <Zap/>}
    <span className="sh-tooltip"><strong>{event.label ?? event.type.replaceAll("_", " ")}</strong><em>{dateLabel(event.date, true)}</em>{event.entity_id && <span>{event.entity_id}</span>}{event.supplier && <span>Supplier: {event.supplier}</span>}{event.quantity !== undefined && <span>Quantity: {number.format(event.quantity)}</span>}{event.original_date && <span>Original arrival: {dateLabel(event.original_date)}</span>}{event.status && <span>Status: {event.status}</span>}</span>
  </span>;
}

function TimelineAxis({ start, end, days, width }: { start: string; end: string; days: number; width: number }) {
  const axis = useMemo(() => buildAxis(start, end, days), [start, end, days]);
  return <div className="sh-axis" style={{ width }}><div className="sh-months">{axis.months.map(month => <span key={`${month.label}-${month.start}`} style={{ left: `${month.start}%`, width: `${month.end - month.start}%` }}>{month.end - month.start >= 4.5 ? month.label : ""}</span>)}</div><div className="sh-ticks">{axis.ticks.map(tick => <span key={tick.date} style={{ left: `${tick.x}%` }}>{tick.label}</span>)}</div></div>;
}

function HorizonWorkspace({ data, selected, onSelect }: { data: SCMHorizon; selected: string; onSelect: (id: string) => void }) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [fitToView, setFitToView] = useState(true);
  const [viewportWidth, setViewportWidth] = useState(1000);
  const rows = useMemo(() => [...data.rows].sort((a, b) => severityRank(a.status) - severityRank(b.status) || a.material.code.localeCompare(b.material.code)), [data.rows]);
  const virtualizer = useVirtualizer({ count: rows.length, getScrollElement: () => scrollRef.current, estimateSize: () => 64, overscan: 12 });
  const start = data.horizon_start ?? data.run?.horizon_start ?? isoDate(new Date());
  const end = data.horizon_end ?? data.run?.horizon_end ?? addDays(start, data.days);
  useLayoutEffect(() => {
    const viewport = scrollRef.current;
    if (!viewport) return;
    const update = () => setViewportWidth(viewport.clientWidth);
    update();
    const observer = new ResizeObserver(update);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);
  const expandedWidth = data.days <= 30 ? 780 : data.days <= 90 ? 1080 : data.days <= 210 ? 1540 : 2380;
  const timelineWidth = fitToView ? Math.max(680, viewportWidth - MATERIAL_COLUMN_WIDTH) : expandedWidth;
  const axis = useMemo(() => buildAxis(start, end, data.days), [start, end, data.days]);
  const today = isoDate(new Date()), todayX = dateToX(today, start, end), showToday = today >= start && today <= end;
  return <section className="sh-workspace">
    <header><div><h2>{data.days}-day supply horizon / risk map</h2><p>Coverage, shortages, receipts, deadlines and planned interventions.</p></div><div><span>{rows.length} materials</span><button type="button" className={fitToView ? "active" : ""} onClick={() => setFitToView(true)}><Focus/>Fit to view</button><button type="button" className={!fitToView ? "active" : ""} onClick={() => setFitToView(false)} aria-label="Use detailed timeline scale" title="Use detailed timeline scale"><Maximize2/></button></div></header>
    <div className="sh-scroll" ref={scrollRef}><div className="sh-canvas" style={{ width: MATERIAL_COLUMN_WIDTH + timelineWidth, height: virtualizer.getTotalSize() + 62 }}>
      <div className="sh-sticky-axis"><div className="sh-material-head">Material</div><TimelineAxis start={start} end={end} days={data.days} width={timelineWidth}/></div>
      <div className="sh-rows" style={{ height: virtualizer.getTotalSize(), top: 62 }}>
        {virtualizer.getVirtualItems().map(item => { const row = rows[item.index]; return <div key={row.material.id} role="button" tabIndex={0} aria-pressed={selected === row.material.id} className={`sh-row ${selected === row.material.id ? "selected" : ""}`} style={{ height: item.size, transform: `translateY(${item.start}px)`, width: MATERIAL_COLUMN_WIDTH + timelineWidth }} onClick={() => onSelect(row.material.id)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(row.material.id); } }}>
          <span className="sh-material"><strong>{row.material.code}</strong><small>{row.material.description}</small>{row.supplier && <em>{row.supplier.name}</em>}</span>
          <span className="sh-track" style={{ width: timelineWidth }}><span className="sh-past" style={{ width: `${showToday ? todayX : today > end ? 100 : 0}%` }}/>{axis.months.slice(1).map(month => <i className="sh-month-line" key={`${month.label}-${month.start}`} style={{ left: `${month.start}%` }}/>)}{row.segments.map(segment => <Segment key={`${segment.start_date}-${segment.state}`} segment={segment} start={start} end={end}/>)}{row.events.map((event, index) => <EventMarker key={`${event.type}-${event.date}-${event.entity_id ?? index}`} event={event} start={start} end={end}/>)}{showToday && <i className="sh-today-line" style={{ left: `${todayX}%` }}/>}</span>
        </div>; })}
        {showToday && <span className="sh-today-label" style={{ left: MATERIAL_COLUMN_WIDTH + timelineWidth * todayX / 100 }}>Today</span>}
      </div>
    </div></div>
    <footer><span><i className="healthy"/>Healthy</span><span><i className="watch"/>Watch</span><span><i className="critical"/>Critical shortage</span><span><i className="excess"/>Excess</span><span><i className="unknown"/>Unknown</span><span><Truck/>Receipt</span><span><Zap/>Intervention</span><span><b>C</b>Cancellation deadline</span></footer>
  </section>;
}

function Inspector({ row, close }: { row?: SCMHorizonRow; close: () => void }) {
  const [creating, setCreating] = useState(false), [result, setResult] = useState("");
  if (!row) return <aside className="sh-drawer empty"><PackageCheck/><strong>Select a material</strong><span>Inspect its coverage and intervention options.</span></aside>;
  const createAction = async () => { if (!row.recommendation) return; setCreating(true); try { const response = await createSCMAction(row.recommendation.id); setResult(`Action ${response.status.toLowerCase()}`); } catch (error) { setResult(error instanceof Error ? error.message : "Action creation failed"); } finally { setCreating(false); } };
  return <aside className="sh-drawer"><header><span>Selected material</span><button onClick={close} aria-label="Close inspector"><X/></button></header><div className="sh-drawer-title"><i className={row.status.toLowerCase()}><PackageCheck/></i><span><strong>{row.material.code}</strong><small>{row.material.description}</small></span>{row.case_id&&<Link href={`/cases/${row.case_id}`}>Open case</Link>}<b className={row.status.toLowerCase()}>{row.status}</b></div>
    <section><header><strong>Coverage outlook</strong><Link href={`/scm/materials/${row.material.id}`}>View full profile</Link></header><div className="sh-stats"><span><small>On hand</small><strong>{number.format(row.coverage.on_hand)}</strong></span><span><small>On order</small><strong>{number.format(row.coverage.on_order)}</strong></span><span><small>Safety stock</small><strong>{number.format(row.coverage.safety_stock)}</strong></span><span><small>Runway</small><strong>{row.coverage.runway_days == null ? "—" : `${Math.round(row.coverage.runway_days)}d`}</strong></span><span><small>Projected run-out</small><strong className="danger-text">{row.coverage.projected_runout ? dateLabel(row.coverage.projected_runout) : "None"}</strong></span></div></section>
    <section><header><strong>Shortage windows</strong><span>{row.risk_windows.length}</span></header><div className="sh-window-list">{row.risk_windows.length ? row.risk_windows.slice(0, 4).map(window => <p key={`${window.start_date}-${window.end_date}`}><span><strong>{dateLabel(window.start_date)} — {dateLabel(window.end_date)}</strong><small>{dayDiff(window.start_date, window.end_date) + 1} days · max gap {number.format(window.maximum_shortage)}</small></span><b className={window.severity.toLowerCase()}>{window.severity}</b></p>) : <p className="safe"><ShieldCheck/><span><strong>No critical shortage</strong><small>Coverage remains above zero.</small></span></p>}</div></section>
    <section><header><strong>Affected</strong><span>{row.affected.length}</span></header><div className="sh-affected">{row.affected.slice(0, 5).map(item => <p key={`${item.entity_type}-${item.entity_id}`}><span><strong>{item.label ?? item.entity_id}</strong><small>{item.entity_type.replaceAll("_", " ")}</small></span></p>)}{!row.affected.length && <p><span><strong>Impact mapping unavailable</strong><small>No downstream mapping was returned; impact is unknown.</small></span></p>}</div></section>
    <section className="sh-recommendation"><header><strong>Recommended</strong></header><div><AlertTriangle/><span><strong>{row.recommendation?.action_type.replaceAll("_", " ") ?? "MONITOR COVERAGE"}</strong><small>{row.recommendation?.reason ?? "Review time-phased coverage before committing an external change."}</small></span></div>{result && <p>{result}</p>}<div className="sh-actions">{row.recommendation && <button disabled={creating} onClick={createAction}>{creating ? "Creating…" : "Create action"}<ArrowRight/></button>}<Link href={`/scm/materials/${row.material.id}`}>Material 360</Link></div></section>
  </aside>;
}

function HorizonPage() {
  const [days, setDays] = useState(210), [risk, setRisk] = useState(""), [selected, setSelected] = useState(""), [filtersOpen, setFiltersOpen] = useState(false), [supplier, setSupplier] = useState(""), [action, setAction] = useState("");
  const query = useQuery({ queryKey: ["scm-horizon", days, risk], queryFn: () => getSCMHorizon(days, risk) });
  const filtered = useMemo(() => query.data ? { ...query.data, rows: query.data.rows.filter(row => (!supplier || row.supplier?.name === supplier) && (!action || row.recommendation?.action_type === action)) } : undefined, [query.data, supplier, action]);
  if (query.isLoading) return <div className="scm-state"><RefreshCw className="spin"/><h2>Building the planning horizon</h2></div>;
  if (query.error || !filtered) return <div className="scm-state error"><AlertTriangle/><h2>Supply horizon unavailable</h2><p>{query.error instanceof Error ? query.error.message : "Run a fresh planning cycle."}</p><button onClick={() => query.refetch()}>Try again</button></div>;
  const summary = filtered.summary ?? { critical_materials: 0, shortage_windows: 0, pull_in_opportunities: 0, cancellation_windows: 0, at_risk_units: 0 };
  const selectedRow = filtered.rows.find(row => row.material.id === selected) ?? filtered.rows[0];
  const suppliers = [...new Set(query.data?.rows.map(row => row.supplier?.name).filter((item): item is string => Boolean(item)))].sort();
  const actions = [...new Set(query.data?.rows.map(row => row.recommendation?.action_type).filter((item): item is string => Boolean(item)))].sort();
  const criticalRows = filtered.rows.filter(row => row.status === "CRITICAL");
  const interventions = filtered.rows.flatMap(row => row.events.filter(event => event.type !== "PO_RECEIPT").map(event => ({ ...event, material: row.material.code }))).sort((a, b) => a.date.localeCompare(b.date));
  const start = filtered.horizon_start ?? filtered.run?.horizon_start ?? isoDate(new Date()), end = filtered.horizon_end ?? filtered.run?.horizon_end ?? addDays(start, days);
  return <div className="supply-horizon-page"><header className="sh-page-head"><h1>See the next {days} days before they break.</h1><p>Visualize material coverage, incoming supply, shortage windows, and intervention points across the planning horizon.</p></header>
    <section className="sh-controls"><label><small>Plant</small><span>{filtered.plant?.name ?? "SCM Demo Plant"}</span></label><label><small>Planning horizon</small><span><CalendarDays/>{dateLabel(start)} — {dateLabel(end, true)}</span></label><div><small>Zoom</small><span>{[30, 90, 210, 365].map(value => <button className={days === value ? "active" : ""} onClick={() => setDays(value)} key={value}>{value}D</button>)}</span></div><div className="sh-current-view"><small>View</small><strong>Material</strong></div><label><small>Risk</small><select value={risk} onChange={event => setRisk(event.target.value)}><option value="">All</option><option value="CRITICAL">Critical</option><option value="WATCH">At Risk</option><option value="HEALTHY">Healthy</option><option value="EXCESS">Excess</option><option value="UNKNOWN">Unknown</option></select></label><button className={filtersOpen ? "active" : ""} onClick={() => setFiltersOpen(value => !value)}><Filter/>More filters</button>
      {filtersOpen && <div className="sh-filter-popover"><header><strong>More filters</strong><button onClick={() => setFiltersOpen(false)}><X/></button></header><label>Supplier<select value={supplier} onChange={event => setSupplier(event.target.value)}><option value="">All suppliers</option>{suppliers.map(value => <option key={value}>{value}</option>)}</select></label><label>Recommended action<select value={action} onChange={event => setAction(event.target.value)}><option value="">All actions</option>{actions.map(value => <option key={value}>{value}</option>)}</select></label><p>Product, OEM, category and planner filters activate when those master-data fields are mapped.</p><button onClick={() => { setSupplier(""); setAction(""); }}>Clear filters</button></div>}
    </section>
    <section className="sh-kpis"><article><i className="critical"><AlertTriangle/></i><span><small>Critical materials</small><strong>{summary.critical_materials}</strong><em>Need intervention</em></span></article><article><i className="watch"><CalendarDays/></i><span><small>Shortage windows</small><strong>{summary.shortage_windows}</strong><em>Across active horizon</em></span></article><article><i className="action"><Zap/></i><span><small>Pull-in opportunities</small><strong>{summary.pull_in_opportunities}</strong><em>Planner candidates</em></span></article><article><i className="deadline"><ShieldCheck/></i><span><small>Cancellation windows</small><strong>{summary.cancellation_windows}</strong><em>Decision deadlines</em></span></article><article><i className="exposure"><CircleDollarSign/></i><span><small>At-risk exposure</small><strong>{number.format(summary.at_risk_units)}</strong><em>Units · no cost master</em></span></article></section>
    <div className="sh-main"><HorizonWorkspace data={filtered} selected={selectedRow?.material.id ?? ""} onSelect={setSelected}/><Inspector row={selectedRow} close={() => setSelected("")}/></div>
    <section className="sh-mobile-list">{filtered.rows.map(row => <button key={row.material.id} onClick={() => setSelected(row.material.id)}><span><strong>{row.material.code}</strong><small>{row.material.description}</small></span><b className={row.status.toLowerCase()}>{row.status}{row.case_id?" · CASE":""}</b></button>)}</section>
    <section className="sh-insights"><article><header><h3>Upcoming risk clusters</h3><Link href="/scm/exceptions">View all <ArrowRight/></Link></header>{criticalRows.slice(0, 3).map(row => { const window = row.risk_windows[0]; return <p key={row.material.id}><AlertTriangle/><span><strong>{window ? `${dateLabel(window.start_date)} — ${dateLabel(window.end_date)}` : "Planning attention"}</strong><small>{row.material.code} · {row.material.description}</small></span><b>{window ? `${dayDiff(window.start_date, window.end_date) + 1}d` : "Open"}</b></p>; })}{!criticalRows.length && <p><Check/><span><strong>No critical risk cluster</strong><small>Current plan is covered.</small></span></p>}</article><article><header><h3>Intervention timeline</h3><Link href="/scm/actions">View actions <ArrowRight/></Link></header>{interventions.slice(0, 4).map(event => <p key={`${event.material}-${event.type}-${event.date}`}><Zap/><span><strong>{event.label ?? event.type.replaceAll("_", " ")}</strong><small>{event.material}</small></span><b>{dateLabel(event.date)}</b></p>)}{!interventions.length && <p><SlidersHorizontal/><span><strong>No pending intervention event</strong><small>Planning engine has not proposed a dated action.</small></span></p>}</article><article><header><h3>Horizon insights</h3></header><ul><li>{summary.critical_materials} materials face at least one critical shortage this horizon.</li><li>{summary.pull_in_opportunities} pull-in candidates are available for planner review.</li><li>{summary.cancellation_windows} cancellation deadlines fall inside the selected horizon.</li></ul></article></section>
  </div>;
}

export function SCMSupplyHorizon() { return <SCMFrame><HorizonPage/></SCMFrame>; }
