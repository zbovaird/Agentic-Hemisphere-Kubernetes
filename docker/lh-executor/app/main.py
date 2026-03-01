"""LH Executor entrypoint.

Ephemeral container that reads a TaskSpec from environment variables
or a mounted file, executes it, and writes the result to stdout.
Designed to run as a Kubernetes Job pod.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import structlog

from .executor import Executor
from .models import TaskSpec

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)

logger = structlog.get_logger()


def load_task_spec() -> TaskSpec:
    """Load task spec from TASK_SPEC env var or /task/spec.json file."""
    spec_json = os.environ.get("TASK_SPEC")

    if spec_json:
        return TaskSpec.model_validate_json(spec_json)

    spec_file = os.environ.get("TASK_SPEC_FILE", "/task/spec.json")
    if os.path.isfile(spec_file):
        with open(spec_file) as f:
            return TaskSpec.model_validate(json.load(f))

    logger.error("no_task_spec", message="No TASK_SPEC env var or spec file found")
    sys.exit(1)


async def main() -> None:
    logger.info("lh_executor_starting")

    spec = load_task_spec()
    logger.info("task_spec_loaded", intent_id=spec.intent_id, task_type=spec.task_type)

    executor = Executor()
    result = await executor.execute(spec)

    result_json = result.model_dump_json(indent=2)
    print(result_json)

    if executor.should_escalate():
        escalation = executor.build_escalate_signal(
            spec, failure_pattern=result.error or "Unknown failure"
        )
        logger.warning("escalation_emitted", signal=escalation.model_dump())

    if not result.success:
        logger.error("task_failed", intent_id=spec.intent_id, error=result.error)
        sys.exit(1)

    logger.info("task_succeeded", intent_id=spec.intent_id)


if __name__ == "__main__":
    asyncio.run(main())
