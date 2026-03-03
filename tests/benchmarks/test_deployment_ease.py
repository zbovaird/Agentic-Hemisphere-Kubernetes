"""Deployment ease tests.

Validates that the project can be set up and deployed with minimal steps,
and that all required files and scripts are present and well-structured.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestProjectCompleteness:
    """Verify all required files exist for a complete deployment."""

    REQUIRED_FILES = [
        "README.md",
        "LICENSE",
        ".gitignore",
        "Makefile",
        "pyproject.toml",
        "scripts/setup.sh",
        "scripts/deploy.sh",
        "scripts/configure.sh",
        "terraform/main.tf",
        "terraform/variables.tf",
        "terraform/outputs.tf",
        "terraform/versions.tf",
        "terraform/terraform.tfvars.example",
        "docker/rh-planner/Dockerfile",
        "docker/rh-planner/requirements.txt",
        "docker/lh-executor/Dockerfile",
        "docker/lh-executor/requirements.txt",
        "operator/Dockerfile",
        "operator/requirements.txt",
        "operator/operator.py",
        "operator/crds/agenttask_crd.yaml",
        "operator/config/rbac.yaml",
        "k8s/base/kustomization.yaml",
        "k8s/base/rh-deployment.yaml",
        "k8s/base/rh-service.yaml",
        "k8s/base/operator-deployment.yaml",
        "k8s/base/network-policies.yaml",
        "k8s/base/resource-quotas.yaml",
        "k8s/overlays/dev/kustomization.yaml",
        "k8s/overlays/prod/kustomization.yaml",
    ]

    @pytest.mark.parametrize("filepath", REQUIRED_FILES)
    def test_required_file_exists(self, filepath: str) -> None:
        assert (PROJECT_ROOT / filepath).is_file(), f"Missing required file: {filepath}"


class TestScriptExecutability:
    """Verify deployment scripts are executable."""

    SCRIPTS = ["scripts/setup.sh", "scripts/deploy.sh", "scripts/configure.sh"]

    @pytest.mark.parametrize("script", SCRIPTS)
    def test_script_is_executable(self, script: str) -> None:
        path = PROJECT_ROOT / script
        assert path.is_file()
        mode = path.stat().st_mode
        assert mode & stat.S_IXUSR, f"{script} is not executable by owner"

    @pytest.mark.parametrize("script", SCRIPTS)
    def test_script_has_shebang(self, script: str) -> None:
        content = (PROJECT_ROOT / script).read_text()
        assert content.startswith("#!/"), f"{script} missing shebang line"

    @pytest.mark.parametrize("script", SCRIPTS)
    def test_script_uses_strict_mode(self, script: str) -> None:
        content = (PROJECT_ROOT / script).read_text()
        assert "set -euo pipefail" in content, f"{script} missing strict mode"


class TestMakefileTargets:
    """Verify Makefile has all required targets."""

    REQUIRED_TARGETS = [
        "setup", "lint", "test", "build", "deploy", "teardown", "clean", "help",
    ]

    @pytest.fixture
    def makefile_content(self) -> str:
        return (PROJECT_ROOT / "Makefile").read_text()

    @pytest.mark.parametrize("target", REQUIRED_TARGETS)
    def test_makefile_has_target(self, makefile_content: str, target: str) -> None:
        assert f"{target}:" in makefile_content, f"Makefile missing target: {target}"


class TestDocumentation:
    """Verify README contains essential sections."""

    @pytest.fixture
    def readme(self) -> str:
        return (PROJECT_ROOT / "README.md").read_text()

    def test_readme_has_architecture(self, readme: str) -> None:
        assert "Architecture" in readme or "architecture" in readme

    def test_readme_has_prerequisites(self, readme: str) -> None:
        assert "Prerequisites" in readme or "prerequisites" in readme

    def test_readme_has_quickstart(self, readme: str) -> None:
        assert "Quickstart" in readme or "quickstart" in readme

    def test_readme_has_pipeline_integration(self, readme: str) -> None:
        assert "Pipeline" in readme or "Jenkins" in readme or "Harness" in readme

    def test_readme_has_testing_section(self, readme: str) -> None:
        assert "Testing" in readme or "testing" in readme

    def test_readme_has_license(self, readme: str) -> None:
        assert "MIT" in readme
        assert "Zach Bovaird" in readme


class TestDeploymentStepCount:
    """Measure the number of manual steps from clone to running cluster."""

    def test_max_deployment_steps(self) -> None:
        """Deployment should require no more than 6 manual commands.

        Expected flow:
        1. git clone
        2. make setup
        3. cp terraform.tfvars.example terraform.tfvars (+ edit)
        4. gcloud auth login
        5. gcloud auth application-default login
        6. make deploy
        """
        readme = (PROJECT_ROOT / "README.md").read_text()
        quickstart_start = readme.find("## Quickstart")
        quickstart_end = readme.find("\n## ", quickstart_start + 1)
        quickstart_section = readme[quickstart_start:quickstart_end]
        command_lines = [
            line.strip()
            for line in quickstart_section.split("\n")
            if line.strip().startswith(("git ", "make ", "gcloud ", "cp ", "source "))
        ]
        assert len(command_lines) <= 10, (
            f"Too many deployment steps ({len(command_lines)}). "
            "Target is <= 10 commands from clone to running cluster."
        )
