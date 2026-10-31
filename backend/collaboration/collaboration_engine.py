"""
Skill Collaboration Engine for JARVIS-APEX.
Coordinates multi-skill task decomposition, sequential/pipelined execution,
data handoff between skills, and lifecycle management (pause/resume/cancel).
"""

import json
import time
import uuid
import asyncio
import sqlite3
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from ..skills import SkillRegistry, SkillExecutor, SkillExecutionRequest, SkillStatus
from ..activity import ActivityLogger
from ..websocket_manager import ws_manager

DB_PATH = Path(__file__).resolve().parent.parent / "jarvis.db"
_collab_lock = threading.Lock()

class CollaborationEngine:
    """
    Orchestrates complex multi-skill workflows, piping outputs of one skill
    into the inputs of subsequent skills with full lifecycle control.
    """
    _running_tasks: Dict[str, asyncio.Task] = {}
    _pause_flags: Dict[str, bool] = {}
    _cancel_flags: Dict[str, bool] = {}

    @classmethod
    def plan_task(cls, objective: str, user_plan: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Creates a structured multi-skill execution plan for a user objective.
        If user_plan is provided, validates skill availability; otherwise builds standard pipeline.
        """
        task_id = f"collab_{uuid.uuid4().hex[:10]}"
        now = time.time()

        if user_plan and len(user_plan) > 0:
            plan_steps = user_plan
        else:
            # Deterministic, multi-skill pipeline generation based on intent keywords
            obj_lower = objective.lower()
            plan_steps = []

            # Step 1: Research or Coding analysis
            if any(k in obj_lower for k in ["code", "script", "syntax", "refactor"]):
                plan_steps.append({
                    "step_index": 0,
                    "skill_id": "coding_specialist",
                    "action_name": "inspect_code",
                    "params": {"code": None, "check_security": True}
                })
            else:
                plan_steps.append({
                    "step_index": 0,
                    "skill_id": "deep_researcher",
                    "action_name": "gather_intelligence",
                    "params": {"topic": objective, "depth": "standard"}
                })

            # Step 2: Data analysis if metrics/finance involved
            if any(k in obj_lower for k in ["quant", "pipeline", "research", "analysis", "stat", "metric", "trend", "finance", "data", "market", "pdf", "report"]):
                plan_steps.append({
                    "step_index": len(plan_steps),
                    "skill_id": "data_analyst",
                    "action_name": "compute_metrics",
                    "params": {"series": [105.0, 108.2, 112.5, 110.0, 115.8, 119.4, 122.0]}
                })

            # Step 3: PDF Generation if requested or default for comprehensive dossiers
            if any(k in obj_lower for k in ["pdf", "report", "dossier", "export", "doc"]) or len(plan_steps) >= 2:
                plan_steps.append({
                    "step_index": len(plan_steps),
                    "skill_id": "pdf_generator",
                    "action_name": "build_pdf_report",
                    "params": {"title": f"Intelligence Dossier: {objective[:40]}", "subtitle": "Collaborative Multi-Skill Output"}
                })

        with _collab_lock:
            with sqlite3.connect(str(DB_PATH)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO collaboration_tasks (
                        task_id, objective, status, plan_json, current_step, output_json, error, created_at, updated_at
                    ) VALUES (?, ?, 'PLANNED', ?, 0, NULL, NULL, ?, ?);
                """, (task_id, objective, json.dumps(plan_steps, ensure_ascii=False), now, now))

                for s in plan_steps:
                    step_id = f"step_{uuid.uuid4().hex[:10]}"
                    cursor.execute("""
                        INSERT INTO collaboration_steps (
                            step_id, task_id, step_index, skill_id, action_name, input_json, output_json, status, started_at, completed_at, error
                        ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'PENDING', NULL, NULL, NULL);
                    """, (
                        step_id, task_id, s["step_index"], s["skill_id"],
                        s.get("action_name", "execute"),
                        json.dumps(s.get("params", {}), ensure_ascii=False)
                    ))

                conn.commit()

        ActivityLogger.log(
            component="collaboration",
            action="plan_task",
            target_resource=task_id,
            approval_status="AUTO_APPROVED",
            execution_status="SUCCESS",
            result_summary=f"Planned {len(plan_steps)}-step collaborative task: '{objective[:50]}'",
            metadata={"task_id": task_id, "step_count": len(plan_steps)}
        )

        return {
            "task_id": task_id,
            "objective": objective,
            "status": "PLANNED",
            "step_count": len(plan_steps),
            "steps": plan_steps
        }

    @classmethod
    async def start_task(cls, task_id: str) -> Dict[str, Any]:
        """Initiates execution of a planned collaborative task in the background."""
        task_info = cls.get_task(task_id)
        if not task_info:
            return {"status": "ERROR", "error": "Task ID not found."}

        if task_id in cls._running_tasks and not cls._running_tasks[task_id].done():
            return {"status": "RUNNING", "message": "Task is already executing."}

        cls._pause_flags[task_id] = False
        cls._cancel_flags[task_id] = False

        bg_task = asyncio.create_task(cls._execute_collaboration_loop(task_id))
        cls._running_tasks[task_id] = bg_task

        return {"status": "STARTED", "task_id": task_id, "message": "Collaboration execution started."}

    @classmethod
    async def _execute_collaboration_loop(cls, task_id: str):
        """Asynchronous execution coordinator with data pipelining between steps."""
        try:
            task = cls.get_task(task_id)
            if not task:
                return

            cls._update_task_status(task_id, "RUNNING")
            steps = cls.get_task_steps(task_id)
            pipeline_context: Dict[str, Any] = {}

            for step in steps:
                # 1. Cancellation Check
                if cls._cancel_flags.get(task_id):
                    cls._update_task_status(task_id, "CANCELLED")
                    cls._update_step_status(step["step_id"], "SKIPPED", error="Task cancelled by user.")
                    return

                # 2. Pause Loop Check
                while cls._pause_flags.get(task_id):
                    cls._update_task_status(task_id, "PAUSED")
                    await asyncio.sleep(0.5)
                    if cls._cancel_flags.get(task_id):
                        cls._update_task_status(task_id, "CANCELLED")
                        return

                cls._update_task_status(task_id, "RUNNING")
                step_idx = step["step_index"]
                skill_id = step["skill_id"]

                # Mark step started
                cls._update_step_status(step["step_id"], "RUNNING", started_at=time.time())
                await ws_manager.broadcast("collaboration_step_progress", {
                    "task_id": task_id,
                    "step_index": step_idx,
                    "step_id": step["step_id"],
                    "skill_id": skill_id,
                    "status": "RUNNING"
                })

                # Prepare step input parameters by merging initial params with pipeline context
                initial_params = step.get("input") or {}
                resolved_params = dict(initial_params)

                # Pipeline data injection
                if skill_id == "data_analyst" and "research_output" in pipeline_context:
                    # Enrich parameters if applicable
                    resolved_params["context_topic"] = pipeline_context["research_output"].get("topic")

                elif skill_id == "pdf_generator":
                    # Assemble publication document from prior skill outputs
                    sections = []
                    if "research_output" in pipeline_context:
                        ro = pipeline_context["research_output"]
                        sections.append({
                            "heading": "1. Strategic Research Findings",
                            "content": ro.get("summary", ""),
                            "table_data": None
                        })
                    if "data_output" in pipeline_context:
                        do = pipeline_context["data_output"]
                        sections.append({
                            "heading": "2. Quantitative Risk & Performance Metrics",
                            "content": do.get("summary", ""),
                            "table_data": do.get("table_data")
                        })
                    if "coding_output" in pipeline_context:
                        co = pipeline_context["coding_output"]
                        sections.append({
                            "heading": "3. Source Code Integrity Audit",
                            "content": co.get("summary", ""),
                            "table_data": None
                        })

                    if sections:
                        resolved_params["sections"] = sections

                # Execute Skill
                req = SkillExecutionRequest(skill_id=skill_id, parameters=resolved_params, timeout_seconds=45)
                exec_result = await SkillExecutor.execute_skill(req)

                if exec_result.status == SkillStatus.SUCCESS:
                    cls._update_step_status(
                        step["step_id"],
                        "COMPLETED",
                        output_data=exec_result.output,
                        completed_at=time.time()
                    )

                    # Update context for downstream skills
                    if skill_id == "deep_researcher":
                        pipeline_context["research_output"] = exec_result.output
                    elif skill_id == "data_analyst":
                        pipeline_context["data_output"] = exec_result.output
                    elif skill_id == "coding_specialist":
                        pipeline_context["coding_output"] = exec_result.output
                    elif skill_id == "pdf_generator":
                        pipeline_context["pdf_output"] = exec_result.output

                    await ws_manager.broadcast("collaboration_step_progress", {
                        "task_id": task_id,
                        "step_index": step_idx,
                        "step_id": step["step_id"],
                        "skill_id": skill_id,
                        "status": "COMPLETED",
                        "output": exec_result.output
                    })
                else:
                    # Step Failed
                    cls._update_step_status(
                        step["step_id"],
                        "FAILED",
                        error=exec_result.error,
                        completed_at=time.time()
                    )
                    cls._update_task_status(task_id, "FAILED", error=f"Step {step_idx} ({skill_id}) failed: {exec_result.error}")
                    await ws_manager.broadcast("collaboration_task_completed", {
                        "task_id": task_id,
                        "status": "FAILED",
                        "error": exec_result.error
                    })
                    return

            # All steps completed successfully
            cls._update_task_status(task_id, "COMPLETED", output_data=pipeline_context)
            await ws_manager.broadcast("collaboration_task_completed", {
                "task_id": task_id,
                "status": "COMPLETED",
                "output": pipeline_context
            })

            ActivityLogger.log(
                component="collaboration",
                action="task_completed",
                target_resource=task_id,
                approval_status="AUTO_APPROVED",
                execution_status="SUCCESS",
                result_summary=f"Collaboration task {task_id} completed successfully with {len(steps)} steps."
            )

        except Exception as e:
            cls._update_task_status(task_id, "FAILED", error=str(e))
            ActivityLogger.log(
                component="collaboration",
                action="task_failed",
                target_resource=task_id,
                approval_status="AUTO_APPROVED",
                execution_status="FAILED",
                error_info=str(e)
            )

    @classmethod
    def pause_task(cls, task_id: str) -> bool:
        cls._pause_flags[task_id] = True
        cls._update_task_status(task_id, "PAUSED")
        return True

    @classmethod
    def resume_task(cls, task_id: str) -> bool:
        cls._pause_flags[task_id] = False
        cls._update_task_status(task_id, "RUNNING")
        return True

    @classmethod
    def cancel_task(cls, task_id: str) -> bool:
        cls._cancel_flags[task_id] = True
        cls._pause_flags[task_id] = False
        cls._update_task_status(task_id, "CANCELLED")
        return True

    @classmethod
    def get_task(cls, task_id: str) -> Optional[Dict[str, Any]]:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM collaboration_tasks WHERE task_id = ?;", (task_id,))
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d["plan"] = json.loads(d["plan_json"])
            except Exception:
                d["plan"] = []
            try:
                d["output"] = json.loads(d["output_json"]) if d.get("output_json") else None
            except Exception:
                d["output"] = None
            d["steps"] = cls.get_task_steps(task_id)
            return d

    @classmethod
    def list_tasks(cls, limit: int = 30) -> List[Dict[str, Any]]:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM collaboration_tasks ORDER BY created_at DESC LIMIT ?;", (limit,))
            rows = cursor.fetchall()

        tasks = []
        for r in rows:
            d = dict(r)
            try:
                d["plan"] = json.loads(d["plan_json"])
            except Exception:
                d["plan"] = []
            tasks.append(d)
        return tasks

    @classmethod
    def get_task_steps(cls, task_id: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM collaboration_steps WHERE task_id = ? ORDER BY step_index ASC;", (task_id,))
            rows = cursor.fetchall()

        steps = []
        for r in rows:
            d = dict(r)
            try:
                d["input"] = json.loads(d["input_json"]) if d.get("input_json") else None
            except Exception:
                d["input"] = None
            try:
                d["output"] = json.loads(d["output_json"]) if d.get("output_json") else None
            except Exception:
                d["output"] = None
            steps.append(d)
        return steps

    @classmethod
    def _update_task_status(cls, task_id: str, status: str, output_data: Any = None, error: Optional[str] = None):
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            out_str = json.dumps(output_data, ensure_ascii=False) if output_data is not None else None
            if out_str:
                cursor.execute("""
                    UPDATE collaboration_tasks SET status = ?, output_json = ?, error = ?, updated_at = ? WHERE task_id = ?;
                """, (status, out_str, error, time.time(), task_id))
            else:
                cursor.execute("""
                    UPDATE collaboration_tasks SET status = ?, error = ?, updated_at = ? WHERE task_id = ?;
                """, (status, error, time.time(), task_id))
            conn.commit()

    @classmethod
    def _update_step_status(
        cls,
        step_id: str,
        status: str,
        output_data: Any = None,
        started_at: Optional[float] = None,
        completed_at: Optional[float] = None,
        error: Optional[str] = None
    ):
        with sqlite3.connect(str(DB_PATH)) as conn:
            cursor = conn.cursor()
            out_str = json.dumps(output_data, ensure_ascii=False) if output_data is not None else None
            if started_at:
                cursor.execute("""
                    UPDATE collaboration_steps SET status = ?, started_at = ? WHERE step_id = ?;
                """, (status, started_at, step_id))
            elif completed_at:
                cursor.execute("""
                    UPDATE collaboration_steps SET status = ?, output_json = ?, completed_at = ?, error = ? WHERE step_id = ?;
                """, (status, out_str, completed_at, error, step_id))
            else:
                cursor.execute("""
                    UPDATE collaboration_steps SET status = ?, error = ? WHERE step_id = ?;
                """, (status, error, step_id))
            conn.commit()
