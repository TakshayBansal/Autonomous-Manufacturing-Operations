"use client";

import Link from "next/link";
import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  History,
  LoaderCircle,
  MessageSquarePlus,
  Paperclip,
  PanelRightClose,
  Send,
  Sparkles,
  Trash2,
  X,
} from "lucide-react";

import {
  AgentHome,
  AgentMessage,
  AgentReply,
  AgentThread,
  WorkspaceOverview,
  apiFormFetch,
  apiFetch,
  mutate,
} from "@/lib/api";
import { roleLabel } from "@/lib/format";

type ThreadDetail = { thread: AgentThread; messages: AgentMessage[] };
type AgentBlockAction = { id: string; label: string; prompt?: string; href?: string; proposal_id?: string; requires_rationale?: boolean };
const legacyBlockTitles = new Set([
  "Answer", "Details", "Sources", "Role ownership", "Not delegated yet",
  "Still needed", "Prepared work saved", "Created records", "What happens next",
]);
const suggestedActionCopy: Record<string, { label: string; prompt: string }> = {
  list_my_tasks: { label: "Show my tasks", prompt: "Show my current tasks." },
  list_team_tasks: { label: "Team follow-ups", prompt: "Show the team tasks that need follow-up." },
  list_approved_materials: { label: "Approved materials", prompt: "What approved material masters do we have?" },
  create_purchase_requirement: { label: "New requirement", prompt: "Create a new material requirement." },
  prepare_rfq_draft: { label: "Prepare supplier request", prompt: "Prepare the supplier request for the selected requirement." },
  upload_supplier_quotes: { label: "Attach quotations", prompt: "Upload and review these supplier quotations." },
  prepare_supplier_comparison: { label: "Compare quotations", prompt: "Compare the verified supplier quotations." },
  summarize_procurement_risks: { label: "Summarize risks", prompt: "Summarize the procurement risks that need my attention." },
  summarize_team_status: { label: "Team progress", prompt: "Summarize my team’s current work and blockers." },
  review_quote_extraction: { label: "Review quotation", prompt: "Show the extracted evidence for the selected quotation." },
  prepare_gate_entry_proposal: { label: "Record arrival", prompt: "Prepare the Gate entry for the selected purchase order." },
  prepare_store_receipt_proposal: { label: "Record receipt", prompt: "Prepare the Stores receipt for the selected purchase order." },
  prepare_quality_inspection_proposal: { label: "Record inspection", prompt: "Prepare the Quality inspection for the selected receipt." },
};

function csrfToken() {
  return window.localStorage.getItem("gg_csrf") ?? "";
}

function selectedPageContext() {
  if (typeof window === "undefined") return undefined;
  const params = new URLSearchParams(window.location.search);
  const candidates: Array<[string, string]> = [
    ["requirement", "purchase_requirement"], ["rfq", "rfq"],
    ["quote", "supplier_quote"], ["comparison", "bid_comparison"],
    ["negotiation", "negotiation_round"], ["award", "award_decision"],
    ["po", "po_draft"], ["asn", "asn"], ["gate", "gate_entry"],
    ["receipt", "store_receipt"], ["inspection", "inspection_result"],
    ["case", "case"],
  ];
  for (const [parameter, entityType] of candidates) {
    const entityId = params.get(parameter);
    if (entityId) return { entity_type: entityType, entity_id: entityId, source: "page" };
  }
  return undefined;
}

function messageLabel(type: string) {
  if (type === "agent") return "Agent";
  if (type === "user") return "You";
  if (type === "proposal") return "Proposal";
  if (type === "delegation") return "Delegation";
  return type.replaceAll("_", " ");
}

function formatThreadDate(value: unknown) {
  if (!value) return "";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function inlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  const tokens = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g);
  return tokens.filter(Boolean).map((token, index) => {
    const key = keyPrefix + "-" + index;
    if (token.startsWith("**") && token.endsWith("**")) return <strong key={key}>{token.slice(2, -2)}</strong>;
    if (token.startsWith("`") && token.endsWith("`")) return <code key={key}>{token.slice(1, -1)}</code>;
    const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) {
      const href = link[2];
      if (href.startsWith("/") || href.startsWith("https://") || href.startsWith("http://")) {
        return <a href={href} key={key} target={href.startsWith("/") ? undefined : "_blank"} rel="noreferrer">{link[1]}</a>;
      }
      return <span key={key}>{link[1]}</span>;
    }
    return <span key={key}>{token}</span>;
  });
}

function tableCells(line: string) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function isTableDivider(line: string) {
  const cells = tableCells(line);
  return cells.length > 1 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

const businessRecordLabels: Record<string, string> = {
  display_id: "Record", requirement_number: "Requirement", rfq_number: "Supplier request",
  comparison_number: "Comparison", po_number: "Purchase order", item_code: "Material code",
  material: "Material", quantity: "Quantity", uom: "Unit", need_by_date: "Need by",
  assignee: "Assigned to", status: "Status", supplier_name: "Supplier",
  verified_quote_count: "Verified quotations", recommendation_rationale: "Recommendation",
  decision_count: "Evidence decisions", deadline: "Response deadline", supplier_count: "Suppliers",
};

function businessRecordEntries(record: Record<string, unknown>) {
  return Object.entries(record).filter(([key, value]) => (
    key in businessRecordLabels && ["string", "number"].includes(typeof value) && value !== ""
  ));
}

function clarificationChoiceLabel(choice: Record<string, unknown>) {
  return String(
    choice.label ?? choice.name ?? choice.business_number ?? choice.code
    ?? choice.value ?? choice.supplier_id ?? choice.id ?? "Select this option",
  );
}

function clarificationPrompt(field: string, choice: Record<string, unknown>, context?: string) {
  const label = clarificationChoiceLabel(choice);
  const subject = field.replaceAll("_", " ") || "selection";
  return context ? `${context}: ${subject} is ${label}` : `${subject} is ${label}`;
}

export function AgentMarkdown({ content }: { content: string }) {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const children = inlineMarkdown(heading[2], "heading-" + index);
      blocks.push(level === 1 ? <h3 key={index}>{children}</h3> : <h4 key={index}>{children}</h4>);
      index += 1;
      continue;
    }

    if (line.includes("|") && index + 1 < lines.length && isTableDivider(lines[index + 1])) {
      const headers = tableCells(line);
      const rows: string[][] = [];
      index += 2;
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(tableCells(lines[index]));
        index += 1;
      }
      blocks.push(
        <div className="agent-markdown-table-wrap" key={"table-" + index}>
          <table>
            <thead><tr>{headers.map((cell, cellIndex) => <th key={cellIndex}>{inlineMarkdown(cell, "th-" + cellIndex)}</th>)}</tr></thead>
            <tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{headers.map((_, cellIndex) => <td key={cellIndex}>{inlineMarkdown(row[cellIndex] ?? "", "td-" + rowIndex + "-" + cellIndex)}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ""));
        index += 1;
      }
      blocks.push(<ul key={"ul-" + index}>{items.map((item, itemIndex) => <li key={itemIndex}>{inlineMarkdown(item, "ul-item-" + itemIndex)}</li>)}</ul>);
      continue;
    }

    if (/^\d+[.)]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+[.)]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+[.)]\s+/, ""));
        index += 1;
      }
      blocks.push(<ol key={"ol-" + index}>{items.map((item, itemIndex) => <li key={itemIndex}>{inlineMarkdown(item, "ol-item-" + itemIndex)}</li>)}</ol>);
      continue;
    }

    const paragraph: string[] = [line];
    index += 1;
    while (index < lines.length) {
      const next = lines[index].trim();
      if (!next || /^(#{1,3})\s+/.test(next) || /^[-*]\s+/.test(next) || /^\d+[.)]\s+/.test(next)) break;
      if (next.includes("|") && index + 1 < lines.length && isTableDivider(lines[index + 1])) break;
      paragraph.push(next);
      index += 1;
    }
    blocks.push(
      <p key={"p-" + index}>
        {paragraph.map((part, partIndex) => <span key={partIndex}>{inlineMarkdown(part, "p-" + index + "-" + partIndex)}{partIndex < paragraph.length - 1 && <br />}</span>)}
      </p>,
    );
  }

  return <div className="agent-markdown">{blocks}</div>;
}

function AgentBlocks({ message, onAction, decidedProposals = {} }: { message: AgentMessage; onAction?: (action: AgentBlockAction) => void; decidedProposals?: Record<string, "confirmed" | "rejected"> }) {
  return (
    <div className="agent-response-blocks">
      {(message.content_blocks ?? []).map((block, index) => (
        <section className={"agent-response-block " + block.type} key={block.type + index}>
          {block.title && !legacyBlockTitles.has(block.title) && <strong>{block.title}</strong>}
          {block.text && <AgentMarkdown content={block.text} />}
          {block.type === "agent_activity" && Array.isArray(block.record?.agents) && (
            <div className="agent-activity-list" aria-label="Team agent activity">
              {(block.record.agents as Array<Record<string, unknown>>).map((entry, entryIndex) => (
                <article key={String(entry.membership_id ?? entryIndex)} className={"agent-activity-item " + String(entry.state ?? "on_track")}>
                  <div className="agent-activity-avatar">{String(entry.employee_name ?? "A").slice(0, 1)}</div>
                  <div><strong>{String(entry.employee_name ?? "Team agent")}</strong><small>{String(entry.role ?? "").replaceAll("_", " ")}</small><p>{String(entry.summary ?? "")}</p></div>
                  <span>{String(entry.state ?? "on track").replaceAll("_", " ")}</span>
                </article>
              ))}
            </div>
          )}
          {!!block.items?.length && <ul>{block.items.map((item) => <li key={item}>{item}</li>)}</ul>}
          {!!block.columns?.length && (
            <div className="agent-markdown-table-wrap">
              <table>
                <thead><tr>{block.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
                <tbody>{(block.rows ?? []).map((row, rowIndex) => <tr key={rowIndex}>{block.columns!.map((_, cellIndex) => <td key={cellIndex}>{row[cellIndex] ?? ""}</td>)}</tr>)}</tbody>
              </table>
            </div>
          )}
          {block.record && businessRecordEntries(block.record).length > 0 && <dl className="agent-record-card">
            {businessRecordEntries(block.record).map(([key, value]) => (
              <div key={key}><dt>{businessRecordLabels[key]}</dt><dd>{String(value).replaceAll("_", " ")}</dd></div>
            ))}
          </dl>}
          {!!block.attachments?.length && <div className="agent-block-attachments">
            {block.attachments.map((attachment, attachmentIndex) => <span key={String(attachment.document_id ?? attachmentIndex)}>{String(attachment.filename ?? attachment.document_id)}</span>)}
          </div>}
          {(block.type === "clarification" || block.type === "missing_information") && (
            <div className="agent-clarification-options">
              {block.attachments?.map((attachment, attachmentIndex) => {
                const choices = Array.isArray(attachment.candidates) ? attachment.candidates as Array<Record<string, unknown>> : [];
                if (!choices.length) return null;
                const filename = String(attachment.filename ?? `File ${attachmentIndex + 1}`);
                return <div className="agent-clarification-group" key={String(attachment.document_id ?? attachmentIndex)}>
                  <span>{filename}</span>
                  <div className="agent-clarification-choices">{choices.slice(0, 5).map((choice, choiceIndex) => {
                    const label = clarificationChoiceLabel(choice);
                    return <button type="button" key={`${label}-${choiceIndex}`} onClick={() => onAction?.({ id: "answer_clarification", label, prompt: clarificationPrompt("supplier", choice, filename) })}>{label}</button>;
                  })}</div>
                </div>;
              })}
              {!block.attachments?.some((attachment) => Array.isArray(attachment.candidates) && attachment.candidates.length > 0) && block.fields?.map((field, fieldIndex) => {
                const choices = Array.isArray(field.choices) ? field.choices as Array<Record<string, unknown>> : [];
                if (!choices.length) return null;
                const fieldName = String(field.name ?? "selection");
                return <div className="agent-clarification-group" key={`${fieldName}-${fieldIndex}`}>
                  <span>Choose {fieldName.replaceAll("_", " ")}</span>
                  <div className="agent-clarification-choices">{choices.slice(0, 5).map((choice, choiceIndex) => {
                    const label = clarificationChoiceLabel(choice);
                    return <button type="button" key={`${label}-${choiceIndex}`} onClick={() => onAction?.({ id: "answer_clarification", label, prompt: clarificationPrompt(fieldName, choice) })}>{label}</button>;
                  })}</div>
                </div>;
              })}
            </div>
          )}
          {(() => {
            const proposalId = String(block.record?.proposal_id ?? block.actions?.find((action) => action.proposal_id)?.proposal_id ?? "");
            const decision = proposalId ? decidedProposals[proposalId] : undefined;
            if (decision) return <div className={`agent-proposal-decision ${decision}`}>{decision === "confirmed" ? "Confirmed" : "Rejected"}</div>;
            if (!block.actions?.length && !proposalId) return null;
            return <div className="agent-block-actions">
              {(block.actions ?? []).map((action) => {
                const normalized = { ...action, proposal_id: action.proposal_id ?? (proposalId || undefined) };
                return action.href
                  ? <Link href={action.href} key={action.id}>{action.label}</Link>
                  : <button type="button" key={action.id} onClick={() => onAction?.(normalized)}>{action.label}</button>;
              })}
              {proposalId && !(block.actions ?? []).some((action) => action.id === "reject_proposal") && <button type="button" className="danger" onClick={() => onAction?.({ id: "reject_proposal", label: "Reject", proposal_id: proposalId, requires_rationale: true })}>Reject</button>}
            </div>;
          })()}
        </section>
      ))}
    </div>
  );
}

export function AgentConversation({ messages, busy = false, onAction, allowedSuggestions = [], decidedProposals = {} }: { messages: AgentMessage[]; busy?: boolean; onAction?: (action: AgentBlockAction) => void; allowedSuggestions?: string[]; decidedProposals?: Record<string, "confirmed" | "rejected"> }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages, busy]);

  return (
    <div className="agent-conversation" aria-live="polite" aria-relevant="additions">
      {!messages.length && (
        <div className="agent-conversation-empty">
          <Sparkles size={18} aria-hidden="true" />
          <strong>Hi! I’m your work agent.</strong>
          <p>Ask naturally, or start with one of these.</p>
          <div className="agent-empty-prompts">
            {allowedSuggestions.filter((id) => suggestedActionCopy[id]).slice(0, 4).map((id) => <button type="button" key={id} onClick={() => onAction?.({ id, label: suggestedActionCopy[id].prompt })}>{suggestedActionCopy[id].label}</button>)}
          </div>
        </div>
      )}
      {messages.map((message) => (
        <article className={"agent-message " + message.message_type} key={message.id}>
          <span>{messageLabel(message.message_type)}</span>
          {message.content_format === "blocks" && message.content_blocks?.length
            ? <AgentBlocks message={message} onAction={onAction} decidedProposals={decidedProposals} />
            : <AgentMarkdown content={message.content} />}
          {!!message.attachments?.length && (
            <div className="agent-citations" aria-label="Attached files">
              {message.attachments.map((attachment) => (
                <span key={attachment.id}>
                  {attachment.filename} · {attachment.status.replaceAll("_", " ")}
                </span>
              ))}
            </div>
          )}
          {message.citations?.length > 0 && (
            <div className="agent-citations" aria-label="Sources">
              {message.citations.map((citation) => (
                <Link href={citation.href} key={message.id + "-" + citation.id}>{citation.label}</Link>
              ))}
            </div>
          )}
        </article>
      ))}
      {busy && <div className="agent-thinking"><LoaderCircle size={15} /> Preparing a scoped response</div>}
      <div ref={endRef} />
    </div>
  );
}

export function AgentDrawer({ overview, hideLauncher = false }: { overview: WorkspaceOverview; hideLauncher?: boolean }) {
  const [open, setOpen] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [home, setHome] = useState<AgentHome | null>(null);
  const [threads, setThreads] = useState<AgentThread[]>([]);
  const [threadId, setThreadId] = useState("");
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [uploadState, setUploadState] = useState("");
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [decidedProposals, setDecidedProposals] = useState<Record<string, "confirmed" | "rejected">>({});
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const requestedWorkItemId = typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("work_item") ?? "";
  const selectedWorkItem = useMemo(
    () => overview.work_items.find((item) => item.id === requestedWorkItemId),
    [overview.work_items, requestedWorkItemId],
  );
  const storageKey = "gg_agent_thread_" + overview.role;

  async function loadThread(id: string) {
    setLoading(true);
    setError("");
    try {
      const detail = await apiFetch<ThreadDetail>("/agent/threads/" + encodeURIComponent(id));
      setThreadId(detail.thread.id);
      setMessages(detail.messages);
      window.localStorage.setItem(storageKey, detail.thread.id);
      setShowHistory(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Conversation could not be loaded");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    let active = true;
    async function loadAgent() {
      try {
        const [agentHome, agentThreads] = await Promise.all([
          apiFetch<AgentHome>("/agent/home"),
          apiFetch<AgentThread[]>("/agent/threads"),
        ]);
        if (!active) return;
        setHome(agentHome);
        setThreads(agentThreads);
        const contextual = requestedWorkItemId
          ? agentThreads.find((thread) => String(thread.work_item_id ?? "") === requestedWorkItemId)
          : undefined;
        const rememberedId = window.localStorage.getItem(storageKey) ?? "";
        const remembered = agentThreads.find((thread) => thread.id === rememberedId);
        const initial = contextual ?? remembered ?? agentThreads[0];
        if (initial) await loadThread(initial.id);
        else setLoading(false);
        if (requestedWorkItemId) setOpen(true);
      } catch (caught) {
        if (!active) return;
        setError(caught instanceof Error ? caught.message : "Role agent could not be loaded");
        setLoading(false);
      }
    }
    void loadAgent();
    return () => { active = false; };
  }, [requestedWorkItemId, storageKey]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    window.setTimeout(() => composerRef.current?.focus(), 80);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  useEffect(() => {
    const openAgent = () => setOpen(true);
    window.addEventListener("genuinegigs:open-agent", openAgent);
    return () => window.removeEventListener("genuinegigs:open-agent", openAgent);
  }, []);

  const hasProcessingAttachments = messages.some((message) =>
    (message.attachments ?? []).some((attachment) =>
      ["uploading", "queued", "extracting", "retrying"].includes(attachment.status),
    ),
  );

  useEffect(() => {
    if (!open || !threadId || !hasProcessingAttachments) return;
    let active = true;
    const refresh = async () => {
      try {
        const detail = await apiFetch<ThreadDetail>("/agent/threads/" + encodeURIComponent(threadId));
        if (active) setMessages(detail.messages);
      } catch {
        // Keep the last grounded state visible. The next bounded poll retries;
        // a user-triggered refresh remains available if connectivity is lost.
      }
    };
    const timer = window.setInterval(() => void refresh(), 2000);
    void refresh();
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [open, threadId, hasProcessingAttachments]);

  function newConversation() {
    setThreadId("");
    setMessages([]);
    setQuestion("");
    setError("");
    setShowHistory(false);
    window.localStorage.removeItem(storageKey);
    window.setTimeout(() => composerRef.current?.focus(), 0);
  }

  async function deleteConversation(id: string) {
    const selected = threads.find((thread) => thread.id === id);
    if (!window.confirm(`Delete “${selected?.title || "this conversation"}”? This removes it from your chat history.`)) return;
    setError("");
    try {
      await mutate(`/agent/threads/${encodeURIComponent(id)}`, csrfToken(), undefined, "DELETE");
      setThreads((current) => current.filter((thread) => thread.id !== id));
      if (threadId === id) newConversation();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Conversation could not be deleted");
    }
  }

  async function submitMessage(content: string, requestedCapability?: string) {
    if (!content || busy || !home?.enabled) return;
    setBusy(true);
    setError("");
    const optimistic: AgentMessage = {
      id: "pending-" + Date.now(),
      message_type: "user",
      content,
      citations: [],
    };
    setMessages((current) => [...current, optimistic]);
    setQuestion("");
    try {
      const attachmentIds: string[] = [];
      const pageContext = selectedPageContext();
      for (const file of files) {
        setUploadState(`Uploading ${file.name}`);
        const form = new FormData();
        form.append("file", file);
        const uploadableContextTypes = new Set(["supplier_quote", "rfq", "po_draft", "case"]);
        const linkedType = pageContext?.entity_type ?? selectedWorkItem?.entity_type;
        const linkedId = pageContext?.entity_id ?? selectedWorkItem?.entity_id;
        if (linkedType && linkedId && uploadableContextTypes.has(linkedType)) {
          form.append("linked_entity_type", linkedType);
          form.append("linked_entity_id", linkedId);
        }
        const uploaded = await apiFormFetch<{ document: { id: string } }>("/documents/upload", form, csrfToken());
        attachmentIds.push(uploaded.document.id);
      }
      setUploadState(attachmentIds.length ? "Processing attachments" : "");
      let activeThreadId = threadId;
      if (!activeThreadId) {
        const created = await mutate<AgentThread>(
          "/agent/threads",
          csrfToken(),
          selectedWorkItem
            ? { thread_type: "work_item", title: selectedWorkItem.title, work_item_id: selectedWorkItem.id }
            : { thread_type: "personal", title: content.trim().replace(/\s+/g, " ").slice(0, 80) || "New conversation" },
        );
        activeThreadId = created.id;
        setThreadId(created.id);
        setThreads((current) => [created, ...current]);
      }
      const reply = await mutate<AgentReply>(
        "/agent/threads/" + encodeURIComponent(activeThreadId) + "/messages",
        csrfToken(),
        {
          content, attachment_ids: attachmentIds,
          requested_capability: requestedCapability,
          selected_context: pageContext,
        },
      );
      const persistedAttachmentIds = new Set(
        (reply.attachments ?? []).map((attachment) => attachment.document_id),
      );
      if (attachmentIds.some((id) => !persistedAttachmentIds.has(id))) {
        throw new Error("Your files were uploaded but are not visible in the sent message yet. They remain selected; retry shortly.");
      }
      setSuggestions((reply.allowed_actions ?? []).filter((id) => suggestedActionCopy[id]).slice(0, 4));
      await loadThread(activeThreadId);
      const refreshed = await apiFetch<AgentThread[]>("/agent/threads");
      setThreads(refreshed);
      setFiles([]);
      setUploadState("");
    } catch (caught) {
      setMessages((current) => current.filter((message) => message.id !== optimistic.id));
      setQuestion(content);
      setError(caught instanceof Error ? caught.message : "Agent request failed");
      setUploadState("");
    } finally {
      setBusy(false);
    }
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitMessage(question.trim());
  }

  async function handleAgentAction(action: AgentBlockAction) {
    if (action.id === "answer_clarification") {
      void submitMessage(action.prompt ?? action.label);
      return;
    }
    if (["confirm", "confirm_proposal", "reject", "reject_proposal"].includes(action.id) && action.proposal_id) {
      const rejecting = action.id === "reject" || action.id === "reject_proposal";
      const reason = rejecting ? window.prompt("Why are you rejecting this prepared action?")?.trim() : "";
      if (rejecting && !reason) return;
      setBusy(true); setError("");
      try {
        await mutate(
          `/agent/proposals/${encodeURIComponent(action.proposal_id)}/${rejecting ? "reject" : "confirm"}`,
          csrfToken(), { reason: reason || undefined },
        );
        setDecidedProposals((current) => ({ ...current, [action.proposal_id!]: rejecting ? "rejected" : "confirmed" }));
        const refreshedHome = await apiFetch<AgentHome>("/agent/home");
        setHome(refreshedHome);
        window.dispatchEvent(new CustomEvent("genuinegigs:refresh"));
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "The proposal decision could not be recorded");
      } finally { setBusy(false); }
      return;
    }
    if (action.id === "reject") {
      setQuestion("");
      setError("The pending request was left unconfirmed.");
      return;
    }
    const actionPrompts: Record<string, string> = {
      confirm: "Confirm the pending request.",
      create_material_master_request: "Prepare a new material request from the saved draft.",
      list_my_tasks: "Show my assigned work.",
      list_team_tasks: "Show the team work I can see.",
      summarize_team_status: "Ask my team agents for their current progress.",
      list_approved_materials: "Show approved material masters.",
    };
    void submitMessage(actionPrompts[action.id] ?? action.label, action.id);
  }

  return (
    <>
      {!hideLauncher && <button
        className={"agent-launcher " + (home?.enabled ? "online" : "offline")}
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open role agent"
        aria-expanded={open}
        title="Open role agent"
      >
        <span className="agent-launcher-icon" aria-hidden="true"><Sparkles size={18} /></span>
        <span className="agent-launcher-copy">
          <strong>Ask GenuineGigs</strong>
          <small><i className={home?.enabled ? "online" : "offline"} /> {home?.enabled ? "Assistant online" : "Assistant unavailable"}</small>
        </span>
        <span className="agent-launcher-arrow" aria-hidden="true">↗</span>
      </button>}

      {open && <div className="agent-drawer-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
        <aside className="agent-drawer" role="region" aria-labelledby="agent-drawer-title">
          <header className="agent-drawer-header">
            <div className="agent-drawer-identity">
              <div className="agent-drawer-avatar"><Bot size={20} /></div>
              <div>
                <strong id="agent-drawer-title">GenuineGigs Assistant <em>Beta</em></strong>
                <span className="agent-drawer-presence"><i className={home?.enabled ? "online" : "offline"} /> {home?.enabled ? "Online" : "Unavailable"}<b>·</b>{home ? roleLabel(home.profile.role) : "Loading workspace"}</span>
              </div>
            </div>
            <div className="agent-drawer-actions">
              <button type="button" onClick={() => setShowHistory((current) => !current)} title="Conversation history" aria-label="Conversation history" aria-pressed={showHistory}><History size={18} /></button>
              <button type="button" onClick={newConversation} title="New conversation" aria-label="New conversation"><MessageSquarePlus size={18} /></button>
              <button type="button" onClick={() => setOpen(false)} title="Close role agent" aria-label="Close role agent"><PanelRightClose size={19} /></button>
            </div>
          </header>

          {selectedWorkItem && (
            <div className="agent-drawer-context">
              <span>Current task</span>
              <strong>{selectedWorkItem.plain_language_goal}</strong>
              <Link href={selectedWorkItem.href}>Open record</Link>
            </div>
          )}

          {showHistory ? (
            <div className="agent-thread-history">
              <div className="agent-thread-history-head"><strong>Conversations</strong><span>{threads.length}</span></div>
              {threads.map((thread) => (
                <div className="agent-thread-history-row" key={thread.id}>
                  <button className={`agent-thread-open ${thread.id === threadId ? "active" : ""}`} type="button" onClick={() => void loadThread(thread.id)}>
                    <span>{thread.title || "Untitled conversation"}</span>
                    <small>{String(thread.thread_type).replaceAll("_", " ")} {formatThreadDate(thread.updated_at)}</small>
                  </button>
                  <button className="agent-thread-delete" type="button" title={`Delete ${thread.title || "conversation"}`} aria-label={`Delete ${thread.title || "conversation"}`} onClick={() => void deleteConversation(thread.id)}><Trash2 size={15} /></button>
                </div>
              ))}
              {!threads.length && <p>No saved conversations yet.</p>}
            </div>
          ) : loading ? (
            <div className="agent-drawer-loading"><LoaderCircle size={20} /> Loading conversation</div>
          ) : (
            <AgentConversation messages={messages} busy={busy} onAction={handleAgentAction} allowedSuggestions={home?.profile.allowed_actions ?? []} decidedProposals={decidedProposals} />
          )}

          <form className="agent-drawer-composer" onSubmit={sendMessage}>
            {error && <div className="agent-inline-error">{error}</div>}
            {!!suggestions.length && <div className="agent-suggestion-chips" aria-label="Suggested actions">
              {suggestions.map((id) => <button type="button" key={id} onClick={() => void submitMessage(suggestedActionCopy[id].prompt)}>{suggestedActionCopy[id].label}</button>)}
            </div>}
            {!!files.length && <div className="agent-selected-files" aria-label="Selected attachments">
              {files.map((file, index) => <span key={`${file.name}-${file.lastModified}`}>
                {file.name}
                <button type="button" aria-label={`Remove ${file.name}`} onClick={() => setFiles((current) => current.filter((_, currentIndex) => currentIndex !== index))}><Trash2 size={13} /></button>
              </span>)}
            </div>}
            {uploadState && <small className="agent-upload-state">{uploadState}</small>}
            <div>
              <label className="sr-only" htmlFor="agent-drawer-question">Message my role agent</label>
              <textarea
                ref={composerRef}
                id="agent-drawer-question"
                rows={3}
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
                placeholder={home?.enabled ? "Ask your plant assistant to prepare, explain, delegate, or follow up..." : "Assistant unavailable; manual workflows remain available"}
                disabled={!home?.enabled || busy}
              />
              <input
                ref={fileInputRef}
                id="agent-quotation-attachments"
                aria-label="Quotation attachments"
                className="sr-only"
                type="file"
                multiple
                accept=".pdf,.png,.jpg,.jpeg,.xlsx,application/pdf,image/png,image/jpeg,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={(event) => {
                  const selected = Array.from(event.target.files ?? []);
                  setFiles((current) => [...current, ...selected].slice(0, 20));
                  event.target.value = "";
                }}
              />
              <button type="button" className="agent-attach-button" disabled={busy} onClick={() => fileInputRef.current?.click()} title="Attach quotations" aria-label="Attach quotations"><Paperclip size={17} /></button>
              <button type="submit" disabled={!home?.enabled || busy || !question.trim()} title="Send message" aria-label="Send message">
                {busy ? <LoaderCircle size={18} /> : <Send size={18} />}
              </button>
            </div>
            <small>Enter to send, Shift+Enter for a new line</small>
          </form>
          <button className="agent-drawer-mobile-close" type="button" onClick={() => setOpen(false)}><X size={16} /> Close</button>
        </aside>
      </div>}
    </>
  );
}
