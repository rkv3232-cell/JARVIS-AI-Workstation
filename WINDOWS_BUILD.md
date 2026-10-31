# JARVIS-APEX Windows Packaging & Binary Build Guide (v2.1.0)

This document provides instructions for compiling and packaging **JARVIS-APEX** into a standalone Windows executable or distributable desktop directory using **PyInstaller**.

---

## 1. Overview of Packaging Architecture

JARVIS-APEX can be packaged in two distinct formats:
1. **Directory Distribution (`--onedir`, Recommended):** High performance, rapid startup time, and clean modular isolation of frontend assets and native binary DLLs.
2. **Single Binary Executable (`--onefile`):** Compact single file distribution that unpacks temporary runtime assets into `%TEMP%` on launch.

The build automation is orchestrated by `scripts/build_windows_app.py`, which ensures all frontend assets (`index.html`, `style.css`, `app.js`), SQLite data templates, and required dynamic link libraries are correctly bundled.

---

## 2. Build Prerequisites

Ensure the following tools are installed in your Python environment:

```powershell
pip install pyinstaller pywebview uvicorn fastapi sounddevice psutil
```

Verify PyInstaller is operational:
```powershell
pyinstaller --version
```

---

## 3. Automated Packaging Execution

Run the provided build automation script:

```powershell
python scripts/build_windows_app.py
```

### What the Build Script Does:
1. **Asset Bundling:** Automatically maps `frontend/` to the destination runtime directory.
2. **Hidden Imports:** Explicitly collects dynamic modules required by FastAPI, Uvicorn, and sounddevice (`uvicorn.logging`, `uvicorn.loops.auto`, `engineio.async_drivers.asgi`).
3. **Clean Build:** Purges stale files in `build/` and `dist/` before compiling.
4. **Output Generation:** Emits the compiled desktop application inside `dist/JARVIS-APEX/`.

---

## 4. Manual PyInstaller Command (Alternative)

If you prefer building manually from PowerShell without the wrapper script, use the following command:

```powershell
pyinstaller `
    --name="JARVIS-APEX" `
    --noconsole `
    --onedir `
    --clean `
    --add-data "frontend;frontend" `
    --add-data "backend;backend" `
    --hidden-import="uvicorn.logging" `
    --hidden-import="uvicorn.loops" `
    --hidden-import="uvicorn.loops.auto" `
    --hidden-import="uvicorn.protocols" `
    --hidden-import="uvicorn.protocols.http" `
    --hidden-import="uvicorn.protocols.http.auto" `
    --hidden-import="uvicorn.protocols.websockets" `
    --hidden-import="uvicorn.protocols.websockets.auto" `
    --hidden-import="uvicorn.lifespan" `
    --hidden-import="uvicorn.lifespan.on" `
    --hidden-import="sounddevice" `
    --hidden-import="psutil" `
    desktop_launcher.py
```

---

## 5. Build Artifact Structure

Upon successful completion, the output will reside in:

```
d:\Trading\dist\JARVIS-APEX\
├── JARVIS-APEX.exe         # Primary executable
├── frontend\               # Bundled UI assets
│   ├── index.html
│   ├── style.css
│   └── app.js
├── python312.dll           # Embedded Python runtime
├── WebView2Loader.dll      # Microsoft Edge WebView2 loader
└── _internal\              # Bundled libraries & Python packages
```

---

## 6. Creating Desktop & Start Menu Shortcuts

To create an instant desktop shortcut to the installed executable or Python launcher:

### Method A: VBScript Shortcut Generator
```powershell
cscript //nologo scripts\create_desktop_shortcut.vbs
```

### Method B: Python Shortcut Generator
```powershell
python scripts\create_shortcut.py
```

Both methods query your Windows User Profile (`%USERPROFILE%\Desktop`), generate a shell link (`JARVIS-APEX.lnk`), set the working directory to `d:\Trading`, and assign the application icon.

---

## 7. Windows Defender & SmartScreen Notice

When compiling custom Python binaries with PyInstaller:
- Windows Defender SmartScreen may display an *"Unknown Publisher"* warning on unsigned binaries.
- To prevent false-positive file locks or heuristic scanning delays:
  1. Open **Windows Security** -> **Virus & threat protection**.
  2. Under **Virus & threat protection settings**, click **Manage settings**.
  3. Under **Exclusions**, add your build directory: `d:\Trading\dist`.

For production deployment across multiple machines, sign the binary with a standard Windows Code Signing Certificate via Microsoft `signtool.exe`:
```powershell
signtool sign /f MyCert.pfx /p "password" /tr http://timestamp.digicert.com /td sha256 /fd sha256 dist\JARVIS-APEX\JARVIS-APEX.exe
```
