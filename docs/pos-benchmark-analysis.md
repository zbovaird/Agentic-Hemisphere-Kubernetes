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

### LLM API Costs

| Model | Role | Input (per 1M tokens) | Output (per 1M tokens) | Source |
|-------|------|-----------------------|------------------------|--------|
| Claude 4.6 Opus | RH Planner (plan + review) | $15.00 | $75.00 | Anthropic API pricing |
| Gemini 2.5 Flash | LH Executor (implementation) | $0.15 | $0.60 | Google Vertex AI pricing |

The price difference is **100x on input** and **125x on output**. This is the core economic lever of the bicameral architecture.

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
| End-of-day reconciliation report | 3x | 123,943 / 3,259 | 204,693 / 20,315 | 3 | 113,813 / 1,224 |

Shift swaps are simple (1 iteration), while scheduling and reconciliation require multiple passes.

### Employee Tasks (50/day)

| Task | Freq | Avg Plan Tokens (in/out) | Avg Impl Tokens (in/out) | Avg Iterations | Avg Review Tokens (in/out) |
|------|------|--------------------------|--------------------------|----------------|---------------------------|
| Place new dine-in order | 20x | 21,759 / 1,001 | 24,667 / 3,821 | 1 | 26,022 / 413 |
| Modify existing order | 10x | 17,830 / 563 | 19,761 / 2,766 | 1 | 19,091 / 319 |
| Cancel order with reason code | 5x | 11,985 / 401 | 9,322 / 1,448 | 1 | 12,387 / 273 |
| Process split-check payment | 8x | 18,773 / 780 | 24,064 / 3,744 | 1 | 23,006 / 339 |
| Apply discount/coupon | 7x | 12,708 / 506 | 9,460 / 964 | 1 | 13,281 / 250 |

Employee tasks are simple, single-iteration operations. They have the smallest token footprints but the highest volume (50/day = 82% of all tasks).

---

## Cost Breakdown by Component

### Where the money goes

For a single "Place new dine-in order" (employee task), here is the exact cost breakdown:

**Bicameral architecture:**

| Phase | Model | Input Tokens | Output Tokens | Cost |
|-------|-------|-------------|---------------|------|
| Plan | Opus | 21,759 | 1,001 | $0.3264 + $0.0751 = **$0.4015** |
| Implementation | Flash | 24,667 | 3,821 | $0.0037 + $0.0023 = **$0.0060** |
| Review | Opus | 26,022 | 413 | $0.3903 + $0.0310 = **$0.4213** |
| GKE Pod (6.1s) | Infra | -- | -- | **$0.0000** |
| **Total** | | | | **$0.8289** |

**Monolithic architecture (same task, all Opus):**

| Phase | Model | Input Tokens | Output Tokens | Cost |
|-------|-------|-------------|---------------|------|
| All phases | Opus | 72,448 | 5,235 | $1.0867 + $0.3926 = **$1.4794** |
| GKE Pod (6.1s) | Infra | -- | -- | **$0.0000** |
| **Total** | | | | **$1.4795** |

**Savings: $0.65/transaction (44%)**

The savings come from the implementation phase: Flash processes 24,667 input + 3,821 output tokens for $0.006, while Opus would charge $0.66 for the same tokens. The plan and review phases still use Opus because they require reasoning about correctness.

### Cost driver analysis

| Cost Component | Daily Bicameral | Daily Monolithic | % of Total (Bi) |
|----------------|-----------------|------------------|------------------|
| Opus API (plan + review) | ~$74.87 | -- | 99.97% |
| Flash API (implementation) | ~$0.02 | -- | 0.03% |
| Opus API (all phases) | -- | ~$155.19 | -- |
| GKE Autopilot pods | ~$0.006 | ~$0.006 | <0.01% |
| Vertex AI endpoint | $0.00 | $0.00 | 0% |
| **Total** | **$74.90** | **$155.21** | |

**Key insight:** LLM API costs are 99.99% of the total. Infrastructure is essentially free at this scale. The entire daily GKE cost for 61 tasks is less than a penny.

---

## Per-Role Cost Summary

| Role | Tasks/Day | Bicameral/Day | Monolithic/Day | Savings | Avg Cost/Task (Bi) | Avg Cost/Task (Mono) |
|------|-----------|---------------|----------------|---------|--------------------|-----------------------|
| Owner | 3 | $14.07 | $42.18 | 66.6% | $4.69 | $14.06 |
| Manager | 8 | $27.03 | $53.43 | 49.4% | $3.38 | $6.68 |
| Employee | 50 | $33.79 | $59.60 | 43.3% | $0.68 | $1.19 |
| **Total** | **61** | **$74.90** | **$155.21** | **51.7%** | **$1.23** | **$2.54** |

### Why owner tasks save the most (66.6%)

Owner tasks have the highest implementation token counts (up to 577K input tokens for inventory analysis). In the bicameral model, these tokens go through Flash at $0.15/M instead of Opus at $15/M. The more implementation tokens a task has, the greater the savings.

### Why employee tasks still save 43.3%

Even though employee tasks are simple, they still have plan and review phases that must use Opus. The implementation phase is small (10K-25K tokens), so the Flash savings are proportionally smaller. But at 50 tasks/day, the absolute savings add up: **$25.81/day just on employee transactions**.

---

## Monthly and Annual Projections

| Period | Bicameral | Monolithic | Savings |
|--------|-----------|------------|---------|
| Daily | $74.90 | $155.21 | $80.31 (51.7%) |
| Monthly (30 days) | $2,246.89 | $4,656.19 | $2,409.30 |
| Annual (365 days) | $27,337.85 | $56,651.65 | $29,313.80 |

---

## Why These Costs Seem High

If $75/day seems expensive for a POS system, consider:

1. **These are LLM API costs, not traditional software costs.** A conventional POS system has near-zero marginal cost per transaction. An AI-powered POS that uses a reasoning model for every interaction is fundamentally more expensive.

2. **Opus output tokens cost $75 per million.** Even a brief 1,000-token plan output costs $0.075. Multiply by 61 tasks and the plan+review phases alone cost ~$74/day.

3. **Context windows are large.** Modern LLM agents send 20K-160K input tokens per call (system prompt, conversation history, tool schemas, database context). This is realistic for production agent workloads.

4. **The comparison is what matters.** The bicameral architecture doesn't eliminate LLM costs -- it cuts them in half by routing the bulk work through a model that is 100x cheaper. The monolithic alternative costs $155/day for the same functionality.

5. **Scaling strategies exist.** In production, you would:
   - Cache common employee task plans (order placement doesn't need fresh Opus reasoning every time)
   - Use prompt compression to reduce input token counts
   - Batch similar tasks to amortize plan/review costs
   - Skip the review phase for low-risk employee tasks

   These optimizations could reduce the bicameral cost by another 40-60%.

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
# Single day simulation
python scripts/pos_benchmark.py

# 30-day simulation with JSON report
python scripts/pos_benchmark.py --days 30 --output-dir benchmark-results/

# The JSON report contains per-task token counts for independent verification
```

## Methodology Notes

- Token counts are simulated using realistic ranges based on production LLM agent workloads
- Random seed is fixed (42) for reproducibility
- Infrastructure costs use published GKE Autopilot pricing for `us-central1`
- LLM pricing uses published API rates as of March 2026
- No caching, batching, or prompt optimization is applied -- these are worst-case costs
