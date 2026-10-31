import os
import json
import time
import uuid
import queue
import sqlite3
import threading
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..config import settings
from ..security import log_audit_event, redact_secrets

DB_PATH = Path(__file__).resolve().parent.parent / "jarvis.db"

class MemoryCategory(str, Enum):
    CONVERSATION_HISTORY = "conversation_history"
    USER_PREFERENCES = "user_preferences"
    USER_APPROVED_MEMORIES = "user_approved_memories"
    PROJECT_MEMORY = "project_memory"
    RESEARCH_KNOWLEDGE = "research_knowledge"
    TRADING_JOURNAL = "trading_journal"
    ACTION_AUDIT = "action_audit"

CURRENT_SCHEMA_VERSION = 2

def apply_migrations():
    """Applies SQLite schema migrations using PRAGMA user_version."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version;")
        ver = cursor.fetchone()[0]

        if ver < 1:
            # Main persistent memory table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS memory_nodes (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    key TEXT,
                    content TEXT NOT NULL,
                    tags TEXT,
                    confidence REAL DEFAULT 1.0,
                    source TEXT DEFAULT 'user',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_category ON memory_nodes(category);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_memory_created ON memory_nodes(created_at);")

            # Persistent Research Jobs Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS research_jobs (
                    job_id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL, -- PENDING, RUNNING, COMPLETED, FAILED
                    progress INTEGER DEFAULT 0,
                    current_step TEXT,
                    result_json TEXT,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
            """)

        if ver < 2:
            # FTS5 Full-Text Search Virtual Table
            try:
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                        id UNINDEXED,
                        category,
                        key,
                        content,
                        tags
                    );
                """)
            except Exception as e:
                print(f"[MemoryBrain Migration] FTS5 setup note: {e}")

        cursor.execute(f"PRAGMA user_version = {CURRENT_SCHEMA_VERSION};")
        conn.commit()

apply_migrations()

# =========================================================================
# BOUNDED BACKGROUND CLOUD SYNC WORKER (Firebase / Cloud Store)
# =========================================================================
_sync_queue: queue.Queue = queue.Queue(maxsize=100)

def _cloud_sync_worker():
    """Consumes background sync queue without blocking main API or SQLite loops."""
    while True:
        try:
            item = _sync_queue.get()
            if item is None:
                break
            # Optional Firebase write attempt if credentials configured
            if settings.FIREBASE_CREDENTIALS_PATH and os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
                try:
                    import firebase_admin
                    from firebase_admin import firestore
                    db = firestore.client()
                    col = item.get("category", "general_memory")
                    doc_id = item.get("id")
                    db.collection(col).document(doc_id).set(item, merge=True)
                except Exception as fb_err:
                    pass  # Non-blocking; local SQLite remains source of truth
            _sync_queue.task_done()
        except Exception:
            time.sleep(1.0)

_sync_thread = threading.Thread(target=_cloud_sync_worker, daemon=True)
_sync_thread.start()

class PersistentMemoryBrain:
    """
    Centralized 7-Category Knowledge and Persistent Memory Subsystem.
    Provides fast FTS5 search, CRUD controls, schema migrations, and JSON import/export.
    """
    @classmethod
    def add_memory(
        cls,
        category: MemoryCategory,
        content: str,
        key: Optional[str] = None,
        tags: Optional[List[str]] = None,
        confidence: float = 1.0,
        source: str = "user"
    ) -> str:
        mem_id = f"mem_{uuid.uuid4().hex[:12]}"
        now = time.time()
        tags_json = json.dumps(tags or [], ensure_ascii=False)

        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO memory_nodes (id, category, key, content, tags, confidence, source, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (mem_id, category.value, key, content, tags_json, confidence, source, now, now))

            # Sync to FTS5
            try:
                cursor.execute("""
                    INSERT INTO memory_fts (id, category, key, content, tags)
                    VALUES (?, ?, ?, ?, ?);
                """, (mem_id, category.value, key or "", content, tags_json))
            except Exception:
                pass
            conn.commit()

        # Enqueue for non-blocking cloud sync
        try:
            _sync_queue.put_nowait({
                "id": mem_id,
                "category": category.value,
                "key": key,
                "content": content,
                "tags": tags or [],
                "created_at": now
            })
        except queue.Full:
            pass

        log_audit_event("add_memory", f"{category.value}: {mem_id}", "safe", "success")
        return mem_id

    @classmethod
    def get_memories(
        cls,
        category: Optional[MemoryCategory] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if category:
                cursor.execute("""
                    SELECT * FROM memory_nodes WHERE category = ? ORDER BY created_at DESC LIMIT ? OFFSET ?;
                """, (category.value, limit, offset))
            else:
                cursor.execute("""
                    SELECT * FROM memory_nodes ORDER BY created_at DESC LIMIT ? OFFSET ?;
                """, (limit, offset))
            rows = cursor.fetchall()

        results = []
        for r in rows:
            d = dict(r)
            try:
                d["tags"] = json.loads(d["tags"])
            except Exception:
                d["tags"] = []
            results.append(d)
        return results

    @classmethod
    def search_memories(
        cls,
        query: str,
        category: Optional[MemoryCategory] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Fast full-text search across all memories using FTS5 with fallback to LIKE.
        """
        clean_q = query.strip()
        if not clean_q:
            return cls.get_memories(category, limit=limit)

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            results = []

            # 1. Attempt FTS5 match
            try:
                # Sanitize query for FTS5 (remove special syntax characters)
                safe_fts = ' '.join(f'"{w}"' for w in clean_q.split() if w.isalnum())
                if safe_fts:
                    if category:
                        cursor.execute("""
                            SELECT m.* FROM memory_fts f
                            JOIN memory_nodes m ON f.id = m.id
                            WHERE memory_fts MATCH ? AND m.category = ?
                            LIMIT ?;
                        """, (safe_fts, category.value, limit))
                    else:
                        cursor.execute("""
                            SELECT m.* FROM memory_fts f
                            JOIN memory_nodes m ON f.id = m.id
                            WHERE memory_fts MATCH ?
                            LIMIT ?;
                        """, (safe_fts, limit))
                    rows = cursor.fetchall()
                    for r in rows:
                        d = dict(r)
                        try:
                            d["tags"] = json.loads(d["tags"])
                        except Exception:
                            d["tags"] = []
                        results.append(d)
            except Exception:
                pass

            # 2. Fallback to SQL LIKE if FTS yielded no results
            if not results:
                like_pat = f"%{clean_q}%"
                if category:
                    cursor.execute("""
                        SELECT * FROM memory_nodes
                        WHERE category = ? AND (content LIKE ? OR key LIKE ? OR tags LIKE ?)
                        ORDER BY created_at DESC LIMIT ?;
                    """, (category.value, like_pat, like_pat, like_pat, limit))
                else:
                    cursor.execute("""
                        SELECT * FROM memory_nodes
                        WHERE content LIKE ? OR key LIKE ? OR tags LIKE ?
                        ORDER BY created_at DESC LIMIT ?;
                    """, (like_pat, like_pat, like_pat, limit))
                for r in cursor.fetchall():
                    d = dict(r)
                    try:
                        d["tags"] = json.loads(d["tags"])
                    except Exception:
                        d["tags"] = []
                    results.append(d)

        return results

    @classmethod
    def update_memory(cls, memory_id: str, new_content: str, tags: Optional[List[str]] = None) -> bool:
        now = time.time()
        tags_json = json.dumps(tags or [], ensure_ascii=False) if tags is not None else None

        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            if tags is not None:
                cursor.execute("""
                    UPDATE memory_nodes SET content = ?, tags = ?, updated_at = ? WHERE id = ?;
                """, (new_content, tags_json, now, memory_id))
            else:
                cursor.execute("""
                    UPDATE memory_nodes SET content = ?, updated_at = ? WHERE id = ?;
                """, (new_content, now, memory_id))
            affected = cursor.rowcount > 0
            conn.commit()

        log_audit_event("update_memory", memory_id, "safe", "success" if affected else "not_found")
        return affected

    @classmethod
    def delete_memory(cls, memory_id: str) -> bool:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM memory_nodes WHERE id = ?;", (memory_id,))
            affected = cursor.rowcount > 0
            try:
                cursor.execute("DELETE FROM memory_fts WHERE id = ?;", (memory_id,))
            except Exception:
                pass
            conn.commit()

        log_audit_event("delete_memory", memory_id, "high", "success" if affected else "not_found")
        return affected

    @classmethod
    def export_all_memories(cls) -> Dict[str, Any]:
        """Exports complete persistent memory dataset for user backup and privacy auditing."""
        all_mems = cls.get_memories(limit=5000)
        return {
            "version": CURRENT_SCHEMA_VERSION,
            "export_time": time.time(),
            "export_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_memories": len(all_mems),
            "memories": all_mems
        }

    @classmethod
    def import_memories(cls, data: Dict[str, Any]) -> int:
        """Restores memories from exported JSON payload."""
        items = data.get("memories", [])
        imported = 0
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            for it in items:
                mid = it.get("id") or f"mem_{uuid.uuid4().hex[:12]}"
                cat = it.get("category", "general_memory")
                k = it.get("key")
                cnt = it.get("content", "")
                tags = json.dumps(it.get("tags", []))
                conf = float(it.get("confidence", 1.0))
                src = it.get("source", "import")
                now = time.time()

                cursor.execute("""
                    INSERT OR REPLACE INTO memory_nodes (id, category, key, content, tags, confidence, source, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """, (mid, cat, k, cnt, tags, conf, src, now, now))
                imported += 1
            conn.commit()
        log_audit_event("import_memories", f"Count: {imported}", "high", "success")
        return imported

    # =========================================================================
    # PERSISTENT DEEP RESEARCH JOBS
    # =========================================================================
    @classmethod
    def create_research_job(cls, topic: str, mode: str = "DEEP") -> str:
        job_id = f"res_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO research_jobs (job_id, topic, mode, status, progress, current_step, result_json, error, created_at, updated_at)
                VALUES (?, ?, ?, 'PENDING', 0, 'Job initialized', NULL, NULL, ?, ?);
            """, (job_id, topic, mode, now, now))
            conn.commit()
        return job_id

    @classmethod
    def update_research_job(
        cls,
        job_id: str,
        progress: int,
        step: str,
        status: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        now = time.time()
        res_str = json.dumps(result, ensure_ascii=False) if result else None
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            if status and res_str:
                cursor.execute("""
                    UPDATE research_jobs
                    SET progress = ?, current_step = ?, status = ?, result_json = ?, error = ?, updated_at = ?
                    WHERE job_id = ?;
                """, (progress, step, status, res_str, error, now, job_id))
            elif status:
                cursor.execute("""
                    UPDATE research_jobs
                    SET progress = ?, current_step = ?, status = ?, error = ?, updated_at = ?
                    WHERE job_id = ?;
                """, (progress, step, status, error, now, job_id))
            else:
                cursor.execute("""
                    UPDATE research_jobs
                    SET progress = ?, current_step = ?, updated_at = ?
                    WHERE job_id = ?;
                """, (progress, step, now, job_id))
            conn.commit()

    @classmethod
    def get_research_job(cls, job_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM research_jobs WHERE job_id = ?;", (job_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            if d.get("result_json"):
                try:
                    d["result"] = json.loads(d["result_json"])
                except Exception:
                    d["result"] = None
            return d

    @classmethod
    def list_research_jobs(cls, limit: int = 20) -> List[Dict[str, Any]]:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT job_id, topic, mode, status, progress, current_step, error, created_at, updated_at FROM research_jobs ORDER BY created_at DESC LIMIT ?;", (limit,))
            return [dict(r) for r in cursor.fetchall()]

