#!/usr/bin/env python3
"""Download an offline wheel set for the SIH-26037 backend."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ("requirements.txt", "requirements-dev.txt", "requirements-webrtc.txt")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=("linux", "windows", "native"), default="native")
    parser.add_argument("--python-version", default="")
    parser.add_argument("--dest", default="")
    args = parser.parse_args()
    platform = args.platform
    dest = Path(args.dest) if args.dest else ROOT / "vendor" / "wheels" / platform
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "pip", "download", "--dest", str(dest)]
    for req in REQUIREMENTS:
        cmd += ["-r", str(ROOT / req)]
    if platform == "windows":
        pyver = args.python_version or "3.13"
        abi = f"cp{pyver.replace('.', '')}"
        cmd += [
            "--only-binary=:all:", "--platform", "win_amd64",
            "--python-version", pyver, "--implementation", "cp", "--abi", abi,
        ]
    print("DOWNLOAD_WHEELS", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode == 0:
        print(f"WHEELS_READY {dest}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
