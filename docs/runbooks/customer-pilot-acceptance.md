# Customer Pilot Acceptance Pack

This document is the evidence template for a controlled GenuineGigs pilot. It
does not assert certification, regulatory compliance, or production acceptance.
Every acceptance row must identify the customer environment, evidence location,
reviewer, date, and result. Blank rows are not passed rows.

## 1. Deployment identity

| Field | Required value |
| --- | --- |
| Customer / workspace | |
| Environment | Excel pilot / read-only / shadow / UAT / limited write |
| Application image digest | |
| Migration revision | |
| Connector provider and adapter version | |
| Connection ID | |
| Mapping profile and version | |
| Agent provider, model, prompt, and policy version | |
| Customer owner | |
| GenuineGigs owner | |
| Acceptance window | |
| Rollback owner and contact | |

## 2. Data-flow inventory

Complete one row for every enabled flow. Anything not listed remains disabled.

| Source | Destination | Dataset/action | Direction | Fields or classification | Transport | Credential identity | Retention | System of record | Enabled mode |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Customer workbook | GenuineGigs | Approved pilot datasets | Inbound | Customer-approved columns | Private upload | Signed-in member | Customer policy | Customer workbook/ERP | |
| GenuineGigs | Customer workbook | Versioned approved exports | Outbound | Mapped business fields | Private download/exchange | Approved export operator | Customer policy | Customer workbook/ERP | |
| Customer ERP/API | GenuineGigs | Manifest-approved reads | Inbound | Mapped scoped fields | Customer-approved API/middleware | Read-only service identity | Customer policy | ERP | |
| GenuineGigs | Customer ERP/API | One approved draft/write action | Outbound | Approved payload only | Customer-approved API/middleware | Separate least-privilege writer | Customer policy | ERP | |
| User document | Private object storage | Quotations/certificates/invoices | Inbound | Business document | Signed private upload | Signed-in or supplier token | Customer policy | Customer-approved source | |
| GenuineGigs | Groq | Minimized language context | Outbound | Allowed role/context subset; no credentials | TLS API | Deployment provider key | Provider/customer agreement | GenuineGigs records remain authoritative | |
| GenuineGigs | Supplier channel | Approved communication | Outbound | Final immutable artifact and approved message | Email/portal | Controlled channel identity | Customer policy | Canonical procurement record | |

Prohibited flows:

- direct writes to ERP database tables;
- browser or model access to ERP, SMTP, object-store, or provider credentials;
- raw unrestricted tenant exports to the model;
- silent overwrite of source workbooks;
- an external write without authority, validation, idempotency, outbox,
  acknowledgement, read-after-write verification, and reconciliation;
- production use of a capability absent from the accepted connector manifest.

## 3. Permission matrix

The generated workspace configuration and live server authorization remain the
authoritative permission source. Attach their exports and record exceptions
below.

| Role | Read scope | Prepare | Confirm / decide | External consequence | Reporting scope |
| --- | --- | --- | --- | --- | --- |
| Plant Manager | Own plant and authorized team work | Requirements, follow-ups | Plant-authorized decisions | Only explicitly granted capabilities | Reporting descendants only |
| Purchase Executive | Assigned procurement scope | RFQ, quotation review, comparison preparation, supplier drafts | Non-commercial internal steps as allowed | Controlled supplier actions only after required approval | Own/assigned work |
| Purchase Manager | Authorized procurement and approvals | Recommendations, negotiation/award/PO proposals | Policy-authorized commercial decisions | Explicit confirmation and connector capability required | Authorized team scope |
| Gate Operator | Expected arrivals for own plant | Gate evidence | Gate receipt step | No commercial or ERP authority unless explicitly granted | Own plant |
| Store Manager | Own-plant receipt work | Receipt and shortage/damage evidence | Store disposition within policy | Controlled inventory consequence | Own plant |
| Quality Inspector/Manager | Assigned inspection evidence | Inspection, hold, rejection, CAPA evidence | Quality disposition within policy | Controlled quality/inventory consequence | Own plant/authorized team |
| Admin / implementation operator | Workspace configuration and accepted integrations | Mapping, connection and policy preparation | Administrative actions with audit | No business approval by virtue of administration alone | Explicit workspace scope |
| Supplier token holder | Token-bound RFQ/PO only | Quote, acknowledgement, delivery evidence | Own supplier response | No internal workflow or cross-supplier access | Single token-bound record |

Acceptance checks:

- [ ] forged tenant, plant, membership, record, and supplier-token IDs fail;
- [ ] reporting descendants are enforced server-side;
- [ ] read and write connector identities are separate;
- [ ] emergency connector disable and global ERP write disable are exercised;
- [ ] agent role tool list contains only capabilities accepted for that role;
- [ ] controlled actions require the correct proposal/confirmation and record
      version;
- [ ] manual workflows remain available with the agent/provider disabled.

## 4. Connector capability acceptance

Attach the generated connector conformance report. Copy only capabilities that
the customer has tested in this environment.

| Capability | Declared by manifest | Contract test | Customer endpoint test | Mode | Evidence | Accepted by |
| --- | --- | --- | --- | --- | --- | --- |
| Test connection | | | | | | |
| Read materials | | | | | | |
| Read suppliers | | | | | | |
| Read requirements | | | | | | |
| Read purchase orders | | | | | | |
| Read receipts | | | | | | |
| Read acknowledgement/invoice status | | | | | | |
| Prepare requisition/RFQ/PO draft | | | | | | |
| Attach approved document | | | | | | |
| Dispatch one accepted write | | | | | | |
| Read-after-write verification | | | | | | |
| Reconciliation | | | | | | |
| Emergency disable | | | | | | |

An unsupported, untested, or blank capability is not accepted. Oracle Fusion,
SAP S/4HANA, Dynamics 365, and Odoo manifests are reference boundaries until a
customer endpoint completes this table.

## 5. Mapping acceptance

For every dataset attach:

1. source workbook/API schema and immutable source hash;
2. mapping-profile version;
3. source-to-canonical field mapping;
4. required fields, types, units, currency, timezone, and enum rules;
5. stable external-key definition;
6. duplicate and tombstone policy;
7. stale-write/concurrency policy;
8. preview and row/cell validation report;
9. approved import identity and timestamp;
10. reconciliation and exception report.

The customer data owner must approve business semantics. GenuineGigs must not
infer customer-specific valuation, account, tax, purchasing-organization, or
inventory meanings.

## 6. Acceptance stages

### Excel-only

- [ ] Clean workspace is created without manual database inserts.
- [ ] Valid, invalid, duplicate, stale, partial, and conflicting workbooks are
      exercised.
- [ ] Multiple sheets, header discovery, mapping preview, dry run, approval,
      lineage, idempotent re-import, and row-level reports pass.
- [ ] The complete golden lifecycle reaches finance handoff without releasing
      payment.
- [ ] Controlled write-back creates a new workbook version.
- [ ] Read-after-write and round-trip reconciliation pass.
- [ ] Re-import creates zero duplicate business records.

### Read-only ERP

- [ ] Read-only credential cannot perform writes.
- [ ] Tenant/plant/company filters, cursors, pagination, rate limits, timezones,
      deletion semantics, and stable external keys are accepted.
- [ ] Initial and incremental sync reconcile with customer totals.
- [ ] Stale source and mapping failures remain visible exceptions.

### Shadow and UAT

- [ ] Every prepared write is compared with the customer-expected payload.
- [ ] Payload hash and semantic idempotency key are stable across retries.
- [ ] Timeout-after-commit recovery checks the external system before retry.
- [ ] External acknowledgement, read-after-write verification, and
      reconciliation are recorded.
- [ ] Emergency disable and rollback drills pass.

### Limited production write

- [ ] Exactly one workflow and connector capability is enabled.
- [ ] Customer approver, observer, support contact, and rollback owner are
      present.
- [ ] Least-privilege writer scope has been independently reviewed.
- [ ] Rate/value/plant/supplier limits and feature flags are recorded.
- [ ] First writes are reconciled synchronously with no ambiguous success.
- [ ] Broader write access remains disabled.

## 7. Incident and continuity drill record

Run each drill with a non-production or customer-approved test record.

| Drill | Trigger | Expected safe state | Evidence | Actual result | Owner / action |
| --- | --- | --- | --- | --- | --- |
| Model provider unavailable | Disable provider/agent | Manual workflows operate; no fabricated answer | | | |
| Connector unavailable | Disable endpoint | Outbox remains pending/exception; no false success | | | |
| Ambiguous timeout | Commit then time out | External lookup by semantic key before retry | | | |
| Duplicate request/retry | Replay identical action | One business effect | | | |
| Stale source update | Import older version | Newer canonical data protected | | | |
| Supplier email failure | Simulate bounce | Delivery state visible; controlled retry | | | |
| Emergency write stop | Disable connection/global write | New dispatch denied; reads/manual work continue | | | |
| Restore | Isolated database/object restore | Counts, hashes, migration and outbox reconcile | | | |
| Agent prompt injection | Malicious document text | Content remains untrusted; no tool escalation | | | |
| Cross-scope ID | Forged tenant/plant/token ID | Request denied and auditable | | | |

## 8. Security and penetration-test preparation

Provide the tester with architecture/data-flow diagrams, scoped accounts for
every role, supplier tokens, accepted endpoints, API contract, test tenant,
test documents/workbooks, and explicit rules of engagement. Never provide
production customer data or secrets.

Minimum test themes:

- authentication, session, CSRF, MFA, invitation, and account recovery;
- horizontal/vertical authorization and tenant/plant/supplier-token isolation;
- mass assignment, forged IDs, stale writes, idempotency and retry races;
- upload MIME/signature, filename, formula, archive/size and prompt injection;
- signed/private object access and token expiry;
- SSRF and connector endpoint/credential boundaries;
- agent unknown-tool, unauthorized-tool, false-success and context leakage;
- supplier communication and ERP consequence controls;
- log, metric, trace, export, error, and provider-payload redaction;
- dependency, secret, image and container findings.

Record each finding with severity, affected version, exploit evidence, owner,
remediation, regression test, retest result, and customer disposition. Any
critical scope leak, unauthorized mutation, uncontrolled communication, false
external success, duplicate write, credential exposure, or lost audit evidence
blocks release.

## 9. Support, SLA, and escalation agreement

Customer and GenuineGigs must agree on:

- support hours, channels, severity definitions and acknowledgement targets;
- customer business owner, IT/integration owner, security contact, and privacy
  contact;
- GenuineGigs incident commander, engineering owner, connector owner, and
  customer-success owner;
- evidence-preserving emergency-stop authority;
- maintenance, model/prompt/policy, connector, mapping and migration change
  windows;
- backup RPO/RTO targets and restore-test cadence;
- notification obligations and approved communication wording;
- data retention, deletion, legal hold and contract-exit export procedure.

Suggested severity policy for customer approval:

| Severity | Example | Immediate action |
| --- | --- | --- |
| P0 | Cross-tenant disclosure, unauthorized external write, credential exposure | Disable affected/global capability, preserve evidence, notify named contacts |
| P1 | Procurement blocked with no manual continuity, repeated reconciliation ambiguity | Disable affected connector action, use manual process, incident bridge |
| P2 | Degraded agent/extraction/integration with manual workaround | Route work manually, investigate during support window |
| P3 | Cosmetic or low-impact issue | Backlog with agreed target |

## 10. Sign-off

| Decision | Name / organization | Role | Date | Evidence/signature |
| --- | --- | --- | --- | --- |
| Business process accepted | | | | |
| Data mapping accepted | | | | |
| Security/privacy accepted | | | | |
| Connector mode/capabilities accepted | | | | |
| Operations/rollback accepted | | | | |
| Pilot go / no-go | | | | |

Acceptance is limited to the recorded environment, versions, mappings,
capabilities, roles, and operating mode. Any material change requires targeted
retesting and renewed acceptance.
