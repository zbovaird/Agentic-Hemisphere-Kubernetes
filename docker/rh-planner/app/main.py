"""RH Planner FastAPI application.

Persistent service running in the owner namespace that provides
architectural planning and implementation review endpoints.
"""

from __future__ import annotations

import os

import structlog
from fastapi import FastAPI, HTTPException

from .models import PlanRequest, PlanResponse, ReviewRequest, ReviewResponse
from .planner import Planner

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger()

app = FastAPI(
    title="RH Planner",
    description="Right Hemisphere architectural planner for the bicameral agent system",
    version="0.1.0",
)

planner = Planner(
    vertex_endpoint=os.environ.get("VERTEX_ENDPOINT"),
    model_name=os.environ.get("RH_MODEL"),
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "component": "rh-planner"}


@app.post("/plan", response_model=PlanResponse)
async def create_plan(request: PlanRequest) -> PlanResponse:
    """Generate an architectural plan (Handshake) for the LH Executor."""
    try:
        return await planner.create_plan(request)
    except Exception as e:
        logger.error("plan_failed", intent_id=request.intent_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/review", response_model=ReviewResponse)
async def review_implementation(request: ReviewRequest) -> ReviewResponse:
    """Review an implementation proof and issue APPROVE or SUPPRESS signal."""
    try:
        return await planner.review(request)
    except Exception as e:
        logger.error("review_failed", intent_id=request.intent_id, error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
