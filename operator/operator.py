"""Hemisphere Operator -- Kopf-based Kubernetes controller.

The Corpus Callosum of the bicameral architecture: watches for AgentTask
custom resources and spawns sandboxed LH Executor pods to handle them.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import kopf
import structlog
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config

logger = structlog.get_logger()

LH_EXECUTOR_IMAGE = os.environ.get("LH_EXECUTOR_IMAGE", "lh-executor:latest")
EMPLOYEE_NAMESPACE = os.environ.get("EMPLOYEE_NAMESPACE", "employee")
POD_TEMPLATE_PATH = os.environ.get(
    "POD_TEMPLATE_PATH",
    str(Path(__file__).parent / "templates" / "lh_pod_template.yaml"),
)


def _load_k8s_config() -> None:
    """Load Kubernetes config -- in-cluster if available, else local kubeconfig."""
    try:
        k8s_config.load_incluster_config()
    except k8s_config.ConfigException:
        k8s_config.load_kube_config()


def _build_pod_manifest(
    task_name: str,
    task_namespace: str,
    spec: dict[str, Any],
    owner_ref: dict[str, Any],
) -> dict[str, Any]:
    """Build an LH Executor pod manifest from the task spec."""
    task_spec_json = json.dumps({
        "intent_id": spec.get("intent_id", "unknown"),
        "task_type": spec.get("task_type", "execute"),
        "payload": spec.get("payload", {}),
        "target_model": spec.get("target_model", "gemini-2.5-flash"),
    })

    pod_name = f"lh-{task_name[:50]}-{datetime.now(timezone.utc).strftime('%H%M%S')}"

    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "name": pod_name,
            "namespace": EMPLOYEE_NAMESPACE,
            "labels": {
                "app": "lh-executor",
                "hemisphere": "left",
                "managed-by": "hemisphere-operator",
                "intent-id": spec.get("intent_id", "unknown")[:63],
            },
            "ownerReferences": [owner_ref],
        },
        "spec": {
            "serviceAccountName": "lh-executor",
            "runtimeClassName": "gvisor",
            "restartPolicy": "Never",
            "automountServiceAccountToken": True,
            "containers": [{
                "name": "executor",
                "image": LH_EXECUTOR_IMAGE,
                "env": [{
                    "name": "TASK_SPEC",
                    "value": task_spec_json,
                }],
                "resources": {
                    "requests": {"cpu": "250m", "memory": "512Mi"},
                    "limits": {"cpu": "500m", "memory": "1Gi"},
                },
                "securityContext": {
                    "allowPrivilegeEscalation": False,
                    "readOnlyRootFilesystem": True,
                    "runAsNonRoot": True,
                    "runAsUser": 1000,
                    "capabilities": {"drop": ["ALL"]},
                },
                "volumeMounts": [
                    {"name": "tmp", "mountPath": "/tmp"},
                    {"name": "task", "mountPath": "/task"},
                ],
            }],
            "volumes": [
                {"name": "tmp", "emptyDir": {"sizeLimit": "100Mi"}},
                {"name": "task", "emptyDir": {"sizeLimit": "50Mi"}},
            ],
            "tolerations": [{
                "key": "sandbox.gke.io/runtime",
                "operator": "Equal",
                "value": "gvisor",
                "effect": "NoSchedule",
            }],
        },
    }


@kopf.on.create("hemisphere.ai", "v1", "agenttasks")
async def on_task_created(
    spec: dict[str, Any],
    name: str,
    namespace: str,
    uid: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """Handle creation of a new AgentTask -- spawn an LH Executor pod."""
    logger.info(
        "agenttask_created",
        name=name,
        namespace=namespace,
        intent_id=spec.get("intent_id"),
        task_type=spec.get("task_type"),
    )

    owner_ref = {
        "apiVersion": "hemisphere.ai/v1",
        "kind": "AgentTask",
        "name": name,
        "uid": uid,
        "blockOwnerDeletion": True,
        "controller": True,
    }

    pod_manifest = _build_pod_manifest(name, namespace, spec, owner_ref)

    _load_k8s_config()
    v1 = k8s_client.CoreV1Api()

    try:
        pod = v1.create_namespaced_pod(
            namespace=EMPLOYEE_NAMESPACE,
            body=pod_manifest,
        )
        pod_name = pod.metadata.name
        logger.info("lh_pod_spawned", pod_name=pod_name, namespace=EMPLOYEE_NAMESPACE)
    except k8s_client.ApiException as e:
        logger.error("pod_creation_failed", error=str(e))
        return {
            "phase": "Failed",
            "error": f"Failed to create LH pod: {e.reason}",
        }

    return {
        "phase": "Running",
        "pod_name": pod_name,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


@kopf.on.update("hemisphere.ai", "v1", "agenttasks")
async def on_task_updated(
    spec: dict[str, Any],
    status: dict[str, Any],
    name: str,
    namespace: str,
    **kwargs: Any,
) -> None:
    """Handle updates to an AgentTask -- log status transitions."""
    phase = status.get("on_task_created", {}).get("phase", "Unknown")
    logger.info(
        "agenttask_updated",
        name=name,
        namespace=namespace,
        phase=phase,
    )


@kopf.on.delete("hemisphere.ai", "v1", "agenttasks")
async def on_task_deleted(
    spec: dict[str, Any],
    status: dict[str, Any],
    name: str,
    namespace: str,
    **kwargs: Any,
) -> None:
    """Handle deletion of an AgentTask -- clean up associated LH pods."""
    pod_name = status.get("on_task_created", {}).get("pod_name")

    if pod_name:
        logger.info("cleaning_up_lh_pod", pod_name=pod_name)
        _load_k8s_config()
        v1 = k8s_client.CoreV1Api()
        try:
            v1.delete_namespaced_pod(
                name=pod_name,
                namespace=EMPLOYEE_NAMESPACE,
                grace_period_seconds=30,
            )
            logger.info("lh_pod_deleted", pod_name=pod_name)
        except k8s_client.ApiException as e:
            if e.status != 404:
                logger.error("pod_deletion_failed", pod_name=pod_name, error=str(e))

    logger.info("agenttask_deleted", name=name, namespace=namespace)
