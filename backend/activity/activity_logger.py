"""
Unified Activity and Audit Logging Subsystem for JARVIS-APEX.
Provides structured recording across all 7 core components with secret redaction,
dual-write to SQLite and data/audit_log.json, CSV/JSON export, and WebSocket broadcasting.
"""

import io
import csv
import json
import time
import uuid
import sqlite3
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..config import settings
from ..security import redact_secrets, AUDIT_LOG_FILE

DB_PATH = Path(__file__).resolve().parent.parent / "jarvis.db"
_activity_lock = threading.Lock()

class ActivityLogger:
    """
    Thread-safe unified activity logger. Dual writes to SQLite activity_logs
    and settings.DATA_DIR / 'audit_log.json'.
    """

    @classmethod
    def log(
        cls,
        component: str,
        action: str,
        user_request: Optional[str] = None,
        target_resource: Optional[str] = None,
        approval_status: str = "AUTO_APPROVED",
        execution_status: str = "SUCCESS",
        result_summary: Optional[str] = None,
        error_info: Optional[str] = None,
        task_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        broadcast_ws: bool = True
    ) -> Dict[str, Any]:
        """
        Logs a structured activity event across any component.
        Redacts all sensitive tokens, keys, and passwords before persistence.
        """
        event_id = f"act_{uuid.uuid4().hex[:12]}"
        now = time.time()
        ts_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))

        sanitized_req = redact_secrets(user_request) if user_request else None
        sanitized_res = redact_secrets(target_resource) if target_resource else None
        sanitized_summary = redact_secrets(result_summary) if result_summary else None
        sanitized_err = redact_secrets(error_info) if error_info else None
        sanitized_meta = redact_secrets(metadata or {})

        record = {
            "event_id": event_id,
            "timestamp": ts_str,
            "epoch": now,
            "component": str(component).lower(),
            "action": action,
            "user_request": sanitized_req,
            "target_resource": sanitized_res,
            "approval_status": approval_status,
            "execution_status": execution_status,
            "result_summary": sanitized_summary,
            "error_info": sanitized_err,
            "task_id": task_id,
            "metadata_json": json.dumps(sanitized_meta, ensure_ascii=False)
        }

        # 1. Write to SQLite
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO activity_logs (
                        event_id, timestamp, epoch, component, action, user_request,
                        target_resource, approval_status, execution_status, result_summary,
                        error_info, task_id, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (
                    record["event_id"], record["timestamp"], record["epoch"],
                    record["component"], record["action"], record["user_request"],
                    record["target_resource"], record["approval_status"],
                    record["execution_status"], record["result_summary"],
                    record["error_info"], record["task_id"], record["metadata_json"]
                ))
                conn.commit()
        except Exception as e:
            print(f"[ActivityLogger SQLite Error]: {e}")

        # 2. Append to data/audit_log.json for persistence
        with _activity_lock:
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

                records.append({
                    "event_id": record["event_id"],
                    "timestamp": record["timestamp"],
                    "epoch": record["epoch"],
                    "component": record["component"],
                    "action_type": record["action"],
                    "target": record["target_resource"],
                    "risk_level": "safe" if approval_status == "AUTO_APPROVED" else "high",
                    "status": record["execution_status"],
                    "approved_by": "user" if approval_status == "USER_APPROVED" else "system",
                    "details": sanitized_meta,
                    "error": record["error_info"]
                })

                if len(records) > 2000:
                    records = records[-2000:]

                with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
                    json.dump(records, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[ActivityLogger JSON File Error]: {e}")

        # 3. Non-blocking WebSocket broadcast
        if broadcast_ws:
            try:
                from ..websocket_manager import ws_manager
                ws_record = dict(record)
                ws_record["metadata"] = sanitized_meta
                # Fire and forget if loop is running
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(ws_manager.broadcast("activity_logged", ws_record))
            except Exception:
                pass

        return record

    @classmethod
    def get_activities(
        cls,
        component: Optional[str] = None,
        action: Optional[str] = None,
        execution_status: Optional[str] = None,
        approval_status: Optional[str] = None,
        search: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Retrieves filtered activity records with total match count for UI pagination.
        """
        conditions = []
        params = []

        if component and component != "all":
            conditions.append("component = ?")
            params.append(component.lower())

        if action:
            conditions.append("action LIKE ?")
            params.append(f"%{action}%")

        if execution_status and execution_status != "all":
            conditions.append("execution_status = ?")
            params.append(execution_status)

        if approval_status and approval_status != "all":
            conditions.append("approval_status = ?")
            params.append(approval_status)

        if start_time:
            conditions.append("epoch >= ?")
            params.append(start_time)

        if end_time:
            conditions.append("epoch <= ?")
            params.append(end_time)

        if search and search.strip():
            pat = f"%{search.strip()}%"
            conditions.append("(action LIKE ? OR user_request LIKE ? OR target_resource LIKE ? OR result_summary LIKE ? OR error_info LIKE ?)")
            params.extend([pat, pat, pat, pat, pat])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Count total matching rows
            count_query = f"SELECT COUNT(*) FROM activity_logs {where_clause};"
            cursor.execute(count_query, params)
            total = cursor.fetchone()[0]

            # Fetch page
            fetch_query = f"""
                SELECT * FROM activity_logs
                {where_clause}
                ORDER BY epoch DESC
                LIMIT ? OFFSET ?;
            """
            cursor.execute(fetch_query, params + [limit, offset])
            rows = cursor.fetchall()

        events = []
        for r in rows:
            d = dict(r)
            try:
                d["metadata"] = json.loads(d["metadata_json"])
            except Exception:
                d["metadata"] = {}
            events.append(d)

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "events": events
        }

    @classmethod
    def get_statistics(cls) -> Dict[str, Any]:
        """Calculates breakdown metrics across components and execution statuses."""
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM activity_logs;")
            total_events = cursor.fetchone()[0]

            cursor.execute("SELECT component, COUNT(*) FROM activity_logs GROUP BY component;")
            by_component = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("SELECT execution_status, COUNT(*) FROM activity_logs GROUP BY execution_status;")
            by_status = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("SELECT approval_status, COUNT(*) FROM activity_logs GROUP BY approval_status;")
            by_approval = {row[0]: row[1] for row in cursor.fetchall()}

        return {
            "total_events": total_events,
            "by_component": by_component,
            "by_status": by_status,
            "by_approval": by_approval
        }

    @classmethod
    def export_data(cls, format_type: str = "json") -> str:
        """
        Exports all activity logs as JSON string or CSV string.
        """
        res = cls.get_activities(limit=5000, offset=0)
        events = res["events"]

        if format_type.lower() == "csv":
            output = io.StringIO()
            fieldnames = [
                "event_id", "timestamp", "epoch", "component", "action",
                "user_request", "target_resource", "approval_status",
                "execution_status", "result_summary", "error_info", "task_id"
            ]
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for ev in events:
                writer.writerow(ev)
            return output.getvalue()

        return json.dumps(events, indent=2, ensure_ascii=False)

    @classmethod
    def clear_logs(cls) -> int:
        """Purges activity logs from SQLite and JSON."""
        deleted_count = 0
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM activity_logs;")
            deleted_count = cursor.rowcount
            conn.commit()

        with _activity_lock:
            try:
                with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
                    json.dump([], f, indent=2)
            except Exception:
                pass

        return deleted_count

