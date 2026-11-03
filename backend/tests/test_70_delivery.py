"""Final delivery documentation and production preview configuration tests."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_environment_variable_documentation_exists() -> None:
    env = (ROOT / "ENVIRONMENT_VARIABLES.md").read_text(encoding="utf-8")
    frontend_env = (ROOT / "frontend" / ".env.example").read_text(encoding="utf-8")
    backend_env = (ROOT / "backend" / ".env.example").read_text(encoding="utf-8")
    root_env = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "VITE_BACKEND_URL" in env and "VITE_BACKEND_URL" in frontend_env
    assert "VITE_FRONTEND_ORIGIN" in env and "VITE_FRONTEND_ORIGIN" in frontend_env
    assert "SIH_BACKEND_PORT" in env and "PORT" in env
    assert "SIH_BACKEND_PORT" in backend_env and "SIH_HOST" in backend_env
    assert "SIH_PUBLIC_PAIR_BASE_URL" in root_env
    assert "no database" in env.lower()


def test_final_audit_and_deployment_readmes_exist() -> None:
    audit = (ROOT / "docs" / "FINAL_AUDIT.md").read_text(encoding="utf-8")
    netlify_readme = (ROOT / "netlify" / "site" / "NETLIFY_DEPLOY_README.md").read_text(encoding="utf-8")
    backend_readme = (ROOT / "deploy" / "backend" / "BACKEND_DEPLOY_README.md").read_text(encoding="utf-8")
    template = (ROOT / "deploy" / "netlify" / "runtime-config.template.js").read_text(encoding="utf-8")

    assert "Implemented and verified" in audit or "**1** implemented and verified" in audit
    assert "Requires physical hardware or external credentials" in audit or "**5** requires physical hardware" in audit
    assert "drag" in netlify_readme.lower() and "runtime-config.js" in netlify_readme
    assert "uvicorn backend.main:app" in backend_readme and "/api/health" in backend_readme
    assert "REPLACE_WITH_BACKEND_ORIGIN" in template and "configured: false" in template


def test_production_preview_proxy_is_configured() -> None:
    config = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    preview_start = config.index("preview:")
    preview_block = config[preview_start:preview_start + 900]
    assert "proxy:" in preview_block
    assert "'/api'" in preview_block and "'/ws'" in preview_block
    assert "ws: true" in preview_block
