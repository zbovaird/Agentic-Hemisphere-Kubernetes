#!/usr/bin/env python3
"""Restaurant POS scenario benchmark: bicameral vs monolithic cost comparison.

Simulates a full day of restaurant operations across three role tiers
(Owner, Manager, Employee) and compares the cost of running each task
through the bicameral (Opus + Flash) architecture vs a monolithic
(Opus-only) approach.

Usage:
    python scripts/pos_benchmark.py
    python scripts/pos_benchmark.py --days 7 --output-dir benchmark-results/

No live cluster, Docker images, or Vertex AI endpoint required.
"""

from __future__ import annotations

import argparse
import json
import random
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

AUTOPILOT_VCPU_HOUR = 0.0445
AUTOPILOT_MEM_GB_HOUR = 0.0049375


@dataclass
class TaskProfile:
    name: str
    role: str
    plan_input: tuple[int, int]
    plan_output: tuple[int, int]
    impl_iterations: tuple[int, int]
    impl_input_per_iter: tuple[int, int]
    impl_output_per_iter: tuple[int, int]
    review_input: tuple[int, int]
    review_output: tuple[int, int]
    pod_seconds: tuple[float, float]
    daily_frequency: int


# --- Owner tasks: complex, strategic, RH-heavy ---

OWNER_TASKS = [
    TaskProfile(
        name="Generate daily P&L report",
        role="owner",
        plan_input=(120_000, 180_000),
        plan_output=(3_000, 6_000),
        impl_iterations=(3, 6),
        impl_input_per_iter=(40_000, 80_000),
        impl_output_per_iter=(5_000, 15_000),
        review_input=(130_000, 200_000),
        review_output=(1_000, 3_000),
        pod_seconds=(30.0, 90.0),
        daily_frequency=1,
    ),
    TaskProfile(
        name="Analyze inventory trends & reorder",
        role="owner",
        plan_input=(100_000, 160_000),
        plan_output=(2_000, 5_000),
        impl_iterations=(4, 8),
        impl_input_per_iter=(50_000, 90_000),
        impl_output_per_iter=(6_000, 18_000),
        review_input=(120_000, 180_000),
        review_output=(1_000, 2_500),
        pod_seconds=(40.0, 120.0),
        daily_frequency=1,
    ),
    TaskProfile(
        name="Review labor cost vs revenue ratio",
        role="owner",
        plan_input=(110_000, 170_000),
        plan_output=(2_500, 5_500),
        impl_iterations=(2, 5),
        impl_input_per_iter=(35_000, 70_000),
        impl_output_per_iter=(4_000, 12_000),
        review_input=(115_000, 175_000),
        review_output=(800, 2_000),
        pod_seconds=(25.0, 75.0),
        daily_frequency=1,
    ),
]

# --- Manager tasks: medium complexity, balanced RH/LH ---

MANAGER_TASKS = [
    TaskProfile(
        name="Build weekly shift schedule (12 employees)",
        role="manager",
        plan_input=(80_000, 120_000),
        plan_output=(2_000, 4_000),
        impl_iterations=(3, 6),
        impl_input_per_iter=(30_000, 60_000),
        impl_output_per_iter=(4_000, 10_000),
        review_input=(90_000, 130_000),
        review_output=(500, 1_500),
        pod_seconds=(20.0, 60.0),
        daily_frequency=2,
    ),
    TaskProfile(
        name="Handle shift swap request",
        role="manager",
        plan_input=(60_000, 100_000),
        plan_output=(1_000, 3_000),
        impl_iterations=(1, 3),
        impl_input_per_iter=(20_000, 50_000),
        impl_output_per_iter=(2_000, 6_000),
        review_input=(70_000, 110_000),
        review_output=(400, 1_200),
        pod_seconds=(10.0, 35.0),
        daily_frequency=3,
    ),
    TaskProfile(
        name="End-of-day reconciliation report",
        role="manager",
        plan_input=(90_000, 140_000),
        plan_output=(2_000, 4_500),
        impl_iterations=(2, 4),
        impl_input_per_iter=(35_000, 65_000),
        impl_output_per_iter=(3_000, 8_000),
        review_input=(95_000, 145_000),
        review_output=(600, 1_800),
        pod_seconds=(15.0, 50.0),
        daily_frequency=3,
    ),
]

# --- Employee tasks: simple, repetitive, LH-heavy ---

EMPLOYEE_TASKS = [
    TaskProfile(
        name="Place new dine-in order",
        role="employee",
        plan_input=(15_000, 30_000),
        plan_output=(500, 1_500),
        impl_iterations=(1, 2),
        impl_input_per_iter=(10_000, 25_000),
        impl_output_per_iter=(1_000, 4_000),
        review_input=(18_000, 35_000),
        review_output=(200, 600),
        pod_seconds=(3.0, 10.0),
        daily_frequency=20,
    ),
    TaskProfile(
        name="Modify existing order",
        role="employee",
        plan_input=(10_000, 22_000),
        plan_output=(300, 1_000),
        impl_iterations=(1, 2),
        impl_input_per_iter=(8_000, 20_000),
        impl_output_per_iter=(800, 3_000),
        review_input=(12_000, 25_000),
        review_output=(150, 500),
        pod_seconds=(2.0, 8.0),
        daily_frequency=10,
    ),
    TaskProfile(
        name="Cancel order with reason code",
        role="employee",
        plan_input=(8_000, 18_000),
        plan_output=(200, 800),
        impl_iterations=(1, 1),
        impl_input_per_iter=(6_000, 15_000),
        impl_output_per_iter=(500, 2_000),
        review_input=(10_000, 20_000),
        review_output=(100, 400),
        pod_seconds=(2.0, 6.0),
        daily_frequency=5,
    ),
    TaskProfile(
        name="Process split-check payment",
        role="employee",
        plan_input=(12_000, 25_000),
        plan_output=(400, 1_200),
        impl_iterations=(1, 2),
        impl_input_per_iter=(10_000, 22_000),
        impl_output_per_iter=(1_000, 3_500),
        review_input=(15_000, 28_000),
        review_output=(200, 600),
        pod_seconds=(3.0, 8.0),
        daily_frequency=8,
    ),
    TaskProfile(
        name="Apply discount/coupon",
        role="employee",
        plan_input=(8_000, 16_000),
        plan_output=(200, 700),
        impl_iterations=(1, 1),
        impl_input_per_iter=(5_000, 12_000),
        impl_output_per_iter=(400, 1_500),
        review_input=(9_000, 18_000),
        review_output=(100, 400),
        pod_seconds=(2.0, 5.0),
        daily_frequency=7,
    ),
]

ALL_PROFILES = OWNER_TASKS + MANAGER_TASKS + EMPLOYEE_TASKS


def _rand(r: tuple[int, int]) -> int:
    return random.randint(r[0], r[1])


def _randf(r: tuple[float, float]) -> float:
    return random.uniform(r[0], r[1])


def simulate_task(task_id: int, profile: TaskProfile) -> dict:
    plan_in = _rand(profile.plan_input)
    plan_out = _rand(profile.plan_output)
    review_in = _rand(profile.review_input)
    review_out = _rand(profile.review_output)
    iterations = _rand(profile.impl_iterations)

    impl_in = sum(_rand(profile.impl_input_per_iter) for _ in range(iterations))
    impl_out = sum(_rand(profile.impl_output_per_iter) for _ in range(iterations))

    pod_secs = _randf(profile.pod_seconds)
    pod_hours = pod_secs / 3600
    infra_cost = pod_hours * 0.25 * AUTOPILOT_VCPU_HOUR + pod_hours * 0.5 * AUTOPILOT_MEM_GB_HOUR

    bicameral_llm = (
        OPUS.cost(plan_in, plan_out)
        + FLASH.cost(impl_in, impl_out)
        + OPUS.cost(review_in, review_out)
    )
    bicameral_total = bicameral_llm + infra_cost

    total_in = plan_in + impl_in + review_in
    total_out = plan_out + impl_out + review_out
    monolithic_total = OPUS.cost(total_in, total_out) + infra_cost

    savings_pct = (1 - bicameral_total / monolithic_total) * 100 if monolithic_total > 0 else 0

    return {
        "task_id": task_id,
        "name": profile.name,
        "role": profile.role,
        "iterations": iterations,
        "tokens": {
            "plan": {"input": plan_in, "output": plan_out},
            "implementation": {"input": impl_in, "output": impl_out},
            "review": {"input": review_in, "output": review_out},
            "total_input": total_in,
            "total_output": total_out,
        },
        "pod_seconds": round(pod_secs, 1),
        "infra_cost": round(infra_cost, 6),
        "cost": {
            "bicameral": round(bicameral_total, 6),
            "monolithic": round(monolithic_total, 6),
            "savings_dollars": round(monolithic_total - bicameral_total, 6),
            "savings_percentage": round(savings_pct, 2),
        },
    }


def run_pos_benchmark(num_days: int = 1, output_dir: Path | None = None) -> dict:
    random.seed(42)

    tasks: list[dict] = []
    task_id = 0
    for _ in range(num_days):
        for profile in ALL_PROFILES:
            for _ in range(profile.daily_frequency):
                task_id += 1
                tasks.append(simulate_task(task_id, profile))

    total_bi = sum(t["cost"]["bicameral"] for t in tasks)
    total_mono = sum(t["cost"]["monolithic"] for t in tasks)
    total_savings = total_mono - total_bi
    avg_savings_pct = (1 - total_bi / total_mono) * 100 if total_mono > 0 else 0

    role_summary = {}
    for role in ("owner", "manager", "employee"):
        role_tasks = [t for t in tasks if t["role"] == role]
        if not role_tasks:
            continue
        bi = sum(t["cost"]["bicameral"] for t in role_tasks)
        mo = sum(t["cost"]["monolithic"] for t in role_tasks)
        role_summary[role] = {
            "task_count": len(role_tasks),
            "total_bicameral": round(bi, 4),
            "total_monolithic": round(mo, 4),
            "savings_dollars": round(mo - bi, 4),
            "savings_percentage": round((1 - bi / mo) * 100, 2) if mo > 0 else 0,
            "avg_cost_per_task_bicameral": round(bi / len(role_tasks), 6),
            "avg_cost_per_task_monolithic": round(mo / len(role_tasks), 6),
        }

    daily_bi = total_bi / num_days
    daily_mono = total_mono / num_days

    report = {
        "benchmark_run": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scenario": "Restaurant POS System",
            "num_days_simulated": num_days,
            "tasks_per_day": task_id // num_days,
            "total_tasks": len(tasks),
            "pricing": {
                "opus": {"model": OPUS.name, "input_per_M": OPUS.input_per_million, "output_per_M": OPUS.output_per_million},
                "flash": {"model": FLASH.name, "input_per_M": FLASH.input_per_million, "output_per_M": FLASH.output_per_million},
            },
            "infra_rates": {
                "autopilot_vcpu_hour": AUTOPILOT_VCPU_HOUR,
                "autopilot_mem_gb_hour": AUTOPILOT_MEM_GB_HOUR,
            },
        },
        "summary": {
            "total_cost_bicameral": round(total_bi, 4),
            "total_cost_monolithic": round(total_mono, 4),
            "total_savings_dollars": round(total_savings, 4),
            "average_savings_percentage": round(avg_savings_pct, 2),
            "daily_cost_bicameral": round(daily_bi, 4),
            "daily_cost_monolithic": round(daily_mono, 4),
            "monthly_projected_bicameral": round(daily_bi * 30, 2),
            "monthly_projected_monolithic": round(daily_mono * 30, 2),
            "monthly_projected_savings": round((daily_mono - daily_bi) * 30, 2),
        },
        "per_role_summary": role_summary,
        "employee_unit_economics": _employee_unit_economics(tasks),
        "tasks": tasks,
    }

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"pos_benchmark_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        report_path.write_text(json.dumps(report, indent=2))
        print(f"\nReport saved to: {report_path}")

    return report


def _employee_unit_economics(tasks: list[dict]) -> dict:
    emp = [t for t in tasks if t["role"] == "employee"]
    if not emp:
        return {}
    bi = sum(t["cost"]["bicameral"] for t in emp)
    mo = sum(t["cost"]["monolithic"] for t in emp)
    return {
        "total_transactions": len(emp),
        "cost_per_transaction_bicameral": round(bi / len(emp), 6),
        "cost_per_transaction_monolithic": round(mo / len(emp), 6),
        "savings_per_transaction": round((mo - bi) / len(emp), 6),
        "note": "Employee tasks dominate volume; this is where bicameral savings compound.",
    }


def print_report(report: dict) -> None:
    s = report["summary"]
    run = report["benchmark_run"]

    print("\n" + "=" * 72)
    print("  RESTAURANT POS BENCHMARK: BICAMERAL vs MONOLITHIC")
    print("=" * 72)
    print(f"  Scenario:         {run['scenario']}")
    print(f"  Days simulated:   {run['num_days_simulated']}")
    print(f"  Tasks per day:    {run['tasks_per_day']}")
    print(f"  Total tasks:      {run['total_tasks']}")
    print(f"  RH model:         {OPUS.name} (${OPUS.input_per_million}/${OPUS.output_per_million} per M tokens)")
    print(f"  LH model:         {FLASH.name} (${FLASH.input_per_million}/${FLASH.output_per_million} per M tokens)")
    print("-" * 72)

    print("\n  DAILY COST COMPARISON")
    print(f"  {'':30s} {'Bicameral':>12s} {'Monolithic':>12s} {'Savings':>10s}")
    print(f"  {'':30s} {'─' * 12:>12s} {'─' * 12:>12s} {'─' * 10:>10s}")

    for role, data in report["per_role_summary"].items():
        days = run["num_days_simulated"]
        bi_daily = data["total_bicameral"] / days
        mo_daily = data["total_monolithic"] / days
        sv = data["savings_percentage"]
        print(f"  {role.capitalize() + ' (' + str(data['task_count'] // days) + '/day)':30s} "
              f"${bi_daily:>10.4f} ${mo_daily:>10.4f} {sv:>8.1f}%")

    print(f"  {'─' * 68}")
    print(f"  {'TOTAL DAILY':30s} ${s['daily_cost_bicameral']:>10.4f} ${s['daily_cost_monolithic']:>10.4f} "
          f"{s['average_savings_percentage']:>8.1f}%")

    print(f"\n  MONTHLY PROJECTION (30 days)")
    print(f"  {'Bicameral':30s} ${s['monthly_projected_bicameral']:>10.2f}")
    print(f"  {'Monolithic (Opus only)':30s} ${s['monthly_projected_monolithic']:>10.2f}")
    print(f"  {'Monthly savings':30s} ${s['monthly_projected_savings']:>10.2f}")

    eu = report.get("employee_unit_economics", {})
    if eu:
        print(f"\n  EMPLOYEE UNIT ECONOMICS (per transaction)")
        print(f"  {'Transactions':30s} {eu['total_transactions']:>10d}")
        print(f"  {'Cost/txn (bicameral)':30s} ${eu['cost_per_transaction_bicameral']:>10.6f}")
        print(f"  {'Cost/txn (monolithic)':30s} ${eu['cost_per_transaction_monolithic']:>10.6f}")
        print(f"  {'Savings/txn':30s} ${eu['savings_per_transaction']:>10.6f}")

    print("\n" + "=" * 72)

    print("\n  WHAT THIS MEANS")
    print("  " + "─" * 68)
    if s["monthly_projected_savings"] > 0:
        pct = s["average_savings_percentage"]
        monthly_save = s["monthly_projected_savings"]
        annual_save = monthly_save * 12
        print(f"  The bicameral architecture saves {pct:.1f}% on LLM costs for this POS workload.")
        print(f"  That is ${monthly_save:.2f}/month or ${annual_save:.2f}/year.")
        print(f"  The savings come primarily from routing high-volume employee tasks")
        print(f"  (order placement, modifications, payments) through the cheaper Flash")
        print(f"  model, while reserving Opus for owner-level strategic analysis and")
        print(f"  manager-level scheduling that genuinely benefits from deeper reasoning.")
    print("=" * 72 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Restaurant POS: bicameral vs monolithic cost benchmark")
    parser.add_argument("--days", type=int, default=1, help="Number of days to simulate (default: 1)")
    parser.add_argument("--output-dir", type=str, default=None, help="Directory to save JSON report")
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else None
    report = run_pos_benchmark(num_days=args.days, output_dir=output_dir)
    print_report(report)


if __name__ == "__main__":
    main()
