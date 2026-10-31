"""
Unit and integration tests for Component 6: Unified Activity Log.
Tests dual-write logging, secret redaction, querying, stats, and CSV/JSON export.
"""

from backend.activity import ActivityLogger
from backend.security import redact_secrets

def test_secret_redaction_in_activity():
    raw_secret = "Authorization: Bearer gsk_1234567890abcdef1234567890abcdef"
    redacted = redact_secrets(raw_secret)
    assert "gsk_1234567890" not in redacted
    assert "REDACTED" in redacted

def test_log_activity_and_query():
    rec = ActivityLogger.log(
        component="test_component",
        action="test_action",
        user_request="Test prompt request",
        target_resource="resource_abc",
        approval_status="AUTO_APPROVED",
        execution_status="SUCCESS",
        result_summary="Completed test action"
    )
    assert rec["event_id"].startswith("act_")

    # Query
    res = ActivityLogger.get_activities(component="test_component", limit=10)
    assert res["total"] >= 1
    found = any(e["event_id"] == rec["event_id"] for e in res["events"])
    assert found is True

def test_activity_stats():
    stats = ActivityLogger.get_statistics()
    assert "total_events" in stats
    assert "by_component" in stats
    assert "by_status" in stats
    assert stats["total_events"] > 0

def test_activity_export():
    # JSON Export
    json_data = ActivityLogger.export_data(format_type="json")
    assert json_data.startswith("[")

    # CSV Export
    csv_data = ActivityLogger.export_data(format_type="csv")
    assert "event_id,timestamp,epoch" in csv_data
