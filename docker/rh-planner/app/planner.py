"""RH Planner -- Right Hemisphere reasoning logic.

Handles architectural planning and implementation review.
In production, this integrates with Vertex AI for LLM-powered reasoning.
The logic is structured to be testable without a live Vertex AI endpoint.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import structlog

from .models import (
    ApproveSignal,
    Handshake,
    PlanRequest,
    PlanResponse,
    ReviewRequest,
    ReviewResponse,
    SuppressSignal,
)

logger = structlog.get_logger()

DEFAULT_MODEL = "claude-4.6-opus"
HANDSHAKE_DIR = os.environ.get("HANDSHAKE_DIR", "/handshakes")


class Planner:
    """Right Hemisphere planner that generates architectural plans and reviews diffs."""

    def __init__(self, vertex_endpoint: str | None = None, model_name: str | None = None) -> None:
        self.vertex_endpoint = vertex_endpoint
        self.model_name = model_name or os.environ.get("RH_MODEL", DEFAULT_MODEL)
        self._plan_count = 0

    async def create_plan(self, request: PlanRequest) -> PlanResponse:
        """Generate an architectural plan as a Handshake for the LH Executor."""
        start = time.monotonic()
        self._plan_count += 1

        logger.info(
            "creating_plan",
            intent_id=request.intent_id,
            description=request.description,
            hemisphere="right",
            model=self.model_name,
            phase="plan",
        )

        handshake = Handshake(
            intent_id=request.intent_id,
            architectural_constraint=f"Plan for: {request.description}",
            target_files=list(request.context.get("target_files", [])),
            acceptance_criteria=list(request.context.get("acceptance_criteria", ["All tests pass"])),
        )

        elapsed_ms = (time.monotonic() - start) * 1000
        input_tokens = len(request.description) * 4 + sum(len(str(v)) for v in request.context.values()) * 4
        output_tokens = len(str(handshake.model_dump())) * 4

        logger.info(
            "plan_completed",
            intent_id=request.intent_id,
            hemisphere="right",
            model=self.model_name,
            phase="plan",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=round(elapsed_ms, 2),
        )

        self._write_handshake(handshake)

        return PlanResponse(
            intent_id=request.intent_id,
            handshake=handshake,
            reasoning=f"Generated plan #{self._plan_count} for intent {request.intent_id}",
        )

    @staticmethod
    def _write_handshake(handshake: Handshake) -> None:
        """Write handshake JSON to the shared volume for the scaling sidecar."""
        pending_dir = Path(HANDSHAKE_DIR) / "pending"
        try:
            pending_dir.mkdir(parents=True, exist_ok=True)
            path = pending_dir / f"{handshake.intent_id}.json"
            path.write_text(json.dumps(handshake.model_dump(), indent=2))
            logger.info("handshake_written", path=str(path), intent_id=handshake.intent_id)
        except OSError as e:
            logger.warning(
                "handshake_write_failed",
                intent_id=handshake.intent_id,
                error=str(e),
            )

    async def review(self, request: ReviewRequest) -> ReviewResponse:
        """Review an Emissary's implementation proof and issue APPROVE or SUPPRESS."""
        start = time.monotonic()

        logger.info(
            "reviewing_implementation",
            intent_id=request.intent_id,
            lint_status=request.implementation_proof.lint_status,
            hemisphere="right",
            model=self.model_name,
            phase="review",
        )

        issues = self._check_for_issues(request)

        if issues:
            elapsed_ms = (time.monotonic() - start) * 1000
            input_tokens = len(str(request.model_dump())) * 4
            output_tokens = sum(len(i) for i in issues) * 4

            logger.warning(
                "review_suppressed",
                intent_id=request.intent_id,
                issues=issues,
                hemisphere="right",
                model=self.model_name,
                phase="review",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_ms=round(elapsed_ms, 2),
            )
            return ReviewResponse(
                intent_id=request.intent_id,
                approved=False,
                signal=SuppressSignal(
                    intent_id=request.intent_id,
                    reason="; ".join(issues),
                    action="ROLLBACK_AND_RETRY",
                ),
            )

        elapsed_ms = (time.monotonic() - start) * 1000
        input_tokens = len(str(request.model_dump())) * 4
        output_tokens = 200

        logger.info(
            "review_approved",
            intent_id=request.intent_id,
            hemisphere="right",
            model=self.model_name,
            phase="review",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=round(elapsed_ms, 2),
        )
        return ReviewResponse(
            intent_id=request.intent_id,
            approved=True,
            signal=ApproveSignal(
                intent_id=request.intent_id,
                follow_up=[],
            ),
        )

    def _check_for_issues(self, request: ReviewRequest) -> list[str]:
        """Check the implementation proof for architectural drift."""
        issues: list[str] = []

        if request.implementation_proof.lint_status != "pass":
            issues.append(f"Lint status is '{request.implementation_proof.lint_status}', expected 'pass'")

        if not request.implementation_proof.test_log:
            issues.append("No test log provided in implementation proof")

        return issues
