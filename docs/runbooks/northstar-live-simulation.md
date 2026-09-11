# Northstar live manufacturing validation

This environment is a closed-loop factory acceptance system. Synthetic source systems send records through connector APIs; they never write GenuineGigs tables directly.

## Start

```bash
export V2_SIMULATION_PASSWORD='Northstar@2026'
export FACTORY_SIMULATOR_TOKEN='northstar-local-simulator-token'
docker compose --profile simulation up --build
```

Open `http://localhost:3000/login` and sign in as `rhea.nair@northstar-mobility.local`. The administrator page contains the live factory control room. Normal production events are emitted every two seconds and drained by scheduled connector jobs every two seconds.

## Acceptance chain

Every scenario must be verified at all checkpoints:

1. Source state changes in `GET :8090/sim/v1/state`.
2. A cursor record appears in `GET :8090/sim/v1/streams/{capability}`.
3. An `integration_ingestion_records` receipt stores source key, hash, cursor and canonical target.
4. The appropriate canonical MES/QMS/CMMS/inventory/business row exists.
5. A detector creates or updates a deviation where applicable.
6. A role-owned task/action and notification exist.
7. An outbox event is exposed over `/api/v2/stream`.
8. The authorized role Home or workspace changes without a refresh.
9. Recovery records complete dependencies and actions.
10. Resumed good production verifies recovery with measured evidence.

## Scenario checkpoints

| Scenario | Source streams | Expected operational result | Primary persona |
|---|---|---|---|
| Normal on-plan shift | production, quality, inventory | Counts advance, measurements stay controlled, connector is fresh | Production Manager |
| Spindle temperature failure | machine, downtime, maintenance | L01 stops; fault, downtime deviation and repair action appear | Maintenance Manager |
| Dimensional drift | quality | Rejection and SPC deviations appear with lot traceability | Quality Manager |
| Supplier material delay | supplier commitment, inventory | TSF-72 readiness becomes AT_RISK/BLOCKED | Purchase Executive |
| Missing spare | CMMS, inventory | Repair action waits on a Stores-owned spare dependency | Stores Manager |
| Line recovery | CMMS, machine, production | Repair completes, dependency resolves, output resumes, recovery becomes verified | Plant Manager |
| Connector outage | connector | Jobs fail and source health is error/stale; normal mode replays the retained cursor buffer | Administrator |
| Customer order surge | ERP business stream | A scheduled MES-160 work order is created | Production Manager |
| Supplier email change | supplier email stream | An inbound supplier channel message appears | Purchase Executive |
| Urgent management requirement | management stream | An urgent capacity-response task is assigned | Production Manager |
| Inbound vehicle mismatch | logistics stream | A Gate Operator task appears | Gate Operator |
| Malformed source record | QMS stream | Record is rejected with an ingestion error; no canonical row is fabricated | Administrator |
| Duplicate replay | any retained stream | Receipt deduplication prevents a second canonical record | Administrator |

## Personas

All accounts use `V2_SIMULATION_PASSWORD`.

| Role | Email |
|---|---|
| Corporate Operations Director | ananya.deshmukh@northstar-mobility.local |
| Plant Manager | vikram.kulkarni@northstar-mobility.local |
| Production Manager | meera.jadhav@northstar-mobility.local |
| Production Supervisor | rohit.shinde@northstar-mobility.local |
| Production Operator | kavita.pawar@northstar-mobility.local |
| Maintenance Manager | suresh.more@northstar-mobility.local |
| Maintenance Technician | imran.shaikh@northstar-mobility.local |
| Quality Manager | neha.bhosale@northstar-mobility.local |
| Quality Inspector | pooja.salunkhe@northstar-mobility.local |
| Purchase Manager | aditya.joshi@northstar-mobility.local |
| Purchase Executive | snehal.patil@northstar-mobility.local |
| Stores Manager | nitin.gaikwad@northstar-mobility.local |
| Gate Operator | mahesh.chavan@northstar-mobility.local |
| Workspace Administrator | rhea.nair@northstar-mobility.local |

## Automated acceptance

```bash
bash scripts/test-v2-simulation.sh
```

To include the browser suite after Playwright system dependencies are installed:

```bash
RUN_BROWSER_E2E=1 bash scripts/test-v2-simulation.sh
```

## Isolation and reset

The seed command returns immediately when Northstar already exists. To reconcile it from a clean state while preserving Apex and all other tenants:

```bash
docker compose --profile simulation run --rm seed-v2-simulation -m app.db.seed_v2_cli --reset
```

Resetting the source simulator from the Admin page clears only its current scenario and source cursor buffer. The Docker volume persists unconsumed events across simulator restarts to test replay behavior.
