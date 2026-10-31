"""
Skill Validator for JARVIS-APEX Skills System.
Validates manifest.json, SKILL.md, and conducts AST security audits on executable scripts.
"""

import ast
from pathlib import Path
from typing import Dict, Any, List, Tuple
from .skill_types import SkillType

BANNED_MODULES = {
    "ctypes", "winreg", "_winapi", "subprocess.Popen", "pty"
}

BANNED_FUNCTIONS = {
    "eval", "exec", "__import__", "globals", "locals"
}

class SkillValidator:
    """
    Validates skill directory integrity and performs static analysis on script assets.
    """

    @classmethod
    def validate_manifest(cls, manifest_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Checks required fields and types in manifest.json."""
        errors = []
        required_fields = ["id", "name", "version", "type", "description"]
        for f in required_fields:
            if not manifest_dict.get(f):
                errors.append(f"Missing required manifest field: '{f}'")

        skill_type = manifest_dict.get("type")
        if skill_type not in [e.value for e in SkillType]:
            errors.append(f"Invalid skill type: '{skill_type}'. Must be one of {[e.value for e in SkillType]}")

        if skill_type in [SkillType.SCRIPT_ENABLED.value, SkillType.TOOL_BASED.value]:
            if not manifest_dict.get("entrypoint"):
                errors.append("Script-enabled or tool-based skill must specify an 'entrypoint' path.")

        return len(errors) == 0, errors

    @classmethod
    def audit_script_security(cls, script_path: Path) -> Tuple[bool, List[str]]:
        """
        Uses Python AST parsing to verify that scripts do not contain dangerous primitives.
        """
        if not script_path.exists():
            return False, [f"Script file not found: {script_path}"]

        try:
            content = script_path.read_text(encoding="utf-8")
            tree = ast.parse(content, filename=str(script_path))
        except SyntaxError as e:
            return False, [f"Syntax error in script: {e}"]
        except Exception as e:
            return False, [f"Failed to read/parse script: {e}"]

        warnings = []
        for node in ast.walk(tree):
            # Check imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in BANNED_MODULES:
                        warnings.append(f"Disallowed module import detected: '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                if node.module in BANNED_MODULES:
                    warnings.append(f"Disallowed module import detected: '{node.module}'")

            # Check dangerous builtins
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in BANNED_FUNCTIONS:
                        warnings.append(f"Disallowed built-in function invocation: '{node.func.id}()'")

        return len(warnings) == 0, warnings

    @classmethod
    def validate_skill_directory(cls, dir_path: Path) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Full directory audit for skill packaging:
        Checks manifest.json, SKILL.md, entrypoint, references/, examples/.
        """
        errors = []
        if not dir_path.is_dir():
            return False, [f"Specified path is not a directory: {dir_path}"], {}

        manifest_file = dir_path / "manifest.json"
        skill_md_file = dir_path / "SKILL.md"

        if not manifest_file.exists():
            errors.append("manifest.json is missing.")
            return False, errors, {}

        if not skill_md_file.exists():
            errors.append("SKILL.md documentation is missing.")

        manifest_data = {}
        try:
            import json
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
        except Exception as e:
            errors.append(f"manifest.json is not valid JSON: {e}")
            return False, errors, {}

        valid_manifest, manifest_errs = cls.validate_manifest(manifest_data)
        errors.extend(manifest_errs)

        # Audit script if entrypoint declared
        entrypoint = manifest_data.get("entrypoint")
        if entrypoint:
            script_full = dir_path / entrypoint
            if not script_full.exists():
                errors.append(f"Declared entrypoint does not exist: {entrypoint}")
            elif script_full.suffix == ".py":
                safe, script_warnings = cls.audit_script_security(script_full)
                if not safe:
                    errors.extend(script_warnings)

        return len(errors) == 0, errors, manifest_data
