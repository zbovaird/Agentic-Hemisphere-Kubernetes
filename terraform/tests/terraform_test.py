"""Terraform configuration validation tests.

These tests verify the structure and correctness of Terraform files
without requiring a live GCP project or terraform init.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

TERRAFORM_DIR = Path(__file__).parent.parent
MODULES_DIR = TERRAFORM_DIR / "modules"

EXPECTED_MODULES = ["gke", "iam", "vertex", "namespaces"]
REQUIRED_ROOT_FILES = ["main.tf", "variables.tf", "outputs.tf", "versions.tf"]


class TestTerraformStructure:
    """Validate that all expected Terraform files and modules exist."""

    def test_root_files_exist(self) -> None:
        for filename in REQUIRED_ROOT_FILES:
            assert (TERRAFORM_DIR / filename).is_file(), f"Missing root file: {filename}"

    def test_tfvars_example_exists(self) -> None:
        assert (TERRAFORM_DIR / "terraform.tfvars.example").is_file()

    @pytest.mark.parametrize("module_name", EXPECTED_MODULES)
    def test_module_directory_exists(self, module_name: str) -> None:
        module_dir = MODULES_DIR / module_name
        assert module_dir.is_dir(), f"Missing module directory: {module_name}"

    @pytest.mark.parametrize("module_name", EXPECTED_MODULES)
    def test_module_has_main_tf(self, module_name: str) -> None:
        assert (MODULES_DIR / module_name / "main.tf").is_file()

    @pytest.mark.parametrize("module_name", EXPECTED_MODULES)
    def test_module_has_variables_tf(self, module_name: str) -> None:
        assert (MODULES_DIR / module_name / "variables.tf").is_file()

    @pytest.mark.parametrize("module_name", EXPECTED_MODULES)
    def test_module_has_outputs_tf(self, module_name: str) -> None:
        assert (MODULES_DIR / module_name / "outputs.tf").is_file()


class TestGKEModule:
    """Validate GKE module configuration."""

    @pytest.fixture
    def gke_main(self) -> str:
        return (MODULES_DIR / "gke" / "main.tf").read_text()

    def test_autopilot_enabled(self, gke_main: str) -> None:
        assert "enable_autopilot = true" in gke_main

    def test_workload_identity_configured(self, gke_main: str) -> None:
        assert "workload_identity_config" in gke_main
        assert "svc.id.goog" in gke_main

    def test_deletion_protection_disabled_for_testing(self, gke_main: str) -> None:
        assert "deletion_protection = false" in gke_main

    def test_release_channel_configured(self, gke_main: str) -> None:
        assert "release_channel" in gke_main


class TestIAMModule:
    """Validate IAM module uses Workload Identity, not keys."""

    @pytest.fixture
    def iam_main(self) -> str:
        return (MODULES_DIR / "iam" / "main.tf").read_text()

    def test_no_service_account_keys(self, iam_main: str) -> None:
        assert "google_service_account_key" not in iam_main

    def test_workload_identity_bindings_exist(self, iam_main: str) -> None:
        assert "workloadIdentityUser" in iam_main

    def test_rh_planner_sa_defined(self, iam_main: str) -> None:
        assert "rh-planner-sa" in iam_main or "rh_planner" in iam_main

    def test_lh_executor_sa_defined(self, iam_main: str) -> None:
        assert "lh-executor-sa" in iam_main or "lh_executor" in iam_main

    def test_operator_sa_defined(self, iam_main: str) -> None:
        assert "hemisphere-operator-sa" in iam_main or "operator" in iam_main

    def test_minimal_iam_roles(self, iam_main: str) -> None:
        assert "roles/aiplatform.user" in iam_main
        assert "roles/container.developer" in iam_main
        assert "roles/owner" not in iam_main
        assert "roles/editor" not in iam_main


class TestVertexModule:
    """Validate Vertex AI module configuration."""

    @pytest.fixture
    def vertex_main(self) -> str:
        return (MODULES_DIR / "vertex" / "main.tf").read_text()

    def test_endpoint_resource_exists(self, vertex_main: str) -> None:
        assert "google_vertex_ai_endpoint" in vertex_main

    def test_traffic_split_lifecycle(self, vertex_main: str) -> None:
        assert "traffic_split" in vertex_main


class TestNamespacesModule:
    """Validate namespace and quota configuration."""

    @pytest.fixture
    def ns_main(self) -> str:
        return (MODULES_DIR / "namespaces" / "main.tf").read_text()

    def test_owner_namespace_exists(self, ns_main: str) -> None:
        assert '"owner"' in ns_main

    def test_manager_namespace_exists(self, ns_main: str) -> None:
        assert '"manager"' in ns_main

    def test_employee_namespace_exists(self, ns_main: str) -> None:
        assert '"employee"' in ns_main

    def test_employee_has_resource_quota(self, ns_main: str) -> None:
        assert "kubernetes_resource_quota" in ns_main

    def test_employee_restricted_pss(self, ns_main: str) -> None:
        assert '"restricted"' in ns_main

    def test_quota_limits_cpu(self, ns_main: str) -> None:
        assert "limits.cpu" in ns_main

    def test_quota_limits_memory(self, ns_main: str) -> None:
        assert "limits.memory" in ns_main

    def test_quota_limits_pods(self, ns_main: str) -> None:
        assert "pods" in ns_main


class TestSecurityCompliance:
    """Verify no secrets or credentials in any Terraform file."""

    @pytest.fixture
    def all_tf_content(self) -> str:
        content = ""
        for tf_file in TERRAFORM_DIR.rglob("*.tf"):
            content += tf_file.read_text() + "\n"
        return content

    def test_no_hardcoded_credentials(self, all_tf_content: str) -> None:
        secret_patterns = [
            r"AKIA[0-9A-Z]{16}",
            r"password\s*=\s*\"[^\"]+\"",
            r"secret_key\s*=\s*\"[^\"]+\"",
        ]
        for pattern in secret_patterns:
            assert not re.search(pattern, all_tf_content), f"Found potential secret: {pattern}"

    def test_no_service_account_key_resources(self, all_tf_content: str) -> None:
        assert "google_service_account_key" not in all_tf_content

    def test_tfvars_example_has_no_real_project(self) -> None:
        example = (TERRAFORM_DIR / "terraform.tfvars.example").read_text()
        assert "your-gcp-project-id" in example
