import hashlib
import json
from pathlib import Path

from app.main import app


generated = Path(__file__).parents[3] / 'packages' / 'shared' / 'src' / 'api.generated.ts'
content = generated.read_text(encoding='utf-8')
digest = hashlib.sha256(
    json.dumps(app.openapi(), sort_keys=True, separators=(',', ':')).encode()
).hexdigest()
marker = f' * openapi-sha256: {digest}\n'
if 'openapi-sha256:' in content:
    import re
    content = re.sub(r' \* openapi-sha256: [0-9a-f]{64}\n', marker, content, count=1)
else:
    content = content.replace(' * Do not make direct changes to the file.\n', ' * Do not make direct changes to the file.\n' + marker, 1)
generated.write_text(content, encoding='utf-8')
print(f'Stamped OpenAPI contract {digest[:12]}')
