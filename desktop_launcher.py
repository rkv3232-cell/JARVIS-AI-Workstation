"""
J.A.R.V.I.S. APEX — Windows Native Desktop Launcher
===================================================
Manages complete workstation lifecycle:
1. Starts the FastAPI backend daemon on 127.0.0.1:8000
2. Awaits port and health check readiness
3. Opens a native hardware-accelerated Windows window using PyWebView (1400x900)
4. Gracefully terminates backend process tree upon window closure.
"""

import os
import sys
import time
import shutil
import subprocess
import webbrowser
from typing import Optional
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = 8000
SERVER_URL = f"http://{HOST}:{PORT}"

def is_backend_ready() -> bool:
    import urllib.request
    try:
        req = urllib.request.Request(f"{SERVER_URL}/api/status", headers={"User-Agent": "JARVIS-Launcher"})
        with urllib.request.urlopen(req, timeout=1.0) as res:
            return res.status == 200
    except Exception:
        return False

def start_backend_process() -> subprocess.Popen:
    print("[Launcher] Starting J.A.R.V.I.S. APEX Backend Service...")
    cmd = [
        sys.executable,
        "-m", "uvicorn",
        "backend.main:app",
        "--host", HOST,
        "--port", str(PORT),
        "--log-level", "info"
    ]
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    
    # Launch backend without separate console window
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        env=env,
        creationflags=creationflags
    )
    return proc

def launch_pywebview(backend_proc: Optional[subprocess.Popen]):
    try:
        import webview
    except ImportError:
        print("[Launcher] PyWebView not found. Falling back to browser app mode.")
        launch_browser_fallback(backend_proc)
        return

    print("[Launcher] Creating native desktop window (1400x900)...")

    def on_closed():
        print("[Launcher] Desktop window closed by user.")
        if backend_proc is not None:
            print("[Launcher] Terminating managed backend process...")
            try:
                backend_proc.terminate()
                backend_proc.wait(timeout=3)
            except Exception:
                try:
                    backend_proc.kill()
                except Exception:
                    pass
        else:
            print("[Launcher] Pre-existing backend server preserved.")
        sys.exit(0)

    window = webview.create_window(
        title="J.A.R.V.I.S. APEX Workstation",
        url=SERVER_URL,
        width=1400,
        height=900,
        min_size=(1024, 700),
        text_select=True,
        zoomable=True
    )
    window.events.closed += on_closed
    webview.start(debug=False)

def launch_browser_fallback(backend_proc: Optional[subprocess.Popen]):
    # Try Chrome or Edge with --app mode for borderless PWA experience
    chrome_path = shutil.which("chrome") or r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    edge_path = shutil.which("msedge") or r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

    opened = False
    for browser in [chrome_path, edge_path]:
        if os.path.exists(browser):
            try:
                subprocess.Popen([browser, f"--app={SERVER_URL}"])
                opened = True
                break
            except Exception:
                pass

    if not opened:
        webbrowser.open(SERVER_URL)

    print(f"\n[Launcher] J.A.R.V.I.S. APEX is live at {SERVER_URL}")
    print("[Launcher] Press Ctrl+C in this console to terminate workstation.")
    try:
        if backend_proc is not None:
            backend_proc.wait()
        else:
            print("[Launcher] Pre-existing backend server detected. App is active.")
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Launcher] Shutting down...")
        if backend_proc is not None:
            backend_proc.terminate()

def main():
    print("=" * 65)
    print("       J.A.R.V.I.S. APEX — OMNI WORKSTATION DESKTOP")
    print("=" * 65)

    backend_proc = None
    if not is_backend_ready():
        backend_proc = start_backend_process()
        print("[Launcher] Waiting for backend readiness", end="", flush=True)
        ready = False
        for _ in range(30):
            time.sleep(0.5)
            print(".", end="", flush=True)
            if is_backend_ready():
                ready = True
                break
        print()
        if not ready:
            print("[Launcher Error] Backend failed to start within 15 seconds.")
            if backend_proc:
                backend_proc.terminate()
            sys.exit(1)
        print("[Launcher] Backend initialized and healthy.")
    else:
        print("[Launcher] Backend is already running.")

    launch_pywebview(backend_proc)

if __name__ == "__main__":
    main()

