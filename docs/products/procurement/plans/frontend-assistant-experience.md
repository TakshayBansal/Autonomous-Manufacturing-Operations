# GenuineGigs Frontend and Assistant Experience Redesign — Codex Execution Contract

> **Purpose:** Replace the confusing ERP-console presentation with a modern assistant-first manufacturing workspace while preserving the existing routes, permissions, APIs, and deterministic manual workflows.
>
> **Repository:** `C:\Users\Takshay\Desktop\Important\GenuineGigs`
>
> **Read first:** latest `HANDOFF.md`, then this file. Execute after `BACKEND_PLAN.md` APIs are complete or against their documented contracts.
>
> **Execution order:** Complete phases in order. Do not modify backend business rules while executing this plan.
>
> **Primary outcome:** A client can immediately understand the product: what needs attention, what the assistant has prepared, what tasks remain, what the team is waiting on, and how to complete procurement work manually or conversationally.

---

## 0. The screen must communicate the right product

The current UI looks like a legacy ERP console because it prioritizes navigation chrome, process stages, large counters, technical status labels, and forms before showing actual work. The redesign must communicate:

> “Every role has a capable plant assistant. It prepares work, explains tasks, coordinates handoffs, and shows the few decisions the employee must make.”

The underlying ERP-style workbenches remain available for detailed verification and manual fallback. They are not the first visual impression.

After this plan:

1. The first viewport shows actionable work, not generic metrics.
2. The assistant is permanently visible on large desktops and easy to open on smaller screens.
3. Tasks left, decisions, prepared artifacts, waiting items, and team follow-ups are explicit.
4. Navigation and notification badges show pending work by role.
5. Creating a requirement is simple in chat and simple manually.
6. Uploading quotations to the assistant produces a visible extraction/review/comparison flow equivalent to the manual workbench.
7. A newly created demo workspace provides a clear role-access/demo panel and can be selected from every role account.
8. Technical runtime concepts are hidden from ordinary users.

---

# 1. Non-negotiable implementation rules

1. **Patch the current frontend. Do not rewrite the app or create replacement `/v2` routes.**
2. Keep Next.js App Router, React, TypeScript, Lucide, existing API client/auth/session handling, and current CSS approach.
3. Do not add a UI framework, Tailwind migration, global state library, charting library, or new design system dependency.
4. Use existing backend routes and the contracts specified in `BACKEND_PLAN.md`.
5. Preserve server authorization. Hiding a navigation item is not an authorization fix.
6. Preserve all manual workflow pages and their business functionality.
7. The assistant and manual screens must display the same persisted records and artifacts.
8. Do not display mock counts, fake tasks, generated IDs, fake assistant success, dead controls, placeholders, or “coming soon.”
9. Do not show chain-of-thought, prompts, tool calls, checkpoints, raw runs, provider payloads, or database terminology.
10. Do not expose normal users to “outbox,” “role queue,” “receipt,” “checkpoint,” “tool call,” or “agent run” labels.
11. Do not use gradients, decorative AI art, glassmorphism, excessive animations, neon colors, or oversized empty cards.
12. Do not preserve the current layout merely by changing colors. Information architecture must change.
13. Do not refactor unrelated pages or API code.
14. Extract only small reusable presentation components where they reduce complexity.
15. Keep all controls keyboard accessible and visibly focused.
16. Preserve responsive behavior and improve it at the documented breakpoints.
17. Add/repair Playwright tests and capture verification screenshots.
18. Do not stop after creating components; wire them to real data and actions.
19. Do not report visual completion without checking desktop, tablet, and mobile sizes.
20. Complete all phase gates before reporting success.

---

# 2. Fixed information architecture

## 2.1 Normal role navigation

Use this visible navigation structure, filtered by role:

```text
My work
Team                     # managers only

Procurement
  Requirements
  RFQs
  Quotations
  Comparisons & approvals
  Purchase orders

Inbound
  Gate                    # relevant roles
  Store                   # relevant roles
  Quality                 # relevant roles

Administration           # Admin/owner only
Audit                     # Plant Manager/Admin only
```

Do not show `/agent` as a normal technical workspace. Agent execution appears through the assistant panel, prepared-work cards, task views, and approval cards. Keep the route compiling for administration/debug access if required, but remove it from normal role navigation.

Compatibility routes such as evidence, negotiations, cases, outbox, and integrations remain hidden unless a specific authorized business flow links to them.

## 2.2 Badge behavior

Show small role-scoped badges only when count is greater than zero:

```text
My work: total immediate action items
Requirements: assigned requirement tasks needing action
RFQs: drafts/publication decisions or responses requiring action
Quotations: extraction/verification work
Comparisons & approvals: review/approval decisions
Purchase orders: confirmation/acknowledgement actions
Inbound: gate/store/quality actions
```

Use the backend `badge_counts`. Do not derive conflicting counts separately in every component.

## 2.3 Page hierarchy

Every page follows:

```text
compact workspace header
page-specific title/actions
primary work content
optional contextual details
assistant panel or assistant drawer
```

Remove duplicate breadcrumb + oversized page title + descriptive paragraph + process rail combinations.

---

# 3. Application shell redesign

## 3.1 Desktop layout at width >= 1280px

Use this three-column structure:

```text
220–232px navigation | flexible main content | 360–400px assistant
```

Requirements:

- sidebar fixed/sticky within viewport;
- main content uses remaining width without a large empty region;
- assistant panel is open by default and contained within the grid;
- user may collapse assistant; main content expands immediately;
- no floating full-width “Open contextual assistant” banner;
- maximum main reading width is applied only to text-heavy content, not dashboards/tables;
- page background is neutral light grey, cards are white.

## 3.2 Medium layout at 900–1279px

- sidebar collapses to compact icon rail or opens as a drawer;
- assistant becomes a right drawer opened by a consistent `Ask assistant` control;
- main content uses the full available width;
- no reserved blank area for a closed assistant;
- page must not horizontally overflow.

## 3.3 Mobile layout below 900px

- top app bar with menu, workspace/role, notifications, and assistant action;
- attention items and tasks appear before metrics or process details;
- assistant opens full-height and retains the current work-item context;
- tables use responsive cards or controlled horizontal scrolling;
- primary actions remain visible and at least 44px high;
- no fixed desktop sidebar.

## 3.4 Compact header

Replace the large current heading region with:

```text
Good morning, Ananya
Plant Manager · Pune Plant
3 items need your attention today
```

Right side:

```text
workspace/role selector
search / Ctrl+K
notification bell
user menu
```

Remove prominent `Role queue active`. Show `Simulated ERP` only as a small non-production environment badge near workspace settings or in Admin.

---

# 4. Visual system

Implement these CSS variables in `apps/web/app/globals.css` and replace conflicting old variables incrementally:

```css
--app-bg: #f4f6f8;
--surface: #ffffff;
--surface-subtle: #f8fafc;
--surface-selected: #fff7ed;
--sidebar: #151c24;
--sidebar-hover: #202b37;
--sidebar-active: #2a3946;
--text: #17202a;
--text-muted: #667085;
--text-soft: #8a94a3;
--border: #e1e6ec;
--border-strong: #cbd3dc;
--primary: #e66b22;
--primary-hover: #c95615;
--primary-soft: #fff0e6;
--success: #14805e;
--success-soft: #e9f7f1;
--warning: #a76512;
--warning-soft: #fff5df;
--danger: #c23b35;
--danger-soft: #fdeceb;
--info: #2868c7;
--info-soft: #edf4ff;
--shadow-sm: 0 1px 2px rgba(16, 24, 40, 0.05);
--shadow-md: 0 8px 24px rgba(16, 24, 40, 0.08);
--radius-sm: 6px;
--radius-md: 10px;
--radius-lg: 14px;
```

Typography:

- retain IBM Plex Sans or current sans stack;
- body 14–16px with comfortable line height;
- page heading 26–30px;
- section heading 16–20px;
- use uppercase letter-spaced labels only for rare metadata, never for every section;
- use monospace only for operational IDs, codes, and tabular numbers.

Card rules:

- avoid one giant border around every section;
- use white surfaces, subtle borders, and small shadows;
- default padding 16–20px;
- default section gap 16px;
- use status color only where it communicates meaning;
- no colored top border on every metric;
- avoid excessive pure black bold text.

---

# 5. My Work — the primary product homepage

Route: `/control-centre` and `/`.

The first viewport at 1440×900 must show real actionable content and the assistant composer.

## 5.1 Main content order

Render these sections in this exact priority:

1. **Needs your attention**
2. **Assistant prepared**
3. **My tasks** and **Waiting on others**
4. **Team follow-ups** for managers
5. compact operational summary and recent activity below the primary work

Do not begin with a seven-stage process rail, four large counters, cycle selector, or delegation form.

## 5.2 Needs your attention

Use backend `attention_items`. Each card contains:

```text
business title
linked record ID and short description
why action is needed
owner/requester
due/age
risk or impact
one primary action
one optional secondary action
```

Examples:

```text
Comparison approval required
RFQ-2026-0031 · Aluminium Ingot
Recommended supplier: Bharat Metals
Due today at 4:00 PM
[Review recommendation]
```

```text
Quotation fields need verification
Bharat Metals · 2 uncertain fields
Payment terms and promised delivery date
[Review quotation]
```

Urgent cards may use a narrow left status bar or soft tinted background. Do not make every card red/orange.

## 5.3 Assistant prepared

Show work generated or prepared by the assistant but awaiting review/confirmation:

- requirement draft;
- RFQ draft/PDF;
- extracted quotation review;
- supplier comparison;
- supplier follow-up draft;
- PO confirmation proposal;
- task/team summary.

Card example:

```text
Supplier comparison prepared
BC-2026-0018 · 3 verified quotations
Bharat Metals recommended · 2 risks identified
[Review comparison] [Ask assistant]
```

Use existing proposals, artifacts, receipts/results, and task links. Do not display runtime statuses such as run/checkpoint.

## 5.4 My tasks

Always show an explicit task section with tabs or compact filters:

```text
To do
In progress
Blocked
Completed
```

Each task row/card shows:

```text
title
record/context
due date
priority
expected output
status
primary next action
```

Above the list, display plain language:

> “You have 4 tasks left: 1 due today and 1 blocked.”

Do not show an empty oversized form when no task is selected.

## 5.5 Waiting on others

Show items the current user delegated or cannot continue until another role acts:

```text
Waiting for Meera Iyer
Collect supplier quotations · RFQ-0034
2 of 3 responses received · Due tomorrow
[Request update]
```

## 5.6 Team follow-ups

Managers only. Show direct/formal descendants with work status, not private conversations:

```text
Vikram Shah
1 overdue · 2 on track
Comparison BC-0018 is awaiting review
[View work] [Request update]
```

Hide this section for non-managers.

## 5.7 Compact summary

Below primary work, use a single compact strip or small cards:

```text
2 critical risks | 1 approval today | 3 overdue tasks | 4 supplier responses pending
```

Use business language. Never show “outbox waiting” as a homepage metric.

---

# 6. Assistant panel — the visual heart of the product

## 6.1 Persistent panel

At desktop widths, render a polished right-side `Role Assistant` panel open by default.

Panel header:

```text
Ananya’s Plant Assistant
Plant Manager · Pune Plant
online / limited mode / unavailable
```

Provider/model names are not shown to normal users. `Limited mode` may be explained as “Manual workflows remain available; some natural-language features are temporarily limited.”

## 6.2 Context chip area

Show current context compactly:

```text
Pune Plant
RFQ-2026-0031
Comparison approval
```

Allow removing/switching the selected work item. Do not dump internal context JSON.

## 6.3 Conversation design

Messages use readable bubbles/cards with clear author distinction. Avoid repeated bordered blocks and repeated headings.

Assistant responses may render:

- natural-language summary;
- clarification choices;
- created-record card;
- task card;
- approval card;
- artifact preview card;
- extracted-fields review card;
- warning/missing-information card.

Success card example:

```text
Requirement created
PR-2026-0042
Aluminium Ingot · 100 KG
Need by 16 Aug 2026
Assigned to Meera Iyer
[Open requirement] [Prepare RFQ]
```

## 6.4 Composer

The composer stays visible at the bottom and includes:

```text
multiline text input
attachment button
send button
optional contextual command chips
```

Placeholder:

> `Ask your plant assistant to prepare, explain, delegate, or follow up…`

Support drag/drop and file picker for PDF, PNG, JPG/JPEG, XLSX according to backend validation.

Before upload, show selected filenames and removal controls. After upload, show validation/progress/status.

## 6.5 Suggested actions

Suggestions are role- and context-aware, sourced from `allowed_actions`, for example:

Plant Manager:

```text
Summarize material risks
Show overdue team work
Create a requirement
Explain this comparison
```

Purchase Manager:

```text
Compare uploaded quotations
Show fields needing review
Prepare supplier follow-ups
Show delayed deliveries
```

Do not show actions the user cannot perform.

## 6.6 Loading and errors

Use honest states:

- `Understanding your request…`
- `Uploading 3 files…`
- `Extracting quotation fields…`
- `Waiting for your verification…`
- `Comparison prepared.`

Never show indefinite “working” after the server response completes. For real background jobs, show progress/status and a refresh/retry action.

Errors must include what failed, what was preserved, and a safe next action. Do not clear the composer or attachments on recoverable failure.

---

# 7. Requirement creation redesign

## 7.1 Conversational path

The assistant is the fastest path. Natural conversation should produce a confirmation or persisted record card. Follow-up references use the current work item.

Do not display a rigid field-by-field chatbot transcript. When two or more details are missing, render a compact inline completion card containing only missing fields.

Example:

```text
I found the approved material ALI-101. Add the remaining details:
[Need-by date] [Purchase Executive]
[Create requirement]
```

## 7.2 Manual path

Keep `/procurement`, but simplify the form:

- one clear `New requirement` primary action;
- open the form in a focused page section or side sheet, not as a permanent large block above the ledger;
- searchable approved material combobox showing code, name, UOM, and specification;
- quantity and UOM grouped;
- need-by date with useful date input;
- reason/purpose;
- assigned Purchase Executive;
- optional advanced section for specification and inspection;
- multiple lines remain available through `Add material line`;
- clear missing-master action when no item matches.

Show a concise preview before submission when useful. After creation, show the same record card/details as the assistant path.

## 7.3 Missing material

When no approved material exists:

- show `Request new material` in the assistant and combobox empty state;
- prefill proposed code/name/UOM/reason from current input;
- explain that approval adds the master item and does not yet create the requirement;
- avoid dead-end text telling the user to navigate elsewhere.

---

# 8. Quotation upload and comparison redesign

## 8.1 Agentic path

Within the assistant:

1. user selects/mentions an RFQ;
2. uploads quotation documents;
3. assistant displays one attachment card per supplier/document;
4. extraction progress appears;
5. uncertain fields appear in an embedded review card;
6. after verification, `Prepare comparison` generates the canonical comparison;
7. comparison card displays recommendation, landed-cost summary, risks, and artifact;
8. controlled `Submit for approval` action remains explicit.

Do not force the user to leave chat merely to see progress or the result. `Open full workbench` is available for detailed verification.

## 8.2 Manual quotations page

Route `/quotes` must use a modern workbench:

```text
left: quotation/RFQ list and filters
center: source document preview
right: extracted fields and verification
```

At narrower widths, use stacked tabs. Clearly distinguish:

```text
Extracting
Needs review
Verified
Rejected
```

For each field show value, confidence only when helpful, source evidence/page, and edit/accept/reject controls. Do not expose parser/model version as primary UI.

## 8.3 Comparison page

Route `/comparison` uses:

- compact RFQ/context header;
- supplier comparison table;
- recommendation summary;
- risk/deviation panel;
- source/evidence access;
- version and approval status;
- PDF preview/download;
- clear primary action based on state.

Use color carefully. Lowest cost is not automatically green if disqualified. Recommended supplier receives a clear but restrained highlight.

At mobile width, use supplier cards rather than an unreadable full comparison table.

---

# 9. Workflow pages

Keep existing routes, but apply consistent structure:

## Requirements

- search/filter and concise ledger;
- status, item count, need-by, assignee, current stage, next action;
- focused create flow;
- no permanent huge form before records.

## RFQs

- draft/published/responses state;
- supplier response progress;
- preview/download/publish actions clearly separated;
- draft preview cannot look identical to final publication.

## Approvals

- show decision summary first;
- recommendation, cost, delivery, compliance, risks, rationale, and version;
- source comparison/PDF available;
- approve/reject controls with required rationale rules;
- no technical proposal terminology.

## Purchase orders

- status and supplier acknowledgement;
- preview/download/email/ERP effects separated visibly;
- simulation/live environment clearly but unobtrusively indicated.

## Gate, Store, Quality

- role-specific queue first;
- selected delivery context second;
- focused entry form third;
- clear handoff status and next role;
- no unrelated procurement administration.

---

# 10. Notifications and task visibility

## 10.1 Header notification bell

Show unread count. Popover sections:

```text
Needs action
Updates
System
```

Each item includes title, short context, age, and navigation target. Support mark-read and mark-all-read.

Do not show every low-value audit event as a notification.

## 10.2 Navigation badges

Use compact circular/pill badges, maximum display `99+`. Red only for overdue/critical; use neutral/amber for normal pending work.

Counts update after relevant assistant/manual mutations without a full-page reload. Use existing client fetching patterns; do not add a global state library.

## 10.3 Task detail

Opening a task shows:

```text
requested outcome
why it matters
linked record/evidence
expected output
due date/priority
owner/requester
blocker or waiting role
activity summary
available transitions
assistant composer in task context
```

Do not execute an action simply because a task is opened.

## 10.4 Delegation

Remove the full delegation form from the homepage. Replace it with:

- `Delegate work` button;
- natural-language assistant delegation;
- compact side sheet for manual structured entry.

The review step shows parsed assignee, due date, priority, linked work, and expected output before creating the task when ambiguity exists.

---

# 11. Demo workspace and role access UI

## 11.1 After workspace creation

Show a success page/section:

```text
Client Demo Plant is ready
7 role seats connected to this workspace
```

Display role cards:

```text
Plant Manager — Ananya Rao — Ready
Purchase Manager — Vikram Shah — Ready
Purchase Executive — Meera Iyer — Ready
Gate Operator — Sanjay Patil — Ready
Store Manager — Rohit Kulkarni — Ready
Quality Inspector — Farhan Ali — Ready
Admin — Neha Kapoor — Ready
```

In server-confirmed demo mode only, show the standard demo email and development password guidance with copy controls. Never expose this section in production mode.

Include:

- `Open workspace`;
- `View demo role access`;
- `Invite real employee`;
- readiness for approved material and capable supplier.

## 11.2 Login/workspace selection

When an account has several memberships, show cards containing:

```text
workspace/company
plant
role
readiness/environment
```

The newly created workspace must appear for each standard demo account after backend reconciliation.

For development demo quick-fill, present role buttons clearly but do not create insecure production impersonation.

## 11.3 Workspace switcher

Header switcher shows current workspace, plant, and role. Switching uses the existing membership-selection flow and refreshes role-scoped navigation, badges, assistant thread/context, and data.

---

# 12. User-facing language replacements

Apply these replacements throughout normal user interfaces:

| Avoid | Use |
| --- | --- |
| Role queue | My work |
| Agent run | Assistant activity / work in progress |
| Proposal | Needs your confirmation / prepared action |
| Receipt | Completed action / result |
| Tool call | Do not display |
| Checkpoint | Do not display |
| Outbox waiting | Supplier messages waiting / ERP actions waiting |
| Objective | Requirement or task, according to record |
| Not delegated yet | No task has been assigned yet |
| Still needed | Add these details |
| Answer | Omit heading |
| Role ownership | Explain only when relevant |

Keep exact procurement IDs and official statuses where operationally necessary, but pair unfamiliar status codes with plain language.

---

# 13. File-level implementation map

Patch first:

```text
apps/web/components/industrial/IndustrialConsole.tsx
apps/web/components/features/WorkflowForms.tsx
apps/web/components/AgentDrawer.tsx
apps/web/components/AgentWorkspace.tsx
apps/web/components/WorkspaceCommandPalette.tsx
apps/web/lib/api.ts
apps/web/app/globals.css
apps/web/app/control-centre/page.tsx
apps/web/app/procurement/page.tsx
apps/web/app/quotes/page.tsx
apps/web/app/comparison/page.tsx
apps/web/app/approvals/page.tsx
apps/web/app/workspace/setup/page.tsx
apps/web/e2e/role-workflows.spec.ts
```

If `AgentDrawer.tsx` or `AgentWorkspace.tsx` lives under a slightly different directory, patch the existing file rather than duplicating it.

Create at most these focused components if the current monolith is difficult to patch cleanly:

```text
apps/web/components/industrial/WorkspaceHeader.tsx
apps/web/components/industrial/AttentionCard.tsx
apps/web/components/industrial/AssistantPanel.tsx
apps/web/components/industrial/TaskSections.tsx
apps/web/components/industrial/NotificationPopover.tsx
apps/web/components/industrial/DemoRoleAccess.tsx
apps/web/components/industrial/RecordActionCard.tsx
```

Do not create a parallel component tree or duplicate the full console.

---

# 14. Phased execution

## Phase F0 — Baseline screenshots and behavior inventory

1. Run existing typecheck/build/E2E baseline.
2. Capture current screenshots at 1440×900, 1280×800, 1024×768, 768×1024, and 390×844.
3. Identify current data sources for My Work, tasks, assistant, notifications, and workspace setup.
4. Add failing E2E assertions for the new above-fold and assistant requirements.

**Gate:** Baseline is recorded and new expectations fail before changes.

## Phase F1 — Visual tokens and application shell

1. Implement new CSS variables and base typography/surfaces.
2. Reduce desktop sidebar to 220–232px.
3. Implement three-column layout and assistant collapse behavior.
4. Implement medium/mobile navigation and assistant drawer.
5. Replace oversized header and remove assistant launcher banner.

**Gate:** No large unused region; no horizontal overflow at required sizes.

## Phase F2 — My Work and notifications

1. Build ordered homepage sections using real `/workspace/home` data.
2. Add badge counts, notification bell/popover, and task summary.
3. Move full delegation form into side sheet/action.
4. Add manager team follow-ups and waiting-on-others.
5. Remove process rail and cycle selector from general homepage.

**Gate:** At least one actionable item and assistant composer are visible above the fold at 1440×900.

## Phase F3 — Assistant experience

1. Implement persistent assistant panel and responsive drawer.
2. Render typed business cards and attachment states.
3. Wire suggestions, current context, created records, proposals/confirmations, and errors.
4. Remove runtime jargon and repeated policy boilerplate.
5. Preserve conversation and attachments during navigation/context changes where current architecture permits safely.

**Gate:** Requirement creation and ID follow-up are clear, concise, and grounded in UI.

## Phase F4 — Requirement and workspace demo flows

1. Simplify the manual requirement flow.
2. Implement missing-material action.
3. Add demo role access/readiness UI after workspace creation.
4. Improve login membership cards and workspace switcher.
5. Confirm each role enters the same new workspace with role-specific UI.

**Gate:** Client demo can move across role accounts without confusion.

## Phase F5 — Quotations and comparison

1. Complete assistant attachment/review/comparison cards.
2. Redesign manual quote verification workbench.
3. Redesign comparison/approval presentation.
4. Confirm assistant-created comparison is immediately visible in manual records.
5. Verify controlled approval/submit flows and artifact preview.

**Gate:** Three uploaded quotations can be taken from assistant upload to visible canonical comparison.

## Phase F6 — Responsive, accessibility, regression

1. Verify keyboard navigation, focus, labels, contrast, live status, and error association.
2. Fix desktop/tablet/mobile layouts.
3. Run full E2E and production build.
4. Capture final screenshots at all baseline sizes.
5. Compare against the acceptance checklist below.

**Gate:** All required checks pass with no regression in manual workflows.

---

# 15. Visual and functional acceptance checklist

## 15.1 At 1440×900

- [ ] Sidebar is no wider than 232px.
- [ ] Assistant is visible and usable without clicking a large launcher.
- [ ] Main content fills available width without a blank right region.
- [ ] At least one complete actionable card is above the fold.
- [ ] Assistant composer is above the fold.
- [ ] Tasks left are stated explicitly.
- [ ] No process rail appears until a specific cycle/record context is selected.
- [ ] No permanent delegation form consumes homepage space.
- [ ] No normal-user runtime jargon appears.
- [ ] No more than three primary visual regions compete in the first viewport.

## 15.2 At 1024×768

- [ ] Main content uses full width.
- [ ] Assistant opens as drawer.
- [ ] Navigation is compact/drawer-based.
- [ ] No page-level horizontal overflow.
- [ ] Primary actions remain visible.

## 15.3 At 390×844

- [ ] Needs-attention items appear first.
- [ ] Notification and assistant controls remain reachable.
- [ ] Composer is usable with the virtual-keyboard-safe layout.
- [ ] Tables/cards do not clip controls.
- [ ] Touch targets are at least 44px.

## 15.4 Business behavior

- [ ] New demo workspace is clearly accessible by every configured role account.
- [ ] Requirement creation returns a visible exact PR ID.
- [ ] “What is its ID?” shows the same record card/ID.
- [ ] Assistant upload accepts quotation files and displays progress.
- [ ] Extraction uncertainty is visibly reviewable.
- [ ] Generated comparison appears in both assistant and manual workbench.
- [ ] Approval notifications and badges update.
- [ ] Manual workflow remains usable when assistant/provider is unavailable.

---

# 16. Required tests and commands

Run:

```powershell
git diff --check
npm run check:api-contract
npm run typecheck
npm run build:web
npm run test:e2e
```

Run targeted Playwright coverage for:

```text
My Work desktop above-fold layout
assistant persistent panel and responsive drawer
notification bell and nav badges
explicit task sections
natural-language requirement creation UI
created requirement card and ID follow-up
missing-material request action
demo workspace role access UI
workspace membership selection
assistant quotation attachments
quotation extraction review
canonical comparison visibility
approval card and notifications
manual fallback/provider unavailable state
mobile and tablet overflow/accessibility
```

Capture final screenshots to a stable test-artifact directory and mention their paths in the completion report. Do not add screenshots to source control unless the current test convention does so.

---

# 17. Client demo script

The final UI must support this sequence without explaining internal architecture:

## Scene 1 — Plant Manager workspace

1. Sign in as Plant Manager.
2. Create `Client Demo Plant`.
3. Show that all seven role seats are ready.
4. Open My Work.
5. Show decisions, tasks left, team follow-ups, and the visible assistant.

## Scene 2 — conversational requirement

```text
Create a raw-material requirement for 100 kg of Aluminium Ingot, needed one month from today.
```

Show the exact persisted PR ID and next actions. Ask:

```text
What is its ID?
```

The same ID appears immediately. Prepare the RFQ through the available action.

## Scene 3 — role access

1. Sign out.
2. Sign in as Purchase Executive.
3. Select `Client Demo Plant`.
4. Show the assigned requirement/task and role-specific assistant.
5. Prepare/preview the RFQ without exposing unauthorized actions.

## Scene 4 — quotation comparison

1. Sign in as Purchase Manager and select the same workspace.
2. Open the assistant with the RFQ in context.
3. Upload three quotation files.
4. Ask for a comparison.
5. Verify uncertain extraction fields.
6. Show comparison recommendation, risks, PDF, and manual workbench equivalence.
7. Submit for approval.

## Scene 5 — approvals

1. Sign in as Plant Manager and then Purchase Executive.
2. Show notification badge and decision card.
3. Review the same frozen comparison version.
4. Complete controlled decisions.

The UI must not display development/runtime jargon during this script.

---

# 18. Completion report format

Codex must finish with exactly:

```text
Implemented
- ...

Files changed
- ...

Screenshots checked
- viewport/path: result

Tests run
- command: result

Client demo scenarios
- My Work and assistant: PASS/FAIL
- Demo workspace role access: PASS/FAIL
- Requirement creation and ID follow-up: PASS/FAIL
- Quotation upload/comparison: PASS/FAIL
- Approval notifications: PASS/FAIL
- Responsive/manual fallback: PASS/FAIL

Remaining blockers
- None
```

If any phase gate or acceptance item fails, report it honestly and do not call the redesign complete.
