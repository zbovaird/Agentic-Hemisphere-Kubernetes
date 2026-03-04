"""Warm pool state tracking and burst calculation.

Tracks the desired number of idle LH Executor pods and computes
how many additional pods are needed for burst scaling.
"""

from __future__ import annotations

DEFAULT_POOL_SIZE = 2


class WarmPool:
    """Manages warm pool sizing and deficit/burst calculations."""

    def __init__(self, desired_size: int = DEFAULT_POOL_SIZE) -> None:
        self.desired_size = desired_size

    def deficit(self, current_idle: int) -> int:
        """How many standby pods need to be created to reach the desired pool size."""
        return max(0, self.desired_size - current_idle)

    def burst_needed(self, task_count: int, current_idle: int) -> int:
        """How many extra pods are needed beyond idle capacity for a batch of tasks."""
        return max(0, task_count - current_idle)
