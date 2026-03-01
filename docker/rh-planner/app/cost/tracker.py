"""Cost tracker for measuring bicameral vs monolithic architecture savings.

Records token usage per phase (plan, implement, review), computes costs
using configurable model pricing, and generates comparison reports.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


@dataclass
class ModelPricing:
    """Per-model pricing in dollars per million tokens."""

    name: str
    input_per_million: float
    output_per_million: float

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_per_million / 1_000_000
            + output_tokens * self.output_per_million / 1_000_000
        )


OPUS_PRICING = ModelPricing(name="claude-4.6-opus", input_per_million=15.00, output_per_million=75.00)
FLASH_PRICING = ModelPricing(name="gemini-2.5-flash", input_per_million=0.15, output_per_million=0.60)


@dataclass
class PhaseUsage:
    """Token usage for a single phase of a task."""

    phase: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class TaskCostRecord:
    """Complete cost record for one task lifecycle."""

    intent_id: str
    phases: list[PhaseUsage] = field(default_factory=list)
    gke_pod_seconds: float = 0.0
    vertex_prediction_cost: float = 0.0
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def bicameral_cost(self, opus: ModelPricing = OPUS_PRICING, flash: ModelPricing = FLASH_PRICING) -> float:
        total = 0.0
        for phase in self.phases:
            pricing = opus if "opus" in phase.model.lower() else flash
            total += pricing.cost(phase.input_tokens, phase.output_tokens)
        total += self._infra_cost()
        return total

    def monolithic_cost(self, opus: ModelPricing = OPUS_PRICING) -> float:
        total_input = sum(p.input_tokens for p in self.phases)
        total_output = sum(p.output_tokens for p in self.phases)
        return opus.cost(total_input, total_output) + self._infra_cost()

    def savings_percentage(self) -> float:
        mono = self.monolithic_cost()
        if mono == 0:
            return 0.0
        return (1 - self.bicameral_cost() / mono) * 100

    def total_latency_ms(self) -> float:
        return sum(p.latency_ms for p in self.phases)

    def _infra_cost(self) -> float:
        autopilot_vcpu_hour = 0.0445
        autopilot_mem_gb_hour = 0.0049375
        pod_hours = self.gke_pod_seconds / 3600
        cpu_cost = pod_hours * 0.25 * autopilot_vcpu_hour
        mem_cost = pod_hours * 0.5 * autopilot_mem_gb_hour
        return cpu_cost + mem_cost + self.vertex_prediction_cost

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "created_at": self.created_at,
            "phases": [
                {
                    "phase": p.phase,
                    "model": p.model,
                    "input_tokens": p.input_tokens,
                    "output_tokens": p.output_tokens,
                    "latency_ms": p.latency_ms,
                    "timestamp": p.timestamp,
                }
                for p in self.phases
            ],
            "gke_pod_seconds": self.gke_pod_seconds,
            "vertex_prediction_cost": self.vertex_prediction_cost,
            "bicameral_cost": round(self.bicameral_cost(), 6),
            "monolithic_cost": round(self.monolithic_cost(), 6),
            "savings_percentage": round(self.savings_percentage(), 2),
            "total_latency_ms": round(self.total_latency_ms(), 2),
        }


class CostTracker:
    """Tracks costs across multiple task lifecycles and generates reports."""

    def __init__(self, output_dir: str | Path | None = None) -> None:
        self.records: list[TaskCostRecord] = []
        self.output_dir = Path(output_dir) if output_dir else None
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)

    def start_phase(self, intent_id: str, phase: str, model: str) -> _PhaseTimer:
        """Start timing a phase. Use as a context manager."""
        return _PhaseTimer(self, intent_id, phase, model)

    def record_phase(
        self,
        intent_id: str,
        phase: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: float = 0.0,
    ) -> None:
        """Manually record a phase's token usage."""
        record = self._get_or_create_record(intent_id)
        usage = PhaseUsage(
            phase=phase,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )
        record.phases.append(usage)

        logger.info(
            "cost_phase_recorded",
            intent_id=intent_id,
            phase=phase,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )

    def set_infra_cost(
        self,
        intent_id: str,
        gke_pod_seconds: float = 0.0,
        vertex_prediction_cost: float = 0.0,
    ) -> None:
        record = self._get_or_create_record(intent_id)
        record.gke_pod_seconds = gke_pod_seconds
        record.vertex_prediction_cost = vertex_prediction_cost

    def get_record(self, intent_id: str) -> TaskCostRecord | None:
        return next((r for r in self.records if r.intent_id == intent_id), None)

    def generate_report(self) -> dict[str, Any]:
        """Generate an aggregate cost comparison report."""
        if not self.records:
            return {"error": "No records to report"}

        total_bicameral = sum(r.bicameral_cost() for r in self.records)
        total_monolithic = sum(r.monolithic_cost() for r in self.records)
        total_savings_pct = (1 - total_bicameral / total_monolithic) * 100 if total_monolithic > 0 else 0

        total_input = sum(p.input_tokens for r in self.records for p in r.phases)
        total_output = sum(p.output_tokens for r in self.records for p in r.phases)

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "task_count": len(self.records),
            "total_tokens": {"input": total_input, "output": total_output},
            "cost_comparison": {
                "bicameral_total": round(total_bicameral, 4),
                "monolithic_total": round(total_monolithic, 4),
                "savings_dollars": round(total_monolithic - total_bicameral, 4),
                "savings_percentage": round(total_savings_pct, 2),
            },
            "per_task_average": {
                "bicameral": round(total_bicameral / len(self.records), 4),
                "monolithic": round(total_monolithic / len(self.records), 4),
            },
            "latency": {
                "avg_ms": round(
                    sum(r.total_latency_ms() for r in self.records) / len(self.records), 2
                ),
                "max_ms": round(max(r.total_latency_ms() for r in self.records), 2),
            },
            "records": [r.to_dict() for r in self.records],
        }

        if self.output_dir:
            report_path = self.output_dir / f"cost_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
            report_path.write_text(json.dumps(report, indent=2))
            logger.info("cost_report_saved", path=str(report_path))

        return report

    def _get_or_create_record(self, intent_id: str) -> TaskCostRecord:
        record = self.get_record(intent_id)
        if record is None:
            record = TaskCostRecord(intent_id=intent_id)
            self.records.append(record)
        return record


class _PhaseTimer:
    """Context manager that times a phase and records token usage."""

    def __init__(self, tracker: CostTracker, intent_id: str, phase: str, model: str) -> None:
        self.tracker = tracker
        self.intent_id = intent_id
        self.phase = phase
        self.model = model
        self._start: float = 0
        self.input_tokens: int = 0
        self.output_tokens: int = 0

    def __enter__(self) -> _PhaseTimer:
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: Any) -> None:
        elapsed_ms = (time.monotonic() - self._start) * 1000
        self.tracker.record_phase(
            intent_id=self.intent_id,
            phase=self.phase,
            model=self.model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            latency_ms=elapsed_ms,
        )
