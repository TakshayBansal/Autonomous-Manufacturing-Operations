"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { apiBlob, apiFetch, apiFormFetch, apiUrl, mutate, type User, type WorkspaceData } from "@/lib/api";
import { useRouteSelection } from "@/lib/useRouteSelection";

export type WorkflowPostAction = (path: string, body?: unknown, successMessage?: string, version?: number | string | null, method?: string) => Promise<void>;

type CommonProps = { workspaceData: WorkspaceData | null; postAction: WorkflowPostAction; busy: boolean };
type Row = Record<string, unknown>;

function text(value: unknown) { return value === null || value === undefined ? "" : String(value); }
function id(row: Row | undefined) { return text(row?.id); }
function version(row: Row | undefined) { return typeof row?.version === "number" ? row.version : undefined; }
function csrfToken() { return window.localStorage.getItem("gg_csrf") ?? ""; }

async function openArtifact(record: Row) {
  const target = text(record.download_url);
  if (!target) return;
  const download = await apiFetch<{ url: string }>(target);
  const anchor = document.createElement("a");
  anchor.href = apiUrl(download.url);
  anchor.target = "_blank";
  anchor.rel = "noreferrer";
  anchor.click();
}

export function RequirementCreatePanel({ workspaceData, postAction, busy }: CommonProps) {
  const items = workspaceData?.items ?? [];
  const assignees = workspaceData?.assignees ?? [];
  const draftLoaded = useRef(false);
  const [title, setTitle] = useState("");
  const [reason, setReason] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [materialSearch, setMaterialSearch] = useState("");
  const filteredItems = useMemo(() => {
    const query = materialSearch.trim().toLowerCase();
    if (!query) return items;
    return items.filter((item) => `${text(item.code)} ${text(item.name)}`.toLowerCase().includes(query));
  }, [items, materialSearch]);
  const [lines, setLines] = useState([{ key: crypto.randomUUID(), item_id: text(items[0]?.id), quantity: "1", need_by_date: "", uom: text(items[0]?.uom_id || "EA"), specification: "", inspection_required: true }]);
  useEffect(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem("gg.requirement-draft.v1") || "null");
      if (saved && typeof saved === "object") {
        setTitle(text(saved.title)); setReason(text(saved.reason)); setAssigneeId(text(saved.assigneeId));
        if (Array.isArray(saved.lines) && saved.lines.length) {
          setLines(saved.lines.map((line: Row) => ({
            key: crypto.randomUUID(), item_id: text(line.item_id), quantity: text(line.quantity || "1"),
            need_by_date: text(line.need_by_date), uom: text(line.uom || "EA"),
            specification: text(line.specification), inspection_required: line.inspection_required !== false,
          })));
        }
      }
    } catch { window.localStorage.removeItem("gg.requirement-draft.v1"); }
    draftLoaded.current = true;
  }, []);
  useEffect(() => {
    if (!draftLoaded.current) return;
    window.localStorage.setItem("gg.requirement-draft.v1", JSON.stringify({ title, reason, assigneeId, lines }));
  }, [title, reason, assigneeId, lines]);
  useEffect(() => {
    if (!items.length) return;
    setLines((current) => current.map((line) => items.some((item) => id(item) === line.item_id) ? line : { ...line, item_id: text(items[0].id), uom: text(items[0].uom_id || "EA") }));
  }, [items]);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void postAction("/procurement/requirements", {
      title: text(form.get("title")), reason: text(form.get("reason")), source: "manual",
      assignee_membership_id: text(form.get('assignee_membership_id')) || undefined,
      lines: lines.map((line) => ({ ...line, quantity: Number(line.quantity), key: undefined })),
    }, "Multi-line material requirement created.");
  }
  function requestMaterial(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void postAction("/procurement/material-requests", {
      item_code: form.get("item_code"), description: form.get("description"),
      uom: form.get("uom"), specification: form.get("specification"),
      reason: form.get("reason"),
    }, "New material request sent for approval. Your purchase requirement remains separate until approval.");
  }
  return <section className="action-panel workflow-action-panel requirement-create-panel">
    <div className="panel-head compact-head"><div><div className="section-kicker">Material request</div><h3>Create new requirement</h3></div><button type="button" className="small-action" onClick={() => setLines((current) => [...current, { key: crypto.randomUUID(), item_id: text(items[0]?.id), quantity: "1", need_by_date: "", uom: text(items[0]?.uom_id || "EA"), specification: "", inspection_required: true }])}>+ Add line</button></div>
    <form className="ops-form requirement-form" onSubmit={submit}>
      <label className="span-2 req-reason">Business reason<textarea name="reason" value={reason} onChange={(event) => setReason(event.target.value)} required /></label>
      <label className="span-2 req-title">Requirement title<input name="title" value={title} onChange={(event) => setTitle(event.target.value)} required /></label>
      <label className='span-2 req-assignee'>Assign Purchase Executive<select name='assignee_membership_id' value={assigneeId} onChange={(event) => setAssigneeId(event.target.value)} required={assignees.length > 1}><option value=''>{assignees.length === 1 ? `Automatic · ${text(assignees[0].name)}` : 'Select assignee'}</option>{assignees.map((assignee) => <option key={text(assignee.membership_id)} value={text(assignee.membership_id)}>{text(assignee.name)}</option>)}</select></label>
      <label className="span-2 req-search">Find approved material<input type="search" value={materialSearch} onChange={(event) => setMaterialSearch(event.target.value)} placeholder="Search by material name or code" /></label>
      <div className="requirement-lines-heading span-4"><strong>Line items</strong><span>{lines.length} {lines.length === 1 ? "item" : "items"}</span></div>
      {lines.map((line, index) => <div className="form-line requirement-line span-4" key={line.key}>
        <label>Material<select value={line.item_id} onChange={(event) => { const chosen = items.find((item) => text(item.id) === event.target.value); setLines((current) => current.map((item) => item.key === line.key ? { ...item, item_id: event.target.value, uom: text(chosen?.uom_id || item.uom) } : item)); }}>{items.filter((item) => text(item.id) === line.item_id || filteredItems.includes(item)).map((item) => <option key={text(item.id)} value={text(item.id)}>{text(item.code)} · {text(item.name)}</option>)}</select></label>
        <label>Quantity<input type="number" min="0.01" step="0.01" value={line.quantity} onChange={(event) => setLines((current) => current.map((item) => item.key === line.key ? { ...item, quantity: event.target.value } : item))} required /></label>
        <label>UOM<input value={line.uom} onChange={(event) => setLines((current) => current.map((item) => item.key === line.key ? { ...item, uom: event.target.value } : item))} required /></label>
        <label>Need by<input type="date" value={line.need_by_date} onChange={(event) => setLines((current) => current.map((item) => item.key === line.key ? { ...item, need_by_date: event.target.value } : item))} required /></label>
        <label className="span-2">Specification<input value={line.specification} onChange={(event) => setLines((current) => current.map((item) => item.key === line.key ? { ...item, specification: event.target.value } : item))} /></label>
        <label className="checkbox-label"><input type="checkbox" checked={line.inspection_required} onChange={(event) => setLines((current) => current.map((item) => item.key === line.key ? { ...item, inspection_required: event.target.checked } : item))} /> Inspection required</label>
        {lines.length > 1 && <button type="button" className="small-action danger" onClick={() => setLines((current) => current.filter((item) => item.key !== line.key))}>Remove</button>}
        <span className="line-index">Line {index + 1}</span>
      </div>)}
      {!items.length && <p className='form-note span-4'>Material not in the approved master? <a href='/workspace/setup'>Request or configure it in Workspace setup</a>. A material-master request is separate from a purchase requirement.</p>}
      <button className="action-button" disabled={busy || !items.length || !assignees.length}>Create requirement</button><button type="button" className="small-action" onClick={() => { setTitle(""); setReason(""); setAssigneeId(""); setLines([{ key: crypto.randomUUID(), item_id: text(items[0]?.id), quantity: "1", need_by_date: "", uom: text(items[0]?.uom_id || "EA"), specification: "", inspection_required: true }]); window.localStorage.removeItem("gg.requirement-draft.v1"); }}>Clear draft</button>
    </form>
    <details className="inline-workflow">
      <summary>Material not listed? Request a new material</summary>
      <form className="ops-form" onSubmit={requestMaterial}>
        <label>Proposed code<input name="item_code" required /></label>
        <label>Material name<input name="description" required /></label>
        <label>Unit of measure<input name="uom" required defaultValue="KG" /></label>
        <label className="span-2">Specification<textarea name="specification" /></label>
        <label className="span-2">Business reason<textarea name="reason" required /></label>
        <button className="action-button" disabled={busy}>Request material approval</button>
      </form>
    </details>
  </section>;
}

export function RequirementListPanel({ workspaceData, postAction, busy, user }: CommonProps & { user: User }) {
  const requirements = workspaceData?.requirements ?? [];
  const materials = workspaceData?.items ?? [];
  const [selectedId, selectRequirement] = useRouteSelection("requirement");
  const selected = requirements.find((row) => id(row) === selectedId) ?? requirements[0];
  useEffect(() => { if (!selectedId && selected) selectRequirement(id(selected)); }, [selectedId, selected, selectRequirement]);
  const materialName = (row: Row) => {
    const material = materials.find((item) => id(item) === text(row.item_id));
    return material ? `${text(material.code)} · ${text(material.name)}` : "Material details unavailable";
  };
  const statusLabel = (value: unknown) => text(value || "draft").replaceAll("_", " ");
  return <section className="requirement-workbench">
    <div className="panel-head compact-head"><div><div className="section-kicker">Purchase demand</div><h3>Requirements</h3><p>Select a requirement to continue its procurement journey.</p></div><span className="record-count">{requirements.length} total</span></div>
    {!requirements.length ? <div className="work-empty">No requirements yet. Create the first one above.</div> : <div className="requirement-workbench-grid">
      <div className="requirement-list" role="list" aria-label="Purchase requirements">{requirements.map((row) => <button type="button" role="listitem" className={`requirement-list-item ${id(row) === id(selected) ? "selected" : ""}`} key={id(row)} onClick={() => selectRequirement(id(row))}>
        <span><strong>{text(row.business_number || "Requirement")}</strong><small>{statusLabel(row.status)}</small></span><b>{materialName(row)}</b><span className="requirement-list-facts"><span>{text(row.quantity)} {text(row.uom)}</span><span>Need by {text(row.need_by_date)}</span></span>
      </button>)}</div>
      {selected && <article className="requirement-detail-card">
        <div className="record-card-heading"><div><small>Selected requirement</small><h4>{text(selected.business_number || "Requirement")}</h4></div><span className={`business-status ${text(selected.status)}`}>{statusLabel(selected.status)}</span></div>
        <h5>{materialName(selected)}</h5><dl className="business-facts"><div><dt>Quantity</dt><dd>{text(selected.quantity)} {text(selected.uom)}</dd></div><div><dt>Need by</dt><dd>{text(selected.need_by_date)}</dd></div><div className="wide"><dt>Business reason</dt><dd>{text(selected.reason) || "No reason recorded"}</dd></div></dl>
        <div className="record-next-step"><div><small>Next step</small><strong>{text(selected.status) === "closed" ? "Procurement lifecycle reconciled" : ["draft", "approved"].includes(text(selected.status)) ? "Choose suppliers and prepare the RFQ" : "Continue or reconcile this procurement lifecycle"}</strong></div>{text(selected.status) !== "closed" && <div className="button-row"><a className="secondary-button" href={`/rfq-builder?requirement=${encodeURIComponent(id(selected))}`}>Open supplier request</a>{["plant_manager", "admin"].includes(user.role) && <button className="action-button" disabled={busy} onClick={() => { if (window.confirm("Close only if delivery, quality, finance, and external payment evidence all reconcile?")) void postAction(`/procurement/requirements/${id(selected)}/close`, undefined, "Procurement lifecycle closed after full reconciliation.", version(selected)); }}>Close reconciled lifecycle</button>}</div>}</div>
      </article>}
    </div>}
  </section>;
}

export function MasterDataPanel({ workspaceData, postAction, busy, user }: CommonProps & { user: User }) {
  const items = workspaceData?.items ?? [];
  const requests = workspaceData?.material_requests ?? [];
  const pending = requests.filter((row) => text(row.status) === "pending");
  const suppliers = workspaceData?.suppliers ?? [];
  const supplierCapabilities = workspaceData?.supplier_item_capabilities ?? [];
  const complianceRequirements = workspaceData?.compliance_requirements ?? [];
  const certificates = workspaceData?.supplier_certificates ?? [];
  const pendingCertificates = certificates.filter((row) => text(row.status) === "pending_review");
  const correctiveActions = workspaceData?.supplier_corrective_actions ?? [];
  const openCorrectiveActions = correctiveActions.filter((row) => !["closed", "cancelled"].includes(text(row.status)));
  const knowledge = workspaceData?.knowledge ?? [];
  const draftKnowledge = knowledge.filter((row) => text(row.approval_state) === "draft");
  const admin = user.role === 'admin' || Boolean(user.capabilities?.includes('workspace.manage_master_data'));
  const canAssignSuppliers = admin || user.role === 'purchase_executive';

  function requestMaterial(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void postAction("/procurement/material-requests", {
      item_code: form.get("item_code"), description: form.get("description"),
      uom: form.get("uom"), specification: form.get("specification"),
      reason: form.get("reason"),
    }, "Material request sent for governed approval.");
  }

  function decideMaterial(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const requestId = text(form.get("request_id"));
    const decision = text(form.get("decision"));
    if (!window.confirm(`${decision === "approve" ? "Approve" : "Reject"} this material master request?`)) return;
    void postAction(`/procurement/material-requests/${requestId}/decision`, {
      decision, reason: form.get("reason"),
    }, "Material master decision recorded.");
  }

  function createSupplier(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void postAction("/procurement/suppliers", {
      name: form.get("name"), vendor_id: form.get("vendor_id"),
      contact_name: form.get("contact_name"), email: form.get("email"),
      phone: form.get("phone"), site_name: form.get("site_name"),
      currency: form.get("currency"), payment_terms: form.get("payment_terms"),
      item_ids: form.getAll("item_ids").map(String),
    }, "Approved supplier added to the workspace.");
  }

  function assignSuppliers(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const itemId = text(form.get("item_id"));
    void postAction(`/procurement/materials/${encodeURIComponent(itemId)}/suppliers`, {
      item_id: itemId,
      supplier_ids: form.getAll("supplier_ids").map(String),
      notes: form.get("notes"),
    }, "Approved supplier capabilities assigned to the material.");
  }

  function createComplianceRequirement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    void postAction("/procurement/supplier-compliance/requirements", {
      certificate_type: form.get("certificate_type"), description: form.get("description"),
      item_id: text(form.get("item_id")) || null, mandatory: true,
    }, "Supplier compliance requirement added. Supplier eligibility will be recalculated from verified evidence.");
  }

  function submitCertificate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    void postAction("/procurement/supplier-certificates", {
      supplier_id: form.get("supplier_id"), certificate_type: form.get("certificate_type"),
      certificate_number: form.get("certificate_number"), expires_on: form.get("expires_on"),
      valid_from: form.get("valid_from"), document_id: text(form.get("document_id")) || null,
    }, "Supplier certificate submitted for evidence review.");
  }

  function decideCertificate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const certificateId = text(form.get("certificate_id")); const decision = text(form.get("decision"));
    if (!window.confirm(`${decision === "verify" ? "Verify" : "Reject"} this supplier certificate evidence?`)) return;
    void postAction(`/procurement/supplier-certificates/${certificateId}/decision`, {
      decision, notes: form.get("notes"),
    }, "Supplier certificate decision recorded.", version(pendingCertificates.find((row) => id(row) === certificateId)));
  }

  function openCorrectiveAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    void postAction("/procurement/supplier-corrective-actions", {
      supplier_id: form.get("supplier_id"), source_entity_type: form.get("source_entity_type"),
      source_entity_id: form.get("source_entity_id"), problem_statement: form.get("problem_statement"),
      response_due_days: Number(form.get("response_due_days") || 7),
    }, "Supplier corrective action opened and follow-up assigned.");
  }

  function updateCorrectiveAction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const actionId = text(form.get("action_id")); const status = text(form.get("status"));
    const evidence = text(form.get("evidence"));
    if (status === "closed" && !window.confirm("Close this corrective action using the recorded effectiveness evidence?")) return;
    void postAction(`/procurement/supplier-corrective-actions/${actionId}/status`, {
      status, root_cause: form.get("root_cause"), corrective_action: form.get("corrective_action"),
      preventive_action: form.get("preventive_action"),
      effectiveness_evidence: evidence ? [{ summary: evidence }] : [],
    }, "Corrective-action status updated.", version(correctiveActions.find((row) => id(row) === actionId)));
  }

  function createKnowledge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const roles = text(form.get("role_acl")).split(",").map((value) => value.trim()).filter(Boolean);
    void postAction("/knowledge", {
      title: form.get("title"), source: form.get("source"), content: form.get("content"),
      role_acl: roles, plant_acl: [],
    }, "SOP or policy saved as a draft for approval.");
  }

  function decideKnowledge(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const documentId = text(form.get("document_id")); const decision = text(form.get("decision"));
    if (!window.confirm(`${decision === "approve" ? "Approve" : "Retire"} this knowledge source for role-agent use?`)) return;
    void postAction(`/knowledge/${documentId}/decision`, { decision }, "Knowledge approval state updated.");
  }

  return <section className="action-panel workflow-action-panel">
    <div className="panel-head compact-head"><div><div className="section-kicker">Approved master data</div><h3>Materials and suppliers</h3></div><span className="record-count">{items.length} materials</span></div>
    <details className="inline-workflow" open={!items.length}>
      <summary>Request a new material</summary>
      <form className="ops-form" onSubmit={requestMaterial}>
        <label>Item code<input name="item_code" required /></label>
        <label>Material name<input name="description" required /></label>
        <label>UOM<input name="uom" required defaultValue="EA" /></label>
        <label className="span-2">Specification<textarea name="specification" /></label>
        <label className="span-2">Business reason<textarea name="reason" required /></label>
        <button className="action-button" disabled={busy}>Request material</button>
      </form>
    </details>
    {admin && <details className="inline-workflow" open={pending.length > 0}>
      <summary>Review material requests ({pending.length})</summary>
      <form className="ops-form" onSubmit={decideMaterial}>
        <label>Pending request<select name="request_id" required><option value="">Select request</option>{pending.map((row) => <option key={id(row)} value={id(row)}>{text(row.requested_code)} / {text(row.requested_name)}</option>)}</select></label>
        <label>Decision<select name="decision"><option value="approve">Approve</option><option value="reject">Reject</option></select></label>
        <label className="span-2">Decision rationale<textarea name="reason" required /></label>
        <button className="action-button" disabled={busy || !pending.length}>Record decision</button>
      </form>
    </details>}
    {admin && <details className="inline-workflow">
      <summary>Add approved supplier</summary>
      <form className="ops-form" onSubmit={createSupplier}>
        <label>Supplier name<input name="name" required /></label>
        <label>ERP vendor ID<input name="vendor_id" required /></label>
        <label>Contact name<input name="contact_name" required /></label>
        <label>Email<input name="email" type="email" required /></label>
        <label>Phone<input name="phone" /></label>
        <label>Site name<input name="site_name" defaultValue="Primary site" required /></label>
        <label>Currency<input name="currency" defaultValue="INR" required /></label>
        <label>Payment terms<input name="payment_terms" defaultValue="30 days" required /></label>
        <label className="span-2">Approved materials<select name="item_ids" multiple required>{items.map((row) => <option key={id(row)} value={id(row)}>{text(row.code)} / {text(row.name)}</option>)}</select></label>
        <button className="action-button" disabled={busy || !items.length}>Create supplier</button>
      </form>
    </details>}
    {canAssignSuppliers && <details className="inline-workflow" open={items.some((item) => !supplierCapabilities.some((capability) => text(capability.item_id) === id(item) && capability.approved === true))}>
      <summary>Assign suppliers to a material</summary>
      <p className="form-note">Choose the material and every supplier approved to quote it. Existing assignments are retained, so this action is safe to repeat.</p>
      <form className="ops-form" onSubmit={assignSuppliers}>
        <label>Material<select name="item_id" required><option value="">Select material</option>{items.map((row) => {
          const count = supplierCapabilities.filter((capability) => text(capability.item_id) === id(row) && capability.approved === true).length;
          return <option key={id(row)} value={id(row)}>{text(row.code)} / {text(row.name)} · {count} approved</option>;
        })}</select></label>
        <label className="span-2">Approved suppliers<select name="supplier_ids" multiple required size={Math.min(6, Math.max(3, suppliers.length))}>{suppliers.map((row) => <option key={id(row)} value={id(row)}>{text(row.name)} · {text(row.status)}</option>)}</select><small>Use Ctrl/Command to select multiple suppliers.</small></label>
        <label className="span-2">Approval note<textarea name="notes" defaultValue="Approved for this material" required /></label>
        <button className="action-button" disabled={busy || !items.length || !suppliers.length}>Assign approved suppliers</button>
      </form>
    </details>}
    {admin && <details className="inline-workflow">
      <summary>Supplier corrective actions ({openCorrectiveActions.length} open)</summary>
      <p className="form-note">Link every corrective action to a real inspection, return, or exception. Supplier communication remains a separately approved step.</p>
      <form className="ops-form" onSubmit={openCorrectiveAction}>
        <label>Supplier<select name="supplier_id" required>{suppliers.map((row) => <option key={id(row)} value={id(row)}>{text(row.name)}</option>)}</select></label>
        <label>Evidence type<select name="source_entity_type"><option value="inspection_result">Quality inspection</option><option value="supplier_return">Supplier return</option><option value="case">Exception case</option></select></label>
        <label>Evidence record ID<input name="source_entity_id" required placeholder="Select from the quality or exception workbench" /></label>
        <label>Supplier response due in<input name="response_due_days" type="number" min="1" max="90" defaultValue="7" required /></label>
        <label className="span-2">Problem statement<textarea name="problem_statement" required /></label>
        <button className="action-button" disabled={busy || !suppliers.length}>Open corrective action</button>
      </form>
      <form className="ops-form" onSubmit={updateCorrectiveAction}>
        <label>Open corrective action<select name="action_id" required><option value="">Select action</option>{openCorrectiveActions.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number)} · {text(row.status).replaceAll("_", " ")}</option>)}</select></label>
        <label>Status<select name="status"><option value="awaiting_supplier">Awaiting supplier</option><option value="response_received">Response received</option><option value="effectiveness_review">Effectiveness review</option><option value="closed">Close after verification</option></select></label>
        <label className="span-2">Root cause<textarea name="root_cause" /></label>
        <label className="span-2">Corrective action<textarea name="corrective_action" /></label>
        <label className="span-2">Preventive action<textarea name="preventive_action" /></label>
        <label className="span-2">Effectiveness evidence<textarea name="evidence" placeholder="Required before closure" /></label>
        <button className="action-button" disabled={busy || !openCorrectiveActions.length}>Update corrective action</button>
      </form>
    </details>}
    {admin && <details className="inline-workflow">
      <summary>Approved SOPs and policies ({knowledge.filter((row) => text(row.approval_state) === "approved").length})</summary>
      <p className="form-note">Only approved sources are sent to role agents. Every answer retains a link back to this source.</p>
      <form className="ops-form" onSubmit={createKnowledge}>
        <label>Document title<input name="title" required /></label>
        <label>Source reference<input name="source" required placeholder="Policy owner, controlled URL, or document number" /></label>
        <label className="span-2">Visible to roles<input name="role_acl" placeholder="purchase_manager, purchase_executive (blank means all roles)" /></label>
        <label className="span-2">Approved text content<textarea name="content" minLength={10} required /></label>
        <button className="action-button" disabled={busy}>Save approval draft</button>
      </form>
      <form className="ops-form" onSubmit={decideKnowledge}>
        <label>Draft source<select name="document_id" required><option value="">Select source</option>{draftKnowledge.map((row) => <option key={id(row)} value={id(row)}>{text(row.title)} · {text(row.source)}</option>)}</select></label>
        <label>Decision<select name="decision"><option value="approve">Approve for agents</option><option value="retire">Retire</option></select></label>
        <button className="action-button" disabled={busy || !draftKnowledge.length}>Record decision</button>
      </form>
      <div className="setup-invitations">{knowledge.map((row) => <div className="setup-invitation-row" key={id(row)}><div><strong>{text(row.title)}</strong><span>{text(row.source)} · version {text(row.document_version)}</span></div><span className={`status-pill ${text(row.approval_state) === "approved" ? "good" : "neutral"}`}>{text(row.approval_state)}</span></div>)}</div>
    </details>}
    {admin && <details className="inline-workflow">
      <summary>Configure supplier compliance ({complianceRequirements.length})</summary>
      <form className="ops-form" onSubmit={createComplianceRequirement}>
        <label>Required certificate<input name="certificate_type" placeholder="ISO 9001, GST registration" required /></label>
        <label>Applies to material<select name="item_id"><option value="">All suppliers</option>{items.map((row) => <option key={id(row)} value={id(row)}>{text(row.code)} · {text(row.name)}</option>)}</select></label>
        <label className="span-2">Requirement description<textarea name="description" /></label>
        <button className="action-button" disabled={busy}>Add compliance requirement</button>
      </form>
      <form className="ops-form" onSubmit={submitCertificate}>
        <label>Supplier<select name="supplier_id" required>{suppliers.map((row) => <option key={id(row)} value={id(row)}>{text(row.name)}</option>)}</select></label>
        <label>Certificate type<input name="certificate_type" list="certificate-types" required /><datalist id="certificate-types">{complianceRequirements.map((row) => <option key={id(row)} value={text(row.certificate_type)} />)}</datalist></label>
        <label>Certificate number<input name="certificate_number" /></label>
        <label>Valid from<input name="valid_from" type="date" /></label>
        <label>Expires on<input name="expires_on" type="date" required /></label>
        <label>Evidence document ID<input name="document_id" placeholder="Optional uploaded document" /></label>
        <button className="action-button" disabled={busy || !suppliers.length}>Submit evidence</button>
      </form>
      <form className="ops-form" onSubmit={decideCertificate}>
        <label>Evidence awaiting review<select name="certificate_id" required><option value="">Select certificate</option>{pendingCertificates.map((row) => <option key={id(row)} value={id(row)}>{text(row.certificate_type)} · {text(row.certificate_number || row.business_number)}</option>)}</select></label>
        <label>Decision<select name="decision"><option value="verify">Verify evidence</option><option value="reject">Reject evidence</option></select></label>
        <label className="span-2">Review notes<textarea name="notes" /></label>
        <button className="action-button" disabled={busy || !pendingCertificates.length}>Record evidence decision</button>
      </form>
    </details>}
    {admin && <div className="confirmation-strip">
      <div><strong>Workspace role agents</strong><span>Disabling cancels active runs. Normal workflows remain available.</span></div>
      <button type="button" className="small-action" disabled={busy} onClick={() => {
        if (window.confirm("Enable role agents for this workspace?")) void postAction("/admin/workspace/agent-policy", { enabled: true }, "Role agents enabled.", undefined, "PATCH");
      }}>Enable</button>
      <button type="button" className="small-action danger" disabled={busy} onClick={() => {
        if (window.confirm("Disable role agents and cancel every active run in this workspace?")) void postAction("/admin/workspace/agent-policy", { enabled: false }, "Role agents disabled and active runs cancelled.", undefined, "PATCH");
      }}>Disable</button>
    </div>}
  </section>;
}

export function SelectableRfqPanel({ workspaceData, postAction, busy }: CommonProps) {
  const requirements = workspaceData?.requirements ?? [];
  const rfqs = workspaceData?.rfqs ?? [];
  const suppliers = workspaceData?.suppliers ?? [];
  const [requirementId, setRequirementId] = useRouteSelection("requirement");
  const [rfqId, setRfqId] = useRouteSelection("rfq");
  const selectedRequirement = requirements.find((row) => id(row) === requirementId);
  const selectedRfq = rfqs.find((row) => id(row) === rfqId);
  const [artifactBusy, setArtifactBusy] = useState(false);
  const [artifactError, setArtifactError] = useState("");
  async function previewPdf() {
    if (!rfqId) return;
    setArtifactBusy(true);
    setArtifactError("");
    try {
      const artifact = await mutate<Row>(`/procurement/rfqs/${rfqId}/pdf-preview`, csrfToken(), {});
      await openArtifact(artifact);
    } catch (caught) {
      setArtifactError(caught instanceof Error ? caught.message : "RFQ preview could not be generated");
    } finally {
      setArtifactBusy(false);
    }
  }
  async function downloadFinalPdf() {
    if (!rfqId) return;
    setArtifactBusy(true);
    setArtifactError("");
    try {
      const artifacts = await apiFetch<Row[]>(`/procurement/rfqs/${rfqId}/artifacts`);
      const artifact = artifacts.find((row) => text(row.status) === "final");
      if (!artifact) throw new Error("Publish the RFQ before downloading its final PDF");
      await openArtifact(artifact);
    } catch (caught) {
      setArtifactError(caught instanceof Error ? caught.message : "RFQ PDF could not be downloaded");
    } finally {
      setArtifactBusy(false);
    }
  }
  function update(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const supplierIds = form.getAll("supplier_ids").map(String);
    void postAction(`/procurement/rfqs/${rfqId}`, { deadline: text(form.get("deadline")), supplier_ids: supplierIds }, "RFQ draft updated.", version(selectedRfq), "PATCH");
  }
  useEffect(() => {
    if (!requirementId || rfqId) return;
    const linked = rfqs.find((row) => text(row.requirement_id) === requirementId);
    if (linked) setRfqId(id(linked));
  }, [requirementId, rfqId, rfqs, setRfqId]);
  const status = text(selectedRfq?.status);
  const supplierCount = Array.isArray(selectedRfq?.supplier_ids) ? selectedRfq.supplier_ids.length : 0;
  return <section className="action-panel workflow-action-panel">
    <div className="panel-head compact-head"><div><div className="section-kicker">Supplier enquiry</div><h3>Prepare supplier request</h3></div></div>
    {(selectedRequirement || selectedRfq) && <div className="quick-record"><span>Selected requirement</span><strong>{text(selectedRequirement?.business_number || selectedRfq?.requirement_number || "Requirement")}</strong><small>{text(selectedRequirement?.status || selectedRfq?.status).replaceAll("_", " ")}</small></div>}
    <ol className="workflow-stepper" aria-label="Supplier request progress">
      <li className={requirementId ? "complete" : "current"}>Request details</li>
      <li className={selectedRfq ? "complete" : requirementId ? "current" : ""}>Suppliers</li>
      <li className={status === "draft" ? "current" : status ? "complete" : ""}>Review</li>
      <li className={status && status !== "draft" ? "complete" : ""}>Send</li>
    </ol>
    {!selectedRfq && <div className="ops-form">
      <label>Requirement<select value={requirementId} onChange={(event) => setRequirementId(event.target.value)}><option value="">Select requirement</option>{requirements.map((row) => <option value={id(row)} key={id(row)}>{text(row.business_number || row.id)} · {text(row.status)}</option>)}</select></label>
      <button className="action-button" disabled={busy || !requirementId} onClick={() => void postAction(`/procurement/requirements/${requirementId}/rfqs`, undefined, "Supplier request prepared for review.")}>Prepare supplier request</button>
    </div>}
    {selectedRfq && <form className="ops-form" onSubmit={update}>
      <label>Deadline<input name="deadline" type="date" defaultValue={text(selectedRfq.deadline)} /></label>
      <label className="span-2">Supplier shortlist<select name="supplier_ids" multiple defaultValue={Array.isArray(selectedRfq.supplier_ids) ? selectedRfq.supplier_ids.map(String) : []}>{suppliers.map((supplier) => <option key={id(supplier)} value={id(supplier)}>{text(supplier.name)}</option>)}</select></label>
      {status === "draft" && <button className="small-action" disabled={busy}>Save changes</button>}
    </form>}
    {selectedRfq && status === "draft" && <div className="confirmation-strip">
      <div><strong>Review before sending</strong><span>{supplierCount} approved supplier{supplierCount === 1 ? "" : "s"} selected · deadline {text(selectedRfq.deadline)}</span></div>
      <button className="small-action" type="button" disabled={busy || artifactBusy} onClick={() => void previewPdf()}>Review supplier document</button>
      <button className="action-button" disabled={busy || artifactBusy || supplierCount === 0} onClick={() => {
        if (window.confirm(`Send ${text(selectedRfq.business_number)} to ${supplierCount} suppliers? This version becomes immutable and approved email deliveries will be prepared with the final document attached.`)) {
          void postAction(`/procurement/rfqs/${rfqId}/publish`, undefined, "Supplier request released; delivery preparation is visible in Delivery status.", version(selectedRfq));
        }
      }}>Send to {supplierCount} supplier{supplierCount === 1 ? "" : "s"}</button>
    </div>}
    {selectedRfq && status !== "draft" && <div className="confirmation-strip"><div><strong>Supplier request sent</strong><span>Draft controls are locked. Track quotations and delivery status from this issued record.</span></div><button className="action-button" type="button" disabled={artifactBusy} onClick={() => void downloadFinalPdf()}>View sent request</button></div>}
    {artifactError && <div className="error-banner">{artifactError}</div>}
  </section>;
}

export function EvidenceReviewPanel({ workspaceData, postAction, busy }: CommonProps) {
  const quotes = workspaceData?.quotes ?? [];
  const exchangeRates = workspaceData?.exchange_rates ?? [];
  const [quoteId, setQuoteId] = useRouteSelection("quote");
  const selected = quotes.find((row) => id(row) === quoteId);
  const verifications = Array.isArray(selected?.field_verifications) ? selected?.field_verifications as Row[] : [];
  const documents = Array.isArray(selected?.documents) ? selected.documents as Row[] : [];
  const sourceDocument = documents[0];
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceError, setSourceError] = useState("");

  useEffect(() => {
    setSourceUrl("");
    setSourceError("");
    if (!sourceDocument) return;
    let objectUrl = "";
    void apiFetch<{ url: string }>(`/documents/${id(sourceDocument)}/download-url`)
      .then((result) => apiBlob(result.url))
      .then((blob) => { objectUrl = URL.createObjectURL(blob); setSourceUrl(objectUrl); })
      .catch((caught) => setSourceError(caught instanceof Error ? caught.message : "Source document is unavailable"));
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [quoteId, sourceDocument]);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const decisions = verifications.filter((row) => text(row.status) === "needs_review").map((row) => {
      const key = id(row);
      const decision = text(form.get(`decision-${key}`)) || "accept";
      return { field_name: text(row.field_name), decision, verified_value: decision === "correct" ? form.get(`value-${key}`) : undefined };
    });
    void postAction(`/procurement/quotes/${quoteId}/verify-fields`, { decisions }, "Quote evidence decisions saved.", version(selected));
  }
  function recordRate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    void postAction("/procurement/exchange-rates", { source_currency: form.get("source_currency"), target_currency: "INR", rate: Number(form.get("rate")), source_name: form.get("source_name"), source_reference: form.get("source_reference"), observed_at: form.get("observed_at") }, "Verified exchange-rate evidence recorded.");
  }
  return <section className="action-panel workflow-action-panel">
    <div className="panel-head compact-head"><div><div className="section-kicker">Human verification gate</div><h3>Review extracted fields</h3></div></div>
    <label className="panel-select">Quote<select value={quoteId} onChange={(event) => setQuoteId(event.target.value)}><option value="">Select quotation</option>{quotes.map((quote) => <option key={id(quote)} value={id(quote)}>{text(quote.quote_number)} / {text(quote.verification_status)}</option>)}</select></label>
    {selected && <div className="quote-review-layout">
      <aside className="source-document-panel">
        <div className="source-document-head">
          <div><small>Supplier source</small><strong>{text(sourceDocument?.filename) || "No document linked"}</strong></div>
          {sourceUrl && <a className="small-action" href={sourceUrl} target="_blank" rel="noreferrer">Open original</a>}
        </div>
        {sourceUrl && text(sourceDocument?.content_type) === "application/pdf"
          ? <object aria-label="Supplier quotation source document" data={sourceUrl} type="application/pdf"><div className="empty-state">This browser cannot render the document. Use Open original or download it for review.</div></object>
          : <div className="empty-state">{sourceError || (sourceDocument ? "This file type cannot be previewed securely. Open the original to review it." : "Upload a quotation document to review it beside extracted fields.")}</div>}
      </aside>
      <form className="evidence-form" onSubmit={submit}>
        {verifications.map((row) => <div className="evidence-decision" key={id(row)}>
          <div><strong>{text(row.display_label || row.field_name).replaceAll("_", " ")}</strong><small>{text(row.section || "Extracted field")} · confidence {text(row.confidence)}</small></div>
          <input name={`value-${id(row)}`} defaultValue={text(row.verified_value || row.extracted_value)} />
          <select name={`decision-${id(row)}`} defaultValue="accept" disabled={text(row.status) !== "needs_review"}><option value="accept">Accept</option><option value="correct">Correct</option><option value="reject">Reject</option></select>
        </div>)}
        <button className="action-button" disabled={busy || !verifications.some((row) => text(row.status) === "needs_review")}>Save decisions</button>
      </form>
    </div>}
    {selected && text(selected.currency || "INR").toUpperCase() !== "INR" && <div className="inline-workflow"><div className="panel-head compact-head"><div><div className="section-kicker">Currency evidence</div><h3>Verify {text(selected.currency).toUpperCase()} conversion</h3><p>A supplier-entered rate cannot influence the recommendation until a buyer links sourced evidence.</p></div></div><form className="ops-form" onSubmit={recordRate}><input type="hidden" name="source_currency" value={text(selected.currency).toUpperCase()} /><label>Rate to INR<input name="rate" type="number" min="0.000001" step="0.000001" required /></label><label>Source name<input name="source_name" required placeholder="Customer treasury rate" /></label><label>Source reference<input name="source_reference" placeholder="Rate sheet / reference" /></label><label>Observed at<input name="observed_at" type="datetime-local" required /></label><button className="small-action" disabled={busy}>Record evidence</button></form><div className="ops-form"><label>Verified observation<select id="quote-fx-observation" defaultValue={text(selected.exchange_rate_observation_id)}><option value="">Select matching evidence</option>{exchangeRates.filter((row) => text(row.source_currency) === text(selected.currency).toUpperCase() && text(row.target_currency) === "INR").map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number)} · {text(row.rate)} · {text(row.source_name)}</option>)}</select></label><button className="action-button" disabled={busy} onClick={() => { const element = document.getElementById("quote-fx-observation") as HTMLSelectElement | null; if (element?.value) void postAction(`/procurement/quotes/${id(selected)}/exchange-rate`, { observation_id: element.value }, "Verified exchange rate linked to quotation.", version(selected)); }}>Apply to quotation</button></div></div>}
  </section>;
}

export function ApprovalReviewPanel({ workspaceData, postAction, busy }: CommonProps) {
  const awards = workspaceData?.awards ?? [];
  const rfqs = workspaceData?.rfqs ?? [];
  const [awardId, setAwardId] = useRouteSelection('award');
  const [rfqId, setRfqId] = useRouteSelection('rfq');
  const award = awards.find((row) => id(row) === awardId);
  return <section className='action-panel workflow-action-panel'>
    <div className='panel-head compact-head'><div><div className='section-kicker'>Human authority</div><h3>Review and confirm selected decisions</h3></div></div>
    <div className='ops-form'>
      <label>Supplier choice (Award)<select value={awardId} onChange={(event) => setAwardId(event.target.value)}><option value=''>Select award</option>{awards.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)} / {text(row.status)}</option>)}</select></label>
      <div className='quick-record'><span>Decision effect</span><strong>{awardId ? 'Authorize supplier choice' : 'Select an award'}</strong><small>Required before a purchase order can be prepared</small></div>
      <button className='action-button' disabled={busy || !awardId || text(award?.status) !== 'pending_approval'} onClick={() => void postAction('/procurement/awards/' + awardId + '/approve', undefined, 'Supplier award approved. The purchase order can now be prepared.', version(award))}>Approve award</button>
    </div>
    <div className='ops-form'>
      <label>Supplier request<select value={rfqId} onChange={(event) => setRfqId(event.target.value)}><option value=''>Select request</option>{rfqs.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)} / {text(row.status).replaceAll('_', ' ')}</option>)}</select></label>
      <div className='quick-record'><span>Supplier release</span><strong>{rfqId ? 'Review in the supplier-request workbench' : 'Select a request'}</strong><small>Sending is controlled from one canonical Review and Send step.</small></div>
      <a className='action-button' aria-disabled={!rfqId} href={rfqId ? `/rfq-builder?rfq=${encodeURIComponent(rfqId)}` : '#'}>Review and send</a>
    </div>
  </section>;
}


export function ComparisonActionPanel({ workspaceData, postAction, busy }: CommonProps) {
  const rfqs = workspaceData?.rfqs ?? [];
  const [rfqId, setRfqId] = useRouteSelection("rfq");
  return <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Verified supplier offers</div><h3>Compare verified quotations</h3></div></div><div className="ops-form"><label>Supplier request<select value={rfqId} onChange={(event) => setRfqId(event.target.value)}><option value="">Select request</option>{rfqs.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)}</option>)}</select></label><button className="action-button" disabled={busy || !rfqId} onClick={() => void postAction(`/procurement/comparisons/${rfqId}/generate`, undefined, "Verified quotations compared with line-level recommendations.")}>Compare verified quotations</button></div></section>;
}

export function NegotiationWorkflowPanel({ workspaceData, postAction, busy }: CommonProps) {
  const rfqs = workspaceData?.rfqs ?? [];
  const suppliers = workspaceData?.suppliers ?? [];
  const rounds = workspaceData?.negotiations ?? [];
  const [roundId, setRoundId] = useRouteSelection("negotiation");
  const selected = rounds.find((row) => id(row) === roundId);
  function create(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = new FormData(event.currentTarget); void postAction("/procurement/negotiations", { rfq_id: form.get("rfq_id"), supplier_id: form.get("supplier_id"), target: form.get("target"), drafted_message: form.get("message") }, "Negotiation draft created."); }
  function counter(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = new FormData(event.currentTarget); void postAction(`/procurement/negotiations/${roundId}/counteroffer`, { revised_unit_price: Number(form.get("price")), message: form.get("counter_message"), commercial_terms: {} }, "Counteroffer recorded.", version(selected)); }
  const status = text(selected?.status);
  return <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Supplier negotiation</div><h3>Agree revised commercial terms</h3></div></div>
    <ol className="workflow-stepper" aria-label="Negotiation progress"><li className={roundId ? "complete" : "current"}>Draft message</li><li className={status === "pending_approval" ? "current" : ["manager_approved", "supplier_countered", "accepted_pending_reverification"].includes(status) ? "complete" : ""}>Approve</li><li className={status === "manager_approved" ? "current" : ["supplier_countered", "accepted_pending_reverification"].includes(status) ? "complete" : ""}>Supplier response</li><li className={status === "supplier_countered" ? "current" : status === "accepted_pending_reverification" ? "complete" : ""}>Reverify offer</li></ol>
    {!roundId && <form className="ops-form" onSubmit={create}><label>Supplier request<select name="rfq_id" required>{rfqs.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)}</option>)}</select></label><label>Supplier<select name="supplier_id" required>{suppliers.map((row) => <option key={id(row)} value={id(row)}>{text(row.name)}</option>)}</select></label><label>Negotiation target<input name="target" required /></label><label className="span-2">Message to supplier<textarea name="message" required /></label><button className="action-button" disabled={busy}>Prepare negotiation</button></form>}
    <div className="ops-form"><label>Negotiation<select value={roundId} onChange={(event) => setRoundId(event.target.value)}><option value="">Start a new negotiation</option>{rounds.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)} · {text(row.status).replaceAll("_", " ")}</option>)}</select></label>{status === "draft" && <button className="action-button" disabled={busy} onClick={() => void postAction(`/procurement/negotiations/${roundId}/submit`, undefined, "Negotiation sent for internal approval.", version(selected))}>Request approval</button>}{status === "pending_approval" && <button className="action-button" disabled={busy} onClick={() => void postAction(`/procurement/negotiations/${roundId}/approve`, undefined, "Negotiation approved and prepared for supplier delivery.", version(selected))}>Approve supplier message</button>}{status === "supplier_countered" && <button className="action-button" disabled={busy} onClick={() => void postAction(`/procurement/negotiations/${roundId}/accept`, undefined, "Counteroffer accepted; the revised offer now requires evidence verification.", version(selected))}>Accept and reverify offer</button>}</div>{status === "manager_approved" && <form className="ops-form" onSubmit={counter}><label>Revised unit price<input name="price" type="number" min="0.01" step="0.01" required /></label><label className="span-2">Supplier response<textarea name="counter_message" required /></label><button className="action-button" disabled={busy}>Record supplier response</button></form>}</section>;
}

export function InboundActionPanel({ workspaceData, postAction, busy, user }: CommonProps & { user: User }) {
  const pos = workspaceData?.po_drafts ?? [];
  const asns = workspaceData?.asns ?? [];
  const receipts = workspaceData?.receipts ?? [];
  function submit(path: string, success: string) { return (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const form = new FormData(event.currentTarget); const body: Record<string, unknown> = Object.fromEntries(form.entries()); ["expected_quantity", "received_quantity", "damaged_quantity", "inspected_quantity", "accepted_quantity", "rejected_quantity", "held_quantity"].forEach((key) => { if (key in body) body[key] = Number(body[key]); }); void postAction(path, body, success); }; }
  return <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Controlled inbound</div><h3>Record next inbound event</h3></div></div>{user.role === "store_manager" && <><form className="ops-form" onSubmit={submit("/inbound/asns", "ASN recorded.")}><label>Posted PO<select name="po_draft_id" required><option value="">Select PO</option>{pos.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)}</option>)}</select></label><label>Expected quantity<input name="expected_quantity" type="number" min="0.01" required /></label><label>Vehicle<input name="vehicle_number" /></label><button className="action-button" disabled={busy}>Create ASN</button></form><form className="ops-form" onSubmit={submit("/inbound/gate-entries", "Gate entry recorded.")}><label>ASN<select name="asn_id" required><option value="">Select ASN</option>{asns.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)}</option>)}</select></label><label>PO<select name="po_draft_id" required><option value="">Select PO</option>{pos.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)}</option>)}</select></label><label>Vehicle<input name="vehicle_number" /></label><button className="action-button" disabled={busy}>Record gate entry</button></form><form className="ops-form" onSubmit={submit("/inbound/receipts", "Store receipt recorded.")}><label>PO<select name="po_draft_id" required><option value="">Select PO</option>{pos.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)}</option>)}</select></label><label>Received<input name="received_quantity" type="number" min="0.01" required /></label><label>Damaged<input name="damaged_quantity" type="number" min="0" defaultValue="0" /></label><button className="action-button" disabled={busy}>Record receipt</button></form></>}{user.role === "quality_inspector" && <form className="ops-form" onSubmit={submit("/inbound/inspections", "Inspection recorded.")}><label>Receipt<select name="receipt_id" required><option value="">Select receipt</option>{receipts.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)}</option>)}</select></label>{["inspected_quantity", "accepted_quantity", "rejected_quantity", "held_quantity"].map((field) => <label key={field}>{field.replaceAll("_", " ")}<input name={field} type="number" min="0" defaultValue="0" required /></label>)}<button className="action-button" disabled={busy}>Record inspection</button></form>}</section>;
}

export function ComparisonV2ActionPanel({ workspaceData, postAction, busy, user }: CommonProps & { user: User }) {
  const rfqs = workspaceData?.rfqs ?? [];
  const comparisons = workspaceData?.comparisons ?? [];
  const [rfqId, setRfqId] = useRouteSelection("rfq");
  const [comparisonId, setComparisonId] = useRouteSelection("comparison");
  const selected = comparisons.find((row) => id(row) === comparisonId);
  const [artifactBusy, setArtifactBusy] = useState(false);
  const [error, setError] = useState("");
  const [allocations, setAllocations] = useState<Record<string, string>>({});
  const manager = user.role === "purchase_manager" || user.role === "admin";
  const approver = user.role === "plant_manager" || user.role === "purchase_executive";
  const comparisonRows = Array.isArray(selected?.rows) ? selected.rows as Row[] : [];
  useEffect(() => {
    const defaults: Record<string, string> = {};
    comparisonRows.forEach((row) => {
      const lineId = text(row.quote_line_id);
      if (lineId) defaults[lineId] = text(row.recommendation) === "Recommended" ? text(row.requested_quantity) : "0";
    });
    setAllocations(defaults);
  }, [comparisonId, selected?.version]);

  function confirmAllocation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const chosen = comparisonRows.filter((row) => Number(allocations[text(row.quote_line_id)] || 0) > 0).map((row) => ({
      rfq_line_id: text(row.rfq_line_id), quote_line_id: text(row.quote_line_id),
      awarded_quantity: Number(allocations[text(row.quote_line_id)]),
      rationale: text(row.recommendation) === "Recommended" ? "Approved comparison recommendation" : "Purchase Manager split allocation",
    }));
    if (!chosen.length) { setError("Allocate a positive quantity to at least one eligible supplier offer."); return; }
    if (!window.confirm(`Create ${new Set(chosen.map((row) => comparisonRows.find((candidate) => text(candidate.quote_line_id) === row.quote_line_id)?.supplier_id)).size} immutable supplier order(s) from this allocation?`)) return;
    void postAction(
      `/procurement/comparison-records/${comparisonId}/confirm-split-award`,
      { confirmation: "CONFIRM_SPLIT_AWARD", allocations: chosen },
      "Supplier allocation confirmed. Separate purchase orders were created and remain unsent until controlled dispatch.",
    );
  }

  async function preview() {
    if (!comparisonId) return;
    setArtifactBusy(true);
    setError("");
    try {
      const artifact = await mutate<Row>(
        `/procurement/comparison-records/${comparisonId}/pdf-preview`,
        csrfToken(),
        {},
      );
      await openArtifact(artifact);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Comparison PDF could not be generated");
    } finally {
      setArtifactBusy(false);
    }
  }

  async function openFinal() {
    if (!comparisonId) return;
    setArtifactBusy(true);
    setError("");
    try {
      const artifacts = await apiFetch<Row[]>(`/procurement/comparison-records/${comparisonId}/artifacts`);
      const artifact = artifacts.find((row) => text(row.status) === "final") ?? artifacts[0];
      if (!artifact) throw new Error("No comparison PDF has been finalized yet");
      await openArtifact(artifact);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Comparison PDF could not be opened");
    } finally {
      setArtifactBusy(false);
    }
  }

  function submitForApproval(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    if (!window.confirm(`Send comparison v${text(selected?.comparison_version || 1)} and its supporting evidence to both approvers?`)) return;
    void postAction(
      `/procurement/comparison-records/${comparisonId}/submit`,
      { recommendation_rationale: form.get("recommendation_rationale") },
      "Recommendation sent to both approvers.",
    );
  }

  function decide(formElement: HTMLFormElement, decision: "approve" | "reject") {
    const form = new FormData(formElement);
    const effect = decision === "approve"
      ? "record your approval against this immutable version"
      : "return this comparison to the Purchase Manager for a new version";
    if (!window.confirm(`This will ${effect}. Continue?`)) return;
    void postAction(
      `/procurement/comparison-records/${comparisonId}/decision`,
      { decision, rationale: form.get("rationale") },
      decision === "approve" ? "Your comparison approval was recorded." : "Comparison rejected and returned for revision.",
    );
  }

  return <section className="action-panel workflow-action-panel">
    <div className="panel-head compact-head">
      <div><div className="section-kicker">Supplier decision</div><h3>Review the recommendation</h3></div>
      <div className="button-row">
        <button className="small-action" type="button" disabled={!comparisonId || artifactBusy} onClick={() => void openFinal()}>View comparison document</button>
        {manager && <button className="small-action" type="button" disabled={!comparisonId || artifactBusy} onClick={() => void preview()}>Preview changes</button>}
      </div>
    </div>
    <ol className="workflow-stepper" aria-label="Supplier decision progress">
      <li className={comparisonId ? "complete" : "current"}>Verified quotations</li>
      <li className={selected && text(selected.status) !== "draft" ? "complete" : comparisonId ? "current" : ""}>Recommendation</li>
      <li className={["approved", "rejected"].includes(text(selected?.status)) ? "complete" : ["ready_for_approval", "partially_approved"].includes(text(selected?.status)) ? "current" : ""}>Approvals</li>
      <li className={text(selected?.status) === "approved" ? "current" : ""}>Create order</li>
    </ol>
    {manager && <div className="ops-form">
      <label>Supplier request<select value={rfqId} onChange={(event) => setRfqId(event.target.value)}><option value="">Select supplier request</option>{rfqs.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)}</option>)}</select></label>
      <button className="small-action" type="button" disabled={busy || !rfqId} onClick={() => void postAction(`/procurement/comparisons/${rfqId}/generate`, undefined, "Verified offers are ready for recommendation review.")}>{comparisonId ? "Refresh verified offers" : "Build comparison"}</button>
    </div>}
    <div className="ops-form">
      <label>Comparison<select value={comparisonId} onChange={(event) => setComparisonId(event.target.value)}><option value="">Select comparison</option>{comparisons.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)} / v{text(row.comparison_version || 1)} / {text(row.status)}</option>)}</select></label>
      <div className="quick-record"><span>Approval status</span><strong>{text(selected?.status).replaceAll("_", " ") || "Select a comparison"}</strong><small>{text(selected?.recommendation_rationale) || "Recommendation rationale not submitted"}</small></div>
    </div>
    {manager && selected && ["draft", "ready_for_manager_review", "rejected"].includes(text(selected.status)) && <form className="ops-form" onSubmit={submitForApproval}>
      <label className="span-2">Purchase Manager recommendation<textarea name="recommendation_rationale" defaultValue={text(selected.recommendation_rationale)} required /></label>
      <button className="action-button" disabled={busy}>Send recommendation for approval</button>
    </form>}
    {manager && text(selected?.status) === "approved" && <form className="ops-form" onSubmit={confirmAllocation}>
      <div className="span-4"><strong>Allocate approved quantities</strong><p className="form-note">Use the recommendation as-is or divide a line between eligible suppliers. Totals cannot exceed either the requested or offered quantity.</p></div>
      {comparisonRows.filter((row) => !row.disqualified).map((row) => <div className="form-line span-4" key={text(row.quote_line_id)}>
        <div className="quick-record"><span>{text(row.supplier_name)}</span><strong>{text(row.net_landed_unit_cost)} INR / unit</strong><small>{text(row.recommendation)} · offered {text(row.offered_quantity)} · requested {text(row.requested_quantity)} · {text(row.source_currency)} rate {text(row.exchange_rate_to_inr)} from {text(row.exchange_rate_source || "missing evidence")}</small></div>
        <label>Award quantity<input type="number" min="0" max={Number(row.offered_quantity || 0)} step="0.001" value={allocations[text(row.quote_line_id)] || "0"} onChange={(event) => setAllocations((current) => ({ ...current, [text(row.quote_line_id)]: event.target.value }))} /></label>
      </div>)}
      <button className="action-button" disabled={busy || !comparisonRows.length}>Confirm allocation and create orders</button>
    </form>}
    {approver && selected && ["ready_for_approval", "partially_approved"].includes(text(selected.status)) && <form className="ops-form">
      <label className="span-2">Decision rationale<textarea name="rationale" required /></label>
      <button className="action-button" type="button" disabled={busy} onClick={(event) => event.currentTarget.form && decide(event.currentTarget.form, "approve")}>Approve this version</button>
      <button className="small-action danger" type="button" disabled={busy} onClick={(event) => event.currentTarget.form && decide(event.currentTarget.form, "reject")}>Reject and return</button>
    </form>}
    {error && <div className="error-banner">{error}</div>}
  </section>;
}

export function PoArtifactPanel({ workspaceData, postAction, busy }: CommonProps) {
  const poDrafts = workspaceData?.po_drafts ?? [];
  const suppliers = workspaceData?.suppliers ?? [];
  const supplierContacts = workspaceData?.supplier_contacts ?? [];
  const [poId, setPoId] = useRouteSelection("po");
  const poLines = (workspaceData?.po_lines ?? []).filter((row) => text(row.po_draft_id) === poId);
  const selected = poDrafts.find((row) => id(row) === poId);
  const selectedSupplier = suppliers.find((row) => id(row) === text(selected?.supplier_id));
  const selectedContact = supplierContacts.find((row) => text(row.supplier_id) === text(selected?.supplier_id));
  const changeRequests = (workspaceData?.acknowledgements ?? []).filter((row) => text(row.po_draft_id) === poId && text(row.status) === "change_requested");
  const [artifactBusy, setArtifactBusy] = useState(false);
  const [error, setError] = useState("");
  const status = text(selected?.status);
  const approved = ["approved_pending_outbox", "simulated_posted", "posted"].includes(status);
  const issued = ["simulated_posted", "posted"].includes(status);
  const isChange = ["amendment", "cancellation"].includes(text(selected?.revision_kind));

  function addSupplierContact(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedSupplier) return;
    const form = new FormData(event.currentTarget);
    void postAction(`/procurement/suppliers/${id(selectedSupplier)}/contacts`, {
      name: form.get("name"), email: form.get("email"), phone: form.get("phone"),
    }, "Supplier delivery contact added. You can now prepare the order for delivery.");
  }

  function prepareChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const changeType = text(form.get("change_type"));
    const lineId = text(form.get("line_id"));
    const lines = changeType === "amendment" ? [{
      line_id: lineId, quantity: Number(form.get("quantity")),
      unit_price: Number(form.get("unit_price")), need_by_date: text(form.get("need_by_date")),
    }] : [];
    if (!window.confirm(`Prepare a new immutable ${changeType} version for approval? The issued order will remain current until external dispatch succeeds.`)) return;
    void postAction(`/procurement/po-drafts/${poId}/changes`, {
      change_type: changeType, reason: form.get("reason"), lines,
      acknowledgement_id: text(form.get("acknowledgement_id")) || null,
    }, `PO ${changeType} prepared for approval.`, version(selected));
  }

  async function preview() {
    if (!poId) return;
    setArtifactBusy(true);
    setError("");
    try {
      const artifact = await mutate<Row>(`/procurement/po-drafts/${poId}/pdf-preview`, csrfToken(), {});
      await openArtifact(artifact);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "PO preview could not be generated");
    } finally {
      setArtifactBusy(false);
    }
  }

  async function openFinal() {
    if (!poId) return;
    setArtifactBusy(true);
    setError("");
    try {
      const artifacts = await apiFetch<Row[]>(`/procurement/po-drafts/${poId}/artifacts`);
      const artifact = artifacts.find((row) => text(row.status) === "final");
      if (!artifact) throw new Error("The final PO PDF has not been created yet");
      await openArtifact(artifact);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Final PO could not be opened");
    } finally {
      setArtifactBusy(false);
    }
  }

  return <section className="action-panel workflow-action-panel">
    <div className="panel-head compact-head"><div><div className="section-kicker">Purchase order</div><h3>Review and issue the order</h3></div></div>
    <ol className="workflow-stepper" aria-label="Order workflow progress">
      <li className={poId ? "complete" : "current"}>Order details</li>
      <li className={approved ? "complete" : poId ? "current" : ""}>Approve</li>
      <li className={issued ? "complete" : approved ? "current" : ""}>Send</li>
      <li className={issued ? "current" : ""}>Acknowledgement</li>
    </ol>
    <div className="ops-form">
      <label>Purchase order<select value={poId} onChange={(event) => setPoId(event.target.value)}><option value="">Select PO</option>{poDrafts.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)} / {text(row.status)}</option>)}</select></label>
      <div className="quick-record"><span>Supplier</span><strong>{text(selectedSupplier?.name) || text(selected?.supplier_id) || "Select a PO"}</strong><small>{selectedContact ? `Delivery contact: ${text(selectedContact.email)}` : "Delivery contact not configured"} · ERP posting: {text(selected?.simulated_posting_correlation_id) || "Not posted"}</small></div>
      {!approved && <>
        <button type="button" className="small-action" disabled={busy || artifactBusy || !poId} onClick={() => void preview()}>Review order document</button>
        <button type="button" className="action-button" disabled={busy || artifactBusy || !poId || status !== "pending_approval"} onClick={() => {
          if (window.confirm(isChange ? `Approve this PO ${text(selected?.revision_kind)} and prepare its separate external action?` : "Approve this purchase order and create its final locked document? This does not yet send it to the supplier or ERP.")) {
            void postAction(isChange ? `/procurement/po-drafts/${poId}/approve-change` : `/procurement/po-drafts/${poId}/approve`, undefined, isChange ? "PO change approved and queued for controlled external dispatch." : "Purchase order approved. The final document is ready to issue.", version(selected));
          }
        }}>Approve purchase order</button>
      </>}
      {approved && <>
        <button type="button" className="small-action" disabled={busy || artifactBusy || !poId} onClick={() => void openFinal()}>View approved order</button>
        <button type="button" className="action-button" disabled={busy || artifactBusy || !poId || !selectedContact} onClick={() => {
          if (window.confirm("Prepare this approved order for supplier delivery? You will still review the delivery queue before it is sent.")) void postAction(`/procurement/po-drafts/${poId}/supplier-email`, {}, "Order prepared for supplier delivery. Review Delivery status to send it.");
        }}>Prepare supplier delivery</button>
      </>}
    </div>
    {approved && selectedSupplier && !selectedContact && <form className="ops-form inline-workflow" onSubmit={addSupplierContact}>
      <div className="span-4"><strong>Add supplier delivery contact</strong><p className="form-note">This supplier was imported without an email contact. Add the intended recipient before preparing delivery.</p></div>
      <label>Contact name<input name="name" required placeholder="Supplier sales contact" /></label>
      <label>Email<input name="email" type="email" required placeholder="sales@supplier.com" /></label>
      <label>Phone (optional)<input name="phone" type="tel" /></label>
      <button className="action-button" disabled={busy}>Save contact</button>
    </form>}
    {issued && <details className="inline-workflow">
      <summary>Change or cancel this issued order</summary>
      {changeRequests.map((request) => <div className="confirmation-strip" key={id(request)}><div><strong>Supplier requested a change</strong><span>{text(request.response_notes)} · proposed quantity {text(request.confirmed_quantity)} · delivery {text(request.confirmed_delivery)}</span></div></div>)}
      <form className="ops-form" onSubmit={prepareChange}>
        <label>Supplier response<select name="acknowledgement_id"><option value="">Internal change</option>{changeRequests.map((request) => <option key={id(request)} value={id(request)}>{text(request.business_number || request.id)} · {text(request.response_notes)}</option>)}</select></label>
        <label>Change type<select name="change_type" defaultValue="amendment"><option value="amendment">Amend order</option><option value="cancellation">Cancel order</option></select></label>
        <label>Order line<select name="line_id" required>{poLines.map((line) => <option key={id(line)} value={id(line)}>{text(line.business_number || line.id)} · {text(line.quantity)} {text(line.uom)}</option>)}</select></label>
        <label>Revised quantity<input name="quantity" type="number" min="0.001" step="0.001" defaultValue={text(poLines[0]?.quantity)} /></label>
        <label>Revised unit price<input name="unit_price" type="number" min="0" step="0.01" defaultValue={text(poLines[0]?.unit_price)} /></label>
        <label>Revised need-by date<input name="need_by_date" type="date" defaultValue={text(poLines[0]?.need_by_date)} /></label>
        <label className="span-2">Business reason<textarea name="reason" required /></label>
        <button className="action-button" disabled={busy || !poLines.length}>Prepare new version</button>
      </form>
      <p className="form-note">Cancellation is blocked after delivery activity. The current version stays effective until the approved external change is acknowledged.</p>
    </details>}
    <div className="confirmation-strip"><div><strong>{approved ? "Approved order" : "Human approval required"}</strong><span>{approved ? "Supplier delivery and ERP synchronization remain separate controlled actions." : "Review the supplier, quantities, price, taxes, and delivery terms before approval."}</span></div></div>
    {error && <div className="error-banner">{error}</div>}
  </section>;
}


export function InboundV2ActionPanel({ workspaceData, postAction, busy, user }: CommonProps & { user: User }) {
  const pos = workspaceData?.po_drafts ?? [];
  const issuedPos = pos.filter((row) => ["posted", "simulated_posted"].includes(text(row.status)));
  const asns = workspaceData?.asns ?? [];
  const deliveryUpdates = workspaceData?.delivery_updates ?? [];
  const documents = workspaceData?.documents ?? [];
  const receipts = workspaceData?.receipts ?? [];
  const [poId, setPoId] = useRouteSelection("po");
  const [receiptId, setReceiptId] = useRouteSelection("receipt");
  useEffect(() => {
    if (!poId && ["gate_operator", "store_manager"].includes(user.role) && issuedPos[0]) setPoId(id(issuedPos[0]));
    if (!receiptId && user.role === "quality_inspector" && receipts[0]) setReceiptId(id(receipts[0]));
  }, [poId, receiptId, issuedPos, receipts, setPoId, setReceiptId, user.role]);
  function submit(path: string, success: string) {
    return (event: FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const body: Record<string, unknown> = Object.fromEntries(new FormData(event.currentTarget).entries());
      ["packages_count", "expected_quantity", "received_quantity", "damaged_quantity", "inspected_quantity", "accepted_quantity", "rejected_quantity", "held_quantity"].forEach((key) => {
        if (key in body) body[key] = Number(body[key]);
      });
      body.production_impact = body.production_impact === "on";
      if (typeof body.defect_codes === "string") body.defect_codes = body.defect_codes.split(",").map((value) => value.trim()).filter(Boolean);
      if (body.asn_id === "") body.asn_id = null;
      void postAction(path, body, success);
    };
  }
  return <section className="action-panel workflow-action-panel">
    <div className="panel-head compact-head"><div><div className="section-kicker">Physical handoff</div><h3>Record the event owned by your role</h3></div></div>
    {user.role === "gate_operator" && <form className="ops-form" onSubmit={submit("/inbound/gate-entries", "Gate entry recorded and Stores notified.")}>
      <label>Issued PO<select name="po_draft_id" value={poId} onChange={(event) => setPoId(event.target.value)} required><option value="">Select PO</option>{issuedPos.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)}</option>)}</select></label>
      <label>ASN (optional)<select name="asn_id"><option value="">No ASN</option>{asns.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)}</option>)}</select></label>
      <label>Vehicle number<input name="vehicle_number" required /></label>
      <label>Supplier challan<input name="supplier_challan" required /></label>
      <label>Packages<input name="packages_count" type="number" min="0" defaultValue="0" /></label>
      <label className="span-2">Arrival notes<textarea name="arrival_notes" /></label>
      <button className="action-button" disabled={busy || !issuedPos.length}>Admit vehicle</button>
    </form>}
    {user.role === "store_manager" && <>
      {asns.some((row) => text(row.source) === "supplier_portal") && <div className="business-card-grid span-4">{asns.filter((row) => text(row.source) === "supplier_portal").map((asn) => { const documentIds = Array.isArray(asn.supplier_document_ids) ? asn.supplier_document_ids.map(String) : []; const evidence = documents.filter((document) => documentIds.includes(id(document))); const updates = deliveryUpdates.filter((update) => text(update.asn_id) === id(asn)).sort((left, right) => text(right.submitted_at).localeCompare(text(left.submitted_at))); const latestUpdate = updates[0]; return <article className="business-record-card" key={id(asn)}><div><strong>{text(asn.business_number || asn.id)}</strong><span>Supplier dispatch {text(asn.dispatch_reference)} · {text(asn.expected_quantity)} expected {text(asn.expected_delivery)}</span>{latestUpdate && <span className="critical-copy">Commitment changed from {text(latestUpdate.previous_expected_delivery)}: {text(latestUpdate.reason)}</span>}<span>Vehicle: {text(asn.vehicle_number) || "Not provided"}</span><span>Evidence: {evidence.length ? evidence.map((document) => `${text(document.filename)} (${text(document.status).replaceAll("_", " ")})`).join(", ") : "No dispatch document uploaded"}</span></div><span className={`status-pill ${latestUpdate?.update_type === "delay" || evidence.some((document) => text(document.status) === "quarantined_rejected") ? "critical" : evidence.length ? "good" : "action"}`}>{latestUpdate ? text(latestUpdate.update_type).replaceAll("_", " ") : evidence.length ? "Evidence received" : "Evidence needed"}</span></article>; })}</div>}
      <form className="ops-form" onSubmit={submit("/inbound/asns", "ASN recorded.")}>
        <label>Issued PO<select name="po_draft_id" value={poId} onChange={(event) => setPoId(event.target.value)} required><option value="">Select PO</option>{issuedPos.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)}</option>)}</select></label>
        <label>Expected quantity<input name="expected_quantity" type="number" min="0.01" required /></label>
        <label>Vehicle<input name="vehicle_number" /></label>
        <button className="small-action" disabled={busy}>Record optional ASN</button>
      </form>
      <form className="ops-form" onSubmit={submit("/inbound/receipts", "Store receipt recorded and Quality notified.")}>
        <label>PO admitted at gate<select name="po_draft_id" value={poId} onChange={(event) => setPoId(event.target.value)} required><option value="">Select PO</option>{pos.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)}</option>)}</select></label>
        <label>Received<input name="received_quantity" type="number" min="0.01" required /></label>
        <label>Damaged<input name="damaged_quantity" type="number" min="0" defaultValue="0" /></label>
        <label>Observed item code<input name="observed_item_code" placeholder="Confirm the material label" /></label>
        <label>Certificate<select name="certificate_status" defaultValue="received"><option value="received">Received</option><option value="missing">Missing</option><option value="invalid">Invalid</option></select></label>
        <label className="span-2">Exception notes<textarea name="exception_notes" placeholder="Describe damage, wrong material, shortage, or missing evidence" /></label>
        <label className="checkbox-label"><input name="production_impact" type="checkbox" /> May affect production</label>
        <button className="action-button" disabled={busy}>Record store receipt</button>
      </form>
    </>}
    {user.role === "quality_inspector" && <form className="ops-form" onSubmit={submit("/inbound/inspections", "Quality inspection recorded.")}>
      <label>Store receipt<select name="receipt_id" value={receiptId} onChange={(event) => setReceiptId(event.target.value)} required><option value="">Select receipt</option>{receipts.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)}</option>)}</select></label>
      {["inspected_quantity", "accepted_quantity", "rejected_quantity", "held_quantity"].map((field) => <label key={field}>{field.replaceAll("_", " ")}<input name={field} type="number" min="0" defaultValue="0" required /></label>)}
      <label>Certificate review<select name="certificate_status" defaultValue="verified"><option value="verified">Verified</option><option value="pending">Pending</option><option value="missing">Missing</option><option value="invalid">Invalid</option></select></label>
      <label>Defect codes<input name="defect_codes" placeholder="SURFACE, DIMENSION" /></label>
      <label className="span-2">Inspection notes<textarea name="inspection_notes" /></label>
      <label className="checkbox-label"><input name="production_impact" type="checkbox" /> May affect production</label>
      <button className="action-button" disabled={busy}>Record inspection</button>
    </form>}
    {!["gate_operator", "store_manager", "quality_inspector"].includes(user.role) && <p className="empty-state">This is a status view for your role. The physical entry controls are assigned to Gate, Stores, and Quality.</p>}
  </section>;
}


export function SupplierReturnPanel({ workspaceData, postAction, busy, user }: CommonProps & { user: User }) {
  const inspections = (workspaceData?.inspections ?? []).filter((row) => Number(row.rejected_quantity || 0) > 0);
  const returns = workspaceData?.supplier_returns ?? [];
  function createReturn(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = new FormData(event.currentTarget); void postAction("/quality/supplier-returns", { inspection_id: form.get("inspection_id"), return_quantity: Number(form.get("return_quantity")), reason: form.get("reason") }, "Supplier return prepared for review."); }
  function requestReplacement(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = new FormData(event.currentTarget); const returnId = text(form.get("supplier_return_id")); void postAction(`/quality/supplier-returns/${returnId}/request-replacement`, { replacement_quantity: Number(form.get("replacement_quantity")), requested_delivery: form.get("requested_delivery") }, "Replacement request placed in the governed supplier queue."); }
  function receiveReplacement(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = new FormData(event.currentTarget); const returnId = text(form.get("supplier_return_id")); void postAction(`/quality/supplier-returns/${returnId}/receive`, { received_quantity: Number(form.get("received_quantity")), supplier_challan: form.get("supplier_challan"), vehicle_number: form.get("vehicle_number"), packages_count: Number(form.get("packages_count") || 0) }, "Replacement received and Quality reinspection assigned."); }
  return <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Rejected material recovery</div><h3>Return → replacement → reinspection</h3><p>Rejected stock stays excluded from usable inventory. Replacement receipts always return to Quality.</p></div><span className="record-count">{returns.length}</span></div>
    {["purchase_manager", "admin"].includes(user.role) && <><form className="ops-form" onSubmit={createReturn}><label>Rejected inspection<select name="inspection_id" required><option value="">Select inspection</option>{inspections.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)} · {text(row.rejected_quantity)} rejected</option>)}</select></label><label>Return quantity<input name="return_quantity" type="number" min="0.01" step="0.01" required /></label><label className="span-2">Reason<textarea name="reason" required /></label><button className="secondary-button" disabled={busy || !inspections.length}>Prepare return</button></form><form className="ops-form" onSubmit={requestReplacement}><label>Prepared return<select name="supplier_return_id" required><option value="">Select return</option>{returns.filter((row) => text(row.status) === "draft").map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)}</option>)}</select></label><label>Replacement quantity<input name="replacement_quantity" type="number" min="0.01" step="0.01" required /></label><label>Requested delivery<input name="requested_delivery" type="date" required /></label><button className="action-button" disabled={busy}>Request replacement</button></form></>}
    {["store_manager", "admin"].includes(user.role) && <form className="ops-form" onSubmit={receiveReplacement}><label>Expected replacement<select name="supplier_return_id" required><option value="">Select return</option>{returns.filter((row) => ["replacement_requested", "replacement_partially_received"].includes(text(row.status))).map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)} · {text(row.status).replaceAll("_", " ")}</option>)}</select></label><label>Received<input name="received_quantity" type="number" min="0.01" step="0.01" required /></label><label>Supplier challan<input name="supplier_challan" required /></label><label>Vehicle<input name="vehicle_number" /></label><label>Packages<input name="packages_count" type="number" min="0" defaultValue="0" /></label><button className="action-button" disabled={busy}>Receive replacement</button></form>}
    <div className="setup-invitations">{returns.map((row) => <div className="setup-invitation-row" key={id(row)}><div><strong>{text(row.business_number || row.id)}</strong><span>{text(row.return_quantity)} returned · {text(row.replacement_received_quantity)} replacement received</span></div><span className={`status-pill ${text(row.status) === "replacement_accepted" ? "good" : "action"}`}>{text(row.status).replaceAll("_", " ")}</span></div>)}</div>
  </section>;
}


export function CaseResolutionPanel({ workspaceData, postAction, busy, user }: CommonProps & { user: User }) {
  const cases = workspaceData?.cases ?? [];
  const [caseId, setCaseId] = useRouteSelection("case");
  const selected = cases.find((row) => id(row) === caseId);
  function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const form = new FormData(event.currentTarget); void postAction(`/cases/${caseId}/close`, { resolution: form.get("resolution"), override: form.get("override") === "on", override_reason: form.get("override_reason") || undefined }, "Case closed.", version(selected)); }
  return <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Exception closure</div><h3>Resolve selected case</h3></div></div><form className="ops-form" onSubmit={submit}><label>Case<select value={caseId} onChange={(event) => setCaseId(event.target.value)}><option value="">Select case</option>{cases.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.title || row.id)}</option>)}</select></label><label className="span-2">Resolution<textarea name="resolution" required /></label>{["plant_manager", "admin"].includes(user.role) && <><label className="checkbox-label"><input name="override" type="checkbox" /> Manager override</label><label>Override rationale<input name="override_reason" /></label></>}<button className="action-button" disabled={busy || !caseId}>Close case</button></form></section>;
}

export function OutboxControlPanel({ workspaceData, postAction, busy }: CommonProps) {
  const rows = workspaceData?.outbox ?? [];
  const [recordId, setRecordId] = useRouteSelection("outbox");
  const selected = useMemo(() => rows.find((row) => id(row) === recordId), [rows, recordId]);
  const kind = text(selected?.outbox_type);
  const status = text(selected?.status);
  const action = kind === "email" ? `/integrations/email/${recordId}/send` : status === "pending_approval" ? `/integrations/outbox/${recordId}/approve` : status === "failed" ? `/integrations/outbox/${recordId}/retry` : `/integrations/outbox/${recordId}/dispatch`;
  const label = kind === "email" ? "Send approved message" : status === "pending_approval" ? "Approve external delivery" : status === "failed" ? "Retry delivery" : "Send to connected system";
  return <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Controlled external delivery</div><h3>Review before anything leaves GenuineGigs</h3><p>Only approved records can be sent. Every attempt is verified against the connected system and remains auditable.</p></div></div><div className="ops-form"><label>Approved record<select value={recordId} onChange={(event) => setRecordId(event.target.value)}><option value="">Select a record to review</option>{rows.map((row) => <option key={`${text(row.outbox_type)}-${id(row)}`} value={id(row)}>{text(row.subject || row.action || "External delivery")} · {text(row.status).replaceAll("_", " ")}</option>)}</select></label><button className="action-button" disabled={busy || !recordId || ["sent", "simulated", "dispatched"].includes(status)} onClick={() => void postAction(action, undefined, `${label} queued.`, version(selected))}>{label}</button></div></section>;
}

export function AdminManagementPanel({ workspaceData, postAction, busy }: CommonProps) {
  const users = workspaceData?.users ?? [];
  const roles = workspaceData?.roles ?? [];
  const plants = workspaceData?.plants ?? [];
  const departments = workspaceData?.departments ?? [];
  const [userId, setUserId] = useRouteSelection("user");
  const selectedUser = users.find((row) => id(row) === userId);

  function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void postAction("/org/users", {
      name: form.get("name"), email: form.get("email"), password: form.get("password"),
      role: form.get("role"), department_id: form.get("department_id"), plant_ids: [form.get("plant_id")],
      manager_id: form.get("manager_id") || null,
    }, "User and plant access created.");
  }

  function updateUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void postAction(`/org/users/${userId}`, {
      role: form.get("role"), is_active: form.get("is_active") === "on",
    }, "User role and access state updated.", version(selectedUser), "PATCH");
  }

  return <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Workspace team</div><h3>Create employee accounts and role agents</h3><p>Each person receives this workspace, plant access, the selected business role, and a governed role agent.</p></div></div><form className="ops-form" onSubmit={createUser}><label>Name<input name="name" required /></label><label>Work email<input name="email" type="email" required /></label><label>Temporary password<input name="password" type="password" minLength={12} required /></label><label>Business role<select name="role" required><option value="">Select role</option>{roles.map((role) => <option key={id(role)} value={id(role)}>{text(role.label)}</option>)}</select></label><label>Department<select name="department_id" required><option value="">Select department</option>{departments.map((department) => <option key={id(department)} value={id(department)}>{text(department.name)}</option>)}</select></label><label>Plant<select name="plant_id" required><option value="">Select plant</option>{plants.map((plant) => <option key={id(plant)} value={id(plant)}>{text(plant.name)}</option>)}</select></label><label>Reports to<select name="manager_id"><option value="">No manager in this workspace</option>{users.map((row) => <option key={id(row)} value={id(row)}>{text(row.name)} · {text(row.role).replaceAll("_", " ")}</option>)}</select></label><button className="action-button" disabled={busy}>Create account and agent</button></form><form className="ops-form" onSubmit={updateUser}><label>User<select value={userId} onChange={(event) => setUserId(event.target.value)}><option value="">Select user</option>{users.map((row) => <option key={id(row)} value={id(row)}>{text(row.name)} · {text(row.role)}</option>)}</select></label><label>Role<select name="role" defaultValue={text(selectedUser?.role)} key={text(selectedUser?.role)} required>{roles.map((role) => <option key={id(role)} value={id(role)}>{text(role.label)}</option>)}</select></label><label className="checkbox-label"><input name="is_active" type="checkbox" defaultChecked={selectedUser?.is_active !== false} key={`${userId}-${text(selectedUser?.is_active)}`} /> Active account</label><button className="action-button" disabled={busy || !userId}>Update user</button></form></section>;
}

export function WorkspaceSetupPanel({ workspaceData, postAction, busy, user }: CommonProps & { user: User }) {
  const setup = (workspaceData?.setup?.[0] ?? {}) as Row;
  const workspaces = workspaceData?.workspaces ?? [];
  const activeRoles = new Set(Array.isArray(setup.active_roles) ? setup.active_roles.map(String) : []);
  const requiredRoles = Array.isArray(setup.required_roles) ? setup.required_roles.map(String) : [];
  const members = Array.isArray(setup.members) ? setup.members as Row[] : [];
  const status = setup.onboarding_status ? text(setup.onboarding_status) : 'needs_team';
  const [workspaceError, setWorkspaceError] = useState('');

  async function createWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setWorkspaceError('');
    try {
      const created = await mutate<{ membership: { id: string }; workspace: { id: string; name?: string } }>('/workspaces', csrfToken(), {
        company_name: form.get('company_name'), workspace_name: form.get('workspace_name'),
        plant_name: form.get('plant_name'), plant_code: form.get('plant_code'), agent_enabled: true,
      });
      const selected = await mutate<{ csrf_token: string }>('/workspaces/select', csrfToken(), { membership_id: created.membership.id });
      window.localStorage.setItem('gg_csrf', selected.csrf_token);
      window.location.assign('/workspace/setup?workspace_created=1');
    } catch (caught) {
      setWorkspaceError(caught instanceof Error ? caught.message : 'Workspace creation failed');
    }
  }

  const checklist = [
    { label: 'Standard operating roles are ready', done: requiredRoles.every((role) => activeRoles.has(role)) },
    { label: 'Add at least one approved material', done: Number(setup.item_count ?? 0) > 0 },
    { label: 'Add at least one capable supplier', done: Number(setup.supplier_count ?? 0) > 0 },
  ];

  return <>
    <section className='action-panel workflow-action-panel'>
      <div className='panel-head compact-head'><div><div className='section-kicker'>Account workspaces</div><h3>Create or review a workspace</h3></div><span className='record-count'>{workspaces.length}</span></div>
      <div className='setup-invitations'>{workspaces.map((workspace) => <div className='setup-invitation-row' key={text(workspace.membership_id)}><div><strong>{text(workspace.workspace_name)}</strong><span>{text(workspace.plant_name)} / {text(workspace.role).replaceAll('_', ' ')}</span></div><span className={`status-pill ${workspace.selected ? 'good' : 'neutral'}`}>{workspace.selected ? 'Current' : 'Choose at sign in'}</span></div>)}</div>
      {user.role === 'admin' && <details className='fresh-workspace-form'><summary>Create another customer workspace</summary><form className='ops-form' onSubmit={createWorkspace}>
        <label>Company<input name='company_name' required /></label><label>Workspace<input name='workspace_name' required /></label><label>Plant<input name='plant_name' required /></label><label>Plant code<input name='plant_code' required /></label>
        <p className='form-note span-2'>You become the Admin owner. The workspace starts with no Apex demo users or transactions; add the real team below after creation.</p>
        <button className='action-button' disabled={busy}>Create clean workspace</button>
      </form></details>}
      {workspaceError && <div className='error-banner'>{workspaceError}</div>}
    </section>
    <section className='action-panel setup-readiness-panel'>
      <div className='panel-head compact-head'><div><div className='section-kicker'>Simple setup</div><h3>{status === 'complete' ? 'Workspace ready' : 'Complete master data'}</h3></div><span className={`status-pill ${status === 'complete' ? 'good' : 'action'}`}>{status.replaceAll('_', ' ')}</span></div>
      <div className='setup-checklist'>{checklist.map((step) => <div className={step.done ? 'done' : ''} key={step.label}><span aria-hidden='true'>{step.done ? '✓' : '○'}</span><strong>{step.label}</strong></div>)}</div>
    </section>
    <section className='action-panel workflow-action-panel'>
      <div className='panel-head compact-head'><div><div className='section-kicker'>Workspace team</div><h3>Employee accounts and role agents</h3><p>Only people explicitly added by an Admin can enter this workspace.</p></div><span className='record-count'>{members.length} active</span></div>
      <div className='setup-invitations'>{members.map((member) => <div className='setup-invitation-row' key={text(member.membership_id)}><div><strong>{text(member.name)}</strong><span>{text(member.role).replaceAll('_', ' ')}</span></div><span className='status-pill good'>Ready</span></div>)}</div>
      {user.role === 'admin' && <div className='button-row'><a className='action-button' href='/admin'>Add employee accounts</a></div>}
    </section>
    <MasterDataPanel workspaceData={workspaceData} postAction={postAction} busy={busy} user={user} />
  </>;
}

export function IntegrationActionPanel({ workspaceData, postAction, busy }: CommonProps) {
  const connections = workspaceData?.connections ?? [];
  const connectorCatalog = workspaceData?.connector_catalog ?? [];
  const mappingProfiles = workspaceData?.mapping_profiles ?? [];
  const poDrafts = workspaceData?.po_drafts ?? [];
  const rfqs = workspaceData?.rfqs ?? [];
  const documents = workspaceData?.documents ?? [];
  const [preview, setPreview] = useState<Row | null>(null);
  const [excelBusy, setExcelBusy] = useState(false);
  const [excelError, setExcelError] = useState("");
  const [mappingName, setMappingName] = useState("Customer procurement workbook");
  const [emailType, setEmailType] = useState<"quotation" | "invoice" | "po_acknowledgement" | "delivery_notice">("quotation");
  const emailUsesPo = emailType !== "quotation";
  const emailNeedsDocument = ["quotation", "invoice"].includes(emailType);
  const emailAcceptsDocument = emailNeedsDocument || emailType === "delivery_notice";
  function sync(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void postAction("/integrations/sync-jobs", { connection_id: form.get("connection_id"), job_type: form.get("job_type") }, "Asynchronous integration sync queued.");
  }
  function reconcile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void postAction("/integrations/reconciliation", { entity_type: "po_draft", entity_id: form.get("entity_id") }, "Purchase order reconciliation completed.");
  }
  function createConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    void postAction("/integrations/connections", { provider: form.get("provider"), name: form.get("name"), mode: form.get("mode"), enabled_capabilities: [] }, "Reference connection created with external writes disabled.");
  }
  function simulateInboundEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    void postAction("/integrations/email/inbound/simulate", {
      external_message_id: form.get("external_message_id"), sender_email: form.get("sender_email"),
      message_type: emailType,
      rfq_reference: emailType === "quotation" ? form.get("rfq_reference") : null,
      po_reference: emailUsesPo ? form.get("po_reference") : null,
      subject: form.get("subject"),
      body_preview: form.get("body_preview"), document_ids: emailAcceptsDocument && form.get("document_id") ? [form.get("document_id")] : [],
      acknowledgement_status: emailType === "po_acknowledgement" ? form.get("acknowledgement_status") : null,
      confirmed_quantity: emailType === "po_acknowledgement" ? Number(form.get("confirmed_quantity")) : null,
      confirmed_delivery: emailType === "po_acknowledgement" ? form.get("confirmed_delivery") : null,
      expected_quantity: emailType === "delivery_notice" ? Number(form.get("expected_quantity")) : null,
      expected_delivery: emailType === "delivery_notice" ? form.get("expected_delivery") : null,
      dispatch_reference: emailType === "delivery_notice" ? form.get("dispatch_reference") : null,
      vehicle_number: emailType === "delivery_notice" ? form.get("vehicle_number") : "",
      attachment_purpose: emailType === "delivery_notice" ? form.get("attachment_purpose") : "supplier_dispatch_document",
    }, emailType === "quotation" ? "Inbound quotation linked to buyer review." : emailType === "invoice" ? "Inbound supplier invoice linked to mandatory buyer verification." : emailType === "po_acknowledgement" ? "Supplier acknowledgement recorded on the canonical order." : "Supplier delivery notice recorded for Gate and Stores.");
  }
  async function previewWorkbook(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setExcelBusy(true); setExcelError("");
    try {
      const form = new FormData(event.currentTarget);
      const result = await apiFormFetch<Row>("/integrations/excel/preview", form, csrfToken());
      setPreview(result);
    } catch (error) { setExcelError(error instanceof Error ? error.message : "Could not inspect workbook"); }
    finally { setExcelBusy(false); }
  }
  const summary = (preview?.summary ?? {}) as Row;
  const discovery = (preview?.discovery ?? {}) as Row;
  const sheets = Array.isArray(discovery.sheets) ? discovery.sheets as Row[] : [];
  const rowIssues = Array.isArray(preview?.row_issues) ? preview.row_issues as Row[] : [];
  const requiredBySheet: Record<string, string[]> = { Organizations: ["external_key", "name"], Plants: ["external_key", "organization_external_key", "code", "name"], Users: ["external_key", "email", "name", "role", "plant_external_key"], ReportingLines: ["employee_external_key", "manager_external_key"], Items: ["external_key", "code", "name", "uom"], Suppliers: ["external_key", "name"], Requirements: ["external_key", "item_code", "quantity", "uom", "need_by_date", "reason"], OpenPOs: ["external_key", "supplier_external_key", "status"], OpenPOLines: ["external_key", "po_external_key", "item_external_key", "quantity", "uom", "unit_price", "need_by_date"], Receipts: ["external_key", "po_external_key", "received_quantity"], QualityStatus: ["external_key", "receipt_external_key", "status", "inspected_quantity", "accepted_quantity"], Invoices: ["external_key", "supplier_external_key", "po_external_key", "invoice_number", "invoice_date", "subtotal", "tax_amount", "total_amount"], InvoiceLines: ["external_key", "invoice_external_key", "po_line_external_key", "quantity", "uom", "unit_price", "line_total"], PaymentStatus: ["invoice_external_key", "status"] };
  const detectedMappings = Object.fromEntries(sheets.flatMap((sheet) => { const name = text(sheet.name); const headers = new Set(Array.isArray(sheet.headers) ? sheet.headers.map(text) : []); const required = requiredBySheet[name] ?? []; return required.length && required.every((field) => headers.has(field)) ? [[name, Object.fromEntries(required.map((field) => [field, field]))]] : []; }));
  return <>
    <section className="action-panel workflow-action-panel excel-connector-panel integration-step integration-step-one">
      <div className="panel-head compact-head"><div><div className="section-kicker">Excel / CSV external system</div><h3>Inspect before anything changes</h3><p>Upload XLSX, CSV, or a ZIP of CSV files. GenuineGigs shows mappings, row errors, duplicates, and conflicts first.</p></div><span className="status-pill good">New-version write-back</span></div>
      <div className="integration-intake-grid"><form className="ops-form" onSubmit={previewWorkbook}><label className="integration-file-drop">External-system file<input name="file" type="file" accept=".xlsx,.csv,.zip" required /><span>Choose a CSV, XLSX, or ZIP file up to 50 MB</span></label><label>Customer mapping<select name="mapping_profile_id"><option value="">Standard GenuineGigs workbook</option>{mappingProfiles.filter((row) => text(row.status) === "active").map((row) => <option key={id(row)} value={id(row)}>{text(row.name)} · v{text(row.profile_version)}</option>)}</select></label><button className="action-button" disabled={busy || excelBusy}>{excelBusy ? "Inspecting…" : "Preview import →"}</button></form><aside className="integration-checklist"><strong>We’ll check for</strong><span>✓ Column mapping and coverage</span><span>✓ Row-level validation errors</span><span>✓ Duplicates and potential conflicts</span><span>✓ Data type and format issues</span></aside></div>
      {excelError && <div className="error-banner" role="alert">{excelError}</div>}
      {preview && <div className="import-preview">
        <div className="metric-strip">{["insert", "update", "unchanged", "conflict", "error"].map((key) => <div key={key}><strong>{text(summary[key] ?? 0)}</strong><span>{key}</span></div>)}</div>
        <div className="setup-invitations">{sheets.map((sheet) => <div className="setup-invitation-row" key={text(sheet.name)}><div><strong>{text(sheet.name)}</strong><span>{text(sheet.row_count)} rows · {(Array.isArray(sheet.headers) ? sheet.headers : []).join(", ")}</span></div><span className={`status-pill ${sheet.recognized ? "good" : "neutral"}`}>{sheet.recognized ? "Mapped" : "Ignored"}</span></div>)}</div>
        {rowIssues.length > 0 && <div className="setup-invitations" aria-label="Import row issues">{rowIssues.map((issue) => <div className="setup-invitation-row" key={`${text(issue.sheet)}-${text(issue.row)}`}><div><strong>{text(issue.sheet)} · row {text(issue.row)}</strong><span>{(Array.isArray(issue.messages) ? issue.messages as Row[] : []).map((message) => text(message.message || message.code)).join("; ")}</span></div><span className="status-pill critical">{text(issue.action)}</span></div>)}</div>}
        <div className="mapping-save-row"><label>Mapping profile name<input value={mappingName} onChange={(event) => setMappingName(event.target.value)} /></label><button className="secondary-button" disabled={busy || !mappingName.trim() || !Object.keys(detectedMappings).length || !connections[0]} onClick={() => void postAction("/integrations/excel/mapping-profiles", { connection_id: id(connections[0]), name: mappingName, mappings: detectedMappings, transforms: {}, ownership: Object.fromEntries(Object.keys(detectedMappings).map((name) => [name, "external_owned"])) }, "Detected customer mapping saved as a new version.")}>Save detected mapping</button></div>
        <div className="button-row"><button className="action-button" disabled={busy || Number(summary.conflict || 0) > 0 || Number(summary.error || 0) > 0} onClick={() => void postAction(`/integrations/excel/imports/${text(preview.batch_id)}/approve`, undefined, "Approved rows imported with lineage and reconciliation.")}>Approve clean import</button><a className="secondary-button" href={apiUrl(`/integrations/excel/imports/${text(preview.batch_id)}/reconciliation.csv`)} download>Download row report</a></div>
      </div>}
      <div className="button-row"><button className="secondary-button" disabled={busy} onClick={() => void postAction("/integrations/excel/export", undefined, "A new versioned procurement exchange workbook is ready.")}>Create new export version</button></div>
    </section>
    <section className="action-panel workflow-action-panel integration-step integration-step-two">
      <div className="panel-head compact-head"><div><div className="section-kicker">Supplier email test channel</div><h3>Process verified supplier evidence</h3><p>Quotations, invoices, order responses, and delivery notices converge on the same canonical records as portal and manual paths.</p></div></div>
      <form className="ops-form" onSubmit={simulateInboundEmail}>
        <label>Message type<select value={emailType} onChange={(event) => setEmailType(event.target.value as typeof emailType)}><option value="quotation">Supplier quotation</option><option value="invoice">Supplier invoice</option><option value="po_acknowledgement">Order acknowledgement</option><option value="delivery_notice">Delivery notice / ASN</option></select></label>
        <label>External message ID<input name="external_message_id" required placeholder="MAIL-2026-0001" /></label>
        <label>Verified supplier sender<input name="sender_email" type="email" required placeholder="accounts@supplier.example" /></label>
        {emailType === "quotation" ? <label>Supplier request<select name="rfq_reference" required><option value="">Select request</option>{rfqs.map((row) => <option key={id(row)} value={text(row.business_number || row.id)}>{text(row.business_number || row.id)}</option>)}</select></label> : <label>Purchase order<select name="po_reference" required><option value="">Select order</option>{poDrafts.map((row) => <option key={id(row)} value={text(row.business_number || row.id)}>{text(row.business_number || row.id)}</option>)}</select></label>}
        {emailAcceptsDocument && <label>{emailNeedsDocument ? "Validated attachment" : "Validated dispatch evidence (optional)"}<select name="document_id" required={emailNeedsDocument}><option value="">{emailNeedsDocument ? "Select document" : "No attachment"}</option>{documents.filter((row) => !["quarantined", "rejected", "invalid"].includes(text(row.status))).map((row) => <option key={id(row)} value={id(row)}>{text(row.filename)}</option>)}</select></label>}
        {emailType === "po_acknowledgement" && <><label>Supplier response<select name="acknowledgement_status" required><option value="accepted">Accepted</option><option value="change_requested">Change requested</option><option value="rejected">Rejected</option></select></label><label>Confirmed quantity<input name="confirmed_quantity" type="number" min="0" step="0.001" required /></label><label>Confirmed delivery<input name="confirmed_delivery" type="date" required /></label></>}
        {emailType === "delivery_notice" && <><label>Expected quantity<input name="expected_quantity" type="number" min="0.001" step="0.001" required /></label><label>Expected delivery<input name="expected_delivery" type="date" required /></label><label>Dispatch reference<input name="dispatch_reference" required /></label><label>Vehicle number<input name="vehicle_number" /></label><label>Attachment type<select name="attachment_purpose"><option value="supplier_dispatch_document">Dispatch document</option><option value="supplier_certificate">Material certificate</option></select></label></>}
        <label>Subject<input name="subject" required /></label><label className="span-2">Message summary<textarea name="body_preview" maxLength={2000} /></label>
        <button className="action-button" disabled={busy || (emailNeedsDocument && !documents.length) || (emailType === "quotation" ? !rfqs.length : !poDrafts.length)}>Process supplier email</button>
      </form>
    </section>
    <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Connection safety</div><h3>Operating modes and emergency controls</h3><p>Writes remain separately disabled until customer acceptance. Disconnecting never blocks manual procurement work.</p></div></div><form className="ops-form" onSubmit={createConnection}><label>Connector<select name="provider" required>{connectorCatalog.map((connector) => <option key={text(connector.provider)} value={text(connector.provider)}>{text(connector.display_name)}</option>)}</select></label><label>Connection name<input name="name" required placeholder="Customer UAT connection" /></label><label>Initial mode<select name="mode" defaultValue="read_only"><option value="read_only">Read only</option><option value="simulation">Simulation</option><option value="shadow">Shadow</option><option value="uat">UAT / sandbox</option><option value="disconnected">Disconnected</option></select></label><button className="action-button" disabled={busy || !connectorCatalog.length}>Add safe connection</button></form><div className="business-card-grid">{connections.map((connection) => <article className="business-record-card" key={id(connection)}><div><strong>{text(connection.name)}</strong><span>{text(connection.provider)} · {text(connection.mode).replaceAll("_", " ")}</span><span className={`status-pill ${connection.writes_enabled ? "critical" : "good"}`}>{connection.writes_enabled ? "Writes enabled" : "Writes disabled"}</span></div><div className="button-row"><button className="secondary-button" disabled={busy || !connection.writes_enabled} onClick={() => void postAction(`/integrations/connections/${id(connection)}`, { writes_enabled: false }, "External writes disabled immediately.", version(connection), "PATCH")}>Disable writes</button><button className="secondary-button" disabled={busy || text(connection.mode) === "disconnected"} onClick={() => void postAction(`/integrations/connections/${id(connection)}`, { mode: "disconnected" }, "Connection disabled; manual workflows remain available.", version(connection), "PATCH")}>Disconnect</button></div></article>)}</div></section>
    <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Tested connector catalog</div><h3>Declared support, without inflated ERP claims</h3></div><span className="record-count">{connectorCatalog.length}</span></div><div className="setup-invitations">{connectorCatalog.map((connector) => <div className="setup-invitation-row" key={text(connector.provider)}><div><strong>{text(connector.display_name)}</strong><span>{(Array.isArray(connector.protocols) ? connector.protocols : []).join(" · ")} · {(Array.isArray(connector.tested_capabilities) ? connector.tested_capabilities : []).length} contract-tested capabilities</span></div><span className={`status-pill ${connector.live_customer_verified ? "good" : "neutral"}`}>{connector.live_customer_verified ? "Customer verified" : "Reference adapter"}</span></div>)}</div><div className="button-row"><a className="secondary-button" href={apiUrl("/integrations/connectors/conformance-report.csv")} download>Download acceptance report</a></div></section>
    <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">API and ERP connections</div><h3>Sync and reconcile governed connections</h3></div></div><form className="ops-form" onSubmit={sync}><label>Connection<select name="connection_id" required><option value="">Select connection</option>{connections.filter((row) => text(row.mode) !== "disconnected").map((row) => <option key={id(row)} value={id(row)}>{text(row.name)} · {text(row.mode)}</option>)}</select></label><label>Dataset<select name="job_type" required><option value="master_data">Master data</option><option value="material_needs">Material needs</option><option value="open_purchase_orders">Open purchase orders</option><option value="receipts">Receipts</option><option value="inspections">Inspections</option><option value="invoices">Invoices</option><option value="payment_status">Payment status (read only)</option></select></label><button className="action-button" disabled={busy}>Queue sync</button></form><form className="ops-form" onSubmit={reconcile}><label>Purchase order<select name="entity_id" required><option value="">Select PO</option>{poDrafts.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)} · {text(row.status)}</option>)}</select></label><button className="action-button" disabled={busy}>Reconcile status</button></form></section>
  </>;
}

export function InvoiceMatchingPanel({ workspaceData, postAction, busy }: CommonProps) {
  const orders = workspaceData?.po_drafts ?? [];
  const lines = workspaceData?.po_lines ?? [];
  const invoices = workspaceData?.invoices ?? [];
  const invoiceExtractions = workspaceData?.invoice_extractions ?? [];
  const matches = workspaceData?.invoice_matches ?? [];
  const paymentStatuses = workspaceData?.invoice_payment_statuses ?? [];
  const [poId, setPoId] = useState(text(orders[0]?.id));
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const order = orders.find((row) => id(row) === poId);
  const orderLines = lines.filter((row) => text(row.po_draft_id) === poId);
  function capture(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const line = orderLines.find((row) => id(row) === text(form.get("po_line_id")));
    if (!line || !order) return;
    const quantity = Number(form.get("quantity")); const unitPrice = Number(form.get("unit_price")); const taxRate = Number(line.gst_rate || 0);
    const lineTotal = quantity * unitPrice; const taxAmount = lineTotal * taxRate / 100;
    void postAction("/procurement/invoices", {
      supplier_id: order.supplier_id, po_draft_id: poId, invoice_number: form.get("invoice_number"),
      invoice_date: form.get("invoice_date"), currency: order.currency || "INR", total_amount: lineTotal + taxAmount,
      source: "manual", lines: [{ po_line_id: line.id, quantity, uom: line.uom, unit_price: unitPrice, line_total: lineTotal, tax_amount: taxAmount }],
    }, "Supplier invoice captured for deterministic matching.");
  }
  async function uploadInvoice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const selectedPo = text(form.get("po_draft_id"));
    form.set("linked_entity_type", "supplier_invoice_draft");
    form.set("linked_entity_id", selectedPo);
    setUploading(true);
    setUploadStatus("Uploading and validating the document…");
    try {
      const uploaded = await apiFormFetch<{ document: { id: string }; job?: { status?: string } }>("/documents/upload", form, csrfToken());
      for (let attempt = 0; attempt < 15; attempt += 1) {
        const detail = await apiFetch<{ job?: { status?: string }; invoice_extractions?: Row[] }>(`/documents/${uploaded.document.id}`);
        if (detail.job?.status === "failed") throw new Error("The invoice file did not pass document validation.");
        if (detail.invoice_extractions?.length) { window.location.reload(); return; }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
      }
      setUploadStatus("The file is safe and queued. Refresh after the document worker finishes extraction.");
    } catch (error) {
      setUploadStatus(error instanceof Error ? error.message : "Invoice upload failed. Your form values are unchanged.");
    } finally { setUploading(false); }
  }
  function verifyExtraction(event: FormEvent<HTMLFormElement>, extraction: Row) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const reviewedPoId = text(form.get("po_draft_id"));
    const reviewedOrder = orders.find((row) => id(row) === reviewedPoId);
    const reviewedLines = lines.filter((row) => text(row.po_draft_id) === reviewedPoId);
    const poLine = reviewedLines.find((row) => id(row) === text(form.get("po_line_id")));
    if (!reviewedOrder || !poLine) return;
    const quantity = Number(form.get("quantity"));
    const unitPrice = Number(form.get("unit_price"));
    const lineTotal = quantity * unitPrice;
    const taxAmount = Number(form.get("tax_amount"));
    void postAction(`/procurement/invoice-extractions/${id(extraction)}/verify`, {
      supplier_id: reviewedOrder.supplier_id, po_draft_id: reviewedPoId,
      invoice_number: form.get("invoice_number"), invoice_date: form.get("invoice_date"),
      currency: form.get("currency") || reviewedOrder.currency || "INR",
      total_amount: lineTotal + taxAmount, source: "upload",
      lines: [{ po_line_id: poLine.id, description: "Verified from supplier invoice", quantity,
        uom: poLine.uom, unit_price: unitPrice, tax_amount: taxAmount, line_total: lineTotal }],
    }, "Invoice evidence verified and captured for matching.");
  }
  return <>
    <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Document intake</div><h3>Upload a supplier invoice</h3><p>The file is quarantined, validated, and extracted. A buyer must verify every commercial value before matching.</p></div></div>
      <form className="ops-form" onSubmit={uploadInvoice}><label>Purchase order<select name="po_draft_id" required><option value="">Select order</option>{orders.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)}</option>)}</select></label><label className="span-2">Invoice file<input name="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.xlsx" required /></label><button className="action-button" disabled={busy || uploading}>{uploading ? "Validating…" : "Upload for review"}</button>{uploadStatus && <p className="form-note span-4" role="status">{uploadStatus}</p>}</form>
    </section>
    {invoiceExtractions.filter((row) => text(row.status) === "needs_review").map((extraction) => { const fields = (extraction.extracted_fields ?? {}) as Row; const extractionPoId = text(extraction.po_draft_id); const extractionOrder = orders.find((row) => id(row) === extractionPoId); const extractionLines = lines.filter((row) => text(row.po_draft_id) === extractionPoId); return <section className="action-panel workflow-action-panel" key={id(extraction)}><div className="panel-head compact-head"><div><div className="section-kicker">Human evidence review</div><h3>Verify extracted invoice</h3><p>Extracted values are suggestions, not posted business data.</p></div><span className="status-pill action">Needs review</span></div><form className="ops-form" onSubmit={(event) => verifyExtraction(event, extraction)} key={id(extraction)}><input type="hidden" name="po_draft_id" value={extractionPoId} /><label>Purchase order<input value={text(extractionOrder?.business_number || extractionPoId)} readOnly /></label><label>Order line<select name="po_line_id" required>{extractionLines.map((row) => <option key={id(row)} value={id(row)}>{text(row.quantity)} {text(row.uom)} · {text(row.unit_price)} each</option>)}</select></label><label>Invoice number<input name="invoice_number" defaultValue={text(fields.invoice_number)} required /></label><label>Invoice date<input name="invoice_date" type="date" defaultValue={text(fields.invoice_date)} required /></label><label>Currency<input name="currency" defaultValue={text(fields.currency || extractionOrder?.currency || "INR")} required /></label><label>Quantity<input name="quantity" type="number" min="0.001" step="0.001" defaultValue={text(fields.quantity)} required /></label><label>Unit price<input name="unit_price" type="number" min="0" step="0.01" defaultValue={text(fields.unit_price)} required /></label><label>Tax amount<input name="tax_amount" type="number" min="0" step="0.01" defaultValue={text(fields.tax_amount || 0)} required /></label><button className="action-button" disabled={busy || !extractionLines.length}>Verify and capture</button></form></section>; })}
    <section className="action-panel workflow-action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Invoice capture</div><h3>Link the supplier invoice to its order</h3><p>Amounts are matched against the issued order and received quantity. Payment is never released here.</p></div></div>
      <form className="ops-form" onSubmit={capture}><label>Purchase order<select required value={poId} onChange={(event) => setPoId(event.target.value)}><option value="">Select order</option>{orders.map((row) => <option key={id(row)} value={id(row)}>{text(row.business_number || row.id)} · {text(row.status)}</option>)}</select></label><label>Order line<select name="po_line_id" required>{orderLines.map((row) => <option key={id(row)} value={id(row)}>{text(row.quantity)} {text(row.uom)} · {text(row.unit_price)} each</option>)}</select></label><label>Supplier invoice number<input name="invoice_number" required /></label><label>Invoice date<input name="invoice_date" type="date" required /></label><label>Invoiced quantity<input name="quantity" type="number" min="0.001" step="0.001" required /></label><label>Unit price<input name="unit_price" type="number" min="0" step="0.01" required /></label><button className="action-button" disabled={busy || !orderLines.length}>Capture invoice</button></form>
    </section>
    <section className="action-panel"><div className="panel-head compact-head"><div><div className="section-kicker">Evidence-backed matching</div><h3>Invoice review</h3></div><span className="record-count">{invoices.length}</span></div><div className="business-card-grid">{invoices.map((invoice) => { const match = matches.find((row) => text(row.invoice_id) === id(invoice) && text(row.status) === "current"); const variances = (match?.variances ?? {}) as Row; const exceptions = Array.isArray(variances.exceptions) ? variances.exceptions.map((item) => text(item).replaceAll("_", " ")) : []; const payment = paymentStatuses.filter((row) => text(row.invoice_id) === id(invoice)).sort((left, right) => text(right.observed_at).localeCompare(text(left.observed_at)))[0]; return <article className="business-record-card" key={id(invoice)}><div><strong>{text(invoice.business_number || invoice.invoice_number)}</strong><span>{text(invoice.invoice_number)} · {text(invoice.currency)} {text(invoice.total_amount)}</span><span className={`status-pill ${text(invoice.status) === "matched" ? "good" : text(invoice.status).includes("exception") ? "critical" : "action"}`}>{text(invoice.status).replaceAll("_", " ")}</span>{exceptions.length > 0 && <span>Blocked by: <strong>{exceptions.join(", ")}</strong>. Correct the supplier/source workbook or receipt evidence, then rerun matching.</span>}{payment ? <span>External payment status: <strong>{text(payment.status).replaceAll("_", " ")}</strong> · observed {text(payment.observed_at)}</span> : <span>No external payment status synchronized</span>}</div><div className="button-row">{!match && <button className="small-action" disabled={busy} onClick={() => void postAction(`/procurement/invoices/${id(invoice)}/match`, undefined, "Invoice matched against canonical order and receipt evidence.")}>Run matching</button>}{match && text(match.result) === "matched" && <button className="small-action" disabled={busy} onClick={() => void postAction(`/procurement/invoice-matches/${id(match)}/finance-handoff`, undefined, "Finance review handoff prepared; no payment was released.")}>Prepare finance review</button>}{match && text(match.result) === "exception" && <button className="small-action" disabled={busy} onClick={() => void postAction(`/procurement/invoices/${id(invoice)}/match`, undefined, "Matching rerun against the latest corrected evidence.")}>Rerun after correction</button>}</div></article>; })}</div></section>
  </>;
}
