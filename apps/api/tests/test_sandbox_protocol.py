import json

import pytest

from app.sandbox import LocalSandboxProvider


def test_sandbox_accepts_only_declared_outputs_and_fixed_operations(tmp_path) -> None:
    provider = LocalSandboxProvider(tmp_path)
    sandbox_id = provider.create("quotation_analysis", {}, ["normalized.json"])
    provider.upload(sandbox_id, "quotes.csv", b"supplier,price\nA,10\n", "text/csv")
    receipt = provider.execute(sandbox_id, "normalize_csv", {"input_path": "quotes.csv", "output_path": "normalized.json"})
    assert receipt["size"] > 0
    assert json.loads(provider.download(sandbox_id, "normalized.json"))["row_count"] == 1
    with pytest.raises(ValueError, match="not allowed"):
        provider.execute(sandbox_id, "shell", {"command": "env", "output_path": "normalized.json"})
    with pytest.raises(ValueError, match="undeclared"):
        provider.execute(sandbox_id, "normalize_csv", {"input_path": "quotes.csv", "output_path": "secret.json"})


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd", "nested/../../secret"])
def test_sandbox_blocks_path_traversal(tmp_path, path: str) -> None:
    provider = LocalSandboxProvider(tmp_path)
    sandbox_id = provider.create("quotation_analysis", {}, ["result.json"])
    with pytest.raises(ValueError, match="safe relative"):
        provider.upload(sandbox_id, path, b"data", "text/plain")


def test_sandbox_blocks_oversize_mime_and_malware(tmp_path) -> None:
    provider = LocalSandboxProvider(tmp_path)
    sandbox_id = provider.create("report_rendering", {}, ["result.json"])
    with pytest.raises(ValueError, match="profile"):
        provider.upload(sandbox_id, "image.png", b"image", "image/png")
    with pytest.raises(ValueError, match="Malware"):
        provider.upload(sandbox_id, "input.txt", b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE", "text/plain")


def test_terminated_sandbox_is_unavailable(tmp_path) -> None:
    provider = LocalSandboxProvider(tmp_path)
    sandbox_id = provider.create("document_extraction", {}, ["result.json"])
    provider.terminate(sandbox_id)
    with pytest.raises(LookupError):
        provider.download(sandbox_id, "result.json")
