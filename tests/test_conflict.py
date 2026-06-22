"""Tests for engine/conflict.py — Conflict Engine.

Covers:
    - No conflicts when agents agree
    - Low severity conflicts (< 10% delta)
    - Medium severity conflicts (10–25% delta)
    - High severity conflicts (> 25% delta)
    - Multiple agents disagreeing on the same parameter
    - Grouping logic
    - Summary generation
    - Edge cases (zero values, identical proposals, single agent)
"""

import pytest
from models.agent_output import AgentOutput
from models.conflict import Conflict
from engine.conflict import (
    calculate_conflict_severity,
    detect_conflicts,
    group_conflicts_by_parameter,
    generate_conflict_summary,
)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _make_output(agent: str, changes: dict[str, float]) -> AgentOutput:
    """Shorthand to create an AgentOutput for testing."""
    return AgentOutput(
        agent_name=agent,
        score=50.0,
        verdict="modify",
        proposed_changes=changes,
        reasoning_and_evidence="test reasoning",
    )


# ── calculate_conflict_severity ────────────────────────────────────────────

class TestCalculateConflictSeverity:
    def test_identical_values(self) -> None:
        assert calculate_conflict_severity(30.0, 30.0) == "low"

    def test_both_zero(self) -> None:
        assert calculate_conflict_severity(0.0, 0.0) == "low"

    def test_low_severity(self) -> None:
        # 5% delta: |100 - 95| / 100 = 5%
        assert calculate_conflict_severity(100.0, 95.0) == "low"

    def test_low_boundary(self) -> None:
        # Exactly at 9.9% → low
        assert calculate_conflict_severity(100.0, 90.1) == "low"

    def test_medium_severity(self) -> None:
        # 20% delta: |100 - 80| / 100 = 20%
        assert calculate_conflict_severity(100.0, 80.0) == "medium"

    def test_medium_boundary_low(self) -> None:
        # Exactly at 10% → medium
        assert calculate_conflict_severity(100.0, 90.0) == "medium"

    def test_medium_boundary_high(self) -> None:
        # Exactly at 25% → medium
        assert calculate_conflict_severity(100.0, 75.0) == "medium"

    def test_high_severity(self) -> None:
        # 50% delta: |100 - 50| / 100 = 50%
        assert calculate_conflict_severity(100.0, 50.0) == "high"

    def test_high_boundary(self) -> None:
        # Just above 25% → high
        assert calculate_conflict_severity(100.0, 74.9) == "high"

    def test_negative_values(self) -> None:
        # |(-10) - (-15)| / max(10, 15) = 5/15 ≈ 33% → high
        assert calculate_conflict_severity(-10.0, -15.0) == "high"

    def test_mixed_sign(self) -> None:
        # |10 - (-10)| / max(10, 10) = 20/10 = 200% → high
        assert calculate_conflict_severity(10.0, -10.0) == "high"


# ── detect_conflicts ───────────────────────────────────────────────────────

class TestDetectConflicts:
    def test_no_conflicts_single_agent(self) -> None:
        outputs = {"finance": _make_output("finance", {"green_space_pct": 10.0})}
        assert detect_conflicts(outputs) == []

    def test_no_conflicts_agents_agree(self) -> None:
        outputs = {
            "finance": _make_output("finance", {"green_space_pct": 30.0}),
            "climate": _make_output("climate", {"green_space_pct": 30.0}),
        }
        assert detect_conflicts(outputs) == []

    def test_no_conflicts_different_params(self) -> None:
        outputs = {
            "finance": _make_output("finance", {"parking_spaces": 200.0}),
            "climate": _make_output("climate", {"green_space_pct": 30.0}),
        }
        assert detect_conflicts(outputs) == []

    def test_high_conflict(self) -> None:
        outputs = {
            "finance": _make_output("finance", {"green_space_pct": 10.0}),
            "climate": _make_output("climate", {"green_space_pct": 40.0}),
        }
        conflicts = detect_conflicts(outputs)
        assert len(conflicts) == 1
        c = conflicts[0]
        assert c.parameter == "green_space_pct"
        assert c.disagreement_severity == "high"
        assert {c.agent_a, c.agent_b} == {"finance", "climate"}

    def test_low_conflict(self) -> None:
        outputs = {
            "finance": _make_output("finance", {"green_space_pct": 30.0}),
            "climate": _make_output("climate", {"green_space_pct": 31.0}),
        }
        conflicts = detect_conflicts(outputs)
        assert len(conflicts) == 1
        assert conflicts[0].disagreement_severity == "low"

    def test_medium_conflict(self) -> None:
        outputs = {
            "finance": _make_output("finance", {"green_space_pct": 100.0}),
            "climate": _make_output("climate", {"green_space_pct": 80.0}),
        }
        conflicts = detect_conflicts(outputs)
        assert len(conflicts) == 1
        assert conflicts[0].disagreement_severity == "medium"

    def test_three_agents_same_param(self) -> None:
        outputs = {
            "finance": _make_output("finance", {"green_space_pct": 10.0}),
            "climate": _make_output("climate", {"green_space_pct": 40.0}),
            "community": _make_output("community", {"green_space_pct": 35.0}),
        }
        conflicts = detect_conflicts(outputs)
        # 3 choose 2 = 3 pairs
        assert len(conflicts) == 3
        params = {c.parameter for c in conflicts}
        assert params == {"green_space_pct"}

    def test_multiple_params_conflicting(self) -> None:
        outputs = {
            "finance": _make_output("finance", {"green_space_pct": 10.0, "parking_spaces": 300.0}),
            "climate": _make_output("climate", {"green_space_pct": 40.0, "parking_spaces": 50.0}),
        }
        conflicts = detect_conflicts(outputs)
        assert len(conflicts) == 2
        params = {c.parameter for c in conflicts}
        assert params == {"green_space_pct", "parking_spaces"}

    def test_empty_outputs(self) -> None:
        assert detect_conflicts({}) == []

    def test_agents_with_no_proposed_changes(self) -> None:
        outputs = {
            "finance": _make_output("finance", {}),
            "climate": _make_output("climate", {}),
        }
        assert detect_conflicts(outputs) == []


# ── group_conflicts_by_parameter ───────────────────────────────────────────

class TestGroupConflicts:
    def test_empty_list(self) -> None:
        assert group_conflicts_by_parameter([]) == {}

    def test_single_conflict(self) -> None:
        c = Conflict(
            parameter="green_space_pct",
            agent_a="finance", agent_b="climate",
            proposed_value_a=10.0, proposed_value_b=40.0,
            disagreement_severity="high",
        )
        grouped = group_conflicts_by_parameter([c])
        assert "green_space_pct" in grouped
        assert len(grouped["green_space_pct"]) == 1

    def test_multiple_params(self) -> None:
        c1 = Conflict(
            parameter="green_space_pct",
            agent_a="finance", agent_b="climate",
            proposed_value_a=10.0, proposed_value_b=40.0,
            disagreement_severity="high",
        )
        c2 = Conflict(
            parameter="parking_spaces",
            agent_a="finance", agent_b="community",
            proposed_value_a=300.0, proposed_value_b=50.0,
            disagreement_severity="high",
        )
        grouped = group_conflicts_by_parameter([c1, c2])
        assert len(grouped) == 2
        assert len(grouped["green_space_pct"]) == 1
        assert len(grouped["parking_spaces"]) == 1


# ── generate_conflict_summary ──────────────────────────────────────────────

class TestGenerateConflictSummary:
    def test_no_conflicts(self) -> None:
        assert generate_conflict_summary([]) == "No conflicts detected."

    def test_single_conflict(self) -> None:
        c = Conflict(
            parameter="green_space_pct",
            agent_a="finance", agent_b="climate",
            proposed_value_a=10.0, proposed_value_b=40.0,
            disagreement_severity="high",
        )
        summary = generate_conflict_summary([c])
        assert "1 conflict(s) detected" in summary
        assert "1 high" in summary
        assert "green_space_pct" in summary
        assert "finance" in summary
        assert "climate" in summary

    def test_mixed_severities(self) -> None:
        c1 = Conflict(
            parameter="green_space_pct",
            agent_a="finance", agent_b="climate",
            proposed_value_a=10.0, proposed_value_b=40.0,
            disagreement_severity="high",
        )
        c2 = Conflict(
            parameter="parking_spaces",
            agent_a="finance", agent_b="community",
            proposed_value_a=100.0, proposed_value_b=95.0,
            disagreement_severity="low",
        )
        summary = generate_conflict_summary([c1, c2])
        assert "2 conflict(s) detected" in summary
        assert "1 high" in summary
        assert "1 low" in summary
