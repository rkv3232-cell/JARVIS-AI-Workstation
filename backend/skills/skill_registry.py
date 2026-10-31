"""
Skill Registry for managing persistent registration, enabling/disabling,
installation, and execution history in SQLite.
"""

import json
import time
import shutil
import sqlite3
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from ..config import settings
from .skill_types import SkillManifest, SkillType, SkillResult
from .skill_loader import SkillLoader, SKILLS_ROOT
from .skill_validator import SkillValidator
from ..activity import ActivityLogger

DB_PATH = Path(__file__).resolve().parent.parent / "jarvis.db"
_registry_lock = threading.Lock()

class SkillRegistry:
    """Manages the lifecycle and state of all installed JARVIS skills."""

    @classmethod
    def sync_with_filesystem(cls) -> int:
        """
        Discovers all valid skills on disk and updates the SQLite registry,
        preserving user's enabled/disabled preferences.
        """
        discovered = SkillLoader.discover_skills()
        now = time.time()
        synced_count = 0

        with _registry_lock:
            with sqlite3.connect(str(DB_PATH)) as conn:
                cursor = conn.cursor()
                for skill in discovered:
                    # Check if skill already exists in DB to preserve is_enabled
                    cursor.execute("SELECT is_enabled, created_at FROM skills_registry WHERE id = ?;", (skill.id,))
                    row = cursor.fetchone()
                    is_enabled = row[0] if row else (1 if skill.is_enabled else 0)
                    created_at = row[1] if row else now

                    cursor.execute("""
                        INSERT OR REPLACE INTO skills_registry (
                            id, name, version, skill_type, description, author,
                            directory_path, is_enabled, manifest_json, permissions_required,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """, (
                        skill.id, skill.name, skill.version, skill.type.value,
                        skill.description, skill.author, skill.directory_path,
                        is_enabled, skill.model_dump_json(),
                        json.dumps(skill.permissions_required),
                        created_at, now
                    ))
                    synced_count += 1
                conn.commit()

        return synced_count

    @classmethod
    def list_skills(cls, enabled_only: bool = False, skill_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves all registered skills from SQLite."""
        cls.sync_with_filesystem()

        conditions = []
        params = []
        if enabled_only:
            conditions.append("is_enabled = 1")
        if skill_type and skill_type != "all":
            conditions.append("skill_type = ?")
            params.append(skill_type)

        query = "SELECT * FROM skills_registry"
        if conditions:
            query += f" WHERE {' AND '.join(conditions)}"
        query += " ORDER BY name ASC;"

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        skills = []
        for r in rows:
            d = dict(r)
            d["is_enabled"] = bool(d["is_enabled"])
            try:
                d["manifest"] = json.loads(d["manifest_json"])
            except Exception:
                d["manifest"] = {}
            try:
                d["permissions_required"] = json.loads(d["permissions_required"])
            except Exception:
                d["permissions_required"] = []
            skills.append(d)

        return skills

    @classmethod
    def get_skill(cls, skill_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves single skill details and documentation."""
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM skills_registry WHERE id = ?;", (skill_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            d["is_enabled"] = bool(d["is_enabled"])
            try:
                d["manifest"] = json.loads(d["manifest_json"])
            except Exception:
                d["manifest"] = {}

        # Read SKILL.md documentation if directory exists
        dir_p = Path(d["directory_path"])
        skill_md = dir_p / "SKILL.md"
        d["skill_md"] = skill_md.read_text(encoding="utf-8") if skill_md.exists() else ""

        # Read references list and examples list
        ref_dir = dir_p / "references"
        ex_dir = dir_p / "examples"
        d["references"] = [f.name for f in ref_dir.iterdir() if f.is_file()] if ref_dir.is_dir() else []
        d["examples"] = [f.name for f in ex_dir.iterdir() if f.is_file()] if ex_dir.is_dir() else []

        return d

    @classmethod
    def set_skill_enabled(cls, skill_id: str, enabled: bool) -> bool:
        """Enables or disables a registered skill."""
        with _registry_lock:
            with sqlite3.connect(str(DB_PATH)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE skills_registry SET is_enabled = ?, updated_at = ? WHERE id = ?;
                """, (1 if enabled else 0, time.time(), skill_id))
                affected = cursor.rowcount > 0
                conn.commit()

        if affected:
            ActivityLogger.log(
                component="skills",
                action="toggle_skill",
                target_resource=skill_id,
                approval_status="USER_APPROVED",
                execution_status="SUCCESS",
                result_summary=f"Skill '{skill_id}' {'enabled' if enabled else 'disabled'}"
            )
        return affected

    @classmethod
    def install_skill_from_folder(cls, source_folder: Path) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Validates and copies a local skill folder into the skills/ directory,
        then registers it in SQLite.
        """
        is_valid, errors, manifest_data = SkillValidator.validate_skill_directory(source_folder)
        if not is_valid:
            return False, f"Skill validation failed: {'; '.join(errors)}", None

        skill_id = manifest_data["id"]
        dest_folder = SKILLS_ROOT / skill_id

        try:
            if dest_folder.exists():
                shutil.rmtree(dest_folder)
            shutil.copytree(source_folder, dest_folder)
            cls.sync_with_filesystem()
            installed = cls.get_skill(skill_id)

            ActivityLogger.log(
                component="skills",
                action="install_skill",
                target_resource=skill_id,
                approval_status="USER_APPROVED",
                execution_status="SUCCESS",
                result_summary=f"Skill '{manifest_data['name']}' ({skill_id}) installed successfully."
            )
            return True, "Skill installed successfully.", installed
        except Exception as e:
            return False, f"Failed to copy skill files: {e}", None

    @classmethod
    def uninstall_skill(cls, skill_id: str) -> Tuple[bool, str]:
        """Removes a skill from disk and deregisters it."""
        skill = cls.get_skill(skill_id)
        if not skill:
            return False, "Skill not found."

        dir_path = Path(skill["directory_path"])
        with _registry_lock:
            with sqlite3.connect(str(DB_PATH)) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM skills_registry WHERE id = ?;", (skill_id,))
                conn.commit()

        try:
            if dir_path.exists() and SKILLS_ROOT in dir_path.resolve().parents:
                shutil.rmtree(dir_path)
        except Exception as e:
            print(f"[SkillRegistry Warning] Cleanup folder: {e}")

        ActivityLogger.log(
            component="skills",
            action="uninstall_skill",
            target_resource=skill_id,
            approval_status="USER_APPROVED",
            execution_status="SUCCESS",
            result_summary=f"Skill '{skill_id}' uninstalled."
        )
        return True, "Skill uninstalled successfully."

    @classmethod
    def record_execution(
        cls,
        skill_id: str,
        input_data: Any,
        output_data: Any,
        status: str,
        duration_ms: float,
        error: Optional[str] = None
    ) -> str:
        """Appends a skill execution event to skill_execution_history."""
        import uuid
        exec_id = f"skex_{uuid.uuid4().hex[:10]}"
        now = time.time()

        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO skill_execution_history (
                    id, skill_id, input_json, output_json, status, execution_time_ms, executed_at, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                exec_id, skill_id,
                json.dumps(input_data, ensure_ascii=False) if input_data else None,
                json.dumps(output_data, ensure_ascii=False) if output_data else None,
                status, duration_ms, now, error
            ))
            conn.commit()

        return exec_id

    @classmethod
    def get_execution_history(cls, skill_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves recent execution runs for skills."""
        query = "SELECT * FROM skill_execution_history"
        params = []
        if skill_id:
            query += " WHERE skill_id = ?"
            params.append(skill_id)
        query += " ORDER BY executed_at DESC LIMIT ?;"
        params.append(limit)

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        history = []
        for r in rows:
            d = dict(r)
            try:
                d["input"] = json.loads(d["input_json"]) if d.get("input_json") else None
            except Exception:
                d["input"] = None
            try:
                d["output"] = json.loads(d["output_json"]) if d.get("output_json") else None
            except Exception:
                d["output"] = None
            history.append(d)

        return history
