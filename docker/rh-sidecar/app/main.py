"""RH Scaling Sidecar FastAPI application.

Provides health and pool status endpoints on :8081.
The main sidecar loop runs as a background task on startup.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import structlog
from fastapi import FastAPI
from kubernetes import client as k8s_client
from kubernetes import config as k8s_config

from .models import PoolStatus
from .sidecar import ScalingSidecar

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger()

WARM_POOL_SIZE = int(os.environ.get("WARM_POOL_SIZE", "2"))
EMPLOYEE_NAMESPACE = os.environ.get("EMPLOYEE_NAMESPACE", "employee")
TASK_NAMESPACE = os.environ.get("TASK_NAMESPACE", "owner")
HANDSHAKE_DIR = os.environ.get("HANDSHAKE_DIR", "/handshakes")
POLL_INTERVAL = float(os.environ.get("POLL_INTERVAL", "1.0"))

sidecar = ScalingSidecar(
    warm_pool_size=WARM_POOL_SIZE,
    employee_namespace=EMPLOYEE_NAMESPACE,
    task_namespace=TASK_NAMESPACE,
    handshake_dir=HANDSHAKE_DIR,
)


def _load_k8s_config() -> None:
    try:
        k8s_config.load_incluster_config()
    except k8s_config.ConfigException:
        k8s_config.load_kube_config()


async def _sidecar_loop() -> None:
    """Background loop: maintain warm pool and process pending handshakes."""
    try:
        _load_k8s_config()
        sidecar._custom_api = k8s_client.CustomObjectsApi()
        sidecar._core_api = k8s_client.CoreV1Api()
    except Exception as e:
        logger.error("k8s_config_failed", error=str(e))
        return

    logger.info("sidecar_started", warm_pool_size=WARM_POOL_SIZE)

    while True:
        try:
            await sidecar.ensure_warm_pool()
            await sidecar.process_pending()
        except Exception as e:
            logger.error("sidecar_loop_error", error=str(e))
        await asyncio.sleep(POLL_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(_sidecar_loop())
    yield
    task.cancel()


app = FastAPI(
    title="RH Scaling Sidecar",
    description="Warm pool manager and Handshake-to-AgentTask bridge",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "component": "rh-sidecar"}


@app.get("/pool", response_model=PoolStatus)
async def pool_status() -> PoolStatus:
    return PoolStatus(
        desired_size=sidecar.pool.desired_size,
        current_idle=sidecar.count_idle_pods(),
    )
