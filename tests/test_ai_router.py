import time
import pytest
from backend.model_router import (
    CircuitBreaker,
    get_model_catalog,
    get_model_telemetry,
    get_gemini_38_probe_status
)

def test_circuit_breaker_trips_and_recovers():
    cb = CircuitBreaker("TestProvider", failure_threshold=3, cooldown_seconds=0.2)
    assert cb.state == "CLOSED"
    assert cb.can_attempt() is True

    # Record 2 failures -> remains CLOSED
    cb.record_failure("error 1")
    cb.record_failure("error 2")
    assert cb.state == "CLOSED"
    assert cb.can_attempt() is True

    # 3rd failure -> trips OPEN
    cb.record_failure("error 3")
    assert cb.state == "OPEN"
    assert cb.can_attempt() is False

    # Wait for cooldown
    time.sleep(0.25)
    assert cb.can_attempt() is True
    assert cb.state == "HALF_OPEN"

    # Successful recovery
    cb.record_success(latency_ms=120.5)
    assert cb.state == "CLOSED"
    assert cb.failure_count == 0
    assert cb.successful_requests == 1

def test_model_catalog_and_telemetry():
    catalog = get_model_catalog()
    assert "voice_chat" in catalog
    assert "coding" in catalog
    assert "screen_vision" in catalog
    assert "research_monograph" in catalog

    telemetry = get_model_telemetry()
    assert "circuits" in telemetry
    assert "gemini" in telemetry["circuits"]
    assert "groq" in telemetry["circuits"]
    assert "gemini_38_status" in telemetry

def test_gemini_38_probe_status_structure():
    status = get_gemini_38_probe_status()
    assert "is_available" in status
    assert "active_key_label" in status
    assert "key_details" in status
