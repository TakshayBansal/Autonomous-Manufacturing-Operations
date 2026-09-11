# Core hardening implementation audit

This audit was recorded before the final SCM-readiness hardening changes.

## Existing

- Shared tenant/company/plant identity: `Tenant`, `Company`, `Plant`.
- Shared manufacturing hierarchy: `PlantArea`, `ProductionLine`, `PlantAsset`.
- Shared supplier master: `Supplier`, enriched with company, code, legal name, lead time and metadata.
- Platform masters/read models: `PlatformMaterial`, `PlatformMaterialSite`, `PlatformProduct`, `PlatformBOM`, `PlatformBOMItem`, `PlatformInventoryLocation`, `PlatformInventoryPosition`.
- Source registry, external identity and provenance: `SourceSystem`, `ExternalEntityReference`, `DataProvenance`, plus the older connector ingestion/import receipt tables.
- Transactional `EventOutbox`, versioned platform envelope, per-consumer `EventConsumerReceipt`, retry/dead-letter/replay dispatcher.
- Relationship storage: `EntityRelationship`.
- Material and work-order state adapters plus generic state snapshots.
- Governed action records: `ActionIntent`, policy evaluation, approval, execution and outcome.
- Platform `OperationalCase`, shared task facade, audits with correlation IDs.
- SCM deterministic planning/scenario engine and Operations simulation/recovery engine.

## Partially existing

- Canonical event catalog covers a few platform flows but not the required Procurement/SCM/Operations families.
- Canonical backfill maps Procurement items, SCM materials and Operations products/BOMs, but not purchase orders, work orders, hierarchy/routings and all inventory/supplier relationships.
- Material state exposes inventory/risk/provenance, but there is no uniform `now / at / history` contract across entity types.
- Action governance is shared, but intent evidence, originating case/risk, expected impact, confidence/risk and external execution receipt are not first-class.
- Outbox retry is durable, but consumer failure receipts are rolled back and retry scheduling/dead-letter timestamps are absent.
- SCM supply orders can reference Procurement records through loose `source_entity_*` fields, not an authoritative canonical PO identity.

## Missing

- Canonical `PurchaseOrder` and a platform identity bridge for `ProductionWorkOrder`.
- Automatic graph synchronization and traversal/impact services.
- Unified chronological correlation trace API.
- Shared simulation scenario/run/output contract.
- Deterministic cross-layer end-to-end architecture acceptance test and requested failure/invariant tests.
- Comprehensive canonical integrity checker for duplicates, orphans, missing site ownership and broken BOM/work-order references.

## Legacy / duplicate

- `Item`, `SCMMaterial`, and Operations BOM component strings can describe the same material.
- `SCMBOM`/`SCMBOMLine` and Operations `ManufacturingProduct`/`ManufacturingBOMLine` coexist with platform Product/BOM.
- `SCMInventorySnapshot` and Operations `MaterialInventoryPosition` coexist with platform inventory positions.
- `PODraft` and `SCMSupplyOrder` describe overlapping purchase-order concepts.
- Two integration identity/receipt families predate the platform `ExternalEntityReference` and `DataProvenance` facade.

## Needs migration

- Every retained domain material/product/BOM/inventory/PO/work-order identity must resolve to a platform/shared canonical ID.
- Normal ingestion, BOM/supplier/PO/work-order changes and backfills must populate canonical relationships automatically.
- SCM planning must consume canonical mappings and propose governed actions rather than mutate Procurement-owned records.
- Operations and SCM simulations must register through one shared scenario/run contract while retaining their algorithms.

