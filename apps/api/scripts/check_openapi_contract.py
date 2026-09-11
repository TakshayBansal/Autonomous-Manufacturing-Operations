import hashlib
import json
import re
from pathlib import Path

from app.main import app


generated = Path(__file__).parents[3] / "packages" / "shared" / "src" / "api.generated.ts"
content = generated.read_text(encoding="utf-8")
match = re.search(r"openapi-sha256: ([0-9a-f]{64})", content)
actual = hashlib.sha256(
    json.dumps(app.openapi(), sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
if match is None or match.group(1) != actual:
    raise SystemExit(
        "Generated API contract is stale. Start the API and run `npm run generate:api`, then update its OpenAPI hash."
    )
print(f"OpenAPI contract is current ({actual[:12]})")
