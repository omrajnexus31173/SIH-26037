# Offline Python wheels

A full verified Linux wheel set was generated with `python3 -m pip download -r requirements.txt -r requirements-dev.txt -r requirements-webrtc.txt` on 2026-11-03. It resolved successfully but measured **184 MB**, dominated by OpenCV, SciPy, NumPy and `av`. Bundling those wheels would push the final deployment archive beyond the practical 128 MB workspace delivery cap.

The exact resolved versions are preserved in `deploy/requirements.lock.txt`. Regenerate a local offline wheel directory before an air-gapped backend install:

```bash
python3 scripts/download_wheels.py --platform linux
python3 -m venv .venv-deploy
.venv-deploy/bin/pip install --no-index --find-links vendor/wheels/linux -r requirements.txt -r requirements-dev.txt -r requirements-webrtc.txt
```

On Windows:

```bat
.venv\Scripts\python.exe scripts\download_wheels.py --platform windows
.venv\Scripts\python.exe -m pip install --no-index --find-links vendor\wheels\windows -r requirements.txt -r requirements-dev.txt -r requirements-webrtc.txt
```

The download script uses the project requirements and prints the resulting wheel directory. It is intentionally not run during ZIP creation so the delivered archive stays portable.
