"""Unit tests for the LH Executor (Left Hemisphere)."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

LH_APP_DIR = str(Path(__file__).parent.parent / "docker" / "lh-executor")

# Insert the LH executor directory at the front of sys.path so `app.*`
# resolves to the LH executor's app package. We stash and restore any
# previously-loaded `app` modules to avoid polluting the RH planner's
# namespace if tests run in the same process.
_stashed: dict[str, ModuleType] = {}
for _key in list(sys.modules):
    if _key == "app" or _key.startswith("app."):
        _stashed[_key] = sys.modules.pop(_key)

sys.path.insert(0, LH_APP_DIR)

from app.models import (  # type: ignore[import]  # noqa: E402
    EscalateSignal as _EscalateSignal,
    ImplementationProof as _ImplementationProof,
    SignalType as _SignalType,
    SurpriseSignal as _SurpriseSignal,
    TaskResult as _TaskResult,
    TaskSpec as _TaskSpec,
)
from app.executor import Executor as _Executor, MAX_ITERATIONS as _MAX_ITERATIONS  # type: ignore[import]  # noqa: E402

# Clean up: remove LH path and restore stashed modules
sys.path.remove(LH_APP_DIR)
for _key in list(sys.modules):
    if _key == "app" or _key.startswith("app."):
        del sys.modules[_key]
sys.modules.update(_stashed)

Executor = _Executor
MAX_ITERATIONS = _MAX_ITERATIONS
EscalateSignal = _EscalateSignal
ImplementationProof = _ImplementationProof
SignalType = _SignalType
SurpriseSignal = _SurpriseSignal
TaskResult = _TaskResult
TaskSpec = _TaskSpec


class TestLHModels:
    """Validate LH-side Pydantic models."""

    def test_task_spec_defaults(self) -> None:
        spec = TaskSpec(intent_id="t-001", task_type="execute")
        assert spec.target_model == "gemini-2.5-flash"
        assert spec.payload == {}

    def test_task_result_with_proof(self) -> None:
        proof = ImplementationProof(test_log="ok", lint_status="pass")
        result = TaskResult(intent_id="t-001", success=True, proof=proof)
        assert result.proof is not None
        assert result.proof.lint_status == "pass"

    def test_escalate_signal_fields(self) -> None:
        sig = EscalateSignal(
            intent_id="t-001",
            iteration_count=5,
            failure_pattern="Timeout",
            attempted_fixes=["Retry", "Increase timeout"],
        )
        assert sig.signal == SignalType.ESCALATE
        assert len(sig.attempted_fixes) == 2

    def test_surprise_signal_low_deviation(self) -> None:
        sig = SurpriseSignal(
            intent_id="t-001",
            prediction="Success",
            actual="Success with warnings",
            deviation="low",
        )
        assert sig.deviation == "low"


class TestExecutor:
    """Test the LH Executor logic."""

    @pytest.fixture
    def executor(self) -> Executor:
        return Executor()

    @pytest.mark.asyncio
    async def test_execute_echo_command(self, executor: Executor) -> None:
        spec = TaskSpec(
            intent_id="exec-001",
            task_type="execute",
            payload={"command": "echo hello"},
        )
        result = await executor.execute(spec)
        assert result.success
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_execute_failing_command(self, executor: Executor) -> None:
        spec = TaskSpec(
            intent_id="exec-002",
            task_type="execute",
            payload={"command": "false"},
        )
        result = await executor.execute(spec)
        assert not result.success

    @pytest.mark.asyncio
    async def test_execute_missing_command(self, executor: Executor) -> None:
        spec = TaskSpec(
            intent_id="exec-003",
            task_type="execute",
            payload={},
        )
        result = await executor.execute(spec)
        assert not result.success
        assert "No command" in result.error

    @pytest.mark.asyncio
    async def test_unknown_task_type(self, executor: Executor) -> None:
        spec = TaskSpec(
            intent_id="exec-004",
            task_type="unknown",
            payload={},
        )
        result = await executor.execute(spec)
        assert not result.success
        assert "Unknown task type" in result.error

    @pytest.mark.asyncio
    async def test_iteration_count_increments_on_failure(self, executor: Executor) -> None:
        spec = TaskSpec(
            intent_id="exec-005",
            task_type="execute",
            payload={"command": "false"},
        )
        for _ in range(3):
            await executor.execute(spec)
        assert executor._iteration_count == 3
        assert not executor.should_escalate()

    @pytest.mark.asyncio
    async def test_escalation_threshold(self, executor: Executor) -> None:
        spec = TaskSpec(
            intent_id="exec-006",
            task_type="execute",
            payload={"command": "false"},
        )
        for _ in range(MAX_ITERATIONS):
            await executor.execute(spec)
        assert executor.should_escalate()

    def test_build_escalate_signal(self, executor: Executor) -> None:
        executor._iteration_count = 5
        spec = TaskSpec(intent_id="esc-001", task_type="execute")
        signal = executor.build_escalate_signal(spec, "Repeated timeout")
        assert signal.signal == SignalType.ESCALATE
        assert signal.iteration_count == 5
        assert signal.failure_pattern == "Repeated timeout"

    def test_build_surprise_signal(self, executor: Executor) -> None:
        spec = TaskSpec(intent_id="sur-001", task_type="execute")
        signal = executor.build_surprise_signal(
            spec, prediction="200 OK", actual="500 Error", deviation="high"
        )
        assert signal.signal == SignalType.SURPRISE
        assert signal.deviation == "high"

    @pytest.mark.asyncio
    async def test_result_includes_proof(self, executor: Executor) -> None:
        spec = TaskSpec(
            intent_id="exec-007",
            task_type="execute",
            payload={"command": "echo proof_test"},
        )
        result = await executor.execute(spec)
        assert result.proof is not None
        assert result.proof.lint_status == "pass"
