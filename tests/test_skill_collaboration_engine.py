"""
Unit and integration tests for Component 5: Skill Collaboration Engine.
Tests task planning, sequential multi-skill execution, and pause/resume/cancel controls.
"""

import pytest
import asyncio
from backend.collaboration import CollaborationEngine
from backend.permissions import CentralPermissionManager, PermissionLevel

@pytest.fixture(autouse=True)
def ensure_permissions():
    CentralPermissionManager.grant_permission("skills", "deep_researcher", PermissionLevel.EXECUTE, is_persistent=True)
    CentralPermissionManager.grant_permission("skills", "data_analyst", PermissionLevel.EXECUTE, is_persistent=True)
    CentralPermissionManager.grant_permission("skills", "pdf_generator", PermissionLevel.EXECUTE, is_persistent=True)
    CentralPermissionManager.grant_permission("skills", "coding_specialist", PermissionLevel.EXECUTE, is_persistent=True)

def test_collaboration_plan_generation():
    plan = CollaborationEngine.plan_task("Comprehensive Market Analysis for Renewable Energy")
    assert plan["task_id"].startswith("collab_")
    assert plan["status"] == "PLANNED"
    assert plan["step_count"] >= 2
    assert plan["steps"][0]["skill_id"] == "deep_researcher"

@pytest.mark.asyncio
async def test_collaboration_end_to_end_execution():
    plan = CollaborationEngine.plan_task("Autonomous Quant Research Pipeline")
    task_id = plan["task_id"]

    # Execute collaboration loop directly
    await CollaborationEngine._execute_collaboration_loop(task_id)

    task = CollaborationEngine.get_task(task_id)
    assert task["status"] == "COMPLETED"
    assert len(task["steps"]) == plan["step_count"]
    for step in task["steps"]:
        assert step["status"] == "COMPLETED"

    # Verify pipeline context and outputs
    output = task["output"]
    assert "research_output" in output
    assert "data_output" in output
    if "pdf_output" in output:
        assert output["pdf_output"]["status"] == "SUCCESS"

def test_collaboration_pause_resume_cancel():
    plan = CollaborationEngine.plan_task("Test Lifecycle Controls")
    task_id = plan["task_id"]

    CollaborationEngine.pause_task(task_id)
    assert CollaborationEngine._pause_flags.get(task_id) is True

    CollaborationEngine.resume_task(task_id)
    assert CollaborationEngine._pause_flags.get(task_id) is False

    CollaborationEngine.cancel_task(task_id)
    assert CollaborationEngine._cancel_flags.get(task_id) is True

