"""Verify `python -m backend.cli openapi-dump` produces a valid OpenAPI
JSON document with the contract surfaces the frontend depends on."""
import json
import subprocess
import sys


def test_openapi_dump_writes_valid_json(tmp_path):
    output = tmp_path / "openapi.json"
    result = subprocess.run(
        [sys.executable, "-m", "backend.cli", "openapi-dump", "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    assert output.exists()

    spec = json.loads(output.read_text())
    assert spec.get("openapi", "").startswith("3."), "Not an OpenAPI 3.x spec"
    assert "paths" in spec
    assert "/api/auth/login" in spec["paths"]
    assert "/api/auth/me" in spec["paths"]
    assert "/api/auth/logout" in spec["paths"]
    assert "/api/auth/register" in spec["paths"]
