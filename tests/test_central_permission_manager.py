"""
Unit and integration tests for Component 4: Central Permission Manager.
Tests Default-Deny, 4 permission levels, interactive approvals, and persistent grants.
"""

from backend.permissions import (
    CentralPermissionManager,
    PermissionLevel,
    PermissionComponent
)

def test_permission_levels_and_default_deny():
    # Arbitrary resource without grant must be denied under default-deny
    auth, reason, _ = CentralPermissionManager.check_permission(
        component="os",
        resource="disk_format",
        level=PermissionLevel.EXECUTE,
        auto_request_approval=False
    )
    assert auth is False
    assert "No active grant" in reason

def test_safe_read_whitelist():
    # Whitelisted read-only resources must be auto-approved
    auth, reason, _ = CentralPermissionManager.check_permission(
        component="files",
        resource="data/reports",
        level=PermissionLevel.READ
    )
    assert auth is True
    assert "Safe resource auto-approved" in reason

def test_permission_grant_and_revoke():
    # 1. Grant permission
    grant = CentralPermissionManager.grant_permission(
        component="skills",
        resource="test_custom_skill",
        level=PermissionLevel.EXECUTE,
        is_persistent=True,
        notes="Automated test grant"
    )
    assert grant["id"].startswith("perm_")

    # 2. Verify authorization
    auth, _, g = CentralPermissionManager.check_permission(
        component="skills",
        resource="test_custom_skill",
        level=PermissionLevel.EXECUTE
    )
    assert auth is True
    assert g["id"] == grant["id"]

    # 3. Revoke grant
    rev_ok = CentralPermissionManager.revoke_permission(grant["id"])
    assert rev_ok is True

    # 4. Verify no longer authorized
    auth_after, _, _ = CentralPermissionManager.check_permission(
        component="skills",
        resource="test_custom_skill",
        level=PermissionLevel.EXECUTE,
        auto_request_approval=False
    )
    assert auth_after is False

def test_sensitive_interactive_approval_flow():
    # SENSITIVE actions trigger pending action approval
    auth, reason, payload = CentralPermissionManager.check_permission(
        component="browser",
        resource="https://bank.com/transfer",
        level=PermissionLevel.SENSITIVE,
        description="Wire transfer test",
        auto_request_approval=True
    )
    assert auth is False
    assert "pending_approval" in str(payload)
    action_id = payload["action_id"]

    # List pending actions
    pending = CentralPermissionManager.list_pending_approvals()
    assert any(p["action_id"] == action_id for p in pending)

    # Approve action
    appr_ok, msg, act = CentralPermissionManager.approve_action(action_id, grant_persistence=False)
    assert appr_ok is True
    assert act["status"] == "approved"

