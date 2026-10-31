import asyncio
import json
import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Query, Request, HTTPException, status, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .models import ChatRequest, ChatResponse, WSMessage
from .system_monitor import get_system_telemetry
from .trading_scanner import scan_market, get_option_chain, get_chart_candles, get_market_overview
from .voice_service import (
    generate_speech_file,
    transcribe_audio_bytes,
    prewarm_voice_cache,
    voice_state_machine,
    VoiceState,
    list_audio_devices
)
from .ai_brain import process_user_intent
from .ai_screen_vision import (
    analyze_screen_with_ai, 
    get_latest_screen_analysis,
    detect_chart_patterns_and_overlays,
    extract_screen_text_and_clipboard
)
from .url_threat_analyzer import analyze_url_threat
from .pdf_report_generator import generate_url_pdf_report
from .deep_research_engine import run_universal_deep_research, get_research_history
from .morning_briefing import generate_morning_briefing, is_briefing_due
from .database import log_trade_alert, save_trading_journal_entry, get_trading_journal

# Upgraded Architecture Modules
from .security import (
    action_registry,
    log_audit_event,
    get_recent_audit_logs,
    privacy_guard,
    validate_upload_file,
    redact_secrets,
    verify_session_token,
    verify_websocket_auth,
    RiskLevel
)
from .os_controller import execute_confirmed_action
from .websocket_manager import ws_manager
from .task_coordinator import task_coordinator
from .health_center import get_system_diagnostics_report, record_system_error
from .model_router import get_model_telemetry, get_model_catalog
from .trading.strategy_lab import StrategyLabBacktester
from .trading.paper_portfolio import PaperTradingPortfolio
from .trading.trading_psychology import TradingPsychologyEngine
from .memory.memory_brain import PersistentMemoryBrain, MemoryCategory
from .workflows.workflow_engine import WorkflowEngine
from .auto_updater import SecureAutoUpdater

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# =========================================================================
# 1. REQUEST CORRELATION ID & LOGGING MIDDLEWARE
# =========================================================================
class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:10]}"
        request.state.request_id = req_id
        t0 = time.perf_counter()
        
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            response.headers["X-Request-ID"] = req_id
            response.headers["X-Response-Time"] = f"{duration_ms}ms"
            return response
        except Exception as exc:
            record_system_error(request.url.path, str(exc))
            raise exc

# =========================================================================
# 2. BACKGROUND TELEMETRY BROADCASTER WITH CONCURRENCY COORDINATION
# =========================================================================
bg_task = None
heartbeat_task = None

async def telemetry_broadcaster():
    """
    Emits hardware telemetry, trading signals, and briefings over WebSocket
    utilizing task_coordinator to prevent overlapping execution.
    """
    market_counter = 0
    option_counter = 0

    while True:
        try:
            if ws_manager.get_active_count() > 0:
                # 1. Hardware telemetry every 2 seconds
                telem = get_system_telemetry()
                await ws_manager.broadcast("telemetry", telem.model_dump(), channel="telemetry")

                # 2. Automated Morning Briefing check (@09:00 AM)
                if is_briefing_due():
                    async def _run_briefing():
                        brief = await generate_morning_briefing()
                        await ws_manager.broadcast("morning_briefing", brief.model_dump(), channel="system")
                    await task_coordinator.run_exclusive("morning_briefing", _run_briefing)

                # 3. Market Scan every SCANNER_INTERVAL_SECONDS
                market_counter += 2
                if market_counter >= settings.SCANNER_INTERVAL_SECONDS:
                    market_counter = 0
                    async def _run_scan():
                        signals = await scan_market(settings.DEFAULT_SYMBOLS)
                        if signals:
                            for sig in signals:
                                log_trade_alert(sig.symbol, sig.signal_type, sig.timeframe, sig.current_price, sig.risk_reward, sig.model_dump())
                            await ws_manager.broadcast("trade_alert", [s.model_dump() for s in signals], channel="trading")
                    await task_coordinator.run_exclusive("market_scan", _run_scan)

                # 4. Option Chain updates every 40 seconds
                option_counter += 2
                if option_counter >= 40:
                    option_counter = 0
                    async def _run_option():
                        oc = await get_option_chain("NIFTY50")
                        await ws_manager.broadcast("option_chain", oc.model_dump(), channel="trading")
                    await task_coordinator.run_exclusive("option_chain", _run_option)

                # 5. Live Market Overview every 6 seconds
                if market_counter % 6 == 0:
                    overview = await get_market_overview()
                    await ws_manager.broadcast("market_overview", overview, channel="trading")

        except asyncio.CancelledError:
            break
        except Exception as e:
            record_system_error("telemetry_broadcaster", str(e))
        await asyncio.sleep(2.0)

# =========================================================================
# 3. CLEAN LIFESPAN STARTUP & SHUTDOWN
# =========================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global bg_task, heartbeat_task
    
    # Connect voice state broadcaster
    voice_state_machine.set_broadcast_callback(ws_manager.broadcast)
    
    bg_task = asyncio.create_task(telemetry_broadcaster())
    heartbeat_task = asyncio.create_task(ws_manager.start_heartbeat(interval_seconds=15))
    asyncio.create_task(prewarm_voice_cache())

    # Background PC Wake-Word Listener ('Hey Jarvis') if enabled
    if privacy_guard.wake_listener_active:
        try:
            from .local_wake_listener import start_local_wake_listener
            loop = asyncio.get_running_loop()
            start_local_wake_listener(broadcast_callback=ws_manager.broadcast, loop=loop)
        except Exception as e:
            print(f"[Lifespan] Wake listener initialization notice: {e}")

    # Start background workflow scheduler
    try:
        from .workflows.workflow_engine import workflow_scheduler
        workflow_scheduler.start()
    except Exception as e:
        print(f"[Lifespan] Workflow scheduler initialization notice: {e}")

    yield

    # Clean shutdown
    try:
        from .workflows.workflow_engine import workflow_scheduler
        workflow_scheduler.stop()
    except Exception:
        pass

    try:
        from .local_wake_listener import stop_local_wake_listener
        stop_local_wake_listener()
    except Exception:
        pass

    if bg_task:
        bg_task.cancel()
    if heartbeat_task:
        heartbeat_task.cancel()

# =========================================================================
# 4. FASTAPI APP INITIALIZATION & SECURITY MIDDLEWARE
# =========================================================================
app = FastAPI(
    title="J.A.R.V.I.S. APEX Omni Workstation",
    version="2.1.0",
    lifespan=lifespan
)

app.add_middleware(RequestCorrelationMiddleware)

# Strict CORS: Only allow explicit trusted local origins, no wildcard '*' with credentials
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Centralized Uniform Exception Handlers
@app.exception_handler(HTTPException)
async def custom_http_exception_handler(request: Request, exc: HTTPException):
    req_id = getattr(request.state, "request_id", "unknown")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.status_code,
                "message": exc.detail
            },
            "request_id": req_id,
            "timestamp": time.time()
        }
    )

@app.exception_handler(Exception)
async def custom_global_exception_handler(request: Request, exc: Exception):
    req_id = getattr(request.state, "request_id", "unknown")
    err_str = redact_secrets(str(exc))
    record_system_error(request.url.path, err_str)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": 500,
                "message": "Internal Server Error",
                "details": err_str
            },
            "request_id": req_id,
            "timestamp": time.time()
        }
    )

# =========================================================================
# 5. CORE SYSTEM & HEALTH CENTER ENDPOINTS
# =========================================================================
@app.get("/api/status")
async def get_status():
    return {
        "status": "online",
        "system": "JARVIS-APEX",
        "version": "2.1.0",
        "privacy": privacy_guard.get_status(),
        "active_websockets": ws_manager.get_active_count()
    }

@app.get("/api/health/diagnostics")
async def get_health_diagnostics_endpoint():
    """Returns real diagnostic telemetry for the System Health Center."""
    return await get_system_diagnostics_report()

@app.get("/api/telemetry")
async def get_telemetry_endpoint():
    return get_system_telemetry()

# =========================================================================
# 6. SECURITY & ACTION CONFIRMATION ENDPOINTS (AUTHENTICATED)
# =========================================================================
@app.get("/api/auth/session")
async def get_session_info(auth: bool = Depends(verify_session_token)):
    return {
        "authenticated": True,
        "environment": settings.ENVIRONMENT,
        "debug": settings.DEBUG
    }

@app.get("/api/os/pending-actions", dependencies=[Depends(verify_session_token)])
async def get_pending_actions_endpoint():
    return {"pending_actions": action_registry.list_pending()}

class ActionConfirmPayload(BaseModel):
    action_id: str

@app.post("/api/os/confirm", dependencies=[Depends(verify_session_token)])
async def confirm_action_endpoint(payload: ActionConfirmPayload):
    ok, msg, action = action_registry.approve(payload.action_id)
    if not ok or not action:
        raise HTTPException(status_code=400, detail=msg)
    
    result = await execute_confirmed_action(action)
    action.status = "executed" if result.get("success") else "failed"
    return {"success": result.get("success", False), "action": action.to_dict(), "result": result}

@app.post("/api/os/reject", dependencies=[Depends(verify_session_token)])
async def reject_action_endpoint(payload: ActionConfirmPayload):
    ok, msg = action_registry.reject(payload.action_id)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

@app.get("/api/security/audit-logs", dependencies=[Depends(verify_session_token)])
async def get_audit_logs_endpoint(limit: int = 50):
    return {"audit_logs": get_recent_audit_logs(limit=limit)}

# Privacy Kill Switches (Authenticated)
@app.get("/api/privacy/status")
async def get_privacy_status_endpoint():
    return privacy_guard.get_status()

class KillSwitchPayload(BaseModel):
    target: str  # mic, screen, wake_listener
    state: bool  # True or False

@app.post("/api/privacy/kill-switch", dependencies=[Depends(verify_session_token)])
async def toggle_kill_switch_endpoint(payload: KillSwitchPayload):
    t = payload.target.lower()
    if t == "mic":
        res = privacy_guard.set_mic_kill_switch(payload.state)
    elif t == "screen":
        res = privacy_guard.set_screen_kill_switch(payload.state)
    elif t in ["wake", "wake_listener"]:
        res = privacy_guard.set_wake_listener(payload.state)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown target '{payload.target}'")
    return {"success": True, "target": t, "new_state": res, "status": privacy_guard.get_status()}

# =========================================================================
# 7. AI MODEL INTELLIGENCE & TELEMETRY ENDPOINTS
# =========================================================================
@app.get("/api/models/telemetry")
async def get_models_telemetry_endpoint():
    return get_model_telemetry()

@app.get("/api/models/catalog")
async def get_models_catalog_endpoint():
    return get_model_catalog()

# =========================================================================
# 8. TRADING STRATEGY LAB & PAPER TRADING ENDPOINTS
# =========================================================================
class BacktestRequest(BaseModel):
    candles: Optional[List[Dict[str, Any]]] = None
    symbol: Optional[str] = "NIFTY50"
    strategy_name: str = "sma_ema_crossover"
    parameters: Optional[Dict[str, Any]] = None
    initial_capital: float = 1000000.0
    slippage_pct: float = 0.05
    fee_pct: float = 0.03

@app.post("/api/trading/backtest")
async def post_backtest_endpoint(req: BacktestRequest):
    candles = req.candles
    if not candles:
        # Load chart candles for the symbol
        candles = await get_chart_candles(symbol=req.symbol or "NIFTY50", interval="15m", limit=120)
    
    result = StrategyLabBacktester.run_backtest(
        candles=candles,
        strategy_name=req.strategy_name,
        params=req.parameters,
        initial_capital=req.initial_capital,
        slippage_pct=req.slippage_pct,
        fee_pct=req.fee_pct
    )
    return result

@app.get("/api/trading/paper/portfolio")
async def get_paper_portfolio_endpoint():
    # Pass live overview prices if available
    overview = await get_market_overview()
    live_map = {}
    if overview and "cards" in overview:
        for c in overview["cards"]:
            s = c.get("symbol")
            p = c.get("current_price")
            if s and p:
                live_map[s] = float(p)
    return PaperTradingPortfolio.get_portfolio_summary(live_prices=live_map)

class PaperOrderRequest(BaseModel):
    symbol: str
    side: str  # BUY or SELL
    quantity: int
    order_type: str = "MARKET"
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

@app.post("/api/trading/paper/order", dependencies=[Depends(verify_session_token)])
async def post_paper_order_endpoint(req: PaperOrderRequest):
    res = PaperTradingPortfolio.execute_order(
        symbol=req.symbol,
        side=req.side,
        quantity=req.quantity,
        order_type=req.order_type,
        price=req.price,
        stop_loss=req.stop_loss,
        take_profit=req.take_profit
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Order rejected."))
    return res

class PaperResetRequest(BaseModel):
    initial_capital: float = 1000000.0
    confirmed: bool = False
    purge_history: bool = False

@app.post("/api/trading/paper/reset", dependencies=[Depends(verify_session_token)])
async def post_paper_reset_endpoint(payload: PaperResetRequest):
    res = PaperTradingPortfolio.reset_account(
        initial_capital=payload.initial_capital,
        confirmed=payload.confirmed,
        purge_history=payload.purge_history
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Reset rejected."))
    return res

@app.get("/api/trading/psychology/analytics")
async def get_psychology_analytics_endpoint():
    return TradingPsychologyEngine.get_psychology_analytics()

@app.get("/api/trading/psychology/entries")
async def get_psychology_entries_endpoint(limit: int = 50):
    return {"entries": TradingPsychologyEngine.get_entries(limit=limit)}

class PsychologyEntryRequest(BaseModel):
    symbol: str
    action: str
    emotion_tag: str
    checklist_answers: List[bool]
    notes: str
    outcome: str = "OPEN"
    pnl: float = 0.0

@app.post("/api/trading/psychology/entry", dependencies=[Depends(verify_session_token)])
async def post_psychology_entry_endpoint(req: PsychologyEntryRequest):
    return TradingPsychologyEngine.record_entry(
        symbol=req.symbol,
        action=req.action,
        emotion_tag=req.emotion_tag,
        checklist_answers=req.checklist_answers,
        notes=req.notes,
        outcome=req.outcome,
        pnl=req.pnl
    )

# =========================================================================
# 9. PERSISTENT MEMORY BRAIN & DEEP RESEARCH WORKSPACE ENDPOINTS (AUTHENTICATED)
# =========================================================================
@app.get("/api/memory", dependencies=[Depends(verify_session_token)])
async def get_memories_endpoint(category: Optional[str] = None, limit: int = 50, offset: int = 0):
    cat_enum = MemoryCategory(category) if category else None
    return {"memories": PersistentMemoryBrain.get_memories(category=cat_enum, limit=limit, offset=offset)}

class AddMemoryRequest(BaseModel):
    category: str
    content: str
    key: Optional[str] = None
    tags: Optional[List[str]] = None
    source: str = "user"

@app.post("/api/memory", dependencies=[Depends(verify_session_token)])
async def post_memory_endpoint(req: AddMemoryRequest):
    cat_enum = MemoryCategory(req.category)
    mem_id = PersistentMemoryBrain.add_memory(
        category=cat_enum,
        content=req.content,
        key=req.key,
        tags=req.tags,
        source=req.source
    )
    return {"success": True, "memory_id": mem_id}

@app.delete("/api/memory/{memory_id}", dependencies=[Depends(verify_session_token)])
async def delete_memory_endpoint(memory_id: str):
    ok = PersistentMemoryBrain.delete_memory(memory_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found.")
    return {"success": True, "message": f"Memory {memory_id} deleted."}

@app.get("/api/memory/search", dependencies=[Depends(verify_session_token)])
async def search_memory_endpoint(q: str = Query(...), category: Optional[str] = None, limit: int = 20):
    cat_enum = MemoryCategory(category) if category else None
    return {"results": PersistentMemoryBrain.search_memories(query=q, category=cat_enum, limit=limit)}

@app.get("/api/memory/export", dependencies=[Depends(verify_session_token)])
async def export_memory_endpoint():
    return PersistentMemoryBrain.export_all_memories()

@app.post("/api/memory/import", dependencies=[Depends(verify_session_token)])
async def import_memory_endpoint(payload: Dict[str, Any]):
    count = PersistentMemoryBrain.import_memories(payload)
    return {"success": True, "imported_count": count}

@app.get("/api/research/jobs")
async def list_research_jobs_endpoint(limit: int = 20):
    return {"jobs": PersistentMemoryBrain.list_research_jobs(limit=limit)}

@app.get("/api/research/jobs/{job_id}")
async def get_research_job_endpoint(job_id: str):
    job = PersistentMemoryBrain.get_research_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Research job not found.")
    return job

# =========================================================================
# 10. VOICE ENGINE & INTERRUPTION ENDPOINTS
# =========================================================================
@app.get("/api/voice/state")
async def get_voice_state_endpoint():
    return {
        "current_state": voice_state_machine.current_state.value,
        "history": voice_state_machine.state_history
    }

@app.post("/api/voice/interrupt", dependencies=[Depends(verify_session_token)])
async def post_voice_interrupt_endpoint():
    """Interrupts active speech and resets listener immediately."""
    return await voice_state_machine.interrupt()

@app.get("/api/voice/devices")
async def get_voice_devices_endpoint():
    return list_audio_devices()

# =========================================================================
# 11. WORKFLOW AUTOMATION STUDIO ENDPOINTS (AUTHENTICATED)
# =========================================================================
@app.get("/api/workflows")
async def list_workflows_endpoint():
    return {"workflows": WorkflowEngine.list_workflows()}

@app.get("/api/workflows/history")
async def get_workflow_history_endpoint(limit: int = 30):
    return {"history": WorkflowEngine.get_run_history(limit=limit)}

@app.post("/api/workflows", dependencies=[Depends(verify_session_token)])
async def create_workflow_endpoint(data: Dict[str, Any]):
    return WorkflowEngine.create_workflow(data)

@app.delete("/api/workflows/{wf_id}", dependencies=[Depends(verify_session_token)])
async def delete_workflow_endpoint(wf_id: str):
    ok = WorkflowEngine.delete_workflow(wf_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return {"success": True, "message": "Workflow deleted."}

@app.post("/api/workflows/{wf_id}/run", dependencies=[Depends(verify_session_token)])
async def run_workflow_endpoint(wf_id: str):
    return await WorkflowEngine.run_workflow(wf_id, is_dry_run=False)

@app.post("/api/workflows/{wf_id}/dry-run", dependencies=[Depends(verify_session_token)])
async def dry_run_workflow_endpoint(wf_id: str):
    return await WorkflowEngine.run_workflow(wf_id, is_dry_run=True)

# =========================================================================
# 12. AUTO-UPDATER ENDPOINTS (AUTHENTICATED)
# =========================================================================
@app.get("/api/updater/version")
async def get_updater_version_endpoint():
    return {"version": SecureAutoUpdater.get_current_version()}

@app.get("/api/updater/check", dependencies=[Depends(verify_session_token)])
async def check_updates_endpoint():
    return await SecureAutoUpdater.check_for_updates()

@app.post("/api/updater/apply", dependencies=[Depends(verify_session_token)])
async def apply_updates_endpoint(manifest: Dict[str, Any]):
    return await SecureAutoUpdater.download_and_apply_update(manifest)

# =========================================================================
# 13. EXISTING MARKET SCAN, VISION & THREAT ENDPOINTS
# =========================================================================
@app.get("/api/scan")
async def get_market_scan_endpoint():
    signals = await scan_market(settings.DEFAULT_SYMBOLS)
    return {"signals": signals, "symbols": settings.DEFAULT_SYMBOLS}

@app.get("/api/market_overview")
async def get_market_overview_endpoint():
    return await get_market_overview()

@app.get("/api/candles")
async def get_candles_endpoint(symbol: str = Query("NIFTY50"), interval: str = Query("15m"), limit: int = Query(100)):
    candles = await get_chart_candles(symbol=symbol, interval=interval, limit=limit)
    return {"symbol": symbol, "interval": interval, "candles": candles}

@app.get("/api/option_chain")
async def get_option_chain_endpoint(symbol: str = Query("NIFTY50")):
    return await get_option_chain(symbol)

@app.get("/api/morning_briefing")
async def get_morning_briefing_endpoint():
    return await generate_morning_briefing()

class ScreenVisionPayload(BaseModel):
    query: Optional[str] = "इस लाइव स्क्रीन का विश्लेषण करें"
    image_base64: Optional[str] = None

@app.post("/api/screen_vision", dependencies=[Depends(verify_session_token)])
async def post_screen_vision_endpoint(payload: Optional[ScreenVisionPayload] = None, query: Optional[str] = None):
    if privacy_guard.screen_kill_switch:
        raise HTTPException(status_code=403, detail="Screen vision is disabled by privacy kill switch.")
    q = (payload.query if payload and payload.query else query) or "इस लाइव स्क्रीन का विश्लेषण करें"
    img_b64 = payload.image_base64 if payload else None
    return await analyze_screen_with_ai(custom_query=q, image_base64=img_b64)

@app.post("/api/screen_patterns", dependencies=[Depends(verify_session_token)])
async def post_screen_patterns_endpoint(payload: Optional[ScreenVisionPayload] = None):
    if privacy_guard.screen_kill_switch:
        raise HTTPException(status_code=403, detail="Screen vision is disabled by privacy kill switch.")
    img_b64 = payload.image_base64 if payload else None
    return await detect_chart_patterns_and_overlays(image_base64=img_b64)

@app.post("/api/screen_ocr", dependencies=[Depends(verify_session_token)])
async def post_screen_ocr_endpoint(payload: Optional[ScreenVisionPayload] = None):
    if privacy_guard.screen_kill_switch:
        raise HTTPException(status_code=403, detail="Screen vision is disabled by privacy kill switch.")
    img_b64 = payload.image_base64 if payload else None
    return await extract_screen_text_and_clipboard(image_base64=img_b64)

class URLAnalysisPayload(BaseModel):
    url: str
    context: Optional[str] = None

@app.post("/api/analyze_url", dependencies=[Depends(verify_session_token)])
async def post_analyze_url_endpoint(payload: URLAnalysisPayload):
    return await analyze_url_threat(payload.url, context_text=payload.context)

class PDFReportRequest(BaseModel):
    url: str
    context: Optional[str] = None
    report_data: Optional[dict] = None

@app.post("/api/generate_pdf_report", dependencies=[Depends(verify_session_token)])
async def generate_pdf_report_endpoint(req: PDFReportRequest):
    data = req.report_data or await analyze_url_threat(req.url, context_text=req.context)
    return generate_url_pdf_report(data)

class ResearchRequest(BaseModel):
    topic: str
    mode: Optional[str] = None

@app.post("/api/research", dependencies=[Depends(verify_session_token)])
async def post_research_endpoint(req: ResearchRequest):
    # Track persistent job in SQLite
    job_id = PersistentMemoryBrain.create_research_job(req.topic, mode=req.mode or "STANDARD")
    
    async def on_progress(event_or_payload, payload=None):
        if payload is not None:
            await ws_manager.broadcast(event_or_payload, payload, channel="research")
            p = payload.get("progress", 0)
            step = payload.get("step", "")
            PersistentMemoryBrain.update_research_job(job_id, p, step)
        else:
            await ws_manager.broadcast("research_progress", event_or_payload, channel="research")
            p = event_or_payload.get("progress", 0)
            step = event_or_payload.get("step", "")
            PersistentMemoryBrain.update_research_job(job_id, p, step)

    try:
        PersistentMemoryBrain.update_research_job(job_id, 10, "Executing deep research...", status="RUNNING")
        report = await run_universal_deep_research(req.topic, requested_mode=req.mode, progress_callback=on_progress)
        PersistentMemoryBrain.update_research_job(job_id, 100, "Research complete", status="COMPLETED", result=report)
        return report
    except Exception as e:
        PersistentMemoryBrain.update_research_job(job_id, 0, "Failed", status="FAILED", error=str(e))
        raise e

@app.get("/api/research/history")
async def get_research_history_endpoint():
    return {"history": get_research_history()}

@app.get("/api/journal")
async def get_journal_endpoint(limit: int = 20):
    return {"journal": get_trading_journal(limit=limit)}

@app.post("/api/journal")
async def post_journal_entry_endpoint(entry: dict):
    return save_trading_journal_entry(
        title=entry.get("title", "Trade Note"),
        symbol=entry.get("symbol", "NIFTY50"),
        outcome=entry.get("outcome", "WIN"),
        notes=entry.get("notes", ""),
        psychology_tags=entry.get("psychology_tags", []),
        pnl=float(entry.get("pnl", 0.0))
    )

@app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(verify_session_token)])
async def chat_endpoint(req: ChatRequest):
    await voice_state_machine.transition_to(VoiceState.THINKING)
    result = await process_user_intent(req.message, progress_callback=ws_manager.broadcast)
    reply_text = result["text"]

    # Ultra-fast speech audio generation with deadline protection
    audio_path = ""
    try:
        await voice_state_machine.transition_to(VoiceState.SPEAKING)
        tts_task = asyncio.create_task(
            generate_speech_file(reply_text, filename=f"reply_{int(time.time()*1000)}.mp3")
        )
        voice_state_machine.register_tts_task(tts_task)
        audio_path = await asyncio.wait_for(asyncio.shield(tts_task), timeout=1.5)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass

    return ChatResponse(
        text=reply_text,
        audio_url=audio_path,
        action_executed=result.get("action_executed"),
        intent=result.get("intent", "general"),
        dynamic_widget=result.get("dynamic_widget")
    )

@app.post("/api/transcribe", dependencies=[Depends(verify_session_token)])
async def transcribe_endpoint(file: UploadFile = File(...)):
    filename = file.filename or "input.wav"
    
    # 1. Immediate extension and filename sanitization check before reading bytes
    is_valid_name, reason = validate_upload_file(filename, 0)
    if not is_valid_name and "size" not in reason.lower():
        raise HTTPException(status_code=400, detail=reason)

    # 2. Chunk-by-chunk bounded streaming read to prevent memory exhaustion
    CHUNK_SIZE = 64 * 1024  # 64 KB
    buffer = bytearray()
    total_read = 0

    while chunk := await file.read(CHUNK_SIZE):
        total_read += len(chunk)
        if total_read > settings.MAX_UPLOAD_SIZE_BYTES:
            await file.close()
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed upload size of {settings.MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)} MB."
            )
        buffer.extend(chunk)

    audio_bytes = bytes(buffer)
    transcript = await transcribe_audio_bytes(audio_bytes, filename=filename)
    return {"text": transcript}

# =========================================================================
# 14. WEBSOCKET ENDPOINT (AUTHENTICATED & ORIGIN VALIDATED)
# =========================================================================
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # Enforce Origin validation and Session Token authentication
    is_valid_auth = await verify_websocket_auth(ws)
    if not is_valid_auth:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized: Missing or invalid session token or untrusted origin.")
        return

    client_id = f"client_{uuid.uuid4().hex[:8]}"
    client = await ws_manager.connect(ws, client_id)

    try:
        # Initial status packet
        telem = get_system_telemetry()
        await ws_manager.send_personal_message(client_id, "telemetry", telem.model_dump())

        while client.is_alive:
            data_raw = await ws.receive_text()
            try:
                data = json.loads(data_raw)
                event = data.get("event")

                if event == "user_message":
                    user_text = data.get("payload", {}).get("text", "")
                    if user_text:
                        await voice_state_machine.transition_to(VoiceState.THINKING)
                        result = await process_user_intent(user_text, progress_callback=ws_manager.broadcast)
                        reply_text = result["text"]
                        dynamic_widget = result.get("dynamic_widget")

                        # Immediate text response dispatch
                        await ws_manager.send_personal_message(client_id, "chat_response", {
                            "text": reply_text,
                            "audio_url": None,
                            "intent": result.get("intent"),
                            "action": result.get("action_executed"),
                            "dynamic_widget": dynamic_widget
                        })

                        if dynamic_widget:
                            await ws_manager.send_personal_message(client_id, "dynamic_widget", dynamic_widget)

                        # Parallel voice generation
                        async def _send_audio():
                            try:
                                await voice_state_machine.transition_to(VoiceState.SPEAKING)
                                audio_url = await generate_speech_file(reply_text, filename=f"ws_reply_{int(time.time()*1000)}.mp3")
                                if audio_url:
                                    await ws_manager.send_personal_message(client_id, "chat_audio", {
                                        "audio_url": audio_url,
                                        "text": reply_text
                                    })
                            except Exception as err:
                                print(f"[WS Audio Error]: {err}")
                            finally:
                                if voice_state_machine.current_state == VoiceState.SPEAKING:
                                    await voice_state_machine.transition_to(VoiceState.IDLE)

                        tts_task = asyncio.create_task(_send_audio())
                        voice_state_machine.register_tts_task(tts_task)

                elif event == "voice_interrupted":
                    await voice_state_machine.interrupt()

                elif event == "pong":
                    client.last_pong = time.time()

            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await ws_manager.disconnect(client_id)
    except Exception as e:
        record_system_error("websocket_endpoint", str(e))
        await ws_manager.disconnect(client_id)

# =========================================================================
# 15. FRONTEND STATIC ASSETS MOUNT
# =========================================================================
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
app.mount("/audio_cache", StaticFiles(directory=str(FRONTEND_DIR / "audio_cache")), name="audio_cache")
REPORTS_DIR = FRONTEND_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/reports", StaticFiles(directory=str(REPORTS_DIR)), name="reports")

@app.get("/")
async def serve_index(request: Request):
    response = FileResponse(FRONTEND_DIR / "index.html")
    # Set secure session token cookie for local client authentication
    response.set_cookie(
        key="session_token",
        value=settings.SESSION_TOKEN,
        httponly=False,
        samesite="lax",
        secure=False
    )
    return response
