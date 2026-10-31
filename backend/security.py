import os
import re
import json
import time
import uuid
import secrets
import threading
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from fastapi import Request, HTTPException, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery

from .config import settings

# Ensure data directory exists
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_LOG_FILE = settings.DATA_DIR / "audit_log.json"

# =========================================================================
# 1. SECRET REDACTION ENGINE
# =========================================================================
SENSITIVE_PATTERNS = [
    # Google Gemini keys (AQ.Ab8... or AIzaSy...)
    re.compile(r'AQ\.[A-Za-z0-9_-]{20,}', re.IGNORECASE),
    re.compile(r'AIza[0-9A-Za-z-_]{20,}', re.IGNORECASE),
    # Groq API keys (gsk_...)
    re.compile(r'gsk_[A-Za-z0-9]{30,}', re.IGNORECASE),
    # OpenRouter API keys (sk-or-v1-...)
    re.compile(r'sk-or-v1-[a-f0-9]{40,}', re.IGNORECASE),
    # Generic Bearer tokens and passwords
    re.compile(r'Bearer\s+[A-Za-z0-9._\-]{20,}', re.IGNORECASE),
    re.compile(r'(password|secret|apikey|api_key|token)\s*[:=]\s*["\']?([^"\'\s]{8,})["\']?', re.IGNORECASE)
]

def redact_secrets(text_or_data: Any) -> Any:
    """
    Recursively scans strings, dictionaries, or lists to sanitize and mask
    sensitive API keys, tokens, or credentials before logging or display.
    """
    if isinstance(text_or_data, str):
        redacted = text_or_data
        # Explicitly mask known keys in settings if present
        for key in settings.gemini_keys_pool + [settings.GROQ_API_KEY, settings.OPENROUTER_API_KEY, settings.SARVAM_API_KEY]:
            if key and len(key) > 8:
                masked = f"{key[:4]}...{key[-4:]}"
                redacted = redacted.replace(key, masked)
        
        for pat in SENSITIVE_PATTERNS:
            redacted = pat.sub(r'***REDACTED_SECRET***', redacted)
        return redacted
    elif isinstance(text_or_data, dict):
        sanitized = {}
        for k, v in text_or_data.items():
            if any(s in k.lower() for s in ["key", "secret", "token", "password", "auth"]):
                if isinstance(v, str) and len(v) > 8:
                    sanitized[k] = f"{v[:4]}...{v[-4:]} [REDACTED]"
                else:
                    sanitized[k] = "***REDACTED***"
            else:
                sanitized[k] = redact_secrets(v)
        return sanitized
    elif isinstance(text_or_data, list):
        return [redact_secrets(item) for item in text_or_data]
    return text_or_data


# =========================================================================
# 2. SESSION TOKEN AUTHENTICATION
# =========================================================================
api_key_header = APIKeyHeader(name="X-JARVIS-Session", auto_error=False)
api_key_query = APIKeyQuery(name="token", auto_error=False)

def verify_session_token(
    request: Request,
    token_header: Optional[str] = Security(api_key_header),
    token_query: Optional[str] = Security(api_key_query)
) -> bool:
    """
    Validates the session token for sensitive administrative & OS endpoints.
    Allows loopback requests if configured, or validates token against settings.SESSION_TOKEN.
    """
    # Accept token from header, query, or cookie
    token = token_header or token_query or request.cookies.get("session_token")
    
    # Check localhost loopback with development tolerance if no token provided
    client_host = request.client.host if request.client else "unknown"
    is_local = client_host in ["127.0.0.1", "localhost", "::1"]
    
    if token:
        if secrets.compare_digest(token, settings.SESSION_TOKEN):
            return True
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired J.A.R.V.I.S. session token."
        )
    
    # If no token passed, require token unless request comes strictly from local machine in debug mode
    if is_local and settings.DEBUG:
        return True
        
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing J.A.R.V.I.S. session authorization header (X-JARVIS-Session)."
    )


# =========================================================================
# 3. ACTION REGISTRY & TWO-STEP CONFIRMATION WORKFLOW
# =========================================================================
class RiskLevel(str, Enum):
    SAFE = "safe"              # Read metrics, list windows, telemetry (Auto-approved)
    MEDIUM = "medium"          # Launch app, open URL, adjust volume (Logged)
    HIGH = "high"              # Terminate process, delete file, empty bin, system settings (Requires 2-step approval)

class PendingAction:
    def __init__(
        self,
        action_type: str,
        target: str,
        description: str,
        risk_level: RiskLevel,
        params: Optional[Dict[str, Any]] = None,
        ttl_seconds: int = 60
    ):
        self.action_id = f"act_{uuid.uuid4().hex[:12]}"
        self.action_type = action_type
        self.target = target
        self.description = description
        self.risk_level = risk_level
        self.params = params or {}
        self.created_at = time.time()
        self.expires_at = self.created_at + ttl_seconds
        self.status = "pending"  # pending, approved, rejected, expired, executed

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "action_type": self.action_type,
            "target": self.target,
            "description": self.description,
            "risk_level": self.risk_level.value,
            "params": self.params,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "remaining_seconds": max(0, int(self.expires_at - time.time()))
        }

class ActionConfirmationRegistry:
    """
    Thread-safe registry for managing pending high-risk system operations.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._pending: Dict[str, PendingAction] = {}

    def register(
        self,
        action_type: str,
        target: str,
        description: str,
        risk_level: RiskLevel = RiskLevel.HIGH,
        params: Optional[Dict[str, Any]] = None,
        ttl_seconds: int = 60
    ) -> PendingAction:
        with self._lock:
            self._cleanup_expired_locked()
            action = PendingAction(action_type, target, description, risk_level, params, ttl_seconds)
            self._pending[action.action_id] = action
            return action

    def get(self, action_id: str) -> Optional[PendingAction]:
        with self._lock:
            self._cleanup_expired_locked()
            return self._pending.get(action_id)

    def approve(self, action_id: str) -> Tuple[bool, str, Optional[PendingAction]]:
        with self._lock:
            self._cleanup_expired_locked()
            action = self._pending.get(action_id)
            if not action:
                return False, "Action ID not found or already expired.", None
            if time.time() > action.expires_at:
                action.status = "expired"
                return False, "Action confirmation window has expired.", action
            if action.status != "pending":
                return False, f"Action is already in state: {action.status}", action
            action.status = "approved"
            return True, "Action approved for execution.", action

    def reject(self, action_id: str) -> Tuple[bool, str]:
        with self._lock:
            self._cleanup_expired_locked()
            action = self._pending.get(action_id)
            if not action:
                return False, "Action ID not found."
            action.status = "rejected"
            return True, "Action was rejected by user."

    def list_pending(self) -> List[Dict[str, Any]]:
        with self._lock:
            self._cleanup_expired_locked()
            return [act.to_dict() for act in self._pending.values() if act.status == "pending"]

    def _cleanup_expired_locked(self):
        now = time.time()
        expired_ids = [aid for aid, act in self._pending.items() if act.status == "pending" and now > act.expires_at]
        for aid in expired_ids:
            self._pending[aid].status = "expired"

action_registry = ActionConfirmationRegistry()


# =========================================================================
# 4. STRUCTURED AUDIT LOGGER
# =========================================================================
_audit_lock = threading.Lock()

def log_audit_event(
    action_type: str,
    target: str,
    risk_level: str,
    status: str,
    approved_by: str = "system",
    details: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None
):
    """
    Appends structured, immutable audit log events to data/audit_log.json
    with sensitive secrets masked and timestamp recorded.
    """
    record = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "epoch": time.time(),
        "action_type": action_type,
        "target": target,
        "risk_level": risk_level,
        "status": status,
        "approved_by": approved_by,
        "details": redact_secrets(details or {}),
        "error": redact_secrets(error) if error else None
    }
    
    with _audit_lock:
        try:
            records = []
            if AUDIT_LOG_FILE.exists() and AUDIT_LOG_FILE.stat().st_size > 0:
                try:
                    with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                        records = json.load(f)
                        if not isinstance(records, list):
                            records = []
                except Exception:
                    records = []
            
            records.append(record)
            # Keep latest 2,000 audit records
            if len(records) > 2000:
                records = records[-2000:]
                
            with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(records, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Audit Log Error]: Failed to write audit event: {e}")

def get_recent_audit_logs(limit: int = 50) -> List[Dict[str, Any]]:
    with _audit_lock:
        if not AUDIT_LOG_FILE.exists():
            return []
        try:
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                records = json.load(f)
                return records[-limit:][::-1] if isinstance(records, list) else []
        except Exception:
            return []


# =========================================================================
# 5. PRIVACY CONTROLS & KILL SWITCHES
# =========================================================================
class PrivacyController:
    """
    Thread-safe hardware and software privacy kill-switches.
    Wake listener is DISABLED by default until explicitly activated by user.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.mic_kill_switch = False       # True = Microphone completely muted/blocked
        self.screen_kill_switch = False    # True = Screen Vision capture blocked
        self.wake_listener_active = settings.ENABLE_WAKE_WORD_DEFAULT

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "mic_kill_switch": self.mic_kill_switch,
                "screen_kill_switch": self.screen_kill_switch,
                "wake_listener_active": self.wake_listener_active,
                "mic_active": not self.mic_kill_switch and self.wake_listener_active,
                "screen_active": not self.screen_kill_switch and settings.ENABLE_SCREEN_VISION
            }

    def set_mic_kill_switch(self, state: bool) -> bool:
        with self._lock:
            self.mic_kill_switch = state
            log_audit_event("privacy_kill_switch", "microphone", "high", "engaged" if state else "released", "user")
            return self.mic_kill_switch

    def set_screen_kill_switch(self, state: bool) -> bool:
        with self._lock:
            self.screen_kill_switch = state
            log_audit_event("privacy_kill_switch", "screen_vision", "high", "engaged" if state else "released", "user")
            return self.screen_kill_switch

    def set_wake_listener(self, state: bool) -> bool:
        with self._lock:
            self.wake_listener_active = state
            log_audit_event("wake_word_listener", "voice_activation", "medium", "enabled" if state else "disabled", "user")
            return self.wake_listener_active

privacy_guard = PrivacyController()


# =========================================================================
# 6. FILE UPLOAD & PATH TRAVERSAL DEFENSE
# =========================================================================
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".png", ".jpg", ".jpeg", ".webp", ".pdf", ".txt", ".json", ".csv"}

def validate_upload_file(filename: str, size_bytes: int) -> Tuple[bool, str]:
    if size_bytes > settings.MAX_UPLOAD_SIZE_BYTES:
        return False, f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_BYTES // (1024*1024)} MB."
    
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Unsupported file type '{ext}'. Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        
    # Check for path traversal attacks in filename
    if ".." in filename or "/" in filename or "\\" in filename:
        return False, "Illegal characters detected in filename."
        
    return True, "Valid"

def sanitize_safe_path(base_dir: Path, user_path: str) -> Optional[Path]:
    """
    Prevents path traversal attacks by ensuring the resolved target path
    is strictly within the intended base directory.
    """
    try:
        resolved = (base_dir / user_path).resolve()
        if base_dir.resolve() in resolved.parents or base_dir.resolve() == resolved:
            return resolved
        return None
    except Exception:
        return None
