"""Deployment artifact regression tests for the Netlify + external backend ZIP."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_deployment_files_exist() -> None:
    required = [
        "README.md",
        "DEPLOYMENT.md",
        "docs/NETLIFY_DEPLOYMENT.md",
        "netlify.toml",
        "netlify/site/index.html",
        "netlify/site/runtime-config.js",
        "netlify/site/_redirects",
        "netlify/site/_headers",
        "Dockerfile",
        "docker-compose.yml",
        "render.yaml",
        "Procfile",
        "fly.toml",
        "deploy/backend/README.md",
        "deploy/backend/start.sh",
        "deploy/requirements.lock.txt",
        "deploy/netlify/.env.example",
        "deploy/netlify/README.md",
        "scripts/download_wheels.py",
        "scripts/make_deploy_zip.py",
        "vendor/wheels/README.md",
        "frontend/public/runtime-config.js",
        "frontend/scripts/build-netlify.mjs",
    ]
    missing = [rel for rel in required if not (ROOT / rel).is_file()]
    assert not missing, f"Missing deployment artifacts: {missing}"


def test_netlify_static_site_has_runtime_config_and_spa_redirect() -> None:
    index = (ROOT / "netlify/site/index.html").read_text(encoding="utf-8")
    runtime = (ROOT / "netlify/site/runtime-config.js").read_text(encoding="utf-8")
    redirects = (ROOT / "netlify/site/_redirects").read_text(encoding="utf-8")
    headers = (ROOT / "netlify/site/_headers").read_text(encoding="utf-8")
    toml = (ROOT / "netlify.toml").read_text(encoding="utf-8")
    package = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))

    assert "runtime-config.js" in index
    assert "REPLACE_WITH_BACKEND_ORIGIN" in runtime
    assert "REPLACE_WITH_NETLIFY_ORIGIN" in runtime
    assert "/*    /index.html   200" in redirects
    assert "Cache-Control: no-store" in headers
    assert "publish = \"netlify/site\"" in toml
    assert "build:netlify" in package.get("scripts", {})


def test_backend_port_fallback_for_platform_deployments(monkeypatch) -> None:
    monkeypatch.delenv("SIH_BACKEND_PORT", raising=False)
    monkeypatch.setenv("PORT", "9123")
    from backend.config import Settings

    assert Settings().port == 9123


def test_resolved_backend_lockfile_is_usable() -> None:
    lock = (ROOT / "deploy/requirements.lock.txt").read_text(encoding="utf-8")
    for package in ("fastapi==", "uvicorn==", "opencv-python==", "numpy==", "scipy==", "aiortc=="):
        assert package in lock
