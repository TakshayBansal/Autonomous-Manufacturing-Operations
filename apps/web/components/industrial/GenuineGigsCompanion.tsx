"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Bot, CheckCircle2, ChevronRight, Clock3, History, LoaderCircle, MessageCircle, Settings2, ShieldCheck, Sparkles, X } from "lucide-react";

import { AgentDrawer } from "@/components/industrial/AgentDrawer";
import { apiFetch, apiUrl, mutate } from "@/lib/api";
import type { CompanionAction, CompanionIntervention, CompanionState, WorkspaceOverview } from "@/lib/api";
import { roleLabel } from "@/lib/format";

type Tab = "now" | "prepared" | "running" | "decisions" | "updates" | "history";

export function GenuineGigsCompanion({ overview, csrf }: { overview: WorkspaceOverview; csrf: string }) {
  const [state, setState] = useState<CompanionState | null>(null);
  const [history, setHistory] = useState<CompanionIntervention[]>([]);
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<Tab>("now");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [bubbleHidden, setBubbleHidden] = useState("");
  const [incoming, setIncoming] = useState<CompanionIntervention | null>(null);
  const announcedRef = useRef("");

  const refresh = useCallback(async () => {
    try {
      const payload = await apiFetch<CompanionState>("/agent/companion/state");
      setState(payload);
      setError("");
      const top = payload.top_intervention;
      const newest = [...payload.interventions]
        .filter((item) => item.trigger_type === "work.handoff")
        .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())
        .find((item) => !window.sessionStorage.getItem(`gg_companion_seen_${item.id}`));
      if (newest && announcedRef.current !== newest.id) {
        setIncoming(newest);
        setBubbleHidden("");
        announcedRef.current = newest.id;
      }
      if (top && window.sessionStorage.getItem(`gg_companion_seen_${top.id}`)) setBubbleHidden(top.id);
      if (top?.delivery_mode === "panel" && announcedRef.current !== top.id && !window.sessionStorage.getItem(`gg_companion_seen_${top.id}`)) {
        announcedRef.current = top.id;
        window.sessionStorage.setItem(`gg_companion_seen_${top.id}`, "1");
        setOpen(true);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Companion is temporarily unavailable");
      setState((current) => current ? { ...current, state: "offline" } : null);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const fallback = window.setInterval(() => void refresh(), 30000);
    let source: EventSource | undefined;
    try {
      source = new EventSource(apiUrl("/agent/companion/stream"), { withCredentials: true });
      const update = (event: Event) => {
        const message = event as MessageEvent<string>;
        try {
          const notice = JSON.parse(message.data || "{}") as { id?: string };
          if (notice.id) {
            void apiFetch<CompanionIntervention>(`/agent/companion/interventions/${encodeURIComponent(notice.id)}`)
              .then((intervention) => {
                if (intervention.delivery_mode === "bubble" || intervention.delivery_mode === "panel") {
                  setIncoming(intervention);
                  setBubbleHidden("");
                  announcedRef.current = intervention.id;
                }
              })
              .catch(() => undefined);
          }
        } catch { /* heartbeat/state events are handled by refresh */ }
        void refresh();
      };
      source.addEventListener("companion.update", update);
      source.addEventListener("companion.state", update);
      source.addEventListener("companion.counts", update);
    } catch {
      source = undefined;
    }
    return () => { window.clearInterval(fallback); source?.close(); };
  }, [refresh]);

  useEffect(() => {
    if (!open || tab !== "history") return;
    void apiFetch<CompanionIntervention[]>("/agent/companion/interventions").then(setHistory).catch(() => setHistory([]));
  }, [open, tab]);

  useEffect(() => {
    const openCompanion = () => setOpen(true);
    window.addEventListener("genuinegigs:open-companion", openCompanion);
    return () => window.removeEventListener("genuinegigs:open-companion", openCompanion);
  }, []);

  const top = state?.top_intervention ?? null;
  const popup = incoming;
  const items = useMemo(() => {
    const rows = [...(state?.interventions ?? [])].sort((left, right) => {
      if (left.trigger_type === "login.briefing" && right.trigger_type !== "login.briefing") return 1;
      if (right.trigger_type === "login.briefing" && left.trigger_type !== "login.briefing") return -1;
      return new Date(right.created_at).getTime() - new Date(left.created_at).getTime();
    });
    if (tab === "prepared") return rows.filter((row) => row.prepared_work_id || row.title.toLowerCase().includes("prepared"));
    if (tab === "running") return rows.filter((row) => row.run_id && row.delivery_state === "acted");
    if (tab === "decisions") return rows.filter((row) => row.proposal_id || row.trigger_type === "decision.required");
    if (tab === "updates") return rows.filter((row) => ["info", "success"].includes(row.severity));
    if (tab === "history") return history.filter((row) => ["dismissed", "resolved", "expired"].includes(row.delivery_state));
    return rows.slice(0, 10);
  }, [history, state, tab]);

  async function markOpen(intervention: CompanionIntervention) {
    if (intervention.delivery_state === "opened") return;
    await mutate(`/agent/companion/interventions/${encodeURIComponent(intervention.id)}/open`, csrf);
  }

  async function act(intervention: CompanionIntervention, action: CompanionAction) {
    if (busy) return;
    setBusy(intervention.id + action.id); setError("");
    try {
      const response = await mutate<Record<string, unknown>>(
        `/agent/companion/interventions/${encodeURIComponent(intervention.id)}/actions`, csrf,
        { action_id: action.id, execution_mode: action.mode, resource_version: intervention.aggregate_version },
      );
      if (response.kind === "navigation") window.location.assign(String(response.href || action.href || "/procurement"));
      if (response.kind === "run") { setTab("running"); setOpen(true); }
      await refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The companion action could not be started");
    } finally { setBusy(""); }
  }

  async function snooze(intervention: CompanionIntervention) {
    await mutate(`/agent/companion/interventions/${encodeURIComponent(intervention.id)}/snooze`, csrf, { minutes: 60 });
    rememberHidden(intervention.id); await refresh();
  }

  async function dismiss(intervention: CompanionIntervention) {
    const reason = ["critical", "warning"].includes(intervention.severity)
      ? window.prompt("Why are you dismissing this high-risk item?")?.trim() : "Not needed";
    if (["critical", "warning"].includes(intervention.severity) && !reason) return;
    await mutate(`/agent/companion/interventions/${encodeURIComponent(intervention.id)}/dismiss`, csrf, { reason });
    rememberHidden(intervention.id); await refresh();
  }

  async function cancel(intervention: CompanionIntervention) {
    setBusy(intervention.id + "cancel");
    try {
      await mutate(`/agent/companion/interventions/${encodeURIComponent(intervention.id)}/cancel`, csrf);
      await refresh();
    } finally { setBusy(""); }
  }

  async function updatePreference(field: string, value: unknown) {
    if (!state) return;
    setBusy("preferences");
    try {
      await mutate("/agent/companion/preferences", csrf, { [field]: value }, "PUT");
      await refresh();
    } finally { setBusy(""); }
  }

  const motionClass = state?.preferences.animation_mode === "reduced" ? "reduced" : "";
  const showBubble = popup && bubbleHidden !== popup.id;

  function rememberHidden(id: string) {
    window.sessionStorage.setItem(`gg_companion_seen_${id}`, "1");
    setBubbleHidden(id);
    setIncoming((current) => current?.id === id ? null : current);
  }

  return <>
    <div className={`gg-companion ${state?.state ?? "idle"} ${motionClass}`} data-testid="genuinegigs-companion">
      {showBubble && popup && <section className={`companion-bubble ${popup.severity}`} aria-live="assertive">
        <button className="companion-bubble-close" onClick={() => rememberHidden(popup.id)} aria-label="Hide this message"><X size={14}/></button>
        <small>{popup.severity === "critical" ? "Urgent attention" : "Gigi has new work for you"}</small>
        <strong>{popup.title}</strong>
        <p>{popup.message}</p>
        <footer className="companion-bubble-actions">
          {popup.actions.filter((action) => action.mode !== "explain").slice(0, 2).map((action) => action.href && action.mode === "manual"
            ? <Link key={action.id} href={action.href} onClick={() => { rememberHidden(popup.id); void markOpen(popup); }}>{action.label}<ChevronRight size={13}/></Link>
            : <button key={action.id} disabled={Boolean(busy)} onClick={() => { rememberHidden(popup.id); void act(popup, action); }}>{action.label}<ChevronRight size={13}/></button>)}
          <button className="quiet" onClick={() => { rememberHidden(popup.id); void markOpen(popup); setOpen(true); }}>Details</button>
        </footer>
      </section>}
      <button className="companion-mascot" type="button" onClick={() => setOpen((value) => !value)} aria-label="Open GenuineGigs companion" aria-expanded={open}>
        <span className="companion-halo" />
        <span className="companion-face"><i/><i/></span>
        <span className="companion-status">{state?.state === "thinking" ? <LoaderCircle size={13}/> : <Sparkles size={13}/>}</span>
        {!!state?.unresolved_count && <em>{state.unresolved_count > 99 ? "99+" : state.unresolved_count}</em>}
      </button>
      <span className="companion-caption">{state?.state === "thinking" ? "Preparing" : state?.state === "urgent" ? "Needs you" : state?.state === "offline" ? "Manual mode" : "GenuineGigs"}</span>
    </div>

    {open && <div className="companion-panel-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setOpen(false)}>
      <aside className="companion-panel" role="dialog" aria-modal="true" aria-labelledby="companion-title">
        <header>
          <div className="companion-panel-identity"><span><Bot size={20}/></span><div><strong id="companion-title">GenuineGigs Companion</strong><small><i className={state?.state ?? "idle"}/> {state?.running_count ? `${state.running_count} preparation running` : "Watching your procurement work"}</small></div></div>
          <div><button onClick={() => window.dispatchEvent(new Event("genuinegigs:open-agent"))} aria-label="Open chat"><MessageCircle size={18}/></button><button onClick={() => setOpen(false)} aria-label="Close companion"><X size={19}/></button></div>
        </header>
        <nav aria-label="Companion views">
          {(["now", "prepared", "running", "decisions", "updates", "history"] as Tab[]).map((name) => <button className={tab === name ? "active" : ""} onClick={() => setTab(name)} key={name}>{name}</button>)}
        </nav>
        {error && <div className="companion-error">{error}. You can continue manually.</div>}
        <div className="companion-feed">
          {tab === "updates" && state && <section className="companion-preferences"><div><strong>How proactive should I be?</strong><small>You can reduce interruptions without losing the inbox or manual workflows.</small></div><label>Presence<select value={state.preferences.proactive_level} disabled={busy === "preferences"} onChange={(event) => void updatePreference("proactive_level", event.target.value)}><option value="risk_tiered">Risk-tiered</option><option value="mostly_silent">Mostly silent</option><option value="muted">Inbox only</option></select></label><label><input type="checkbox" checked={state.preferences.background_preparation_enabled} disabled={busy === "preferences"} onChange={(event) => void updatePreference("background_preparation_enabled", event.target.checked)}/> Prepare eligible work automatically</label><label><input type="checkbox" checked={state.preferences.login_briefing_enabled} disabled={busy === "preferences"} onChange={(event) => void updatePreference("login_briefing_enabled", event.target.checked)}/> Show my daily briefing</label></section>}
          {items.length ? items.map((item) => <article className={`companion-item ${item.severity}`} key={item.id} onFocus={() => void markOpen(item)}>
            <div className="companion-item-head"><span>{item.severity === "critical" ? <ShieldCheck size={16}/> : item.run_id && item.delivery_state === "acted" ? <LoaderCircle size={16}/> : <Sparkles size={16}/>}</span><div><small>{item.trigger_type.replaceAll("_", " ").replaceAll(".", " · ")}</small><strong>{item.title}</strong></div></div>
            <p>{item.message}</p>
            <details><summary>Why now and evidence</summary><p>{item.why_now}</p><small>{item.evidence.length} evidence reference{item.evidence.length === 1 ? "" : "s"}{item.confidence != null ? ` · ${Math.round(item.confidence * 100)}% confidence` : ""}</small>{item.responsible_authority && <span>Responsible authority: {roleLabel(item.responsible_authority)}</span>}</details>
            <footer>{item.actions.map((action) => action.href && action.mode === "manual"
              ? <Link key={action.id} href={action.href} onClick={() => void markOpen(item)}>{action.label}</Link>
              : <button key={action.id} disabled={Boolean(busy)} onClick={() => void act(item, action)}>{busy === item.id + action.id ? <LoaderCircle size={13}/> : null}{action.label}</button>)}
              {item.run_id && item.delivery_state === "acted" && <button className="quiet" disabled={Boolean(busy)} onClick={() => void cancel(item)}>Stop</button>}
              <button className="quiet" onClick={() => void snooze(item)}><Clock3 size={13}/> Snooze</button><button className="quiet" onClick={() => void dismiss(item)}>Dismiss</button>
            </footer>
          </article>) : <div className="companion-empty"><CheckCircle2 size={26}/><strong>You are caught up</strong><p>No item in this view needs your attention.</p></div>}
        </div>
        <footer className="companion-panel-footer"><button onClick={() => window.dispatchEvent(new Event("genuinegigs:open-agent"))}><MessageCircle size={15}/> Ask GenuineGigs</button><button onClick={() => setTab("history")}><History size={15}/> Activity history</button><button onClick={() => setTab("updates")}><Settings2 size={15}/> Updates</button></footer>
      </aside>
    </div>}
    <AgentDrawer overview={overview} hideLauncher />
  </>;
}
