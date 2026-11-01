"""
Type definitions and data models for JARVIS-APEX Skills System.
"""

from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class SkillType(str, Enum):
    INSTRUCTION_ONLY = "instruction_only"
    TOOL_BASED = "tool_based"
    SCRIPT_ENABLED = "script_enabled"

class SkillStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    DENIED = "DENIED"
    VALIDATION_ERROR = "VALIDATION_ERROR"

class SkillManifest(BaseModel):
    id: str
    name: str
    version: str = "1.0.0"
    type: SkillType = SkillType.INSTRUCTION_ONLY
    description: str
    author: str = "JARVIS Core"
    entrypoint: Optional[str] = None
    permissions_required: List[str] = Field(default_factory=list)
    parameters_schema: Dict[str, Any] = Field(default_factory=dict)
    returns_schema: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)
    is_enabled: bool = True
    directory_path: Optional[str] = None

class SkillExecutionRequest(BaseModel):
    skill_id: str
    action: Optional[str] = "execute"
    parameters: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: Optional[int] = 30

class SkillResult(BaseModel):
    skill_id: str
    status: SkillStatus
    execution_time_ms: float
    output: Any = None
    error: Optional[str] = None
    stdout: Optional[str] = None

