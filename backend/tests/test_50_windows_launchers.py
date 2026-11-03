"""Regression tests for Windows cmd.exe launcher syntax."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "scripts" / "check_windows_bat.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_workspace_windows_launchers_pass_static_syntax_check() -> None:
    result = _run("--static")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "STATIC_CHECK_OK" in result.stdout


def test_static_checker_detects_unescaped_echo_parenthesis(tmp_path: Path) -> None:
    bad = tmp_path / "bad_launcher.bat"
    bad.write_text(
        "@echo off\n"
        "if 1==1 (\n"
        "  echo [ERROR] Install Node.js 18 or newer (LTS recommended).\n"
        "  goto :fail\n"
        ")\n"
        "exit /b 0\n"
        ":fail\n"
        "exit /b 1\n",
        encoding="utf-8",
    )
    result = _run("--file", str(bad))
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "unescaped" in combined
    assert "bad_launcher.bat:3" in combined
