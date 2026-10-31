# CHANGELOG — JARVIS-APEX

All notable changes to the **JARVIS-APEX** Windows Desktop AI Workstation will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.1.0] - 2026-10-31

### 🛡️ Security, Authentication & Safe OS Execution
- **Added:** Two-step `ActionConfirmationRegistry` in `backend/security.py` requiring explicit user approval for destructive/high-impact operations (process kills, file deletes, recycle bin emptying).
- **Added:** Structured immutable audit trail in `data/audit_log.json` logging all commands, authorizations, and file operations with ISO UTC timestamps.
- **Added:** Secret redaction engine automatically masking Google Gemini, Groq, OpenRouter, Sarvam, and generic Bearer tokens across logs, stdout, and telemetry.
- **Added:** Hardware Privacy Kill Switches for instant hardware microphone mute and screen vision feed blanking.
- **Added:** Wake-word listener disabled by default (`ENABLE_WAKE_WORD_DEFAULT=False`) to prevent background listening without explicit intent.
- **Added:** `RequestCorrelationMiddleware` injecting unique `X-Request-ID` across all REST requests and WebSocket connections.
- **Added:** Session token authentication middleware (`X-JARVIS-Session`) and strict configurable CORS origin validation.
- **Security Fix:** Completely eliminated `shell=True` from `backend/os_controller.py`. Replaced with `subprocess.Popen(..., shell=False)` with validated arguments and native `os.startfile`.
- **Security Fix:** Added path traversal sanitization and upload validation (25MB limit and allowed MIME extensions).

### ⚡ AI Brain, Model Router & Circuit Breakers
- **Added:** Per-provider `CircuitBreaker` pattern in `backend/model_router.py`. Automatically trips for 60 seconds after 3 consecutive failures, preventing system freezes.
- **Added:** Integrated support for 5 distinct AI providers:
  1. Google Gemini (with 3-Key round-robin rotation pool)
  2. Groq LPU (Llama 3.3 70B Versatile)
  3. OpenRouter (Claude 3.5 Sonnet, DeepSeek R1)
  4. Sarvam AI (Indic / Hindi speech and language)
  5. Local Ollama (Private offline sovereign fallback)
- **Added:** Active Gemini 3.8 Intelligence Probe dynamically verifying model capability across configured keys.
- **Added:** Model telemetry tracking latency, success rates, and trip statistics via `GET /api/system/model-telemetry`.

### 📈 Trading Strategy Lab & Simulated Paper Trading
- **Added:** `MarketDataValidator` enforcing OHLC price validity, strictly ascending timestamps, duplicate bar rejection, and stale quote detection (>300s).
- **Added:** `StrategyLabBacktester` in `backend/trading/strategy_lab.py`:
  - Algorithmic strategies: SMA/EMA Crossovers, RSI Mean Reversion, MACD Momentum, Bollinger Breakouts.
  - Smart Money Concepts (SMC): Fair Value Gaps (FVG) and Order Blocks (OB).
  - Metrics: Win Rate %, Profit Factor, Max Drawdown %, Sharpe Ratio, and Equity Curves.
  - Realistic friction: 0.05% slippage and ₹20 flat brokerage.
  - Overfitting protection: 70% In-Sample / 30% Out-of-Sample Walk-Forward validation.
- **Added:** `PaperTradingPortfolio` with ₹10,00,000 virtual balance, simulated Market/Limit/SL execution, and P&L tracking in SQLite.
- **Added:** `TradingPsychologyEngine` with emotional tagging (Disciplined, FOMO, Revenge Trade, Greedy, Anxious), 4-point checklist enforcement, objective 0–100 Discipline Score, and mental risk advisories.
- **Policy Enforcement:** Real-money live brokerage orders are strictly prohibited. Simulated and educational only.

### 🔬 Deep Research & Persistent Memory Brain
- **Added:** `PersistentMemoryBrain` in `backend/memory/memory_brain.py` with 7 classified categories (`TRADING_RULE`, `SYSTEM_PREFERENCE`, `RESEARCH_TOPIC`, `USER_PROFILE`, `WORKFLOW_AUTOMATION`, `FINANCIAL_GOAL`, `GENERAL`).
- **Added:** SQLite Full-Text Search (FTS5) for instant phrase and keyword retrieval across all persistent records.
- **Added:** Automatic SQLite schema migrations using `PRAGMA user_version`.
- **Added:** Resumable SQLite research job persistence (`PENDING -> GATHERING -> ANALYZING -> REPORTING -> COMPLETED`).
- **Added:** JSON export and restore endpoints for persistent memory backups.

### 🎙️ Advanced Voice Engine & Barge-In Interruption
- **Added:** Explicit Voice State Machine in `backend/voice_service.py` (`IDLE -> LISTENING -> CAPTURING -> TRANSCRIBING -> THINKING -> SPEAKING -> INTERRUPTED -> ERROR`).
- **Added:** Real-time barge-in audio interruption protocol (`POST /api/voice/interrupt`) that immediately halts TTS audio playback, flushes sound buffers, and resets to `IDLE` in under 50ms.
- **Added:** Dynamic audio device enumeration via `sounddevice` returning input microphones and output speakers.

### ⚙️ Visual Workflow Automation Studio
- **Added:** Declarative `WorkflowEngine` in `backend/workflows/workflow_engine.py` supporting `TRIGGER -> CONDITION -> ACTION -> APPROVAL -> RESULT` execution pipelines.
- **Added:** Execution safety enforcement: only allowlisted actions are permitted.
- **Added:** Dry-run execution mode testing conditions and generating trace reports without side effects.
- **Added:** 4 pre-built workflow templates:
  1. *Morning Market Briefing*
  2. *High Volatility Alert*
  3. *System Health Sentinel*
  4. *Market Close Portfolio Summary*

### 🪟 Windows Packaging, Native Launcher & Auto-Updater
- **Added:** `desktop_launcher.py` running the workstation inside a native 1400x900 Windows desktop shell using `pywebview` with automatic browser app-mode fallback.
- **Added:** Desktop shortcut creation scripts: `scripts/create_desktop_shortcut.vbs` and `scripts/create_shortcut.py`.
- **Added:** PyInstaller compilation automation in `scripts/build_windows_app.py`.
- **Added:** `SecureAutoUpdater` in `backend/auto_updater.py` with semantic version comparison, mandatory SHA-256 integrity verification, staging isolation (`data/staging/`), pre-update rollback snapshots (`data/backups/`), and atomic rollback recovery.

### 💻 Frontend & UI Enhancements
- **Added:** 10-Tab Workstation Navigation (`Command Center`, `Health Center`, `AI Providers`, `Strategy Lab`, `Paper Portfolio`, `Psychology`, `Research Lab`, `Memory Brain`, `Workflows`, `Security`).
- **Added:** Header hardware privacy kill switch toggles (Mic & Screen).
- **Added:** Real-time voice state badge and instant "Stop Voice" barge-in interruption button.
- **Added:** Action confirmation modal dialog for two-step approval of high-impact actions.
- **Added:** Comprehensive OLED dark theme styling in `frontend/style.css`.

### 🧪 Automated Testing & Documentation
- **Added:** 29 automated tests across 8 test suites in `tests/` with 100% pass rate.
- **Added:** Complete documentation suite:
  - `README.md`
  - `ARCHITECTURE.md`
  - `SECURITY.md`
  - `INSTALLATION.md`
  - `WINDOWS_BUILD.md`
  - `AUTO_UPDATE.md`
  - `TEST_REPORT.md`
  - `CHANGELOG.md`

---

## [2.0.0] - 2026-10-25
- Initial release of JARVIS AI Workstation.
- Basic FastAPI backend and WebSocket telemetry.
- Voice synthesis and local wake-word listener.
- Screen vision and OCR capture tools.
- Initial trading scanner and PDF research engine.

