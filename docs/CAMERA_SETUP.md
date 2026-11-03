# Camera Setup

## Source options

| Source | When to use | Backend path |
|---|---|---|
| Phone Camera via QR / Wi-Fi | Preferred wireless Android camera | WebRTC preferred; authenticated MJPEG/WebSocket fallback |
| Phone Camera via USB | UVC camera or ADB reverse + IP Webcam | OpenCV device index or stream URL |
| IP Webcam | Phone app or network camera already exposes HTTP/MJPEG/RTSP | OpenCV `VideoCapture(url)` |
| Laptop Webcam | Built-in/USB webcam connected to Windows laptop | OpenCV device index, DirectShow on Windows |
| Video Upload / Demo Clip | No hardware available; software verification | Uploaded file or `assets/demo_drive.avi` |
| Synthetic Test Pattern | Automated pipeline wiring test only | Generated frame, explicitly NOT a real camera |

A source is reported connected only after real decoded frames reach `CameraHub` and the telemetry status updates. Selecting a source is not a fake connection state.

---

## Android QR / Wi-Fi pairing

1. On Windows, complete `setup_windows.bat`.
2. Set `SIH_USE_HTTPS=1` in `.env` (camera access over a LAN IP is a secure-context requirement).
3. Run `start_project.bat` and trust `certs\sih-26037.crt` on the phone (see `docs/HTTPS_GUIDE.md`).
4. Connect the phone and laptop to the same Wi-Fi/LAN.
5. Open the dashboard using the laptop's LAN IP, e.g. `https://192.168.1.10:5173`, not `localhost`.
6. Open **Camera Connection**.
7. Inspect **Recommended reachable pair URL**. It must contain the LAN IP and an active token. If it contains `localhost`, do not scan it on the phone; choose the LAN-IP candidate or set `SIH_PUBLIC_PAIR_BASE_URL`.
8. Click **Regenerate QR** to create a fresh single-peer token when needed.
9. Scan the QR with the Android phone. The `/pair?token=...` page opens.
10. Grant camera permission. Rear/environment camera is the default; use the Front/Rear selector before starting.
11. Press **Start camera streaming**. The page validates the link, checks secure context, creates a WebRTC offer, waits for complete ICE gathering, then posts it with the token.
12. If WebRTC/ICE fails, the page automatically switches to authenticated MJPEG-over-WebSocket frames. The dashboard shows the actual transport, FPS, resolution, RTT and frames received.

### Invalid-link troubleshooting

- `Token missing / expired / regenerated`: regenerate QR on the dashboard and rescan.
- `Insecure context` or camera permission blocked: use HTTPS on a LAN IP and trust the certificate; plain `http://192.168.x.x` is blocked by Android browsers.
- `localhost` QR on a phone: invalid for a separate device; it points at the phone itself.
- Control WebSocket fails: check that backend and frontend are both running, and that the phone can reach the frontend origin.
- WebRTC fails: MJPEG fallback starts automatically; this is still a real authenticated camera stream.

---

## IP Webcam

1. Start an IP Webcam-style app on the phone or connect a network camera.
2. In **Camera Connection → Camera source controls**, select **IP Webcam**.
3. Enter e.g. `http://PHONE_IP:8080/video` or an RTSP URL supported by the local OpenCV build.
4. Click **Connect / verify source**. The backend validates the URL before opening it.
5. Verify from **Live Perception**: frames, YOLO boxes, FPS and resolution must update.

---

## Laptop webcam

1. Select **Laptop Webcam**.
2. Set the OpenCV/DirectShow device index (normally `0`; try `1` or `2` if camera 0 is unavailable).
3. Click **Connect / verify source**.
4. Use `/api/camera/devices` (the USB diagnostics panel) to see probed indices and Windows PnP camera names.

---

## Video upload / bundled demo

1. Select **Video Upload / Demo Clip**.
2. Either leave `assets/demo_drive.avi` or choose a `.mp4`, `.avi`, `.mov`, `.mkv`, `.m4v` or `.webm` file.
3. Click **Upload & run** for a chosen file, or **Connect / verify source** for the workspace path.
4. Uploaded files are saved under `uploads/` with a sanitized filename and size limit. They are excluded from the delivered ZIP.

The demo clip is generated from `assets/sample_road.jpg` with synthetic pan/zoom. It validates the real pipeline but is not real driving footage.

---

## Synthetic fallback

Select **Synthetic Test Pattern** only for software verification. The backend annotates it with `SYNTHETIC TEST FRAME - NOT A REAL CAMERA`, and the dashboard shows an explicit warning. It never counts as a hardware camera connection or a real detection benchmark.

## Netlify-hosted pairing

When the dashboard is on Netlify, set `VITE_FRONTEND_ORIGIN`/runtime `frontendOrigin` to the public Netlify HTTPS origin and `VITE_BACKEND_URL`/runtime `backendUrl` to the external backend HTTPS origin. QR candidate URLs are generated from `frontendOrigin()`, while phone WebSockets and WebRTC signalling go to the backend origin. The Netlify site is already a secure context for `getUserMedia`; the backend must also be HTTPS/WSS. No physical phone or public deployment was exercised in this workspace.
