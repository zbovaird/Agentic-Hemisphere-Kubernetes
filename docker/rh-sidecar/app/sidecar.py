"""Scaling Sidecar -- warm pool manager, handshake watcher, AgentTask bridge.

Runs alongside the RH Planner in the same pod. Watches a shared volume
for Handshake JSON files, ensures LH Executor capacity via a warm pool
of standby pods, and creates AgentTask CRs to dispatch work.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from kubernetes import client as k8s_client

from .pool import WarmPool

logger = structlog.get_logger()

STANDBY_LABEL = "warm-standby"
STANDBY_PREFIX = "standby-"


def _sanitize_k8s_name(raw: str, max_len: int = 53) -> str:
    """Convert an arbitrary string into a valid K8s resource name fragment."""
    lowered = raw.lower()
    cleaned = re.sub(r"[^a-z0-9-]", "-", lowered)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned[:max_len]


class HandshakeWatcher:
    """Watches a directory for pending handshake JSON files."""

    def __init__(self, pending_dir: Path, processed_dir: Path) -> None:
        self.pending_dir = pending_dir
        self.processed_dir = processed_dir

    def scan(self) -> list[Path]:
        """Return all .json files in the pending directory, sorted by mtime."""
        if not self.pending_dir.exists():
            return []
        files = sorted(self.pending_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        return files

    def parse(self, path: Path) -> dict[str, Any]:
        """Parse a handshake JSON file."""
        return json.loads(path.read_text())

    def move_to_processed(self, path: Path) -> None:
        """Move a handshake file from pending to processed."""
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        dest = self.processed_dir / path.name
        shutil.move(str(path), str(dest))
        logger.info("handshake_processed", file=path.name)


class AgentTaskCreator:
    """Builds and submits AgentTask custom resources."""

    def __init__(self, namespace: str = "owner") -> None:
        self.namespace = namespace

    def build_manifest(
        self,
        handshake: dict[str, Any],
        task_type: str = "execute",
    ) -> dict[str, Any]:
        """Build an AgentTask CR manifest from a handshake."""
        intent_id = handshake["intent_id"]
        safe_name = _sanitize_k8s_name(intent_id)
        ts = datetime.now(UTC).strftime("%H%M%S")
        name = f"at-{safe_name}-{ts}"[:63]

        return {
            "apiVersion": "hemisphere.ai/v1",
            "kind": "AgentTask",
            "metadata": {
                "name": name,
                "namespace": self.namespace,
                "labels": {
                    "app": "agenttask",
                    "managed-by": "rh-sidecar",
                    "intent-id": _sanitize_k8s_name(intent_id, max_len=63),
                },
            },
            "spec": {
                "intent_id": intent_id,
                "task_type": task_type,
                "payload": {
                    "target_files": handshake.get("target_files", []),
                    "acceptance_criteria": handshake.get("acceptance_criteria", []),
                    "architectural_constraint": handshake.get("architectural_constraint", ""),
                },
            },
        }

    def build_standby_manifest(self, pool_index: int) -> dict[str, Any]:
        """Build a standby AgentTask for warm pool pre-warming."""
        ts = datetime.now(UTC).strftime("%H%M%S")
        intent_id = f"{STANDBY_PREFIX}{pool_index}"
        name = f"at-standby-{pool_index}-{ts}"[:63]

        return {
            "apiVersion": "hemisphere.ai/v1",
            "kind": "AgentTask",
            "metadata": {
                "name": name,
                "namespace": self.namespace,
                "labels": {
                    "app": "agenttask",
                    "managed-by": "rh-sidecar",
                    "pool-role": STANDBY_LABEL,
                    "intent-id": intent_id,
                },
            },
            "spec": {
                "intent_id": intent_id,
                "task_type": "standby",
                "payload": {},
            },
        }

    def create(
        self,
        api: k8s_client.CustomObjectsApi,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        """Submit an AgentTask CR to the K8s API."""
        return api.create_namespaced_custom_object(
            group="hemisphere.ai",
            version="v1",
            namespace=self.namespace,
            plural="agenttasks",
            body=manifest,
        )


class ScalingSidecar:
    """Main orchestrator: warm pool + handshake watcher + task bridge."""

    def __init__(
        self,
        warm_pool_size: int = 2,
        employee_namespace: str = "employee",
        task_namespace: str = "owner",
        handshake_dir: str = "/handshakes",
    ) -> None:
        self.pool = WarmPool(desired_size=warm_pool_size)
        self.employee_namespace = employee_namespace
        self.task_creator = AgentTaskCreator(namespace=task_namespace)
        self.watcher = HandshakeWatcher(
            pending_dir=Path(handshake_dir) / "pending",
            processed_dir=Path(handshake_dir) / "processed",
        )
        self._custom_api: k8s_client.CustomObjectsApi | None = None
        self._core_api: k8s_client.CoreV1Api | None = None

    def count_idle_pods(self) -> int:
        """Count LH Executor pods in Running phase with a standby intent-id."""
        if self._core_api is None:
            return 0
        pods = self._core_api.list_namespaced_pod(
            namespace=self.employee_namespace,
            label_selector="app=lh-executor,managed-by=hemisphere-operator",
        )
        idle = 0
        for pod in pods.items:
            labels = pod.metadata.labels or {}
            intent = labels.get("intent-id", "")
            if pod.status.phase == "Running" and intent.startswith(STANDBY_PREFIX):
                idle += 1
        return idle

    def count_standby_agent_tasks(self) -> int:
        """Count standby AgentTasks already created (prevents over-provisioning)."""
        if self._custom_api is None:
            return 0
        try:
            result = self._custom_api.list_namespaced_custom_object(
                group="hemisphere.ai",
                version="v1",
                namespace=self.task_creator.namespace,
                plural="agenttasks",
                label_selector=f"pool-role={STANDBY_LABEL}",
            )
            return len(result.get("items", []))
        except k8s_client.ApiException:
            return 0

    async def ensure_warm_pool(self) -> None:
        """Create standby AgentTasks to fill the warm pool to desired size."""
        if self._custom_api is None:
            return
        current_standby = self.count_standby_agent_tasks()
        deficit = self.pool.deficit(current_standby)
        if deficit <= 0:
            return

        logger.info("warm_pool_filling", deficit=deficit, current_standby=current_standby)
        for i in range(deficit):
            manifest = self.task_creator.build_standby_manifest(pool_index=current_standby + i)
            try:
                self.task_creator.create(self._custom_api, manifest)
                logger.info("standby_task_created", index=current_standby + i)
            except k8s_client.ApiException as e:
                logger.error("standby_creation_failed", error=str(e))

    async def _burst_scale(self, needed: int) -> None:
        """Create additional standby pods for burst capacity."""
        if self._custom_api is None or needed <= 0:
            return
        logger.info("burst_scaling", additional_pods=needed)
        current_idle = self.count_idle_pods()
        for i in range(needed):
            manifest = self.task_creator.build_standby_manifest(pool_index=current_idle + i)
            try:
                self.task_creator.create(self._custom_api, manifest)
            except k8s_client.ApiException as e:
                logger.error("burst_creation_failed", error=str(e))

    async def process_pending(self) -> None:
        """Scan for pending handshakes, burst-scale if needed, then create AgentTasks."""
        if self._custom_api is None:
            return

        pending_files = self.watcher.scan()
        if not pending_files:
            return

        current_idle = self.count_idle_pods()
        burst = self.pool.burst_needed(
            task_count=len(pending_files),
            current_idle=current_idle,
        )
        if burst > 0:
            await self._burst_scale(burst)

        for path in pending_files:
            try:
                handshake = self.watcher.parse(path)
                manifest = self.task_creator.build_manifest(handshake, task_type="execute")
                self.task_creator.create(self._custom_api, manifest)
                self.watcher.move_to_processed(path)
                logger.info("agent_task_dispatched", intent_id=handshake.get("intent_id"))
            except Exception as e:
                logger.error("handshake_processing_failed", file=path.name, error=str(e))
