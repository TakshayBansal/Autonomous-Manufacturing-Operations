# Procurement V2 Release Architecture

## Canonical Ownership

~~~mermaid
flowchart LR
  R[Requirement<br/>Plant Manager or Purchase Executive] --> F[RFQ and supplier dispatch<br/>Purchase Executive]
  F --> Q[Quotation extraction and verification<br/>Purchase Manager]
  Q --> C[Comparison and recommendation<br/>Purchase Manager]
  C --> P[Plant Manager approval]
  C --> E[Purchase Executive approval]
  P --> O[Final PO confirmation<br/>Purchase Manager]
  E --> O
  O --> G[Gate arrival<br/>Gate Operator]
  G --> S[Quantity receipt<br/>Store Manager]
  S --> I[Disposition<br/>Quality Inspector]
~~~

Demand forecasting is intentionally outside this release. Requirements carry the human-provided material, quantity, UOM, need-by date, specification, and business reason.

## Artifact Boundary

GeneratedArtifact binds a PDF type, business entity, artifact version, source snapshot hash, document checksum, template version, generator, and finalization timestamp.

| Artifact | Draft behavior | Finalization authority | Final behavior |
| --- | --- | --- | --- |
| RFQ PDF | Watermarked preview; no dispatch | Purchase Executive publishes | Immutable PDF attached to controlled supplier email |
| Comparison PDF | Watermarked Manager preview | Manager submits for approval | Immutable version bound to both named approvals |
| PO PDF | Watermarked preview | Purchase Manager confirms after both approvals | Immutable supplier/ERP source document |

Preview and download endpoints never execute workflow mutations. Supplier email preparation, email dispatch, ERP approval, and ERP dispatch remain separate actions.

## Quotation Evidence

~~~mermaid
sequenceDiagram
  participant M as Purchase Manager
  participant API
  participant Store as Evidence storage
  participant Worker
  M->>API: Upload RFQ, supplier, and quotation document
  API->>Store: Quarantine original bytes
  API->>Worker: Validate and extract
  Worker->>Worker: PDF text, OCR fallback, deterministic parsing
  Worker->>Worker: Optional Groq structured extraction
  Worker->>API: Typed fields, page evidence, confidence, missing fields
  M->>API: Accept, correct, or reject each field
  API->>API: Mark quotation verified only after human review
~~~

Structured extraction is Pydantic validated. Uploaded text is untrusted and cannot alter tool permissions or system policy. The UI shows the source document beside extracted fields.

## Dual Approval

Submitting a comparison freezes a PDF and creates two ComparisonApprovalRequest records for the current version. Each request is bound to a named workspace membership.

- Commercial fields cannot be edited during approval.
- Approval order does not matter.
- One approval produces partially_approved.
- Both approvals produce approved.
- Either rejection requires rationale, invalidates the other pending request, and assigns revision to Purchase Manager.
- Resubmission creates a new comparison version; old decisions cannot authorize it.

## Controlled PO And Inbound Effects

Purchase Manager confirmation creates the final PO PDF and a pending ERP outbox proposal. It does not dispatch the proposal. A separate explicit action prepares the supplier email with the authorized PO attachment.

After approved ERP dispatch, one named Gate Operator task is created. Gate records PO, vehicle, challan, packages, arrival, notes, and optional ASN. Store cannot receive before Gate. Quality cannot inspect before Store.

## Role-Agent Scope

Each agent is bound to one workspace membership and receives server-assembled context for that member's work only.

| Role agent | Permitted assistance |
| --- | --- |
| Plant Manager | Objective decomposition, formal team status, approval explanation |
| Purchase Executive | Requirement clarification, RFQ drafting, approval evidence explanation |
| Purchase Manager | Extraction review, comparison, negotiation, PO preparation |
| Gate Operator | Issued-PO lookup and arrival checklist |
| Store Manager | Receipt checklist and discrepancy evidence |
| Quality Inspector | Inspection checklist, certificate review, disposition draft |
| Admin | Configuration diagnostics and policy explanation |

Agents cannot approve, publish RFQs, issue POs, dispatch email, post ERP data, update inventory, or approve master data. Agent responses are stored as validated readable blocks with sanitized Markdown fallback.

## Release Controls

- procurement_v2 gates V2 service entry points per tenant.
- agent_enabled requires deployment availability, tenant policy, and enabled member profile.
- Fresh workspace creation can atomically enable role agents; secrets remain deployment managed.
- Disabling workspace agents cancels active runs without disabling normal workflows.
- Every artifact, approval, handoff, email, outbox event, and denial is tenant/plant scoped and audited.
