# JARVIS-APEX Installation & Setup Guide (v2.1.0)

This guide provides step-by-step instructions for installing, configuring, verifying, and running the **JARVIS-APEX** Windows Desktop AI Workstation.

---

## 1. System Requirements

### Hardware Requirements
- **OS:** Windows 10 (Build 19041+) or Windows 11 (64-bit).
- **CPU:** Modern Intel Core i5/i7/i9 or AMD Ryzen 5/7/9 (4+ cores recommended).
- **RAM:** Minimum 8 GB (16 GB recommended if running local Ollama LLMs).
- **Disk:** At least 2 GB free SSD space for dependencies, models, and SQLite storage.
- **Audio:** Microphone and speaker/headset (required for voice features).

### Software Prerequisites
- **Python:** Python 3.12 (64-bit). *Ensure "Add Python to PATH" was selected during install.*
- **Microsoft Edge WebView2 Runtime:** Pre-installed on Windows 10/11. Required for native PyWebView desktop mode.
- **Git:** Git for Windows (recommended for updates).
- **Optional - Ollama:** For 100% offline private local AI reasoning ([Download Ollama](https://ollama.ai/)).

---

## 2. Step-by-Step Installation

### Step 2.1: Open PowerShell or Command Prompt
Open Windows Terminal, PowerShell, or Command Prompt:
```powershell
cd d:\Trading
```

### Step 2.2: Set Up Python Virtual Environment (Recommended)
```powershell
# Create a virtual environment named .venv
python -m venv .venv

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1
```
*(If script execution is disabled in PowerShell, run `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`)*

### Step 2.3: Upgrade pip and Install Dependencies
```powershell
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Verify key packages are installed:
```powershell
python -c "import fastapi, uvicorn, pywebview, sounddevice, pytest; print('All core packages verified!')"
```

---

## 3. Environment Configuration (`.env`)

Create or update the `.env` file in the root directory (`d:\Trading\.env`). A template is provided below:

```ini
# =========================================================================
# JARVIS-APEX CONFIGURATION
# =========================================================================

# Server Port and Session Security
PORT=8000
SESSION_TOKEN=jarvis_secure_token_change_in_production
ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000

# Hardware Privacy Defaults
ENABLE_WAKE_WORD_DEFAULT=False

# -------------------------------------------------------------------------
# AI PROVIDER API KEYS (Configure at least one for cloud intelligence)
# -------------------------------------------------------------------------

# Google Gemini API Keys (3-Key Pool for round-robin quota rotation)
GEMINI_API_KEY=your_gemini_api_key_primary
GEMINI_API_KEY_1=your_gemini_api_key_secondary
GEMINI_API_KEY_2=your_gemini_api_key_tertiary

# Groq LPU (Ultra-fast inference)
GROQ_API_KEY=gsk_your_groq_api_key

# OpenRouter (Multi-model provider)
OPENROUTER_API_KEY=sk-or-v1-your_openrouter_api_key

# Sarvam AI (Indic / Hindi Voice and Language Models)
SARVAM_API_KEY=your_sarvam_api_key

# Local Ollama LLM (Private sovereign intelligence fallback)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

> **Security Note:** Never commit your `.env` file to any public version control repository. The `.gitignore` file is configured to exclude all `.env*` files automatically.

---

## 4. Optional Component Setup

### 4.1 Local Offline Ollama LLM Setup
If you want complete privacy or offline operation when internet connectivity is interrupted:
1. Install Ollama from [ollama.ai](https://ollama.ai/).
2. Open PowerShell and pull a lightweight model:
   ```powershell
   ollama pull llama3.2
   ```
3. Start the Ollama server (runs in the background automatically or via `ollama serve`).
4. JARVIS-APEX will automatically use Ollama as a fallback if cloud AI circuits trip.

### 4.2 Audio Device Verification
Ensure your default Windows input/output devices are active:
```powershell
python -c "import sounddevice as sd; print(sd.query_devices())"
```

---

## 5. Verification & Testing

Before launching the user interface, verify system integrity by running the automated pytest suite:

```powershell
pytest -v tests
```

Expected output:
```
======================== 29 passed in 3.73s (100%) ========================
```

---

## 6. Launching JARVIS-APEX

### Option A: Native Desktop Mode (Recommended)
Launches the integrated 1400x900 native Windows desktop window:
```powershell
python desktop_launcher.py
```
*Features:*
- Automatically starts the FastAPI backend in a managed background process.
- Waits for health diagnostics to respond before rendering the UI.
- Intercepts window close events to cleanly shut down all background tasks.
- If Edge WebView2 is unavailable, automatically opens your default web browser in app-mode.

### Option B: Web Server Mode
If you prefer running inside standard Google Chrome or Microsoft Edge:
```powershell
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
Navigate to: `http://localhost:8000`

---

## 7. Creating Desktop Shortcuts

To generate a Windows desktop shortcut for one-click access:
```powershell
cscript //nologo scripts\create_desktop_shortcut.vbs
```
This places a "JARVIS-APEX" shortcut directly on your Windows Desktop pointing to `desktop_launcher.py`.

---

## 8. Common Troubleshooting

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| **Port 8000 already in use** | A previous server instance is running. | Run `netstat -ano \| findstr :8000`, kill the PID via `taskkill /PID <PID> /F`, or change `PORT=8080` in `.env`. |
| **PyWebView window blank** | Missing Edge WebView2 runtime. | Download and install the [Evergreen WebView2 Bootstrapper](https://developer.microsoft.com/en-us/microsoft-edge/webview2/). |
| **Mic not detecting speech** | Hardware Privacy Kill Switch active. | Check the UI header toggle. Ensure "Mic" is active (green). |
| **AI requests failing** | API keys missing or quota exceeded. | Check keys in `.env` or verify the Circuit Breaker status in the **Health Center** tab. |
| **Action Confirmation prompt appears** | High-impact action triggered (kill app, empty bin). | This is an intentional security gate. Review details in the modal and click "Confirm Action". |

