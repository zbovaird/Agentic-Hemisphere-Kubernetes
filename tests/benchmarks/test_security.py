"""Security validation tests.

Validates RBAC, gVisor enforcement, NetworkPolicies, privilege escalation
prevention, and secret management across all Kubernetes manifests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

PROJECT_ROOT = Path(__file__).parent.parent.parent
K8S_BASE = PROJECT_ROOT / "k8s" / "base"
OPERATOR_DIR = PROJECT_ROOT / "operator"


def _load_all_yaml(directory: Path) -> list[dict[str, Any]]:
    """Load all YAML documents from all .yaml files in a directory."""
    docs = []
    for yaml_file in directory.glob("*.yaml"):
        for doc in yaml.safe_load_all(yaml_file.read_text()):
            if doc:
                docs.append(doc)
    return docs


def _find_containers(docs: list[dict]) -> list[dict[str, Any]]:
    """Extract all container specs from deployments and pod templates."""
    containers = []
    for doc in docs:
        kind = doc.get("kind", "")
        if kind == "Deployment":
            template = doc.get("spec", {}).get("template", {}).get("spec", {})
            containers.extend(template.get("containers", []))
        elif kind == "Pod":
            containers.extend(doc.get("spec", {}).get("containers", []))
    return containers


class TestGVisorEnforcement:
    """Validate gVisor sandbox is enforced on LH pods."""

    def test_lh_pod_template_uses_gvisor(self) -> None:
        template = yaml.safe_load(
            (OPERATOR_DIR / "templates" / "lh_pod_template.yaml").read_text()
        )
        assert template["spec"]["runtimeClassName"] == "gvisor"

    def test_lh_pod_template_has_gvisor_toleration(self) -> None:
        template = yaml.safe_load(
            (OPERATOR_DIR / "templates" / "lh_pod_template.yaml").read_text()
        )
        tolerations = template["spec"].get("tolerations", [])
        gvisor_tols = [
            t for t in tolerations
            if t.get("key") == "sandbox.gke.io/runtime"
        ]
        assert len(gvisor_tols) > 0


class TestPrivilegeEscalation:
    """Validate no containers allow privilege escalation."""

    @pytest.fixture
    def base_docs(self) -> list[dict[str, Any]]:
        return _load_all_yaml(K8S_BASE)

    @pytest.fixture
    def all_containers(self, base_docs: list) -> list[dict[str, Any]]:
        return _find_containers(base_docs)

    @pytest.mark.security
    def test_no_privilege_escalation(self, all_containers: list) -> None:
        for container in all_containers:
            sc = container.get("securityContext", {})
            assert sc.get("allowPrivilegeEscalation") is False, (
                f"Container '{container.get('name')}' allows privilege escalation"
            )

    @pytest.mark.security
    def test_read_only_root_filesystem(self, all_containers: list) -> None:
        for container in all_containers:
            sc = container.get("securityContext", {})
            assert sc.get("readOnlyRootFilesystem") is True, (
                f"Container '{container.get('name')}' does not have read-only root filesystem"
            )

    @pytest.mark.security
    def test_run_as_non_root(self, all_containers: list) -> None:
        for container in all_containers:
            sc = container.get("securityContext", {})
            assert sc.get("runAsNonRoot") is True, (
                f"Container '{container.get('name')}' does not enforce runAsNonRoot"
            )

    @pytest.mark.security
    def test_drop_all_capabilities(self, all_containers: list) -> None:
        for container in all_containers:
            sc = container.get("securityContext", {})
            caps = sc.get("capabilities", {})
            assert "ALL" in caps.get("drop", []), (
                f"Container '{container.get('name')}' does not drop ALL capabilities"
            )

    @pytest.mark.security
    def test_lh_template_no_privilege_escalation(self) -> None:
        template = yaml.safe_load(
            (OPERATOR_DIR / "templates" / "lh_pod_template.yaml").read_text()
        )
        sc = template["spec"]["containers"][0]["securityContext"]
        assert sc["allowPrivilegeEscalation"] is False
        assert sc["readOnlyRootFilesystem"] is True
        assert sc["runAsNonRoot"] is True
        assert "ALL" in sc["capabilities"]["drop"]


class TestNetworkPolicies:
    """Validate NetworkPolicy configuration."""

    @pytest.fixture
    def network_policies(self) -> list[dict[str, Any]]:
        docs = _load_all_yaml(K8S_BASE)
        return [d for d in docs if d.get("kind") == "NetworkPolicy"]

    @pytest.mark.security
    def test_employee_default_deny(self, network_policies: list) -> None:
        deny = next(
            p for p in network_policies
            if p["metadata"]["name"] == "deny-all-employee"
        )
        assert deny["metadata"]["namespace"] == "employee"
        assert "Ingress" in deny["spec"]["policyTypes"]
        assert "Egress" in deny["spec"]["policyTypes"]

    @pytest.mark.security
    def test_owner_default_deny(self, network_policies: list) -> None:
        deny = next(
            p for p in network_policies
            if p["metadata"]["name"] == "deny-all-owner"
        )
        assert deny["metadata"]["namespace"] == "owner"

    @pytest.mark.security
    def test_lh_egress_restricted(self, network_policies: list) -> None:
        lh_egress = next(
            p for p in network_policies
            if p["metadata"]["name"] == "allow-lh-egress"
        )
        assert lh_egress["metadata"]["namespace"] == "employee"
        egress_rules = lh_egress["spec"]["egress"]
        assert len(egress_rules) > 0

        external_rule = next(
            r for r in egress_rules
            if any(
                "ipBlock" in to_item
                for to_item in r.get("to", [])
            )
        )
        ip_block = next(
            to_item["ipBlock"]
            for to_item in external_rule["to"]
            if "ipBlock" in to_item
        )
        assert "10.0.0.0/8" in ip_block.get("except", [])
        assert "172.16.0.0/12" in ip_block.get("except", [])
        assert "192.168.0.0/16" in ip_block.get("except", [])

    @pytest.mark.security
    def test_lh_can_reach_dns(self, network_policies: list) -> None:
        lh_egress = next(
            p for p in network_policies
            if p["metadata"]["name"] == "allow-lh-egress"
        )
        dns_rule = next(
            r for r in lh_egress["spec"]["egress"]
            if any(p.get("port") == 53 for p in r.get("ports", []))
        )
        assert dns_rule is not None


class TestResourceQuotas:
    """Validate resource quotas prevent sub-agent sprawl."""

    @pytest.fixture
    def quotas(self) -> list[dict[str, Any]]:
        docs = _load_all_yaml(K8S_BASE)
        return [d for d in docs if d.get("kind") == "ResourceQuota"]

    @pytest.fixture
    def limit_ranges(self) -> list[dict[str, Any]]:
        docs = _load_all_yaml(K8S_BASE)
        return [d for d in docs if d.get("kind") == "LimitRange"]

    @pytest.mark.security
    def test_employee_has_quota(self, quotas: list) -> None:
        employee_quotas = [
            q for q in quotas if q["metadata"]["namespace"] == "employee"
        ]
        assert len(employee_quotas) > 0

    @pytest.mark.security
    def test_employee_pod_limit(self, quotas: list) -> None:
        quota = next(
            q for q in quotas if q["metadata"]["namespace"] == "employee"
        )
        assert "pods" in quota["spec"]["hard"]
        assert int(quota["spec"]["hard"]["pods"]) <= 20

    @pytest.mark.security
    def test_employee_has_limit_range(self, limit_ranges: list) -> None:
        employee_lr = [
            lr for lr in limit_ranges if lr["metadata"]["namespace"] == "employee"
        ]
        assert len(employee_lr) > 0


class TestNoSecrets:
    """Validate no secrets or credentials in any manifest."""

    @pytest.mark.security
    def test_no_secret_env_vars(self) -> None:
        docs = _load_all_yaml(K8S_BASE)
        containers = _find_containers(docs)
        for container in containers:
            for env in container.get("env", []):
                name = env.get("name", "").lower()
                assert "password" not in name, f"Password env var found: {env['name']}"
                assert "secret" not in name, f"Secret env var found: {env['name']}"
                assert "api_key" not in name, f"API key env var found: {env['name']}"

    @pytest.mark.security
    def test_no_secret_volumes(self) -> None:
        docs = _load_all_yaml(K8S_BASE)
        for doc in docs:
            if doc.get("kind") == "Deployment":
                volumes = (
                    doc.get("spec", {})
                    .get("template", {})
                    .get("spec", {})
                    .get("volumes", [])
                )
                for vol in volumes:
                    assert "secret" not in vol, (
                        f"Secret volume found in {doc['metadata']['name']}"
                    )

    @pytest.mark.security
    def test_rbac_no_cluster_admin(self) -> None:
        docs = list(yaml.safe_load_all(
            (OPERATOR_DIR / "config" / "rbac.yaml").read_text()
        ))
        for doc in docs:
            if doc.get("kind") == "ClusterRoleBinding":
                assert doc["roleRef"]["name"] != "cluster-admin"
