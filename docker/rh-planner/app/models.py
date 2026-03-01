"""Pydantic models for the bicameral signaling protocol.

These models enforce the JSON handshake structure defined in the
Corpus Callosum (03_callosum.mdc) for communication between the
Right Hemisphere (Planner) and Left Hemisphere (Executor).
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


class Handshake(BaseModel):
    intent_id: str = Field(..., description="Unique identifier for this intent")
    architectural_constraint: str = Field(
        ..., description="Constraints the executor must respect"
    )
    target_files: list[str] = Field(
        default_factory=list, description="Files the executor is permitted to modify"
    )
    acceptance_criteria: list[str] = Field(
        default_factory=list, description="Conditions that must be met for approval"
    )
    implementation_proof: ImplementationProof | None = None


class ApproveSignal(BaseModel):
    signal: SignalType = SignalType.APPROVE
    intent_id: str
    follow_up: list[str] = Field(default_factory=list)


class SuppressSignal(BaseModel):
    signal: SignalType = SignalType.SUPPRESS
    intent_id: str
    reason: str
    action: str = "ROLLBACK_AND_RETRY"


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


class PlanRequest(BaseModel):
    intent_id: str
    description: str
    context: dict[str, Any] = Field(default_factory=dict)


class PlanResponse(BaseModel):
    intent_id: str
    handshake: Handshake
    reasoning: str = ""


class ReviewRequest(BaseModel):
    intent_id: str
    handshake: Handshake
    implementation_proof: ImplementationProof


class ReviewResponse(BaseModel):
    intent_id: str
    approved: bool
    signal: ApproveSignal | SuppressSignal


class TaskSpec(BaseModel):
    """Specification for an LH Executor task, matching the AgentTask CRD spec."""

    intent_id: str
    task_type: str = Field(..., description="Type of task: execute, test, lint")
    payload: dict[str, Any] = Field(default_factory=dict)
    target_model: str = "gemini-2.5-flash"


class TaskResult(BaseModel):
    """Result reported by an LH Executor after task completion."""

    intent_id: str
    success: bool
    output: str = ""
    error: str = ""
    proof: ImplementationProof | None = None
