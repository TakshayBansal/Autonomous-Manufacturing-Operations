# GenuineGigs SCM Control Tower — Implementation Plan

**Document purpose:** Implementation-ready blueprint for Codex to build the reusable SCM scaffolding inside the existing GenuineGigs codebase before detailed Lumax discovery.

**Status:** Pre-design-partner scaffolding

**Primary design partner:** Lumax (initial discovery context)

**Long-term target:** Discrete manufacturing / EMS / automotive suppliers, multi-plant, ERP-heavy environments

**Core product thesis:** GenuineGigs SCM should not replace SAP/ERP. It should sit above ERP, Excel, supplier data, and procurement systems as a **supply-chain decision and execution layer** that converts fragmented transactional data into time-phased material visibility, exceptions, prioritized actions, and explainable recommendations.

---

## 0. Instructions to Codex

Read this entire file before modifying code.

Before implementing anything:

1. Inspect the existing GenuineGigs repository and identify:
   - backend framework;
   - frontend framework;
   - database and ORM;
   - Redis/Celery usage;
   - authentication and authorization model;
   - current procurement and operations domain entities;
   - Docker/Docker Compose setup;
   - test framework;
   - migrations framework;
   - API conventions;
   - logging conventions;
   - existing background workers and queues;
   - any reusable supplier, material, PO, user, organization, plant, attachment, notification, or audit models.
2. Produce a short `SCM_REPO_ASSESSMENT.md` describing what can be reused versus what must be added.
3. Do **not** create a second parallel architecture if the existing codebase already has equivalent abstractions.
4. Prefer extending reusable entities over duplicating them, but do not overload existing procurement models with planning-specific semantics if that would make them ambiguous.
5. Keep every Lumax-specific rule configurable. Do not hard-code customer names, file columns, plant IDs, safety thresholds, forecast horizons, or alert formulas.
6. Build deterministic planning and risk calculations first. Do not make an LLM responsible for inventory arithmetic, shortage calculations, pegging, or action eligibility.
7. Every planning result must be explainable from underlying source records.
8. Every import must be idempotent and traceable.
9. Every recommendation must distinguish:
   - `DETECTED_FACT` — directly observed from source data;
   - `CALCULATED_RESULT` — deterministic calculation;
   - `RECOMMENDATION` — action suggested by configured rules;
   - `PREDICTION` — future statistical/ML estimate, if enabled later.
10. Treat production safety, data correctness, auditability, and rollback as product features.

---

# 1. Product Context

## 1.1 Problem observed at Lumax

The current SCM workflow described by Anurag is centered around a large Excel-based material planning workbook fed from SAP/ERP and planning inputs.

The workbook has approximately thousands of material rows even for a one-month planning window, while the actual planning cycle can extend roughly six to seven months.

For each material/component, planners may need to understand:

- material identity and specifications;
- supplier(s);
- which finished-good/SKU/BOM consumes the material;
- which OEM/customer the finished good ultimately serves;
- plant/location;
- inventory currently available;
- inventory reserved or otherwise not freely usable;
- expected receipts / open purchase orders;
- expected receipt dates;
- indents/material requirements;
- demand forecasts over future months;
- projected consumption;
- shortage date / days of coverage / runway;
- future supply gaps;
- demand increases requiring PO pull-ins or additional procurement;
- demand decreases requiring PO push-outs, reductions, or cancellations;
- cancellation/freeze windows;
- risk status across the future planning horizon.

A typical operational question is:

> We require 100,000 units in the next 30 days, have 30,000 available, and the next receipt is after the projected stockout date. What is the exact shortage window, what finished goods/OEMs are exposed, and which supply should be pulled in or newly procured?

The current process can answer some of these questions manually, but visualization and multi-month exception management are weak.

## 1.2 Product outcome

The SCM module should become a **Supply Chain Control Tower / Material Readiness layer** that provides:

1. A single normalized view across ERP and spreadsheet sources.
2. A six-to-seven-month or configurable planning horizon.
3. Time-phased projected inventory.
4. Supply-demand pegging / traceability.
5. Material shortage detection before stockout.
6. BOM-to-finished-good-to-OEM impact visibility.
7. Pull-in, push-out, cancel, expedite, and new-buy action candidates.
8. Clear red/amber/green visualization.
9. What-if scenario capability later.
10. A reusable architecture that works beyond Lumax.

---

# 2. Explicit Non-Goals for the First Scaffolding

Do not build these yet unless the existing repo already has reusable implementations:

- full ERP replacement;
- accounting;
- warehouse execution;
- barcode/WMS workflows;
- production scheduling optimizer;
- transportation management;
- supplier payment workflows;
- autonomous PO changes in SAP;
- black-box ML forecasting;
- reinforcement learning optimization;
- LLM-calculated stock levels;
- customer-specific dashboards without discovery validation;
- complex multi-echelon optimization;
- Kubernetes;
- multi-region active-active infrastructure;
- elaborate microservices decomposition.

The first release must remain a modular monolith or match the current GenuineGigs architecture unless scale measurements prove otherwise.

---

# 3. Competitive/Reference Patterns to Adopt Conceptually

The following are design patterns, not code-copy instructions.

## 3.1 ERP-overlay approach

Products such as LeanDNA position planning/execution intelligence above existing ERP data rather than requiring ERP replacement. GenuineGigs should follow this principle.

**Implication:** Build adapters into a canonical SCM data model. ERP remains system of record for transactional execution until an approved write-back workflow is intentionally implemented.

## 3.2 Supply-demand pegging

Oracle Supply Planning and traditional MRP systems link demand to the supplies that satisfy it. This is fundamental for explaining why a material is at risk.

**Implication:** A planner must be able to move from:

`OEM demand -> finished good -> BOM component demand -> inventory / PO / transfer supply`

and also reverse:

`PO receipt -> material -> demands it protects -> finished goods -> OEM/customer`.

## 3.3 Exception/action messages

Infor and other planning systems produce exception/action messages when supply is late, insufficient, or out of alignment.

**Implication:** GenuineGigs should not force planners to inspect 3,800 rows. It should generate a ranked queue of exceptions and recommended actions.

## 3.4 Projected inventory and safety stock

Microsoft Dynamics and other MRP systems calculate projected inventory relative to demand, replenishment, lead time, reorder thresholds, and safety stock.

**Implication:** Build a deterministic time-phased inventory engine with transparent formulas and configurable policies.

## 3.5 Supply chain network visualization

SAP IBP and control-tower tools visually represent supply relationships and exceptions.

**Implication:** Store relationships in a way that supports graph-like traversal, but do not introduce a graph database prematurely. PostgreSQL relational tables plus adjacency/closure queries are sufficient initially.

## 3.6 Open-source references

ERPNext, Odoo, and OpenBoxes may be inspected to understand common domain boundaries such as BOMs, inventory movements, purchase orders, and material requirements.

**Important:** Reuse concepts, not licensed code, unless legal/license compatibility has been explicitly reviewed.

---

# 4. Product Architecture Principles

## 4.1 Architectural shape

Preferred conceptual architecture:

```text
                    +-----------------------+
                    |      SAP / ERP        |
                    +-----------+-----------+
                                |
                    +-----------v-----------+
                    |   Connector / Import  |
                    |  CSV XLSX API SFTP    |
                    +-----------+-----------+
                                |
                    +-----------v-----------+
                    |  Raw Import / Staging |
                    | Immutable + traceable |
                    +-----------+-----------+
                                |
                    +-----------v-----------+
                    | Canonical SCM Model   |
                    | material/supply/demand|
                    +-----------+-----------+
                                |
              +-----------------+------------------+
              |                                    |
    +---------v----------+               +---------v----------+
    | Planning Engine    |               | Event/Change Engine|
    | deterministic      |               | recompute impacted |
    +---------+----------+               +---------+----------+
              |                                    |
              +-----------------+------------------+
                                |
                    +-----------v-----------+
                    | Risk / Action Engine  |
                    | exceptions + priority |
                    +-----------+-----------+
                                |
                    +-----------v-----------+
                    | SCM APIs / Read Model |
                    +-----------+-----------+
                                |
                    +-----------v-----------+
                    | Control Tower UI      |
                    +-----------------------+
```

## 4.2 Keep transactional truth separate from planning truth

Transactional facts come from ERP/imports. Planning values may be derived.

Never overwrite imported source facts merely because a planner changes a scenario.

Use separate concepts for:

- actual source record;
- normalized record;
- planning scenario override;
- calculated result;
- recommendation;
- approved execution action.

## 4.3 Deterministic first

Initial planning output must be reproducible.

Given the same:

- inventory;
- forecasts;
- orders;
- BOM;
- receipts;
- planning parameters;
- calendar;

then the engine must produce the same result.

ML can be added later for uncertain variables such as:

- demand forecast adjustment;
- supplier delay probability;
- lead-time distribution;
- safety stock tuning;
- anomaly detection.

It must not silently modify core planning arithmetic.

---

# 5. Canonical Domain Model

Codex must map these concepts onto the existing GenuineGigs domain where appropriate.

All tenant-owned records must include tenant/company scoping.

## 5.1 Organization hierarchy

### `Organization`

Fields:

- `id`
- `name`
- `external_id`
- `timezone`
- `default_currency`
- `created_at`
- `updated_at`

### `Plant`

Fields:

- `id`
- `organization_id`
- `code`
- `name`
- `external_id`
- `timezone`
- `active`

### `StorageLocation` (optional scaffolding)

Fields:

- `id`
- `plant_id`
- `code`
- `name`
- `external_id`

Do not require StorageLocation granularity for MVP calculations unless data supports it.

---

## 5.2 Material master

### `Material`

Fields:

- `id`
- `organization_id`
- `material_code`
- `description`
- `material_type` enum:
  - RAW_MATERIAL
  - COMPONENT
  - SUBASSEMBLY
  - FINISHED_GOOD
  - PACKAGING
  - CONSUMABLE
  - OTHER
- `base_uom`
- `specification_text`
- `manufacturer_part_number` nullable
- `customer_part_number` nullable
- `lifecycle_status`
- `active`
- `external_id`
- `metadata_json`

Indexes:

- unique `(organization_id, material_code)`
- material type
- external id

### `MaterialPlantPolicy`

Plant-specific planning parameters:

- `material_id`
- `plant_id`
- `procurement_type`
- `default_supplier_id`
- `planned_lead_time_days`
- `goods_receipt_processing_days`
- `safety_stock_qty`
- `minimum_order_qty`
- `order_multiple`
- `minimum_coverage_days`
- `maximum_coverage_days`
- `planning_time_fence_days`
- `cancellation_window_days`
- `expedite_window_days`
- `active`

All fields must be nullable/configurable because Lumax-specific definitions will come from discovery.

---

## 5.3 Unit-of-measure support

### `UOMConversion`

- `material_id`
- `from_uom`
- `to_uom`
- `factor`

All planning arithmetic must normalize to a material base UOM.

Reject or quarantine records when UOM conversion is required but unavailable.

Never guess conversions.

---

## 5.4 Supplier model

Prefer reusing the GenuineGigs procurement supplier model if it exists.

### Additional SCM relationship: `MaterialSupplier`

Fields:

- `material_id`
- `plant_id` nullable
- `supplier_id`
- `supplier_material_code`
- `approved_status`
- `priority_rank`
- `contract_lead_time_days`
- `minimum_order_qty`
- `order_multiple`
- `cancellation_window_days`
- `pushout_allowed`
- `cancellation_allowed`
- `expedite_allowed`
- `valid_from`
- `valid_to`

Later additions:

- historical on-time delivery;
- lead-time variability;
- quality score;
- technical approval status;
- commercial constraints.

---

## 5.5 Customer/OEM relationship

Prefer reusing existing customer entities if present.

### `MaterialCustomerUsage`

Fields:

- `finished_good_material_id`
- `customer_id`
- `customer_part_number`
- `plant_id`
- `program_name` nullable
- `valid_from`
- `valid_to`

This enables impact statements such as:

> Component C123 shortage threatens Finished Goods FG10 and FG11 supplied to OEM Honda.

---

## 5.6 BOM model

### `BOM`

- `id`
- `organization_id`
- `parent_material_id`
- `plant_id`
- `bom_code`
- `revision`
- `effective_from`
- `effective_to`
- `status`
- `source_system`
- `external_id`

### `BOMLine`

- `bom_id`
- `component_material_id`
- `quantity_per`
- `uom`
- `scrap_factor` nullable
- `operation_ref` nullable
- `line_number`

Requirements:

- support nested BOMs;
- detect cycles;
- version/effective-date aware;
- do not delete historical revisions if source changes;
- expose BOM explosion service.

### BOM explosion interface

```text
explode_bom(parent_material, quantity, effective_date, plant)
 -> list[component requirement]
```

Each result should retain path metadata:

```text
FG-A -> SUB-1 -> COMPONENT-X
```

so UI can explain dependency chains.

---

# 6. Supply and Demand Model

Do not create one giant planning table. Preserve semantic types and expose a normalized planning-event interface.

## 6.1 Inventory snapshots

### `InventorySnapshot`

- `material_id`
- `plant_id`
- `storage_location_id` nullable
- `snapshot_at`
- `on_hand_qty`
- `unrestricted_qty` nullable
- `quality_hold_qty` nullable
- `blocked_qty` nullable
- `reserved_qty` nullable
- `available_qty` nullable
- `source_system`
- `source_record_id`
- `import_batch_id`

Planning engine must use a configured availability definition, e.g.:

```text
planning_available = unrestricted - reserved
```

but do not hard-code the exact rule before design-partner validation.

## 6.2 Demand forecast

### `DemandForecast`

- `material_id`
- `plant_id`
- `customer_id` nullable
- `forecast_version`
- `bucket_start`
- `bucket_end`
- `quantity`
- `uom`
- `forecast_type`
- `source_system`
- `source_record_id`
- `import_batch_id`

Keep forecast versions immutable where practical.

## 6.3 Indent / material requirement

If GenuineGigs already has an indent/material request concept, reuse it.

### `MaterialRequirement`

- `material_id`
- `plant_id`
- `required_date`
- `quantity`
- `requirement_type`
  - INDENT
  - PRODUCTION
  - CUSTOMER_ORDER
  - FORECAST
  - TRANSFER
  - SAFETY_STOCK
  - OTHER
- `priority`
- `finished_good_id` nullable
- `customer_id` nullable
- `source_system`
- `external_id`

## 6.4 Purchase order supply

Reuse procurement PO entities where possible.

The SCM engine requires schedule-level semantics.

### `SupplyOrder`

Normalized read model over source PO/transfer/production supply:

- `supply_type`
  - PURCHASE_ORDER
  - TRANSFER_ORDER
  - PRODUCTION_ORDER
  - PLANNED_ORDER
  - MANUAL_COMMIT
- `material_id`
- `plant_id`
- `supplier_id` nullable
- `order_number`
- `line_number`
- `schedule_line_number` nullable
- `ordered_qty`
- `received_qty`
- `open_qty`
- `original_due_date`
- `current_due_date`
- `supplier_commit_date` nullable
- `status`
- `firmness`
- `source_system`
- `source_record_id`

**Critical:** Support multiple receipt schedule lines for one PO line.

## 6.5 Goods receipt

### `GoodsReceipt`

- `material_id`
- `plant_id`
- `supply_order_id` nullable
- `receipt_date`
- `quantity`
- `uom`
- `source_system`
- `source_record_id`

---

# 7. Import and Integration Framework

## 7.1 Design goal

Build a pluggable ingestion system so Lumax-specific Excel/SAP schemas are mapping configuration, not application rewrites.

## 7.2 Connector interface

Create a connector abstraction equivalent to:

```python
class SCMConnector:
    def discover_schema(self) -> ConnectorSchema: ...
    def extract(self, checkpoint) -> RawBatch: ...
    def validate_raw(self, batch) -> ValidationReport: ...
    def map_to_canonical(self, batch, mapping_config) -> CanonicalBatch: ...
    def load(self, canonical_batch) -> LoadResult: ...
```

Adapt naming to existing codebase conventions.

Initial connector implementations:

1. `CSVConnector`
2. `ExcelConnector`
3. `ManualUploadConnector`
4. `MockERPConnector`
5. `SAPConnector` interface/stub only until Lumax provides technical access details

Optional future:

- REST connector;
- OData connector;
- SFTP drop connector;
- database read replica connector;
- SAP RFC/BAPI/OData depending customer architecture.

## 7.3 Do not guess SAP integration

Do not build a fake production SAP integration ahead of discovery.

Lumax may expose data through:

- SAP OData/API;
- RFC/BAPI;
- SAP Integration Suite;
- scheduled exports;
- database intermediary;
- SFTP files;
- manual Excel initially.

Create the adapter boundary now; implement the selected transport later.

## 7.4 Raw import layer

Every inbound import must produce an immutable `ImportBatch`.

### `ImportBatch`

- `id`
- `organization_id`
- `connector_type`
- `source_name`
- `source_file_hash` nullable
- `started_at`
- `completed_at`
- `status`
- `rows_received`
- `rows_valid`
- `rows_rejected`
- `mapping_version`
- `checkpoint`
- `triggered_by`
- `error_summary`

### `RawImportRecord`

Store either:

- original row JSON;
- raw file plus row reference;
- or equivalent traceable representation.

Every canonical record derived from an import should be traceable back to `ImportBatch` and source record.

## 7.5 Mapping configuration

Build configurable column mapping.

Example:

```yaml
entity: inventory_snapshot
version: 1
columns:
  material_code: "Material"
  plant_code: "Plant"
  snapshot_at: "As Of Date"
  unrestricted_qty: "Unrestricted"
  blocked_qty: "Blocked"
  uom: "UOM"
transforms:
  trim_strings: true
  normalize_codes: true
```

Do not hard-code column names in core services.

## 7.6 Data validation

Validation categories:

- missing material code;
- unknown plant;
- invalid date;
- negative quantity where impossible;
- unknown UOM;
- duplicate source key;
- PO receipt > PO ordered quantity;
- BOM cycle;
- missing BOM parent/component;
- forecast bucket overlap;
- impossible date ordering;
- missing required supplier;
- stale source snapshot;
- inconsistent material code casing/format.

Results must go into a Data Quality UI/API, not disappear into logs.

## 7.7 Idempotency

Importing the same source batch twice must not double inventory, demand, or PO quantities.

Use stable source keys + import hashes + upsert/versioning policies.

---

# 8. Planning Event Model

Normalize all supply/demand effects into a common internal event shape used by the planning engine.

```text
PlanningEvent
- event_id
- event_type
- material_id
- plant_id
- event_date
- quantity_delta
- source_entity_type
- source_entity_id
- firmness
- priority
- scenario_id
- metadata
```

Convention:

- supply = positive quantity delta;
- demand/consumption = negative quantity delta.

Examples:

```text
+30,000 PO receipt on 2026-09-08
-10,000 forecast consumption on 2026-09-01
-4,000 production requirement on 2026-09-02
```

Keep the underlying typed source record. `PlanningEvent` is a projection/read model, not the system of record.

---

# 9. Deterministic Planning Engine

This is the core of the product.

## 9.1 First version objective

For every material/plant combination and configurable horizon (default scaffold: 210 days), generate:

- opening available inventory;
- dated supply events;
- dated demand events;
- projected inventory after each event;
- projected minimum inventory;
- first safety-stock breach date;
- first stockout date;
- shortage quantity;
- recovery date;
- coverage/runway;
- excess position;
- supply-demand peg links;
- candidate actions;
- risk severity.

## 9.2 Time buckets

Engine must support:

- daily buckets;
- weekly aggregation;
- monthly aggregation.

Calculate at daily granularity initially if source dates support it; aggregate for UI.

Do not compute only month-end balances because a material can stock out mid-month and recover later.

## 9.3 Projected available balance

Base formula:

```text
PAB(t) = opening_available_inventory
       + cumulative_confirmed_supply_through(t)
       - cumulative_demand_through(t)
```

Safety-aware position:

```text
buffer_adjusted_position(t) = PAB(t) - safety_stock(t)
```

Exact demand priority and available-inventory definition are configurable.

## 9.4 Runway / days of coverage

Implement at least two transparent variants behind configuration:

### Method A — forward simulation

Find first date `t` where projected available balance becomes <= 0.

```text
runway_days = stockout_date - as_of_date
```

Preferred for time-phased demand because it naturally handles irregular consumption.

### Method B — average-demand coverage

```text
coverage_days = available_inventory / average_daily_demand
```

Useful as a display KPI but should not replace time-phased simulation.

The UI must indicate which definition is being displayed.

## 9.5 Shortage detection

A shortage exception exists when:

```text
PAB(t) < configured_threshold
```

Threshold may be:

- zero;
- safety stock;
- minimum coverage;
- customer/program-specific buffer.

Return:

- breach date;
- peak shortage quantity;
- duration;
- impacted demands;
- next recovery supply;
- source of demand change if identifiable.

## 9.6 Recovery date

First future date after breach where projected balance returns above threshold.

## 9.7 Excess detection

Initial simple policy:

- projected ending stock exceeds configured maximum coverage or max inventory;
- or supply exists that is not needed within the horizon.

Do not optimize carrying cost yet.

---

# 10. Supply-Demand Pegging Engine

## 10.1 Why it matters

Without pegging, an alert can say “Component X is short” but cannot answer:

- Which demand caused it?
- Which OEM is impacted?
- Which PO is supposed to cover it?
- Can another receipt cover it?
- What happens if this PO moves five days?

## 10.2 Initial pegging strategy

Implement deterministic FIFO-by-required-date pegging as a first configurable strategy:

1. Sort demand events by required date and configured priority.
2. Use opening inventory first or per configured policy.
3. Sort supply by availability date and firmness.
4. Allocate supply quantities to demand quantities.
5. Persist peg relationships.
6. Allow partial pegs.

### `SupplyDemandPeg`

- `scenario_id`
- `material_id`
- `plant_id`
- `supply_event_id`
- `demand_event_id`
- `pegged_qty`
- `peg_strategy`
- `created_at`

This must be recomputable and versioned by planning run.

## 10.3 BOM demand lineage

If demand comes from BOM explosion, preserve lineage:

```text
OEM -> finished good -> production/forecast demand -> BOM -> component
```

Peg output should retain enough references to traverse that chain.

---

# 11. Pull-In / Push-Out / Cancel / Buy Recommendation Engine

Recommendations are not automatic execution.

Each recommendation must contain:

- what action is suggested;
- quantity;
- current date;
- proposed date;
- reason;
- impacted shortage/excess;
- source records;
- confidence/type;
- constraints checked;
- financial/operational impact placeholders;
- approval status.

## 11.1 Pull-in candidate

Generate when:

- a material will breach its risk threshold;
- there is an open future supply order after the breach;
- pulling all or part of it forward can reduce/resolve shortage;
- the order is not locked by a planning time fence;
- supplier/business constraints do not mark it ineligible.

Basic algorithm:

1. Detect shortage interval.
2. Find future unreceived supply for same material/plant.
3. Calculate minimum quantity required to eliminate or reduce breach.
4. Calculate latest acceptable receipt date.
5. Produce action candidate.

Example:

```text
PULL_IN
PO: 45000123 / line 20
Material: C-1004
Qty: 18,000
Current due: Sep 14
Required by: Sep 09
Reason: projected stockout Sep 10; Honda FG-204 affected
```

## 11.2 New procurement candidate

Generate when no existing movable supply can cover the shortage.

Use configured lead time / MOQ / lot multiple.

Do not create a real PO automatically.

## 11.3 Push-out candidate

Generate when future demand decreases or supply produces excess beyond configured thresholds.

Check:

- cancellation/freeze window;
- supplier push-out eligibility;
- need date of later demand;
- open quantity;
- MOQ/order constraints.

Return proposed new receipt date and quantity.

## 11.4 Cancel/reduce candidate

Generate only when:

- excess persists through horizon or beyond required buffer;
- order is cancellable/reducible;
- cancellation window allows it;
- pegging proves quantity is not required by protected demand.

## 11.5 Expedite candidate

Can be synonymous with pull-in initially, but keep semantic room for:

- supplier expediting;
- alternate transport mode;
- alternate supplier;
- inter-plant transfer.

These alternatives may be added after discovery.

---

# 12. Risk and Priority Engine

Do not use a single opaque “AI risk score.”

Store both severity and ranking factors.

## 12.1 Initial severity

Suggested scaffold:

- `GREEN` — no threshold breach in horizon
- `YELLOW` — threshold/safety breach approaching or low coverage
- `ORANGE` — confirmed shortage but recovery exists before critical demand / moderate impact
- `RED` — production/customer demand is uncovered or stockout occurs before next usable supply
- `CRITICAL` — imminent or current production-stop/customer-service exposure

Actual thresholds must remain configuration.

## 12.2 Priority factors

Build a composable score using configurable weights later:

- days until shortage;
- shortage quantity;
- shortage duration;
- number of affected finished goods;
- number/priority of affected OEMs;
- demand firmness;
- supplier lead time;
- available mitigation options;
- financial value;
- customer priority;
- line-stop risk.

Store factor breakdown so users can understand ranking.

---

# 13. Planning Runs and Versioning

### `PlanningRun`

Fields:

- `id`
- `organization_id`
- `scenario_id`
- `as_of_at`
- `horizon_start`
- `horizon_end`
- `input_version_summary`
- `engine_version`
- `policy_version`
- `started_at`
- `completed_at`
- `status`
- `materials_processed`
- `exceptions_generated`
- `error_summary`

Planning results must be associated with a run so numbers can be reproduced and audited.

Do not mutate old planning runs after completion.

---

# 14. Event/Recalculation Engine

The control tower should eventually feel live, but do not recalculate all materials unnecessarily.

## 14.1 Domain events

Examples:

- `InventoryImported`
- `ForecastChanged`
- `RequirementCreated`
- `POCreated`
- `PODueDateChanged`
- `SupplierCommitChanged`
- `GoodsReceiptPosted`
- `BOMChanged`
- `PlanningPolicyChanged`

## 14.2 Impacted-set computation

When an event occurs, identify affected:

- material;
- plant;
- dependent BOM parents;
- planning horizon.

Queue background recomputation using existing Celery/worker infrastructure.

## 14.3 Reliability

Tasks must be:

- idempotent;
- retryable;
- bounded;
- observable;
- dead-letter/failure visible;
- safe against duplicate events.

Do not use Redis as the authoritative persistent business database.

---

# 15. Scenario / What-If Scaffolding

Do not build advanced optimization yet, but design for it.

### `PlanningScenario`

- `id`
- `organization_id`
- `name`
- `type`
  - BASELINE
  - WHAT_IF
- `base_scenario_id` nullable
- `created_by`
- `created_at`
- `status`

### `ScenarioOverride`

Possible overrides:

- demand quantity/date;
- PO receipt date;
- PO quantity;
- inventory adjustment;
- supplier lead time;
- safety stock;

Scenarios must not alter base transactional records.

Later UI examples:

- “What if Honda demand increases 20%?”
- “What if Supplier A is delayed 10 days?”
- “What if this PO is pulled in by 5 days?”

---

# 16. API Surface

Follow existing GenuineGigs API conventions.

Suggested resource groups:

```text
/scm/imports
/scm/data-quality
/scm/materials
/scm/boms
/scm/inventory
/scm/demand
/scm/supply
/scm/planning-runs
/scm/exceptions
/scm/actions
/scm/scenarios
/scm/control-tower
/scm/config
```

## 16.1 Essential endpoints for scaffolding

### Imports

- upload file
- list imports
- retrieve validation errors
- preview mapping
- execute mapping/load

### Materials

- material list/search
- material detail
- material timeline
- dependent finished goods
- suppliers

### Planning

- trigger run
- run status
- latest material projection
- exception list
- exception detail

### Actions

- recommendation list
- recommendation detail
- accept/reject/defer

Accepting a recommendation initially means workflow acknowledgement, not automatic ERP write-back.

---

# 17. Read Models for UI Performance

Do not make every dashboard request run full planning logic.

Persist or materialize read-optimized results:

### `MaterialProjectionPoint`

- `planning_run_id`
- `material_id`
- `plant_id`
- `date`
- `opening_balance`
- `supply_qty`
- `demand_qty`
- `closing_balance`
- `safety_stock_qty`
- `risk_status`

### `MaterialRiskSummary`

- material
- plant
- first_breach_date
- stockout_date
- shortage_qty
- recovery_date
- severity
- priority_score
- affected_finished_goods_count
- affected_customers_count
- recommended_action_count

Indexes must support filters by plant/status/date/material/supplier/customer.

---

# 18. Control Tower UI — Scaffolding Only

Do not over-polish before Anurag validates the workflow.

Build functional components and data contracts.

## 18.1 Main control tower

Top section:

- last data refresh;
- latest planning run;
- horizon;
- data quality warning count.

KPI cards:

- materials monitored;
- red/critical materials;
- shortages within 7/14/30 days;
- pull-in candidates;
- push-out/cancel candidates;
- projected excess materials.

Primary visualization:

A time-horizon heatmap/grid.

Rows:

- material or grouped finished-good/program.

Columns:

- time buckets across 6–7 months.

Cells:

- green/yellow/orange/red.

Click cell -> explanation drawer.

## 18.2 Exception workbench

Table/list sorted by priority:

- material;
- plant;
- description;
- shortage date;
- days to shortage;
- shortage qty;
- next receipt;
- supplier;
- finished goods;
- OEM/customer;
- recommended action;
- status/owner.

Filters:

- plant;
- supplier;
- OEM/customer;
- material;
- status;
- horizon;
- action type;
- owner.

## 18.3 Material detail

Header:

- material code/description/spec;
- plant;
- primary supplier;
- current inventory;
- current severity.

Timeline chart:

- projected inventory curve;
- safety stock/threshold line;
- supply receipts;
- demand events;
- shortage region.

Below:

- PO schedule lines;
- demand buckets;
- pegged supply/demand;
- impacted BOM/finished goods/OEMs;
- action candidates;
- source data lineage.

## 18.4 BOM impact view

Basic expandable tree is enough initially.

Future graph visualization is optional.

## 18.5 Data quality page

Show:

- failed rows;
- warning rows;
- missing master data;
- stale data sources;
- duplicate mappings;
- unknown UOMs;
- missing supplier/BOM links.

This page is essential. Bad SCM outputs often originate from bad source data.

---

# 19. AI / ML Policy

## 19.1 What NOT to use LLMs for

Never let an LLM be authoritative for:

- arithmetic;
- stock projection;
- shortage dates;
- BOM explosion;
- pegging;
- order quantities;
- lead-time calculations;
- cancellation eligibility;
- source-data reconciliation.

## 19.2 Good LLM use cases later

After deterministic engine is stable:

- explain an exception in plain English;
- summarize why a material became red;
- generate supplier follow-up draft;
- answer natural-language questions over already-calculated data;
- summarize a planner’s daily action queue;
- explain changes between two planning runs.

Example:

> “Why is C-1004 red?”

LLM receives structured evidence and produces a narrative. It does not compute the evidence.

## 19.3 ML candidates later

Only after sufficient historical data:

1. supplier delay probability;
2. lead-time distribution prediction;
3. demand forecast models;
4. consumption anomaly detection;
5. recommended safety stock;
6. risk classification.

Every ML model must be backtested and benchmarked against a simple baseline.

---

# 20. Reuse of Existing GenuineGigs Modules

Codex must specifically inspect and attempt to reuse:

## 20.1 Procurement

Likely reusable concepts:

- suppliers;
- RFQ/vendor information;
- POs;
- PO lines;
- approval workflows;
- user roles;
- notifications;
- audit logging;
- supplier communication.

SCM should enrich procurement with planning context rather than duplicate it.

Example future interaction:

```text
SCM detects shortage
 -> suggests new buy / pull-in
 -> planner accepts
 -> GenuineGigs Procurement opens appropriate workflow
 -> execution happens through approved procurement process
```

## 20.2 Operations

Potential reuse:

- plants;
- organizational structure;
- task/workflow engine;
- alerts;
- issue ownership;
- dashboards;
- status tracking.

## 20.3 Shared platform

Reuse:

- auth;
- RBAC;
- tenant scoping;
- file storage;
- audit;
- background tasks;
- API error conventions;
- Docker setup;
- logging;
- environment settings.

---

# 21. Security and Enterprise Readiness

This is a design-partner production system handling sensitive supply-chain data.

## 21.1 Authentication

Reuse existing secure authentication.

No anonymous SCM access.

## 21.2 RBAC

Minimum roles:

- SCM_ADMIN
- SCM_PLANNER
- SCM_VIEWER
- PROCUREMENT_USER
- EXECUTIVE_VIEWER

Potential scoping:

- organization;
- plant;
- supplier/program.

## 21.3 Tenant isolation

Every query and background task must respect tenant organization boundaries.

Add automated tests for cross-tenant data leakage.

## 21.4 Audit log

Audit:

- imports;
- mapping changes;
- planning-policy changes;
- scenario changes;
- recommendation decisions;
- manual adjustments;
- user exports;
- future ERP write-back actions.

## 21.5 Secrets

No credentials in source code or Docker images.

Use environment/secret management appropriate to deployment.

## 21.6 Encryption

- TLS in transit;
- encrypted persistent storage where provider supports it;
- secure backup storage.

## 21.7 Least privilege

SAP integration user should be read-only for initial phase unless a separate approved write-back use case is implemented.

---

# 22. Production Environments and Deployment

Keep this simple for a solo founder.

## 22.1 Environments

Required:

1. `local/dev`
2. `staging`
3. `production`

Staging should closely mirror production configuration and Docker versions.

## 22.2 Git workflow

Do not create bureaucracy for one developer.

Recommended:

- `main` = production-ready;
- feature branches = all significant work;
- optional `develop` only if it fits the current repo workflow.

A permanent `develop` branch is not mandatory.

Better solo workflow:

```text
feature/scm-import-framework
 -> CI
 -> merge main
 -> auto-deploy staging
 -> smoke test
 -> manual production promotion
```

Use tags/releases for production versions.

## 22.3 CI pipeline

On each feature/main push:

1. lint;
2. type checks if supported;
3. unit tests;
4. integration tests;
5. migration validation;
6. build Docker images;
7. dependency/security scanning if available;
8. artifact/image tagging.

## 22.4 CD pipeline

Staging:

- automatic after merge to main or selected branch.

Production:

- explicit/manual promotion;
- known Docker image digest/tag;
- pre-deploy backup;
- migration step;
- health check;
- smoke tests;
- rollback procedure.

## 22.5 Do not use `latest` image tags for production

Tag by commit SHA/version.

## 22.6 Database migrations

All schema changes through migration framework.

Rules:

- migration files committed;
- backup before destructive changes;
- avoid long blocking migrations;
- prefer backward-compatible expand/migrate/contract for risky changes.

## 22.7 Backups

At minimum:

- automated database backups;
- retention policy;
- encryption;
- restore test.

A backup that has never been restored is not proven.

## 22.8 Initial infrastructure

Use the existing Dockerized architecture on a straightforward production platform/VM/container host or managed service.

Do not introduce Kubernetes unless actual scale/availability requirements justify it.

---

# 23. Observability

Production bugs in planning can be worse than crashes because incorrect numbers may look plausible.

## 23.1 Structured logging

Log with:

- request ID;
- organization;
- user;
- import batch;
- planning run;
- worker task ID;
- material/plant where relevant.

Do not log sensitive credentials or unrestricted raw files.

## 23.2 Application metrics

Track:

- request latency/error rate;
- worker queue depth;
- failed worker tasks;
- import duration;
- rows/sec;
- planning-run duration;
- materials processed/sec;
- planning failures;
- stale source age;
- data-quality error count;
- DB connection usage;
- CPU/memory/disk.

## 23.3 Health checks

Expose:

- liveness;
- readiness;
- DB connectivity;
- Redis/queue connectivity if required.

## 23.4 Error tracking

Integrate the current project’s error tracker, or add one if none exists.

## 23.5 Business-level reconciliation metrics

This is particularly important:

For a sample set of materials compare:

- source inventory vs normalized inventory;
- source open PO qty vs normalized open PO qty;
- source forecast vs normalized forecast;
- manual Excel expected shortage date vs GenuineGigs result.

These should become automated reconciliation reports where possible.

---

# 24. Testing Strategy

## 24.1 Unit tests

Required for:

- UOM conversion;
- BOM explosion;
- PAB calculation;
- runway;
- safety-stock breach;
- stockout/recovery;
- FIFO pegging;
- pull-in recommendation;
- push-out recommendation;
- MOQ/lot rounding;
- time-fence rules.

## 24.2 Golden planning fixtures

Create small deterministic datasets where expected output is manually specified.

Example Fixture A:

```text
Opening inventory: 30
Demand:
 D1: -10 day 1
 D2: -10 day 2
 D3: -10 day 3
 D4: -10 day 4
Supply:
 S1: +20 day 5

Expected:
 day1 PAB 20
 day2 PAB 10
 day3 PAB 0
 day4 PAB -10
 first stockout day3 or configured <=0 semantics
 shortage before receipt: 10
 recovery day5
```

Codex must define exact boundary semantics in tests.

## 24.3 Edge cases

Test:

- zero demand;
- zero inventory;
- same-day supply and demand ordering;
- multiple suppliers;
- partial receipts;
- overdue PO;
- cancelled PO;
- demand increase;
- demand decrease;
- nested BOM;
- BOM cycle;
- missing BOM;
- negative correction;
- no next supply;
- horizon-ending shortage;
- safety-stock-only breach;
- multiple demand priorities;
- multiple plants;
- UOM conversion;
- order multiple rounding;
- planning time fence;
- duplicate import.

## 24.4 Integration tests

Test full flow:

```text
Excel -> raw import -> validation -> canonical load
 -> planning run -> projections -> exception
 -> recommendation -> API -> UI response
```

## 24.5 Performance tests

Initial target dataset:

- 5,000 materials;
- 10 plants;
- 210-day horizon;
- 100k+ planning events;
- nested BOMs.

Do not over-optimize yet, but measure.

Set a target after baseline profiling rather than inventing a hard SLA before real data.

## 24.6 Regression tests

Every production calculation bug must gain a regression test before fix is considered complete.

---

# 25. Data Quality Is a First-Class Module

The system must never silently convert invalid data into confident SCM recommendations.

Introduce statuses:

- VALID
- WARNING
- REJECTED
- QUARANTINED

Planning run can be configured to:

- reject if critical source data is invalid;
- continue with warnings where safe.

Examples of critical failures:

- duplicate material master keys;
- unknown plant for inventory;
- unresolved UOM conversion affecting quantities;
- BOM cycle;
- malformed dates in supply schedules.

---

# 26. Configuration / Policy Engine

All planning policies must be versioned.

### `PlanningPolicySet`

Potential fields:

- planning horizon days;
- default safety stock behavior;
- shortage threshold semantics;
- same-day event ordering;
- pegging strategy;
- forecast consumption logic;
- firm vs forecast demand priority;
- include overdue receipts?;
- stale PO handling;
- default lead time;
- risk thresholds;
- time fences;
- rounding rules.

Store `policy_version` in each planning run.

---

# 27. Discovery Questions for Anurag / Lumax

Do not assume answers. Use the next meeting to resolve these.

## 27.1 Planning scope

1. Exactly which plants are in phase 1?
2. Approximate material count by plant?
3. Planning horizon: 6 months, 7 months, rolling 26 weeks, or something else?
4. Daily, weekly, or monthly decision granularity?
5. Which materials are most critical?
6. Are subassemblies planned like purchased parts?

## 27.2 Source systems

7. Which SAP product/version is used?
8. Which modules provide inventory, PO, BOM, forecast, production demand?
9. Is SAP the source of truth for all these datasets?
10. Which values are maintained only in Excel?
11. Can read-only APIs be exposed?
12. Are scheduled exports easier for phase 1?
13. How frequently should data refresh?
14. Is near-real-time actually required, or is hourly/daily adequate?

## 27.3 Current Excel

15. Obtain a sanitized copy of the exact workbook.
16. What does every column mean?
17. Which columns are manually maintained?
18. Which formulas are business-critical?
19. Which cells/colors trigger decisions?
20. Which rows are ignored and why?
21. What manual steps are performed before/after the workbook?

## 27.4 Inventory

22. Which SAP inventory buckets count as available?
23. Is blocked/QC stock usable?
24. How is reserved stock handled?
25. Are inter-plant transfers considered supply?
26. Is WIP considered?
27. Are goods in transit considered available and on what date?

## 27.5 Demand

28. Distinguish forecast, customer schedule, production plan, indent, firm order.
29. Which demand wins when records overlap?
30. Is forecast consumed by firm demand?
31. How do forecast revisions arrive?
32. How are sudden demand increases handled today?
33. Are customer priorities different by OEM/program?

## 27.6 Supply

34. Which date is trusted: PO due date, supplier commit date, ASN date, planned delivery date?
35. How are partial receipts represented?
36. What counts as overdue?
37. Are blanket/scheduling agreements used?
38. Is material supplied on schedule lines?
39. What are pull-in constraints?
40. What are push-out constraints?
41. What are cancellation windows?
42. Is cancellation window supplier/material-specific?
43. MOQ and order multiples?
44. Can supply be moved across plants?

## 27.7 Shortage logic

45. Define “runway” exactly.
46. Is zero inventory already red or only negative projected stock?
47. Is safety stock a warning threshold?
48. What makes something yellow vs red?
49. What does “NG” mean in the current sheet?
50. How far before stockout should planner be warned?
51. Which shortage types require escalation?

## 27.8 BOM / customer impact

52. Is BOM available directly from SAP?
53. How often are BOMs revised?
54. Are alternate components supported?
55. Are substitutes allowed?
56. Can one component feed multiple finished goods?
57. Can one finished good serve multiple OEMs?
58. Need multi-level BOM explosion?
59. Need engineering revision/effectivity support in phase 1?

## 27.9 Workflow and action

60. Who owns a shortage?
61. Buyer, planner, SCM head, procurement?
62. What action does a user take after seeing a risk?
63. Do they email supplier?
64. Update SAP?
65. Call procurement?
66. Create an escalation?
67. Which actions need approval?
68. What should GenuineGigs write back, if anything, in phase 1?

## 27.10 Visualization

69. What should the first screen answer in 10 seconds?
70. What grouping matters: plant, supplier, customer, commodity, planner, finished good?
71. What time granularity is ideal?
72. Preferred drill-down path?
73. Which metrics appear in management review?
74. Which exports are required?

## 27.11 Success criteria

75. What manual work should disappear?
76. How much planning time is spent on Excel today?
77. How many shortage surprises occur?
78. How do they measure line stoppages/material readiness?
79. What outcome would make them call the pilot successful after 30–60 days?

---

# 28. Recommended Four-Week Aggressive Implementation Sequence

This assumes one founder working heavily with Codex and getting fast access to design-partner data. It is intentionally aggressive.

Do not confuse code-generation time with validation time.

## Pre-meeting: Scaffolding now

Build only reusable foundations:

- repo assessment;
- SCM module/package skeleton;
- canonical data model migrations;
- import batch framework;
- CSV/XLSX importer;
- configurable mapping;
- data validation framework;
- planning event abstraction;
- planning engine interfaces;
- BOM service interfaces;
- planning-run model;
- risk/action enums;
- initial unit-test fixtures;
- local/staging CI improvements if missing.

Do not finalize Lumax calculations or UI yet.

---

## Week 1 — Lumax data contract + baseline engine

### Goals

- ingest actual/sanitized workbook;
- map material, inventory, demand, supply, BOM;
- reconcile totals;
- implement baseline time-phased projection.

### Deliverables

- source-to-canonical mapping config;
- import validation report;
- inventory reconciliation;
- open PO reconciliation;
- demand reconciliation;
- PAB/runway/stockout/recovery engine;
- golden test cases based on Lumax examples;
- planner-facing material detail endpoint.

### Exit criterion

For a hand-selected sample of materials, GenuineGigs numbers match the manually verified Lumax workbook logic or discrepancies are explicitly understood.

---

## Week 2 — Pegging + exceptions + pull/push recommendations

### Deliverables

- supply-demand pegging;
- BOM lineage;
- shortage exception generation;
- severity model;
- priority queue;
- pull-in candidate logic;
- new-buy candidate logic;
- push-out/cancel scaffold;
- explanation data payloads.

### Exit criterion

Given a known shortage scenario, GenuineGigs identifies:

- shortage date;
- quantity;
- recovery;
- future PO causing/solving issue;
- impacted FG/OEM;
- plausible action candidate.

---

## Week 3 — Control tower UI + workflow

### Deliverables

- heatmap/horizon view;
- exception workbench;
- material timeline;
- BOM/customer impact panel;
- action detail;
- data refresh state;
- data quality page;
- owner/status workflow.

### Exit criterion

Anurag can use the UI to find the same issues he currently finds in Excel, faster and across the full horizon.

---

## Week 4 — Production hardening + pilot

### Deliverables

- staging parity;
- monitored production deployment;
- access control;
- audit log;
- automated backup;
- restore procedure;
- import scheduling;
- reconciliation dashboard;
- error tracking;
- load/performance testing;
- pilot runbook;
- rollback runbook;
- user feedback fixes.

### Exit criterion

System is safe enough for controlled design-partner use with read-only ERP integration and human-approved actions.

---

# 29. Codex Execution Backlog

Codex should implement in small PR-sized or commit-sized slices even if only one developer exists.

## Epic A — SCM module foundation

- [ ] Inspect repository architecture
- [ ] Create `SCM_REPO_ASSESSMENT.md`
- [ ] Define SCM module boundaries
- [ ] Add feature flag `SCM_ENABLED`
- [ ] Add SCM permissions/roles using existing auth framework
- [ ] Add SCM navigation placeholder

## Epic B — Canonical model

- [ ] Organization/plant reuse mapping
- [ ] Material model/reuse
- [ ] MaterialPlantPolicy
- [ ] UOMConversion
- [ ] MaterialSupplier
- [ ] BOM + BOMLine
- [ ] Customer usage mapping
- [ ] InventorySnapshot
- [ ] DemandForecast
- [ ] MaterialRequirement
- [ ] SupplyOrder normalized projection
- [ ] GoodsReceipt
- [ ] migrations
- [ ] factories/fixtures

## Epic C — Import framework

- [ ] ImportBatch
- [ ] RawImportRecord or raw-file trace mechanism
- [ ] Connector interface
- [ ] CSV connector
- [ ] Excel connector
- [ ] mapping config
- [ ] validation rules
- [ ] preview import API
- [ ] commit import API
- [ ] rejected-row storage
- [ ] idempotency tests

## Epic D — BOM engine

- [ ] BOM cycle detection
- [ ] effective-date selection
- [ ] single-level explosion
- [ ] multi-level explosion
- [ ] lineage path
- [ ] unit tests

## Epic E — Planning engine

- [ ] PlanningEvent projection
- [ ] PlanningScenario
- [ ] PlanningRun
- [ ] daily projection
- [ ] aggregation
- [ ] safety threshold
- [ ] stockout/recovery
- [ ] runway/coverage
- [ ] excess detection
- [ ] material projection persistence
- [ ] golden test suite

## Epic F — Pegging

- [ ] demand ordering
- [ ] supply ordering
- [ ] opening stock allocation
- [ ] partial pegs
- [ ] peg persistence
- [ ] reverse trace
- [ ] BOM/OEM lineage
- [ ] tests

## Epic G — Exceptions/actions

- [ ] MaterialRiskSummary
- [ ] severity engine
- [ ] priority factor model
- [ ] pull-in candidate
- [ ] new-buy candidate
- [ ] push-out candidate
- [ ] cancel/reduce candidate
- [ ] recommendation explanation
- [ ] accept/reject/defer workflow

## Epic H — Event/recompute

- [ ] domain events
- [ ] impacted-material calculation
- [ ] Celery task integration
- [ ] retries
- [ ] idempotency
- [ ] failure visibility

## Epic I — UI scaffold

- [ ] SCM overview route
- [ ] KPI cards
- [ ] horizon heatmap
- [ ] exceptions table
- [ ] material detail
- [ ] inventory timeline
- [ ] supply/demand events
- [ ] BOM/OEM impact
- [ ] action drawer
- [ ] import/data quality page

## Epic J — Production readiness

- [ ] staging config
- [ ] CI tests
- [ ] tagged images
- [ ] manual production promotion
- [ ] DB backup
- [ ] restore test docs
- [ ] structured logs
- [ ] error tracking
- [ ] health endpoints
- [ ] worker metrics
- [ ] audit coverage
- [ ] security checks

---

# 30. Suggested Code Organization

Codex must adapt to existing repo conventions rather than blindly creating this exact tree.

Conceptually:

```text
backend/
  scm/
    domain/
      materials
      bom
      supply
      demand
      planning
      risk
      actions
    application/
      imports
      planning_runs
      exception_workbench
      scenarios
    infrastructure/
      connectors/
        csv
        excel
        sap_stub
      repositories
      workers
    api/
    tests/
      unit/
      integration/
      fixtures/

frontend/
  scm/
    pages/
      ControlTower
      Exceptions
      MaterialDetail
      Imports
    components/
      HorizonHeatmap
      ProjectionChart
      RiskBadge
      ActionDrawer
      BOMImpactTree
    api/
    types/
```

Avoid premature microservices.

---

# 31. Calculation Explainability Contract

Every exception endpoint should be able to return an explanation object similar to:

```json
{
  "material": "C-1004",
  "plant": "P1",
  "as_of_date": "2026-08-20",
  "opening_available_qty": 30000,
  "first_threshold_breach_date": "2026-08-29",
  "first_stockout_date": "2026-08-30",
  "peak_shortage_qty": 18000,
  "next_recovery_date": "2026-09-01",
  "triggering_demands": [],
  "expected_supplies": [],
  "impacted_finished_goods": [],
  "impacted_customers": [],
  "recommended_actions": [],
  "policy_version": "v1",
  "planning_run_id": "...",
  "source_lineage": []
}
```

The exact schema may differ, but explanation must be first-class.

---

# 32. Data Freshness Model

Every dashboard must indicate freshness.

### `DataSourceState`

- connector/source
- last_successful_import
- last_attempt
- status
- expected_frequency
- stale_after
- records_processed

If inventory is stale, the control tower must display it prominently.

Never show a “green” material without warning if key source data is stale beyond configured tolerance.

---

# 33. Manual Overrides

Planners may need temporary corrections during pilot.

Do not edit imported facts directly.

Create `PlanningAdjustment`:

- material;
- plant;
- type;
- quantity/date override;
- reason;
- created_by;
- created_at;
- expires_at optional;
- approval state.

Every adjustment must be visible in explanation and audit logs.

---

# 34. Performance Design

Start with PostgreSQL or the existing relational DB.

Optimize only after profiling.

Recommended initial tactics:

- indexes on `(organization, plant, material, date)`;
- bulk inserts/upserts;
- avoid ORM N+1 queries;
- precomputed read models;
- batch planning by material/plant;
- worker parallelism bounded by DB capacity;
- incremental recompute after source changes;
- cache UI summaries only when invalidation is clear.

Do not add a graph database only because the domain is graph-like.

---

# 35. Failure Modes to Design Against

## 35.1 Plausible but wrong numbers

Mitigation:

- reconciliation;
- explainability;
- source lineage;
- tests;
- data freshness;
- policy versioning.

## 35.2 Duplicate import doubles supply

Mitigation:

- stable source IDs;
- hashes;
- idempotent upserts;
- duplicate batch detection.

## 35.3 PO rescheduled but old due date remains

Mitigation:

- version/source sync policy;
- source record identity;
- latest active schedule line semantics.

## 35.4 BOM change rewrites history

Mitigation:

- effective dating/revisions.

## 35.5 Same part code exists at multiple plants

Mitigation:

- material master vs plant policy separation;
- plant-scoped planning.

## 35.6 Forecast and firm orders double counted

Mitigation:

- explicit forecast-consumption policy after Lumax validation.

## 35.7 Users trust stale data

Mitigation:

- freshness banner;
- block/flag planning when source stale.

## 35.8 AI gives different arithmetic than engine

Mitigation:

- LLM receives calculated values only;
- never asks LLM to recompute.

---

# 36. Definition of Done for the Pre-Anurag Scaffolding

The pre-discovery scaffolding is complete when all of the following are true:

- [ ] SCM lives cleanly inside the existing GenuineGigs repo.
- [ ] Existing auth/tenant/platform components are reused.
- [ ] Canonical SCM entities exist with migrations.
- [ ] CSV/XLSX can be uploaded and mapped to at least a sample dataset.
- [ ] Imports are traceable and idempotent.
- [ ] Invalid records are visible.
- [ ] BOM model and explosion interface exist.
- [ ] PlanningEvent interface exists.
- [ ] PlanningRun/scenario/policy abstractions exist.
- [ ] Basic deterministic projection engine works on synthetic test fixtures.
- [ ] Risk/action interfaces exist but customer rules remain configurable.
- [ ] At least one simple control-tower page can render synthetic projections.
- [ ] CI runs tests.
- [ ] Staging deployment path is known/working or documented.
- [ ] No actual SAP credentials/assumptions are hard-coded.
- [ ] No ML dependency is required to produce baseline planning results.

---

# 37. What Should Be Left Intentionally Unfinished Before Lumax Discovery

Leave these as configuration/TODO until Anurag defines them:

- exact runway formula used operationally;
- exact available-inventory buckets;
- forecast-consumption rules;
- same-day supply vs demand ordering;
- red/yellow/green thresholds;
- cancellation logic;
- pull-in constraints;
- push-out constraints;
- supplier commitments vs PO dates;
- alternate parts/substitution;
- plant-transfer logic;
- customer/OEM prioritization;
- exact dashboard grouping;
- SAP transport mechanism;
- refresh frequency;
- write-back scope;
- approval workflow.

This is intentional. Building these before discovery would create rework disguised as progress.

---

# 38. Post-Discovery Artifacts Codex Should Generate

After the Lumax session, update this plan and create:

1. `LUMAX_DATA_DICTIONARY.md`
2. `LUMAX_SOURCE_MAPPING.yaml`
3. `LUMAX_PLANNING_RULES.md`
4. `LUMAX_ACCEPTANCE_TESTS.md`
5. `LUMAX_UI_WORKFLOWS.md`
6. `LUMAX_DEPLOYMENT_RUNBOOK.md`
7. `LUMAX_PILOT_METRICS.md`

The pilot should not begin without explicit acceptance examples.

---

# 39. Pilot Metrics

Measure product value, not just feature completion.

Potential metrics:

- time spent preparing SCM Excel/report;
- time from data refresh to identified shortage;
- number of future shortages identified earlier;
- shortage surprises after pilot;
- planner action lead time;
- pull-in actions generated/resolved;
- excess/push-out opportunities identified;
- projected line-stop risks avoided;
- material readiness percentage;
- data reconciliation accuracy;
- active planner usage.

Baseline these before claiming improvement.

---

# 40. Product Direction Beyond Lumax

The reusable GenuineGigs SCM module should eventually support:

## Phase 1 — Visibility

- ingest ERP/Excel;
- normalized data;
- projected inventory;
- control tower;
- exceptions;
- BOM/customer impact.

## Phase 2 — Decision support

- pull-in/push-out;
- new-buy;
- cancellation;
- scenario analysis;
- supplier collaboration;
- procurement handoff.

## Phase 3 — Predictive intelligence

- supplier delay risk;
- lead-time prediction;
- forecast adjustment;
- inventory optimization;
- dynamic safety stock.

## Phase 4 — Controlled execution

- approved ERP write-backs;
- automated supplier communication;
- workflow orchestration;
- multi-plant rebalancing;
- human-in-the-loop agents.

## Phase 5 — Manufacturing operations intelligence layer

Connect SCM with existing GenuineGigs procurement and operations to create a broader execution layer across:

- demand;
- materials;
- suppliers;
- procurement;
- quality;
- stores;
- production readiness;
- operational exceptions.

---

# 41. Key Technical Decisions Summary

1. **ERP-overlay, not ERP replacement.**
2. **Canonical model between connectors and planning.**
3. **Raw imports remain traceable.**
4. **Deterministic planning first.**
5. **Supply-demand pegging is foundational.**
6. **BOM/customer lineage is foundational.**
7. **Action queue matters more than giant tables.**
8. **LLMs explain; they do not calculate.**
9. **ML comes after historical data and baseline validation.**
10. **Relational DB first; no premature graph DB.**
11. **Celery/Redis can be reused for jobs, not authoritative state.**
12. **Incremental recompute via domain events.**
13. **Staging + CI + backups + observability before design-partner production.**
14. **Read-only ERP first; write-back only later with approval.**
15. **No Kubernetes unless proven necessary.**
16. **Data quality and freshness are visible product features.**
17. **Every recommendation must be explainable.**
18. **Every production bug creates a regression test.**

---

# 42. First Codex Prompt

Give Codex this entire `PLAN.md`, then use a prompt similar to:

> Read PLAN.md fully. First inspect the existing GenuineGigs repository; do not implement yet. Produce SCM_REPO_ASSESSMENT.md showing the current architecture, what existing procurement/operations/auth/background-job/database components can be reused, conflicts with PLAN.md, and your recommended exact implementation sequence. Then implement only the pre-Anurag scaffolding described in Section 36, in small testable steps. Do not invent Lumax-specific business rules. Before each major module, state which existing code you are reusing. Add tests for every deterministic calculation and import idempotency. Keep the application runnable through the existing Docker workflow at each milestone.

After Codex produces the repo assessment, review it before allowing broad implementation.

---

# 43. Second Codex Prompt — After Repo Assessment

> Using the approved SCM_REPO_ASSESSMENT.md and PLAN.md, implement the SCM foundation in this order: (1) feature/module boundary and permissions, (2) canonical data models/migrations, (3) import batch + CSV/XLSX mapping/validation, (4) BOM service, (5) PlanningEvent + PlanningRun abstractions, (6) deterministic projection engine against synthetic fixtures, (7) risk/action interfaces, (8) minimal SCM UI against synthetic data. Reuse existing GenuineGigs supplier, PO, user, tenant, plant, Celery/Redis, logging, and audit capabilities where they are appropriate. Do not build actual SAP transport, ML forecasting, production write-back, or Lumax-specific business formulas yet. Run the full test suite after every milestone and fix regressions before continuing.

---

# 44. Third Codex Prompt — After Anurag Discovery

Do not use until the meeting is complete and Lumax artifacts are filled.

> Read PLAN.md plus LUMAX_DATA_DICTIONARY.md, LUMAX_PLANNING_RULES.md, LUMAX_ACCEPTANCE_TESTS.md, and the sanitized source files. Create a gap analysis between the generic scaffold and actual Lumax requirements. Do not code immediately. Identify ambiguities, rules that affect arithmetic, source-system mappings, and UI workflow changes. Then implement only the validated requirements, ensuring each manually confirmed Lumax example becomes an automated golden test.

---

# 45. Final Product Principle

The core promise should be:

> **GenuineGigs tells a manufacturing SCM team what material will become a problem, when it will become a problem, what downstream production/customer demand is exposed, why the problem exists, and what action should be considered — using the company’s existing ERP and planning data.**

If a feature does not strengthen that promise during the design-partner phase, it is probably not a priority.
