"""RH Planner -- Right Hemisphere reasoning logic.

Handles architectural planning and implementation review.
In production, this integrates with Vertex AI for LLM-powered reasoning.
The logic is structured to be testable without a live Vertex AI endpoint.
"""

from __future__ import annotations

import structlog

from .models import (
    ApproveSignal,
    Handshake,
    ImplementationProof,
    PlanRequest,
    PlanResponse,
    ReviewRequest,
    ReviewResponse,
    SuppressSignal,
)

logger = structlog.get_logger()


class Planner:
    """Right Hemisphere planner that generates architectural plans and reviews diffs."""

    def __init__(self, vertex_endpoint: str | None = None) -> None:
        self.vertex_endpoint = vertex_endpoint
        self._plan_count = 0

    async def create_plan(self, request: PlanRequest) -> PlanResponse:
        """Generate an architectural plan as a Handshake for the LH Executor."""
        self._plan_count += 1

        logger.info(
            "creating_plan",
            intent_id=request.intent_id,
            description=request.description,
        )

        handshake = Handshake(
            intent_id=request.intent_id,
            architectural_constraint=f"Plan for: {request.description}",
            target_files=list(request.context.get("target_files", [])),
            acceptance_criteria=list(request.context.get("acceptance_criteria", ["All tests pass"])),
        )

        return PlanResponse(
            intent_id=request.intent_id,
            handshake=handshake,
            reasoning=f"Generated plan #{self._plan_count} for intent {request.intent_id}",
        )

    async def review(self, request: ReviewRequest) -> ReviewResponse:
        """Review an Emissary's implementation proof and issue APPROVE or SUPPRESS."""
        logger.info(
            "reviewing_implementation",
            intent_id=request.intent_id,
            lint_status=request.implementation_proof.lint_status,
        )

        issues = self._check_for_issues(request)

        if issues:
            logger.warning("review_suppressed", intent_id=request.intent_id, issues=issues)
            return ReviewResponse(
                intent_id=request.intent_id,
                approved=False,
                signal=SuppressSignal(
                    intent_id=request.intent_id,
                    reason="; ".join(issues),
                    action="ROLLBACK_AND_RETRY",
                ),
            )

        logger.info("review_approved", intent_id=request.intent_id)
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
