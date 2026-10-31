import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings

@pytest.fixture
def client():
    return TestClient(app)

def test_unauthenticated_request_rejected(client):
    """
    Verifies that sensitive endpoints strictly return HTTP 401 when
    unauthenticated requests are sent (no X-JARVIS-Session header or cookie).
    """
    sensitive_endpoints = [
        ("GET", "/api/os/pending-actions"),
        ("POST", "/api/os/confirm", {"action_id": "act_test123"}),
        ("POST", "/api/os/reject", {"action_id": "act_test123"}),
        ("GET", "/api/security/audit-logs"),
        ("POST", "/api/privacy/kill-switch", {"target": "mic", "state": True}),
        ("POST", "/api/trading/paper/order", {"symbol": "NIFTY50", "side": "BUY", "quantity": 1}),
        ("POST", "/api/trading/paper/reset", {"initial_capital": 1000000.0, "confirmed": True}),
        ("GET", "/api/memory"),
        ("POST", "/api/memory", {"category": "GENERAL", "content": "Test secret memory"}),
        ("GET", "/api/memory/export"),
        ("POST", "/api/workflows", {"name": "Test", "action_type": "send_notification"}),
        ("POST", "/api/voice/interrupt", {}),
        ("POST", "/api/chat", {"message": "Hello"})
    ]

    for item in sensitive_endpoints:
        method = item[0]
        path = item[1]
        payload = item[2] if len(item) > 2 else None

        if method == "GET":
            res = client.get(path)
        elif method == "POST":
            res = client.post(path, json=payload or {})
        elif method == "DELETE":
            res = client.delete(path)

        assert res.status_code == 401, f"Endpoint {method} {path} should return 401, got {res.status_code}"

def test_authenticated_request_authorized(client):
    """
    Verifies that requests carrying valid X-JARVIS-Session header are accepted.
    """
    headers = {"X-JARVIS-Session": settings.SESSION_TOKEN}
    
    # 1. Auth verify session endpoint
    res = client.get("/api/auth/session", headers=headers)
    assert res.status_code == 200
    assert res.json()["authenticated"] is True

    # 2. Sensitive endpoints work with header
    res_os = client.get("/api/os/pending-actions", headers=headers)
    assert res_os.status_code == 200
    assert "pending_actions" in res_os.json()

    res_audit = client.get("/api/security/audit-logs", headers=headers)
    assert res_audit.status_code == 200
    assert "audit_logs" in res_audit.json()

def test_cookie_authentication_authorized(client):
    """
    Verifies that the session_token cookie set on page load is accepted for authentication.
    """
    cookies = {"session_token": settings.SESSION_TOKEN}
    res = client.get("/api/os/pending-actions", cookies=cookies)
    assert res.status_code == 200

def test_query_string_auth_rejected_for_rest(client):
    """
    Proves that query-string token mechanism is explicitly rejected for ordinary REST routes.
    """
    res = client.get(f"/api/os/pending-actions?token={settings.SESSION_TOKEN}")
    assert res.status_code == 401

def test_websocket_unauthenticated_rejected(client):
    """
    Verifies WebSocket handshake rejection when no session token is provided.
    """
    with pytest.raises(Exception):
        with client.websocket_connect("/ws") as ws:
            pass

def test_websocket_untrusted_origin_rejected(client):
    """
    Verifies WebSocket handshake rejection when an untrusted external Origin is passed.
    """
    headers = {"Origin": "https://malicious-phishing-site.com"}
    with pytest.raises(Exception):
        with client.websocket_connect(f"/ws?token={settings.SESSION_TOKEN}", headers=headers) as ws:
            pass

def test_websocket_authenticated_accepted(client):
    """
    Verifies WebSocket connection succeeds when valid token and allowed Origin are provided.
    """
    headers = {"Origin": "http://127.0.0.1:8000"}
    with client.websocket_connect(f"/ws?token={settings.SESSION_TOKEN}", headers=headers) as ws:
        data = ws.receive_json()
        assert data["event"] == "telemetry"
        assert "cpu_percent" in data["payload"]

