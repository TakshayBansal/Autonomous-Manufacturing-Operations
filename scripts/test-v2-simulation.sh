#!/usr/bin/env bash
set -euo pipefail

python3 -m compileall -q apps/api/app services/factory-simulator
(cd services/factory-simulator && python3 -m unittest -v test_app.py)
(cd apps/api && .venv/bin/python -m pytest \
  tests/test_factory_simulation_pipeline.py \
  tests/test_connector_conformance.py \
  tests/test_operational_v2.py \
  tests/test_operational_v2_api.py -q)
npm --workspace apps/web run lint
npm run build:web
docker compose --profile simulation config -q

if [[ "${RUN_BROWSER_E2E:-0}" == "1" ]]; then
  PLAYWRIGHT_OUTPUT_DIR="${PLAYWRIGHT_OUTPUT_DIR:-/tmp/genuinegigs-northstar-e2e}" \
    npm run test:e2e -- --project=desktop apps/web/e2e/northstar-live-simulation.spec.ts
fi

echo "Northstar simulation acceptance checks passed."
