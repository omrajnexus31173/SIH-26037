"""Verify or download the two bundled ONNX models with SHA-256 checks."""
from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
SPECS = {
    "yolov8n.onnx": {
        "url": "https://huggingface.co/Kalray/yolov8/resolve/main/yolov8n.onnx",
        "sha256": "65158dad735be799c2466fa15e260c09558080bd530b42a8d0c3d1b419afd8b5",
        "license": "Ultralytics YOLOv8 AGPL-3.0",
    },
    "twinlitenet_da.onnx": {
        "url": "https://raw.githubusercontent.com/harrylal/TwinLiteNet-onnx-opencv-dnn/main/models/best.onnx",
        "sha256": "f505b56bd7c9e4e38b2928373aa4daa191a9a398e07e1fb340024b9ce84d4285",
        "license": "MIT (TwinLiteNet / ONNX wrapper)",
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, destination: Path) -> None:
    print(f"Downloading {destination.name} from {url}")
    tmp = destination.with_suffix(destination.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as response, tmp.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    tmp.replace(destination)


def main(force: bool = False) -> int:
    MODELS.mkdir(parents=True, exist_ok=True)
    for name, spec in SPECS.items():
        path = MODELS / name
        if path.exists() and not force:
            actual = sha256(path)
            if actual == spec["sha256"]:
                print(f"OK      {name}: bundled SHA-256 verified ({actual[:12]}...)")
                continue
            print(f"REPLACE {name}: bundled checksum mismatch; re-downloading")
        try:
            download(spec["url"], path)
            actual = sha256(path)
            if actual != spec["sha256"]:
                print(f"ERROR   {name}: checksum mismatch after download: {actual}")
                return 2
            print(f"OK      {name}: downloaded and verified ({actual[:12]}...) [{spec['license']}]")
        except Exception as exc:
            print(f"ERROR   {name}: {exc}")
            print("The project can still run if a valid ONNX file is already present. See models/README.md.")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--force" in sys.argv))
