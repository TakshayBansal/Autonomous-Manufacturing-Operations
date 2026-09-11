"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ProductShell } from "@/components/platform/ProductShell";
import { getDecisionInbox } from "@/lib/case-api";
import "../cases/cases.css";

export default function Decisions() {
  const query = useQuery({ queryKey: ["decision-inbox"], queryFn: getDecisionInbox, retry: false });
  return <ProductShell module="decisions" navigation={[]}><main className="case-index">
    <header><p>SHARED DECISION INBOX</p><h1>Choices and approvals requiring judgment.</h1><span>Recovery recommendations, assigned purchasing approvals and governed action requests. Each decision remains with its authoritative workflow.</span></header>
    {query.isPending ? <p role="status">Loading decisions…</p> : query.isError ? <div role="alert" className="case-state"><strong>Decision queue unavailable</strong><p>We cannot establish whether approvals are waiting.</p><button onClick={() => void query.refetch()}>Retry</button></div> : <>
    <section className="case-list">{query.data.map(row => <Link href={row.href} key={row.id}><i/><div><small>{row.source_type.replaceAll("_", " ")} · {row.owner ?? "Shared response"}</small><h2>{row.title}</h2><p>{row.alternative_count == null ? row.status.replaceAll("_", " ") : `${row.alternative_count} evaluated alternatives`}</p></div><dl><div><dt>Decision deadline</dt><dd>{row.deadline ? new Date(row.deadline).toLocaleString() : "Not recorded"}</dd></div></dl><span>Review →</span></Link>)}</section>
    {!query.data.length && <div className="case-state"><strong>No decisions returned for your scope</strong></div>}
    </>}
  </main></ProductShell>;
}
