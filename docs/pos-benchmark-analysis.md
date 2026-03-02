# Restaurant POS Benchmark: Cost Analysis

This document breaks down the cost simulation from `scripts/pos_benchmark.py`, explaining what each number means, where the costs come from, and why the bicameral architecture saves money.

## Scenario

A mid-size restaurant running an AI-powered POS system for one day of lunch and dinner service. Three role tiers interact with the system:

- **Owner** (3 tasks/day): Strategic operations -- financial reports, inventory analysis, labor cost review
- **Manager** (8 tasks/day): Operational management -- shift scheduling, swap handling, end-of-day reconciliation
- **Employee** (50 tasks/day): Transactional operations -- placing orders, modifications, cancellations, payments, discounts

**Total: 61 tasks per day.**

---

## Pricing Inputs

### LLM API Costs (as of March 2026)

| Model | Role | Input (per 1M tokens) | Output (per 1M tokens) | Source |
|-------|------|-----------------------|------------------------|--------|
| Claude 4.6 Opus | RH Planner (plan + review) | $5.00 | $25.00 | Anthropic API pricing |
| Gemini 2.5 Flash | LH Executor (implementation) | $0.15 | $0.60 | Google Vertex AI pricing |

The price difference is **33x on input** and **42x on output**. This is the core economic lever of the bicameral architecture.

> **Note:** Previous versions of this analysis used Opus 4.1 pricing ($15/$75 per M tokens). Anthropic reduced Opus pricing by 67% with the 4.5/4.6 releases, bringing it to $5/$25. All numbers in this document reflect the current pricing.

### Alternative RH Planner Models

| Model | Input/M | Output/M | Notes |
|-------|---------|----------|-------|
| Claude 4.6 Opus | $5.00 | $25.00 | Default; strongest reasoning |
| GPT-5 | $1.25 | $10.00 | Strong general-purpose alternative |
| Gemini 2.5 Pro | $1.25 | $10.00 | Matches GPT-5 pricing, 1M context |
| o3 | $2.00 | $8.00 | OpenAI reasoning model |
| DeepSeek R1 | $0.55 | $2.19 | Lowest cost reasoning model |
| Claude Haiku 4.5 | $1.00 | $5.00 | Fast, cost-efficient Anthropic model |

### GKE Autopilot Infrastructure

| Resource | Rate | Notes |
|----------|------|-------|
| vCPU | $0.0445/vCPU-hour | Pay-per-pod, no idle node cost |
| Memory | $0.0049375/GB-hour | Billed per pod lifetime |
| Pod sizing | 0.25 vCPU, 0.5 GB RAM | Minimal sizing for LH executor pods |

Infrastructure cost per task is negligible ($0.00001-$0.0002) because pods run for seconds, not hours.

### Vertex AI Endpoint

| Item | Cost |
|------|------|
| Endpoint (idle) | $0/hour (no deployed model in test config) |
| Per prediction | Varies by model; not included in simulation |

The Vertex AI endpoint is provisioned but has no model deployed in the test configuration. In production, prediction costs would add to both architectures equally, so they cancel out in the comparison.

---

## Task Inventory

### Owner Tasks (3/day)

| Task | Freq | Avg Plan Tokens (in/out) | Avg Impl Tokens (in/out) | Avg Iterations | Avg Review Tokens (in/out) |
|------|------|--------------------------|--------------------------|----------------|---------------------------|
| Generate daily P&L report | 1x | 161,905 / 3,456 | 282,279 / 44,018 | 5 | 133,278 / 2,518 |
| Analyze inventory trends & reorder | 1x | 115,247 / 4,069 | 577,396 / 90,691 | 8 | 159,453 / 1,054 |
| Review labor cost vs revenue ratio | 1x | 134,898 / 2,896 | 205,942 / 30,362 | 4 | 138,526 / 1,504 |

Owner tasks are the most complex. The inventory analysis requires 8 implementation iterations (scanning stock levels, computing trends, generating reorder recommendations), which produces ~577K input tokens and ~91K output tokens in the implementation phase alone.

### Manager Tasks (8/day)

| Task | Freq | Avg Plan Tokens (in/out) | Avg Impl Tokens (in/out) | Avg Iterations | Avg Review Tokens (in/out) |
|------|------|--------------------------|--------------------------|----------------|---------------------------|
| Build weekly shift schedule | 2x | 104,305 / 2,875 | 164,280 / 28,178 | 4 | 111,157 / 1,185 |
| Handle shift swap request | 3x | 75,426 / 2,105 | 46,234 / 7,213 | 1 | 88,280 / 740 |
| End-of-day reconciliation report | 3x | 123,943 / 3,259 | 204,693 / 20,315 | 4 | 113,813 / 1,224 |

Shift swaps are simple (1 iteration), while scheduling and reconciliation require multiple passes.

### Employee Tasks (50/day)

| Task | Freq | Avg Plan Tokens (in/out) | Avg Impl Tokens (in/out) | Avg Iterations | Avg Review Tokens (in/out) |
|------|------|--------------------------|--------------------------|----------------|---------------------------|
| Place new dine-in order | 20x | 21,759 / 1,001 | 24,667 / 3,821 | 2 | 26,022 / 413 |
| Modify existing order | 10x | 17,830 / 563 | 19,761 / 2,766 | 1 | 19,091 / 319 |
| Cancel order with reason code | 5x | 11,985 / 401 | 9,322 / 1,448 | 1 | 12,387 / 273 |
| Process split-check payment | 8x | 18,773 / 780 | 24,064 / 3,744 | 2 | 23,006 / 339 |
| Apply discount/coupon | 7x | 12,708 / 506 | 9,460 / 964 | 1 | 13,281 / 250 |

Employee tasks are simple, single-iteration operations. They have the smallest token footprints but the highest volume (50/day = 82% of all tasks).

---

## Cost Breakdown by Component

### Where the money goes

For a single "Place new dine-in order" (employee task), here is the exact cost breakdown:

**Bicameral architecture (Opus RH):**

| Phase | Model | Input Tokens | Output Tokens | Cost |
|-------|-------|-------------|---------------|------|
| Plan | Opus | 21,759 | 1,001 | $0.1088 + $0.0250 = **$0.1338** |
| Implementation | Flash | 24,667 | 3,821 | $0.0037 + $0.0023 = **$0.0060** |
| Review | Opus | 26,022 | 413 | $0.1301 + $0.0103 = **$0.1404** |
| GKE Pod (6.1s) | Infra | -- | -- | **$0.0000** |
| **Total** | | | | **$0.2803** |

**Monolithic architecture (same task, all Opus):**

| Phase | Model | Input Tokens | Output Tokens | Cost |
|-------|-------|-------------|---------------|------|
| All phases | Opus | 72,448 | 5,235 | $0.3622 + $0.1309 = **$0.4932** |
| GKE Pod (6.1s) | Infra | -- | -- | **$0.0000** |
| **Total** | | | | **$0.4932** |

**Savings: $0.21/transaction (43%)**

The savings come from the implementation phase: Flash processes 24,667 input + 3,821 output tokens for $0.006, while Opus would charge $0.22 for the same tokens.

### Cost driver analysis

| Cost Component | Daily Bicameral | Daily Monolithic | % of Total (Bi) |
|----------------|-----------------|------------------|------------------|
| Opus API (plan + review) | ~$25.44 | -- | 99.9% |
| Flash API (implementation) | ~$0.02 | -- | 0.1% |
| Opus API (all phases) | -- | ~$51.73 | -- |
| GKE Autopilot pods | ~$0.006 | ~$0.006 | <0.01% |
| Vertex AI endpoint | $0.00 | $0.00 | 0% |
| **Total** | **$25.46** | **$51.74** | |

**Key insight:** LLM API costs are 99.99% of the total. Infrastructure is essentially free at this scale. The entire daily GKE cost for 61 tasks is less than a penny.

---

## Per-Role Cost Summary

| Role | Tasks/Day | Bicameral/Day | Monolithic/Day | Savings | Avg Cost/Task (Bi) | Avg Cost/Task (Mono) |
|------|-----------|---------------|----------------|---------|--------------------|-----------------------|
| Owner | 3 | $4.86 | $14.06 | 65.4% | $1.62 | $4.69 |
| Manager | 8 | $9.18 | $17.81 | 48.5% | $1.15 | $2.23 |
| Employee | 50 | $11.42 | $19.87 | 42.5% | $0.23 | $0.40 |
| **Total** | **61** | **$25.46** | **$51.74** | **50.8%** | **$0.42** | **$0.85** |

### Why owner tasks save the most (65.4%)

Owner tasks have the highest implementation token counts (up to 577K input tokens for inventory analysis). In the bicameral model, these tokens go through Flash at $0.15/M instead of Opus at $5/M. The more implementation tokens a task has, the greater the savings.

### Why employee tasks still save 42.5%

Even though employee tasks are simple, they still have plan and review phases that must use Opus. The implementation phase is small (10K-25K tokens), so the Flash savings are proportionally smaller. But at 50 tasks/day, the absolute savings add up: **$8.44/day just on employee transactions**.

---

## Monthly and Annual Projections

| Period | Bicameral | Monolithic | Savings |
|--------|-----------|------------|---------|
| Daily | $25.46 | $51.74 | $26.27 (50.8%) |
| Monthly (30 days) | $763.87 | $1,552.11 | $788.25 |
| Annual (365 days) | $9,293.03 | $18,884.04 | $9,591.01 |

---

## Multi-Model Comparison

The benchmark supports swapping the RH Planner model. Here is the daily cost for each model with no optimizations applied:

| RH Model | Daily Bicameral | vs Monolithic Opus | Savings |
|----------|-----------------|--------------------|---------| 
| Claude 4.6 Opus | $25.46 | $51.74 | 50.8% |
| GPT-5 | $7.30 | $51.74 | 85.9% |
| Gemini 2.5 Pro | $7.30 | $51.74 | 85.9% |
| o3 | $10.43 | $51.74 | 79.8% |
| DeepSeek R1 | $3.41 | $51.74 | 93.4% |
| Claude Haiku 4.5 | $5.69 | $51.74 | 89.0% |

GPT-5 and Gemini 2.5 Pro offer the best price-to-capability ratio for the RH Planner role at identical pricing ($1.25/$10.00 per M tokens). DeepSeek R1 is the cheapest option at $3.41/day but may sacrifice some reasoning quality on complex owner tasks.

---

## Optimization Strategies

Four optimization strategies can be applied independently or together:

### 1. Plan Caching (`--cache-plans`)

Reuses plans for repeated task types. Employee tasks have an 80% cache hit rate (order placement is repetitive), managers 30%, owners 0% (each task is unique).

| With Opus RH | Daily Cost | Reduction |
|--------------|-----------|-----------|
| No optimization | $25.46 | -- |
| + Plan caching | $21.18 | 16.8% |

### 2. Prompt Compression (`--compress-prompts`)

Reduces input token counts by 60% through context summarization and RAG instead of full history.

| With Opus RH | Daily Cost | Reduction |
|--------------|-----------|-----------|
| No optimization | $25.46 | -- |
| + Compression | $11.85 | 53.5% |

### 3. Batch Amortization (`--batch-similar`)

Groups identical task types and amortizes one plan across the batch. 20 "Place order" tasks share 1 plan.

| With Opus RH | Daily Cost | Reduction |
|--------------|-----------|-----------|
| No optimization | $25.46 | -- |
| + Batching | $17.60 | 30.9% |

### 4. Skip Low-Risk Review (`--skip-low-risk-review`)

Employee tasks skip the Opus review phase entirely. Manager and owner tasks still get reviewed.

| With Opus RH | Daily Cost | Reduction |
|--------------|-----------|-----------|
| No optimization | $25.46 | -- |
| + Skip review | $19.78 | 22.3% |

### All Optimizations Combined

| With Opus RH | Daily Cost | Reduction vs Baseline | vs Monolithic |
|--------------|-----------|----------------------|---------------|
| All optimizations | $5.32 | 79.1% | 89.7% |

With all four optimizations and Opus as the RH Planner, daily cost drops from $25.46 to $5.32 -- a 79% reduction from the unoptimized bicameral cost and 90% savings vs monolithic.

---

## Full Comparison Matrix

Daily bicameral cost by RH model and optimization strategy:

| Strategy | Opus | GPT-5 | Gem Pro | o3 | DeepSeek | Haiku |
|----------|------|-------|---------|-----|----------|-------|
| No optimization | $25.46 | $7.30 | $7.30 | $10.43 | $3.41 | $5.69 |
| + Cache | $21.18 | $6.11 | $6.11 | $8.77 | $2.94 | $4.82 |
| + Compress | $11.85 | $3.69 | $3.69 | $4.82 | $1.66 | $2.74 |
| + Batch | $17.60 | $5.16 | $5.16 | $7.38 | $2.57 | $4.12 |
| + Skip review | $19.78 | $5.81 | $5.81 | $8.19 | $2.79 | $4.55 |
| All optimizations | $5.32 | $1.79 | $1.79 | $2.34 | $0.97 | $1.43 |
| **Monolithic Opus** | **$51.74** | -- | -- | -- | -- | -- |

**Best combination:** DeepSeek R1 with all optimizations = **$0.97/day** (98.1% savings vs monolithic Opus).

**Recommended production setup:** GPT-5 or Gemini 2.5 Pro with all optimizations = **$1.79/day** -- balances strong reasoning capability with 96.5% cost savings vs monolithic Opus.

---

## Infrastructure Cost Detail

For completeness, here is the GKE Autopilot cost breakdown:

| Metric | Value |
|--------|-------|
| Total pod-seconds/day | ~530s across 61 tasks |
| Average pod lifetime | 8.7 seconds |
| vCPU cost (0.25 vCPU x 530s) | $0.0016 |
| Memory cost (0.5 GB x 530s) | $0.0004 |
| **Total daily infra** | **$0.0020** |
| Monthly infra | $0.06 |

GKE Autopilot's pay-per-pod model means you only pay for the seconds each LH executor pod runs. At ~9 seconds per task, infrastructure is effectively free.

---

## How to Run

```bash
# Single day simulation (default: Opus RH, no optimizations)
python scripts/pos_benchmark.py

# 30-day simulation with JSON report
python scripts/pos_benchmark.py --days 30 --output-dir benchmark-results/

# Use a different RH planner model
python scripts/pos_benchmark.py --rh-model gemini-2.5-pro

# Enable individual optimizations
python scripts/pos_benchmark.py --cache-plans
python scripts/pos_benchmark.py --compress-prompts
python scripts/pos_benchmark.py --batch-similar
python scripts/pos_benchmark.py --skip-low-risk-review

# Enable all optimizations
python scripts/pos_benchmark.py --all-optimizations

# Full multi-model x optimization comparison matrix
python scripts/pos_benchmark.py --matrix --output-dir benchmark-results/

# Combine: different model + optimizations + multi-day
python scripts/pos_benchmark.py --rh-model deepseek-r1 --all-optimizations --days 30
```

## Methodology Notes

- Token counts are simulated using realistic ranges based on production LLM agent workloads
- Random seed is fixed (42) for reproducibility
- Infrastructure costs use published GKE Autopilot pricing for `us-central1`
- LLM pricing uses published API rates as of March 2026
- Monolithic baseline always uses Claude 4.6 Opus ($5/$25) for fair comparison
- Cache hit rates: 80% employee, 30% manager, 0% owner
- Prompt compression: 60% input token reduction across all phases
- Batch amortization: plan cost divided by daily frequency of each task type
