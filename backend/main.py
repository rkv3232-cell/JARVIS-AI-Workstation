import asyncio
import json
import time
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional
from pydantic import BaseModel

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import ChatRequest, ChatResponse, WSMessage
from .system_monitor import get_system_telemetry
from .trading_scanner import scan_market, get_option_chain, get_chart_candles, get_market_overview
from .voice_service import generate_speech_file, transcribe_audio_bytes, prewarm_voice_cache
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

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

connected_clients: set[WebSocket] = set()
bg_task = None

async def telemetry_broadcaster():
    """
    Periodically emits hardware telemetry, trading signals, option chain, and morning briefings.
    """
    market_counter = 0
    option_counter = 0

    while True:
        try:
            if connected_clients:
                # 1. Hardware telemetry every 2 seconds
                telem = get_system_telemetry()
                telem_msg = WSMessage(event="telemetry", payload=telem.model_dump())
                telem_json = json.dumps(telem_msg.model_dump())
                
                dead_clients = set()
                for client in connected_clients:
                    try:
                        await client.send_text(telem_json)
                    except Exception:
                        dead_clients.add(client)
                connected_clients.difference_update(dead_clients)

                # 2. Automated Morning Briefing check (@09:00 AM)
                if is_briefing_due():
                    brief = await generate_morning_briefing()
                    brief_msg = WSMessage(event="morning_briefing", payload=brief.model_dump())
                    brief_json = json.dumps(brief_msg.model_dump())
                    for client in list(connected_clients):
                        try:
                            await client.send_text(brief_json)
                        except Exception:
                            pass

                # 3. Market Scan every SCANNER_INTERVAL_SECONDS
                market_counter += 2
                if market_counter >= settings.SCANNER_INTERVAL_SECONDS:
                    market_counter = 0
                    signals = await scan_market(settings.DEFAULT_SYMBOLS)
                    if signals:
                        for sig in signals:
                            log_trade_alert(sig.symbol, sig.signal_type, sig.timeframe, sig.current_price, sig.risk_reward, sig.model_dump())
                        alert_msg = WSMessage(event="trade_alert", payload=[s.model_dump() for s in signals])
                        alert_json = json.dumps(alert_msg.model_dump())
                        for client in list(connected_clients):
                            try:
                                await client.send_text(alert_json)
                            except Exception:
                                pass

                # 4. Option Chain updates every 40 seconds
                option_counter += 2
                if option_counter >= 40:
                    option_counter = 0
                    oc = await get_option_chain("NIFTY50")
                    oc_msg = WSMessage(event="option_chain", payload=oc.model_dump())
                    oc_json = json.dumps(oc_msg.model_dump())
                    for client in list(connected_clients):
                        try:
                            await client.send_text(oc_json)
                        except Exception:
                            pass

                # 5. Live Market Overview & Prices every 6 seconds
                if market_counter % 6 == 0:
                    overview = await get_market_overview()
                    overview_msg = WSMessage(event="market_overview", payload=overview)
                    overview_json = json.dumps(overview_msg.model_dump())
                    for client in list(connected_clients):
                        try:
                            await client.send_text(overview_json)
                        except Exception:
                            pass

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[Broadcaster Error]: {e}")
        await asyncio.sleep(2.0)

async def broadcast_ws_message(event: str, payload: dict):
    """
    Thread-safe broadcaster for dispatching events to all active dashboard WebSocket connections.
    """
    if not connected_clients:
        return
    try:
        msg = WSMessage(event=event, payload=payload)
        msg_json = json.dumps(msg.model_dump())
        dead_clients = set()
        for client in list(connected_clients):
            try:
                await client.send_text(msg_json)
            except Exception:
                dead_clients.add(client)
        connected_clients.difference_update(dead_clients)
    except Exception as err:
        print(f"[WS Broadcaster Error]: {err}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global bg_task
    bg_task = asyncio.create_task(telemetry_broadcaster())
    asyncio.create_task(prewarm_voice_cache())

    # Autonomous Background PC Wake-Word Listener ('Hey Jarvis')
    try:
        from .local_wake_listener import start_local_wake_listener, stop_local_wake_listener
        loop = asyncio.get_running_loop()
        start_local_wake_listener(broadcast_callback=broadcast_ws_message, loop=loop)
    except Exception as e:
        print(f"[Lifespan] Wake listener initialization notice: {e}")

    yield

    try:
        from .local_wake_listener import stop_local_wake_listener
        stop_local_wake_listener()
    except Exception:
        pass

    if bg_task:
        bg_task.cancel()

app = FastAPI(title="JARVIS-APEX Command Center", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST API Endpoints
@app.get("/api/status")
async def get_status():
    return {"status": "online", "system": "JARVIS-APEX", "version": "2.0.0", "firebase": settings.FIREBASE_PROJECT_ID}

@app.get("/api/wake_status")
async def get_wake_status():
    from .local_wake_listener import get_wake_listener
    l = get_wake_listener()
    return {
        "is_running": l.is_running,
        "model_loaded": l.model is not None,
        "is_capturing_command": l.is_capturing_command,
        "is_processing": l.is_processing,
        "thread_alive": l.thread.is_alive() if l.thread else False
    }

@app.get("/api/telemetry")
async def get_telemetry_endpoint():
    return get_system_telemetry()

@app.get("/api/scan")
async def get_market_scan_endpoint():
    signals = await scan_market(settings.DEFAULT_SYMBOLS)
    return {"signals": signals, "symbols": settings.DEFAULT_SYMBOLS}

@app.get("/api/market_overview")
async def get_market_overview_endpoint():
    overview = await get_market_overview()
    return overview

@app.get("/api/candles")
async def get_candles_endpoint(symbol: str = Query("NIFTY50"), interval: str = Query("15m"), limit: int = Query(100)):
    candles = await get_chart_candles(symbol=symbol, interval=interval, limit=limit)
    return {"symbol": symbol, "interval": interval, "candles": candles}

@app.get("/api/option_chain")
async def get_option_chain_endpoint(symbol: str = Query("NIFTY50")):
    oc = await get_option_chain(symbol)
    return oc

@app.get("/api/morning_briefing")
async def get_morning_briefing_endpoint():
    brief = await generate_morning_briefing()
    return brief

class ScreenVisionPayload(BaseModel):
    query: Optional[str] = "इस लाइव स्क्रीन का विश्लेषण करें"
    image_base64: Optional[str] = None

@app.post("/api/screen_vision")
async def post_screen_vision_endpoint(payload: Optional[ScreenVisionPayload] = None, query: Optional[str] = None):
    q = (payload.query if payload and payload.query else query) or "इस लाइव स्क्रीन का विश्लेषण करें"
    img_b64 = payload.image_base64 if payload else None
    analysis = await analyze_screen_with_ai(custom_query=q, image_base64=img_b64)
    return analysis

@app.post("/api/screen_patterns")
async def post_screen_patterns_endpoint(payload: Optional[ScreenVisionPayload] = None):
    img_b64 = payload.image_base64 if payload else None
    res = await detect_chart_patterns_and_overlays(image_base64=img_b64)
    return res

@app.post("/api/screen_ocr")
async def post_screen_ocr_endpoint(payload: Optional[ScreenVisionPayload] = None):
    img_b64 = payload.image_base64 if payload else None
    res = await extract_screen_text_and_clipboard(image_base64=img_b64)
    return res

class URLAnalysisPayload(BaseModel):
    url: str
    context: Optional[str] = None

@app.post("/api/analyze_url")
async def post_analyze_url_endpoint(payload: URLAnalysisPayload):
    report = await analyze_url_threat(payload.url, context_text=payload.context)
    return report

class PDFReportRequest(BaseModel):
    url: str
    context: Optional[str] = None
    report_data: Optional[dict] = None

@app.post("/api/generate_pdf_report")
async def generate_pdf_report_endpoint(req: PDFReportRequest):
    data = req.report_data
    if not data:
        data = await analyze_url_threat(req.url, context_text=req.context)
    pdf_info = generate_url_pdf_report(data)
    return pdf_info

class ResearchRequest(BaseModel):
    topic: str
    mode: Optional[str] = None

@app.post("/api/research")
async def post_research_endpoint(req: ResearchRequest):
    async def on_progress(event_or_payload, payload=None):
        if payload is not None:
            await broadcast_ws_message(event_or_payload, payload)
        else:
            await broadcast_ws_message("research_progress", event_or_payload)
    report = await run_universal_deep_research(req.topic, requested_mode=req.mode, progress_callback=on_progress)
    return report

@app.get("/api/research/history")
async def get_research_history_endpoint():
    return {"history": get_research_history()}

@app.get("/api/journal")
async def get_journal_endpoint(limit: int = 20):
    return {"journal": get_trading_journal(limit=limit)}

@app.post("/api/journal")
async def post_journal_entry_endpoint(entry: dict):
    saved = save_trading_journal_entry(
        title=entry.get("title", "Trade Note"),
        symbol=entry.get("symbol", "NIFTY50"),
        outcome=entry.get("outcome", "WIN"),
        notes=entry.get("notes", ""),
        psychology_tags=entry.get("psychology_tags", []),
        pnl=float(entry.get("pnl", 0.0))
    )
    return saved

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    result = await process_user_intent(req.message, progress_callback=broadcast_ws_message)
    reply_text = result["text"]
    
    # Ultra-fast speech audio generation with 1.5s deadline protection
    audio_path = ""
    try:
        audio_path = await asyncio.wait_for(
            generate_speech_file(reply_text, filename=f"reply_{int(time.time()*1000)}.mp3"),
            timeout=1.5
        )
    except asyncio.TimeoutError:
        # Background generation so user gets text response instantly
        asyncio.create_task(generate_speech_file(reply_text, filename=f"reply_{int(time.time()*1000)}.mp3"))
    
    return ChatResponse(
        text=reply_text,
        audio_url=audio_path,
        action_executed=result.get("action_executed"),
        intent=result.get("intent", "general"),
        dynamic_widget=result.get("dynamic_widget")
    )

@app.post("/api/transcribe")
async def transcribe_endpoint(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    filename = file.filename or "input.wav"
    transcript = await transcribe_audio_bytes(audio_bytes, filename=filename)
    return {"text": transcript}

# WebSocket Endpoint
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.add(ws)
    try:
        # Initial status packet
        telem = get_system_telemetry()
        await ws.send_text(json.dumps(WSMessage(event="telemetry", payload=telem.model_dump()).model_dump()))
        
        while True:
            data_raw = await ws.receive_text()
            try:
                data = json.loads(data_raw)
                event = data.get("event")
                if event == "user_message":
                    user_text = data.get("payload", {}).get("text", "")
                    if user_text:
                        result = await process_user_intent(user_text, progress_callback=broadcast_ws_message)
                        reply_text = result["text"]
                        dynamic_widget = result.get("dynamic_widget")
                        
                        # 1. IMMEDIATE DISPATCH: Send text response instantly (<200ms)
                        resp_msg = WSMessage(
                            event="chat_response",
                            payload={
                                "text": reply_text,
                                "audio_url": None,
                                "intent": result.get("intent"),
                                "action": result.get("action_executed"),
                                "dynamic_widget": dynamic_widget
                            }
                        )
                        await ws.send_text(json.dumps(resp_msg.model_dump()))

                        # Send dynamic autonomous widget projection if available
                        if dynamic_widget:
                            await ws.send_text(json.dumps(WSMessage(
                                event="dynamic_widget",
                                payload=dynamic_widget
                            ).model_dump()))
                        
                        # 2. Async parallel audio generation (Sarvam AI / Edge-TTS)
                        async def send_sarvam_audio(text: str, socket: WebSocket):
                            try:
                                audio_url = await generate_speech_file(text, filename=f"ws_reply_{int(time.time()*1000)}.mp3")
                                if audio_url:
                                    audio_msg = WSMessage(
                                        event="chat_audio",
                                        payload={"audio_url": audio_url, "text": text}
                                    )
                                    await socket.send_text(json.dumps(audio_msg.model_dump()))
                            except Exception as err:
                                print(f"[WS] Parallel audio generation exception: {err}")

                        asyncio.create_task(send_sarvam_audio(reply_text, ws))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        connected_clients.discard(ws)
    except Exception as e:
        print(f"[WS Error]: {e}")
        connected_clients.discard(ws)

# Mount frontend static files
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
app.mount("/audio_cache", StaticFiles(directory=str(FRONTEND_DIR / "audio_cache")), name="audio_cache")
REPORTS_DIR = FRONTEND_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/reports", StaticFiles(directory=str(REPORTS_DIR)), name="reports")

@app.get("/")
async def serve_index():
    return FileResponse(FRONTEND_DIR / "index.html")
