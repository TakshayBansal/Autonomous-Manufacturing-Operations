# GenuineGigs SCM — 50-product end-to-end test

Test workbook: `SCM_50_Product_End_to_End_Test.xlsx`

The workbook was generated on **2026-08-27** using live-relative planning dates. It contains 396 connected records across 12 importer-supported sheets.

## Dataset map

| Data | Records | Purpose |
|---|---:|---|
| Materials | 50 | 10 finished goods and 40 purchased components |
| Plant policies | 50 | Lead time, safety stock, MOQ and ordering multiples |
| Customers / usage | 5 / 10 | Finished-good OEM exposure |
| BOMs / BOM lines | 10 / 40 | Four components per finished good |
| Inventory snapshots | 50 | Fresh on-hand and available balances |
| Forecasts / requirements | 50 / 50 | Medium-term forecast and firm demand |
| Supply orders / schedules | 38 / 38 | Confirmed purchase-order supply, including delays |
| Goods receipts | 5 | Recent inbound history |

Expected scenario groups:

- `GG-CMP-001`–`008`: critical; supply arrives well after firm demand.
- `GG-CMP-009`–`016`: watch/short-duration exposure.
- `GG-CMP-017`–`028`: healthy supply coverage.
- `GG-CMP-029`–`034`: excess inventory candidates.
- `GG-CMP-035`–`038`: supplier delay; original day 8 moved to day 27.
- `GG-CMP-039`–`040`: critical demand with no confirmed supply.
- `GG-FG-001`–`010`: finished goods connected to customers and BOMs.

Exact counts can include the four pre-existing SCM demo materials if the demo workspace has already been seeded.

## 1. Start the complete stack

From the repository root:

```bash
docker compose build migrate api worker web
docker compose up -d postgres migrate api worker web
docker compose ps
```

The `migrate` container must show a successful exit and the API, worker and web services must be running.

If this is a completely empty database, initialize the demo workspace and approved UOM master once:

```bash
docker compose --profile simulation run --rm seed-platform-demos
```

Open `http://localhost:3000/login` and sign in as the SCM demo administrator.

## 2. Preview the Excel workbook

1. Open **SCM → Imports & Quality**.
2. Choose `test-data/SCM_50_Product_End_to_End_Test.xlsx`.
3. Select **Preview import**.
4. Verify the preview reports **396 valid**, zero rejected and zero ignored rows.
5. Spot-check that all 12 sheets are discovered.
6. Do not commit if required rows are rejected; inspect their row-level messages first.

## 3. Commit and verify ingestion

1. Select **Commit valid rows**.
2. Wait until the batch status becomes `completed`.
3. Confirm Data Health shows the file source and no rejected records.
4. Open **Materials** and search for:
   - `GG-FG-001`
   - `GG-CMP-001`
   - `GG-CMP-020`
   - `GG-CMP-039`
5. Confirm descriptions, UOM and material types match the workbook.

Re-uploading the unchanged workbook should resolve to the existing completed batch rather than duplicating canonical records.

## 4. Run the baseline plan

1. Open **Control Tower**.
2. Select **Run fresh plan**.
3. Wait for the planning run to become `COMPLETED`.
4. Open **Supply Horizon** and use the 210-day view.
5. Verify the scenario groups above produce visibly different coverage bands.

Key checks:

- `GG-CMP-001` should show a shortage before its confirmed receipt.
- `GG-CMP-020` should remain covered.
- `GG-CMP-035` should expose the delayed receipt.
- `GG-CMP-039` should have no receipt marker and should be critical.
- `GG-CMP-030` should retain high/excess coverage.

Open a material profile and verify its inventory, dated demand, dated receipts, projection, risk explanation and recommendation are mutually consistent.

## 5. Prove manual data changes the plan

### Resolve an uncovered material

1. In Supply Horizon select `GG-CMP-039`.
2. Select **Add delivery**.
3. Enter:
   - Quantity: `2000 EA`
   - Expected delivery: a date before its displayed demand date
   - Reason: `Supplier confirmed emergency replenishment for test`
4. Select **Save & replan**.
5. Open **Data Entries** and verify the entry has a correlation ID and its plan moves from queued to completed.
6. Return to Supply Horizon and verify the receipt appears and the shortage is removed or materially reduced.

### Correct physical inventory

1. Select **Add data → Correct inventory**.
2. Choose `GG-CMP-040` and enter `2000 EA`.
3. Save with a cycle-count reason.
4. Verify the new plan uses 2,000 as opening available and does not change the imported Excel row.

### Repair a supplier delay

1. Select **Add data → Change delivery date**.
2. Choose `GG-CMP-035` and its open PO schedule.
3. Move delivery to a date before the requirement.
4. Save and verify the risk changes only after the automatic planning run completes.

### Increase demand

1. Select **Add data → Change demand**.
2. Choose a healthy material such as `GG-CMP-020` and its demand record.
3. Increase quantity enough to exceed available inventory and supply.
4. Confirm a previously healthy material becomes at-risk and a recommendation is generated.

## 6. Test manual-versus-Excel reconciliation

1. Keep one of the manual entries above active.
2. Make a copy of the workbook and change the matching material's Inventory or Requirement row.
3. Change that row's `external_id` as well, so it represents a new source observation rather than an idempotent replay.
4. Preview and commit the modified workbook.
5. Open **Data Entries → Source conflicts**.
6. Verify the import did not silently overwrite the manual value.
7. Test **Keep manual** and confirm the overlay remains active.
8. Repeat with another changed source row and test **Accept import**; verify the manual entry becomes reconciled and another plan is started.

## 7. Test validation and failure behavior

Use copies of the workbook—do not damage the golden file.

- Change a `base_uom` to `INVALID`: commit should reject the affected material.
- Remove a required `material_code`: preview should reject the row.
- Duplicate an `external_id` in the same sheet: preview should report a duplicate source key.
- Add an Excel formula to an imported field: preview should reject the formula.
- Set schedule `received_qty` greater than `scheduled_qty`: commit should reject the schedule.
- Stop the worker, save a manual entry, and verify the entry persists with a queued plan. Restart the worker and verify processing recovers.

## 8. Final acceptance checklist

- [ ] 396 valid source rows previewed.
- [ ] Import completed with provenance and batch history.
- [ ] Re-upload created no duplicates.
- [ ] 50 workbook materials are searchable.
- [ ] Healthy, watch, critical, delayed and excess patterns are visible.
- [ ] BOM/product impact is traceable.
- [ ] Manual delivery changes the horizon after replanning.
- [ ] Inventory correction changes opening availability.
- [ ] Demand increase creates a new risk.
- [ ] Manual/import conflicts require an explicit decision.
- [ ] Invalid rows are surfaced rather than silently accepted.
- [ ] Worker interruption does not lose saved input or queued planning work.

If testing occurs more than roughly one day after the generated date, regenerate the workbook so inventory timestamps remain fresh:

```bash
apps/api/.venv/bin/python scripts/generate_scm_50_product_workbook.py
```
