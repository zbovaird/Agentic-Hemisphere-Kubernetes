#!/usr/bin/env python3
"""Benchmark script: bicameral vs monolithic cost and efficiency comparison.

Runs N simulated task lifecycles through the bicameral architecture,
records token usage and latency, then computes what the same workload
would cost on a monolithic (Opus-only) architecture.

Usage:
    python scripts/benchmark.py --tasks 10 --output-dir benchmark-results/

The script does NOT require a live cluster or Vertex AI endpoint.
It uses simulated token counts based on realistic task profiles.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ModelPricing:
    name: str
    input_per_million: float
    output_per_million: float

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_per_million / 1_000_000
            + output_tokens * self.output_per_million / 1_000_000
        )


OPUS = ModelPricing("claude-4.6-opus", input_per_million=15.00, output_per_million=75.00)
FLASH = ModelPricing("gemini-2.5-flash", input_per_million=0.15, output_per_million=0.60)

TASK_PROFILES = {
    "simple": {
        "plan_input": (80_000, 120_000),
        "plan_output": (1_000, 3_000),
        "impl_iterations": (1, 3),
        "impl_input_per_iter": (30_000, 60_000),
        "impl_output_per_iter": (3_000, 8_000),
        "review_input": (90_000, 130_000),
        "review_output": (500, 1_500),
    },
    "medium": {
        "plan_input": (100_000, 150_000),
        "plan_output": (2_000, 5_000),
        "impl_iterations": (3, 5),
        "impl_input_per_iter": (40_000, 80_000),
        "impl_output_per_iter": (5_000, 12_000),
        "review_input": (110_000, 160_000),
        "review_output": (500, 2_000),
    },
    "complex": {
        "plan_input": (150_000, 250_000),
        "plan_output": (3_000, 8_000),
        "impl_iterations": (5, 10),
        "impl_input_per_iter": (50_000, 100_000),
        "impl_output_per_iter": (8_000, 20_000),
        "review_input": (160_000, 270_000),
        "review_output": (1_000, 3_000),
    },
}


def _rand(range_tuple: tuple[int, int]) -> int:
    return random.randint(*range_tuple)


def simulate_task(task_id: int, profile_name: str) -> dict:
    profile = TASK_PROFILES[profile_name]

    plan_in = _rand(profile["plan_input"])
    plan_out = _rand(profile["plan_output"])
    review_in = _rand(profile["review_input"])
    review_out = _rand(profile["review_output"])
    iterations = _rand(profile["impl_iterations"])

    impl_in_total = sum(_rand(profile["impl_input_per_iter"]) for _ in range(iterations))
    impl_out_total = sum(_rand(profile["impl_output_per_iter"]) for _ in range(iterations))

    bicameral_cost = (
        OPUS.cost(plan_in, plan_out)
        + FLASH.cost(impl_in_total, impl_out_total)
        + OPUS.cost(review_in, review_out)
    )

    total_in = plan_in + impl_in_total + review_in
    total_out = plan_out + impl_out_total + review_out
    monolithic_cost = OPUS.cost(total_in, total_out)

    savings_pct = (1 - bicameral_cost / monolithic_cost) * 100 if monolithic_cost > 0 else 0

    plan_latency = random.uniform(2000, 8000)
    impl_latency = iterations * random.uniform(1500, 5000)
    review_latency = random.uniform(2000, 6000)
    network_overhead = 3 * random.uniform(50, 200)

    return {
        "task_id": task_id,
        "profile": profile_name,
        "iterations": iterations,
        "tokens": {
            "plan": {"input": plan_in, "output": plan_out, "model": OPUS.name},
            "implementation": {"input": impl_in_total, "output": impl_out_total, "model": FLASH.name},
            "review": {"input": review_in, "output": review_out, "model": OPUS.name},
            "total_input": total_in,
            "total_output": total_out,
        },
        "cost": {
            "bicameral": round(bicameral_cost, 6),
            "monolithic": round(monolithic_cost, 6),
            "savings_dollars": round(monolithic_cost - bicameral_cost, 6),
            "savings_percentage": round(savings_pct, 2),
        },
        "latency": {
            "plan_ms": round(plan_latency, 1),
            "implementation_ms": round(impl_latency, 1),
            "review_ms": round(review_latency, 1),
            "network_overhead_ms": round(network_overhead, 1),
            "total_ms": round(plan_latency + impl_latency + review_latency + network_overhead, 1),
        },
    }


def run_benchmark(num_tasks: int, output_dir: Path | None = None) -> dict:
    random.seed(42)

    profiles = list(TASK_PROFILES.keys())
    tasks = []
    for i in range(num_tasks):
        profile = profiles[i % len(profiles)]
        tasks.append(simulate_task(i + 1, profile))

    total_bicameral = sum(t["cost"]["bicameral"] for t in tasks)
    total_monolithic = sum(t["cost"]["monolithic"] for t in tasks)
    total_savings = total_monolithic - total_bicameral
    avg_savings_pct = (1 - total_bicameral / total_monolithic) * 100 if total_monolithic > 0 else 0

    avg_latency = sum(t["latency"]["total_ms"] for t in tasks) / len(tasks)

    report = {
        "benchmark_run": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "num_tasks": num_tasks,
            "profiles_used": list(TASK_PROFILES.keys()),
            "pricing": {
                "opus": {"input_per_M": OPUS.input_per_million, "output_per_M": OPUS.output_per_million},
                "flash": {"input_per_M": FLASH.input_per_million, "output_per_M": FLASH.output_per_million},
            },
        },
        "summary": {
            "total_cost_bicameral": round(total_bicameral, 4),
            "total_cost_monolithic": round(total_monolithic, 4),
            "total_savings_dollars": round(total_savings, 4),
            "average_savings_percentage": round(avg_savings_pct, 2),
            "cost_per_task_bicameral": round(total_bicameral / num_tasks, 4),
            "cost_per_task_monolithic": round(total_monolithic / num_tasks, 4),
            "average_latency_ms": round(avg_latency, 1),
        },
        "per_profile_summary": {},
        "tasks": tasks,
    }

    for profile_name in profiles:
        profile_tasks = [t for t in tasks if t["profile"] == profile_name]
        if profile_tasks:
            bi = sum(t["cost"]["bicameral"] for t in profile_tasks)
            mo = sum(t["cost"]["monolithic"] for t in profile_tasks)
            report["per_profile_summary"][profile_name] = {
                "count": len(profile_tasks),
                "avg_bicameral": round(bi / len(profile_tasks), 4),
                "avg_monolithic": round(mo / len(profile_tasks), 4),
                "avg_savings_pct": round((1 - bi / mo) * 100, 2) if mo > 0 else 0,
                "avg_iterations": round(sum(t["iterations"] for t in profile_tasks) / len(profile_tasks), 1),
            }

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"benchmark_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        report_path.write_text(json.dumps(report, indent=2))
        print(f"Report saved to: {report_path}")

    return report


def print_summary(report: dict) -> None:
    s = report["summary"]
    print("\n" + "=" * 60)
    print("  BICAMERAL vs MONOLITHIC COST BENCHMARK")
    print("=" * 60)
    print(f"  Tasks run:              {report['benchmark_run']['num_tasks']}")
    print(f"  Monolithic total:       ${s['total_cost_monolithic']:.4f}")
    print(f"  Bicameral total:        ${s['total_cost_bicameral']:.4f}")
    print(f"  Savings:                ${s['total_savings_dollars']:.4f} ({s['average_savings_percentage']:.1f}%)")
    print(f"  Avg cost/task (mono):   ${s['cost_per_task_monolithic']:.4f}")
    print(f"  Avg cost/task (bi):     ${s['cost_per_task_bicameral']:.4f}")
    print(f"  Avg latency:            {s['average_latency_ms']:.0f}ms")
    print("-" * 60)

    for name, data in report.get("per_profile_summary", {}).items():
        print(f"  [{name:>8}]  avg savings: {data['avg_savings_pct']:.1f}%  "
              f"avg iters: {data['avg_iterations']:.1f}  "
              f"bi: ${data['avg_bicameral']:.4f}  mono: ${data['avg_monolithic']:.4f}")

    print("=" * 60 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bicameral vs Monolithic cost benchmark")
    parser.add_argument("--tasks", type=int, default=30, help="Number of tasks to simulate")
    parser.add_argument("--output-dir", type=str, default=None, help="Directory to save report JSON")
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else None
    report = run_benchmark(args.tasks, output_dir)
    print_summary(report)


if __name__ == "__main__":
    main()
