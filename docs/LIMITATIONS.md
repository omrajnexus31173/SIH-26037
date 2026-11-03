# Limitations and Honest Scope

## Hardware not available in this workspace

This project was built and validated in a Linux sandbox without:

- a physical Android phone,
- a phone WebRTC media session with valid SDP/ICE,
- a USB/UVC camera,
- a laptop webcam,
- Full Windows 10 `cmd.exe` setup/start/stop execution (the static launcher checker was run by the user on Windows 10),
- an NVIDIA/CUDA GPU,
- browser certificate-trust interaction on Android.

Software integration was verified with TestClient phone frames, a generated synthetic source, a generated sample-derived video, QR/token APIs, WebSocket control messages, WebRTC invalid-offer handling and the aiortc receiver import/status. None of those are claims that physical hardware worked.

## Camera measurement basis

- YOLOv8n ONNX detections and TwinLiteNet ONNX segmentation outputs are real model inferences.
- Without calibration, distances, TTC and obstacle coordinates from a monocular camera are **image-plane/perspective proxies**, not physical metres.
- With calibration, flat-ground inverse-perspective values are still estimates requiring a flat road, correct intrinsics, measured camera height/pitch and objects touching the ground plane. They are labelled `estimate_only_not_ground_truth`.
- Optical scale-rate TTC and metric simulation TTC are distinct and reported with their basis.

## Simulation scope

- Simulation actors are deterministic ground truth, not detections from a camera.
- Completion/collision/avoidance statistics are measured engine events in metric coordinates.
- Zero collisions in a headless run is not a real-road safety guarantee or production validation.
- The 3D ego follows backend pure-pursuit and A* state; it is not an independent browser physics model.

## WebRTC and USB scope

- The backend contains a real aiortc receiver and the phone page creates a complete ICE-gathered offer. A valid end-to-end phone media flow was not executed without a device.
- Authenticated MJPEG/WebSocket fallback is implemented and tested with real encoded frames over WebSocket.
- Ordinary Android MTP/PTP file transfer is not a camera stream. UVC or ADB reverse + IP Webcam/Wi-Fi pairing is required.
- A device appearing in a PnP/OpenCV diagnostic list is not a connection until real frames are processed.

## Performance

- CPU-only operation is mandatory-compatible; no dedicated GPU is required.
- TwinLiteNet is intentionally cached every third processed frame on CPU and the result is explicitly labelled `cached`.
- FPS/latency vary by laptop CPU, camera resolution and browser. The dashboard reports measured values; it does not hard-code benchmarks.
- Optional CUDA/Ultralytics backends are used only when installed and runtime-detected; failures fall back to the bundled ONNX CPU path.

## Windows scripts

`setup_windows.bat`, `start_project.bat` and `stop_project.bat` are written for Windows 10 `cmd.exe`. Full Windows execution was not performed in this Linux sandbox. Their syntax is regression-checked by `scripts/check_windows_bat.py --static`, and stubbed copies were run through Wine `cmd.exe` with `--wine`; all three reached their completion markers without parse errors. The user additionally ran `--static` on Windows 10 `10.0.19045.7417` and reported `STATIC_CHECK_OK 3 files`. Wine is a parser check, not a substitute for running the scripts on Windows 10; full setup/start/stop execution remains unverified. Their individual commands were also validated here using Python/npm/uvicorn/Vite equivalents.

## Models and assets

- Bundled YOLOv8n ONNX and TwinLiteNet ONNX hashes are verified; licenses/attribution are in `THIRD_PARTY_NOTICES.md`.
- `assets/sample_road.jpg` is the Ultralytics `bus.jpg` sample.
- `assets/demo_drive.avi` is generated from that image with synthetic pan/zoom; it is not real driving footage.
- 3D assets are procedural; no third-party vehicle meshes are required.

## Security

- Self-signed HTTPS requires manual trust. Do not expose the dashboard/camera endpoints to an untrusted network.
- Pairing tokens expire and are single-peer, but the prototype is not a hardened internet-facing service.
- The private key is excluded from the ZIP and must be generated locally.

## Netlify and external hosting

- Netlify static hosting cannot run the FastAPI/OpenCV process, ONNX inference, MJPEG stream, telemetry WebSocket, phone WebSocket or WebRTC receiver. An always-on container/VPS/Render/Railway/Fly backend is mandatory.
- Netlify redirects do not replace WebSocket connectivity; the frontend uses an absolute external HTTPS/WSS backend origin from `runtime-config.js`.
- No Netlify account, DNS record, external backend host, public HTTPS/WSS connection or browser certificate-trust UI was available in this workspace. The static build, runtime configuration, redirects, backend recipes and ZIP integrity were verified here, but an actual Netlify deployment remains a user-side action.
- The full resolved Linux wheel set measured 184 MB and is not bundled in the ZIP. `deploy/requirements.lock.txt` and `scripts/download_wheels.py` reproduce it locally for an air-gapped install.

## Browser verification limitation

No browser automation, DOM inspection or developer-console capture was available in this workspace. TypeScript typecheck, both production builds, production-preview HTTP/WebSocket checks and asset loading were executed; visual rendering and console output remain user-side browser verification.
