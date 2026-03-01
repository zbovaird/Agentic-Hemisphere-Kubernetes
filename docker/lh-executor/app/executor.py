"""LH Executor -- Left Hemisphere task execution logic.

Ephemeral executor that receives a TaskSpec, performs the work,
and reports a TaskResult. Designed to run as a Kubernetes Job
spawned by the operator.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys

import structlog

from .models import (
    EscalateSignal,
    ImplementationProof,
    SurpriseSignal,
    TaskResult,
    TaskSpec,
)

logger = structlog.get_logger()

MAX_ITERATIONS = 5


class Executor:
    """Left Hemisphere executor that processes discrete tasks."""

    def __init__(self) -> None:
        self._iteration_count = 0

    async def execute(self, spec: TaskSpec) -> TaskResult:
        """Execute a task and return the result."""
        logger.info(
            "executing_task",
            intent_id=spec.intent_id,
            task_type=spec.task_type,
            target_model=spec.target_model,
        )

        handler = self._get_handler(spec.task_type)
        if handler is None:
            return TaskResult(
                intent_id=spec.intent_id,
                success=False,
                error=f"Unknown task type: {spec.task_type}",
            )

        try:
            result = await handler(spec)
            logger.info(
                "task_completed",
                intent_id=spec.intent_id,
                success=result.success,
            )
            return result
        except Exception as e:
            logger.error(
                "task_failed",
                intent_id=spec.intent_id,
                error=str(e),
            )
            return TaskResult(
                intent_id=spec.intent_id,
                success=False,
                error=str(e),
            )

    def _get_handler(self, task_type: str):  # noqa: ANN202
        handlers = {
            "execute": self._handle_execute,
            "test": self._handle_test,
            "lint": self._handle_lint,
        }
        return handlers.get(task_type)

    async def _handle_execute(self, spec: TaskSpec) -> TaskResult:
        """Execute a generic command from the task payload."""
        command = spec.payload.get("command", "")
        if not command:
            return TaskResult(
                intent_id=spec.intent_id,
                success=False,
                error="No command specified in payload",
            )

        prediction = f"Command '{command}' completes successfully"
        logger.info("prediction", prediction=prediction)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

            output = stdout.decode() if stdout else ""
            error_output = stderr.decode() if stderr else ""
            success = proc.returncode == 0

            if not success:
                self._iteration_count += 1
                if self._iteration_count >= MAX_ITERATIONS:
                    logger.warning(
                        "escalation_threshold_reached",
                        intent_id=spec.intent_id,
                        iterations=self._iteration_count,
                    )

            return TaskResult(
                intent_id=spec.intent_id,
                success=success,
                output=output[:2000],
                error=error_output[:2000] if not success else "",
                proof=ImplementationProof(
                    test_log=output[:500],
                    lint_status="pass" if success else "fail",
                ),
            )
        except asyncio.TimeoutError:
            return TaskResult(
                intent_id=spec.intent_id,
                success=False,
                error="Command timed out after 300 seconds",
            )

    async def _handle_test(self, spec: TaskSpec) -> TaskResult:
        """Run tests specified in the payload."""
        test_path = spec.payload.get("test_path", "tests/")
        return await self._handle_execute(
            TaskSpec(
                intent_id=spec.intent_id,
                task_type="execute",
                payload={"command": f"{sys.executable} -m pytest {test_path} -v"},
                target_model=spec.target_model,
            )
        )

    async def _handle_lint(self, spec: TaskSpec) -> TaskResult:
        """Run linting on specified paths."""
        lint_path = spec.payload.get("lint_path", ".")
        return await self._handle_execute(
            TaskSpec(
                intent_id=spec.intent_id,
                task_type="execute",
                payload={"command": f"ruff check {lint_path}"},
                target_model=spec.target_model,
            )
        )

    def should_escalate(self) -> bool:
        return self._iteration_count >= MAX_ITERATIONS

    def build_escalate_signal(self, spec: TaskSpec, failure_pattern: str) -> EscalateSignal:
        return EscalateSignal(
            intent_id=spec.intent_id,
            iteration_count=self._iteration_count,
            failure_pattern=failure_pattern,
        )

    def build_surprise_signal(
        self, spec: TaskSpec, prediction: str, actual: str, deviation: str
    ) -> SurpriseSignal:
        return SurpriseSignal(
            intent_id=spec.intent_id,
            prediction=prediction,
            actual=actual,
            deviation=deviation,
        )
