# GenuineGigs current-to-target architecture map

This file is the Phase 0 implementation ledger for the Core Manufacturing
Platform. Existing module routes remain compatibility APIs; new cross-module
behavior uses `app.platform` services and `/api/v1/platform` contracts.

| Existing implementation | Platform target | Migration decision |
|---|---|---|
| `Tenant` | Tenant boundary | Reuse unchanged |
| `Company` | Organization | Reuse through platform catalog facade |
| `Plant` | Site | Reuse; plant ID is the canonical site ID |
| `PlantArea` | Area | Reuse |
| `ProductionLine` | WorkCenter / ProductionLine | Reuse |
| `PlantAsset` | EquipmentAsset | Reuse |
| `Uom` | Unit of measure | Reuse; conversions remain SCM extension initially |
| `Item` | Legacy Procurement material | Map to `PlatformMaterial` with `ExternalEntityReference` |
| `SCMMaterial` | Legacy SCM material/read model | Map to `PlatformMaterial`; no new module masters |
| `Supplier` | Canonical Supplier | Reuse and enrich with organization/code/metadata fields |
| `ManufacturingProduct` | Legacy Operations product | Map to `PlatformProduct` |
| `SCMBOM` / `ManufacturingBOMLine` | Legacy BOM sources | Map to `PlatformBOM` / `PlatformBOMItem` |
| SCM/Operations inventory snapshots | Source observations | Project into `PlatformInventoryPosition` and `MaterialStateProjection` |
| `ProductionWorkOrder` | Canonical work-order adapter | Reuse and expose from platform state API |
| `OperationalStateSnapshot` | Production-state projection | Reuse via platform state service |
| `RecoveryCase` | Operations case detail | Link to `OperationalCase`; preserve recovery evidence and verification |
| `Case` | Procurement case detail | Link to `OperationalCase` |
| `Task` | Shared work item | Reuse via platform work service/API |
| `EventOutbox` | Canonical outbox | Reuse with versioned envelope columns and registry validation |
| `EventConsumerReceipt` | Consumer idempotency | Reuse |
| `OperationalAction` / `V2PreparedAction` | Legacy action details | Link/propose through `ActionIntent` for consequential changes |
| `PolicyDecisionRecord` | General agent policy record | Reuse; action-specific evaluation remains `ActionPolicyEvaluation` |
| `IntegrationConnection` | Connector instance | Reuse and link to `SourceSystem` |
| import/sync/ingestion tables | Integration pipeline | Reuse; write canonical identity/provenance records |
| Procurement agents / Operations agents | Shared runtime | Use platform context + typed action tools; no direct critical writes |

## Dependency rules enforced

- Cross-module coordination uses canonical events or `app.platform` services.
- Existing direct ORM access remains only as a compatibility adapter during
  progressive migration.
- No module may introduce a new Plant, Supplier, Material, audit, event, or
  permission master.
- Phase 9 (Temporal/Kafka) and Phase 10 (real plant edge) remain intentionally
  dormant until the trigger conditions in the architecture document are met.
