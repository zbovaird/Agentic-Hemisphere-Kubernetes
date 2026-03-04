"""Pydantic models for the scaling sidecar.

Re-exports the shared Handshake model and adds sidecar-specific types.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class HandshakeFile(BaseModel):
    """A handshake as read from the shared volume."""

    intent_id: str
    architectural_constraint: str = ""
    target_files: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class PoolStatus(BaseModel):
    """Current state of the warm pool for the /pool health endpoint."""

    component: str = "rh-sidecar"
    desired_size: int
    current_idle: int = 0
    standby_tasks: int = 0
