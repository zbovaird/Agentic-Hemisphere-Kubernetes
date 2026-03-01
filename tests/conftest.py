"""Shared test fixtures for Agentic-Hemisphere-Kubernetes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def project_root() -> Path:
    """Return the project root directory."""
    return Path(__file__).parent.parent


@pytest.fixture
def sample_handshake() -> dict[str, Any]:
    """Return a sample handshake payload for testing."""
    return {
        "intent_id": "test-intent-001",
        "architectural_constraint": "Test constraint",
        "target_files": ["tests/test_example.py"],
        "acceptance_criteria": ["All tests pass"],
        "implementation_proof": {
            "test_log": "",
            "diff_summary": "",
            "lint_status": "pass",
        },
    }


@pytest.fixture
def sample_agent_task_spec() -> dict[str, Any]:
    """Return a sample AgentTask CR spec for testing."""
    return {
        "intent_id": "test-task-001",
        "task_type": "execute",
        "payload": {
            "tool": "echo",
            "args": ["hello world"],
        },
        "target_model": "gemini-2.5-flash",
    }


@pytest.fixture
def terraform_dir(project_root: Path) -> Path:
    """Return the terraform directory path."""
    return project_root / "terraform"


@pytest.fixture
def k8s_dir(project_root: Path) -> Path:
    """Return the k8s manifests directory path."""
    return project_root / "k8s"
