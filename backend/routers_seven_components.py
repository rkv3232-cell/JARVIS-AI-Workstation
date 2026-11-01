"""
FastAPI Router for JARVIS-APEX 7 Core Architecture Components:
1. AI Browser Operator
2. Skills System
3. Skill Manager
4. Central Permission Manager
5. Skill Collaboration Engine
6. Unified Activity Log
7. Memory Timeline & Transparency
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends, status, Query, Response
from fastapi.responses import PlainTextResponse

from .security import verify_session_token
from .browser import BrowserEngine, BrowserSecurityGuard, BrowserOperator
from .skills import (
    SkillRegistry,
    SkillExecutor,
    SkillExecutionRequest,
    SkillManifest,
    SkillStatus
)
from .permissions import CentralPermissionManager, PermissionLevel
from .collaboration import CollaborationEngine
from .activity import ActivityLogger
from .memory import MemoryTimelineManager

router = APIRouter(prefix="/api")

# =========================================================================
# COMPONENT 1: AI BROWSER OPERATOR
# =========================================================================
class NewTabRequest(BaseModel):
    url: Optional[str] = "about:blank"

class TabSwitchRequest(BaseModel):
    tab_id: str

class TabCloseRequest(BaseModel):
    tab_id: str

class NavigateRequest(BaseModel):
    tab_id: Optional[str] = None
    url: str

class BrowserActionRequest(BaseModel):
    tab_id: Optional[str] = None
    action: str  # back, forward, reload, home, search, click, type
    params: Optional[Dict[str, Any]] = None

class BookmarkRequest(BaseModel):
    title: str
    url: str
    folder: Optional[str] = "default"
    tags: Optional[List[str]] = None

class AISummarizeRequest(BaseModel):
    tab_id: Optional[str] = None

class AIQARequest(BaseModel):
    question: str
    tab_id: Optional[str] = None

class AICompareRequest(BaseModel):
    tab_ids: List[str]
    criteria: Optional[str] = "Key differences and technical insights"

class AIReportRequest(BaseModel):
    tab_id: Optional[str] = None

@router.post("/browser/tab/new", dependencies=[Depends(verify_session_token)])
async def browser_new_tab(req: NewTabRequest):
    return await BrowserEngine.new_tab(req.url)

@router.get("/browser/tabs", dependencies=[Depends(verify_session_token)])
async def browser_list_tabs():
    return {"tabs": await BrowserEngine.list_tabs()}

@router.post("/browser/tab/switch", dependencies=[Depends(verify_session_token)])
async def browser_switch_tab(req: TabSwitchRequest):
    return await BrowserEngine.switch_tab(req.tab_id)

@router.post("/browser/tab/close", dependencies=[Depends(verify_session_token)])
async def browser_close_tab(req: TabCloseRequest):
    return await BrowserEngine.close_tab(req.tab_id)

@router.post("/browser/navigate", dependencies=[Depends(verify_session_token)])
async def browser_navigate(req: NavigateRequest):
    return await BrowserEngine.navigate(req.tab_id, req.url)

@router.post("/browser/action", dependencies=[Depends(verify_session_token)])
async def browser_action(req: BrowserActionRequest):
    return await BrowserEngine.perform_action(req.tab_id, req.action, req.params)

@router.get("/browser/snapshot", dependencies=[Depends(verify_session_token)])
async def browser_get_snapshot(tab_id: Optional[str] = None):
    return await BrowserEngine.get_snapshot(tab_id)

@router.post("/browser/stop", dependencies=[Depends(verify_session_token)])
async def browser_emergency_stop():
    return {"status": "SUCCESS", "stopped": BrowserEngine.stop_automation()}

@router.get("/browser/bookmarks", dependencies=[Depends(verify_session_token)])
async def browser_get_bookmarks():
    return {"bookmarks": BrowserEngine.list_bookmarks()}

@router.post("/browser/bookmarks", dependencies=[Depends(verify_session_token)])
async def browser_add_bookmark(req: BookmarkRequest):
    return BrowserEngine.add_bookmark(req.title, req.url, req.folder or "default", req.tags)

@router.delete("/browser/bookmarks/{bookmark_id}", dependencies=[Depends(verify_session_token)])
async def browser_delete_bookmark(bookmark_id: str):
    ok = BrowserEngine.delete_bookmark(bookmark_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Bookmark not found.")
    return {"status": "SUCCESS", "deleted": True}

@router.get("/browser/history", dependencies=[Depends(verify_session_token)])
async def browser_get_history(limit: int = 50):
    return {"history": BrowserEngine.get_history(limit=limit)}

@router.delete("/browser/history", dependencies=[Depends(verify_session_token)])
async def browser_clear_history():
    count = BrowserEngine.clear_history()
    return {"status": "SUCCESS", "cleared_count": count}

@router.post("/browser/ai/summarize", dependencies=[Depends(verify_session_token)])
async def browser_ai_summarize(req: AISummarizeRequest):
    return await BrowserOperator.summarize_page(req.tab_id)

@router.post("/browser/ai/qa", dependencies=[Depends(verify_session_token)])
async def browser_ai_qa(req: AIQARequest):
    return await BrowserOperator.qa_page(req.question, req.tab_id)

@router.post("/browser/ai/compare", dependencies=[Depends(verify_session_token)])
async def browser_ai_compare(req: AICompareRequest):
    return await BrowserOperator.compare_pages(req.tab_ids, req.criteria)

@router.post("/browser/ai/extract-tables", dependencies=[Depends(verify_session_token)])
async def browser_ai_extract_tables(req: AISummarizeRequest):
    return await BrowserOperator.extract_tables(req.tab_id)

@router.post("/browser/ai/report", dependencies=[Depends(verify_session_token)])
async def browser_ai_report(req: AIReportRequest):
    return await BrowserOperator.generate_research_report(req.tab_id)


# =========================================================================
# COMPONENTS 2 & 3: SKILLS SYSTEM & SKILL MANAGER
# =========================================================================
class SkillToggleRequest(BaseModel):
    enabled: bool

class SkillExecutePayload(BaseModel):
    parameters: Optional[Dict[str, Any]] = None
    timeout_seconds: Optional[int] = 30

class SkillInstallRequest(BaseModel):
    source_path: str

@router.get("/skills/list", dependencies=[Depends(verify_session_token)])
async def skills_list(enabled_only: bool = False, skill_type: Optional[str] = None):
    return {"skills": SkillRegistry.list_skills(enabled_only=enabled_only, skill_type=skill_type)}

@router.get("/skills/{skill_id}", dependencies=[Depends(verify_session_token)])
async def skills_get(skill_id: str):
    skill = SkillRegistry.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found.")
    return skill

@router.post("/skills/{skill_id}/toggle", dependencies=[Depends(verify_session_token)])
async def skills_toggle(skill_id: str, req: SkillToggleRequest):
    ok = SkillRegistry.set_skill_enabled(skill_id, req.enabled)
    if not ok:
        raise HTTPException(status_code=404, detail="Skill not found.")
    return {"status": "SUCCESS", "skill_id": skill_id, "is_enabled": req.enabled}

@router.post("/skills/{skill_id}/execute", dependencies=[Depends(verify_session_token)])
async def skills_execute(skill_id: str, payload: SkillExecutePayload):
    req = SkillExecutionRequest(
        skill_id=skill_id,
        parameters=payload.parameters or {},
        timeout_seconds=payload.timeout_seconds or 30
    )
    result = await SkillExecutor.execute_skill(req)
    return result.model_dump()

@router.post("/skills/install", dependencies=[Depends(verify_session_token)])
async def skills_install(req: SkillInstallRequest):
    src = Path(req.source_path)
    ok, msg, installed = SkillRegistry.install_skill_from_folder(src)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "SUCCESS", "message": msg, "skill": installed}

@router.delete("/skills/{skill_id}", dependencies=[Depends(verify_session_token)])
async def skills_uninstall(skill_id: str):
    ok, msg = SkillRegistry.uninstall_skill(skill_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "SUCCESS", "message": msg}

@router.get("/skills/{skill_id}/history", dependencies=[Depends(verify_session_token)])
async def skills_history(skill_id: str, limit: int = 50):
    return {"history": SkillRegistry.get_execution_history(skill_id=skill_id, limit=limit)}


# =========================================================================
# COMPONENT 4: CENTRAL PERMISSION MANAGER
# =========================================================================
class PermissionGrantRequest(BaseModel):
    component: str
    resource: str
    level: str  # READ, WRITE, EXECUTE, SENSITIVE
    is_persistent: bool = False
    ttl_seconds: Optional[int] = None
    notes: Optional[str] = None

class PermissionApproveRequest(BaseModel):
    grant_persistence: bool = False

@router.get("/permissions/list", dependencies=[Depends(verify_session_token)])
async def permissions_list(component: Optional[str] = None, active_only: bool = True):
    return {"grants": CentralPermissionManager.list_grants(component=component, active_only=active_only)}

@router.post("/permissions/grant", dependencies=[Depends(verify_session_token)])
async def permissions_grant(req: PermissionGrantRequest):
    try:
        level_enum = PermissionLevel(req.level.upper())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid level '{req.level}'. Must be READ, WRITE, EXECUTE, or SENSITIVE.")

    grant = CentralPermissionManager.grant_permission(
        component=req.component,
        resource=req.resource,
        level=level_enum,
        is_persistent=req.is_persistent,
        ttl_seconds=req.ttl_seconds,
        notes=req.notes
    )
    return {"status": "SUCCESS", "grant": grant}

@router.delete("/permissions/grant/{grant_id}", dependencies=[Depends(verify_session_token)])
async def permissions_revoke(grant_id: str):
    ok = CentralPermissionManager.revoke_permission(grant_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Grant ID not found.")
    return {"status": "SUCCESS", "revoked": True}

@router.get("/permissions/pending", dependencies=[Depends(verify_session_token)])
async def permissions_pending():
    return {"pending_actions": CentralPermissionManager.list_pending_approvals()}

@router.post("/permissions/approve/{action_id}", dependencies=[Depends(verify_session_token)])
async def permissions_approve(action_id: str, req: Optional[PermissionApproveRequest] = None):
    persist = req.grant_persistence if req else False
    ok, msg, act = CentralPermissionManager.approve_action(action_id, grant_persistence=persist)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "SUCCESS", "message": msg, "action": act}

@router.post("/permissions/reject/{action_id}", dependencies=[Depends(verify_session_token)])
async def permissions_reject(action_id: str):
    ok, msg = CentralPermissionManager.reject_action(action_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "SUCCESS", "message": msg}


# =========================================================================
# COMPONENT 5: SKILL COLLABORATION ENGINE
# =========================================================================
class CollaborationPlanRequest(BaseModel):
    objective: str
    user_plan: Optional[List[Dict[str, Any]]] = None

@router.post("/collaboration/plan", dependencies=[Depends(verify_session_token)])
async def collaboration_plan(req: CollaborationPlanRequest):
    return CollaborationEngine.plan_task(req.objective, user_plan=req.user_plan)

@router.post("/collaboration/start/{task_id}", dependencies=[Depends(verify_session_token)])
async def collaboration_start(task_id: str):
    return await CollaborationEngine.start_task(task_id)

@router.get("/collaboration/tasks", dependencies=[Depends(verify_session_token)])
async def collaboration_list_tasks(limit: int = 30):
    return {"tasks": CollaborationEngine.list_tasks(limit=limit)}

@router.get("/collaboration/task/{task_id}", dependencies=[Depends(verify_session_token)])
async def collaboration_get_task(task_id: str):
    task = CollaborationEngine.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task

@router.post("/collaboration/task/{task_id}/pause", dependencies=[Depends(verify_session_token)])
async def collaboration_pause_task(task_id: str):
    ok = CollaborationEngine.pause_task(task_id)
    return {"status": "SUCCESS", "paused": ok}

@router.post("/collaboration/task/{task_id}/resume", dependencies=[Depends(verify_session_token)])
async def collaboration_resume_task(task_id: str):
    ok = CollaborationEngine.resume_task(task_id)
    return {"status": "SUCCESS", "resumed": ok}

@router.post("/collaboration/task/{task_id}/cancel", dependencies=[Depends(verify_session_token)])
async def collaboration_cancel_task(task_id: str):
    ok = CollaborationEngine.cancel_task(task_id)
    return {"status": "SUCCESS", "cancelled": ok}


# =========================================================================
# COMPONENT 6: UNIFIED ACTIVITY LOG
# =========================================================================
@router.get("/activity-log/events", dependencies=[Depends(verify_session_token)])
async def activity_log_events(
    component: Optional[str] = None,
    action: Optional[str] = None,
    execution_status: Optional[str] = None,
    approval_status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    return ActivityLogger.get_activities(
        component=component,
        action=action,
        execution_status=execution_status,
        approval_status=approval_status,
        search=search,
        limit=limit,
        offset=offset
    )

@router.get("/activity-log/stats", dependencies=[Depends(verify_session_token)])
async def activity_log_stats():
    return ActivityLogger.get_statistics()

@router.get("/activity-log/export", dependencies=[Depends(verify_session_token)])
async def activity_log_export(format: str = "json"):
    data_str = ActivityLogger.export_data(format_type=format)
    media_type = "text/csv" if format.lower() == "csv" else "application/json"
    filename = f"activity_log_export_{int(time.time())}.{format.lower()}"
    return Response(
        content=data_str,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.delete("/activity-log/clear", dependencies=[Depends(verify_session_token)])
async def activity_log_clear():
    # SENSITIVE action check
    auth, reason, _ = CentralPermissionManager.check_permission(
        component="system",
        resource="activity_logs",
        level=PermissionLevel.SENSITIVE,
        description="Purge structured activity logs"
    )
    if not auth:
        raise HTTPException(status_code=403, detail=f"Permission denied: {reason}")
    cleared = ActivityLogger.clear_logs()
    return {"status": "SUCCESS", "cleared_records": cleared}


# =========================================================================
# COMPONENT 7: MEMORY TIMELINE & TRANSPARENCY
# =========================================================================
class MemoryNodeCreateRequest(BaseModel):
    category: str
    content: str
    key: Optional[str] = None
    tags: Optional[List[str]] = None
    source_type: Optional[str] = "explicit_instruction"
    source_url: Optional[str] = None
    source_reference: Optional[str] = None
    confidence: Optional[float] = 1.0
    is_important: Optional[bool] = False

class MemoryNodeUpdateRequest(BaseModel):
    content: str
    key: Optional[str] = None
    tags: Optional[List[str]] = None
    is_important: Optional[bool] = None

class MemoryPrivacySettingsRequest(BaseModel):
    recording_enabled: bool
    excluded_categories: Optional[List[str]] = None
    sensitive_keywords: Optional[List[str]] = None
    retention_days: Optional[int] = 0

class ClearCategoryRequest(BaseModel):
    category: str

@router.get("/memory/timeline", dependencies=[Depends(verify_session_token)])
async def memory_timeline(
    category: Optional[str] = None,
    source_type: Optional[str] = None,
    search: Optional[str] = None,
    is_important: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0
):
    return MemoryTimelineManager.get_timeline(
        category=category,
        source_type=source_type,
        search=search,
        is_important=is_important,
        limit=limit,
        offset=offset
    )

@router.get("/memory/{memory_id}/history", dependencies=[Depends(verify_session_token)])
async def memory_history(memory_id: str):
    res = MemoryTimelineManager.get_memory_history(memory_id)
    if res.get("status") == "ERROR":
        raise HTTPException(status_code=404, detail="Memory node not found.")
    return res

@router.post("/memory/node", dependencies=[Depends(verify_session_token)])
async def memory_create_node(req: MemoryNodeCreateRequest):
    mid = MemoryTimelineManager.add_memory_with_source(
        category=req.category,
        content=req.content,
        key=req.key,
        tags=req.tags,
        source_type=req.source_type or "explicit_instruction",
        source_url=req.source_url,
        source_reference=req.source_reference,
        confidence=req.confidence or 1.0,
        is_important=req.is_important or False
    )
    if not mid:
        raise HTTPException(status_code=400, detail="Memory recording is disabled or category is excluded by privacy settings.")
    return {"status": "SUCCESS", "memory_id": mid}

@router.put("/memory/{memory_id}", dependencies=[Depends(verify_session_token)])
async def memory_update_node(memory_id: str, req: MemoryNodeUpdateRequest):
    ok = MemoryTimelineManager.update_memory_inplace(
        memory_id=memory_id,
        content=req.content,
        key=req.key,
        tags=req.tags,
        is_important=req.is_important
    )
    if not ok:
        raise HTTPException(status_code=404, detail="Memory node not found.")
    return {"status": "SUCCESS", "memory_id": memory_id, "updated": True}

@router.delete("/memory/{memory_id}", dependencies=[Depends(verify_session_token)])
async def memory_delete_node(memory_id: str):
    ok = MemoryTimelineManager.delete_memory_permanent(memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory node not found.")
    return {"status": "SUCCESS", "memory_id": memory_id, "deleted": True}

@router.get("/memory/privacy/settings", dependencies=[Depends(verify_session_token)])
async def memory_get_privacy_settings():
    return MemoryTimelineManager.get_privacy_settings()

@router.post("/memory/privacy/settings", dependencies=[Depends(verify_session_token)])
async def memory_update_privacy_settings(req: MemoryPrivacySettingsRequest):
    return MemoryTimelineManager.update_privacy_settings(
        recording_enabled=req.recording_enabled,
        excluded_categories=req.excluded_categories,
        sensitive_keywords=req.sensitive_keywords,
        retention_days=req.retention_days or 0
    )

@router.post("/memory/privacy/clear-category", dependencies=[Depends(verify_session_token)])
async def memory_clear_category(req: ClearCategoryRequest):
    count = MemoryTimelineManager.clear_category(req.category)
    return {"status": "SUCCESS", "category": req.category, "cleared_count": count}

