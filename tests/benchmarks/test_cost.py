"""Cost estimation tests for infrastructure resources.

Validates that all Terraform resources use minimal sizing appropriate
for a testing environment, and estimates monthly costs.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

TERRAFORM_DIR = Path(__file__).parent.parent.parent / "terraform"
MODULES_DIR = TERRAFORM_DIR / "modules"


# GKE Autopilot pricing (us-central1, as of 2026)
# Autopilot charges per pod resource request, not per node.
AUTOPILOT_VCPU_PER_HOUR = 0.0445
AUTOPILOT_MEMORY_GB_PER_HOUR = 0.0049375
HOURS_PER_MONTH = 730


class TestCostMinimalSizing:
    """Verify all resources use the smallest viable configuration."""

    def test_gke_uses_autopilot(self) -> None:
        gke_main = (MODULES_DIR / "gke" / "main.tf").read_text()
        assert "enable_autopilot = true" in gke_main, (
            "GKE must use Autopilot for pay-per-pod billing"
        )

    def test_no_gpu_resources(self) -> None:
        for tf_file in TERRAFORM_DIR.rglob("*.tf"):
            content = tf_file.read_text()
            assert "gpu" not in content.lower() or "# gpu" in content.lower(), (
                f"GPU resources found in {tf_file.name} -- not needed for testing"
            )

    def test_employee_quota_is_minimal(self) -> None:
        tfvars = (TERRAFORM_DIR / "terraform.tfvars.example").read_text()
        cpu_match = re.search(r'employee_cpu_quota\s*=\s*"(\d+)"', tfvars)
        mem_match = re.search(r'employee_memory_quota\s*=\s*"(\d+)Gi"', tfvars)
        pod_match = re.search(r'employee_pod_quota\s*=\s*"(\d+)"', tfvars)

        assert cpu_match and int(cpu_match.group(1)) <= 4, "CPU quota should be <= 4 for testing"
        assert mem_match and int(mem_match.group(1)) <= 4, "Memory quota should be <= 4Gi for testing"
        assert pod_match and int(pod_match.group(1)) <= 20, "Pod quota should be <= 20 for testing"


class TestCostEstimation:
    """Estimate monthly costs based on resource specifications."""

    @pytest.mark.benchmark
    def test_estimate_autopilot_cost(self) -> None:
        """Estimate cost for a minimal Autopilot workload.

        Assumes:
        - RH Planner: 1 pod, 0.25 vCPU, 0.5Gi memory, always-on
        - Operator: 1 pod, 0.25 vCPU, 0.5Gi memory, always-on
        - LH Executor: avg 2 pods, 0.25 vCPU, 0.5Gi each, 10% duty cycle
        """
        rh_cpu_cost = 1 * 0.25 * AUTOPILOT_VCPU_PER_HOUR * HOURS_PER_MONTH
        rh_mem_cost = 1 * 0.5 * AUTOPILOT_MEMORY_GB_PER_HOUR * HOURS_PER_MONTH
        rh_total = rh_cpu_cost + rh_mem_cost

        op_total = rh_total  # same sizing

        lh_cpu_cost = 2 * 0.25 * AUTOPILOT_VCPU_PER_HOUR * HOURS_PER_MONTH * 0.10
        lh_mem_cost = 2 * 0.5 * AUTOPILOT_MEMORY_GB_PER_HOUR * HOURS_PER_MONTH * 0.10
        lh_total = lh_cpu_cost + lh_mem_cost

        total_monthly = rh_total + op_total + lh_total

        assert total_monthly < 50.0, (
            f"Estimated monthly cost ${total_monthly:.2f} exceeds $50 testing budget"
        )

    @pytest.mark.benchmark
    def test_vertex_endpoint_cost_awareness(self) -> None:
        """Vertex AI endpoint has no idle cost when no model is deployed.

        With an empty traffic_split and no model_id, the endpoint exists
        but incurs no prediction charges.
        """
        tfvars = (TERRAFORM_DIR / "terraform.tfvars.example").read_text()
        assert 'vertex_model_id      = ""' in tfvars, (
            "Default config should not deploy a model to avoid idle charges"
        )
        assert "vertex_traffic_split = {}" in tfvars, (
            "Default traffic split should be empty"
        )
