# GenuineGigs V2 — UI/UX Master Plan

> **Document purpose:** This file is the design and interaction contract for GenuineGigs V2. It defines how the product must look, feel, behave, guide users, communicate operational urgency, and simplify factory work.
>
> **Critical instruction to Codex:** Do not treat this as a generic dashboard brief. GenuineGigs must **not** look like a traditional ERP, a template SaaS dashboard, or a collection of CRUD tables. The UI must communicate operational state visually, minimize cognitive load, surface only what matters to each person, and make the next action obvious.
>
> The product is intended to become the day-to-day operating surface for manufacturing teams. A user should not need to constantly jump between SAP/Tally/Excel/email/WhatsApp/BI dashboards just to understand what is happening and what they need to do.
>
> The UI should feel **premium, calm, operational, modern, trustworthy, visual, fast, and intelligent**.

---

# 1. UX North Star

The user should be able to open GenuineGigs and understand within seconds:

1. **What is happening right now?**
2. **What is not going according to plan?**
3. **Why does it matter?**
4. **What requires my attention?**
5. **What is GenuineGigs already handling for me?**
6. **What do I need to do next?**

The UI should never force the user to first understand how the software is organized before they can understand their work.

The fundamental UX promise is:

> **GenuineGigs should reduce the amount of reality a manufacturing employee has to manually monitor.**

---

# 2. Core Design Philosophy

## 2.1 Do not recreate ERP navigation

Avoid UI patterns like:

```text
Masters
Transactions
Purchase
Sales
Inventory
Production
Maintenance
Reports
Administration
```

That is software-centric navigation.

GenuineGigs should be **work-centric and outcome-centric**.

The product should organize itself around:

- What needs attention
- What is running
- What is at risk
- What is waiting
- What is blocked
- What has changed
- What requires a decision
- What can be improved

## 2.2 Visual first, tables second

Tables are necessary for detail. They should not be the primary experience.

Prefer:

- timelines,
- flow diagrams,
- loss trees,
- progress paths,
- status lanes,
- risk maps,
- dependency graphs,
- production curves,
- readiness indicators,
- causal chains,
- event timelines,
- visual process cards.

Use tables only when the user needs density, sorting, filtering, or exact comparison.

## 2.3 Progressive disclosure

The system should not show everything at once.

Hierarchy:

```text
Summary
→ Important deviation
→ Context
→ Evidence
→ Raw data
```

Example:

A Plant Head should first see:

> Line 3 is projected to miss plan by 640 units.

Not:

> 42 KPI cards + 11 charts + 84 alerts.

If they click the deviation:

> 43 minutes downtime + material delay + elevated rejection.

Then if needed:

> raw event history, machine tags, work order, quality records.

## 2.4 Role-aware interface

The interface should adapt to who is using it.

A Plant Head, Maintenance Engineer, Buyer, Operator, and Quality Manager should not see the same home screen.

The underlying data is shared. The presentation is role-specific.

## 2.5 Exception-driven operations

Normal operation should visually recede. Problems should become obvious.

The UI should answer:

> **What is different from expected?**

A line running normally should not compete visually with a serious production risk.

## 2.6 Action over observation

Every important insight must connect to:

- owner,
- next action,
- due time,
- decision,
- escalation,
- evidence,
- resolution.

Never create dead-end dashboards.

## 2.7 Calm urgency

Manufacturing software easily becomes red-alert chaos.

Do not make everything red.

Use urgency deliberately.

A user should feel:

> “The system understands what is important.”

not:

> “Everything is broken.”

---

# 3. Overall Product Personality

The product should feel like:

- industrially serious,
- technologically advanced,
- minimal but not empty,
- intelligent but not gimmicky,
- precise,
- responsive,
- confident,
- trustworthy.

Avoid:

- cartoonish AI design,
- glowing neon everywhere,
- excessive gradients,
- glassmorphism overload,
- generic startup illustrations,
- huge hero cards with no operational value,
- playful productivity-app styling,
- old grey ERP styling,
- dense enterprise admin software.

A useful conceptual reference is:

> **modern mission-control software for a factory, but approachable enough for day-to-day employees.**

---

# 4. Visual Language

## 4.1 Base aesthetic

Use a clean, premium industrial interface.

Characteristics:

- strong information hierarchy,
- controlled whitespace,
- slightly dense but breathable layout,
- sharp alignment,
- high-quality typography,
- subtle depth,
- restrained borders,
- minimal visual noise.

Avoid excessive rounded “bubble” cards.

Cards can have slight corner radius, but the interface should not look like a generic consumer finance dashboard.

## 4.2 Color strategy

Use color semantically.

Primary interface should remain mostly neutral.

Operational colors should mean something.

Suggested semantics:

```text
Neutral / graphite = normal UI structure
Blue = informational / selected / active system state
Green = healthy / on-plan / resolved
Amber = watch / approaching risk
Orange = significant operational issue
Red = critical / requires urgent action
Purple = AI/Gigi intelligence layer
```

Do not use rainbow dashboards.

Do not assign random colors to every module.

## 4.3 Status must not rely only on color

Always combine color with:

- icon,
- label,
- shape,
- text,
- pattern.

Example:

```text
● On Plan
▲ At Risk
■ Blocked
✓ Resolved
```

## 4.4 Typography

Use a modern professional sans-serif.

Hierarchy should clearly separate:

- page title,
- operational number,
- label,
- context,
- metadata.

Large numbers should be used only for genuinely important KPIs.

Do not create 25 large KPI cards.

---

# 5. Global Application Shell

## 5.1 Desktop layout

```text
┌─────────────────────────────────────────────────────────────┐
│ Top context bar                                             │
│ Plant | Shift | Date | Data health | Search | Gigi | User   │
├───────────────┬─────────────────────────────────────────────┤
│               │                                             │
│ Navigation    │ Main operational workspace                  │
│               │                                             │
│               │                                             │
└───────────────┴─────────────────────────────────────────────┘
```

## 5.2 Primary navigation

Recommended top-level navigation:

```text
Home
My Work
Operations
Materials
Quality
Maintenance
Improvement
Knowledge

--- role/admin only ---
Integrations
Administration
```

Procurement should live inside **Materials** unless the customer's process requires a separate procurement workspace.

The UI should reflect the larger manufacturing product, not V1's procurement-first history.

## 5.3 Navigation behavior

Navigation items should show subtle meaningful counters only when necessary.

Example:

```text
My Work        3
Operations     2 critical
Materials      1 risk
Quality
Maintenance    1 overdue
```

Do not show huge badge counts like 137.

Aggregate lower-level noise.

---

# 6. Universal Plant Context Bar

Always show the operational context.

Example:

```text
Pune Plant   /   Machining   /   Shift B
12 Aug 2026 · 13:42
Live data: 18 sec ago
```

If data is stale:

```text
⚠ Machine data delayed by 7 minutes
```

This should be visible without opening settings.

Users must always know:

- which plant,
- which line/area,
- which shift,
- whether the data is fresh.

---

# 7. Home — Role-Specific Command Center

Home is not a fixed dashboard.

It is a **decision surface** tailored by role.

---

# 8. Plant Head / COO Command Center

This is the flagship experience.

It should answer:

> Are we going to hit today's plan?

## 8.1 Top section — Today's Operating Pulse

Use one dominant visual.

Example:

```text
Today's Production Plan
18,000

Produced
8,250

Expected now
9,700

Forecast end of shift
16,100

Gap
-1,900
```

Visualize this as a clean progress/forecast trajectory.

Prefer:

- plan line,
- actual line,
- forecast line.

This instantly communicates trajectory.

## 8.2 Below — Why are we behind?

Use a visual loss breakdown.

Example:

```text
1,900 units at risk

Downtime           780
Material           510
Quality            370
Changeover         160
Other               80
```

A horizontal loss waterfall or stacked bar is better than five disconnected KPI cards.

Clicking a category filters deviations.

## 8.3 Top operational deviations

Display 3–7 maximum.

Each deviation card:

```text
LINE 3 · CNC-04

43 min unplanned downtime

Impact
~₹38,000
~420 units

Current state
Maintenance investigating

Owner
A. Sharma

Next escalation
13 min

[Open incident]
```

Cards should visually show:

- severity,
- value,
- owner,
- resolution state.

## 8.4 Decisions required

Separate problems being handled from decisions requiring leadership.

Example:

```text
2 decisions require you

WO-482
Approve alternate routing
Potential recovery: 280 units

RM-218
Approve alternate material
Production need: 16:30
```

These should be prominent because they are directly actionable.

## 8.5 What GenuineGigs is handling

Important trust feature.

Example:

```text
Gigi is currently handling 7 items

✓ 3 supplier confirmations requested
✓ Maintenance follow-up scheduled
✓ Quality evidence collected
✓ Stores availability checked
...
```

This makes the automation tangible.

---

# 9. Operations Workspace

The Operations page should feel like a live plant model.

## 9.1 Plant / line overview

Use a visual line map.

Example:

```text
MACHINING

Line 1        Line 2        Line 3        Line 4
ON PLAN       WATCH         AT RISK       ON PLAN

96%           91%           74%           101%
```

Each line card includes:

- current work order,
- target vs actual,
- state,
- most important blocker.

Click → line workspace.

---

# 10. Line Workspace

This is the main surface for supervisors and production managers.

## 10.1 Header

```text
Machining Line 3

WO-482 · AX-109
Shift B
Target 930
Actual 681
Forecast 854

AT RISK · -76 units
```

## 10.2 Visual production timeline

Show the shift as a timeline.

```text
06:00 ─────────────────────────────── 14:00

RUN     RUN     DOWN      RUN     SLOW     RUN
███████ ███████ ░░░░░░░░ ███████ ▒▒▒▒▒▒ ███
                ↑
            43 min fault
```

Overlay:

- downtime,
- changeover,
- quality hold,
- material waiting.

This lets users understand what happened visually.

## 10.3 Plan vs actual graph

Do not overcomplicate.

Show:

- planned cumulative production,
- actual cumulative production,
- forecast,
- key incident markers.

Tooltips explain incidents.

## 10.4 Loss tree

Interactive:

```text
Lost output: 249 units

Availability              118
 └ CNC-04 fault            107
 └ Waiting maintenance      11

Performance                 63
 └ Cycle-time drift         63

Quality                     41
 └ Dimensional defect       31
 └ Surface defect           10

Material                    27
 └ RM-218 staging delay     27
```

This becomes a signature GenuineGigs visual.

## 10.5 Active recovery

Use a horizontal flow:

```text
Deviation
   ↓
Maintenance notified
   ↓
Technician acknowledged
   ↓
Spare checked
   ↓
Repair underway
   ↓
Recovery verification
```

User instantly sees where resolution currently stands.

---

# 11. Operational Deviation Page

Every meaningful problem gets a dedicated workspace.

This should replace fragmented chats, emails, task pages, and dashboards.

## 11.1 Hero

```text
CNC-04 unplanned downtime

Started 12:14
Duration 43 min
Severity: High

Estimated impact
₹38,400
420 units

WO-482 at risk
```

## 11.2 Three-column structure

### Left — What happened

- event timeline,
- evidence,
- machine/production state,
- related records.

### Center — Why / impact

- probable causes,
- impact breakdown,
- related incidents,
- Gigi summary.

### Right — Recovery

- owner,
- current action,
- SLA,
- next escalation,
- decisions,
- task flow.

## 11.3 Event timeline

Example:

```text
12:14  Machine stopped
12:15  Fault 701 detected
12:16  Deviation created
12:16  Maintenance notified
12:18  Technician acknowledged
12:22  Similar incident found
12:25  Spare BR-28 confirmed available
12:31  Repair started
```

This creates operational memory.

---

# 12. My Work

This page must be extremely simple.

It should not feel like Jira.

It should answer:

> What should I do now?

## 12.1 Main structure

```text
NOW
3 items

NEXT
4 items

WAITING
6 items

DONE TODAY
12
```

## 12.2 Task card

Each card:

```text
URGENT

Inspect rejected lot QL-284

Why
Rejection on Line 2 crossed 4%.

Impact
WO-392 currently blocked.
~₹21,000 production at risk.

Due
14:20

[Start task]
[Ask Gigi]
```

That is much better than:

```text
Task #381
Status: Open
Priority: High
Assigned to: Rahul
```

## 12.3 Contextual completion

When user clicks Start:

Do not redirect to a giant form.

Open a focused execution drawer/workspace.

Show:

- instructions,
- required fields,
- evidence,
- related records,
- Gigi help.

## 12.4 Minimal form principle

Never ask user to enter information GenuineGigs already knows.

If:

- machine,
- work order,
- line,
- lot,
- employee,
- shift

are known, prefill them.

---

# 13. Material Readiness UX

This should be much more visual than procurement V1.

Primary question:

> Can upcoming production actually start?

## 13.1 Production-order readiness board

Rows are upcoming work orders.

Columns visually summarize readiness:

```text
WO-482  Tomorrow 08:00

Material      92%
Quality       READY
Tooling       READY
Machine       READY
People        READY

STATUS: AT RISK
```

Click material.

## 13.2 BOM readiness visualization

Example:

```text
28 required materials

24 READY
2 WATCH
1 AT RISK
1 BLOCKED
```

Then visually show risky components.

## 13.3 Material risk card

```text
RM-218

Required
2,000

Usable stock
600

Expected
1,600

Supplier confirmed
NO

Need time
Tomorrow 08:00

Risk
HIGH

Gigi:
Supplier confirmation requested at 10:12.
No response yet.
Next escalation at 13:00.
```

---

# 14. Procurement UX

Procurement remains part of Materials.

Avoid a traditional PO-entry-heavy layout.

## 14.1 Procurement cycle visualization

Represent the cycle visually:

```text
Requirement
   ✓

RFQ
   ✓

Supplier Responses
   4 / 5

Comparison
   In progress

Approval
   Waiting

PO
   Not started

Supplier Confirmation
   Not started
```

Use a horizontal/vertical workflow depending screen size.

## 14.2 Multi-cycle overview

Instead of showing 40 rows initially:

Group by state:

```text
Needs attention       4
Waiting suppliers     8
Waiting approval      3
PO in progress        2
On track             17
```

Then users can drill down.

---

# 15. Quality Workspace

Quality UX should revolve around:

> deviations → containment → root cause → closure.

## 15.1 Quality pulse

Visualize:

- FPY trend,
- current rejection,
- top defects,
- lines at risk,
- active holds.

## 15.2 Defect Pareto

Clean visual Pareto.

Click defect → affected:

- machine,
- product,
- shift,
- lot,
- supplier,
- time period.

## 15.3 RCA workspace

Do not force teams into one RCA methodology.

Support visual templates:

- 5 Why,
- Ishikawa,
- evidence timeline,
- factor comparison.

Gigi may assist, but human owns confirmed RCA.

---

# 16. Maintenance Workspace

Focus on production impact rather than just work-order counts.

## 16.1 Maintenance command board

Show:

```text
Assets down now
2

Production at risk
₹84k

Repeated faults
3

Awaiting spare
1
```

## 16.2 Asset card

```text
CNC-04

RUNNING

Current WO
WO-482

Last 30 days
Availability 93.8%
Downtime 6h 24m
4 recurring fault events

Next planned maintenance
3 days
```

## 16.3 Fault workspace

Combine:

- live fault,
- previous incidents,
- relevant manual,
- spare availability,
- technician,
- production impact,
- recommended next checks.

---

# 17. Improvement Studio

This should feel like an analytical investigation tool.

Not management reporting.

## 17.1 Improvement opportunities

Rank by addressable value.

Example:

```text
Recurring CNC-04 fault
₹4.8L annualized loss

RM-218 supplier delay
₹3.2L

Line 2 changeover variability
₹2.4L
```

Click opportunity → evidence.

## 17.2 Explore mode

Allow filtering by:

- plant,
- line,
- product,
- machine,
- shift,
- supplier,
- date,
- loss category.

Visuals:

- Pareto,
- trend,
- scatter,
- distribution,
- timeline,
- contribution tree.

Do not expose advanced analytics to every frontline user.

---

# 18. Gigi / AI Mascot UX

Gigi is one of the most important UX elements.

It must be useful without becoming childish.

## 18.1 Visual character

Gigi can have a distinctive mascot/avatar.

Requirements:

- premium,
- minimal,
- intelligent,
- approachable,
- not cartoonish,
- not a floating ChatGPT clone,
- not a cute toy robot.

Think:

> visual identity of a digital plant guardian.

Use subtle animation sparingly:

- attention,
- listening,
- processing,
- success,
- warning.

Never distract during critical workflows.

## 18.2 Gigi should exist in three modes

### Passive

Small presence in global UI.

Example:

```text
Gigi ●
```

Click opens assistant.

### Contextual

Appears inside relevant work.

Example:

```text
Gigi noticed this fault occurred 3 times recently.

[View previous incidents]
```

### Proactive

Only when important.

Example:

```text
Gigi

WO-482 is now likely to miss plan.
The issue is no longer just informational.

Production Manager decision required.
```

---

# 19. Gigi Side Panel

Do not make Gigi a full-screen chat by default.

Use a right-side contextual panel.

Example:

```text
┌──────────────────────────────┐
│ Gigi                         │
│                              │
│ What I know                  │
│                              │
│ CNC-04 stopped at 12:14      │
│ Fault 701                    │
│ Similar event: 6 Aug         │
│                              │
│ Suggested next action        │
│ Check bearing BR-28          │
│                              │
│ Evidence                     │
│ 4 records                    │
│                              │
│ [Prepare maintenance task]   │
│                              │
│ Ask anything...              │
└──────────────────────────────┘
```

This keeps AI tied to context.

---

# 20. AI Interaction Principles

## 20.1 Never make user phrase perfect prompts

The employee should not need to know how to “talk to AI.”

Provide contextual suggested actions.

Examples:

- Explain why output is behind
- Show similar incidents
- Prepare supplier follow-up
- Summarize this shift
- What is blocking this work order?
- Draft RCA
- Show tomorrow's material risks

## 20.2 AI actions must be visible

If Gigi does something:

Show it.

Example:

```text
Gigi requested supplier confirmation
10:12

Gigi created follow-up task for Purchase
10:45
```

No invisible autonomous behavior.

## 20.3 Confidence and evidence

If AI is uncertain:

Say so.

Example:

```text
Likely cause
Tool wear

Confidence
Moderate

Why
Cycle time increased 17%
Tool age is above normal range
Similar pattern occurred twice
```

---

# 21. Notification UX

Notifications should be operationally intelligent.

Do not replicate a social-media notification center.

## 21.1 Notification types

### Digest
Non-urgent summary.

### Action
User must do something.

### Escalation
Something missed its expected response.

### Critical
Significant production/safety/business risk.

## 21.2 Grouping

Bad:

```text
Machine alarm
Machine alarm
Machine alarm
Machine alarm
Machine alarm
```

Good:

```text
CNC-04 incident

5 related alarms grouped
43 min downtime
```

---

# 22. Search

Global search should behave like operational command search.

User can search:

```text
WO-482
CNC-04
RM-218
Supplier ABC
Fault 701
Line 3
```

Results grouped by entity.

Eventually support natural language:

> Show all repeated Line 3 faults this month.

---

# 23. Mobile / Tablet UX

Manufacturing users may not sit at desktops.

## 23.1 Mobile primary use cases

- My Work,
- approvals,
- alerts,
- photo/evidence upload,
- quick status update,
- Gigi help,
- maintenance response,
- quality checks,
- shift handover.

Do not simply shrink desktop dashboards.

## 23.2 Shop-floor tablet

Use:

- large touch targets,
- simple cards,
- low typing burden,
- visible status,
- scan/QR support,
- camera evidence.

---

# 24. Forms

Forms are a major source of ERP pain.

GenuineGigs must be significantly better.

## Rules

1. Autofill known context.
2. Ask only essential fields.
3. Use defaults intelligently.
4. Support progressive sections.
5. Save automatically where safe.
6. Allow evidence attachment naturally.
7. Explain why unusual data is required.
8. Avoid modal-within-modal patterns.

---

# 25. Approvals

Approvals should contain enough context to decide without searching elsewhere.

Example:

```text
Approve alternate material

WO-482

Current material
RM-218
Projected shortage: 1,400

Proposed alternate
RM-219

Quality
Previously approved for AX-109

Impact if rejected
~280 units at risk

[Approve]
[Reject]
[Ask question]
```

Do not show:

```text
Request #23813
Type: Material substitution
Approve?
```

---

# 26. Empty States

Avoid decorative illustrations.

Use empty states to guide.

Example:

```text
No operational data connected yet.

Start with one production line.

[Import production plan]
[Connect data source]
```

---

# 27. Loading States

Operational software must feel fast.

Prefer:

- skeleton layout,
- cached previous data with freshness marker,
- streaming partial updates.

Do not blank entire pages while one widget loads.

---

# 28. Error States

Errors should be actionable.

Bad:

> Failed to sync.

Good:

```text
SAP production data has not synced for 18 minutes.

Last successful update
13:04

Impact
Production forecasts may be stale.

[Retry]
[View connector health]
```

---

# 29. Data Freshness UX

Every operational metric must know freshness.

Possible UI:

```text
Live
18 sec ago

Recent
4 min ago

Stale
27 min ago
```

If stale data could mislead, downgrade/disable predictions.

---

# 30. Onboarding

The onboarding experience should avoid a giant configuration wizard.

Use staged activation.

## Stage 1 — Plant

Create:

- plant,
- areas,
- lines.

## Stage 2 — Data

Choose:

```text
ERP
Production
Machines
Quality
Maintenance
Excel
```

Allow starting with only Excel.

## Stage 3 — One use case

Ask:

> What do you want GenuineGigs to improve first?

Examples:

- production loss,
- material readiness,
- quality,
- maintenance.

Configure only what is needed.

---

# 31. Role Onboarding

A new employee should not receive a product tour of 14 modules.

Show:

```text
Welcome, Rahul.

You work in Maintenance.

GenuineGigs will primarily help you with:
- active machine problems,
- assigned recovery work,
- repair history,
- manuals,
- spares,
- escalation.

[Go to My Work]
```

---

# 32. In-Product Guidance

Do not use excessive tutorial popups.

Prefer contextual guidance.

Example:

```text
Material Readiness is calculated from:
inventory + open receipts + quality status.

[Learn more]
```

---

# 33. Visual Process Representation

Because GenuineGigs coordinates processes across departments, flows should be first-class.

Use:

- horizontal stage flows,
- dependency graphs,
- timelines,
- status lanes.

Example:

```text
Requirement
   ↓
Supplier RFQ
   ↓
Quote received
   ↓
Approval
   ↓
PO
   ↓
Supplier commitment
   ↓
Inbound
   ↓
Quality
   ↓
Material ready
```

Current stage highlighted.

Problems shown directly on stage.

---

# 34. Cross-Department Dependency Visualization

This is potentially a differentiating UX.

Example:

```text
WO-482
  │
  ├── Material RM-218
  │      └── Supplier confirmation missing
  │             └── Owner: Purchase
  │
  ├── Machine CNC-04
  │      └── Available
  │
  └── Quality approval
         └── Complete
```

This answers:

> Why can't this work happen?

---

# 35. Causal Chain Visualization

For incidents:

```text
Supplier delayed
      ↓
Material arrived late
      ↓
Stores staged late
      ↓
Line starved 27 min
      ↓
Production lost 210 units
      ↓
Shipment buffer reduced
```

Users should be able to inspect the chain.

---

# 36. Operational Timeline

Create a reusable timeline component.

Used for:

- deviation,
- shift,
- machine,
- work order,
- supplier commitment,
- quality case.

Each event has:

- time,
- actor,
- event,
- evidence.

---

# 37. Interaction Model

Use a consistent interaction pattern.

## Object click

Opens focused detail view.

## Quick action

Executes simple safe action inline.

## Complex action

Opens side drawer/workspace.

## Deep investigation

Navigates to full page.

Avoid random combinations of modals and pages.

---

# 38. Side Drawers

Use side drawers for:

- task completion,
- approval,
- Gigi,
- evidence,
- quick entity preview.

Benefits:

User retains operational context.

---

# 39. Keyboard Efficiency

For desktop power users:

- command search,
- shortcuts,
- arrow navigation,
- quick approve,
- quick open.

But shortcuts are secondary; UI must remain obvious without them.

---

# 40. Personalization

Allow limited useful personalization.

Examples:

- default plant,
- default line,
- preferred density,
- pinned KPIs,
- notification preferences.

Do not let dashboards become completely unstandardized.

Shared operational understanding matters.

---

# 41. Accessibility

Minimum:

- WCAG-conscious contrast,
- keyboard navigation,
- focus states,
- screen-reader labels,
- no color-only communication,
- minimum touch target sizes.

Manufacturing environments may have:

- glare,
- gloves,
- noise,
- distance from screen.

Design accordingly.

---

# 42. Internationalization

Architecture should support:

- multiple languages,
- local date/time,
- local number formatting.

Later, operators may benefit from localized UI/SOP assistance.

---

# 43. Performance Requirements

Target:

- app shell should feel immediate,
- primary operational data < 2 sec where possible,
- incremental live updates,
- no heavy chart blocking,
- lazy-load deep historical analytics.

Real-time views should update without page refresh.

---

# 44. Design System

Create a dedicated GenuineGigs design system.

Reusable primitives:

- status badge,
- severity indicator,
- deviation card,
- task card,
- KPI delta,
- operational timeline,
- loss tree,
- readiness state,
- process step,
- owner chip,
- evidence chip,
- AI recommendation,
- decision card,
- freshness indicator,
- plant selector,
- line selector.

Do not repeatedly redesign these per page.

---

# 45. Chart Design Rules

Charts should answer questions, not decorate.

Every chart must have a clear question.

Examples:

> Are we meeting plan?

→ cumulative plan vs actual.

> Why are we losing output?

→ loss tree / Pareto.

> Is quality getting worse?

→ trend/control chart.

> Which recurring issues matter most?

→ Pareto ranked by ₹ impact.

Avoid:

- donut charts for everything,
- meaningless 3D charts,
- excessive gauges,
- charts with 12 colors,
- tiny legends,
- too many simultaneous axes.

---

# 46. Dashboard Density Rules

One screen should contain:

- 1 dominant question,
- 3–7 key operational items,
- supporting visuals.

Never:

- 18 equal-weight cards,
- 12 charts,
- 40 metrics above the fold.

---

# 47. AI Visual Language

AI-generated/AI-derived information should have a subtle identifiable treatment.

Example:

```text
Gigi insight
```

Use a restrained accent.

Do not make the entire application purple/neon because AI exists.

---

# 48. Human vs AI Actions

Always distinguish:

```text
Rahul completed inspection

Gigi requested supplier status

SAP sync updated PO

CNC-04 generated alarm
```

Actor types should be visually identifiable.

---

# 49. Trust UI

For important AI recommendations provide:

```text
Recommendation

Move WO-482 to CNC-07.

Expected recovery
~280 units

Why
CNC-07 becomes available at 14:20.
Tooling compatible.
Material already staged.

Risks
Changeover 18 min.

Evidence
4 sources

[Review details]
```

This is how users develop trust.

---

# 50. Human Override

Users must be able to override AI where authority allows.

Require optional/mandatory reason depending action risk.

The UI should not shame users for disagreeing.

Those overrides become learning/evaluation data.

---

# 51. Safety-Critical UX

Any action affecting production, quality release, machine state, or high-value transaction must visibly communicate risk.

Use confirmation patterns proportional to risk.

Low risk:

> Send reminder

One click.

High risk:

> Release quality hold

Require:

- context,
- effect,
- confirmation,
- authority.

Do not over-confirm routine low-risk actions.

---

# 52. Audit Without Clutter

Audit should exist everywhere but remain secondary.

Users can expand:

```text
History
```

to see:

- who,
- when,
- what changed,
- source.

Do not show audit metadata on every card by default.

---

# 53. Daily Briefing UX

At shift/day start:

Gigi can show:

```text
Good morning, Rahul.

3 priorities today

1. RM-218 shortage risk
   Need by 11:00

2. Supplier ABC confirmation
   Still missing

3. WO-482
   Approval due at 10:30

Yesterday
12/14 commitments completed
2 carried forward
```

Avoid motivational fluff.

Keep it operational.

---

# 54. End-of-Shift UX

Gigi generates:

```text
Shift B summary

Plan
18,000

Actual
16,920

Main losses
Downtime       510
Quality        340
Material       230

Recovered
~410 units

Carry-over
3 issues

[Review handover]
```

Supervisor verifies/edit before publishing if required.

---

# 55. Manager Drill-Down Philosophy

Plant Head:

> 5 important problems.

Production Head:

> 14 active production deviations.

Supervisor:

> exact line events.

Engineer:

> raw incident evidence.

All derived from same system.

Never force executives to inspect raw machine events.

---

# 56. No “Admin Everywhere”

Configuration belongs in dedicated administration.

Daily operational screens should not expose:

- database IDs,
- mapping settings,
- configuration fields,
- technical connector properties.

---

# 57. Integration UX

Integrations should feel like infrastructure health.

Example:

```text
SAP
Connected
Last sync 32 sec ago

Production SQL
Connected
Last event 4 sec ago

Line 3 Edge
Connected
18 signals active

Quality Excel
Manual import
Last uploaded yesterday
```

---

# 58. Data Mapping UX

When onboarding external systems, create visual mapping.

Example:

```text
SAP Material MATNR
       ↓
GenuineGigs Material.external_code
```

Allow preview.

Do not require developer access for every field mapping later.

---

# 59. Operational Setup UX

Admins should configure:

- plant hierarchy,
- production calendars,
- shifts,
- KPI targets,
- loss categories,
- escalation rules,
- value formulas,
- action policies.

Use guided workflows.

---

# 60. UI Permissions

Do not merely hide pages.

Permissions should control:

- visibility,
- actions,
- financial data,
- employee data,
- plant scope.

Example:

Operator may see:

> production loss units.

but not:

> full financial contribution margin.

---

# 61. Employee Performance UX

Be extremely careful.

Do not create opaque “employee score.”

If managers need performance views, show sourced facts:

- commitments made,
- commitments completed,
- response time,
- blockers,
- production/quality KPIs where role-appropriate.

Always preserve context.

Example:

```text
Task missed

Reason
Waiting on Stores

Dependency delay
47 min
```

Do not blame employee for upstream blocker.

---

# 62. UX for Low-Digital-Maturity Users

Some users may be uncomfortable with complex software.

Design:

- large clear actions,
- plain language,
- familiar manufacturing terms,
- minimal setup,
- contextual AI help,
- shallow navigation.

Do not dumb down the product.

Make it obvious.

---

# 63. Terminology

Use customer terminology where possible.

Configurable labels may be required.

Examples:

- Work Order vs Production Order
- Item vs Material
- GRN vs Receipt
- Line vs Cell
- Rejection vs Scrap

Internally retain canonical entities.

---

# 64. Anti-Patterns — Hard Prohibitions

Codex must avoid all of these unless explicitly requested.

## 64.1 Generic SaaS homepage

Do not create:

```text
Welcome back, Takshay!
Here is your overview.
```

with four random cards.

Use operational context.

## 64.2 ERP tables as primary UI

Do not make every module:

```text
[Add New]

Search...

ID | Name | Status | Date | Action
```

CRUD screens may exist in admin/detail areas only.

## 64.3 Excessive sidebar nesting

Avoid:

```text
Operations
 > Production
   > Orders
   > Jobs
   > Lines
 > Downtime
 > OEE
 > Reports
```

Use contextual workspaces.

## 64.4 Random gradients

Avoid artificial “AI SaaS” appearance.

## 64.5 Every item in a card

Use cards only where grouping/context adds meaning.

## 64.6 Excessive modals

Do not stack dialogs.

## 64.7 Gigi as floating chat bubble only

Gigi must be integrated throughout workflows.

## 64.8 Static dashboards

Important screens should respond to operational state.

## 64.9 AI-generated decorative text

No verbose AI prose where structured information is clearer.

---

# 65. Design Review Checklist

Before accepting any UI implementation, ask:

### Clarity
Can a first-time target user understand the purpose in 10 seconds?

### Priority
Is the most important operational issue visually obvious?

### Action
Does the user know what to do next?

### Context
Does the UI explain why the action matters?

### Density
Are we showing too much?

### Data freshness
Can the user tell whether information is current?

### Trust
Can the user inspect evidence?

### Role relevance
Is this information necessary for this persona?

### ERP test
Does this screen feel like an old ERP module?

If yes, redesign.

### Generic SaaS test
Could this screenshot belong to a finance CRM or project-management app if labels were changed?

If yes, redesign.

### Manufacturing test
Does the interface visually communicate:

- production,
- flow,
- material,
- machines,
- deviations,
- actions,
- operational context?

If no, redesign.

---

# 66. Reference Screen Architecture

The following should become the flagship V2 screen set.

## Core

1. Plant Command Center
2. My Work
3. Operations Overview
4. Line Workspace
5. Deviation Workspace
6. Material Readiness
7. Procurement Cycle
8. Quality Workspace
9. Maintenance Workspace
10. Improvement Studio
11. Knowledge
12. Integrations/Admin

## AI

13. Gigi side panel
14. Gigi daily briefing
15. Gigi recommendation/decision card
16. AI action history

---

# 67. Phase 1 UI Implementation Priority

Even though the full design above describes the end state, initial implementation should focus on proving the visual/interaction system.

Build first:

1. V2 application shell.
2. Plant context bar.
3. Plant Command Center.
4. Operations overview.
5. Line workspace.
6. Production loss tree.
7. Deviation cards.
8. Deviation detail workspace.
9. My Work V2.
10. Gigi contextual panel.
11. Shift briefing.
12. Material Readiness prototype.

Do not build every Quality/Maintenance page before the design language is proven.

---

# 68. Phase 1 Prototype Data

It is acceptable for early UI work to use realistic seeded data.

Seed:

- plant,
- 4 lines,
- current shift,
- production targets,
- actual production,
- downtime,
- material risk,
- quality issue,
- active recovery actions.

The prototype should demonstrate the complete UX even before live OT integration.

---

# 69. Design-to-Code Workflow for Codex

Codex should not make large visual changes blindly.

For each major screen:

## Step 1

Document:

- persona,
- user question,
- primary action,
- information hierarchy.

## Step 2

Create the page structure/wireframe.

## Step 3

Validate against this document.

## Step 4

Implement reusable design-system components.

## Step 5

Use real/seeded domain data.

## Step 6

Take screenshot.

## Step 7

Review:

- hierarchy,
- density,
- genericness,
- ERP smell,
- visual clarity.

## Step 8

Iterate before moving to next major page.

---

# 70. Codex Guardrails for Large UI Refactors

When implementing a broad V2 UI change, Codex must follow these rules:

1. **Do not redesign every screen at once.** Establish the shell and design system first.
2. **Do not remove working business functionality merely because the old page looks outdated.** Migrate functionality into the new interaction model.
3. **Do not invent features or KPIs just to fill empty space.** Seeded/demo values must correspond to the V2 domain model.
4. **Do not replace meaningful visualizations with generic cards for implementation convenience.**
5. **Do not use placeholder gradients, AI blobs, abstract 3D art, or generic dashboard screenshots.**
6. **Do not add charts unless they answer a specific operational question.**
7. **Do not make every screen independent.** Work Order, Material, Machine, Deviation, Task, and Gigi context must link naturally.
8. **Do not force navigation for routine actions.** Prefer contextual quick actions and drawers.
9. **Do not overload Gigi.** Gigi should surface and orchestrate important work, not cover bad information architecture.
10. **After every major page, verify with screenshots at desktop and relevant tablet/mobile breakpoints.**

---

# 71. UX Acceptance Criteria for V2 Screens

A major screen is not complete until it satisfies all applicable criteria.

## First-glance comprehension

Within 5–10 seconds, a user should be able to identify:

- current state,
- whether there is a problem,
- most important issue,
- next action.

## One-click path to action

An important deviation should normally require no more than one click to reach the action/decision interface.

## No duplicate context entry

Known operational context must be prefilled.

## Evidence available

Material AI/operational claims must have an accessible evidence trail.

## Visible ownership

Active problems must make owner/current handling state clear.

## Visible outcome

Resolution should show what changed, not merely mark a ticket “Closed.”

## Data health

Live operational surfaces must show stale/degraded data states.

## Role fit

The screen must be tested from the perspective of its primary persona, not only an administrator.

---

# 72. Final UX Vision

A manufacturing employee should experience GenuineGigs like this:

They come to work.

They do not open five systems to understand their day.

GenuineGigs already knows:

- current plant state,
- their role,
- active production,
- blockers,
- commitments,
- dependencies,
- material risks,
- quality issues,
- machine issues,
- deadlines.

The product gives them a small, ordered set of actions.

When something changes, GenuineGigs explains the impact.

When an issue crosses departments, the system follows the dependency automatically.

When the employee needs help, Gigi already has the relevant context.

When management opens the product, they do not see noise.

They see:

> **What is at risk, why, what it costs, who is handling it, and what requires a decision.**

When the shift ends, the plant does not lose context through informal handover.

When the month ends, management can see where operational losses repeatedly occurred and which interventions actually improved performance.

The UX should make the complexity of a factory feel manageable without pretending that manufacturing itself is simple.

That is the standard every V2 screen should be judged against.

---

# 73. One-Sentence Design Rule

> **Do not make the user navigate the software to find the work; make the software understand the plant and bring the right work to the user.**



---

# 74. CODEX UI EXECUTION CONTRACT — IMPLEMENT, DO NOT GENERICIZE

This section is a hard frontend implementation contract. Codex may adjust minor responsive spacing, but it must not replace the information architecture with generic KPI cards/tables or independently redesign the product.

## 74.1 Route map

```text
/v2/home
/v2/my-work
/v2/operations
/v2/operations/lines/[lineId]
/v2/deviations/[deviationId]
/v2/materials
/v2/materials/readiness
/v2/materials/procurement
/v2/quality
/v2/quality/deviations/[id]
/v2/maintenance
/v2/maintenance/assets/[assetId]
/v2/improvement
/v2/knowledge
/v2/integrations
/v2/admin
```

Do not create one route per CRUD table/entity.

---

# 75. Exact App Shell Geometry

Desktop ≥1280 px:

```text
sidebar expanded: 224 px
sidebar collapsed: 72 px
top context bar: 56 px
page horizontal padding: 24 px
page vertical padding: 20–24 px
main content: fluid
```

Tablet 768–1279:

```text
sidebar collapsed by default
secondary panes move to drawers
```

Mobile <768:

```text
no persistent sidebar
compact mobile navigation
top bar keeps plant + alerts + Gigi
mobile-specific chart/action forms
```

---

# 76. Design Tokens

Use a central token layer.

```css
--bg-app:          #F5F7F9;
--bg-surface:      #FFFFFF;
--bg-subtle:       #F0F3F5;
--border-default:  #DCE2E7;
--border-strong:   #C7D0D8;

--text-primary:    #17212B;
--text-secondary:  #52606D;
--text-muted:      #7A8793;

--info:            #2563EB;
--healthy:         #15803D;
--watch:           #B7791F;
--high:            #D97706;
--critical:        #C9362B;
--ai:              #6D4AFF;

--radius-sm:       6px;
--radius-md:       10px;
--radius-lg:       14px;

--shadow-float:    0 12px 30px rgba(15,23,42,.10);
```

If a working GenuineGigs brand primary already exists, preserve it for brand/selection states. Operational semantics above remain fixed.

Rules:

- normal surfaces neutral;
- red only for genuine urgency;
- purple only for Gigi/AI provenance;
- no random module colors;
- no decorative rainbow graphs.

---

# 77. Typography Contract

Use existing high-quality product font; otherwise Inter.

```text
Page title         24–28 px / 32–36 line
Section title      17–20 / 24–28
Operational hero   32–44 / 38–48
Card title         14–16 / 20–24
Body               14 / 20–22
Metadata           12–13 / 16–18
Button             13–14 / 18
```

No marketing-sized headings inside the operating application.

---

# 78. Layout Grid Contract

Use 12-column desktop grids.

## Command Center

```text
Operating Pulse         8
Decisions               4

Loss Breakdown          7
Active Deviations       5

Gigi Activity           7
Data Health             5
```

## Line Workspace

```text
Hero                    12
Trajectory               8
Current action/status    4
Timeline                12
Loss Tree                7
Recovery Flow            5
```

## Deviation Workspace

```text
Evidence/history         4
Cause + impact           5
Recovery/actions         3
```

On smaller widths stack by operational priority, never by arbitrary DOM order.

---

# 79. Required Reusable Components

Build these before duplicating page-specific versions:

```text
AppShell
PlantContextBar
PlantSelector
ShiftSelector
DataFreshnessIndicator

StatusBadge
SeverityBadge
OwnerChip
EntityChip
EvidenceChip

OperatingPulse
PlanActualForecastChart
LossBreakdownChart
LossTree
ProductionTimeline
ReadinessMeter
ProcessStageFlow
DependencyGraph
CausalChain

DeviationCard
DeviationHero
DecisionCard
OperationalActionCard
RecoveryFlow
EventTimeline

GigiAvatar
GigiPanel
GigiInsight
GigiActivityItem
AIConfidence
EvidenceList

EmptyOperationalState
DegradedDataBanner
ConnectorHealthCard
```

---

# 80. State Management Contract

Use TanStack Query (or existing equivalent) for server state.

Canonical query keys:

```text
["command-center", plantId, shiftId]
["operations-overview", plantId, shiftId]
["line-workspace", lineId, shiftId]
["deviation", deviationId]
["my-work", userId, plantId]
["material-readiness", plantId, horizon]
["gigi-briefing", plantId, userId, shiftId]
```

SSE events update/invalidate relevant cache entries.

Local React state only for:

```text
tabs
filters
drawer state
draft fields
temporary UI expansion
```

Do not duplicate canonical business state in Zustand/context.

---

# 81. Plant Command Center — Exact Screen

## Header

```text
Plant Command Center
Pune Plant · Shift B
```

Right:

```text
data freshness
last update
time horizon if applicable
```

Never “Welcome back”.

## Operating Pulse

Required:

```text
target
actual
expected_now
forecast_end
gap_units
gap_pct
confidence
```

One visual:

- plan line,
- actual line,
- dashed forecast,
- current-time marker,
- incident markers.

Below it show only:

```text
Target
Actual now
Forecast end
```

## Loss Breakdown

Default measure = lost units.

Toggle:

```text
Units | Time | ₹
```

Categories:

```text
Downtime
Performance
Quality
Material
Changeover
Waiting/Other
```

Click category filters deviations.

## Decisions Required

Maximum 5 cards. Each contains:

```text
decision
affected object
expected impact
need-by time
Review/Approve
```

## Active deviations

Maximum 5–7, sorted by:

```text
severity
business impact
time sensitivity
```

not creation time alone.

---

# 82. Operations Overview — Exact Screen

Each line card contains:

```text
line
state
active work order
target
actual
forecast
gap
single top blocker
freshness
```

Do not include full OEE breakdown on every card.

Filter:

```text
All | At Risk | Blocked | On Plan
```

Click → line workspace.

---

# 83. Line Workspace — Exact Screen

## Hero

Always visible:

```text
Line
Work order
Product
Shift

Target
Actual
Forecast

State
Gap units
Gap %
```

Right side:

```text
top active deviation
owner
current/next recovery action
```

## Timeline

Required event types:

```text
running
downtime
planned downtime
changeover
material wait
quality hold
```

Click block shows:

```text
start
end
duration
reason
impact
deviation
```

## Plan/Actual chart

Incident marker must open the related deviation.

## Loss Tree

Preserve hierarchy:

```text
Lost Output
 ├ Availability
 │  ├ Unplanned downtime
 │  └ Waiting maintenance
 ├ Performance
 │  └ Slow cycle
 ├ Quality
 │  └ Defect
 └ Material
    └ Staging delay
```

Node click filters contributing events.

## Recovery Flow

Only render real action progression. Never fake a generic process stepper.

---

# 84. Deviation Workspace — Exact Screen

## Hero

```text
category
title
severity
status

start/duration
affected line/WO/asset/material
lost units
₹ impact
```

Primary CTA changes by lifecycle:

```text
Detected         Acknowledge
Assigned         Start investigation
Action required  Review action
In progress      Update
Monitoring       Verify recovery
Resolved         Verify outcome
```

## Left: Evidence/history

Actor types:

```text
Machine
System
Gigi
User
ERP/MES
```

## Center: Understanding

```text
What happened
Impact
Likely contributors
Confirmed cause
Similar incidents
```

Hypotheses must never visually look like confirmed facts.

## Right: Recovery

```text
Owner
SLA
Current action
Dependencies
Escalation
Decision required
```

Sticky on desktop.

---

# 85. My Work — Exact Screen

Groups:

```text
NOW
NEXT
WAITING
DONE TODAY
```

NOW contains:

```text
urgent
due soon
blocking another action
linked to high/critical deviation
user decision required
```

Every action card:

```text
verb/action title
why it matters
impact
due
entity context
primary CTA
Ask Gigi
```

WAITING items must show dependency and not appear as employee failure.

---

# 86. Material Readiness — Exact Screen

Horizon:

```text
Today | Tomorrow | 7 Days
```

Work-order row/card:

```text
WO
start
product
readiness %
state
number risky materials
biggest risk
```

Per-material detail:

```text
material
required
usable now
confirmed inbound
unconfirmed inbound
need-by
state
owner/action
```

State comes from backend Readiness Engine, never frontend math.

---

# 87. Procurement V2 — Exact Screen

Primary UI is a material/sourcing lifecycle:

```text
Requirement
RFQ
Responses
Comparison
Approval
ERP PO
Supplier Acknowledgement
Inbound
Quality
Ready
```

Each stage shows:

```text
state
owner
waiting duration
blocker
```

Summary buckets:

```text
Needs attention
Waiting supplier
Waiting internal
On track
```

Existing V1 tables/forms remain secondary detail views until safely migrated.

---

# 88. Quality Workspace — MVP Screen

Primary question:

> Where is quality hurting production/value now?

Top:

```text
current rejection
target rejection
FPY
active holds
scrap/rework impact
```

Then:

```text
Pareto by loss value
active quality deviations
trend
```

Do not build a generic QMS replacement.

---

# 89. Maintenance Workspace — MVP Screen

Primary question:

> Which reliability problem is hurting production now?

Top:

```text
assets down
production impact
repeat faults
waiting for spare
```

Asset card focuses on:

```text
state
production consequence
repeat history
current recovery work
```

Do not recreate CMMS administration first.

---

# 90. Gigi Panel — Exact Contract

Desktop:

```text
width 380–440 px
right side
non-modal
plant page remains visible
```

Structure:

```text
Gigi header + current context
proactive insight if applicable
conversation
evidence chips
suggested actions
composer
```

Initial visible answer should generally be concise; deeper details expand.

Suggested actions:

```text
Show similar incidents
Prepare maintenance task
Explain impact
Prepare follow-up
```

---

# 91. Gigi Proactive UX

Do not auto-open panel for routine events.

```text
normal → activity log
watch → subtle Gigi indicator
high → contextual banner/card
critical + decision → prominent actionable interruption
```

Proactive message order:

```text
What changed
Why it matters
What GenuineGigs is already doing
What the user must do
```

---

# 92. Notifications

Tabs:

```text
Needs You
Updates
All
```

Needs You:

```text
approvals
decisions
overdue owned action
critical escalation
```

Group alarm storms into a single operational incident.

---

# 93. Drawer/Form Contract

Desktop action drawer:

```text
480–620 px
```

Mobile: full screen.

Structure:

```text
title
why/context
fields
evidence
primary action
cancel
```

Never open a modal on top of a drawer.

---

# 94. Loading / Stale / Error States

## Loading

Retain shell and cached data; skeleton only missing region.

## Stale

Example:

```text
Production data is 18 min old.
Forecast may be inaccurate.
```

Calculations depending on stale input must show `Data stale` instead of fake precision.

## Error

Explain operational impact and recovery action, not generic “Something went wrong”.

---

# 95. Chart/Graph Library Rules

Use Recharts:

```text
line
area
bar
stacked bar
Pareto
basic scatter
```

Custom SVG/React:

```text
loss tree
production timeline
stage flow
readiness meter
```

@xyflow/react only:

```text
dependency graph
causal graph
```

No graph canvas for a simple linear workflow.

---

# 96. Motion and Iconography

Motion only explains state change:

```text
drawer
new deviation
Gigi processing
small chart/filter transition
```

No decorative floating/pulsing backgrounds.

Use existing icon set; otherwise Lucide. Never mix icon families.

---

# 97. Responsive Priority

When space reduces, preserve:

```text
1. critical state
2. primary action
3. impact
4. owner
5. core visual
6. evidence summary
7. metadata
```

Never hide the action to preserve decoration.

---

# 98. Shop-Floor Accessibility

Minimum touch target:

```text
desktop 36 px
touch 44 px
```

Critical actions require visible text, not icon-only controls.

Design for glare, gloves, distance, and lower digital familiarity.

---

# 99. Screenshot Acceptance Tests

For every flagship screen capture:

```text
1440x900 desktop
1024x768 tablet if relevant
390x844 mobile for My Work/Gigi/approvals
```

Reject screen if:

1. plant/shift/freshness is unclear;
2. biggest problem is not obvious;
3. next action is hidden;
4. business impact is absent;
5. more than ~7 equal-priority cards dominate;
6. a table dominates where timeline/process/graph is clearer;
7. it could be relabeled into a CRM/project-management dashboard;
8. Gigi is decorative rather than contextual;
9. normal operations visually compete with exceptions;
10. a first-time target user needs a product tour to understand the page.

---

# 100. V2 UI Implementation Order

Implement exactly in this sequence:

```text
1. theme/tokens
2. AppShell
3. PlantContextBar + freshness
4. status/severity/entity primitives
5. V2 API query layer
6. Plant Command Center
7. Operations Overview
8. Line Workspace
9. Deviation Workspace
10. My Work V2
11. Gigi panel
12. Material Readiness
13. Procurement V2 migration
14. Quality
15. Maintenance
16. Improvement Studio
```

Do not jump to later modules before the Command Center → Line → Deviation → Action loop is coherent.

---

# 101. Frontend Definition of Done

A V2 screen is complete only when:

```text
route exists
loading state exists
empty state exists
stale/degraded state exists
error state exists
role permissions respected
data comes from V2 API/query layer
live update works if applicable
actions function
Gigi context wired where applicable
desktop screenshot reviewed
tablet/mobile reviewed where applicable
lint/typecheck pass
```

Hard-coded mock arrays inside final page components are not complete implementation.
