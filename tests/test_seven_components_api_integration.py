"""
FastAPI REST API integration tests for all 7 Core Architecture Components.
Verifies authorization enforcement and functional response payloads across routes.
"""

import pytest
import httpx
from fastapi.testclient import TestClient

from backend.main import app
from backend.config import settings

client = TestClient(app)
AUTH_HEADERS = {"X-JARVIS-Session": settings.SESSION_TOKEN}

def test_unauthenticated_requests_rejected():
    # Sensitive endpoints must return 401 when missing session token
    protected_endpoints = [
        ("POST", "/api/browser/tab/new", {"url": "about:blank"}),
        ("GET", "/api/browser/tabs", None),
        ("POST", "/api/skills/coding_specialist/toggle", {"enabled": True}),
        ("GET", "/api/permissions/list", None),
        ("POST", "/api/collaboration/plan", {"objective": "Test objective"}),
        ("GET", "/api/activity-log/events", None),
        ("GET", "/api/memory/timeline", None)
    ]
    for method, path, body in protected_endpoints:
        if method == "POST":
            res = client.post(path, json=body)
        else:
            res = client.get(path)
        assert res.status_code == 401, f"Endpoint {path} did not reject unauthenticated request!"

@pytest.mark.asyncio
async def test_api_browser_lifecycle():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as ac:
        # 1. New Tab
        res = await ac.post("/api/browser/tab/new", json={"url": "about:blank"}, headers=AUTH_HEADERS)
        assert res.status_code == 200
        tab_data = res.json()
        assert tab_data["status"] == "SUCCESS"
        tab_id = tab_data["tab_id"]

        # 2. List Tabs
        res_list = await ac.get("/api/browser/tabs", headers=AUTH_HEADERS)
        assert res_list.status_code == 200
        tabs = res_list.json()["tabs"]
        assert any(t["tab_id"] == tab_id for t in tabs)

        # 3. Close Tab
        res_close = await ac.post("/api/browser/tab/close", json={"tab_id": tab_id}, headers=AUTH_HEADERS)
        assert res_close.status_code == 200

def test_api_skills_endpoints():
    # 1. List skills
    res = client.get("/api/skills/list", headers=AUTH_HEADERS)
    assert res.status_code == 200
    skills = res.json()["skills"]
    assert len(skills) >= 6

    # 2. Get specific skill
    res_skill = client.get("/api/skills/coding_specialist", headers=AUTH_HEADERS)
    assert res_skill.status_code == 200
    data = res_skill.json()
    assert data["name"] == "Python & Systems Coding Specialist"
    assert "skill_md" in data

    # 3. Toggle skill
    res_toggle = client.post("/api/skills/coding_specialist/toggle", json={"enabled": True}, headers=AUTH_HEADERS)
    assert res_toggle.status_code == 200

def test_api_permissions_endpoints():
    # 1. Grant permission
    res_grant = client.post("/api/permissions/grant", json={
        "component": "files",
        "resource": "data/test",
        "level": "WRITE",
        "is_persistent": True
    }, headers=AUTH_HEADERS)
    assert res_grant.status_code == 200
    grant_id = res_grant.json()["grant"]["id"]

    # 2. List grants
    res_list = client.get("/api/permissions/list", headers=AUTH_HEADERS)
    assert res_list.status_code == 200
    grants = res_list.json()["grants"]
    assert any(g["id"] == grant_id for g in grants)

    # 3. Revoke
    res_rev = client.delete(f"/api/permissions/grant/{grant_id}", headers=AUTH_HEADERS)
    assert res_rev.status_code == 200

def test_api_collaboration_endpoints():
    # Plan task
    res_plan = client.post("/api/collaboration/plan", json={
        "objective": "API Test Multi-Skill Flow"
    }, headers=AUTH_HEADERS)
    assert res_plan.status_code == 200
    data = res_plan.json()
    assert data["status"] == "PLANNED"
    assert "task_id" in data

    # List tasks
    res_tasks = client.get("/api/collaboration/tasks", headers=AUTH_HEADERS)
    assert res_tasks.status_code == 200
    assert len(res_tasks.json()["tasks"]) >= 1

def test_api_activity_log_endpoints():
    # Events query
    res = client.get("/api/activity-log/events?limit=10", headers=AUTH_HEADERS)
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "events" in data

    # Stats query
    res_stats = client.get("/api/activity-log/stats", headers=AUTH_HEADERS)
    assert res_stats.status_code == 200
    stats = res_stats.json()
    assert "total_events" in stats

def test_api_memory_timeline_endpoints():
    # 1. Create node
    res_create = client.post("/api/memory/node", json={
        "category": "user_preferences",
        "content": "Prefer concise technical summaries.",
        "key": "summary_pref",
        "source_type": "explicit_instruction"
    }, headers=AUTH_HEADERS)
    assert res_create.status_code == 200
    mem_id = res_create.json()["memory_id"]

    # 2. Timeline query
    res_tl = client.get("/api/memory/timeline?category=user_preferences", headers=AUTH_HEADERS)
    assert res_tl.status_code == 200
    assert any(m["id"] == mem_id for m in res_tl.json()["timeline"])

    # 3. History
    res_hist = client.get(f"/api/memory/{mem_id}/history", headers=AUTH_HEADERS)
    assert res_hist.status_code == 200

    # 4. Delete
    res_del = client.delete(f"/api/memory/{mem_id}", headers=AUTH_HEADERS)
    assert res_del.status_code == 200
