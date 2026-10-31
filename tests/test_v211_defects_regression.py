import json
import pytest
import zipfile
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ed25519

from backend.auto_updater import SecureAutoUpdater, SecurityError
from backend.trading.paper_portfolio import PaperTradingPortfolio
from backend.trading.strategy_lab import StrategyLabBacktester
from backend.workflows.workflow_engine import WorkflowEngine
from backend.security import privacy_guard
from backend.ai_screen_vision import capture_desktop_image, analyze_screen_with_ai
from backend.health_center import check_ai_provider_latencies

# --------------------------------------------------------------------------
# 1. Digital Signature & Updater Hardening
# --------------------------------------------------------------------------
def test_updater_digital_signature_verification():
    # Generate ephemeral Ed25519 keypair for test
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    pub_hex = public_key.public_bytes_raw().hex()

    manifest_data = {
        "version": "2.2.0",
        "download_url": "https://github.com/rkv3232-cell/JARVIS-AI-Workstation/releases/download/v2.2.0/update.zip",
        "sha256": "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    }
    canonical = json.dumps(manifest_data, sort_keys=True, separators=(',', ':')).encode("utf-8")
    sig = private_key.sign(canonical).hex()

    valid_manifest = {
        "manifest_data": manifest_data,
        "signature": sig
    }
    assert SecureAutoUpdater.verify_manifest_signature(valid_manifest, public_key_hex=pub_hex) is True

    # Tampered data
    tampered_manifest = {
        "manifest_data": {**manifest_data, "version": "2.3.0"},
        "signature": sig
    }
    assert SecureAutoUpdater.verify_manifest_signature(tampered_manifest, public_key_hex=pub_hex) is False

    # Unsigned manifest
    assert SecureAutoUpdater.verify_manifest_signature({"manifest_data": manifest_data}, public_key_hex=pub_hex) is False

def test_updater_zip_slip_protection(tmp_path):
    evil_zip_path = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil_zip_path, "w") as zf:
        zf.writestr("../../evil.txt", "Malicious content")

    dest_dir = tmp_path / "extracted"
    with pytest.raises(SecurityError) as excinfo:
        SecureAutoUpdater.safe_extract_zip(evil_zip_path, dest_dir)
    assert "ZIP Slip" in str(excinfo.value)

@pytest.mark.asyncio
async def test_updater_offline_returns_unavailable():
    # Non-existent domain should return UPDATE_CHECK_UNAVAILABLE rather than claiming up to date
    res = await SecureAutoUpdater.check_for_updates(manifest_url="https://invalid-nonexistent-domain-xyz.com/manifest.json")
    assert res["success"] is False
    assert res["status"] == "UPDATE_CHECK_UNAVAILABLE"
    assert "unavailable" in res["message"].lower()

# --------------------------------------------------------------------------
# 2. Paper Trading Execution Corrections
# --------------------------------------------------------------------------
def test_paper_trading_market_order_requires_valid_price():
    # Missing price on MARKET order must fail (no 100.0 fallback)
    res_none = PaperTradingPortfolio.execute_order("NIFTY50", "BUY", 10, order_type="MARKET", price=None)
    assert res_none["success"] is False
    assert "Execution price is unavailable" in res_none["error"]

    res_zero = PaperTradingPortfolio.execute_order("NIFTY50", "BUY", 10, order_type="MARKET", price=0.0)
    assert res_zero["success"] is False

def test_paper_trading_limit_order_lifecycle():
    PaperTradingPortfolio.reset_account(initial_capital=1000000.0, confirmed=True)

    # 1. Submit BUY limit below market: 22000 when market is 22500
    res = PaperTradingPortfolio.execute_order("NIFTY50", "BUY", 5, order_type="LIMIT", price=22000.0)
    assert res["success"] is True
    assert res["status"] == "PENDING"
    order_id = res["order_id"]

    # Verify order is pending in summary
    summary = PaperTradingPortfolio.get_portfolio_summary()
    pending = [o for o in summary["recent_orders"] if o["order_id"] == order_id]
    assert len(pending) == 1
    assert pending[0]["status"] == "PENDING"
    assert len(summary["positions"]) == 0

    # 2. Tick at 22600 does not trigger BUY limit
    execs_none = PaperTradingPortfolio.evaluate_pending_orders_and_triggers("NIFTY50", 22600.0)
    assert len(execs_none) == 0

    # 3. Tick drops to 21950 triggers BUY limit fill
    execs = PaperTradingPortfolio.evaluate_pending_orders_and_triggers("NIFTY50", 21950.0)
    assert len(execs) == 1
    assert execs[0]["status"] == "FILLED"

    summary_after = PaperTradingPortfolio.get_portfolio_summary()
    assert len(summary_after["positions"]) == 1
    assert summary_after["positions"][0]["quantity"] == 5

def test_paper_trading_reset_requires_confirmation_and_creates_backup():
    # Without confirmation -> rejected
    unconfirmed_res = PaperTradingPortfolio.reset_account(initial_capital=500000.0, confirmed=False)
    assert unconfirmed_res["success"] is False
    assert "requires explicit confirmation" in unconfirmed_res["error"]

    # With confirmation -> succeeds and creates snapshot backup
    confirmed_res = PaperTradingPortfolio.reset_account(initial_capital=500000.0, confirmed=True)
    assert confirmed_res["success"] is True
    assert "snapshot_id" in confirmed_res
    assert confirmed_res["snapshot_id"].startswith("snap_")

    summary = PaperTradingPortfolio.get_portfolio_summary()
    assert summary["cash_balance"] == 500000.0

# --------------------------------------------------------------------------
# 3. Backtesting Next-Bar Open Execution & Warmup
# --------------------------------------------------------------------------
def test_backtest_next_bar_open_execution_model():
    from tests.test_trading_lab import generate_sample_candles
    candles = generate_sample_candles(60)

    res = StrategyLabBacktester.run_backtest(
        candles=candles,
        strategy_name="sma_ema_crossover",
        params={"fast_period": 5, "slow_period": 15},
        initial_capital=1000000.0
    )
    assert res["success"] is True
    assert res["execution_model"].startswith("Next-Bar Open")
    assert "chronological_holdout_split" in res
    assert res["chronological_holdout_split"]["warmup_bars_preserved"] > 0
    assert "rolling_walk_forward" in res
    assert res["rolling_walk_forward"] is not None

# --------------------------------------------------------------------------
# 4. Workflow Fail-Closed Condition Safety
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workflow_condition_missing_context_fails_closed():
    # Workflow requires 'ram_percent' > 80.0
    # Context passes empty dict {} -> MUST NOT PASS! Must fail-closed.
    res = await WorkflowEngine.run_workflow("wf_system_health", context={}, is_dry_run=False)
    assert res["success"] is True
    assert res["status"] in ["SKIPPED_FAIL_CLOSED", "SIMULATED_FAIL_CLOSED"]
    # Verify condition met is False
    cond_step = [s for s in res["trace"] if s["step"] == "CONDITION"][0]
    assert cond_step["met"] is False
    assert "missing" in cond_step["error"].lower() or "unavailable" in cond_step["error"].lower()

@pytest.mark.asyncio
async def test_workflow_condition_unknown_operator_rejected():
    # Workflow with unknown operator
    custom_wf = {
        "id": "wf_test_bad_op",
        "name": "Invalid Operator Workflow",
        "trigger_type": "manual",
        "trigger_config": {},
        "condition_config": {"field": "price", "operator": "MAGIC_OPERATOR", "value": 100},
        "action_type": "send_notification",
        "action_params": {"message": "Test"}
    }
    WorkflowEngine.create_workflow(custom_wf)
    res = await WorkflowEngine.run_workflow("wf_test_bad_op", context={"price": 105}, is_dry_run=False)
    assert res["success"] is False
    assert res["status"] == "VALIDATION_FAILED"
    assert "invalid condition operator" in res["error"]
    WorkflowEngine.delete_workflow("wf_test_bad_op")

# --------------------------------------------------------------------------
# 5. Microphone & Screen Vision Privacy Verification
# --------------------------------------------------------------------------
def test_microphone_privacy_releases_stream():
    # Engage mic kill switch
    privacy_guard.set_mic_kill_switch(True)
    status = privacy_guard.get_status()
    assert status["mic_kill_switch"] is True
    assert status["mic_active"] is False

    # Screen vision kill switch blocks capture
    privacy_guard.set_screen_kill_switch(True)
    assert capture_desktop_image() is None

    # Reset kill switches for clean environment
    privacy_guard.set_mic_kill_switch(False)
    privacy_guard.set_screen_kill_switch(False)

# --------------------------------------------------------------------------
# 6. Provider Health Accuracy Probing
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_provider_health_probe_accuracy():
    latencies = await check_ai_provider_latencies()
    assert "Google Gemini" in latencies
    assert "Groq LPU" in latencies
    assert "OpenRouter" in latencies
    assert "Sarvam AI" in latencies
    assert "Ollama (Local Private)" in latencies

    # Sarvam AI has verified_at and state
    sarvam = latencies["Sarvam AI"]
    assert "state" in sarvam
    assert "verified_at" in sarvam
    assert "reachable" in sarvam
    assert "authenticated" in sarvam

# --------------------------------------------------------------------------
# 7. SSRF Protection & Scheme Validation
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ssrf_protection_blocks_internal_ips_and_schemes():
    from backend.url_threat_analyzer import validate_url_for_ssrf, probe_url_safely, analyze_url_threat

    # 1. Scheme checks
    safe_file, _, err = validate_url_for_ssrf("file:///etc/passwd")
    assert safe_file is False
    assert "Blocked unsafe scheme" in err

    safe_gopher, _, _ = validate_url_for_ssrf("gopher://127.0.0.1:6379")
    assert safe_gopher is False

    # 2. Localhost & Private IP checks
    safe_local, _, err_loc = validate_url_for_ssrf("http://127.0.0.1:8000/api/os/execute")
    assert safe_local is False
    assert "blocked" in err_loc.lower()

    safe_priv, _, _ = validate_url_for_ssrf("http://192.168.1.1")
    assert safe_priv is False

    safe_meta, _, _ = validate_url_for_ssrf("http://169.254.169.254/latest/meta-data/")
    assert safe_meta is False

    # 3. Probe with internal URL should return SSRF_BLOCKED
    probe_res = await probe_url_safely("http://127.0.0.1:8000")
    assert "SSRF_BLOCKED" in probe_res.get("probe_error", "")

    # 4. Threat analysis should flag SSRF attempt with critical score
    threat_res = await analyze_url_threat("http://127.0.0.1:8000")
    assert threat_res["threat_level"] == "CRITICAL"
    assert any("SSRF" in s for s in threat_res["scam_types"])

# --------------------------------------------------------------------------
# 8. Workflow Approval Resumption
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_workflow_approval_resumption():
    from backend.security import action_registry
    from backend.os_controller import execute_confirmed_action

    wf_id = "wf_test_approval_resumption"
    wf_data = {
        "id": wf_id,
        "name": "Approval Resumption Test Workflow",
        "trigger_type": "manual",
        "trigger_config": {},
        "condition_config": {"type": "always_true"},
        "action_type": "send_notification",
        "action_params": {"title": "Resumed", "message": "Resumed successfully"},
        "requires_approval": 1
    }
    WorkflowEngine.create_workflow(wf_data)

    # Run workflow -> must pause at PENDING_APPROVAL
    run_res = await WorkflowEngine.run_workflow(wf_id, is_dry_run=False)
    assert run_res["status"] == "PENDING_APPROVAL"
    action_id = run_res["action_id"]

    # User confirms the action
    ok, msg, action = action_registry.approve(action_id)
    assert ok is True
    assert action is not None

    # System resumes workflow execution through execute_confirmed_action
    exec_res = await execute_confirmed_action(action)
    assert exec_res["success"] is True
    assert exec_res["status"] == "COMPLETED"

    # Cleanup
    WorkflowEngine.delete_workflow(wf_id)

# --------------------------------------------------------------------------
# 9. Smart Money Concepts FVG No-Lookahead Bar Alignment
# --------------------------------------------------------------------------
def test_smc_fvg_no_lookahead_bar_alignment():
    from backend.trading.strategy_lab import detect_smc_structures

    candles = [
        {"time": 1, "open": 100, "high": 105, "low": 98, "close": 102, "volume": 100},
        {"time": 2, "open": 103, "high": 120, "low": 102, "close": 118, "volume": 200},
        {"time": 3, "open": 118, "high": 130, "low": 115, "close": 128, "volume": 300},
    ]
    # Candle 3 Low (115) > Candle 1 High (105).
    # FVG is ONLY confirmed when candle 3 (bar index 2) has formed.
    smc = detect_smc_structures(candles)
    assert len(smc["fvgs"]) == 1
    fvg = smc["fvgs"][0]
    assert fvg["type"] == "BULLISH_FVG"
    # Bar index MUST be 2 (the confirmation bar), NEVER 1 (which would create lookahead leakage into previous bar)
    assert fvg["bar_index"] == 2
    assert fvg["time"] == 3

# --------------------------------------------------------------------------
# 10. Honest Vision Fallback (Zero Hallucinated Chart Overlays)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_vision_honest_fallback_reporting():
    from backend.ai_screen_vision import detect_chart_patterns_and_overlays

    # Without an active image or with API failure, must report failure honestly
    res = await detect_chart_patterns_and_overlays(image_base64="")
    assert res["success"] is False
    assert res["patterns_detected"] == []
    assert res["overlays"] == []
    assert "उपलब्ध नहीं" in res["summary"] or "अनुपलब्ध" in res["summary"]


