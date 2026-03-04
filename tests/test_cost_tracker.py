"""Unit tests for the cost tracking module."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "docker" / "rh-planner"))

from app.cost.tracker import (
    CostTracker,
    ModelPricing,
    PhaseUsage,
    TaskCostRecord,
    OPUS_PRICING,
    FLASH_PRICING,
)


class TestModelPricing:
    def test_opus_pricing(self) -> None:
        cost = OPUS_PRICING.cost(input_tokens=1_000_000, output_tokens=0)
        assert cost == pytest.approx(OPUS_PRICING.input_per_million, rel=0.01)

    def test_flash_pricing(self) -> None:
        cost = FLASH_PRICING.cost(input_tokens=1_000_000, output_tokens=0)
        assert cost == pytest.approx(FLASH_PRICING.input_per_million, rel=0.01)

    def test_opus_output_pricing(self) -> None:
        cost = OPUS_PRICING.cost(input_tokens=0, output_tokens=1_000_000)
        assert cost == pytest.approx(OPUS_PRICING.output_per_million, rel=0.01)

    def test_flash_output_pricing(self) -> None:
        cost = FLASH_PRICING.cost(input_tokens=0, output_tokens=1_000_000)
        assert cost == pytest.approx(FLASH_PRICING.output_per_million, rel=0.01)

    def test_combined_cost(self) -> None:
        cost = OPUS_PRICING.cost(input_tokens=100_000, output_tokens=2_000)
        expected = (100_000 * OPUS_PRICING.input_per_million / 1_000_000
                    + 2_000 * OPUS_PRICING.output_per_million / 1_000_000)
        assert cost == pytest.approx(expected, rel=0.001)


class TestTaskCostRecord:
    def test_bicameral_cost_calculation(self) -> None:
        record = TaskCostRecord(intent_id="test-001")
        record.phases = [
            PhaseUsage(phase="plan", model="claude-4.6-opus", input_tokens=100_000, output_tokens=2_000),
            PhaseUsage(phase="implementation", model="gemini-2.5-flash", input_tokens=250_000, output_tokens=30_000),
            PhaseUsage(phase="review", model="claude-4.6-opus", input_tokens=110_000, output_tokens=1_000),
        ]
        bicameral = record.bicameral_cost()
        assert bicameral > 0

        plan_cost = OPUS_PRICING.cost(100_000, 2_000)
        impl_cost = FLASH_PRICING.cost(250_000, 30_000)
        review_cost = OPUS_PRICING.cost(110_000, 1_000)
        expected = plan_cost + impl_cost + review_cost
        assert bicameral == pytest.approx(expected, rel=0.01)

    def test_monolithic_cost_higher(self) -> None:
        record = TaskCostRecord(intent_id="test-002")
        record.phases = [
            PhaseUsage(phase="plan", model="claude-4.6-opus", input_tokens=100_000, output_tokens=2_000),
            PhaseUsage(phase="implementation", model="gemini-2.5-flash", input_tokens=250_000, output_tokens=30_000),
            PhaseUsage(phase="review", model="claude-4.6-opus", input_tokens=110_000, output_tokens=1_000),
        ]
        assert record.monolithic_cost() > record.bicameral_cost()

    def test_savings_percentage_positive(self) -> None:
        record = TaskCostRecord(intent_id="test-003")
        record.phases = [
            PhaseUsage(phase="plan", model="claude-4.6-opus", input_tokens=100_000, output_tokens=2_000),
            PhaseUsage(phase="implementation", model="gemini-2.5-flash", input_tokens=200_000, output_tokens=20_000),
            PhaseUsage(phase="review", model="claude-4.6-opus", input_tokens=100_000, output_tokens=1_000),
        ]
        savings = record.savings_percentage()
        assert savings > 0
        assert savings < 100

    def test_to_dict_has_all_fields(self) -> None:
        record = TaskCostRecord(intent_id="test-004")
        record.phases = [
            PhaseUsage(phase="plan", model="claude-4.6-opus", input_tokens=50_000, output_tokens=1_000),
        ]
        d = record.to_dict()
        assert "intent_id" in d
        assert "bicameral_cost" in d
        assert "monolithic_cost" in d
        assert "savings_percentage" in d
        assert "total_latency_ms" in d
        assert len(d["phases"]) == 1

    def test_empty_record_zero_cost(self) -> None:
        record = TaskCostRecord(intent_id="test-005")
        assert record.bicameral_cost() == 0.0
        assert record.monolithic_cost() == 0.0


class TestCostTracker:
    def test_record_phase(self) -> None:
        tracker = CostTracker()
        tracker.record_phase("t-001", "plan", "claude-4.6-opus", 100_000, 2_000, 500.0)
        record = tracker.get_record("t-001")
        assert record is not None
        assert len(record.phases) == 1
        assert record.phases[0].input_tokens == 100_000

    def test_multiple_phases(self) -> None:
        tracker = CostTracker()
        tracker.record_phase("t-001", "plan", "claude-4.6-opus", 100_000, 2_000)
        tracker.record_phase("t-001", "implementation", "gemini-2.5-flash", 200_000, 20_000)
        tracker.record_phase("t-001", "review", "claude-4.6-opus", 100_000, 1_000)
        record = tracker.get_record("t-001")
        assert record is not None
        assert len(record.phases) == 3

    def test_generate_report(self) -> None:
        tracker = CostTracker()
        tracker.record_phase("t-001", "plan", "claude-4.6-opus", 100_000, 2_000, 3000.0)
        tracker.record_phase("t-001", "implementation", "gemini-2.5-flash", 200_000, 20_000, 5000.0)
        tracker.record_phase("t-001", "review", "claude-4.6-opus", 100_000, 1_000, 2000.0)

        report = tracker.generate_report()
        assert report["task_count"] == 1
        assert report["cost_comparison"]["savings_percentage"] > 0
        assert report["cost_comparison"]["bicameral_total"] < report["cost_comparison"]["monolithic_total"]
        assert report["latency"]["avg_ms"] == pytest.approx(10000.0, rel=0.01)

    def test_report_with_multiple_tasks(self) -> None:
        tracker = CostTracker()
        for i in range(5):
            tracker.record_phase(f"t-{i}", "plan", "claude-4.6-opus", 100_000, 2_000)
            tracker.record_phase(f"t-{i}", "implementation", "gemini-2.5-flash", 200_000, 20_000)
        report = tracker.generate_report()
        assert report["task_count"] == 5

    def test_phase_timer_context_manager(self) -> None:
        tracker = CostTracker()
        with tracker.start_phase("t-001", "plan", "claude-4.6-opus") as timer:
            timer.input_tokens = 50_000
            timer.output_tokens = 1_000
        record = tracker.get_record("t-001")
        assert record is not None
        assert record.phases[0].input_tokens == 50_000
        assert record.phases[0].latency_ms > 0

    def test_set_infra_cost(self) -> None:
        tracker = CostTracker()
        tracker.record_phase("t-001", "plan", "claude-4.6-opus", 100_000, 2_000)
        tracker.set_infra_cost("t-001", gke_pod_seconds=3600, vertex_prediction_cost=0.05)
        record = tracker.get_record("t-001")
        assert record is not None
        assert record.gke_pod_seconds == 3600
        assert record.vertex_prediction_cost == 0.05
        assert record.bicameral_cost() > OPUS_PRICING.cost(100_000, 2_000)

    def test_report_saves_to_file(self, tmp_path: Path) -> None:
        tracker = CostTracker(output_dir=tmp_path)
        tracker.record_phase("t-001", "plan", "claude-4.6-opus", 100_000, 2_000)
        tracker.generate_report()
        json_files = list(tmp_path.glob("cost_report_*.json"))
        assert len(json_files) == 1
