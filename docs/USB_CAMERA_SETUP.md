# USB Camera Setup for Android / Windows

## Critical fact

**Ordinary Android USB file transfer (MTP/PTP) does not expose a camera stream.** Seeing the phone in Windows Explorer or Device Manager as a portable device is not evidence of a UVC camera. The dashboard never labels MTP as connected.

Use one of the following real video paths.

---

## Option A — Recommended: USB tether + ADB reverse + IP Webcam

Requirements:

- Android Platform Tools (`adb`) on Windows
- USB debugging enabled on the phone
- An IP Webcam / camera-streaming app on the phone
- USB cable (used as a network tunnel, not MTP)

Steps:

```bat
adb devices
adb reverse tcp:8080 tcp:8080
```

Start the phone camera server on port `8080`. In the dashboard:

1. Open **Camera Connection → Camera source controls**.
2. Select **Phone Camera via USB**.
3. Choose **ADB IP webcam**.
4. Enter `http://127.0.0.1:8080/video` (or the exact URL from the app).
5. Click **Connect / verify source**.
6. Confirm real frames in **Live Perception** and `frames_received > 0` in camera status.

Verification is frame-based: a listed device or a started app alone is not a connection.

To clean up:

```bat
adb reverse --remove-all
```

---

## Option B — Direct UVC / external USB webcam

This works only if the phone exposes a USB webcam/UVC gadget, or if you connect an actual USB webcam/UVC capture device.

1. Open Windows Device Manager and look under **Cameras** or **Imaging devices**.
2. Open **Camera Connection → USB camera discovery** and click **Re-run probe**.
3. Review OpenCV indices and Windows PnP devices.
4. Select **Phone Camera via USB** or **Laptop Webcam**, choose the detected index and click **Connect / verify source**.
5. Verify that annotated frames and real detections appear.

The PnP list is diagnostic. It is not a claim that a stream is connected.

---

## Option C — USB-tethered QR/WebRTC

If the phone can reach the laptop frontend through an `adb reverse` tunnel, the QR/WebRTC pairing page can be opened over that tunnel. This still uses the secure-context rules: HTTPS and a trusted certificate (or localhost on the same device) are required for `getUserMedia`.

```bat
adb reverse tcp:5173 tcp:5173
adb reverse tcp:8000 tcp:8000
```

Open the HTTPS frontend URL produced by the dashboard and follow `docs/CAMERA_SETUP.md`.

---

## Windows diagnostics

- `/api/camera/devices` calls OpenCV `VideoCapture` for indices `0..4` and PowerShell PnP enumeration on Windows.
- On non-Windows platforms, PnP enumeration reports `platform: non-windows`; OpenCV probing still runs.
- V4L2 warnings in a Linux sandbox are expected when no physical devices exist.
- If Windows blocks PowerShell enumeration, the dashboard shows the actual error from `windows_error` and does not invent a device list.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Phone appears only as `Portable Device`/MTP | Use ADB reverse + IP Webcam, UVC-capable mode, or Wi-Fi QR; MTP is not video |
| `adb devices` shows `unauthorized` | Accept the RSA prompt on the phone |
| `adb reverse` connection refused | Start the phone camera server; confirm its port |
| OpenCV index opens but no frames | Try another index; close other apps using the camera; check Windows privacy settings |
| PnP list empty but webcam works | Use the OpenCV index directly; some drivers do not expose friendly PnP names |
| Frame freezes | Disconnect/reconnect source; check CPU load and lower AI/Camera FPS in System Controls |
