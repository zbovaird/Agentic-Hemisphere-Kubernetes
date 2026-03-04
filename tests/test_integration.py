"""Integration tests for the full bicameral lifecycle.

These tests validate the end-to-end flow without requiring a live cluster:
RH Planner creates a plan -> AgentTask CR is formed -> Operator builds
a pod manifest -> LH Executor processes the task -> Result is returned.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

DOCKER_DIR = Path(__file__).parent.parent / "docker"
OPERATOR_DIR = Path(__file__).parent.parent / "operator"

sys.path.insert(0, str(DOCKER_DIR / "rh-planner"))
from app.models import (
    Handshake,
    ImplementationProof,
    PlanRequest,
    ReviewRequest,
)
from app.planner import Planner


def _import_operator():
    spec = importlib.util.spec_from_file_location(
        "hemisphere_operator", OPERATOR_DIR / "operator.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _import_lh_executor():
    _stashed = {}
    for key in list(sys.modules):
        if key == "app" or key.startswith("app."):
            _stashed[key] = sys.modules.pop(key)

    lh_path = str(DOCKER_DIR / "lh-executor")
    sys.path.insert(0, lh_path)

    from app.executor import Executor
    from app.models import TaskSpec

    sys.path.remove(lh_path)
    for key in list(sys.modules):
        if key == "app" or key.startswith("app."):
            del sys.modules[key]
    sys.modules.update(_stashed)

    return Executor, TaskSpec


class TestEndToEndLifecycle:
    """Test the full RH -> Operator -> LH lifecycle without a live cluster."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_plan_to_task_to_execution(self) -> None:
        """Full lifecycle: plan -> build task -> execute -> review."""
        planner = Planner()

        plan_response = await planner.create_plan(PlanRequest(
            intent_id="integration-001",
            description="Run echo command",
            context={
                "target_files": ["tests/test_example.py"],
                "acceptance_criteria": ["Command exits 0"],
            },
        ))
        assert plan_response.handshake.intent_id == "integration-001"

        op_mod = _import_operator()
        task_spec_dict = {
            "intent_id": plan_response.handshake.intent_id,
            "task_type": "execute",
            "payload": {"command": "echo integration_test"},
            "target_model": "gemini-2.5-flash",
        }

        pod_manifest = op_mod._build_pod_manifest(
            "integration-task-001", "owner", task_spec_dict
        )

        assert pod_manifest["metadata"]["namespace"] == "employee"
        assert pod_manifest["spec"]["runtimeClassName"] == "gvisor"

        task_env = next(
            e for e in pod_manifest["spec"]["containers"][0]["env"]
            if e["name"] == "TASK_SPEC"
        )
        parsed_spec = json.loads(task_env["value"])
        assert parsed_spec["intent_id"] == "integration-001"

        Executor, TaskSpec = _import_lh_executor()
        executor = Executor()
        lh_spec = TaskSpec(**parsed_spec)
        result = await executor.execute(lh_spec)

        assert result.success
        assert "integration_test" in result.output

        review_response = await planner.review(ReviewRequest(
            intent_id="integration-001",
            handshake=plan_response.handshake,
            implementation_proof=ImplementationProof(
                test_log=result.output,
                diff_summary="1 file changed",
                lint_status=result.proof.lint_status if result.proof else "pass",
            ),
        ))
        assert review_response.approved

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_failed_task_triggers_suppress(self) -> None:
        """A failed task should result in a SUPPRESS signal on review."""
        planner = Planner()

        plan_response = await planner.create_plan(PlanRequest(
            intent_id="integration-002",
            description="Run failing command",
        ))

        Executor, TaskSpec = _import_lh_executor()
        executor = Executor()
        result = await executor.execute(TaskSpec(
            intent_id="integration-002",
            task_type="execute",
            payload={"command": "false"},
        ))

        assert not result.success

        review_response = await planner.review(ReviewRequest(
            intent_id="integration-002",
            handshake=plan_response.handshake,
            implementation_proof=ImplementationProof(
                test_log="",
                lint_status="fail",
            ),
        ))
        assert not review_response.approved

    @pytest.mark.integration
    def test_pod_manifest_security_in_lifecycle(self) -> None:
        """Verify security properties are maintained through the lifecycle."""
        op_mod = _import_operator()
        manifest = op_mod._build_pod_manifest(
            "sec-test", "owner",
            {"intent_id": "sec-001", "task_type": "execute"},
        )

        container = manifest["spec"]["containers"][0]
        sc = container["securityContext"]
        assert sc["allowPrivilegeEscalation"] is False
        assert sc["readOnlyRootFilesystem"] is True
        assert sc["runAsNonRoot"] is True
        assert "ALL" in sc["capabilities"]["drop"]
        assert manifest["spec"]["runtimeClassName"] == "gvisor"
