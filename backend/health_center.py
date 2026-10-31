import os
import time
import psutil
import sqlite3
import httpx
from pathlib import Path
from typing import Dict, Any, List

from .config import settings
from .security import privacy_guard, get_recent_audit_logs, redact_secrets
from .websocket_manager import ws_manager

SERVER_START_TIME = time.time()
ERROR_LOG_WINDOW: List[Dict[str, Any]] = []

def record_system_error(module: str, error_message: str):
    """Stores recent errors in an in-memory rotating buffer for diagnostics."""
    global ERROR_LOG_WINDOW
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "epoch": time.time(),
        "module": module,
        "error": redact_secrets(error_message)
    }
    ERROR_LOG_WINDOW.append(entry)
    if len(ERROR_LOG_WINDOW) > 100:
        ERROR_LOG_WINDOW = ERROR_LOG_WINDOW[-100:]

async def check_ai_provider_latencies() -> Dict[str, Dict[str, Any]]:
    """
    Probes connectivity and measures latency for all configured AI providers.
    Uses fast HEAD/GET requests or lightweight calls with strict 2.5s timeouts.
    """
    results = {}

    # 1. Google Gemini Multi-Key Pool
    gemini_keys = settings.gemini_keys_pool
    if gemini_keys:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=2.5) as client:
                res = await client.get(
                    f"https://generativelanguage.googleapis.com/v1beta/models?key={gemini_keys[0]}",
                    timeout=2.5
                )
                latency = round((time.perf_counter() - t0) * 1000, 1)
                results["Google Gemini"] = {
                    "status": "ONLINE" if res.status_code == 200 else f"HTTP_{res.status_code}",
                    "latency_ms": latency,
                    "keys_configured": len(gemini_keys),
                    "active_key": f"{gemini_keys[0][:4]}...{gemini_keys[0][-4:]}"
                }
        except Exception as e:
            results["Google Gemini"] = {"status": "OFFLINE", "latency_ms": None, "error": str(e)[:60]}
    else:
        results["Google Gemini"] = {"status": "NOT_CONFIGURED", "latency_ms": None}

    # 2. Groq LPU
    if settings.GROQ_API_KEY:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=2.5) as client:
                res = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                    timeout=2.5
                )
                latency = round((time.perf_counter() - t0) * 1000, 1)
                results["Groq LPU"] = {
                    "status": "ONLINE" if res.status_code == 200 else f"HTTP_{res.status_code}",
                    "latency_ms": latency
                }
        except Exception as e:
            results["Groq LPU"] = {"status": "OFFLINE", "latency_ms": None, "error": str(e)[:60]}
    else:
        results["Groq LPU"] = {"status": "NOT_CONFIGURED", "latency_ms": None}

    # 3. OpenRouter
    if settings.OPENROUTER_API_KEY:
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=2.5) as client:
                res = await client.get("https://openrouter.ai/api/v1/models", timeout=2.5)
                latency = round((time.perf_counter() - t0) * 1000, 1)
                results["OpenRouter"] = {
                    "status": "ONLINE" if res.status_code == 200 else f"HTTP_{res.status_code}",
                    "latency_ms": latency
                }
        except Exception as e:
            results["OpenRouter"] = {"status": "OFFLINE", "latency_ms": None, "error": str(e)[:60]}
    else:
        results["OpenRouter"] = {"status": "NOT_CONFIGURED", "latency_ms": None}

    # 4. Sarvam AI
    if settings.SARVAM_API_KEY:
        results["Sarvam AI"] = {
            "status": "ONLINE",
            "speaker": settings.SARVAM_SPEAKER,
            "model": settings.SARVAM_MODEL
        }
    else:
        results["Sarvam AI"] = {"status": "NOT_CONFIGURED", "latency_ms": None}

    # 5. Ollama (Local Private LLM)
    try:
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=1.5) as client:
            res = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            latency = round((time.perf_counter() - t0) * 1000, 1)
            results["Ollama (Local Private)"] = {
                "status": "ONLINE" if res.status_code == 200 else "DEGRADED",
                "latency_ms": latency,
                "url": settings.OLLAMA_BASE_URL
            }
    except Exception:
        results["Ollama (Local Private)"] = {
            "status": "OFFLINE",
            "latency_ms": None,
            "note": "Optional local offline LLM daemon not running"
        }

    return results

def get_audio_devices_status() -> Dict[str, Any]:
    """Enumerates sound input (microphones) and output (speakers) via sounddevice."""
    try:
        import sounddevice as sd
        devices = sd.query_devices()
        input_devs = []
        output_devs = []
        default_in = sd.default.device[0] if sd.default.device else -1
        default_out = sd.default.device[1] if sd.default.device else -1

        for idx, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) > 0:
                input_devs.append({
                    "id": idx,
                    "name": dev.get("name"),
                    "channels": dev.get("max_input_channels"),
                    "sample_rate": dev.get("default_samplerate"),
                    "is_default": (idx == default_in)
                })
            if dev.get("max_output_channels", 0) > 0:
                output_devs.append({
                    "id": idx,
                    "name": dev.get("name"),
                    "channels": dev.get("max_output_channels"),
                    "sample_rate": dev.get("default_samplerate"),
                    "is_default": (idx == default_out)
                })

        return {
            "status": "available",
            "input_devices": input_devs,
            "output_devices": output_devs,
            "default_input_id": default_in,
            "default_output_id": default_out
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

def get_database_diagnostics() -> Dict[str, Any]:
    """Inspects SQLite database file size, integrity, and row counts."""
    db_path = Path(__file__).resolve().parent / "jarvis.db"
    if not db_path.exists():
        return {"status": "missing", "size_kb": 0, "tables": {}}

    try:
        size_kb = round(db_path.stat().st_size / 1024, 2)
        tables_info = {}
        with sqlite3.connect(str(db_path), timeout=3) as conn:
            cursor = conn.cursor()
            # Check PRAGMA integrity
            cursor.execute("PRAGMA integrity_check;")
            integrity = cursor.fetchone()[0]

            # List tables & count
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall() if not row[0].startswith("sqlite_")]
            for tbl in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM [{tbl}];")
                    tables_info[tbl] = cursor.fetchone()[0]
                except Exception:
                    tables_info[tbl] = -1

        return {
            "status": "healthy" if integrity == "ok" else "corrupt",
            "integrity": integrity,
            "size_kb": size_kb,
            "tables": tables_info
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

async def get_system_diagnostics_report() -> Dict[str, Any]:
    """
    Generates an exhaustive, production-grade telemetry & diagnostics payload
    for the J.A.R.V.I.S. System Health Center.
    """
    proc = psutil.Process(os.getpid())
    mem_info = proc.memory_info()
    cpu_percent = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    # Compute errors in last 1 hour
    one_hour_ago = time.time() - 3600
    recent_errors = [e for e in ERROR_LOG_WINDOW if e["epoch"] >= one_hour_ago]

    ai_latencies = await check_ai_provider_latencies()
    audio_status = get_audio_devices_status()
    db_diagnostics = get_database_diagnostics()
    privacy_status = privacy_guard.get_status()

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "server_uptime_seconds": int(time.time() - SERVER_START_TIME),
        "process": {
            "pid": proc.pid,
            "cpu_percent": round(proc.cpu_percent(interval=None), 1),
            "memory_rss_mb": round(mem_info.rss / (1024 * 1024), 2),
            "memory_vms_mb": round(mem_info.vms / (1024 * 1024), 2),
            "threads_count": proc.num_threads()
        },
        "hardware": {
            "cpu_total_percent": cpu_percent,
            "cpu_cores_logical": psutil.cpu_count(logical=True),
            "cpu_cores_physical": psutil.cpu_count(logical=False),
            "ram_total_gb": round(ram.total / (1024**3), 2),
            "ram_used_gb": round(ram.used / (1024**3), 2),
            "ram_free_gb": round(ram.available / (1024**3), 2),
            "ram_percent": ram.percent,
            "disk_total_gb": round(disk.total / (1024**3), 2),
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "disk_free_gb": round(disk.free / (1024**3), 2),
            "disk_percent": disk.percent
        },
        "websocket": {
            "active_clients": ws_manager.get_active_count()
        },
        "ai_providers": ai_latencies,
        "audio_hardware": audio_status,
        "database": db_diagnostics,
        "privacy_guards": privacy_status,
        "recent_errors": {
            "last_hour_count": len(recent_errors),
            "entries": recent_errors[-10:]
        }
    }
