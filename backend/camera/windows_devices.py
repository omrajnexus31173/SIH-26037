"""Windows PnP camera diagnostics (names only).

This module reports device names for troubleshooting. It does NOT claim that a
device is connected to the AI pipeline: `CameraHub` only reports a working
connection after OpenCV actually returns frames.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict, List


def _run_powershell(command: str, timeout: float = 6.0) -> Any:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, timeout=timeout, check=False)
    if completed.returncode != 0 or not completed.stdout.strip():
        raise RuntimeError(completed.stderr.strip() or "PowerShell returned no data")
    text = completed.stdout.strip()
    # Remove occasional BOM / informational prefixes.
    start = min([i for i in (text.find("["), text.find("{")) if i >= 0] or [0])
    return json.loads(text[start:])


def enumerate_windows_camera_devices() -> Dict[str, Any]:
    if os.name != "nt":
        return {"platform": "non-windows", "devices": [],
                "note": "Windows PnP enumeration is skipped on this platform; OpenCV indices are still probed."}
    commands = [
        "Get-PnpDevice -Class Camera,Image | Select-Object FriendlyName,Status,InstanceId | ConvertTo-Json -Compress",
        ("Get-CimInstance Win32_PnPEntity | Where-Object { $_.PNPClass -in @('Camera','Image') } | "
         "Select-Object Name,Status,PNPDeviceID | ConvertTo-Json -Compress"),
    ]
    last_error = ""
    for command in commands:
        try:
            raw = _run_powershell(command)
            rows = raw if isinstance(raw, list) else [raw]
            devices: List[Dict[str, str]] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                devices.append({
                    "name": str(row.get("FriendlyName") or row.get("Name") or "Unknown camera"),
                    "status": str(row.get("Status") or "Unknown"),
                    "instance_id": str(row.get("InstanceId") or row.get("PNPDeviceID") or ""),
                })
            return {"platform": "windows", "devices": devices,
                    "note": "PnP names are diagnostics; OpenCV index selection still requires a real frame."}
        except Exception as exc:
            last_error = str(exc)
    return {"platform": "windows", "devices": [],
            "error": last_error or "Windows camera enumeration unavailable",
            "note": "Install/update Windows camera drivers and use OpenCV device indices."}
