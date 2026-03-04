"""Unit tests for the RH Scaling Sidecar.

Tests warm pool management, handshake file watching, AgentTask CR creation,
and burst scaling logic. Written TDD-first per project coding standards.

Uses importlib to load sidecar modules directly from docker/rh-sidecar/app/
without modifying sys.path, avoiding conflicts with the rh-planner's app package.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SIDECAR_APP_DIR = Path(__file__).parent.parent / "docker" / "rh-sidecar" / "app"


def _load_module(name: str, filepath: Path):
    """Load a single Python file as a module, handling relative imports."""
    full_name = f"_sidecar_app.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]

    # Ensure the parent package exists
    pkg_name = "_sidecar_app"
    if pkg_name not in sys.modules:
        pkg_spec = importlib.util.spec_from_file_location(
            pkg_name,
            SIDECAR_APP_DIR / "__init__.py",
            submodule_search_locations=[str(SIDECAR_APP_DIR)],
        )
        assert pkg_spec is not None and pkg_spec.loader is not None
        pkg = importlib.util.module_from_spec(pkg_spec)
        sys.modules[pkg_name] = pkg
        pkg_spec.loader.exec_module(pkg)

    spec = importlib.util.spec_from_file_location(full_name, filepath)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Load modules using our isolated loader
_pool_mod = _load_module("pool", SIDECAR_APP_DIR / "pool.py")
WarmPool = _pool_mod.WarmPool

_sidecar_mod = _load_module("sidecar", SIDECAR_APP_DIR / "sidecar.py")
HandshakeWatcher = _sidecar_mod.HandshakeWatcher
AgentTaskCreator = _sidecar_mod.AgentTaskCreator
ScalingSidecar = _sidecar_mod.ScalingSidecar


class TestWarmPool:
    """Test warm pool state tracking and burst calculation."""

    def test_pool_desired_size(self) -> None:
        pool = WarmPool(desired_size=3)
        assert pool.desired_size == 3

    def test_pool_default_size(self) -> None:
        pool = WarmPool()
        assert pool.desired_size == 2

    def test_pool_deficit_when_empty(self) -> None:
        pool = WarmPool(desired_size=3)
        assert pool.deficit(current_idle=0) == 3

    def test_pool_deficit_when_partial(self) -> None:
        pool = WarmPool(desired_size=3)
        assert pool.deficit(current_idle=1) == 2

    def test_pool_no_deficit_when_full(self) -> None:
        pool = WarmPool(desired_size=3)
        assert pool.deficit(current_idle=3) == 0

    def test_pool_no_deficit_when_over(self) -> None:
        pool = WarmPool(desired_size=3)
        assert pool.deficit(current_idle=5) == 0

    def test_burst_needed(self) -> None:
        pool = WarmPool(desired_size=2)
        needed = pool.burst_needed(task_count=5, current_idle=2)
        assert needed == 3

    def test_burst_not_needed_when_idle_sufficient(self) -> None:
        pool = WarmPool(desired_size=2)
        needed = pool.burst_needed(task_count=1, current_idle=3)
        assert needed == 0

    def test_burst_accounts_for_zero_idle(self) -> None:
        pool = WarmPool(desired_size=2)
        needed = pool.burst_needed(task_count=3, current_idle=0)
        assert needed == 3


class TestHandshakeWatcher:
    """Test handshake file detection and parsing."""

    def test_scan_pending_directory(self, tmp_path: Path) -> None:
        pending = tmp_path / "pending"
        pending.mkdir()
        processed = tmp_path / "processed"
        processed.mkdir()

        handshake = {
            "intent_id": "test-001",
            "architectural_constraint": "None",
            "target_files": ["src/main.py"],
            "acceptance_criteria": ["Tests pass"],
        }
        (pending / "test-001.json").write_text(json.dumps(handshake))

        watcher = HandshakeWatcher(pending_dir=pending, processed_dir=processed)
        files = watcher.scan()
        assert len(files) == 1
        assert files[0].name == "test-001.json"

    def test_scan_ignores_non_json(self, tmp_path: Path) -> None:
        pending = tmp_path / "pending"
        pending.mkdir()
        processed = tmp_path / "processed"
        processed.mkdir()

        (pending / "readme.txt").write_text("not a handshake")

        watcher = HandshakeWatcher(pending_dir=pending, processed_dir=processed)
        assert watcher.scan() == []

    def test_parse_handshake_file(self, tmp_path: Path) -> None:
        pending = tmp_path / "pending"
        pending.mkdir()
        processed = tmp_path / "processed"
        processed.mkdir()

        handshake = {
            "intent_id": "test-002",
            "architectural_constraint": "GKE only",
            "target_files": [],
            "acceptance_criteria": ["lint passes"],
        }
        path = pending / "test-002.json"
        path.write_text(json.dumps(handshake))

        watcher = HandshakeWatcher(pending_dir=pending, processed_dir=processed)
        parsed = watcher.parse(path)
        assert parsed["intent_id"] == "test-002"
        assert parsed["architectural_constraint"] == "GKE only"

    def test_move_to_processed(self, tmp_path: Path) -> None:
        pending = tmp_path / "pending"
        pending.mkdir()
        processed = tmp_path / "processed"
        processed.mkdir()

        path = pending / "test-003.json"
        path.write_text(json.dumps({"intent_id": "test-003"}))

        watcher = HandshakeWatcher(pending_dir=pending, processed_dir=processed)
        watcher.move_to_processed(path)

        assert not path.exists()
        assert (processed / "test-003.json").exists()

    def test_scan_empty_directory(self, tmp_path: Path) -> None:
        pending = tmp_path / "pending"
        pending.mkdir()
        processed = tmp_path / "processed"
        processed.mkdir()

        watcher = HandshakeWatcher(pending_dir=pending, processed_dir=processed)
        assert watcher.scan() == []


class TestAgentTaskCreator:
    """Test AgentTask CR creation from handshakes."""

    def test_build_agent_task_manifest(self) -> None:
        creator = AgentTaskCreator(namespace="owner")
        handshake = {
            "intent_id": "task-001",
            "architectural_constraint": "No new deps",
            "target_files": ["src/main.py"],
            "acceptance_criteria": ["Tests pass"],
        }

        manifest = creator.build_manifest(handshake, task_type="execute")
        assert manifest["apiVersion"] == "hemisphere.ai/v1"
        assert manifest["kind"] == "AgentTask"
        assert manifest["spec"]["intent_id"] == "task-001"
        assert manifest["spec"]["task_type"] == "execute"
        assert manifest["spec"]["payload"]["target_files"] == ["src/main.py"]

    def test_build_standby_manifest(self) -> None:
        creator = AgentTaskCreator(namespace="owner")
        manifest = creator.build_standby_manifest(pool_index=0)
        assert manifest["spec"]["task_type"] == "standby"
        assert manifest["spec"]["intent_id"].startswith("standby-")
        assert manifest["metadata"]["labels"]["pool-role"] == "warm-standby"

    def test_manifest_name_is_valid_k8s(self) -> None:
        creator = AgentTaskCreator(namespace="owner")
        handshake = {
            "intent_id": "UPPER_CASE-with spaces!@#",
            "architectural_constraint": "c",
            "target_files": [],
            "acceptance_criteria": [],
        }
        manifest = creator.build_manifest(handshake, task_type="execute")
        name = manifest["metadata"]["name"]
        assert len(name) <= 63
        assert name == name.lower()
        assert all(c.isalnum() or c == "-" for c in name)

    def test_build_manifest_includes_handshake_in_payload(self) -> None:
        creator = AgentTaskCreator(namespace="owner")
        handshake = {
            "intent_id": "task-002",
            "architectural_constraint": "Constraint",
            "target_files": ["a.py", "b.py"],
            "acceptance_criteria": ["lint", "test"],
        }
        manifest = creator.build_manifest(handshake, task_type="test")
        payload = manifest["spec"]["payload"]
        assert payload["acceptance_criteria"] == ["lint", "test"]
        assert payload["architectural_constraint"] == "Constraint"

    @pytest.mark.asyncio
    async def test_create_calls_k8s_api(self) -> None:
        creator = AgentTaskCreator(namespace="owner")
        mock_api = MagicMock()
        mock_api.create_namespaced_custom_object = MagicMock(
            return_value={"metadata": {"name": "at-task-001"}}
        )

        manifest = {
            "apiVersion": "hemisphere.ai/v1",
            "kind": "AgentTask",
            "metadata": {"name": "at-task-001", "namespace": "owner"},
            "spec": {"intent_id": "task-001", "task_type": "execute", "payload": {}},
        }

        creator.create(mock_api, manifest)
        mock_api.create_namespaced_custom_object.assert_called_once_with(
            group="hemisphere.ai",
            version="v1",
            namespace="owner",
            plural="agenttasks",
            body=manifest,
        )


class TestSidecarLoop:
    """Test the main sidecar orchestration logic."""

    @pytest.mark.asyncio
    async def test_ensure_warm_pool_creates_standby_tasks(self) -> None:
        mock_custom_api = MagicMock()
        mock_custom_api.create_namespaced_custom_object = MagicMock(
            return_value={"metadata": {"name": "standby-0"}}
        )
        mock_core_api = MagicMock()
        mock_core_api.list_namespaced_pod = MagicMock(
            return_value=MagicMock(items=[])
        )

        sidecar = ScalingSidecar(
            warm_pool_size=2,
            employee_namespace="employee",
            task_namespace="owner",
            handshake_dir="/tmp/test-handshakes",  # noqa: S108
        )
        sidecar._custom_api = mock_custom_api
        sidecar._core_api = mock_core_api

        await sidecar.ensure_warm_pool()
        assert mock_custom_api.create_namespaced_custom_object.call_count == 2

    @pytest.mark.asyncio
    async def test_process_handshake_creates_agent_task(self, tmp_path: Path) -> None:
        pending = tmp_path / "pending"
        pending.mkdir()
        processed = tmp_path / "processed"
        processed.mkdir()

        handshake = {
            "intent_id": "real-task-001",
            "architectural_constraint": "None",
            "target_files": ["src/main.py"],
            "acceptance_criteria": ["Tests pass"],
        }
        (pending / "real-task-001.json").write_text(json.dumps(handshake))

        mock_custom_api = MagicMock()
        mock_custom_api.create_namespaced_custom_object = MagicMock(
            return_value={"metadata": {"name": "at-real-task-001"}}
        )
        mock_core_api = MagicMock()
        mock_core_api.list_namespaced_pod = MagicMock(
            return_value=MagicMock(items=[])
        )

        sidecar = ScalingSidecar(
            warm_pool_size=0,
            employee_namespace="employee",
            task_namespace="owner",
            handshake_dir=str(tmp_path),
        )
        sidecar._custom_api = mock_custom_api
        sidecar._core_api = mock_core_api

        await sidecar.process_pending()

        mock_custom_api.create_namespaced_custom_object.assert_called()
        call_args = mock_custom_api.create_namespaced_custom_object.call_args
        body = call_args.kwargs.get("body") or call_args[1].get("body")
        assert body["spec"]["intent_id"] == "real-task-001"
        assert body["spec"]["task_type"] == "execute"

        assert not (pending / "real-task-001.json").exists()
        assert (processed / "real-task-001.json").exists()

    @pytest.mark.asyncio
    async def test_burst_scaling_before_task_dispatch(self, tmp_path: Path) -> None:
        pending = tmp_path / "pending"
        pending.mkdir()
        processed = tmp_path / "processed"
        processed.mkdir()

        for i in range(3):
            handshake = {
                "intent_id": f"burst-{i}",
                "architectural_constraint": "None",
                "target_files": [],
                "acceptance_criteria": [],
            }
            (pending / f"burst-{i}.json").write_text(json.dumps(handshake))

        mock_custom_api = MagicMock()
        mock_custom_api.create_namespaced_custom_object = MagicMock(
            return_value={"metadata": {"name": "at-burst"}}
        )
        mock_core_api = MagicMock()
        mock_core_api.list_namespaced_pod = MagicMock(
            return_value=MagicMock(items=[])
        )

        sidecar = ScalingSidecar(
            warm_pool_size=1,
            employee_namespace="employee",
            task_namespace="owner",
            handshake_dir=str(tmp_path),
        )
        sidecar._custom_api = mock_custom_api
        sidecar._core_api = mock_core_api

        await sidecar.process_pending()

        total_calls = mock_custom_api.create_namespaced_custom_object.call_count
        assert total_calls >= 3

    @pytest.mark.asyncio
    async def test_idle_pod_counting(self) -> None:
        mock_pod_running = MagicMock()
        mock_pod_running.status.phase = "Running"
        mock_pod_running.metadata.labels = {
            "app": "lh-executor",
            "managed-by": "hemisphere-operator",
            "intent-id": "standby-0",
        }

        mock_pod_active = MagicMock()
        mock_pod_active.status.phase = "Running"
        mock_pod_active.metadata.labels = {
            "app": "lh-executor",
            "managed-by": "hemisphere-operator",
            "intent-id": "real-task",
        }

        mock_core_api = MagicMock()
        mock_core_api.list_namespaced_pod = MagicMock(
            return_value=MagicMock(items=[mock_pod_running, mock_pod_active])
        )

        sidecar = ScalingSidecar(
            warm_pool_size=2,
            employee_namespace="employee",
            task_namespace="owner",
            handshake_dir="/tmp/test",  # noqa: S108
        )
        sidecar._core_api = mock_core_api

        idle = sidecar.count_idle_pods()
        assert idle == 1


class TestSidecarHealthEndpoint:
    """Test the sidecar FastAPI health endpoint."""

    @pytest.fixture
    def client(self):
        # Temporarily swap sys.path and module cache to load the sidecar's app.main
        saved_modules = {}
        for key in list(sys.modules.keys()):
            if key == "app" or key.startswith("app."):
                saved_modules[key] = sys.modules.pop(key)

        sidecar_root = str(SIDECAR_APP_DIR.parent)
        sys.path.insert(0, sidecar_root)

        from app.main import app as sidecar_app
        from fastapi.testclient import TestClient

        yield TestClient(sidecar_app)

        sys.path.remove(sidecar_root)
        for key in list(sys.modules.keys()):
            if key == "app" or key.startswith("app."):
                sys.modules.pop(key, None)
        sys.modules.update(saved_modules)

    def test_health_returns_ok(self, client) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["component"] == "rh-sidecar"

    def test_pool_status_endpoint(self, client) -> None:
        response = client.get("/pool")
        assert response.status_code == 200
        data = response.json()
        assert "desired_size" in data
        assert "component" in data
