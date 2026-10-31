import time
import pytest
from pathlib import Path
from backend.security import (
    redact_secrets,
    action_registry,
    RiskLevel,
    privacy_guard,
    validate_upload_file,
    sanitize_safe_path,
    log_audit_event,
    get_recent_audit_logs
)

def test_secret_redaction():
    text_with_keys = "My key is AIzaSyD3xAmPlE1234567890abcdefghijklm and groq is gsk_123456789012345678901234567890"
    cleaned = redact_secrets(text_with_keys)
    assert "AIzaSyD3xAmPlE" not in cleaned
    assert "gsk_123456789012" not in cleaned
    assert "REDACTED" in cleaned

    dict_data = {"api_key": "super_secret_value_123456", "username": "admin"}
    redacted_dict = redact_secrets(dict_data)
    assert "super_secret_value_123456" not in str(redacted_dict)
    assert redacted_dict["username"] == "admin"

def test_action_registry_confirmation_lifecycle():
    action = action_registry.register(
        action_type="delete_file",
        target="temp.txt",
        description="Delete temporary log file",
        risk_level=RiskLevel.HIGH,
        params={"path": "temp.txt"},
        ttl_seconds=60
    )
    assert action.status == "pending"
    assert action.action_id.startswith("act_")

    # Verify retrieval
    retrieved = action_registry.get(action.action_id)
    assert retrieved is not None
    assert retrieved.action_type == "delete_file"

    # Approve action
    ok, msg, approved_act = action_registry.approve(action.action_id)
    assert ok is True
    assert approved_act.status == "approved"

    # Cannot approve again
    ok2, msg2, _ = action_registry.approve(action.action_id)
    assert ok2 is False

def test_path_traversal_sanitizer(tmp_path):
    safe_base = tmp_path / "sandbox"
    safe_base.mkdir()
    
    # Valid relative path
    valid_p = sanitize_safe_path(safe_base, "sub/file.txt")
    assert valid_p is not None

    # Attack: directory traversal attempt
    attack_p = sanitize_safe_path(safe_base, "../../windows/system32/cmd.exe")
    assert attack_p is None

def test_upload_validator():
    # Valid audio file
    ok, msg = validate_upload_file("voice.wav", 1024 * 100)
    assert ok is True

    # Invalid extension
    ok, msg = validate_upload_file("malicious.exe", 1024)
    assert ok is False
    assert "Unsupported file type" in msg

    # Oversized file
    ok, msg = validate_upload_file("huge.wav", 30 * 1024 * 1024)
    assert ok is False
    assert "exceeds maximum" in msg

    # Traversal in filename
    ok, msg = validate_upload_file("../etc/passwd.txt", 100)
    assert ok is False
    assert "Illegal characters" in msg

def test_privacy_kill_switches():
    # Mic kill switch
    privacy_guard.set_mic_kill_switch(True)
    assert privacy_guard.mic_kill_switch is True
    assert privacy_guard.get_status()["mic_kill_switch"] is True

    privacy_guard.set_mic_kill_switch(False)
    assert privacy_guard.mic_kill_switch is False

    # Screen kill switch
    privacy_guard.set_screen_kill_switch(True)
    assert privacy_guard.screen_kill_switch is True
    privacy_guard.set_screen_kill_switch(False)
    assert privacy_guard.screen_kill_switch is False

def test_structured_audit_logger():
    log_audit_event("test_audit_action", "unit_test_target", "safe", "success", "pytest")
    logs = get_recent_audit_logs(limit=10)
    assert len(logs) > 0
    latest = logs[0]
    assert latest["action_type"] == "test_audit_action"
    assert latest["approved_by"] == "pytest"
