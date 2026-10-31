# CHANGELOG — JARVIS-APEX

All notable changes to the **JARVIS-APEX** Windows Desktop AI Workstation will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.2.0] - 2026-10-31

### 🚀 7 Core Architecture Components Implementation
- **🌐 Component 1 — AI Browser Operator:**
  - Integrated Playwright-powered multi-tab browser engine (`backend/browser/browser_engine.py`) with persistent context support in `data/browser_profile`.
  - Added enterprise-grade SSRF protection (`validate_url_for_ssrf`), protocol restriction, prompt injection containment, and emergency stop automation (`POST /api/browser/stop`).
  - Implemented AI page understanding suite (`backend/browser/browser_operator.py`): page summarization, grounded Q&A against DOM, multi-tab comparison, HTML table extraction, and grounded publication-grade PDF report compiler.
  - Implemented persistent bookmarks, history, and downloads in SQLite (`browser_bookmarks`, `browser_history`, `browser_downloads`).
- **⚡ Component 2 — Modular Skills System:**
  - Established standardized `skills/` directory structure with `manifest.json`, `SKILL.md`, `scripts/main.py`, `references/`, and `examples/`.
  - Implemented `SkillValidator` with Python AST static security analysis to detect and block dangerous imports (`ctypes`, `winreg`) and unsafe functions (`eval`, `exec`).
  - Authored 6 production skills: `coding_specialist`, `deep_researcher`, `pdf_generator`, `windows_controller`, `data_analyst`, and `custom_automation`.
- **🧰 Component 3 — Skill Manager:**
  - Built dynamic discovery, registration, and enable/disable toggling in SQLite (`skills_registry`).
  - Added secure local folder installation with pre-install directory structure and security audits.
  - Added execution history tracking in `skill_execution_history`.
- **🛡️ Component 4 — Central Permission Manager:**
  - Centralized authorization authority with Default-Deny architecture (`backend/permissions/permission_manager.py`).
  - Defined 4 permission levels: `READ`, `WRITE`, `EXECUTE`, `SENSITIVE`.
  - Stored persistent and temporary (TTL) grants in SQLite `permission_grants` table.
  - Integrated interactive two-step approval flow via `ActionConfirmationRegistry` with real-time WebSocket notifications.
- **🤝 Component 5 — Skill Collaboration Engine:**
  - Developed multi-skill task planner (`backend/collaboration/collaboration_engine.py`) decomposing complex user objectives into sequential DAG pipelines.
  - Built data pipelining transferring outputs from preceding skills into downstream inputs.
  - Added lifecycle controls: pause, resume, cancel, and step retry with SQLite persistence in `collaboration_tasks` and `collaboration_steps`.
- **📜 Component 6 — Unified Activity Log:**
  - Unified audit trail (`backend/activity/activity_logger.py`) capturing operations across Browser, Skills, Permissions, Collaboration, Memory, OS, and System.
  - Dual-write architecture to SQLite `activity_logs` table and `data/audit_log.json`.
  - Automatic secret redaction for all tokens, credentials, and keys via `redact_secrets()`.
  - Filtering by component, execution status, approval status, and text search, with JSON and CSV export capabilities.
- **⏳ Component 7 — Memory Timeline & Transparency Engine:**
  - Migrated `memory_nodes` table to schema v3 with source attribution (`source_type`, `source_url`, `source_reference`), importance flags, and access counters.
  - Implemented access tracking in `memory_access_log`.
  - Added true in-place editing, permanent deletion (from SQLite and FTS5 index), and comprehensive privacy controls (recording kill-switch, excluded categories, sensitive keywords).
- **🧪 Test Suite & Quality Assurance:**
  - 81 / 81 automated pytest tests passing with 100% success rate across all components.

## [2.1.1] - 2026-10-31

### 🔒 Security, SSRF & Frontend XSS Hardening
- **Added:** Enterprise-grade Server-Side Request Forgery (SSRF) protection in `backend/url_threat_analyzer.py` (`is_ssrf_safe_ip`, `validate_url_for_ssrf`). Rejects loopback (`127.0.0.1`, `localhost`, `::1`), private RFC 1918 subnets, link-local addresses, and cloud metadata endpoints (`169.254.169.254`, `metadata.google.internal`).
- **Added:** Manual redirect inspection validating destination IP on each redirect hop up to 5 levels to prevent redirect-based SSRF.
- **Added:** Memory exhaustion defense on `/api/transcribe`: validates filename before byte ingestion and performs chunked streaming reading (64KB chunks) capped at `settings.MAX_UPLOAD_SIZE_BYTES`, aborting with HTTP 413 upon overflow.
- **Added:** Comprehensive Frontend XSS defense in `frontend/app.js` with `escapeHtml()` sanitization across chat feeds, persistent memory views, workflow templates, execution histories, and confirmation dialogs.

### 👁️ AI Vision Reliability & Honest Fallbacks
- **Eliminated:** Hallucinated screen perceptions in `backend/ai_screen_vision.py`. When vision AI providers fail or are unreachable, returns clear `is_fallback: True` and explicit notice rather than fabricated statements.
- **Eliminated:** Fabricated chart pattern overlays with hardcoded support levels on provider failure. Returns `success: False` with empty overlays list.
- **Fixed:** Accurate clipboard error reporting: does not falsely report that code was copied to clipboard if `pyperclip.copy` failed.

### ⚙️ Visual Workflow Automation Engine Completion
- **Added:** Asynchronous `WorkflowScheduler` running in the FastAPI lifespan, periodically checking and triggering enabled time-scheduled workflows.
- **Added:** Resumption of approved workflows: `execute_confirmed_action()` now handles `workflow_execution` actions by calling `WorkflowEngine.resume_confirmed_workflow()`.
- **Added:** Genuine subsystems dispatching for allowlisted workflow actions (`send_notification`, `speak_voice_message`, `run_market_scan`, `open_url`, `set_system_theme`, `create_trade_journal`).

### 📈 Trading Lab & SMC Bar Alignment
- **Fixed:** Fair Value Gap (FVG) detection bar index aligned to bar $i$ (confirmation bar) with `c2["time"]`, eliminating look-ahead into the preceding bar $i-1$.
- **Added:** Integrated pending limit and stop-loss/take-profit evaluation on all live price feeds in `PaperTradingPortfolio.get_portfolio_summary()`.

### 📦 Desktop Packaging & Repository Hygiene
- **Hardened:** ZIP-slip extraction defense (`safe_extract_zip`) applied to updater rollback snapshots.
- **Fixed:** `scripts/build_windows_app.py` propagates PyInstaller exit codes correctly and supports `--onefile` or `--onedir`.
- **Repository Hygiene:** Untracked 38 MP3 cache files (-16.9 MB) and git-ignored `frontend/audio_cache/`.
- **Automated Tests:** 51 / 51 tests passed (100% success rate).

### 🔒 API & WebSocket Authentication Enforcement
- **Enforced:** Applied `verify_session_token` dependency to all sensitive REST endpoints across OS controls, pending action approvals, audit logs, persistent memory, paper trading, and visual workflows.
- **Enforced:** Strict Origin validation and token checking for WebSocket connections with code 1008 rejection for untrusted origins or invalid credentials.
- **Hardened:** Replaced predictable default session secret with dynamic high-entropy 32-byte secret generated in `data/.session_secret`; raises fatal `RuntimeError` on startup if secret is missing or insecure in production.
- **Hardened:** Switched `DEBUG` setting default to `False`.
- **Hardened:** Query-string token authorization strictly prohibited for ordinary REST endpoints (allowed solely on WebSocket handshake due to browser WebSocket API constraints).
- **Hardened:** Secure frontend session initialization with automated `session_token` cookie and `X-JARVIS-Session` fetch interceptor in `frontend/app.js`.

### 🎙️ Hardware Microphone & Screen Vision Privacy
- **Fixed:** True runtime physical lifecycle control in `backend/local_wake_listener.py`. Microphone OFF physically stops and closes the active `sd.InputStream` and drains residual queues.
- **Fixed:** Thread-safe listener synchronization preventing race conditions and duplicate microphone streams.
- **Enforced:** Screen-vision kill switch systematically enforced across all capture entry points: `capture_desktop_image`, `analyze_screen_with_ai`, `detect_chart_patterns_and_overlays`, and `extract_screen_text_and_clipboard`.

### 📦 Cryptographic Auto-Updater
- **Added:** Pinned Ed25519 digital signature verification (`PINNED_UPDATE_PUBLIC_KEY_HEX`) verifying canonical JSON release manifests before parsing.
- **Added:** Absolute ZIP-Slip path traversal defense with `SecurityError` during package extraction.
- **Hardened:** HTTPS-only release checks with trusted origin whitelisting (`github.com`, `raw.githubusercontent.com`, `objects.githubusercontent.com`).
- **Fixed:** Offline/network error returns explicit `UPDATE_CHECK_UNAVAILABLE` status instead of falsely claiming "up to date".
- **Added:** Isolated staging extraction (`updates/staging/`), automatic pre-update backup snapshot creation (`updates/backup/`), and automatic rollback upon update failure.

### 📈 Paper-Trading & Backtesting Execution Corrections
- **Fixed:** Removed arbitrary ₹100.0 price fallback for simulated MARKET orders; requires positive price from live ticker or explicitly rejected.
- **Added:** PENDING queue lifecycle for LIMIT and STOP_LOSS orders triggered by real tick evaluations (`evaluate_pending_orders_and_triggers`).
- **Added:** Realistic execution friction: ₹20 flat brokerage fee and 0.05% execution slippage applied to paper orders.
- **Fixed:** Dynamic SQLite migration adding `fee` and `notes` columns to `paper_orders` without data destruction.
- **Fixed:** Reversible account reset creating an immutable snapshot in `paper_account_snapshots` before restoring initial balance.
- **Fixed:** Strategy Lab next-bar open fill execution model (`candle[i+1]['open']`) eliminating bar-close look-ahead bias.
- **Fixed:** Indicator warm-up preserved for out-of-sample evaluation (`eval_start_idx=split_idx`).
- **Added:** Rolling walk-forward cross-validation alongside chronological holdout evaluation.

### ⚙️ Workflow Engine Condition Safety
- **Fixed:** Strict fail-closed execution on missing context fields (`SKIPPED_FAIL_CLOSED` or `SIMULATED_FAIL_CLOSED` in dry-run).
- **Added:** Operator validation against `ALLOWED_OPERATORS` returning `VALIDATION_FAILED` on unsupported operators.
- **Added:** Type-safe numeric and string comparison handling operand type mismatches gracefully.

### 🪟 Windows Desktop Launcher & Health Center
- **Fixed:** Safe process lifecycle management in `desktop_launcher.py`: gracefully handles pre-existing backend servers and avoids terminating `None` process handles.
- **Fixed:** Sarvam AI health probe actually verified via authenticated HTTP requests rather than purely credential presence.
- **Fixed:** OpenRouter reachability and authentication verified independently.
- **Added:** Detailed status classification (`CONFIGURED`, `AUTHENTICATED`, `REACHABLE`, `DEGRADED`, `UNAVAILABLE`) with ISO timestamps.

### 🧪 Automated Testing
- **Added:** `tests/test_api_auth_integration.py` (6 integration tests for REST & WebSocket auth, origin validation, cookie & header parsing).
- **Added:** `tests/test_v211_defects_regression.py` (12 regression tests verifying Ed25519 signatures, ZIP-slip defense, offline updater status, market price validation, pending limit lifecycle, reversible reset, next-bar open backtesting, fail-closed workflows, mic/screen privacy, and provider health states).
- **Result:** Total automated tests increased to 47, with 100% pass rate.

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

