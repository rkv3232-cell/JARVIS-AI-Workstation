"""
Unit and integration tests for Component 7: Memory Timeline & Transparency.
Tests source tracking, access logging, in-place edit, permanent delete, and privacy settings.
"""

from backend.memory import MemoryTimelineManager

def test_add_memory_with_source_and_retrieve():
    mid = MemoryTimelineManager.add_memory_with_source(
        category="research_knowledge",
        content="Reinforcement learning from human feedback stabilizes reasoning models.",
        key="rlhf_research",
        tags=["ai", "rlhf"],
        source_type="browser_research",
        source_url="https://arxiv.org/abs/test",
        is_important=True
    )
    assert mid is not None
    assert mid.startswith("mem_")

    # Record Access
    MemoryTimelineManager.record_access(mid, component="collaboration", context_summary="Used in step 1")

    # View History
    hist = MemoryTimelineManager.get_memory_history(mid)
    assert hist["status"] == "SUCCESS"
    assert hist["access_count"] >= 1
    assert hist["memory"]["source_type"] == "browser_research"
    assert hist["memory"]["source_url"] == "https://arxiv.org/abs/test"

    # In-place Edit
    edit_ok = MemoryTimelineManager.update_memory_inplace(mid, "Updated RLHF content with DPO comparative metrics.")
    assert edit_ok is True

    # Permanent Delete
    del_ok = MemoryTimelineManager.delete_memory_permanent(mid)
    assert del_ok is True

    # Verify gone
    hist_after = MemoryTimelineManager.get_memory_history(mid)
    assert hist_after["status"] == "ERROR"

def test_memory_privacy_settings_controls():
    # Toggle recording
    MemoryTimelineManager.update_privacy_settings(
        recording_enabled=False,
        excluded_categories=["trading_journal"],
        sensitive_keywords=["secret_pass"]
    )
    settings = MemoryTimelineManager.get_privacy_settings()
    assert settings["recording_enabled"] is False
    assert "trading_journal" in settings["excluded_categories"]

    # When recording is disabled, add_memory_with_source returns None
    blocked_id = MemoryTimelineManager.add_memory_with_source(
        category="general",
        content="This should not be saved"
    )
    assert blocked_id is None

    # Re-enable
    MemoryTimelineManager.update_privacy_settings(
        recording_enabled=True,
        excluded_categories=[],
        sensitive_keywords=[]
    )
    settings_after = MemoryTimelineManager.get_privacy_settings()
    assert settings_after["recording_enabled"] is True
