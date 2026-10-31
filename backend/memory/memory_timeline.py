"""
Memory Timeline and Transparency Engine for JARVIS-APEX.
Provides full source tracking, usage logging, in-place edits, permanent deletions,
and granular privacy controls across all persistent knowledge nodes.
"""

import json
import time
import uuid
import sqlite3
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from ..config import settings
from .memory_brain import PersistentMemoryBrain, MemoryCategory
from ..activity import ActivityLogger

DB_PATH = Path(__file__).resolve().parent.parent / "jarvis.db"
_mem_lock = threading.Lock()

class MemoryTimelineManager:
    """
    Manages chronological timeline inspection, source attribution,
    access usage logs, and user privacy configurations.
    """

    @classmethod
    def get_privacy_settings(cls) -> Dict[str, Any]:
        """Loads memory recording preferences from SQLite."""
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM memory_privacy_settings WHERE id = 'default';")
            row = cursor.fetchone()
            if not row:
                return {
                    "recording_enabled": True,
                    "excluded_categories": [],
                    "sensitive_keywords": [],
                    "retention_days": 0
                }
            d = dict(row)
            try:
                d["excluded_categories"] = json.loads(d["excluded_categories"])
            except Exception:
                d["excluded_categories"] = []
            try:
                d["sensitive_keywords"] = json.loads(d["sensitive_keywords"])
            except Exception:
                d["sensitive_keywords"] = []
            d["recording_enabled"] = bool(d["recording_enabled"])
            return d

    @classmethod
    def update_privacy_settings(
        cls,
        recording_enabled: bool,
        excluded_categories: Optional[List[str]] = None,
        sensitive_keywords: Optional[List[str]] = None,
        retention_days: int = 0
    ) -> Dict[str, Any]:
        """Saves memory privacy and auto-recording settings."""
        now = time.time()
        ex_str = json.dumps(excluded_categories or [])
        kw_str = json.dumps(sensitive_keywords or [])

        with _mem_lock:
            with sqlite3.connect(str(DB_PATH)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO memory_privacy_settings (
                        id, recording_enabled, excluded_categories, sensitive_keywords, retention_days, updated_at
                    ) VALUES ('default', ?, ?, ?, ?, ?);
                """, (1 if recording_enabled else 0, ex_str, kw_str, retention_days, now))
                conn.commit()

        ActivityLogger.log(
            component="memory",
            action="update_privacy_settings",
            target_resource="memory_privacy_settings",
            approval_status="USER_APPROVED",
            execution_status="SUCCESS",
            result_summary=f"Memory recording {'enabled' if recording_enabled else 'disabled'}"
        )
        return cls.get_privacy_settings()

    @classmethod
    def add_memory_with_source(
        cls,
        category: str,
        content: str,
        key: Optional[str] = None,
        tags: Optional[List[str]] = None,
        source_type: str = "explicit_instruction",
        source_url: Optional[str] = None,
        source_reference: Optional[str] = None,
        confidence: float = 1.0,
        is_important: bool = False
    ) -> Optional[str]:
        """
        Adds a memory node with full source attribution, respecting user privacy settings.
        """
        settings_data = cls.get_privacy_settings()
        if not settings_data["recording_enabled"]:
            return None

        if category in settings_data["excluded_categories"]:
            return None

        # Check sensitive keywords
        content_lower = content.lower()
        for kw in settings_data["sensitive_keywords"]:
            if kw.lower() in content_lower:
                return None

        mem_id = f"mem_{uuid.uuid4().hex[:12]}"
        now = time.time()
        tags_json = json.dumps(tags or [], ensure_ascii=False)

        with _mem_lock:
            with sqlite3.connect(str(DB_PATH)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO memory_nodes (
                        id, category, key, content, tags, confidence, source,
                        created_at, updated_at, source_type, source_url,
                        source_reference, is_important, is_deleted, access_count
                    ) VALUES (?, ?, ?, ?, ?, ?, 'user', ?, ?, ?, ?, ?, ?, 0, 0);
                """, (
                    mem_id, category, key, content, tags_json, confidence,
                    now, now, source_type, source_url, source_reference,
                    1 if is_important else 0
                ))

                # Sync to FTS5
                try:
                    cursor.execute("""
                        INSERT INTO memory_fts (id, category, key, content, tags)
                        VALUES (?, ?, ?, ?, ?);
                    """, (mem_id, category, key or "", content, tags_json))
                except Exception:
                    pass
                conn.commit()

        ActivityLogger.log(
            component="memory",
            action="add_memory",
            target_resource=mem_id,
            approval_status="AUTO_APPROVED",
            execution_status="SUCCESS",
            result_summary=f"Saved memory [{category}] via {source_type}"
        )
        return mem_id

    @classmethod
    def record_access(cls, memory_id: str, component: str, context_summary: str, task_id: Optional[str] = None):
        """Records an access log entry when a memory is retrieved by an AI routine."""
        acc_id = f"acc_{uuid.uuid4().hex[:10]}"
        now = time.time()

        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memory_access_log (access_id, memory_id, accessed_at, task_id, component, context_summary)
                VALUES (?, ?, ?, ?, ?, ?);
            """, (acc_id, memory_id, now, task_id, component, context_summary))

            cursor.execute("""
                UPDATE memory_nodes
                SET last_accessed_at = ?, access_count = access_count + 1
                WHERE id = ?;
            """, (now, memory_id))
            conn.commit()

    @classmethod
    def get_timeline(
        cls,
        category: Optional[str] = None,
        source_type: Optional[str] = None,
        search: Optional[str] = None,
        is_important: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Chronological timeline feed with source tracking and total counts.
        """
        conditions = ["is_deleted = 0"]
        params: List[Any] = []

        if category and category != "all":
            conditions.append("category = ?")
            params.append(category)

        if source_type and source_type != "all":
            conditions.append("source_type = ?")
            params.append(source_type)

        if is_important is not None:
            conditions.append("is_important = ?")
            params.append(1 if is_important else 0)

        if search and search.strip():
            pat = f"%{search.strip()}%"
            conditions.append("(content LIKE ? OR key LIKE ? OR tags LIKE ?)")
            params.extend([pat, pat, pat])

        where_clause = f"WHERE {' AND '.join(conditions)}"

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(f"SELECT COUNT(*) FROM memory_nodes {where_clause};", params)
            total = cursor.fetchone()[0]

            query = f"""
                SELECT * FROM memory_nodes
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?;
            """
            cursor.execute(query, params + [limit, offset])
            rows = cursor.fetchall()

        memories = []
        for r in rows:
            d = dict(r)
            try:
                d["tags"] = json.loads(d["tags"])
            except Exception:
                d["tags"] = []
            d["is_important"] = bool(d.get("is_important", 0))
            memories.append(d)

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "timeline": memories
        }

    @classmethod
    def get_memory_history(cls, memory_id: str) -> Dict[str, Any]:
        """Returns details and all access logs for a specific memory."""
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM memory_nodes WHERE id = ?;", (memory_id,))
            mem_row = cursor.fetchone()
            if not mem_row:
                return {"status": "ERROR", "error": "Memory not found."}

            mem_data = dict(mem_row)
            try:
                mem_data["tags"] = json.loads(mem_data["tags"])
            except Exception:
                mem_data["tags"] = []

            cursor.execute("SELECT * FROM memory_access_log WHERE memory_id = ? ORDER BY accessed_at DESC;", (memory_id,))
            access_logs = [dict(r) for r in cursor.fetchall()]

        return {
            "status": "SUCCESS",
            "memory": mem_data,
            "access_count": len(access_logs),
            "access_logs": access_logs
        }

    @classmethod
    def update_memory_inplace(
        cls,
        memory_id: str,
        content: str,
        key: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_important: Optional[bool] = None
    ) -> bool:
        """Performs true in-place update of memory content and tags."""
        now = time.time()
        tags_json = json.dumps(tags or [], ensure_ascii=False) if tags is not None else None

        with _mem_lock:
            with sqlite3.connect(str(DB_PATH)) as conn:
                cursor = conn.cursor()
                updates = ["content = ?", "updated_at = ?"]
                params: List[Any] = [content, now]

                if key is not None:
                    updates.append("key = ?")
                    params.append(key)
                if tags_json is not None:
                    updates.append("tags = ?")
                    params.append(tags_json)
                if is_important is not None:
                    updates.append("is_important = ?")
                    params.append(1 if is_important else 0)

                params.append(memory_id)
                sql = f"UPDATE memory_nodes SET {', '.join(updates)} WHERE id = ?;"
                cursor.execute(sql, params)
                affected = cursor.rowcount > 0

                # Update FTS5
                if affected:
                    try:
                        cursor.execute("DELETE FROM memory_fts WHERE id = ?;", (memory_id,))
                        cursor.execute("""
                            INSERT INTO memory_fts (id, category, key, content, tags)
                            SELECT id, category, key, content, tags FROM memory_nodes WHERE id = ?;
                        """, (memory_id,))
                    except Exception:
                        pass
                conn.commit()

        if affected:
            ActivityLogger.log(
                component="memory",
                action="update_memory",
                target_resource=memory_id,
                approval_status="USER_APPROVED",
                execution_status="SUCCESS",
                result_summary=f"In-place updated memory {memory_id}"
            )
        return affected

    @classmethod
    def delete_memory_permanent(cls, memory_id: str) -> bool:
        """Permanently purges a memory node and its access log entries."""
        with _mem_lock:
            with sqlite3.connect(str(DB_PATH)) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM memory_nodes WHERE id = ?;", (memory_id,))
                affected = cursor.rowcount > 0

                cursor.execute("DELETE FROM memory_access_log WHERE memory_id = ?;", (memory_id,))
                try:
                    cursor.execute("DELETE FROM memory_fts WHERE id = ?;", (memory_id,))
                except Exception:
                    pass
                conn.commit()

        if affected:
            ActivityLogger.log(
                component="memory",
                action="delete_memory_permanent",
                target_resource=memory_id,
                approval_status="USER_APPROVED",
                execution_status="SUCCESS",
                result_summary=f"Permanently purged memory {memory_id}"
            )
        return affected

    @classmethod
    def clear_category(cls, category: str) -> int:
        """Bulk purges all memories belonging to a specific category."""
        with _mem_lock:
            with sqlite3.connect(str(DB_PATH)) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM memory_nodes WHERE category = ?;", (category,))
                count = cursor.rowcount
                try:
                    cursor.execute("DELETE FROM memory_fts WHERE category = ?;", (category,))
                except Exception:
                    pass
                conn.commit()

        ActivityLogger.log(
            component="memory",
            action="clear_category",
            target_resource=category,
            approval_status="USER_APPROVED",
            execution_status="SUCCESS",
            result_summary=f"Purged {count} memories from category '{category}'"
        )
        return count
