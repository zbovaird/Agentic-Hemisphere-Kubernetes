"""Efficiency benchmark tests.

Validates resource efficiency, container image sizing, and
operator design for minimal latency.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

PROJECT_ROOT = Path(__file__).parent.parent.parent
K8S_BASE = PROJECT_ROOT / "k8s" / "base"
K8S_DEV = PROJECT_ROOT / "k8s" / "overlays" / "dev"
OPERATOR_DIR = PROJECT_ROOT / "operator"


def _parse_cpu_millicores(cpu_str: str) -> int:
    """Convert CPU string to millicores (e.g., '500m' -> 500, '1' -> 1000)."""
    if cpu_str.endswith("m"):
        return int(cpu_str[:-1])
    return int(float(cpu_str) * 1000)


def _parse_memory_mi(mem_str: str) -> int:
    """Convert memory string to MiB (e.g., '512Mi' -> 512, '1Gi' -> 1024)."""
    if mem_str.endswith("Gi"):
        return int(float(mem_str[:-2]) * 1024)
    if mem_str.endswith("Mi"):
        return int(mem_str[:-2])
    return int(mem_str)


class TestContainerEfficiency:
    """Validate container images are efficiently sized."""

    @pytest.mark.benchmark
    def test_rh_dockerfile_uses_slim_base(self) -> None:
        dockerfile = (PROJECT_ROOT / "docker" / "rh-planner" / "Dockerfile").read_text()
        assert "slim" in dockerfile, "RH Planner should use a slim base image"

    @pytest.mark.benchmark
    def test_lh_dockerfile_uses_slim_base(self) -> None:
        dockerfile = (PROJECT_ROOT / "docker" / "lh-executor" / "Dockerfile").read_text()
        assert "slim" in dockerfile, "LH Executor should use a slim base image"

    @pytest.mark.benchmark
    def test_rh_dockerfile_is_multistage(self) -> None:
        dockerfile = (PROJECT_ROOT / "docker" / "rh-planner" / "Dockerfile").read_text()
        assert dockerfile.count("FROM ") >= 2, "RH Planner should use multi-stage build"

    @pytest.mark.benchmark
    def test_lh_dockerfile_is_multistage(self) -> None:
        dockerfile = (PROJECT_ROOT / "docker" / "lh-executor" / "Dockerfile").read_text()
        assert dockerfile.count("FROM ") >= 2, "LH Executor should use multi-stage build"

    @pytest.mark.benchmark
    def test_operator_dockerfile_is_multistage(self) -> None:
        dockerfile = (OPERATOR_DIR / "Dockerfile").read_text()
        assert dockerfile.count("FROM ") >= 2, "Operator should use multi-stage build"

    @pytest.mark.benchmark
    def test_dockerfiles_use_no_cache(self) -> None:
        for dockerfile_path in [
            PROJECT_ROOT / "docker" / "rh-planner" / "Dockerfile",
            PROJECT_ROOT / "docker" / "lh-executor" / "Dockerfile",
            OPERATOR_DIR / "Dockerfile",
        ]:
            content = dockerfile_path.read_text()
            assert "--no-cache-dir" in content, (
                f"{dockerfile_path.name} should use --no-cache-dir for pip"
            )


class TestResourceEfficiency:
    """Validate resource requests/limits are appropriately sized."""

    @pytest.fixture
    def base_deployments(self) -> list[dict[str, Any]]:
        docs = []
        for yaml_file in K8S_BASE.glob("*.yaml"):
            for doc in yaml.safe_load_all(yaml_file.read_text()):
                if doc and doc.get("kind") == "Deployment":
                    docs.append(doc)
        return docs

    @pytest.mark.benchmark
    def test_base_cpu_requests_under_1_core(self, base_deployments: list) -> None:
        for dep in base_deployments:
            container = dep["spec"]["template"]["spec"]["containers"][0]
            cpu_req = container["resources"]["requests"]["cpu"]
            mc = _parse_cpu_millicores(cpu_req)
            assert mc <= 1000, (
                f"{dep['metadata']['name']} requests {cpu_req} CPU -- should be <= 1 core"
            )

    @pytest.mark.benchmark
    def test_base_memory_requests_under_2gi(self, base_deployments: list) -> None:
        for dep in base_deployments:
            container = dep["spec"]["template"]["spec"]["containers"][0]
            mem_req = container["resources"]["requests"]["memory"]
            mi = _parse_memory_mi(mem_req)
            assert mi <= 2048, (
                f"{dep['metadata']['name']} requests {mem_req} memory -- should be <= 2Gi"
            )

    @pytest.mark.benchmark
    def test_lh_pod_template_minimal_resources(self) -> None:
        template = yaml.safe_load(
            (OPERATOR_DIR / "templates" / "lh_pod_template.yaml").read_text()
        )
        resources = template["spec"]["containers"][0]["resources"]
        assert _parse_cpu_millicores(resources["requests"]["cpu"]) <= 500
        assert _parse_memory_mi(resources["requests"]["memory"]) <= 1024

    @pytest.mark.benchmark
    def test_lh_executor_is_ephemeral(self) -> None:
        template = yaml.safe_load(
            (OPERATOR_DIR / "templates" / "lh_pod_template.yaml").read_text()
        )
        assert template["spec"]["restartPolicy"] == "Never", (
            "LH pods should be ephemeral (restartPolicy: Never)"
        )


class TestAutopilotEfficiency:
    """Validate design choices that optimize for GKE Autopilot billing."""

    @pytest.mark.benchmark
    def test_no_daemonsets(self) -> None:
        """Autopilot doesn't support DaemonSets well -- verify none exist."""
        for yaml_file in K8S_BASE.glob("*.yaml"):
            for doc in yaml.safe_load_all(yaml_file.read_text()):
                if doc:
                    assert doc.get("kind") != "DaemonSet", (
                        "DaemonSets are inefficient on Autopilot"
                    )

    @pytest.mark.benchmark
    def test_single_replica_for_testing(self) -> None:
        for yaml_file in K8S_BASE.glob("*.yaml"):
            for doc in yaml.safe_load_all(yaml_file.read_text()):
                if doc and doc.get("kind") == "Deployment":
                    replicas = doc["spec"].get("replicas", 1)
                    assert replicas <= 2, (
                        f"{doc['metadata']['name']} has {replicas} replicas -- "
                        "base should use minimal replicas"
                    )
