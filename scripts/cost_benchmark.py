#!/usr/bin/env python3
"""Role-based cost benchmark: bicameral vs monolithic cost comparison.

Simulates a multi-role workload across three tiers (Owner, Manager, Employee)
and compares the cost of running each task through the bicameral (RH Planner +
Flash Executor) architecture vs a monolithic (single-model) approach.

Supports multiple RH planner models and four optimization strategies.

Usage:
    python scripts/cost_benchmark.py
    python scripts/cost_benchmark.py --days 7 --output-dir benchmark-results/
    python scripts/cost_benchmark.py --rh-model gemini-2.5-pro --all-optimizations
    python scripts/cost_benchmark.py --matrix

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


RH_MODELS: dict[str, ModelPricing] = {
    "claude-4.6-opus": ModelPricing("claude-4.6-opus", input_per_million=5.00, output_per_million=25.00),
    "gpt-5": ModelPricing("gpt-5", input_per_million=1.25, output_per_million=10.00),
    "gemini-2.5-pro": ModelPricing("gemini-2.5-pro", input_per_million=1.25, output_per_million=10.00),
    "o3": ModelPricing("o3", input_per_million=2.00, output_per_million=8.00),
    "deepseek-r1": ModelPricing("deepseek-r1", input_per_million=0.55, output_per_million=2.19),
    "claude-haiku-4.5": ModelPricing("claude-haiku-4.5", input_per_million=1.00, output_per_million=5.00),
}

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


@dataclass
class OptimizationFlags:
    cache_plans: bool = False
    compress_prompts: bool = False
    batch_similar: bool = False
    skip_low_risk_review: bool = False

    @property
    def label(self) -> str:
        if not any([self.cache_plans, self.compress_prompts, self.batch_similar, self.skip_low_risk_review]):
            return "No optimization"
        parts = []
        if self.cache_plans:
            parts.append("cache")
        if self.compress_prompts:
            parts.append("compress")
        if self.batch_similar:
            parts.append("batch")
        if self.skip_low_risk_review:
            parts.append("skip-review")
        return "+ " + ", ".join(parts)


OWNER_TASKS = [
    TaskProfile(
        name="Generate daily financial report",
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
        name="Analyze resource trends & replenishment",
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
        name="Review cost vs revenue ratio",
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

MANAGER_TASKS = [
    TaskProfile(
        name="Build weekly schedule",
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
        name="Handle schedule swap request",
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
        name="End-of-day reconciliation",
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

EMPLOYEE_TASKS = [
    TaskProfile(
        name="Create new transaction",
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
        name="Modify existing transaction",
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
        name="Cancel transaction with reason",
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
        name="Process split payment",
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
        name="Apply promotion",
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

CACHE_HIT_RATES = {"owner": 0.0, "manager": 0.30, "employee": 0.80}
COMPRESSION_FACTOR = 0.40  # keep 40% of tokens (60% reduction)


def _rand(r: tuple[int, int]) -> int:
    return random.randint(r[0], r[1])


def _randf(r: tuple[float, float]) -> float:
    return random.uniform(r[0], r[1])


def simulate_task(
    task_id: int,
    profile: TaskProfile,
    rh_model: ModelPricing,
    opts: OptimizationFlags,
    plan_cache: dict[str, tuple[int, int]],
    batch_counts: dict[str, int],
) -> dict:
    plan_in = _rand(profile.plan_input)
    plan_out = _rand(profile.plan_output)
    review_in = _rand(profile.review_input)
    review_out = _rand(profile.review_output)
    iterations = _rand(profile.impl_iterations)

    impl_in = sum(_rand(profile.impl_input_per_iter) for _ in range(iterations))
    impl_out = sum(_rand(profile.impl_output_per_iter) for _ in range(iterations))

    plan_in_eff, plan_out_eff = plan_in, plan_out
    review_in_eff, review_out_eff = review_in, review_out
    impl_in_eff, impl_out_eff = impl_in, impl_out

    cache_hit = False
    if opts.cache_plans:
        hit_rate = CACHE_HIT_RATES.get(profile.role, 0.0)
        if profile.name in plan_cache and random.random() < hit_rate:
            plan_in_eff, plan_out_eff = 0, 0
            cache_hit = True
        else:
            plan_cache[profile.name] = (plan_in, plan_out)

    if opts.compress_prompts:
        plan_in_eff = int(plan_in_eff * COMPRESSION_FACTOR)
        review_in_eff = int(review_in_eff * COMPRESSION_FACTOR)
        impl_in_eff = int(impl_in_eff * COMPRESSION_FACTOR)

    batch_divisor = 1
    if opts.batch_similar:
        count = batch_counts.get(profile.name, 1)
        if count > 1:
            batch_divisor = count
            plan_in_eff = plan_in_eff // batch_divisor
            plan_out_eff = plan_out_eff // batch_divisor

    skip_review = False
    if opts.skip_low_risk_review and profile.role == "employee":
        review_in_eff, review_out_eff = 0, 0
        skip_review = True

    pod_secs = _randf(profile.pod_seconds)
    pod_hours = pod_secs / 3600
    infra_cost = pod_hours * 0.25 * AUTOPILOT_VCPU_HOUR + pod_hours * 0.5 * AUTOPILOT_MEM_GB_HOUR

    bicameral_llm = (
        rh_model.cost(plan_in_eff, plan_out_eff)
        + FLASH.cost(impl_in_eff, impl_out_eff)
        + rh_model.cost(review_in_eff, review_out_eff)
    )
    bicameral_total = bicameral_llm + infra_cost

    total_in = plan_in + impl_in + review_in
    total_out = plan_out + impl_out + review_out
    mono_model = RH_MODELS["claude-4.6-opus"]
    monolithic_total = mono_model.cost(total_in, total_out) + infra_cost

    savings_pct = (1 - bicameral_total / monolithic_total) * 100 if monolithic_total > 0 else 0

    return {
        "task_id": task_id,
        "name": profile.name,
        "role": profile.role,
        "iterations": iterations,
        "rh_model": rh_model.name,
        "optimizations": {
            "cache_hit": cache_hit,
            "compression": opts.compress_prompts,
            "batch_divisor": batch_divisor,
            "review_skipped": skip_review,
        },
        "tokens": {
            "plan": {"input": plan_in, "output": plan_out, "effective_input": plan_in_eff, "effective_output": plan_out_eff},
            "implementation": {"input": impl_in, "output": impl_out, "effective_input": impl_in_eff, "effective_output": impl_out_eff},
            "review": {"input": review_in, "output": review_out, "effective_input": review_in_eff, "effective_output": review_out_eff},
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


def _build_batch_counts(profiles: list[TaskProfile], num_days: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in profiles:
        counts[p.name] = p.daily_frequency * num_days
    return counts


def run_cost_benchmark(
    num_days: int = 1,
    rh_model_name: str = "claude-4.6-opus",
    opts: OptimizationFlags | None = None,
    output_dir: Path | None = None,
) -> dict:
    random.seed(42)
    if opts is None:
        opts = OptimizationFlags()

    rh_model = RH_MODELS[rh_model_name]
    plan_cache: dict[str, tuple[int, int]] = {}
    batch_counts = _build_batch_counts(ALL_PROFILES, num_days) if opts.batch_similar else {}

    tasks: list[dict] = []
    task_id = 0
    for _ in range(num_days):
        for profile in ALL_PROFILES:
            for _ in range(profile.daily_frequency):
                task_id += 1
                tasks.append(simulate_task(task_id, profile, rh_model, opts, plan_cache, batch_counts))

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
            "scenario": "Multi-role business operations",
            "num_days_simulated": num_days,
            "tasks_per_day": task_id // num_days,
            "total_tasks": len(tasks),
            "rh_model": rh_model.name,
            "optimizations": opts.label,
            "pricing": {
                "rh": {"model": rh_model.name, "input_per_M": rh_model.input_per_million, "output_per_M": rh_model.output_per_million},
                "lh": {"model": FLASH.name, "input_per_M": FLASH.input_per_million, "output_per_M": FLASH.output_per_million},
                "monolithic_baseline": {"model": "claude-4.6-opus", "input_per_M": 5.00, "output_per_M": 25.00},
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
        "high_volume_unit_economics": _high_volume_unit_economics(tasks),
        "tasks": tasks,
    }

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"cost_benchmark_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        report_path.write_text(json.dumps(report, indent=2))
        print(f"\nReport saved to: {report_path}")

    return report


def _high_volume_unit_economics(tasks: list[dict]) -> dict:
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
    }


def print_report(report: dict) -> None:
    s = report["summary"]
    run = report["benchmark_run"]
    rh = RH_MODELS.get(run["rh_model"], RH_MODELS["claude-4.6-opus"])

    print("\n" + "=" * 72)
    print("  COST BENCHMARK: BICAMERAL vs MONOLITHIC")
    print("=" * 72)
    print(f"  Scenario:         {run['scenario']}")
    print(f"  Days simulated:   {run['num_days_simulated']}")
    print(f"  Tasks per day:    {run['tasks_per_day']}")
    print(f"  Total tasks:      {run['total_tasks']}")
    print(f"  RH model:         {rh.name} (${rh.input_per_million}/${rh.output_per_million} per M tokens)")
    print(f"  LH model:         {FLASH.name} (${FLASH.input_per_million}/${FLASH.output_per_million} per M tokens)")
    print(f"  Optimizations:    {run['optimizations']}")
    print(f"  Mono baseline:    claude-4.6-opus ($5.00/$25.00 per M tokens)")
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

    eu = report.get("high_volume_unit_economics", {})
    if eu:
        print(f"\n  HIGH-VOLUME UNIT ECONOMICS (per transaction)")
        print(f"  {'Transactions':30s} {eu['total_transactions']:>10d}")
        print(f"  {'Cost/txn (bicameral)':30s} ${eu['cost_per_transaction_bicameral']:>10.6f}")
        print(f"  {'Cost/txn (monolithic)':30s} ${eu['cost_per_transaction_monolithic']:>10.6f}")
        print(f"  {'Savings/txn':30s} ${eu['savings_per_transaction']:>10.6f}")

    print("\n" + "=" * 72 + "\n")


def run_matrix(num_days: int = 1) -> dict:
    """Run all model x optimization combinations and return a comparison matrix."""
    optimization_combos = [
        OptimizationFlags(),
        OptimizationFlags(cache_plans=True),
        OptimizationFlags(compress_prompts=True),
        OptimizationFlags(batch_similar=True),
        OptimizationFlags(skip_low_risk_review=True),
        OptimizationFlags(cache_plans=True, compress_prompts=True, batch_similar=True, skip_low_risk_review=True),
    ]

    matrix: dict[str, dict[str, float]] = {}
    for opt in optimization_combos:
        matrix[opt.label] = {}
        for model_name in RH_MODELS:
            report = run_cost_benchmark(num_days=num_days, rh_model_name=model_name, opts=opt)
            matrix[opt.label][model_name] = report["summary"]["daily_cost_bicameral"]

    mono_report = run_cost_benchmark(num_days=num_days, rh_model_name="claude-4.6-opus", opts=OptimizationFlags())
    mono_daily = mono_report["summary"]["daily_cost_monolithic"]

    return {"matrix": matrix, "monolithic_baseline": mono_daily, "num_days": num_days}


def print_matrix(result: dict) -> None:
    matrix = result["matrix"]
    mono = result["monolithic_baseline"]
    models = list(RH_MODELS.keys())
    short_names = {
        "claude-4.6-opus": "Opus",
        "gpt-5": "GPT-5",
        "gemini-2.5-pro": "Gem Pro",
        "o3": "o3",
        "deepseek-r1": "DeepSeek",
        "claude-haiku-4.5": "Haiku",
    }

    col_w = 10
    label_w = 28
    header = f"  {'':>{label_w}s}"
    for m in models:
        header += f"  {short_names.get(m, m):>{col_w}s}"

    print("\n" + "=" * (label_w + 2 + (col_w + 2) * len(models) + 4))
    print("  MULTI-MODEL x OPTIMIZATION MATRIX (daily cost, bicameral)")
    print("=" * (label_w + 2 + (col_w + 2) * len(models) + 4))
    print(header)
    print(f"  {'':>{label_w}s}" + ("  " + "─" * col_w) * len(models))

    for opt_label, model_costs in matrix.items():
        row = f"  {opt_label:>{label_w}s}"
        for m in models:
            cost = model_costs.get(m, 0)
            row += f"  ${cost:>{col_w - 1}.2f}"
        print(row)

    print(f"  {'─' * (label_w + (col_w + 2) * len(models) + 2)}")
    row = f"  {'Monolithic Opus baseline':>{label_w}s}"
    row += f"  ${mono:>{col_w - 1}.2f}"
    for _ in models[1:]:
        row += f"  {'--':>{col_w}s}"
    print(row)

    best_label = ""
    best_model = ""
    best_cost = float("inf")
    for opt_label, model_costs in matrix.items():
        for m, c in model_costs.items():
            if c < best_cost:
                best_cost = c
                best_model = m
                best_label = opt_label

    print(f"\n  Best combo: {short_names.get(best_model, best_model)} with {best_label} "
          f"= ${best_cost:.2f}/day (vs ${mono:.2f} monolithic)")
    savings = (1 - best_cost / mono) * 100 if mono > 0 else 0
    print(f"  Savings: {savings:.1f}% vs monolithic Opus baseline")
    print("=" * (label_w + 2 + (col_w + 2) * len(models) + 4) + "\n")

    return


def main() -> None:
    parser = argparse.ArgumentParser(description="Role-based cost benchmark: bicameral vs monolithic")
    parser.add_argument("--days", type=int, default=1, help="Number of days to simulate (default: 1)")
    parser.add_argument("--output-dir", type=str, default=None, help="Directory to save JSON report")
    parser.add_argument("--rh-model", type=str, default="claude-4.6-opus",
                        choices=list(RH_MODELS.keys()),
                        help="RH planner model to use (default: claude-4.6-opus)")
    parser.add_argument("--cache-plans", action="store_true", help="Enable plan caching optimization")
    parser.add_argument("--compress-prompts", action="store_true", help="Enable prompt compression (60%% reduction)")
    parser.add_argument("--batch-similar", action="store_true", help="Enable batch amortization of plans")
    parser.add_argument("--skip-low-risk-review", action="store_true", help="Skip review for employee tasks")
    parser.add_argument("--all-optimizations", action="store_true", help="Enable all four optimizations")
    parser.add_argument("--matrix", action="store_true", help="Run full model x optimization comparison matrix")
    args = parser.parse_args()

    if args.matrix:
        result = run_matrix(num_days=args.days)
        print_matrix(result)
        if args.output_dir:
            out = Path(args.output_dir)
            out.mkdir(parents=True, exist_ok=True)
            path = out / f"matrix_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
            path.write_text(json.dumps(result, indent=2, default=str))
            print(f"Matrix saved to: {path}")
        return

    opts = OptimizationFlags(
        cache_plans=args.all_optimizations or args.cache_plans,
        compress_prompts=args.all_optimizations or args.compress_prompts,
        batch_similar=args.all_optimizations or args.batch_similar,
        skip_low_risk_review=args.all_optimizations or args.skip_low_risk_review,
    )

    output_dir = Path(args.output_dir) if args.output_dir else None
    report = run_cost_benchmark(num_days=args.days, rh_model_name=args.rh_model, opts=opts, output_dir=output_dir)
    print_report(report)


if __name__ == "__main__":
    main()
