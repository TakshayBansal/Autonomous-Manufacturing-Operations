"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  CircleStop,
  Clock3,
  MessageSquare,
  Send,
} from "lucide-react";

import {
  AgentHome,
  AgentMessage,
  AgentReply,
  AgentThread,
  User,
  WorkspaceData,
  WorkspaceOverview,
  mutate,
} from "@/lib/api";
import { asText, roleLabel } from "@/lib/format";


function csrfToken() {
  return window.localStorage.getItem("gg_csrf") ?? "";
}


function firstObject<T>(rows: Array<Record<string, unknown>> | undefined) {
  return (rows?.[0] ?? null) as T | null;
}


function dateText(value: unknown) {
  if (!value) return "No commitment";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}


export function AgentWorkspace({
  workspaceData,
  user,
}: {
  workspaceData: WorkspaceData | null;
  user: User;
}) {
  const home = firstObject<AgentHome>(workspaceData?.agent_home);
  const team = workspaceData?.team_status ?? [];
  const workspaces = workspaceData?.workspaces ?? [];
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const queue = home?.queue ?? [];

  if (!home) return <section className="agent-empty-state"><Clock3 size={18} /><p>Loading your role workspace.</p></section>;

  return (
    <div className="agent-workspace">
      <section className="agent-command-band">
        <div className="agent-command-heading">
          <div>
            <div className="section-kicker">{roleLabel(user.role)} agent</div>
            <h2>{home.profile.display_name}</h2>
            <p>{queue.length} assigned item{queue.length === 1 ? "" : "s"} in your personal queue.</p>
          </div>
          <span className={"agent-availability " + (home.enabled ? "online" : "offline")}>
            <span /> {home.enabled ? "Available" : "Disabled"}
          </span>
        </div>
        <div className='agent-mode-summary'><MessageSquare size={18} /><div><strong>{home.provider_mode === 'groq' ? 'Groq connected' : 'Limited mode'}</strong><span>{home.provider_mode === 'groq' ? 'Use the role-agent button to discuss work or explicitly delegate a complete requirement.' : 'Scoped explanations remain available. Free-form actions are disabled until Groq is connected.'}</span></div></div>
        {error && <div className="agent-inline-error">{error}</div>}
        {notice && <div className="agent-inline-notice"><CheckCircle2 size={15} /> {notice}</div>}
      </section>

      <div className="agent-operations-grid">
        <AgentQueue queue={queue} />
        <RunAndReview home={home} />
      </div>

      {user.role === "plant_manager" && <TeamFollowUp rows={team} />}
      <DelegationRegister rows={home.delegations} />
      <WorkspaceRegister rows={workspaces} user={user} onBusy={setBusy} onError={setError} busy={busy} />
    </div>
  );
}


function AgentConversation({ messages }: { messages: AgentMessage[] }) {
  if (!messages.length) return null;
  return (
    <div className="agent-conversation" aria-live="polite">
      {messages.map((message) => (
        <article className={"agent-message " + message.message_type} key={message.id}>
          <span>{message.message_type === "agent" ? "Agent" : "You"}</span>
          <p>{message.content}</p>
          {!!message.attachments?.length && (
            <div className="agent-citations" aria-label="Attached files">
              {message.attachments.map((attachment) => (
                <span key={attachment.id}>{attachment.filename} · {attachment.status.replaceAll("_", " ")}</span>
              ))}
            </div>
          )}
          {message.citations?.length > 0 && (
            <div className="agent-citations">
              {message.citations.map((citation) => (
                <Link href={citation.href} key={message.id + "-" + citation.id}>{citation.label}</Link>
              ))}
            </div>
          )}
        </article>
      ))}
    </div>
  );
}


function AgentQueue({ queue }: { queue: Array<Record<string, unknown>> }) {
  return (
    <section className="agent-ledger">
      <div className="panel-head compact-head">
        <div><div className="section-kicker">Named ownership</div><h3>Personal queue</h3></div>
        <span className="record-count">{queue.length}</span>
      </div>
      <div className="agent-definition-list">
        {queue.length ? queue.map((task) => (
          <div className="agent-definition-row" key={asText(task.id)}>
            <div><strong>{asText(task.title)}</strong><span>{roleLabel(asText(task.owner_role))}</span></div>
            <div><small>Due</small><strong>{dateText(task.due_at)}</strong></div>
            <a className="small-action" href={"/agent?work_item=" + encodeURIComponent(asText(task.id))}>Discuss <ArrowRight size={14} /></a>
          </div>
        )) : <p className="empty-state">No assigned work is waiting for you.</p>}
      </div>
    </section>
  );
}


function RunAndReview({ home }: { home: AgentHome }) {
  const [busyId, setBusyId] = useState('');
  const [error, setError] = useState('');

  async function decide(proposal: Record<string, unknown>, decision: 'confirm' | 'reject') {
    const id = asText(proposal.id);
    let reason: string | null = null;
    if (decision === 'confirm') {
      const accepted = window.confirm(
        'Confirm this controlled action? The server will recheck your authority and the current record version.',
      );
      if (!accepted) return;
    } else {
      reason = window.prompt('Why are you rejecting this proposal?');
      if (!reason?.trim()) return;
    }
    setBusyId(id);
    setError('');
    try {
      await mutate(
        '/agent/proposals/' + encodeURIComponent(id) + '/' + decision,
        csrfToken(),
        { reason },
      );
      window.location.reload();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Proposal decision failed');
      setBusyId('');
    }
  }

  return (
    <section className="agent-ledger">
      <div className="panel-head compact-head">
        <div><div className="section-kicker">Human review</div><h3>Runs and proposals</h3></div>
        <span className="record-count">{home.proposals.length} pending</span>
      </div>
      <dl className="agent-counts">
        <div><dt>Recent runs</dt><dd>{home.runs.length}</dd></div>
        <div><dt>Draft threads</dt><dd>{home.threads.length}</dd></div>
        <div><dt>Awaiting review</dt><dd>{home.proposals.length}</dd></div>
      </dl>
      {error && <div className="agent-inline-error">{error}</div>}
      {home.proposals.map((proposal) => (
        <div className="agent-review-row" key={asText(proposal.id)}>
          <div>
            <strong>{asText(proposal.action).replaceAll("_", " ")}</strong>
            <span>{asText(proposal.expected_effect)}</span>
            <small>{asText(proposal.risk_class, 'R4')} � authority: {roleLabel(asText(proposal.required_authority))}</small>
          </div>
          <div className="button-row">
            <button className="small-action" type="button" disabled={busyId === asText(proposal.id)} onClick={() => void decide(proposal, 'confirm')}>Confirm</button>
            <button className="small-action danger" type="button" disabled={busyId === asText(proposal.id)} onClick={() => void decide(proposal, 'reject')}>Reject</button>
          </div>
        </div>
      ))}
      {!home.proposals.length && <p className="empty-state">No agent-prepared decision is awaiting your authority.</p>}
      <div className="agent-activity-list" aria-label="Recent agent activity">
        {home.runs.map((run) => (
          <article key={asText(run.id)}>
            <div>
              <strong>{asText(run.intent, 'Scoped assistance').replaceAll('_', ' ')}</strong>
              <span>{asText(run.provider)} / {asText(run.model)}</span>
            </div>
            <span className={'status-pill ' + (asText(run.state) === 'completed' ? 'good' : 'action')}>{asText(run.state)}</span>
          </article>
        ))}
        {home.receipts.map((receipt) => (
          <article key={asText(receipt.id)}>
            <div>
              <strong>Verified receipt � {asText(receipt.tool_name).replaceAll('_', ' ')}</strong>
              <span>{asText(receipt.target_entity_type)} / {asText(receipt.target_entity_id)}</span>
            </div>
            <span className="status-pill good">{asText(receipt.status)}</span>
          </article>
        ))}
      </div>
    </section>
  );
}


function TeamFollowUp({ rows }: { rows: Array<Record<string, unknown>> }) {
  return (
    <section className="agent-ledger">
      <div className="panel-head compact-head">
        <div><div className="section-kicker">Reporting hierarchy</div><h3>Team commitments and blockers</h3></div>
        <span className="record-count">{rows.length} people</span>
      </div>
      <div className="team-status-grid">
        {rows.map((row) => (
          <article className="team-status-row" key={asText(row.membership_id)}>
            <div><strong>{asText(row.employee_name)}</strong><span>{roleLabel(asText(row.role))}</span></div>
            <div><small>Open work</small><strong>{asText(row.open_work, "0")}</strong></div>
            <div><small>Commitment</small><strong>{dateText(row.next_commitment)}</strong></div>
            <div><small>Formal status</small><strong>{asText(row.latest_status).replaceAll("_", " ")}</strong></div>
            <div className={"team-risk " + asText(row.risk)}>{asText(row.blocker, asText(row.risk).replaceAll("_", " "))}</div>
          </article>
        ))}
        {!rows.length && <p className="empty-state">No reporting-line status is available yet.</p>}
      </div>
    </section>
  );
}


function DelegationRegister({ rows }: { rows: Array<Record<string, unknown>> }) {
  return (
    <section className="agent-ledger">
      <div className="panel-head compact-head">
        <div><div className="section-kicker">Agent handoffs</div><h3>Delegation requests</h3></div>
        <span className="record-count">{rows.length}</span>
      </div>
      <div className="agent-definition-list">
        {rows.map((row) => (
          <div className="agent-definition-row" key={asText(row.id)}>
            <div><strong>{asText(row.requested_outcome)}</strong><span>Depth {asText(row.depth)} / {asText(row.status).replaceAll("_", " ")}</span></div>
            <div><small>Due</small><strong>{dateText(row.due_at)}</strong></div>
            <span className={"status-pill " + (asText(row.status) === "pending" ? "action" : "good")}>{asText(row.status)}</span>
          </div>
        ))}
        {!rows.length && <p className="empty-state">No active handoff is waiting for this role.</p>}
      </div>
    </section>
  );
}


function WorkspaceRegister({
  rows,
  user,
  busy,
  onBusy,
  onError,
}: {
  rows: Array<Record<string, unknown>>;
  user: User;
  busy: boolean;
  onBusy: (value: boolean) => void;
  onError: (value: string) => void;
}) {
  const deploymentAvailable = rows.every((row) => row.deployment_agent_available !== false);
  const unavailableReason = asText(rows.find((row) => row.agent_unavailable_reason)?.agent_unavailable_reason);

  async function selectWorkspace(membershipId: string) {
    onBusy(true);
    onError("");
    try {
      const selected = await mutate<{ csrf_token: string }>(
        "/workspaces/select",
        csrfToken(),
        { membership_id: membershipId },
      );
      window.localStorage.setItem("gg_csrf", selected.csrf_token);
      window.location.assign("/agent");
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Workspace switch failed");
      onBusy(false);
    }
  }

  async function createWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    onBusy(true);
    onError("");
    try {
      const created = await mutate<{ membership: { id: string } }>(
        "/workspaces",
        csrfToken(),
        {
          company_name: form.get("company_name"),
          workspace_name: form.get("workspace_name"),
          plant_name: form.get("plant_name"),
          plant_code: form.get("plant_code"),
          agent_enabled: form.get("agent_enabled") === "on",
        },
      );
      const selected = await mutate<{ csrf_token: string }>(
        '/workspaces/select', csrfToken(), { membership_id: created.membership.id },
      );
      window.localStorage.setItem('gg_csrf', selected.csrf_token);
      window.location.assign('/workspace/setup');
    } catch (caught) {
      onError(caught instanceof Error ? caught.message : "Workspace creation failed");
      onBusy(false);
    }
  }

  return (
    <section className="agent-ledger">
      <div className="panel-head compact-head">
        <div><div className="section-kicker">Account workspaces</div><h3>Demo and fresh environments</h3></div>
        <span className="record-count">{rows.length}</span>
      </div>
      <div className="workspace-switch-list">
        {rows.map((row) => (
          <div className="workspace-switch-row" key={asText(row.membership_id)}>
            <div><strong>{asText(row.workspace_name)}</strong><span>{asText(row.plant_name)} / {roleLabel(asText(row.role))}</span></div>
            <span className={"workspace-kind " + asText(row.workspace_kind)}>{asText(row.workspace_kind)}</span>
            {row.selected ? <span className="status-pill good">Current</span> : (
              <button className="small-action" disabled={busy} onClick={() => void selectWorkspace(asText(row.membership_id))}>Open</button>
            )}
          </div>
        ))}
      </div>
      {(user.role === "plant_manager" || user.role === "admin") && (
        <details className="fresh-workspace-form">
          <summary>Create fresh workspace</summary>
          <form className="ops-form" onSubmit={createWorkspace}>
            <label>Company<input name="company_name" required /></label>
            <label>Workspace<input name="workspace_name" required /></label>
            <label>Plant<input name="plant_name" required /></label>
            <label>Plant code<input name="plant_code" required /></label>
            <label className="checkbox-label">
              <input name="agent_enabled" type="checkbox" defaultChecked={deploymentAvailable} disabled={!deploymentAvailable} />
              Enable role agents
            </label>
            {!deploymentAvailable && <p className="form-note">{unavailableReason || "Configure the deployment model provider to enable role agents."}</p>}
            <button className="action-button" disabled={busy}>Create empty workspace</button>
          </form>
        </details>
      )}
    </section>
  );
}


export function TaskAgentPanel({ overview }: { overview: WorkspaceOverview }) {
  const [workItemId, setWorkItemId] = useState("");
  const [threadId, setThreadId] = useState("");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setWorkItemId(new URLSearchParams(window.location.search).get("work_item") ?? "");
  }, []);

  const item = overview.work_items.find((candidate) => candidate.id === workItemId);
  if (!item) return null;
  const selectedItem = item;

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (!question.trim()) return;
    setBusy(true);
    setError("");
    try {
      let activeThread = threadId;
      if (!activeThread) {
        const created = await mutate<AgentThread>(
          "/agent/threads",
          csrfToken(),
          { thread_type: "work_item", title: selectedItem.title, work_item_id: selectedItem.id },
        );
        activeThread = created.id;
        setThreadId(created.id);
      }
      const reply = await mutate<AgentReply>(
        "/agent/threads/" + activeThread + "/messages",
        csrfToken(),
        { content: question.trim() },
      );
      setMessages((current) => [...current, reply.message]);
      setQuestion("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Agent request failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rail-card task-agent-panel">
      <div className="rail-kicker">Task agent</div>
      <h2>{item.plain_language_goal}</h2>
      <p>{item.why_now}</p>
      <dl>
        <div><dt>Result</dt><dd>{item.expected_result}</dd></div>
        <div><dt>Evidence</dt><dd>{item.required_evidence.join(", ")}</dd></div>
      </dl>
      <div className="agent-capability-list">
        {item.agent_capabilities.map((capability) => <span key={capability}>{capability.replaceAll("_", " ")}</span>)}
      </div>
      <AgentConversation messages={messages} />
      <form className="rail-agent-composer" onSubmit={ask}>
        <label className="sr-only" htmlFor="task-agent-question">Ask about this task</label>
        <textarea id="task-agent-question" rows={3} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask for an explanation or draft" />
        <button className="action-button wide" disabled={busy || !question.trim()}><Send size={15} /> Ask about this task</button>
      </form>
      {error && <div className="agent-inline-error">{error}</div>}
    </section>
  );
}
