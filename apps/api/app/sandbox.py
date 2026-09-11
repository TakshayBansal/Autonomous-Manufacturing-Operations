"""Credential-free ephemeral sandbox protocol with a hardened local provider.

The local provider is intentionally an operation runner, not a shell. Production
providers can implement the same protocol with containers or remote isolation.
"""
from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import uuid4
from urllib.request import Request, urlopen

from app.core.config import get_settings
from app.db import models
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class SandboxProfile:
    name: str
    max_input_bytes: int
    max_output_bytes: int
    timeout_seconds: int
    allowed_mime_types: frozenset[str]
    network_allowed: bool = False


PROFILES = {
    "document_extraction": SandboxProfile("document_extraction", 20_000_000, 5_000_000, 120, frozenset({"application/pdf", "image/png", "image/jpeg", "text/plain"})),
    "quotation_analysis": SandboxProfile("quotation_analysis", 25_000_000, 5_000_000, 120, frozenset({"application/json", "text/csv", "text/plain"})),
    "report_rendering": SandboxProfile("report_rendering", 10_000_000, 5_000_000, 60, frozenset({"application/json", "text/plain"})),
    "integration_transformation": SandboxProfile("integration_transformation", 25_000_000, 5_000_000, 120, frozenset({"application/json", "text/csv", "application/xml", "text/xml"})),
    "admin_import_preview": SandboxProfile("admin_import_preview", 25_000_000, 5_000_000, 120, frozenset({"text/csv", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"})),
}


class SandboxProtocol(Protocol):
    def create(self, profile: str, input_manifest: dict, declared_outputs: list[str]) -> str: ...
    def upload(self, sandbox_id: str, path: str, content: bytes, mime_type: str) -> dict: ...
    def execute(self, sandbox_id: str, operation: str, arguments: dict) -> dict: ...
    def download(self, sandbox_id: str, path: str) -> bytes: ...
    def terminate(self, sandbox_id: str) -> None: ...


def _safe_relative(path: str) -> Path:
    candidate = PurePosixPath(path)
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError("Sandbox path must be a safe relative path")
    return Path(*candidate.parts)


class LocalSandboxProvider:
    def __init__(self, root: Path | None = None):
        self.settings = get_settings()
        self.root = root or self.settings.sandbox_root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def create(self, profile: str, input_manifest: dict, declared_outputs: list[str]) -> str:
        if profile not in PROFILES:
            raise ValueError("Unknown sandbox profile")
        for path in declared_outputs:
            _safe_relative(path)
        sandbox_id = str(uuid4())
        directory = self.root / sandbox_id
        directory.mkdir(mode=0o700)
        metadata = {"profile": profile, "input_manifest": input_manifest, "declared_outputs": declared_outputs,
                    "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=self.settings.sandbox_default_ttl_seconds)).isoformat()}
        (directory / ".manifest.json").write_text(json.dumps(metadata), encoding="utf-8")
        return sandbox_id

    def _metadata(self, sandbox_id: str) -> tuple[Path, dict]:
        if not sandbox_id or "/" in sandbox_id or ".." in sandbox_id:
            raise ValueError("Invalid sandbox identifier")
        directory = self.root / sandbox_id
        if not directory.is_dir():
            raise LookupError("Sandbox not found")
        metadata = json.loads((directory / ".manifest.json").read_text(encoding="utf-8"))
        if datetime.fromisoformat(metadata["expires_at"]) < datetime.now(timezone.utc):
            self.terminate(sandbox_id)
            raise TimeoutError("Sandbox expired")
        return directory, metadata

    def upload(self, sandbox_id: str, path: str, content: bytes, mime_type: str) -> dict:
        directory, metadata = self._metadata(sandbox_id)
        profile = PROFILES[metadata["profile"]]
        if mime_type not in profile.allowed_mime_types or len(content) > profile.max_input_bytes:
            raise ValueError("Input violates the sandbox profile")
        if b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in content:
            raise ValueError("Malware signature detected; artifact quarantined")
        target = directory / "input" / _safe_relative(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return {"path": path, "size": len(content), "mime_type": mime_type,
                "sha256": hashlib.sha256(content).hexdigest()}

    def execute(self, sandbox_id: str, operation: str, arguments: dict) -> dict:
        directory, metadata = self._metadata(sandbox_id)
        allowed = {
            "validate_json": self._validate_json,
            "normalize_csv": self._normalize_csv,
            "render_report": self._render_report,
        }
        if operation not in allowed:
            raise ValueError("Operation is not allowed by the sandbox profile")
        result = allowed[operation](directory, arguments)
        output_path = str(arguments.get("output_path") or "result.json")
        if output_path not in metadata["declared_outputs"]:
            raise ValueError("Operation attempted an undeclared output")
        body = json.dumps(result, sort_keys=True).encode()
        if len(body) > PROFILES[metadata["profile"]].max_output_bytes:
            raise ValueError("Sandbox output exceeds the profile limit")
        target = directory / "output" / _safe_relative(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        return {"output_path": output_path, "size": len(body), "sha256": hashlib.sha256(body).hexdigest()}

    def _validate_json(self, directory: Path, arguments: dict) -> dict:
        source = directory / "input" / _safe_relative(str(arguments["input_path"]))
        return {"valid": True, "data": json.loads(source.read_text(encoding="utf-8"))}

    def _normalize_csv(self, directory: Path, arguments: dict) -> dict:
        import csv
        source = directory / "input" / _safe_relative(str(arguments["input_path"]))
        with source.open(newline="", encoding="utf-8-sig") as handle:
            records = [{str(key).strip(): str(value).strip() for key, value in row.items()} for row in csv.DictReader(handle)]
        return {"rows": records, "row_count": len(records)}

    def _render_report(self, _directory: Path, arguments: dict) -> dict:
        return {"title": str(arguments.get("title") or "Operational report"), "sections": list(arguments.get("sections") or [])}

    def download(self, sandbox_id: str, path: str) -> bytes:
        directory, metadata = self._metadata(sandbox_id)
        if path not in metadata["declared_outputs"]:
            raise PermissionError("Output was not declared")
        target = directory / "output" / _safe_relative(path)
        content = target.read_bytes()
        guessed = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if guessed not in {"application/json", "text/plain", "text/csv"}:
            raise ValueError("Output MIME type is not allowed")
        return content[:self.settings.sandbox_max_output_bytes]

    def terminate(self, sandbox_id: str) -> None:
        directory = self.root / sandbox_id
        if directory.parent != self.root or not directory.exists():
            return
        shutil.rmtree(directory)

    def cleanup_expired(self) -> int:
        cleaned = 0
        for directory in self.root.iterdir():
            if not directory.is_dir():
                continue
            try:
                metadata = json.loads((directory / ".manifest.json").read_text(encoding="utf-8"))
                if datetime.fromisoformat(metadata["expires_at"]) < datetime.now(timezone.utc):
                    self.terminate(directory.name)
                    cleaned += 1
            except (OSError, ValueError, KeyError):
                continue
        return cleaned


class HardenedSandboxProvider:
    """HTTP client for the separately hardened production sandbox runner."""
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or get_settings().sandbox_service_url).rstrip("/")

    def _call(self, method: str, path: str, payload: dict | None = None) -> dict:
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(self.base_url + path, data=body, method=method,
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=10) as response:  # noqa: S310 - configured internal runner
            return json.loads(response.read())

    def create(self, profile: str, input_manifest: dict, declared_outputs: list[str]) -> str:
        if profile not in PROFILES:
            raise ValueError("Unknown sandbox profile")
        return str(self._call("POST", "/sandboxes", {"profile": profile, "input_manifest": input_manifest,
            "declared_outputs": declared_outputs})["id"])

    def upload(self, sandbox_id: str, path: str, content: bytes, mime_type: str) -> dict:
        import base64
        _safe_relative(path)
        return self._call("POST", f"/sandboxes/{sandbox_id}/artifacts", {"path": path,
            "mime_type": mime_type, "content_base64": base64.b64encode(content).decode()})

    def execute(self, sandbox_id: str, operation: str, arguments: dict) -> dict:
        return self._call("POST", f"/sandboxes/{sandbox_id}/execute", {"operation": operation, "arguments": arguments})

    def download(self, sandbox_id: str, path: str) -> bytes:
        import base64
        _safe_relative(path)
        result = self._call("POST", f"/sandboxes/{sandbox_id}/download", {"path": path})
        return base64.b64decode(result["content_base64"], validate=True)

    def terminate(self, sandbox_id: str) -> None:
        self._call("DELETE", f"/sandboxes/{sandbox_id}")


class DeepAgentsSandboxAdapter:
    """Narrow adapter for specialists that expect a sandbox-style backend."""
    def __init__(self, provider: SandboxProtocol):
        self.provider = provider

    def run_operation(self, profile: str, operation: str, inputs: dict[str, tuple[bytes, str]],
                      arguments: dict, output_path: str) -> bytes:
        sandbox_id = self.provider.create(profile, {"inputs": list(inputs)}, [output_path])
        try:
            for path, (content, mime_type) in inputs.items():
                self.provider.upload(sandbox_id, path, content, mime_type)
            self.provider.execute(sandbox_id, operation, {**arguments, "output_path": output_path})
            return self.provider.download(sandbox_id, output_path)
        finally:
            self.provider.terminate(sandbox_id)


class ManagedSandbox:
    """Persists lifecycle metadata while keeping artifacts inside the provider."""
    def __init__(self, db: Session, tenant_id: str, plant_id: str | None,
                 correlation_id: str, provider: SandboxProtocol | None = None):
        self.db, self.tenant_id, self.plant_id = db, tenant_id, plant_id
        self.correlation_id = correlation_id
        self.provider = provider or (HardenedSandboxProvider() if get_settings().sandbox_provider == "hardened" else LocalSandboxProvider())

    def create(self, profile: str, input_manifest: dict, declared_outputs: list[str], specialist_run_id: str | None = None) -> tuple[models.SandboxRun, str]:
        provider_id = self.provider.create(profile, input_manifest, declared_outputs)
        row = models.SandboxRun(tenant_id=self.tenant_id, plant_id=self.plant_id,
            provider=get_settings().sandbox_provider, profile=profile, specialist_run_id=specialist_run_id,
            correlation_id=self.correlation_id, input_manifest={**input_manifest, "provider_id": provider_id},
            declared_outputs=declared_outputs,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=get_settings().sandbox_default_ttl_seconds))
        self.db.add(row)
        self.db.flush()
        return row, provider_id

    def terminate(self, row: models.SandboxRun, provider_id: str) -> None:
        self.provider.terminate(provider_id)
        row.state = "terminated"
        row.terminated_at = datetime.now(timezone.utc)
