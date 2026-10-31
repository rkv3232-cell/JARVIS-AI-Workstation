# JARVIS-APEX — Omni Windows AI Workstation (v2.1.0)

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-green.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Security Hardened](https://img.shields.io/badge/Security-Strict%20Auth%20%2B%20KillSwitch-red.svg)](#security-and-safety)
[![Tests Passing](https://img.shields.io/badge/Tests-29%2F29%20Passed%20(100%25)-brightgreen.svg)](#test-suite)

> **J.A.R.V.I.S.-APEX** is a mission-critical, enterprise-grade Windows Desktop AI Workstation combining sovereign AI intelligence, financial strategy research & paper trading, deep multi-source research, voice synthesis with real-time audio interruption, visual workflow automation, and hardened operating system desktop controllers.

---

## 🌟 Key Features

### 1. 🛡️ Security, Authentication & Safe OS Control
- **Session Authentication & CSRF Protection:** Strict `X-JARVIS-Session` header checks and configurable CORS origins.
- **Two-Step Confirmation Registry:** High-impact desktop actions (process kill, file deletion, recycle bin emptying) are halted into a `PENDING_CONFIRMATION` state requiring explicit modal user approval.
- **Hardware Privacy Kill Switches:** One-click instant hardware mute for microphone and screen capture feeds. Wake-word engine is disabled by default for zero unintended listening.
- **Immutable Structured Audit Trail:** Every sensitive operation, authorization decision, and OS command is recorded in `data/audit_log.json`.
- **Zero-Secret Logging:** Automatic regex masking for Google Gemini, Groq, OpenRouter, Sarvam, and generic Bearer tokens.
- **Strict Safe Process Spawning:** Absolute elimination of `shell=True`. All desktop processes launch with validated arguments via `subprocess.Popen(..., shell=False)` or Windows native `os.startfile`.

### 2. ⚡ AI Brain, Model Router & Circuit Breakers
- **Multi-Provider Intelligent Routing:** Dynamically routes requests across a 3-Key Gemini Pool, Groq LPUs, OpenRouter, Sarvam AI (Hindi/Indic voice and NLP), and private local Ollama LLMs.
- **Automatic Circuit Breakers:** Protects workstation responsiveness. Trips for 60 seconds after 3 consecutive provider failures, automatically failing over to the next healthy provider or local Ollama.
- **Dynamic Model Telemetry:** Real-time latency tracking, success/failure metrics, and circuit breaker trip counters.
- **Active Gemini 3.8 Intelligence Probe:** Automatically tests API key access for Gemini 3.8 models, falling back gracefully to Gemini 2.5 Flash / Flash-Lite.

### 3. 📈 Trading Strategy Lab & Simulated Paper Trading
> *DISCLAIMER: Educational and simulation purposes only. Real-money orders and automated brokerage executions are strictly prohibited.*
- **Market Data Validator:** Validates OHLC integrity, strictly ascending timestamps, duplicate bars, and flag stale quotes (>300s).
- **Strategy Lab Backtester:** Tests algorithmic strategies (SMA/EMA Crossovers, RSI Mean Reversion, MACD Momentum, Bollinger Breakouts, and SMC Fair Value Gap & Order Blocks). Computes Win Rate %, Profit Factor, Max Drawdown %, Sharpe Ratio, Equity Curves, and 70/30 Walk-Forward In-Sample/Out-of-Sample analysis.
- **Paper Trading Portfolio:** Pre-funded virtual portfolio (₹10,00,000 balance). Executes simulated Market, Limit, and Stop-Loss orders with realistic slippage (0.05%) and commission models (₹20 flat).
- **Trading Psychology Journal:** Logs emotional states (Disciplined, FOMO, Revenge Trade, Greedy, Anxious), enforces pre-trade checklists, calculates an objective 0–100 Discipline Score, and generates mental risk advisories.

### 4. 🔬 Deep Research & Persistent Memory Brain
- **Resumable Research Workspace:** Structured multi-source research engine with SQLite job persistence (`PENDING -> GATHERING -> ANALYZING -> REPORTING -> COMPLETED`).
- **Persistent Memory Brain:** Classified knowledge storage across 7 distinct categories (`TRADING_RULE`, `SYSTEM_PREFERENCE`, `RESEARCH_TOPIC`, `USER_PROFILE`, `WORKFLOW_AUTOMATION`, `FINANCIAL_GOAL`, `GENERAL`).
- **Full-Text Search (FTS5):** Instant keyword search across all memories, notes, and research summaries.
- **Cloud Sync Worker:** Bounded background synchronization worker with SQLite `PRAGMA user_version` migrations and JSON import/export.

### 5. 🎙️ Advanced Voice Engine & Real-Time Interruption
- **Explicit Voice State Machine:** `IDLE -> LISTENING -> CAPTURING -> TRANSCRIBING -> THINKING -> SPEAKING -> INTERRUPTED -> ERROR`.
- **Instant Audio Interruption:** One-click Stop / Barge-In halts TTS playback instantly, purges audio buffers, and resets the engine to `IDLE`.
- **Device Enumeration:** Automatically enumerates host microphones and audio output devices via `sounddevice`.

### 6. ⚙️ Visual Workflow Automation Studio
- **Declarative Workflows:** `TRIGGER -> CONDITION -> ACTION -> APPROVAL -> RESULT` execution pipeline.
- **Allowlisted Actions Only:** Enforces strict execution safety. Unknown actions are rejected.
- **Dry-Run Engine:** Simulates workflow executions, validating conditions and producing mock outputs without running side effects.
- **Pre-Built Starter Templates:**
  1. *Morning Market Briefing* (Scheduled 08:45 AM briefing)
  2. *High Volatility Alert* (Alert on market moves > 2%)
  3. *System Health Sentinel* (Hourly CPU/RAM checks)
  4. *Market Close Portfolio Summary* (Daily 03:35 PM report)

### 7. 🪟 Windows Desktop Application & Secure Auto-Updater
- **Native Desktop Shell:** `desktop_launcher.py` provides a clean 1400x900 native Windows window using `pywebview`, with browser app-mode fallback.
- **Single-Click Installer/Shortcut:** `scripts/create_desktop_shortcut.vbs` and `scripts/create_shortcut.py` generate official Windows desktop icons.
- **Standalone Binary Packaging:** `scripts/build_windows_app.py` bundles the full application into a standalone executable using PyInstaller.
- **Cryptographic Auto-Updater:** Checks remote version manifests, validates SHA256 checksums, creates pre-update ZIP rollback snapshots, and deploys updates atomically.

---

## 🚀 Quick Start Guide

### Prerequisites
- Windows 10 or Windows 11 (64-bit)
- Python 3.12 installed and added to `PATH`
- Edge WebView2 Runtime (installed by default on Windows 10/11)

### Installation
1. Clone or open the repository:
   ```powershell
   cd d:\Trading
   ```
2. Install Python dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
3. Set up environment variables in `.env`:
   ```ini
   PORT=8000
   SESSION_TOKEN=jarvis_secure_token_change_in_production
   GEMINI_API_KEY=your_gemini_key_1
   GEMINI_API_KEY_1=your_gemini_key_2
   GEMINI_API_KEY_2=your_gemini_key_3
   GROQ_API_KEY=your_groq_key
   OPENROUTER_API_KEY=your_openrouter_key
   SARVAM_API_KEY=your_sarvam_key
   OLLAMA_BASE_URL=http://localhost:11434
   ```

### Running the Application

#### Option A: Native Desktop Mode (Recommended)
```powershell
python desktop_launcher.py
```
*Launches the native 1400x900 desktop window, boots the FastAPI backend automatically, and handles clean graceful shutdown.*

#### Option B: Standalone Web Server
```powershell
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```
Open your browser to: `http://localhost:8000`

---

## 🧪 Test Suite

Run the full automated pytest suite covering all 8 architectural modules:
```powershell
pytest -v tests
```

### Verified Test Results
```
tests/test_ai_router.py::test_circuit_breaker_trips_and_recovers PASSED
tests/test_ai_router.py::test_model_catalog_and_telemetry PASSED
tests/test_ai_router.py::test_gemini_38_probe_status_structure PASSED
tests/test_auto_updater.py::test_version_parsing_and_comparison PASSED
tests/test_auto_updater.py::test_file_sha256_verification PASSED
tests/test_auto_updater.py::test_backup_snapshot_creation PASSED
tests/test_memory_brain.py::test_persistent_memory_crud_and_fts PASSED
tests/test_memory_brain.py::test_memory_export_and_import PASSED
tests/test_memory_brain.py::test_research_jobs_persistence PASSED
tests/test_security.py::test_secret_redaction PASSED
tests/test_security.py::test_action_registry_confirmation_lifecycle PASSED
tests/test_security.py::test_path_traversal_sanitizer PASSED
tests/test_security.py::test_upload_validator PASSED
tests/test_security.py::test_privacy_kill_switches PASSED
tests/test_security.py::test_structured_audit_logger PASSED
tests/test_trading_lab.py::test_data_validator PASSED
tests/test_trading_lab.py::test_technical_indicators PASSED
tests/test_trading_lab.py::test_smc_structures PASSED
tests/test_trading_lab.py::test_backtest_execution PASSED
tests/test_trading_lab.py::test_paper_portfolio_lifecycle PASSED
tests/test_trading_lab.py::test_trading_psychology_engine PASSED
tests/test_voice_state.py::test_voice_state_transitions PASSED
tests/test_voice_state.py::test_audio_interruption_protocol PASSED
tests/test_voice_state.py::test_audio_devices_enumeration PASSED
tests/test_websocket.py::test_websocket_manager_connect_and_broadcast PASSED
tests/test_websocket.py::test_bounded_queue_slow_client_overflow PASSED
tests/test_workflows.py::test_workflow_listing_and_templates PASSED
tests/test_workflows.py::test_workflow_allowlist_validation PASSED
tests/test_workflows.py::test_workflow_dry_run_execution PASSED

======================== 29 passed in 3.73s (100%) ========================
```

---

## 📁 Repository Architecture

```
JARVIS-AI-Workstation/
├── backend/
│   ├── main.py                     # Primary FastAPI application & REST/WS router
│   ├── config.py                   # Pydantic Settings, paths, and environment defaults
│   ├── security.py                 # Action registry, privacy kill switches, audit logger
│   ├── websocket_manager.py        # Bounded client queues, heartbeats, topic broadcasts
│   ├── task_coordinator.py        # Non-overlapping background task coordinator
│   ├── health_center.py           # Real-time CPU/RAM/Disk, AI latency, SQLite diagnostics
│   ├── model_router.py            # AI circuit breakers, multi-key pools, telemetry
│   ├── os_controller.py           # Windows desktop automation (shell=False)
│   ├── auto_updater.py            # SHA256 checksums, staging isolation, rollback backups
│   ├── trading/
│   │   ├── data_validator.py       # OHLC and timestamp consistency verification
│   │   ├── strategy_lab.py         # Strategy backtesting, SMC structures, walk-forward
│   │   ├── paper_portfolio.py      # Virtual ₹10L simulated account & order book
│   │   └── trading_psychology.py   # Emotional journaling, discipline score & risk advice
│   ├── memory/
│   │   └── memory_brain.py         # Persistent 7-category SQLite FTS5 memory & research
│   └── workflows/
│       └── workflow_engine.py      # Declarative triggers, conditions, allowlisted actions
├── frontend/
│   ├── index.html                  # 10-Tab Workstation GUI, privacy controls, modal gates
│   ├── style.css                   # OLED dark theme, responsive grids, HUD components
│   └── app.js                      # JarvisClient, WebSocket handlers, view controllers
├── scripts/
│   ├── build_windows_app.py        # PyInstaller packaging automation
│   ├── create_desktop_shortcut.vbs # VBScript desktop shortcut creator
│   └── create_shortcut.py          # Python desktop shortcut helper
├── tests/                          # 29 unit and integration tests across 8 domains
├── data/                           # SQLite databases, audit log, research jobs
├── desktop_launcher.py             # PyWebView native Windows desktop launcher
├── ARCHITECTURE.md                 # Detailed architectural diagrams & design specifications
├── SECURITY.md                     # Comprehensive threat model & security policies
├── INSTALLATION.md                 # Step-by-step setup and environment configuration
├── WINDOWS_BUILD.md                # Standalone Windows EXE packaging instructions
├── AUTO_UPDATE.md                  # Cryptographic update protocol & manifest schema
├── TEST_REPORT.md                  # Full verification report with line-by-line coverage
└── CHANGELOG.md                    # Release history and upgrade breakdown
```

---

## 📜 Documentation Directory

- [ARCHITECTURE.md](ARCHITECTURE.md) — Comprehensive architectural diagrams, concurrency models, and state machines.
- [SECURITY.md](SECURITY.md) — Threat model, security boundaries, authentication, and privacy controls.
- [INSTALLATION.md](INSTALLATION.md) — Environment prerequisites, Python 3.12 installation, and optional tools.
- [WINDOWS_BUILD.md](WINDOWS_BUILD.md) — Building the PyInstaller `.exe` and generating desktop shortcuts.
- [AUTO_UPDATE.md](AUTO_UPDATE.md) — Secure auto-updater protocol, manifest structure, and rollback mechanics.
- [TEST_REPORT.md](TEST_REPORT.md) — Complete 29-test test suite report and domain verification breakdown.
- [CHANGELOG.md](CHANGELOG.md) — Version 2.1.0 release notes and feature breakdown.

---

## ⚖️ Safety & Compliance Notice
This software is developed strictly for personal automation, quantitative research, and educational simulation. Real-money automated order execution is intentionally disabled. High-impact operating system commands require explicit manual confirmation.

