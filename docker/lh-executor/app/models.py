"""Shared models for the LH Executor.

Re-exports from the canonical model definitions to keep both containers
in sync with the signaling protocol.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SignalType(str, Enum):
    APPROVE = "APPROVE"
    SUPPRESS = "SUPPRESS"
    ESCALATE = "ESCALATE"
    SURPRISE = "SURPRISE"


class ImplementationProof(BaseModel):
    test_log: str = ""
    diff_summary: str = ""
    lint_status: str = "pass"


class EscalateSignal(BaseModel):
    signal: SignalType = SignalType.ESCALATE
    intent_id: str
    iteration_count: int = Field(..., ge=1)
    failure_pattern: str
    attempted_fixes: list[str] = Field(default_factory=list)
    request: str = "Architectural guidance needed."


class SurpriseSignal(BaseModel):
    signal: SignalType = SignalType.SURPRISE
    intent_id: str
    prediction: str
    actual: str
    deviation: str = Field(..., pattern="^(low|medium|high)$")


class TaskSpec(BaseModel):
    intent_id: str
    task_type: str = Field(..., description="Type of task: execute, test, lint")
    payload: dict[str, Any] = Field(default_factory=dict)
    target_model: str = "gemini-2.5-flash"


class TaskResult(BaseModel):
    intent_id: str
    success: bool
    output: str = ""
    error: str = ""
    proof: ImplementationProof | None = None
