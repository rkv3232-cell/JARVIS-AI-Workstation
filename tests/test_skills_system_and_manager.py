"""
Unit and integration tests for Components 2 & 3: Skills System and Skill Manager.
Tests discovery, AST security validation, execution of skills, and registry management.
"""

import pytest
import asyncio
from pathlib import Path

from backend.skills import (
    SkillLoader,
    SkillValidator,
    SkillRegistry,
    SkillExecutor,
    SkillExecutionRequest,
    SkillStatus
)
from backend.permissions import CentralPermissionManager, PermissionLevel

def test_skill_discovery():
    discovered = SkillLoader.discover_skills()
    skill_ids = [s.id for s in discovered]
    assert "coding_specialist" in skill_ids
    assert "deep_researcher" in skill_ids
    assert "pdf_generator" in skill_ids
    assert "windows_controller" in skill_ids
    assert "data_analyst" in skill_ids
    assert "custom_automation" in skill_ids

def test_skill_validator_ast_security():
    # Valid script passes
    valid_script = Path("skills/coding/scripts/main.py")
    safe, warnings = SkillValidator.audit_script_security(valid_script)
    assert safe is True, f"Valid script produced warnings: {warnings}"

    # Banned script fails
    banned_code = "import ctypes\ndef dangerous():\n    eval('2 + 2')"
    temp_script = Path("scratch_banned.py")
    temp_script.write_text(banned_code, encoding="utf-8")
    try:
        safe, warnings = SkillValidator.audit_script_security(temp_script)
        assert safe is False
        assert any("ctypes" in w for w in warnings)
        assert any("eval" in w for w in warnings)
    finally:
        if temp_script.exists():
            temp_script.unlink()

@pytest.mark.asyncio
async def test_skill_execution_coding_specialist():
    CentralPermissionManager.grant_permission("skills", "coding_specialist", PermissionLevel.EXECUTE, is_persistent=True)
    req = SkillExecutionRequest(
        skill_id="coding_specialist",
        parameters={"code": "def calculate_risk(a, b):\n    return a * b"}
    )
    res = await SkillExecutor.execute_skill(req)
    assert res.status == SkillStatus.SUCCESS
    assert res.output["valid_syntax"] is True
    assert res.output["functions_count"] == 1

@pytest.mark.asyncio
async def test_skill_execution_data_analyst():
    CentralPermissionManager.grant_permission("skills", "data_analyst", PermissionLevel.EXECUTE, is_persistent=True)
    req = SkillExecutionRequest(
        skill_id="data_analyst",
        parameters={"series": [10.0, 12.0, 11.5, 14.0, 16.0]}
    )
    res = await SkillExecutor.execute_skill(req)
    assert res.status == SkillStatus.SUCCESS
    assert res.output["count"] == 5
    assert "mean" in res.output

def test_skill_manager_registry_controls():
    # Toggle enabled / disabled
    ok = SkillRegistry.set_skill_enabled("custom_automation", False)
    assert ok is True
    skill = SkillRegistry.get_skill("custom_automation")
    assert skill["is_enabled"] is False

    # Re-enable
    ok = SkillRegistry.set_skill_enabled("custom_automation", True)
    assert ok is True
    skill = SkillRegistry.get_skill("custom_automation")
    assert skill["is_enabled"] is True

