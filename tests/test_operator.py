"""Unit tests for the Hemisphere Operator (Corpus Callosum)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

OPERATOR_DIR = Path(__file__).parent.parent / "operator"
CRD_PATH = OPERATOR_DIR / "crds" / "agenttask_crd.yaml"
RBAC_PATH = OPERATOR_DIR / "config" / "rbac.yaml"
POD_TEMPLATE_PATH = OPERATOR_DIR / "templates" / "lh_pod_template.yaml"

sys.path.insert(0, str(OPERATOR_DIR))


class TestCRDSchema:
    """Validate the AgentTask CRD definition."""

    @pytest.fixture
    def crd(self) -> dict[str, Any]:
        return yaml.safe_load(CRD_PATH.read_text())

    def test_crd_api_version(self, crd: dict) -> None:
        assert crd["apiVersion"] == "apiextensions.k8s.io/v1"

    def test_crd_kind(self, crd: dict) -> None:
        assert crd["kind"] == "CustomResourceDefinition"

    def test_crd_group(self, crd: dict) -> None:
        assert crd["spec"]["group"] == "hemisphere.ai"

    def test_crd_names(self, crd: dict) -> None:
        names = crd["spec"]["names"]
        assert names["kind"] == "AgentTask"
        assert names["plural"] == "agenttasks"
        assert "at" in names["shortNames"]

    def test_crd_has_spec_fields(self, crd: dict) -> None:
        schema = crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]
        spec_props = schema["properties"]["spec"]["properties"]
        assert "intent_id" in spec_props
        assert "task_type" in spec_props
        assert "payload" in spec_props
        assert "target_model" in spec_props
        assert "timeout_seconds" in spec_props

    def test_crd_task_type_enum(self, crd: dict) -> None:
        schema = crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]
        task_type = schema["properties"]["spec"]["properties"]["task_type"]
        assert set(task_type["enum"]) == {"execute", "test", "lint", "standby"}

    def test_crd_has_status_fields(self, crd: dict) -> None:
        schema = crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]
        status_props = schema["properties"]["status"]["properties"]
        assert "phase" in status_props
        assert "pod_name" in status_props
        assert "result" in status_props
        assert "signal" in status_props

    def test_crd_status_phase_enum(self, crd: dict) -> None:
        schema = crd["spec"]["versions"][0]["schema"]["openAPIV3Schema"]
        phase = schema["properties"]["status"]["properties"]["phase"]
        expected = {"Pending", "Running", "Standby", "Completed", "Failed", "Escalated"}
        assert set(phase["enum"]) == expected

    def test_crd_has_status_subresource(self, crd: dict) -> None:
        subresources = crd["spec"]["versions"][0]["subresources"]
        assert "status" in subresources

    def test_crd_has_printer_columns(self, crd: dict) -> None:
        columns = crd["spec"]["versions"][0]["additionalPrinterColumns"]
        column_names = {c["name"] for c in columns}
        assert "Intent" in column_names
        assert "Type" in column_names
        assert "Phase" in column_names


class TestRBAC:
    """Validate RBAC configuration."""

    @pytest.fixture
    def rbac_docs(self) -> list[dict[str, Any]]:
        return list(yaml.safe_load_all(RBAC_PATH.read_text()))

    def test_operator_service_account(self, rbac_docs: list) -> None:
        sa = next(
            d for d in rbac_docs
            if d["kind"] == "ServiceAccount" and d["metadata"]["name"] == "hemisphere-operator"
        )
        assert sa["metadata"]["namespace"] == "owner"
        assert "iam.gke.io/gcp-service-account" in sa["metadata"]["annotations"]

    def test_operator_cluster_role(self, rbac_docs: list) -> None:
        role = next(d for d in rbac_docs if d["kind"] == "ClusterRole")
        api_groups = {rule["apiGroups"][0] for rule in role["rules"]}
        assert "hemisphere.ai" in api_groups
        assert "" in api_groups  # core API group for pods

    def test_operator_can_manage_agenttasks(self, rbac_docs: list) -> None:
        role = next(d for d in rbac_docs if d["kind"] == "ClusterRole")
        at_rule = next(
            r for r in role["rules"]
            if "agenttasks" in r["resources"]
        )
        assert "create" in at_rule["verbs"]
        assert "delete" in at_rule["verbs"]
        assert "watch" in at_rule["verbs"]

    def test_operator_can_manage_pods(self, rbac_docs: list) -> None:
        role = next(d for d in rbac_docs if d["kind"] == "ClusterRole")
        pod_rule = next(
            r for r in role["rules"]
            if "pods" in r["resources"] and r["apiGroups"] == [""]
        )
        assert "create" in pod_rule["verbs"]
        assert "delete" in pod_rule["verbs"]

    def test_lh_executor_service_account(self, rbac_docs: list) -> None:
        sa = next(
            d for d in rbac_docs
            if d["kind"] == "ServiceAccount" and d["metadata"]["name"] == "lh-executor"
        )
        assert sa["metadata"]["namespace"] == "employee"

    def test_rh_planner_service_account(self, rbac_docs: list) -> None:
        sa = next(
            d for d in rbac_docs
            if d["kind"] == "ServiceAccount" and d["metadata"]["name"] == "rh-planner"
        )
        assert sa["metadata"]["namespace"] == "owner"

    def test_no_cluster_admin(self, rbac_docs: list) -> None:
        for doc in rbac_docs:
            if doc["kind"] == "ClusterRoleBinding":
                assert doc["roleRef"]["name"] != "cluster-admin"


class TestPodTemplate:
    """Validate the LH pod template."""

    @pytest.fixture
    def template(self) -> dict[str, Any]:
        return yaml.safe_load(POD_TEMPLATE_PATH.read_text())

    def test_gvisor_runtime(self, template: dict) -> None:
        assert template["spec"]["runtimeClassName"] == "gvisor"

    def test_never_restart(self, template: dict) -> None:
        assert template["spec"]["restartPolicy"] == "Never"

    def test_security_context(self, template: dict) -> None:
        sc = template["spec"]["containers"][0]["securityContext"]
        assert sc["allowPrivilegeEscalation"] is False
        assert sc["readOnlyRootFilesystem"] is True
        assert sc["runAsNonRoot"] is True
        assert sc["capabilities"]["drop"] == ["ALL"]

    def test_resource_limits(self, template: dict) -> None:
        resources = template["spec"]["containers"][0]["resources"]
        assert "requests" in resources
        assert "limits" in resources
        assert resources["requests"]["cpu"] == "250m"
        assert resources["limits"]["memory"] == "1Gi"

    def test_gvisor_toleration(self, template: dict) -> None:
        tolerations = template["spec"]["tolerations"]
        gvisor_tol = next(
            t for t in tolerations if t.get("key") == "sandbox.gke.io/runtime"
        )
        assert gvisor_tol["value"] == "gvisor"


def _import_operator_module():
    """Import operator.py without conflicting with Python's built-in operator module."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "hemisphere_operator", OPERATOR_DIR / "operator.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestOperatorLogic:
    """Test the operator's pod-building logic (no live cluster needed)."""

    def test_build_pod_manifest(self) -> None:
        op_mod = _import_operator_module()
        _build_pod_manifest = op_mod._build_pod_manifest

        spec = {
            "intent_id": "test-001",
            "task_type": "execute",
            "payload": {"command": "echo hello"},
            "target_model": "gemini-2.5-flash",
        }
        manifest = _build_pod_manifest("test-task", "owner", spec)

        assert manifest["metadata"]["namespace"] == "employee"
        assert manifest["metadata"]["labels"]["app"] == "lh-executor"
        assert manifest["metadata"]["labels"]["intent-id"] == "test-001"
        assert manifest["spec"]["runtimeClassName"] == "gvisor"
        assert manifest["spec"]["restartPolicy"] == "Never"

        container = manifest["spec"]["containers"][0]
        assert container["image"] == "lh-executor:latest"
        assert container["securityContext"]["allowPrivilegeEscalation"] is False

        task_spec_env = next(
            e for e in container["env"] if e["name"] == "TASK_SPEC"
        )
        parsed = json.loads(task_spec_env["value"])
        assert parsed["intent_id"] == "test-001"
        assert parsed["task_type"] == "execute"

    def test_build_pod_manifest_truncates_long_names(self) -> None:
        op_mod = _import_operator_module()
        _build_pod_manifest = op_mod._build_pod_manifest

        long_name = "a" * 100
        spec = {"intent_id": long_name, "task_type": "test"}
        manifest = _build_pod_manifest(long_name, "owner", spec)
        assert len(manifest["metadata"]["name"]) <= 63
        assert len(manifest["metadata"]["labels"]["intent-id"]) <= 63
