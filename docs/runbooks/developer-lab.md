# GenuineGigs Developer Lab

The Developer Lab is a localhost-only test surface. It contains the Factory Lab
and Runtime Observatory and is deliberately separate from the customer product.

## Start

```bash
docker compose --profile developer-lab up --build
docker compose --profile developer-lab run --rm seed-v2-simulation -m app.db.seed_v2_cli --reset
```

Open `http://127.0.0.1:3100`. The customer product remains at
`http://127.0.0.1:3000`.

## Test a machine condition

1. In Factory Lab, publish at least three successive CNC-01-01 samples at or
   above 82°C, or start **Bearing heat ramp**.
2. Do not publish a fault or downtime label. The source contains measurements
   only.
3. In Runtime Observatory, watch the connector job apply the samples, then open
   the resulting `machine.signal.updated` correlation trace.
4. In GenuineGigs Operations, confirm the inferred machine-condition deviation,
   maintenance ownership, action, and changed line state.
5. Use the trace waterfall to distinguish source acceptance, normalization,
   detector output, outbox processing, and agent activity.

## Security boundary

The portal binds to `127.0.0.1`, authenticates its upstream calls with
`DEVELOPER_LAB_TOKEN`, and the API exposes developer endpoints only when
`DEVELOPER_LAB_ENABLED=true`. Developer replay is hard-limited to the Northstar
simulation tenant. Never enable this profile in a customer deployment.
