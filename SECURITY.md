# J.A.R.V.I.S. APEX — Security Architecture & Hardening Guide

## 1. Executive Summary & Threat Model

J.A.R.V.I.S. APEX is designed to operate as a sovereign, secure local workstation intelligence assistant on Windows 10/11. Because the workstation interacts directly with operating system APIs, filesystem directories, multimedia hardware, and financial analytical models, a defense-in-depth security model is enforced at the core architectural level.

### Key Threat Vectors Addressed
1. **Malicious Web Browser Cross-Origin Hijacking (CSRF / Origin Spoofing):**
   - **Vulnerability:** Unrestricted CORS (`allow_origins=["*"]`) combined with credentials allows malicious websites visited by the user to silently trigger OS commands via background AJAX/fetch.
   - **Mitigation:** Wildcard origins with credentials have been eliminated. CORS is strictly restricted to trusted loopback origins (`127.0.0.1`, `localhost`, `pywebview://localhost`).
2. **Command Injection & Arbitrary Shell Execution:**
   - **Vulnerability:** Unescaped strings passed to `subprocess.Popen(..., shell=True)` permit arbitrary command execution.
   - **Mitigation:** `shell=True` has been completely eliminated. Desktop settings schemes (`ms-settings:`) and explorer shortcuts (`shell:Downloads`) are launched natively via `os.startfile()`. Executable programs are verified via `shutil.which()` and executed with argument arrays (`shell=False`).
3. **Accidental High-Impact Destruction (File Deletion, Process Termination, Recycle Bin Purge):**
   - **Mitigation:** Two-step Action Confirmation Registry requiring human confirmation tokens before execution.
4. **Hardware Surveillance & Privacy Infiltration:**
   - **Mitigation:** Dedicated hardware/software kill switches for both microphone and screen vision. The wake-word listener is disabled by default until explicitly activated.
5. **Credential Leakage in Logs & Responses:**
   - **Mitigation:** Automated recursive Secret Redaction Engine masking Gemini, Groq, OpenRouter, and Sarvam API keys across logs, WebSocket broadcasts, and error responses.

---

## 2. Authentication & Session Management

- **Mandatory Endpoint Enforcement:** All sensitive administrative, OS, memory, trading, and workflow execution endpoints require a valid session token via FastAPI dependencies (`verify_session_token`).
- **Accepted Token Vectors:** Session credentials may be supplied via `X-JARVIS-Session` request header, `Authorization: Bearer <token>`, or `session_token` HTTP cookie. Query string tokens (`?token=...`) are explicitly rejected on ordinary REST endpoints.
- **WebSocket Handshake Validation:** Every WebSocket handshake to `/ws` is cryptographically validated for:
  1. Origin verification against `settings.ALLOWED_ORIGINS` (closing with code 1008 if untrusted).
  2. Credential verification via cookie, header, or validated handshake token query param.
- **High-Entropy Secret Generation:** Predictable default tokens have been eliminated. In local development, a secure 32-byte high-entropy token is dynamically generated and stored in `.session_secret` (git-ignored). In production mode (`ENVIRONMENT=production`), startup is aborted with a fatal `RuntimeError` if an explicit, cryptographically secure `SESSION_TOKEN` (>= 32 chars) is not configured.
- **Constant-Time Verification:** All session token validations employ `secrets.compare_digest` to prevent timing side-channel attacks.
- **Fail-Safe Defaults:** `DEBUG` defaults strictly to `False`.

---

## 3. Cryptographic Auto-Updater & Supply-Chain Hardening

- **Ed25519 Digital Signatures:** Release manifests are verified against a pinned Ed25519 public key (`PINNED_UPDATE_PUBLIC_KEY_HEX`) over canonical JSON serialization (`separators=(',', ':')`) before manifest fields are read.
- **Package Checksums:** Downloaded update archives are verified against signed SHA-256 integrity hashes.
- **Transport Security:** Updates are restricted exclusively to HTTPS origins on whitelisted official hosts (`github.com`, `raw.githubusercontent.com`, `objects.githubusercontent.com`).
- **ZIP-Slip Traversal Prevention:** The extraction engine resolves canonical targets against the extraction root and raises `SecurityError` upon detecting any parent directory traversal (`../`).
- **Pre-Update Backups & Atomic Rollback:** An isolated backup snapshot of code directories (`updates/backup/`) is compiled prior to update application. In the event of an extraction error, the previous version is restored atomically.
- **Offline Integrity:** Connection dropouts return an explicit `UPDATE_CHECK_UNAVAILABLE` status rather than falsely reporting that the system is up-to-date.

---

## 4. Hardware Privacy Kill Switches

High-impact desktop operations are classified into three explicit risk categories:

| Risk Level | Operations | Execution Policy |
| :--- | :--- | :--- |
| **SAFE** | System telemetry, list windows, read status, lock workstation | Auto-approved & logged |
| **MEDIUM** | Launch application, open URL, adjust volume, change theme | Auto-approved & logged |
| **HIGH** | Terminate process (`taskkill`), empty recycle bin, delete file, alter system configuration | **Requires Explicit Two-Step Approval** |

### Confirmation Workflow
```
User Query / Automated Workflow
            ↓
Risk Assessment (os_controller.py)
            ↓ (If HIGH Risk)
Action Confirmation Registry (security.py)
   - Generates Unique Action ID (e.g., act_7f9c2d11)
   - Sets Expiration (60 Seconds TTL)
   - Status: PENDING
            ↓
WebSocket / HTTP Response (`status: pending_confirmation`)
            ↓
Frontend Visual Confirmation Dialog
   - Displays Target, Command, and Countdown
            ↓
User Clicks [Approve] → POST /api/os/confirm
User Clicks [Deny]    → POST /api/os/reject
            ↓
Executed only if Approved & Unexpired
            ↓
Immutable Audit Log Written (data/audit_log.json)
```

---

## 4. Hardware Privacy Kill Switches

J.A.R.V.I.S. APEX features hardware and software isolation controls managed by `backend/security.py`:

- **Microphone Kill Switch (`privacy_guard.mic_kill_switch`):**
  - Instantly blocks audio input stream at both software and hardware layer.
  - Physical `sd.InputStream` is stopped and closed via thread-safe lock, releasing host hardware handles.
  - Residual audio queues are drained immediately to prevent audio chunk leakage.
  - Accessible via UI toggle or `POST /api/privacy/kill-switch` (`target: mic`).
- **Screen Vision Kill Switch (`privacy_guard.screen_kill_switch`):**
  - Universally enforced across all 4 capture entry points (`capture_desktop_image`, `analyze_screen_with_ai`, `detect_chart_patterns_and_overlays`, and `extract_screen_text_and_clipboard`).
  - Returns HTTP 403 Forbidden or empty payload if engaged.
- **Wake-Word Listener Default:**
  - `ENABLE_WAKE_WORD_DEFAULT=False` prevents continuous background microphone monitoring until the user explicitly toggles the wake word on.

---

## 5. Structured Audit Logging

Every operation executed by J.A.R.V.I.S. is logged to `data/audit_log.json`:

```json
{
  "timestamp": "2026-10-31 20:30:15",
  "epoch": 1793460615.12,
  "action_type": "close_app",
  "target": "chrome",
  "risk_level": "high",
  "status": "success",
  "approved_by": "user",
  "details": {
    "app_name": "chrome",
    "success": true
  },
  "error": null
}
```

- Bounded capacity: Retains the latest 2,000 events to prevent unbounded disk growth.
- Secret sanitization: All payload details pass through `redact_secrets()` before write.

---

## 6. File Upload & Path Traversal Protections

- **Upload Size Limit:** Capped at 25 MB (`settings.MAX_UPLOAD_SIZE_BYTES`).
- **Extension Allowlist:** Only audio (`.wav`, `.mp3`, `.m4a`, `.ogg`), images (`.png`, `.jpg`, `.jpeg`, `.webp`), documents (`.pdf`, `.txt`, `.json`, `.csv`) are allowed.
- **Path Sanitization:** Filenames containing `..`, `/`, `\`, or null bytes are rejected. All file access inside workspaces uses `sanitize_safe_path()` to ensure operations remain within intended directories.

