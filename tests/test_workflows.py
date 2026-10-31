import pytest
from backend.workflows.workflow_engine import WorkflowEngine

def test_workflow_listing_and_templates():
    wfs = WorkflowEngine.list_workflows()
    assert len(wfs) >= 4  # Default 4 seed templates
    names = [w["name"] for w in wfs]
    assert "Morning Market Briefing" in names

def test_workflow_allowlist_validation():
    # Allowlisted action
    res = WorkflowEngine.create_workflow({
        "name": "Test Notification Flow",
        "trigger_type": "manual",
        "action_type": "send_notification",
        "action_params": {"message": "Test"}
    })
    assert res["success"] is True
    wf_id = res["workflow_id"]

    # Blocked action (Arbitrary shell command rejected!)
    blocked_res = WorkflowEngine.create_workflow({
        "name": "Malicious Shell Flow",
        "trigger_type": "manual",
        "action_type": "execute_shell_cmd",
        "action_params": {"cmd": "rm -rf /"}
    })
    assert blocked_res["success"] is False
    assert "not in allowlist" in blocked_res["error"]

    # Cleanup
    WorkflowEngine.delete_workflow(wf_id)

@pytest.mark.asyncio
async def test_workflow_dry_run_execution():
    wfs = WorkflowEngine.list_workflows()
    target_wf = wfs[0]
    
    # Execute in dry-run mode
    dry_res = await WorkflowEngine.run_workflow(target_wf["id"], is_dry_run=True)
    assert dry_res["success"] is True
    assert dry_res["is_dry_run"] is True
    assert "trace" in dry_res
    steps = [t["step"] for t in dry_res["trace"]]
    assert "TRIGGER" in steps
    assert "CONDITION" in steps
    assert "ACTION" in steps

