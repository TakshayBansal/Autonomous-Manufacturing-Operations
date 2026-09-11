"use client";

import Link from "next/link";
import { AlertTriangle, Bot, ExternalLink, Send, X } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiFetch, mutate } from "@/lib/api";

type Briefing = { summary: string; severity: string; facts: Array<{ label: string; value: string | number }>; recommended_actions: Array<{ label: string; deviation_id?: string }>; evidence_refs: Array<Record<string, unknown>>; confidence: string; proactive_insight?:{what_changed:string;why_it_matters:string;already_doing:string;user_action:string;deviation_id:string}|null };

export function GigiPanel({ open, onClose, contextLabel, initialQuestion = "" }: { open: boolean; onClose: () => void; contextLabel: string; initialQuestion?: string }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<Briefing | null>(null);
  const [askError, setAskError] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const inputRef=useRef<HTMLInputElement>(null);
  const query = useQuery({ queryKey: ["gigi-briefing"], queryFn: () => apiFetch<Briefing>("/api/v2/gigi/briefing"), enabled: open });
  useEffect(()=>{if(!open)return;inputRef.current?.focus();const close=(event:KeyboardEvent)=>{if(event.key==="Escape")onClose()};window.addEventListener("keydown",close);return()=>window.removeEventListener("keydown",close)},[open,onClose]);
  useEffect(()=>{if(open)setQuestion(initialQuestion)},[open,initialQuestion]);
  async function ask(event: FormEvent) { event.preventDefault(); if (!question.trim() || asking) return; setAskError(null); setAsking(true); try { setAnswer(await mutate<Briefing>("/api/v2/gigi/query",localStorage.getItem("gg_csrf")??"",{query:question})); setQuestion(""); } catch (error) { setAskError(error instanceof Error ? error.message : "Gigi could not answer from current plant evidence."); } finally { setAsking(false); } }
  if (!open) return null;
  const content = answer ?? query.data;
  return <aside className="v2-gigi-panel" aria-label="Gigi plant guardian"><header><div><Bot/><span><strong>Gigi</strong><small>Plant Guardian</small></span></div><button onClick={onClose} aria-label="Close Gigi"><X/></button></header><div className="v2-gigi-context">{contextLabel}</div><div className="v2-gigi-conversation" aria-live="polite">{query.isLoading ? <p>Reading current plant context…</p> : query.error ? <div className="v2-degraded"><AlertTriangle/><div><strong>Grounded plant context is unavailable.</strong><p>Gigi will not invent an answer without current evidence.</p></div><button onClick={() => query.refetch()}>Retry</button></div> : <>{content?.proactive_insight&&<section className={`v2-gigi-proactive ${content.severity}`}><small>Contextual insight</small><dl><div><dt>What changed</dt><dd>{content.proactive_insight.what_changed}</dd></div><div><dt>Why it matters</dt><dd>{content.proactive_insight.why_it_matters}</dd></div><div><dt>Already in motion</dt><dd>{content.proactive_insight.already_doing}</dd></div><div><dt>Needs you</dt><dd>{content.proactive_insight.user_action}</dd></div></dl><Link href={`/v2/deviations/${content.proactive_insight.deviation_id}`}>Review context <ExternalLink/></Link></section>}<p className="v2-gigi-answer">{content?.summary}</p><div className="v2-gigi-facts">{content?.facts.map(item => <div key={item.label}><span>{item.label}</span><strong>{item.value}</strong></div>)}</div><div className="v2-evidence-chips"><span>Confidence: {content?.confidence}</span><span>{content?.evidence_refs.length ?? 0} evidence references</span></div>{content?.recommended_actions.map(item => item.deviation_id ? <Link href={`/v2/deviations/${item.deviation_id}`} key={item.label}>{item.label}<ExternalLink/></Link> : null)}</>}</div>{askError&&<p className="v2-form-error" role="alert">{askError}</p>}<form onSubmit={ask}><input ref={inputRef} value={question} onChange={event => setQuestion(event.target.value)} placeholder="Ask about the current plant state" aria-label="Ask Gigi"/><button aria-label="Send question" disabled={asking}>{asking?"Reading…":<Send/>}</button></form></aside>;
}
