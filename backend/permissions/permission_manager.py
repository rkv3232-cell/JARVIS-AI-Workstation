"""
Centralized Permission Manager for JARVIS-APEX.
Implements Default-Deny authorization across Browser, Skills, Files, Memory, OS, and Automation.
Four permission levels: READ, WRITE, EXECUTE, SENSITIVE.
"""

import time
import uuid
import sqlite3
import threading
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from fastapi import HTTPException, status, Request

from ..config import settings
from ..security import action_registry, RiskLevel
from ..activity import ActivityLogger

DB_PATH = Path(__file__).resolve().parent.parent / "jarvis.db"

class PermissionLevel(str, Enum):
    READ = "READ"           # Safe inspection, metrics, querying
    WRITE = "WRITE"         # Mutation, creation, configuration updates
    EXECUTE = "EXECUTE"     # Code execution, terminal commands, process launching
    SENSITIVE = "SENSITIVE" # High-risk actions (financials, deletions, external network, system core)

LEVEL_RANKS = {
    PermissionLevel.READ: 1,
    PermissionLevel.WRITE: 2,
    PermissionLevel.EXECUTE: 3,
    PermissionLevel.SENSITIVE: 4
}

class PermissionComponent(str, Enum):
    BROWSER = "browser"
    SKILLS = "skills"
    FILES = "files"
    MEMORY = "memory"
    OS = "os"
    AUTOMATION = "automation"
    COLLABORATION = "collaboration"

# Whitelisted safe read-only resources that do not require explicit pre-grants
SAFE_READ_RESOURCES = {
    "data", "reports", "frontend", "skills", "system_metrics", "tab_list", "memory_search", "audit_log"
}

class CentralPermissionManager:
    """
    Central authorization authority for all privileged operations.
    Thread-safe and persistent in SQLite.
    """
    _lock = threading.Lock()

    @classmethod
    def grant_permission(
        cls,
        component: str,
        resource: str,
        level: PermissionLevel,
        is_persistent: bool = False,
        ttl_seconds: Optional[int] = None,
        granted_by: str = "user",
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Grants a permission to a component & resource at a specific level.
        Can be persistent or time-limited (TTL).
        """
        grant_id = f"perm_{uuid.uuid4().hex[:10]}"
        now = time.time()
        expires_at = (now + ttl_seconds) if (ttl_seconds and not is_persistent) else None

        with cls._lock:
            with sqlite3.connect(str(DB_PATH)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO permission_grants (
                        id, component, resource, level, is_persistent, granted_at, expires_at, granted_by, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    grant_id, component.lower(), resource.lower(), level.value,
                    1 if is_persistent else 0, now, expires_at, granted_by, notes or ""
                ))
                conn.commit()

        grant_record = {
            "id": grant_id,
            "component": component.lower(),
            "resource": resource.lower(),
            "level": level.value,
            "is_persistent": is_persistent,
            "granted_at": now,
            "expires_at": expires_at,
            "granted_by": granted_by,
            "notes": notes
        }

        ActivityLogger.log(
            component="permissions",
            action="grant_permission",
            target_resource=f"{component}:{resource}",
            approval_status="USER_APPROVED" if granted_by == "user" else "AUTO_APPROVED",
            execution_status="SUCCESS",
            result_summary=f"Granted {level.value} on {component}:{resource} (persistent={is_persistent})",
            metadata=grant_record
        )

        return grant_record

    @classmethod
    def revoke_permission(cls, grant_id: str) -> bool:
        """Revokes an existing permission grant."""
        with cls._lock:
            with sqlite3.connect(str(DB_PATH)) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT component, resource, level FROM permission_grants WHERE id = ?;", (grant_id,))
                row = cursor.fetchone()
                if not row:
                    return False

                cursor.execute("DELETE FROM permission_grants WHERE id = ?;", (grant_id,))
                conn.commit()

        ActivityLogger.log(
            component="permissions",
            action="revoke_permission",
            target_resource=f"{row[0]}:{row[1]}",
            approval_status="USER_APPROVED",
            execution_status="SUCCESS",
            result_summary=f"Revoked grant {grant_id} ({row[2]} on {row[0]}:{row[1]})"
        )
        return True

    @classmethod
    def list_grants(cls, component: Optional[str] = None, active_only: bool = True) -> List[Dict[str, Any]]:
        """Lists active and persistent permission grants."""
        now = time.time()
        query = "SELECT * FROM permission_grants"
        conditions = []
        params = []

        if component and component != "all":
            conditions.append("component = ?")
            params.append(component.lower())

        if active_only:
            conditions.append("(is_persistent = 1 OR expires_at IS NULL OR expires_at > ?)")
            params.append(now)

        if conditions:
            query += f" WHERE {' AND '.join(conditions)}"

        query += " ORDER BY granted_at DESC;"

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(r) for r in cursor.fetchall()]

    @classmethod
    def check_permission(
        cls,
        component: str,
        resource: str,
        level: PermissionLevel,
        description: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        auto_request_approval: bool = True
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Evaluates whether an action is authorized under default-deny policy.
        Returns: (is_authorized, reason, payload)
        If level is SENSITIVE and no persistent grant exists, automatically registers
        a pending action in ActionConfirmationRegistry for interactive user approval.
        """
        comp_key = component.lower()
        res_key = resource.lower()
        req_rank = LEVEL_RANKS[level]
        now = time.time()

        # 1. Safe READ Whitelist
        if level == PermissionLevel.READ:
            if any(safe_res in res_key for safe_res in SAFE_READ_RESOURCES):
                return True, "Safe resource auto-approved for READ.", None

        # 2. Check active grants in SQLite
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Match exact resource or wildcard '*'
            cursor.execute("""
                SELECT * FROM permission_grants
                WHERE component = ? AND (resource = ? OR resource = '*')
                AND (is_persistent = 1 OR expires_at IS NULL OR expires_at > ?)
                ORDER BY is_persistent DESC, granted_at DESC;
            """, (comp_key, res_key, now))
            grants = cursor.fetchall()

        for g in grants:
            g_level = PermissionLevel(g["level"])
            g_rank = LEVEL_RANKS.get(g_level, 0)
            # If the grant rank satisfies requested level rank
            if g_rank >= req_rank:
                # If requested level is SENSITIVE, verify persistent grant explicitly specifies SENSITIVE
                if level == PermissionLevel.SENSITIVE and g_level != PermissionLevel.SENSITIVE:
                    continue
                return True, f"Authorized by grant {g['id']} ({g['level']}).", dict(g)

        # 3. If SENSITIVE or no grant found:
        if level == PermissionLevel.SENSITIVE:
            if auto_request_approval:
                action_desc = description or f"Privileged {level.value} action requested on {component}:{resource}"
                pending = action_registry.register(
                    action_type=f"{component}:{resource}",
                    target=resource,
                    description=action_desc,
                    risk_level=RiskLevel.HIGH,
                    params=context or {},
                    ttl_seconds=90
                )

                # Broadcast pending approval to frontend via WebSocket
                try:
                    from ..websocket_manager import ws_manager
                    import asyncio
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(ws_manager.broadcast("security_approval_required", {
                            "action_id": pending.action_id,
                            "action_type": pending.action_type,
                            "target": pending.target,
                            "description": pending.description,
                            "risk_level": pending.risk_level.value,
                            "ttl_seconds": 90
                        }))
                except Exception:
                    pass

                ActivityLogger.log(
                    component="permissions",
                    action="request_approval",
                    target_resource=f"{component}:{resource}",
                    approval_status="PENDING",
                    execution_status="IN_PROGRESS",
                    result_summary=f"Requires user approval: {pending.action_id}",
                    metadata={"action_id": pending.action_id, "level": level.value}
                )

                return False, "SENSITIVE operation requires user confirmation.", {"action_id": pending.action_id, "status": "pending_approval"}

            return False, f"Permission denied: SENSITIVE authorization required on {component}:{resource}.", None

        # Standard Default-Deny for READ/WRITE/EXECUTE without grant
        ActivityLogger.log(
            component="permissions",
            action="permission_denied",
            target_resource=f"{component}:{resource}",
            approval_status="DENIED",
            execution_status="FAILED",
            result_summary=f"Default-deny blocked {level.value} on {component}:{resource}"
        )
        return False, f"Permission denied: No active grant for {level.value} on {component}:{resource}.", None

    @classmethod
    def approve_action(cls, action_id: str, grant_persistence: bool = False) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Approves an interactive pending action. If grant_persistence is True,
        also records a persistent grant in SQLite.
        """
        success, msg, action = action_registry.approve(action_id)
        if not success or not action:
            return False, msg, None

        if grant_persistence:
            comp, res = action.action_type.split(":", 1) if ":" in action.action_type else ("system", action.action_type)
            cls.grant_permission(
                component=comp,
                resource=res,
                level=PermissionLevel.SENSITIVE,
                is_persistent=True,
                granted_by="user",
                notes=f"Auto-persisted via action approval: {action_id}"
            )

        ActivityLogger.log(
            component="permissions",
            action="action_approved",
            target_resource=action.target,
            approval_status="USER_APPROVED",
            execution_status="SUCCESS",
            result_summary=f"User approved action {action_id} ({action.action_type})"
        )

        return True, "Action approved successfully.", action.to_dict()

    @classmethod
    def reject_action(cls, action_id: str) -> Tuple[bool, str]:
        """Rejects a pending action."""
        success, msg = action_registry.reject(action_id)
        action = action_registry.get(action_id)
        target = action.target if action else action_id

        ActivityLogger.log(
            component="permissions",
            action="action_rejected",
            target_resource=target,
            approval_status="DENIED",
            execution_status="FAILED",
            result_summary=f"User rejected action {action_id}"
        )
        return success, msg

    @classmethod
    def list_pending_approvals(cls) -> List[Dict[str, Any]]:
        """Returns all currently pending interactive authorization requests."""
        return action_registry.list_pending()
