"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Bell, CheckCircle2, Clock3, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { getV2Notifications, searchV2, type V2OperationalNotification } from "@/lib/api";
import { useV2Formatting } from "./V2Formatting";

type Layer = "search" | "notifications" | null;
type NotificationTab = "needs" | "updates" | "all";

function needsUser(item: V2OperationalNotification) {
  return ["critical", "high", "action", "urgent"].includes(item.severity) ||
    ["approval", "decision", "escalation"].some(value => item.type.toLowerCase().includes(value));
}

export function OperationalCommandLayer() {
  const format = useV2Formatting();
  const [layer, setLayer] = useState<Layer>(null);
  const [term, setTerm] = useState("");
  const [settledTerm, setSettledTerm] = useState("");
  const [tab, setTab] = useState<NotificationTab>("needs");
  const inputRef = useRef<HTMLInputElement>(null);
  const notifications = useQuery({ queryKey: ["v2-notifications"], queryFn: getV2Notifications, refetchInterval: 30_000 });
  const search = useQuery({ queryKey: ["v2-search", settledTerm], queryFn: () => searchV2(settledTerm), enabled: settledTerm.length > 0 });
  const needsCount = notifications.data?.filter(needsUser).length ?? 0;
  const visibleNotifications = useMemo(() => (notifications.data ?? []).filter(item =>
    tab === "all" || (tab === "needs" ? needsUser(item) : !needsUser(item))), [notifications.data, tab]);

  useEffect(() => { const timer = window.setTimeout(() => setSettledTerm(term.trim()), 180); return () => window.clearTimeout(timer); }, [term]);
  useEffect(() => {
    if (layer === "search") inputRef.current?.focus();
    if (!layer) return;
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") setLayer(null); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [layer]);

  return <>
    <div className="v2-command-tools">
      <button onClick={() => setLayer(layer === "search" ? null : "search")} aria-label="Search plant records" aria-expanded={layer === "search"}><Search/><span>Search</span></button>
      <button className="v2-alert-button" onClick={() => setLayer(layer === "notifications" ? null : "notifications")} aria-label={`${needsCount} operational alerts`} aria-expanded={layer === "notifications"}><Bell/><span>Alerts</span>{needsCount > 0 && <b>{needsCount > 9 ? "9+" : needsCount}</b>}</button>
    </div>
    {layer && <button className="v2-command-scrim" aria-label="Close command panel" onClick={() => setLayer(null)}/>} 
    {layer && <aside className="v2-command-drawer" aria-label={layer === "search" ? "Operational search" : "Operational alerts"}>
      <header><div><small>Plant command layer</small><h2>{layer === "search" ? "Find operational context" : "Attention center"}</h2></div><button onClick={() => setLayer(null)} aria-label="Close panel"><X/></button></header>
      {layer === "search" ? <div className="v2-search-panel">
        <label><Search/><input ref={inputRef} value={term} onChange={event => setTerm(event.target.value)} placeholder="Line, asset, work order, material or fault" aria-label="Search plant records"/></label>
        {!settledTerm && <div className="v2-command-empty"><Search/><strong>Search the plant model</strong><p>Jump directly to connected operational context without navigating through tables.</p></div>}
        {search.isFetching && <p className="v2-command-loading">Searching canonical records…</p>}
        {search.error&&<div className="v2-command-empty" role="alert"><AlertTriangle/><strong>Operational search is unavailable</strong><p>No result is shown because canonical retrieval failed.</p><button onClick={()=>search.refetch()}>Retry</button></div>}
        {settledTerm && !search.isFetching && !search.error && !search.data?.groups.length && <div className="v2-command-empty"><AlertTriangle/><strong>No connected record found</strong><p>Try a line code, work order, material code or machine fault.</p></div>}
        {search.data?.groups.map(group => <section className="v2-search-group" key={group.entity}><h3>{group.entity}</h3>{group.results.map(result => <Link onClick={() => setLayer(null)} href={result.href} key={`${group.entity}-${result.id}`}><div><strong>{result.label}</strong><span>{result.context}</span></div><ArrowRight/></Link>)}</section>)}
      </div> : <div className="v2-notification-panel">
        <nav aria-label="Alert filters">{(["needs", "updates", "all"] as const).map(value => <button className={tab === value ? "active" : ""} onClick={() => setTab(value)} key={value}>{value === "needs" ? "Needs You" : value[0].toUpperCase() + value.slice(1)}</button>)}</nav>
        {notifications.isLoading && <p className="v2-command-loading">Loading attention items…</p>}
        {notifications.error&&<div className="v2-command-empty" role="alert"><AlertTriangle/><strong>Operational alerts are unavailable</strong><p>Do not infer that nothing needs attention.</p><button onClick={()=>notifications.refetch()}>Retry</button></div>}
        {!notifications.isLoading && !notifications.error && !visibleNotifications.length && <div className="v2-command-empty"><CheckCircle2/><strong>{tab === "needs" ? "Nothing needs your decision" : "No updates in this view"}</strong><p>New operational events will appear here with their source and consequence.</p></div>}
        <div className="v2-notification-list">{visibleNotifications.map(item => <Link href={item.href || "/operations"} onClick={() => setLayer(null)} key={item.id}><i className={item.severity}/><div><span><b>{item.severity}</b>{item.type.replaceAll("_", " ")}</span><strong>{item.title}</strong><p>{item.summary}</p><small><Clock3/>{format.time(item.created_at)}</small></div><ArrowRight/></Link>)}</div>
      </div>}
    </aside>}
  </>;
}
