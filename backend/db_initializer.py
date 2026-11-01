"""
Database schema migrations and initialization for JARVIS-APEX 7 Core Architecture Components.
Manages SQLite tables in backend/jarvis.db.
"""

import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "jarvis.db"

def init_seven_components_db():
    """
    Initializes database tables and migrates schemas for the 7 Core Components:
    1. AI Browser Operator (bookmarks, history, downloads)
    2. Skills System (registry, execution history)
    3. Central Permission Manager (permissions, grants)
    4. Skill Collaboration Engine (collaboration_tasks, collaboration_steps)
    5. Unified Activity Log (activity_logs)
    6. Memory Timeline & Privacy (memory_access_log, privacy_settings, memory_nodes columns)
    """
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # ---------------------------------------------------------
    # 1. AI Browser Operator
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS browser_bookmarks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            url TEXT NOT NULL,
            folder TEXT DEFAULT 'default',
            tags TEXT,
            created_at REAL NOT NULL
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bm_url ON browser_bookmarks(url);")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS browser_history (
            id TEXT PRIMARY KEY,
            tab_id TEXT,
            title TEXT,
            url TEXT NOT NULL,
            visited_at REAL NOT NULL,
            transition_type TEXT DEFAULT 'link'
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_hist_visited ON browser_history(visited_at);")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS browser_downloads (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            url TEXT NOT NULL,
            file_path TEXT NOT NULL,
            size_bytes INTEGER DEFAULT 0,
            status TEXT DEFAULT 'COMPLETED',
            downloaded_at REAL NOT NULL
        );
    """)

    # ---------------------------------------------------------
    # 2. Central Permission Manager
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS permission_grants (
            id TEXT PRIMARY KEY,
            component TEXT NOT NULL,
            resource TEXT NOT NULL,
            level TEXT NOT NULL, -- READ, WRITE, EXECUTE, SENSITIVE
            is_persistent INTEGER DEFAULT 0,
            granted_at REAL NOT NULL,
            expires_at REAL,
            granted_by TEXT DEFAULT 'user',
            notes TEXT
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_perm_lookup ON permission_grants(component, resource);")

    # ---------------------------------------------------------
    # 3. Skills System & Registry
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skills_registry (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version TEXT NOT NULL,
            skill_type TEXT NOT NULL, -- instruction_only, tool_based, script_enabled
            description TEXT,
            author TEXT,
            directory_path TEXT NOT NULL,
            is_enabled INTEGER DEFAULT 1,
            manifest_json TEXT NOT NULL,
            permissions_required TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS skill_execution_history (
            id TEXT PRIMARY KEY,
            skill_id TEXT NOT NULL,
            input_json TEXT,
            output_json TEXT,
            status TEXT NOT NULL, -- SUCCESS, FAILED, TIMEOUT, DENIED
            execution_time_ms REAL NOT NULL,
            executed_at REAL NOT NULL,
            error TEXT
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_skill_exec_time ON skill_execution_history(executed_at);")

    # ---------------------------------------------------------
    # 4. Skill Collaboration Engine
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collaboration_tasks (
            task_id TEXT PRIMARY KEY,
            objective TEXT NOT NULL,
            status TEXT NOT NULL, -- PLANNED, RUNNING, PAUSED, COMPLETED, FAILED, CANCELLED
            plan_json TEXT NOT NULL,
            current_step INTEGER DEFAULT 0,
            output_json TEXT,
            error TEXT,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collaboration_steps (
            step_id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            step_index INTEGER NOT NULL,
            skill_id TEXT NOT NULL,
            action_name TEXT NOT NULL,
            input_json TEXT,
            output_json TEXT,
            status TEXT NOT NULL, -- PENDING, RUNNING, COMPLETED, FAILED, SKIPPED
            started_at REAL,
            completed_at REAL,
            error TEXT
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_collab_steps_task ON collaboration_steps(task_id);")

    # ---------------------------------------------------------
    # 5. Unified Activity Log
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            event_id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            epoch REAL NOT NULL,
            component TEXT NOT NULL, -- browser, skills, permissions, collaboration, memory, os, system
            action TEXT NOT NULL,
            user_request TEXT,
            target_resource TEXT,
            approval_status TEXT NOT NULL, -- AUTO_APPROVED, USER_APPROVED, PENDING, DENIED
            execution_status TEXT NOT NULL, -- SUCCESS, FAILED, SKIPPED, IN_PROGRESS
            result_summary TEXT,
            error_info TEXT,
            task_id TEXT,
            metadata_json TEXT
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_act_epoch ON activity_logs(epoch);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_act_component ON activity_logs(component);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_act_status ON activity_logs(execution_status);")

    # ---------------------------------------------------------
    # 6. Memory Timeline & Transparency Engine
    # ---------------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_access_log (
            access_id TEXT PRIMARY KEY,
            memory_id TEXT NOT NULL,
            accessed_at REAL NOT NULL,
            task_id TEXT,
            component TEXT NOT NULL,
            context_summary TEXT
        );
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_mem_access ON memory_access_log(memory_id);")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memory_privacy_settings (
            id TEXT PRIMARY KEY,
            recording_enabled INTEGER DEFAULT 1,
            excluded_categories TEXT, -- JSON array
            sensitive_keywords TEXT, -- JSON array
            retention_days INTEGER DEFAULT 0,
            updated_at REAL NOT NULL
        );
    """)

    # Seed default privacy settings if not present
    cursor.execute("SELECT id FROM memory_privacy_settings WHERE id = 'default';")
    if not cursor.fetchone():
        cursor.execute("""
            INSERT INTO memory_privacy_settings (id, recording_enabled, excluded_categories, sensitive_keywords, retention_days, updated_at)
            VALUES ('default', 1, '[]', '[]', 0, ?);
        """, (time.time(),))

    # Migration on memory_nodes: add columns if they don't exist
    cursor.execute("PRAGMA table_info(memory_nodes);")
    existing_cols = {col[1] for col in cursor.fetchall()}

    new_cols = [
        ("source_type", "TEXT DEFAULT 'explicit_instruction'"),
        ("source_url", "TEXT DEFAULT NULL"),
        ("source_reference", "TEXT DEFAULT NULL"),
        ("is_important", "INTEGER DEFAULT 0"),
        ("is_deleted", "INTEGER DEFAULT 0"),
        ("last_accessed_at", "REAL DEFAULT NULL"),
        ("access_count", "INTEGER DEFAULT 0"),
    ]

    for col_name, col_def in new_cols:
        if col_name not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE memory_nodes ADD COLUMN {col_name} {col_def};")
            except Exception as e:
                print(f"[Migration Warning] Add column {col_name}: {e}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_seven_components_db()
    print("Database initialization and migration completed successfully.")

