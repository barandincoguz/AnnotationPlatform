import json
import os
import subprocess
import sys
import textwrap

from backend.shared.security_headers import CONTENT_SECURITY_POLICY


def test_real_spa_mount_applies_deploy_safe_headers(tmp_path):
    static_dir = tmp_path / "static"
    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True)
    (static_dir / "index.html").write_text(
        '<div id="root"></div><script src="/assets/app-abc123.js"></script>',
        encoding="utf-8",
    )
    (static_dir / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")
    (assets_dir / "app-abc123.js").write_text(
        "const value = '" + "x" * 2000 + "';",
        encoding="utf-8",
    )

    script = textwrap.dedent(
        f"""
        import json
        import os

        os.environ.pop("DISABLE_SPA_MOUNT", None)
        os.environ["ENVIRONMENT"] = "test"

        from fastapi.testclient import TestClient
        from pathlib import Path
        from backend import config

        config.STATIC_DIR = Path({str(static_dir)!r})
        from backend.main import app

        client = TestClient(app)
        login = client.get("/login")
        favicon = client.get("/favicon.svg")
        asset = client.get(
            "/assets/app-abc123.js",
            headers={{"Accept-Encoding": "gzip"}},
        )
        print(json.dumps({{
            "login_status": login.status_code,
            "login_cache": login.headers.get("cache-control"),
            "login_csp": login.headers.get("content-security-policy"),
            "login_frame": login.headers.get("x-frame-options"),
            "favicon_cache": favicon.headers.get("cache-control"),
            "asset_cache": asset.headers.get("cache-control"),
            "asset_encoding": asset.headers.get("content-encoding"),
            "asset_nosniff": asset.headers.get("x-content-type-options"),
        }}))
        """
    )
    env = os.environ.copy()
    env.pop("DISABLE_SPA_MOUNT", None)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    result = json.loads(completed.stdout.strip())

    assert result == {
        "login_status": 200,
        "login_cache": "no-cache",
        "login_csp": CONTENT_SECURITY_POLICY,
        "login_frame": "DENY",
        "favicon_cache": "no-cache",
        "asset_cache": "public, max-age=31536000, immutable",
        "asset_encoding": "gzip",
        "asset_nosniff": "nosniff",
    }
