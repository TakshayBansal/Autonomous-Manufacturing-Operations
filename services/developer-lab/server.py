"""Local reverse proxy and static host for Factory Lab / Runtime Observatory."""
import hashlib, json, mimetypes, os, pathlib, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SIMULATOR=os.getenv("FACTORY_SIMULATOR_URL","http://factory-simulator:8090")
API=os.getenv("GENUINEGIGS_API_URL","http://api:8000")
SIM_TOKEN=os.getenv("FACTORY_SIMULATOR_TOKEN","northstar-local-simulator-token")
DEV_TOKEN=os.getenv("DEVELOPER_LAB_TOKEN","northstar-developer-local")
BIND_HOST=os.getenv("DEVELOPER_LAB_BIND_HOST","127.0.0.1")

class Handler(BaseHTTPRequestHandler):
    def send_json(self,status,data):
        body=json.dumps(data).encode(); self.send_response(status); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def proxy(self,method):
        size=int(self.headers.get("Content-Length","0")); body=self.rfile.read(size) if size else None
        path=self.path
        if path.startswith("/api/developer-lab/"):
            suffix=path.removeprefix("/api/developer-lab")
            simulator_roots=("/runs","/scenarios","/sources","/summary","/email")
            if suffix.startswith(simulator_roots): path="/lab/v2"+suffix
            else: path="/internal/devtools"+suffix
        if path.startswith(("/lab/v1/","/lab/v2/")):
            url=SIMULATOR+path; headers={"Authorization":f"Bearer {SIM_TOKEN}","Content-Type":"application/json"}
        elif path.startswith("/internal/devtools/"):
            url=API+path; headers={"X-Developer-Token":DEV_TOKEN,"Content-Type":"application/json"}
        else: return self.send_json(404,{"detail":"Not found"})
        try:
            if method in ("POST", "PUT", "PATCH", "DELETE"):
                digest=hashlib.sha256((path.encode()+b":"+(body or b""))).hexdigest()
                headers["Idempotency-Key"]=f"developer-lab:{digest}"
            request=urllib.request.Request(url,data=body,method=method,headers=headers)
            with urllib.request.urlopen(request,timeout=10) as response:
                content_type=response.headers.get("Content-Type","application/json")
                if content_type.startswith("text/event-stream"):
                    self.send_response(response.status); self.send_header("Content-Type",content_type)
                    self.send_header("Cache-Control","no-cache"); self.send_header("X-Accel-Buffering","no")
                    self.end_headers()
                    while chunk := response.readline():
                        self.wfile.write(chunk); self.wfile.flush()
                    return
                payload=response.read(); self.send_response(response.status); self.send_header("Content-Type",content_type); self.send_header("Content-Length",str(len(payload))); self.end_headers(); self.wfile.write(payload)
        except urllib.error.HTTPError as exc: self.send_json(exc.code,{"detail":exc.read().decode()})
        except Exception as exc: self.send_json(502,{"detail":type(exc).__name__})
    def do_GET(self):
        path=self.path.split("?",1)[0]
        if path in ("/","/index.html","/app.js","/styles.css","/extras.css"):
            filename="index.html" if path in ("/","/index.html") else path[1:]
            resolved=pathlib.Path(filename)
            body=resolved.read_bytes(); self.send_response(200); self.send_header("Content-Type",mimetypes.guess_type(filename)[0] or "application/octet-stream"); self.send_header("Content-Length",str(len(body))); self.end_headers(); return self.wfile.write(body)
        if self.path=="/health": return self.send_json(200,{"status":"ok"})
        self.proxy("GET")
    def do_POST(self): self.proxy("POST")
    def do_PUT(self): self.proxy("PUT")
    def do_PATCH(self): self.proxy("PATCH")
    def log_message(self,*_): pass

ThreadingHTTPServer((BIND_HOST,3100),Handler).serve_forever()
