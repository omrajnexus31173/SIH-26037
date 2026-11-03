# Bundled models

| File | Purpose | Input | Runtime | Size |
|---|---|---|---|---:|
| `yolov8n.onnx` | COCO object detection | 640×640 letterbox | OpenCV DNN CPU (optional CUDA) | ~12.8 MB |
| `twinlitenet_da.onnx` | Drivable-area + lane segmentation | 640×360 | OpenCV DNN CPU (optional CUDA) | ~1.8 MB |

The models are already bundled so the project runs offline after setup. `scripts/download_models.py` verifies or re-downloads them with SHA-256 checks. Licenses and source URLs are in `../THIRD_PARTY_NOTICES.md`.

CPU-only execution is the default. To attempt optional CUDA acceleration, set `SIH_USE_CUDA=1` with an OpenCV build that includes the CUDA DNN backend; otherwise the loader falls back to CPU and reports that fact. To use the optional Ultralytics/PyTorch detector, install `ultralytics` separately and choose that backend in Model Settings. No GPU is required to launch the application.
