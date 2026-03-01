"""Unit tests for the RH Planner (Right Hemisphere)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "docker" / "rh-planner"))

from app.models import (
    ApproveSignal,
    EscalateSignal,
    Handshake,
    ImplementationProof,
    PlanRequest,
    PlanResponse,
    ReviewRequest,
    ReviewResponse,
    SignalType,
    SuppressSignal,
    SurpriseSignal,
    TaskSpec,
    TaskResult,
)
from app.planner import Planner


class TestModels:
    """Validate Pydantic models match the signaling protocol."""

    def test_handshake_creation(self) -> None:
        h = Handshake(
            intent_id="test-001",
            architectural_constraint="No new deps",
            target_files=["src/main.py"],
            acceptance_criteria=["Tests pass"],
        )
        assert h.intent_id == "test-001"
        assert h.implementation_proof is None

    def test_handshake_with_proof(self) -> None:
        proof = ImplementationProof(
            test_log="PASSED", diff_summary="1 file changed", lint_status="pass"
        )
        h = Handshake(
            intent_id="test-002",
            architectural_constraint="Constraint",
            implementation_proof=proof,
        )
        assert h.implementation_proof is not None
        assert h.implementation_proof.lint_status == "pass"

    def test_approve_signal(self) -> None:
        sig = ApproveSignal(intent_id="test-001", follow_up=["Update docs"])
        assert sig.signal == SignalType.APPROVE
        assert sig.follow_up == ["Update docs"]

    def test_suppress_signal(self) -> None:
        sig = SuppressSignal(
            intent_id="test-001",
            reason="Introduced redis dependency",
            action="ROLLBACK_AND_RETRY",
        )
        assert sig.signal == SignalType.SUPPRESS

    def test_escalate_signal(self) -> None:
        sig = EscalateSignal(
            intent_id="test-001",
            iteration_count=5,
            failure_pattern="Type mismatch",
        )
        assert sig.signal == SignalType.ESCALATE
        assert sig.iteration_count == 5

    def test_escalate_signal_rejects_zero_iterations(self) -> None:
        with pytest.raises(Exception):
            EscalateSignal(
                intent_id="test-001",
                iteration_count=0,
                failure_pattern="Error",
            )

    def test_surprise_signal(self) -> None:
        sig = SurpriseSignal(
            intent_id="test-001",
            prediction="Expected 200",
            actual="Got 500",
            deviation="high",
        )
        assert sig.signal == SignalType.SURPRISE

    def test_surprise_signal_rejects_invalid_deviation(self) -> None:
        with pytest.raises(Exception):
            SurpriseSignal(
                intent_id="test-001",
                prediction="Expected 200",
                actual="Got 500",
                deviation="extreme",
            )

    def test_task_spec(self) -> None:
        spec = TaskSpec(
            intent_id="test-001",
            task_type="execute",
            payload={"command": "echo hello"},
        )
        assert spec.target_model == "gemini-2.5-flash"

    def test_task_result_success(self) -> None:
        result = TaskResult(intent_id="test-001", success=True, output="done")
        assert result.success
        assert result.error == ""

    def test_task_result_failure(self) -> None:
        result = TaskResult(intent_id="test-001", success=False, error="boom")
        assert not result.success


class TestPlanner:
    """Test the RH Planner logic."""

    @pytest.fixture
    def planner(self) -> Planner:
        return Planner()

    @pytest.mark.asyncio
    async def test_create_plan(self, planner: Planner) -> None:
        request = PlanRequest(
            intent_id="test-plan-001",
            description="Add auth endpoint",
            context={"target_files": ["src/auth.py"], "acceptance_criteria": ["Tests pass"]},
        )
        response = await planner.create_plan(request)
        assert response.intent_id == "test-plan-001"
        assert response.handshake.intent_id == "test-plan-001"
        assert "src/auth.py" in response.handshake.target_files

    @pytest.mark.asyncio
    async def test_create_plan_increments_counter(self, planner: Planner) -> None:
        request = PlanRequest(intent_id="test-001", description="Task 1")
        await planner.create_plan(request)
        await planner.create_plan(request)
        assert planner._plan_count == 2

    @pytest.mark.asyncio
    async def test_review_approves_valid_proof(self, planner: Planner) -> None:
        handshake = Handshake(
            intent_id="test-review-001",
            architectural_constraint="No constraint",
        )
        proof = ImplementationProof(
            test_log="All 10 tests passed",
            diff_summary="2 files changed",
            lint_status="pass",
        )
        request = ReviewRequest(
            intent_id="test-review-001",
            handshake=handshake,
            implementation_proof=proof,
        )
        response = await planner.review(request)
        assert response.approved
        assert response.signal.signal == SignalType.APPROVE

    @pytest.mark.asyncio
    async def test_review_suppresses_failed_lint(self, planner: Planner) -> None:
        handshake = Handshake(
            intent_id="test-review-002",
            architectural_constraint="No constraint",
        )
        proof = ImplementationProof(
            test_log="Tests passed",
            lint_status="fail",
        )
        request = ReviewRequest(
            intent_id="test-review-002",
            handshake=handshake,
            implementation_proof=proof,
        )
        response = await planner.review(request)
        assert not response.approved
        assert response.signal.signal == SignalType.SUPPRESS

    @pytest.mark.asyncio
    async def test_review_suppresses_missing_test_log(self, planner: Planner) -> None:
        handshake = Handshake(
            intent_id="test-review-003",
            architectural_constraint="No constraint",
        )
        proof = ImplementationProof(test_log="", lint_status="pass")
        request = ReviewRequest(
            intent_id="test-review-003",
            handshake=handshake,
            implementation_proof=proof,
        )
        response = await planner.review(request)
        assert not response.approved


class TestFastAPIEndpoints:
    """Test the FastAPI app endpoints."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app)

    def test_health_endpoint(self, client) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["component"] == "rh-planner"

    def test_plan_endpoint(self, client) -> None:
        response = client.post("/plan", json={
            "intent_id": "api-test-001",
            "description": "Test plan",
            "context": {},
        })
        assert response.status_code == 200
        data = response.json()
        assert data["intent_id"] == "api-test-001"
        assert "handshake" in data

    def test_review_endpoint_approve(self, client) -> None:
        response = client.post("/review", json={
            "intent_id": "api-test-002",
            "handshake": {
                "intent_id": "api-test-002",
                "architectural_constraint": "None",
            },
            "implementation_proof": {
                "test_log": "All passed",
                "diff_summary": "1 file",
                "lint_status": "pass",
            },
        })
        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is True

    def test_review_endpoint_suppress(self, client) -> None:
        response = client.post("/review", json={
            "intent_id": "api-test-003",
            "handshake": {
                "intent_id": "api-test-003",
                "architectural_constraint": "None",
            },
            "implementation_proof": {
                "test_log": "",
                "diff_summary": "",
                "lint_status": "fail",
            },
        })
        assert response.status_code == 200
        data = response.json()
        assert data["approved"] is False
