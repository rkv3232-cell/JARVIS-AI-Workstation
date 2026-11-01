"""
Skill Loader for discovering and indexing skills in JARVIS-APEX.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..config import settings
from .skill_types import SkillManifest, SkillType
from .skill_validator import SkillValidator

SKILLS_ROOT = settings.BASE_DIR / "skills"

class SkillLoader:
    """Discovers skills across the skills/ workspace directory."""

    @classmethod
    def discover_skills(cls, root_dir: Optional[Path] = None) -> List[SkillManifest]:
        root = root_dir or SKILLS_ROOT
        if not root.exists():
            root.mkdir(parents=True, exist_ok=True)
            return []

        discovered: List[SkillManifest] = []

        # Walk through subdirectories
        for item in root.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                manifest_path = item / "manifest.json"
                if manifest_path.exists():
                    is_valid, errs, m_data = SkillValidator.validate_skill_directory(item)
                    if is_valid:
                        try:
                            manifest = SkillManifest(
                                id=m_data["id"],
                                name=m_data["name"],
                                version=m_data.get("version", "1.0.0"),
                                type=SkillType(m_data.get("type", "instruction_only")),
                                description=m_data.get("description", ""),
                                author=m_data.get("author", "JARVIS Core"),
                                entrypoint=m_data.get("entrypoint"),
                                permissions_required=m_data.get("permissions_required", []),
                                parameters_schema=m_data.get("parameters_schema", {}),
                                returns_schema=m_data.get("returns_schema", {}),
                                tags=m_data.get("tags", []),
                                is_enabled=m_data.get("is_enabled", True),
                                directory_path=str(item.resolve())
                            )
                            discovered.append(manifest)
                        except Exception as parse_err:
                            print(f"[SkillLoader Error]: Failed to construct model for {item.name}: {parse_err}")
                    else:
                        print(f"[SkillLoader Warning]: Skipping invalid skill folder {item.name}: {errs}")

        return discovered

