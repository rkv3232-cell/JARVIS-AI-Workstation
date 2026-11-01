"""
Skill Executor for JARVIS-APEX.
Handles safe execution of instruction-only, tool-based, and script-enabled skills
with strict permission checks, timeouts, and structured result contracts.
"""

import sys
import json
import time
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from .skill_types import SkillType, SkillStatus, SkillResult, SkillExecutionRequest
from .skill_registry import SkillRegistry
from ..permissions import CentralPermissionManager, PermissionLevel
from ..activity import ActivityLogger

class SkillExecutor:
    """Executes registered skills under strict permission constraints and timeouts."""

    @classmethod
    async def execute_skill(cls, request: SkillExecutionRequest) -> SkillResult:
        t0 = time.perf_counter()
        skill_id = request.skill_id
        skill_data = SkillRegistry.get_skill(skill_id)

        if not skill_data:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            SkillRegistry.record_execution(skill_id, request.parameters, None, "FAILED", duration_ms, "Skill not found")
            return SkillResult(
                skill_id=skill_id,
                status=SkillStatus.FAILED,
                execution_time_ms=duration_ms,
                error=f"Skill '{skill_id}' is not installed."
            )

        if not skill_data["is_enabled"]:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            SkillRegistry.record_execution(skill_id, request.parameters, None, "DENIED", duration_ms, "Skill is disabled")
            return SkillResult(
                skill_id=skill_id,
                status=SkillStatus.DENIED,
                execution_time_ms=duration_ms,
                error=f"Skill '{skill_id}' is currently disabled in Skill Manager."
            )

        # 1. Permission Check via Central Permission Manager
        authorized, reason, grant_info = CentralPermissionManager.check_permission(
            component="skills",
            resource=skill_id,
            level=PermissionLevel.EXECUTE,
            description=f"Execution of skill '{skill_data['name']}' ({skill_id})",
            context={"parameters": request.parameters}
        )

        if not authorized:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            SkillRegistry.record_execution(skill_id, request.parameters, None, "DENIED", duration_ms, reason)
            return SkillResult(
                skill_id=skill_id,
                status=SkillStatus.DENIED,
                execution_time_ms=duration_ms,
                error=f"Permission denied: {reason}"
            )

        skill_type = skill_data["skill_type"]

        # 2. Execution Logic based on Type
        # Case A: Instruction Only
        if skill_type == SkillType.INSTRUCTION_ONLY.value:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            output = {
                "instruction": skill_data.get("skill_md", ""),
                "description": skill_data.get("description", ""),
                "parameters_echo": request.parameters
            }
            SkillRegistry.record_execution(skill_id, request.parameters, output, "SUCCESS", duration_ms)
            ActivityLogger.log(
                component="skills",
                action="execute_skill",
                target_resource=skill_id,
                approval_status="AUTO_APPROVED",
                execution_status="SUCCESS",
                result_summary=f"Evaluated instruction skill '{skill_id}'"
            )
            return SkillResult(
                skill_id=skill_id,
                status=SkillStatus.SUCCESS,
                execution_time_ms=duration_ms,
                output=output
            )

        # Case B: Script Enabled or Tool Based
        dir_path = Path(skill_data["directory_path"])
        entrypoint_rel = skill_data.get("manifest", {}).get("entrypoint")
        if not entrypoint_rel:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            err = "Declared entrypoint is missing from manifest."
            SkillRegistry.record_execution(skill_id, request.parameters, None, "FAILED", duration_ms, err)
            return SkillResult(
                skill_id=skill_id,
                status=SkillStatus.FAILED,
                execution_time_ms=duration_ms,
                error=err
            )

        entrypoint_abs = (dir_path / entrypoint_rel).resolve()
        if not entrypoint_abs.exists():
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            err = f"Entrypoint script not found at: {entrypoint_abs}"
            SkillRegistry.record_execution(skill_id, request.parameters, None, "FAILED", duration_ms, err)
            return SkillResult(
                skill_id=skill_id,
                status=SkillStatus.FAILED,
                execution_time_ms=duration_ms,
                error=err
            )

        # Execute in isolated subprocess with timeout
        timeout = request.timeout_seconds or 30
        input_payload = json.dumps(request.parameters, ensure_ascii=False)

        try:
            process = subprocess.Popen(
                [sys.executable, str(entrypoint_abs)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(dir_path),
                text=True,
                encoding="utf-8"
            )
            stdout_data, stderr_data = process.communicate(input=input_payload, timeout=timeout)
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)

            if process.returncode != 0:
                err_msg = stderr_data.strip() or f"Script exited with error code {process.returncode}"
                SkillRegistry.record_execution(skill_id, request.parameters, None, "FAILED", duration_ms, err_msg)
                ActivityLogger.log(
                    component="skills",
                    action="execute_skill",
                    target_resource=skill_id,
                    approval_status="AUTO_APPROVED",
                    execution_status="FAILED",
                    error_info=err_msg
                )
                return SkillResult(
                    skill_id=skill_id,
                    status=SkillStatus.FAILED,
                    execution_time_ms=duration_ms,
                    error=err_msg,
                    stdout=stdout_data
                )

            # Try parsing output as JSON; fallback to raw text
            try:
                parsed_output = json.loads(stdout_data.strip())
            except Exception:
                parsed_output = {"raw_output": stdout_data.strip()}

            SkillRegistry.record_execution(skill_id, request.parameters, parsed_output, "SUCCESS", duration_ms)
            ActivityLogger.log(
                component="skills",
                action="execute_skill",
                target_resource=skill_id,
                approval_status="AUTO_APPROVED",
                execution_status="SUCCESS",
                result_summary=f"Skill '{skill_id}' completed in {duration_ms}ms"
            )
            return SkillResult(
                skill_id=skill_id,
                status=SkillStatus.SUCCESS,
                execution_time_ms=duration_ms,
                output=parsed_output,
                stdout=stdout_data
            )

        except subprocess.TimeoutExpired:
            process.kill()
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            err = f"Skill execution timed out after {timeout} seconds."
            SkillRegistry.record_execution(skill_id, request.parameters, None, "TIMEOUT", duration_ms, err)
            ActivityLogger.log(
                component="skills",
                action="execute_skill",
                target_resource=skill_id,
                approval_status="AUTO_APPROVED",
                execution_status="FAILED",
                error_info=err
            )
            return SkillResult(
                skill_id=skill_id,
                status=SkillStatus.TIMEOUT,
                execution_time_ms=duration_ms,
                error=err
            )
        except Exception as exc:
            duration_ms = round((time.perf_counter() - t0) * 1000, 2)
            err = f"Execution exception: {str(exc)}"
            SkillRegistry.record_execution(skill_id, request.parameters, None, "FAILED", duration_ms, err)
            return SkillResult(
                skill_id=skill_id,
                status=SkillStatus.FAILED,
                execution_time_ms=duration_ms,
                error=err
            )

