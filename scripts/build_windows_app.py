"""
J.A.R.V.I.S. APEX — Windows Binary Packager (PyInstaller)
=========================================================
Builds a standalone executable for J.A.R.V.I.S. APEX Workstation.
Configures data files, static directories, and required hidden imports.
"""

import sys
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

def build_executable():
    print("=" * 60)
    print("Building J.A.R.V.I.S. APEX Standalone Windows Executable")
    print("=" * 60)

    try:
        import PyInstaller
    except ImportError:
        print("[Build Notice] PyInstaller is not currently installed. To bundle into an EXE, run:")
        print("  pip install pyinstaller")
        print("  python scripts/build_windows_app.py [--onedir | --onefile]")
        sys.exit(1)

    # Detect package mode flag (--onefile vs --onedir)
    mode_flag = "--onefile" if "--onefile" in sys.argv else "--onedir"
    print(f"[Packaging Mode] Building with: {mode_flag}")

    pyinstaller_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=JARVIS_APEX",
        "--noconsole",
        mode_flag,
        f"--add-data={BASE_DIR / 'frontend'};frontend",
        f"--add-data={BASE_DIR / 'data'};data",
        "--hidden-import=uvicorn.logging",
        "--hidden-import=uvicorn.loops",
        "--hidden-import=uvicorn.loops.auto",
        "--hidden-import=uvicorn.protocols",
        "--hidden-import=uvicorn.protocols.http",
        "--hidden-import=uvicorn.protocols.http.auto",
        "--hidden-import=uvicorn.protocols.websockets",
        "--hidden-import=uvicorn.protocols.websockets.auto",
        "--hidden-import=webview",
        "--hidden-import=engineio.async_drivers.asgi",
        "--hidden-import=sounddevice",
        "--hidden-import=edge_tts",
        str(BASE_DIR / "desktop_launcher.py")
    ]

    print(f"Running PyInstaller command: {' '.join(pyinstaller_cmd)}")
    res = subprocess.run(pyinstaller_cmd, cwd=str(BASE_DIR))
    if res.returncode == 0:
        print(f"\nBuild successful! Output generated in dist/JARVIS_APEX/ ({mode_flag})")
    else:
        print(f"\nBuild failed with exit code {res.returncode}")
    sys.exit(res.returncode)

if __name__ == "__main__":
    build_executable()

