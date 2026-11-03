# HTTPS and Secure Context Guide

## Why HTTPS is required

Android browsers expose `getUserMedia` (camera) and WebRTC only in a secure context:

- `https://...` with a certificate trusted by the phone, or
- `http://localhost` / `http://127.0.0.1` on the **same machine** (localhost exception).

A plain `http://192.168.1.10:5173` QR link opening on a phone is not a secure context. The browser will block camera access even though the dashboard loads. The mobile `/pair` page explicitly diagnoses this condition.

---

## Generate a certificate on the Windows laptop

`setup_windows.bat` already runs:

```bat
.venv\Scripts\python.exe scripts\generate_cert.py
```

The generator includes:

- `DNS:localhost`
- the Windows hostname
- detected LAN IPv4 addresses
- `IP:127.0.0.1`

If the Wi-Fi/LAN IP changes, regenerate the certificate so its SAN includes the new address:

```bat
.venv\Scripts\python.exe scripts\generate_cert.py
```

The private key `certs\sih-26037.key` is intentionally excluded from the delivered ZIP. Generate it locally.

---

## Enable HTTPS

Edit `.env`:

```ini
SIH_USE_HTTPS=1
```

Optionally set an explicit public/reachable origin:

```ini
SIH_PUBLIC_PAIR_BASE_URL=https://192.168.1.10:5173
```

Start:

```bat
start_project.bat
```

The launcher passes SSL arguments to uvicorn and enables HTTPS in Vite when the certificate/key exist. Open:

```text
https://localhost:5173
```

on the laptop and:

```text
https://<LAN_IP>:5173
```

on the phone.

---

## Trust `certs/sih-26037.crt` on Android

1. Copy `certs\sih-26037.crt` to the phone.
2. Android Settings → Security / Encryption & credentials → Install from storage / Install a certificate → CA certificate (wording varies by version).
3. Select the `.crt` file and name it e.g. `SIH-26037 local`.
4. Reopen the QR link. Some browsers require a restart after installing a CA.
5. If the browser still warns, confirm the certificate SAN contains the exact LAN IP in the URL.

Trusting a self-signed certificate is required because no public CA is involved. Do not install unknown certificates from untrusted sources.

---

## QR URL diagnostics

In **Camera Connection**, inspect candidates:

- **Dashboard origin** — recommended when the dashboard itself is reachable from the phone.
- **Local network** — detected LAN IP.
- **Configured public URL** — from `SIH_PUBLIC_PAIR_BASE_URL`.
- **Current request host** — useful behind a proxy/preview.
- **This laptop only** — localhost; explicitly not for a separate phone.

The QR endpoint rejects URLs that do not include a valid token or absolute `http(s)` origin. The `/pair` page validates the token before requesting camera permission.

---

## Common failures

| Message | Fix |
|---|---|
| `Insecure context` | Use HTTPS on LAN; trust certificate |
| `net::ERR_CERT_AUTHORITY_INVALID` | Install/trust the generated `.crt` on the phone |
| `ERR_CERT_COMMON_NAME_INVALID` | Regenerate cert after LAN IP change; open the exact SAN hostname/IP |
| `localhost` QR from phone | Invalid for a separate device; choose LAN-IP candidate |
| WebRTC ICE fails | MJPEG/WebSocket fallback starts automatically |
| Control WebSocket fails | Check firewall, both service ports, and that frontend origin is reachable |

## Scope note

This sandbox generated a certificate with its own sandbox LAN IP (`169.254.0.21`) and verified the SAN. Physical Android trust, browser certificate UI and valid SDP/ICE media flow were not exercised here.

## Netlify deployments

Netlify provides trusted HTTPS for the static dashboard and `/pair` page, which satisfies the phone browser's secure-context requirement for that origin. It does not secure the backend. Put the external FastAPI/WebSocket backend behind managed TLS or a reverse proxy and set `VITE_BACKEND_URL=https://...`; plain `http://` and `ws://` will be blocked as mixed content from a Netlify HTTPS page. Regenerate any local self-signed certificate for the backend's real hostname; never include the private key in deployment artifacts.
