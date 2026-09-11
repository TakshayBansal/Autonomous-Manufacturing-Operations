# Developer Lab — Factory Simulation and Backend Observatory

The Developer Lab is an isolated local test bench. It is not part of the
customer-facing V2 product and is available only through the `developer-lab`
Compose profile on host loopback.

## Start the complete lab

```bash
docker compose --profile developer-lab up --build -d
```

Open:

- Developer Lab: `http://127.0.0.1:3100`
- GenuineGigs product: `http://localhost:3000`
- Mailpit mailbox: `http://localhost:8025`
- Jaeger traces: `http://localhost:16686`
- MQTT broker: `localhost:1883`
- OPC UA server: `opc.tcp://localhost:4840/northstar/`

## Continuous streaming controls

Starting or restarting any scenario automatically enables continuous streaming.
At `1x`, virtual time follows wall-clock time; `10x` advances ten simulated
seconds per real second. The run bar must show `AUTO STREAMING`.

`Step +10s` is a debugging control: it advances exactly one tick and then leaves
the run paused. Click `Resume streaming` to return to automatic progression.
The same button becomes `Pause streaming` while the loop is running. If the
background loop encounters an exception, the run bar displays `LOOP ERROR`
with the latest error instead of silently appearing frozen.

The profile adds Factory Lab, MQTT, OPC UA, the outbound edge bridge, Jaeger,
and the Developer Lab UI. The normal product still uses its existing API,
PostgreSQL, Redis/Celery, outbox/SSE and web services.

## First complete test

1. Open **Scenarios** and run `S02 Gradual machine degradation`.
2. Set speed to `10×` from the global run bar.
3. Open **Factory truth**. Confirm CNC-01 remains the simulator's source truth;
   this panel does not show a GenuineGigs conclusion.
4. Open **Timeline**. Select a vibration or temperature event and choose its
   trace. The trace first shows emission, then connector receipt and canonical
   normalization when ingestion catches up.
5. Open **State / twin**. Compare physical Line 01 state with the six independent
   GenuineGigs state dimensions and source freshness.
6. Open **Detectors**. Inspect trigger facts, rule version, expected/current
   state, derived lost units and severity.
7. Open **Recovery**. Inspect all candidate playbooks, score components,
   constraints, freshness, history and the deterministic recommendation.
8. In the product, sign in as Plant Manager and select a recovery strategy.
   The simulator responds with source-system facts, never a forced recovery
   label.
9. Return to **Timeline**, **Recovery**, **Value ledger** and **Assertions**.
   Recovery must verify only after post-action operational evidence arrives.
10. Use **Fork** at the same event and choose another recovery strategy. Review
    both run records under **Replay & compare**.

## Test source and data failures

Use **Source systems** to pause one source independently. Use **Chaos** for
bounded latency, loss, duplication, out-of-order delivery, API errors and clock
skew. Every chaos setting is stored with the run and seeded for reproduction.

Use **Manual inject** to:

- publish raw machine mode, temperature and vibration;
- start a factual machine, quality, material, counter or source-conflict preset;
- send a supplier message through actual SMTP with a generated CSV or PDF
  attachment.

Mail is visible in Mailpit. MQTT publishes Sparkplug-inspired birth/data state.
The edge bridge subscribes to MQTT and posts through the signed, idempotent edge
endpoint. The OPC UA hierarchy exposes Plant → Machining → CNC-01-01 and its
current source tags.

## Golden regression pack

The initial immutable pack contains:

- S01 Healthy stable shift
- S02 Gradual machine degradation
- S03 Sudden machine fault
- S04 Supplier commitment slip
- S05 Quality SPC drift
- S06 Material quality hold
- S07 Production counter reset
- S08 Source authority conflict
- S09 Connectivity outage and replay
- S10 Repair versus reroute

Run the headless pack after the stack is healthy:

```bash
docker compose --profile developer-lab exec factory-simulator \
  python golden_runner.py all --steps 30
```

Run one scenario:

```bash
docker compose --profile developer-lab exec factory-simulator \
  python golden_runner.py gradual_machine_degradation --steps 30
```

`WAITING` is reported separately from `PASS`; the runner never treats missing
evidence as success.

## Safety and isolation

- The browser binds only to `127.0.0.1:3100`.
- Observatory APIs require both `DEVELOPER_LAB_ENABLED=true` and the developer
  token.
- Simulator control uses a separate simulator bearer token.
- All product database queries are fixed to the Northstar tenant.
- Lab assertions live in the simulator event store and are never inputs to
  detectors, recovery ranking or Gigi.
- Lab metadata is ignored at normalization; source event IDs are retained only
  for lineage.
- Trace payloads redact passwords, cookies, secrets and authorization values.
- Customer/product V2 pages do not import Developer Lab UI code.

To disable the observatory even if its container is accidentally started:

```bash
DEVELOPER_LAB_ENABLED=false docker compose up -d api worker beat
```

## Troubleshooting

Check all lab services:

```bash
docker compose --profile developer-lab ps
```

Inspect logs without restarting anything:

```bash
docker compose logs --tail=150 \
  developer-lab factory-simulator mqtt ot-simulator lab-edge-bridge api worker
```

If source events appear in Factory Timeline but not in a product trace, inspect
**Connectors** and **Workers & queues**. An event marked `emitted` has left the
simulated source; it is not marked ingested until a canonical ingestion receipt
exists.
