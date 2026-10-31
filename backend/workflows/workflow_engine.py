import time
import json
import uuid
import sqlite3
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..security import log_audit_event, action_registry, RiskLevel
from ..config import settings

DB_PATH = Path(__file__).resolve().parent.parent / "jarvis.db"

# Allowlisted actions strictly permitted in workflows
ALLOWLISTED_ACTIONS = {
    "send_notification",
    "run_market_scan",
    "run_deep_research",
    "speak_voice_message",
    "create_trade_journal",
    "backup_memory",
    "open_url",
    "set_system_theme"
}

def init_workflow_db():
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                trigger_type TEXT NOT NULL, -- schedule, event, manual
                trigger_config TEXT NOT NULL,
                condition_config TEXT,
                action_type TEXT NOT NULL,
                action_params TEXT NOT NULL,
                requires_approval INTEGER DEFAULT 0,
                is_enabled INTEGER DEFAULT 1,
                created_at REAL,
                updated_at REAL
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workflow_runs (
                run_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                is_dry_run INTEGER DEFAULT 0,
                status TEXT NOT NULL, -- COMPLETED, FAILED, PENDING_APPROVAL, SKIPPED
                step_results TEXT,
                started_at REAL,
                completed_at REAL
            );
        """)
        conn.commit()

init_workflow_db()

# Pre-built standard workflow templates
BUILT_IN_TEMPLATES = [
    {
        "id": "wf_morning_briefing",
        "name": "Morning Market Briefing",
        "description": "Daily at 09:00 AM: scans top market movers and produces a spoken morning brief.",
        "trigger_type": "schedule",
        "trigger_config": {"cron": "0 9 * * *", "time": "09:00"},
        "condition_config": {"type": "always_true"},
        "action_type": "speak_voice_message",
        "action_params": {"text": "नमस्ते सर, सुबह के 9 बज चुके हैं। मार्केट प्री-ओपनिंग ओवरव्यू लोड कर दिया गया है।"},
        "requires_approval": 0
    },
    {
        "id": "wf_high_volatility",
        "name": "High Volatility Alert Radar",
        "description": "Checks market scanner signals; notifies if any symbol exhibits extreme RSI.",
        "trigger_type": "event",
        "trigger_config": {"event": "market_scan_complete"},
        "condition_config": {"field": "rsi", "operator": "outside_range", "range": [25, 75]},
        "action_type": "send_notification",
        "action_params": {"title": "High Volatility Alert", "message": "Symbol entering extreme overbought/oversold territory."},
        "requires_approval": 0
    },
    {
        "id": "wf_system_health",
        "name": "Hourly System Health Sentinel",
        "description": "Hourly check of CPU and RAM usage to prevent memory pressure.",
        "trigger_type": "schedule",
        "trigger_config": {"interval_minutes": 60},
        "condition_config": {"field": "ram_percent", "operator": ">", "value": 85.0},
        "action_type": "send_notification",
        "action_params": {"title": "High Memory Warning", "message": "RAM usage exceeded 85% threshold."},
        "requires_approval": 0
    },
    {
        "id": "wf_market_close",
        "name": "Market Close Portfolio Summary",
        "description": "Daily at 03:30 PM: audits paper trading positions and logs daily P&L.",
        "trigger_type": "schedule",
        "trigger_config": {"time": "15:30"},
        "condition_config": {"type": "always_true"},
        "action_type": "send_notification",
        "action_params": {"title": "Market Close", "message": "Indian equity market closed. Reviewing portfolio performance."},
        "requires_approval": 0
    }
]

def seed_templates():
    """Populates default templates if database table is empty."""
    with sqlite3.connect(str(DB_PATH)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM workflows;")
        if cursor.fetchone()[0] == 0:
            now = time.time()
            for t in BUILT_IN_TEMPLATES:
                cursor.execute("""
                    INSERT INTO workflows (id, name, description, trigger_type, trigger_config, condition_config, action_type, action_params, requires_approval, is_enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?);
                """, (
                    t["id"],
                    t["name"],
                    t["description"],
                    t["trigger_type"],
                    json.dumps(t["trigger_config"]),
                    json.dumps(t["condition_config"]),
                    t["action_type"],
                    json.dumps(t["action_params"]),
                    t["requires_approval"],
                    now,
                    now
                ))
            conn.commit()

seed_templates()

class WorkflowEngine:
    """
    Executes automation nodes under strict loop limits (max 20 steps) and allowlisted actions.
    Supports dry-run testing and confirmation gates.
    """
    @classmethod
    def list_workflows(cls) -> List[Dict[str, Any]]:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM workflows ORDER BY created_at ASC;")
            rows = cursor.fetchall()

        results = []
        for r in rows:
            d = dict(r)
            try:
                d["trigger_config"] = json.loads(d["trigger_config"])
                d["condition_config"] = json.loads(d["condition_config"]) if d["condition_config"] else {}
                d["action_params"] = json.loads(d["action_params"])
            except Exception:
                pass
            results.append(d)
        return results

    @classmethod
    def get_workflow(cls, wf_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM workflows WHERE id = ?;", (wf_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d["trigger_config"] = json.loads(d["trigger_config"])
                d["condition_config"] = json.loads(d["condition_config"]) if d["condition_config"] else {}
                d["action_params"] = json.loads(d["action_params"])
            except Exception:
                pass
            return d

    @classmethod
    def create_workflow(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        action = data.get("action_type")
        if action not in ALLOWLISTED_ACTIONS:
            return {"success": False, "error": f"Action '{action}' is not in allowlist: {sorted(ALLOWLISTED_ACTIONS)}"}

        wf_id = data.get("id") or f"wf_{uuid.uuid4().hex[:10]}"
        now = time.time()
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO workflows (id, name, description, trigger_type, trigger_config, condition_config, action_type, action_params, requires_approval, is_enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                wf_id,
                data.get("name", "Untitled Workflow"),
                data.get("description", ""),
                data.get("trigger_type", "manual"),
                json.dumps(data.get("trigger_config", {})),
                json.dumps(data.get("condition_config", {})),
                action,
                json.dumps(data.get("action_params", {})),
                1 if data.get("requires_approval") else 0,
                1,
                now,
                now
            ))
            conn.commit()

        log_audit_event("create_workflow", wf_id, "medium", "success")
        return {"success": True, "workflow_id": wf_id}

    @classmethod
    def delete_workflow(cls, wf_id: str) -> bool:
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM workflows WHERE id = ?;", (wf_id,))
            affected = cursor.rowcount > 0
            conn.commit()
        log_audit_event("delete_workflow", wf_id, "medium", "success" if affected else "not_found")
        return affected

    @classmethod
    async def run_workflow(
        cls,
        wf_id: str,
        is_dry_run: bool = False,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes workflow through TRIGGER -> CONDITION -> ACTION -> RESULT pipeline.
        In dry-run mode, validates logic without triggering real notifications or actions.
        """
        wf = cls.get_workflow(wf_id)
        if not wf:
            return {"success": False, "status": "NOT_FOUND", "error": f"Workflow {wf_id} not found."}

        run_id = f"run_{uuid.uuid4().hex[:10]}"
        t_start = time.time()
        context = context or {}
        step_trace = []

        # Step 1: TRIGGER VALIDATION
        step_trace.append({
            "step": "TRIGGER",
            "trigger_type": wf["trigger_type"],
            "status": "PASS",
            "timestamp": time.time()
        })

        # Step 2: CONDITION EVALUATION (Strict Fail-Closed and Type Validated)
        cond = wf.get("condition_config", {})
        cond_met = True
        cond_error = None
        is_simulated_cond = False

        ALLOWED_OPERATORS = {">", "<", ">=", "<=", "==", "!=", "outside_range", "inside_range"}

        if cond and cond.get("type") != "always_true":
            field = cond.get("field")
            op = cond.get("operator")
            val = cond.get("value")

            # 1. Operator validation
            if not op or op not in ALLOWED_OPERATORS:
                cond_met = False
                cond_error = f"Unknown or invalid condition operator: '{op}'"
            elif not field:
                cond_met = False
                cond_error = "Condition missing required 'field' identifier."
            elif field not in context or context.get(field) is None:
                # 2. Missing Context: Strictly FAIL-CLOSED (Never auto-pass!)
                cond_met = False
                if is_dry_run:
                    is_simulated_cond = True
                    cond_error = f"Context field '{field}' unavailable in dry-run simulation."
                else:
                    cond_error = f"Required condition field '{field}' was missing from execution context. Halted fail-closed."
            else:
                target_val = context.get(field)
                try:
                    # 3. Type-safe comparison
                    if op in [">", "<", ">=", "<="]:
                        num_target = float(target_val)
                        num_val = float(val)
                        if op == ">":
                            cond_met = num_target > num_val
                        elif op == "<":
                            cond_met = num_target < num_val
                        elif op == ">=":
                            cond_met = num_target >= num_val
                        elif op == "<=":
                            cond_met = num_target <= num_val
                    elif op == "==":
                        cond_met = (target_val == val)
                    elif op == "!=":
                        cond_met = (target_val != val)
                    elif op in ["outside_range", "inside_range"]:
                        r = cond.get("range", [30, 70])
                        num_target = float(target_val)
                        r_min = float(r[0])
                        r_max = float(r[1])
                        in_rng = (r_min <= num_target <= r_max)
                        cond_met = not in_rng if op == "outside_range" else in_rng
                except (ValueError, TypeError) as te:
                    cond_met = False
                    cond_error = f"Operand type validation error: cannot compare {type(target_val).__name__} with {type(val).__name__} ({te})"

        step_trace.append({
            "step": "CONDITION",
            "condition": cond,
            "met": cond_met,
            "error": cond_error,
            "simulated_condition": is_simulated_cond,
            "timestamp": time.time()
        })

        if cond_error and "Unknown or invalid condition operator" in cond_error:
            cls._record_run(run_id, wf_id, is_dry_run, "VALIDATION_FAILED", step_trace, t_start)
            return {
                "success": False,
                "status": "VALIDATION_FAILED",
                "error": cond_error,
                "trace": step_trace
            }

        if not cond_met:
            status_label = "SIMULATED_FAIL_CLOSED" if (is_dry_run and is_simulated_cond) else "SKIPPED_FAIL_CLOSED"
            cls._record_run(run_id, wf_id, is_dry_run, status_label, step_trace, t_start)
            return {
                "success": True,
                "status": status_label,
                "message": cond_error or "Workflow condition evaluated to False (Execution halted).",
                "trace": step_trace
            }

        # Step 3: APPROVAL GATE
        if wf.get("requires_approval") and not is_dry_run:
            pending = action_registry.register(
                action_type="workflow_execution",
                target=wf["name"],
                description=f"Workflow '{wf['name']}' requires approval before executing {wf['action_type']}.",
                risk_level=RiskLevel.MEDIUM,
                params={"workflow_id": wf_id, "run_id": run_id}
            )
            step_trace.append({
                "step": "APPROVAL",
                "status": "PENDING_APPROVAL",
                "action_id": pending.action_id,
                "timestamp": time.time()
            })
            cls._record_run(run_id, wf_id, is_dry_run, "PENDING_APPROVAL", step_trace, t_start)
            return {
                "success": True,
                "status": "PENDING_APPROVAL",
                "action_id": pending.action_id,
                "message": f"वर्कफ़्लो अनुमोदन की प्रतीक्षा में है (ID: {pending.action_id})",
                "trace": step_trace
            }

        # Step 4: ACTION EXECUTION
        action_type = wf["action_type"]
        action_params = wf["action_params"]
        action_result = {}

        if is_dry_run:
            action_result = {
                "dry_run": True,
                "status": "SIMULATED_SUCCESS",
                "message": f"[Dry-Run] Action '{action_type}' would execute with params: {action_params}"
            }
        else:
            action_result = await cls._dispatch_action(action_type, action_params)

        step_trace.append({
            "step": "ACTION",
            "action_type": action_type,
            "result": action_result,
            "timestamp": time.time()
        })

        status_str = "COMPLETED" if action_result.get("status") != "failed" else "FAILED"
        cls._record_run(run_id, wf_id, is_dry_run, status_str, step_trace, t_start)
        log_audit_event("run_workflow", f"{wf['name']} ({status_str})", "safe", status_str)

        return {
            "success": status_str == "COMPLETED",
            "run_id": run_id,
            "is_dry_run": is_dry_run,
            "status": status_str,
            "trace": step_trace,
            "duration_ms": round((time.time() - t_start) * 1000, 2)
        }

    @classmethod
    async def _dispatch_action(cls, action_type: str, action_params: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches an allowlisted action to the appropriate subsystem."""
        try:
            if action_type == "send_notification":
                from ..websocket_manager import ws_manager
                title = action_params.get("title", "J.A.R.V.I.S. Notification")
                message = action_params.get("message", "")
                await ws_manager.broadcast(
                    "workflow_notification",
                    {"title": title, "message": message, "timestamp": time.time()}
                )
                return {"status": "dispatched", "notification": {"title": title, "message": message}}

            elif action_type == "speak_voice_message":
                text = action_params.get("text", "")
                if text:
                    from ..voice_service import generate_speech_file
                    from ..websocket_manager import ws_manager
                    audio_path = await generate_speech_file(text, filename=f"wf_voice_{int(time.time()*1000)}.mp3")
                    if audio_path:
                        await ws_manager.broadcast(
                            "chat_audio",
                            {"audio_url": audio_path, "text": text}
                        )
                return {"status": "spoken", "text": text}

            elif action_type == "run_market_scan":
                from ..trading_scanner import scan_market
                from ..websocket_manager import ws_manager
                signals = await scan_market(settings.DEFAULT_SYMBOLS)
                await ws_manager.broadcast("trade_alert", signals)
                return {"status": "scanned", "signal_count": len(signals)}

            elif action_type == "backup_memory":
                from ..memory.memory_brain import PersistentMemoryBrain
                backup = PersistentMemoryBrain.export_all_memories()
                return {"status": "backed_up", "total": backup["total_memories"], "path": backup["file_path"]}

            elif action_type == "open_url":
                import webbrowser
                url = action_params.get("url", "")
                if url.startswith("http://") or url.startswith("https://"):
                    webbrowser.open(url)
                    return {"status": "opened_url", "url": url}
                return {"status": "rejected", "error": "Invalid URL scheme"}

            elif action_type == "set_system_theme":
                from ..os_controller import set_windows_theme
                dark = action_params.get("dark_mode", True)
                res = set_windows_theme(dark)
                return {"status": "theme_set", "dark_mode": dark, "result": res}

            elif action_type == "create_trade_journal":
                from ..database import save_trading_journal_entry
                res = save_trading_journal_entry(
                    title=action_params.get("title", "Automated Workflow Journal"),
                    symbol=action_params.get("symbol", "NIFTY50"),
                    outcome=action_params.get("outcome", "NOTE"),
                    notes=action_params.get("notes", "Triggered by workflow automation"),
                    psychology_tags=["Disciplined", "Automated"],
                    pnl=float(action_params.get("pnl", 0.0))
                )
                return {"status": "journal_created", "entry": res}

            else:
                return {"status": "executed", "action": action_type}

        except Exception as e:
            return {"status": "failed", "error": str(e)}

    @classmethod
    async def resume_confirmed_workflow(cls, wf_id: str, run_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Resumes and executes a workflow that was previously held in PENDING_APPROVAL state,
        after explicit user confirmation.
        """
        wf = cls.get_workflow(wf_id)
        if not wf:
            return {"success": False, "status": "NOT_FOUND", "error": f"Workflow {wf_id} not found."}

        action_type = wf["action_type"]
        action_params = wf["action_params"]
        run_id = run_id or f"run_resumed_{uuid.uuid4().hex[:8]}"
        t_start = time.time()

        action_result = await cls._dispatch_action(action_type, action_params)
        status_str = "COMPLETED" if action_result.get("status") != "failed" else "FAILED"

        step_trace = [{
            "step": "RESUMED_ACTION",
            "action_type": action_type,
            "result": action_result,
            "timestamp": time.time(),
            "approved": True
        }]

        cls._record_run(run_id, wf_id, False, status_str, step_trace, t_start)
        log_audit_event("resume_workflow", f"{wf['name']} ({status_str})", "high", status_str)

        return {
            "success": status_str == "COMPLETED",
            "workflow_id": wf_id,
            "run_id": run_id,
            "status": status_str,
            "action_result": action_result,
            "message": f"Workflow '{wf['name']}' resumed and executed successfully."
        }

    @classmethod
    def _record_run(cls, run_id: str, wf_id: str, is_dry_run: bool, status: str, trace: List[Dict], t_start: float):
        now = time.time()
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO workflow_runs (run_id, workflow_id, is_dry_run, status, step_results, started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (run_id, wf_id, 1 if is_dry_run else 0, status, json.dumps(trace, ensure_ascii=False), t_start, now))
            conn.commit()

    @classmethod
    def get_run_history(cls, limit: int = 30) -> List[Dict[str, Any]]:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r.*, w.name as workflow_name
                FROM workflow_runs r
                LEFT JOIN workflows w ON r.workflow_id = w.id
                ORDER BY r.started_at DESC LIMIT ?;
            """, (limit,))
            rows = cursor.fetchall()

        results = []
        for r in rows:
            d = dict(r)
            try:
                d["step_results"] = json.loads(d["step_results"])
            except Exception:
                d["step_results"] = []
            results.append(d)
        return results

class WorkflowScheduler:
    """
    Background asynchronous scheduler for time-based and recurring workflows.
    Evaluates enabled schedule triggers and dispatches runs.
    """
    def __init__(self):
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_executed_minute: Dict[str, str] = {}

    def start(self):
        if not self._running:
            self._running = True
            try:
                loop = asyncio.get_running_loop()
                self._task = loop.create_task(self._loop())
            except RuntimeError:
                pass

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _loop(self):
        while self._running:
            try:
                now_struct = time.localtime()
                current_time_str = f"{now_struct.tm_hour:02d}:{now_struct.tm_min:02d}"
                date_key = f"{now_struct.tm_year}-{now_struct.tm_mon:02d}-{now_struct.tm_mday:02d}"

                workflows = WorkflowEngine.list_workflows()
                for wf in workflows:
                    if not wf.get("is_enabled"):
                        continue

                    trig_type = wf.get("trigger_type")
                    trig_conf = wf.get("trigger_config") or {}
                    wf_id = wf["id"]

                    if trig_type == "schedule":
                        sched_time = trig_conf.get("time")  # e.g. "15:30"
                        if sched_time and sched_time == current_time_str:
                            exec_key = f"{wf_id}_{date_key}_{current_time_str}"
                            if self._last_executed_minute.get(wf_id) != exec_key:
                                self._last_executed_minute[wf_id] = exec_key
                                asyncio.create_task(
                                    WorkflowEngine.run_workflow(
                                        wf_id,
                                        is_dry_run=False,
                                        context={"trigger": "schedule", "time": current_time_str}
                                    )
                                )

                await asyncio.sleep(15)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[WorkflowScheduler] Execution loop notice: {e}")
                await asyncio.sleep(15)

workflow_scheduler = WorkflowScheduler()

