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


# ═══════════════════════════════════════════════════════════════════════════
#  RESOLUTION TESTS
# ═══════════════════════════════════════════════════════════════════════════

from engine.conflict import (
    resolve_parameter,
    requires_human_review,
    resolve_conflicts,
    generate_resolution_summary,
    AGENT_WEIGHTS,
)
from engine.state import create_initial_proposal

class TestResolveParameter:
    def test_high_severity_returns_none(self) -> None:
        result = resolve_parameter("green_space_pct", {"finance": 10.0, "climate": 50.0}, "high")
        assert result is None

    def test_low_severity_arithmetic_mean(self) -> None:
        # 10, 20, 30 -> mean is 20
        result = resolve_parameter("green_space_pct", {"finance": 10.0, "climate": 20.0, "community": 30.0}, "low")
        assert result == 20.0

    def test_medium_severity_weighted_mean(self) -> None:
        # finance(0.4) * 10 + climate(0.3) * 20 + community(0.3) * 30
        # 4 + 6 + 9 = 19
        # total weight = 1.0
        result = resolve_parameter("green_space_pct", {"finance": 10.0, "climate": 20.0, "community": 30.0}, "medium")
        assert result == 19.0

    def test_medium_severity_partial_agents(self) -> None:
        # finance(0.4) * 10 + climate(0.3) * 20
        # 4 + 6 = 10
        # total weight = 0.7
        result = resolve_parameter("green_space_pct", {"finance": 10.0, "climate": 20.0}, "medium")
        assert result == pytest.approx(10.0 / 0.7)

    def test_medium_severity_unknown_agent_fallback(self) -> None:
        # default weight is 1/3
        result = resolve_parameter("green_space_pct", {"unknown": 10.0, "other": 20.0}, "medium")
        assert result == pytest.approx(15.0)

    def test_low_severity_confidence_weighted(self) -> None:
        # finance: 100 (conf 1.0), climate: 95 (conf 0.2)
        # weighted sum: 100*1.0 + 95*0.2 = 100 + 19 = 119
        # total conf: 1.2
        # result: 119 / 1.2 = 99.1666...
        result = resolve_parameter("green_space_pct", {"finance": 100.0, "climate": 95.0}, "low", agent_confidences={"finance": 1.0, "climate": 0.2})
        assert result == pytest.approx(119.0 / 1.2)

    def test_medium_severity_equal_weight_different_confidence(self) -> None:
        # climate (weight 0.3), community (weight 0.3)
        # climate proposes 100 (conf 1.0), community proposes 80 (conf 0.2)
        # combined weights: climate 0.3*1.0 = 0.3, community 0.3*0.2 = 0.06. total = 0.36
        # weighted sum: 0.3*100 + 0.06*80 = 30 + 4.8 = 34.8
        # result = 34.8 / 0.36 = 96.666... (pulled heavily toward climate's 100)
        result = resolve_parameter(
            "green_space_pct",
            {"climate": 100.0, "community": 80.0},
            "medium",
            agent_confidences={"climate": 1.0, "community": 0.2},
        )
        assert result == pytest.approx(34.8 / 0.36)

    def test_missing_or_default_confidence_matches_flat_mean(self) -> None:
        # Proving backward compatibility with flat mean / fixed weight when confidence is missing/default
        res_default = resolve_parameter("green_space_pct", {"finance": 10.0, "climate": 20.0, "community": 30.0}, "low")
        res_explicit = resolve_parameter("green_space_pct", {"finance": 10.0, "climate": 20.0, "community": 30.0}, "low", agent_confidences={"finance": 1.0, "climate": 1.0, "community": 1.0})
        assert res_default == res_explicit == 20.0

class TestRequiresHumanReview:
    def test_no_high_conflicts(self) -> None:
        c1 = Conflict(parameter="green_space_pct", agent_a="a", agent_b="b", proposed_value_a=1, proposed_value_b=2, disagreement_severity="low")
        c2 = Conflict(parameter="parking_spaces", agent_a="a", agent_b="b", proposed_value_a=1, proposed_value_b=2, disagreement_severity="medium")
        assert requires_human_review([c1, c2]) == []

    def test_with_high_conflicts(self) -> None:
        c1 = Conflict(parameter="green_space_pct", agent_a="a", agent_b="b", proposed_value_a=1, proposed_value_b=2, disagreement_severity="high")
        c2 = Conflict(parameter="parking_spaces", agent_a="a", agent_b="b", proposed_value_a=1, proposed_value_b=2, disagreement_severity="medium")
        c3 = Conflict(parameter="housing_units", agent_a="a", agent_b="b", proposed_value_a=1, proposed_value_b=2, disagreement_severity="high")
        assert requires_human_review([c1, c2, c3]) == ["green_space_pct", "housing_units"]


class TestResolveConflicts:
    @pytest.fixture
    def proposal(self):
        return create_initial_proposal("phoenix_az")

    def test_single_proposer_no_conflict(self, proposal):
        outputs = {"finance": _make_output("finance", {"green_space_pct": 25.0})}
        conflicts = detect_conflicts(outputs)
        resolution = resolve_conflicts(proposal, outputs, conflicts)
        
        assert resolution["resolved_changes"] == {"green_space_pct": 25.0}
        assert not resolution["requires_human_review"]
        assert resolution["human_review_params"] == []

    def test_multiple_proposers_agree(self, proposal):
        outputs = {
            "finance": _make_output("finance", {"green_space_pct": 25.0}),
            "climate": _make_output("climate", {"green_space_pct": 25.0})
        }
        conflicts = detect_conflicts(outputs)
        resolution = resolve_conflicts(proposal, outputs, conflicts)
        
        assert resolution["resolved_changes"] == {"green_space_pct": 25.0}
        assert not resolution["requires_human_review"]

    def test_low_conflict_resolution(self, proposal):
        outputs = {
            "finance": _make_output("finance", {"green_space_pct": 100.0}),
            "climate": _make_output("climate", {"green_space_pct": 95.0}) # 5% delta -> low
        }
        conflicts = detect_conflicts(outputs)
        resolution = resolve_conflicts(proposal, outputs, conflicts)
        
        assert resolution["resolved_changes"] == {"green_space_pct": 97.5}

    def test_medium_conflict_resolution(self, proposal):
        outputs = {
            "finance": _make_output("finance", {"green_space_pct": 100.0}),
            "climate": _make_output("climate", {"green_space_pct": 80.0}) # 20% delta -> medium
        }
        conflicts = detect_conflicts(outputs)
        resolution = resolve_conflicts(proposal, outputs, conflicts)
        
        # Finance 0.4 * 100 = 40. Climate 0.3 * 80 = 24. sum = 64. total weight = 0.7. 64/0.7 = 91.428...
        assert resolution["resolved_changes"]["green_space_pct"] == pytest.approx(64.0 / 0.7)

    def test_high_conflict_escalation(self, proposal):
        outputs = {
            "finance": _make_output("finance", {"green_space_pct": 100.0}),
            "climate": _make_output("climate", {"green_space_pct": 50.0}) # 50% delta -> high
        }
        conflicts = detect_conflicts(outputs)
        resolution = resolve_conflicts(proposal, outputs, conflicts)
        
        assert resolution["resolved_changes"] == {}
        assert resolution["requires_human_review"] is True
        assert resolution["human_review_params"] == ["green_space_pct"]

    def test_human_locked_parameter(self, proposal):
        from engine.override import apply_human_override
        locked_proposal = apply_human_override(proposal, "green_space_pct", 30.0)
        
        outputs = {
            "finance": _make_output("finance", {"green_space_pct": 100.0, "parking_spaces": 200.0}),
        }
        conflicts = detect_conflicts(outputs)
        resolution = resolve_conflicts(locked_proposal, outputs, conflicts)
        
        # green_space_pct is skipped, parking_spaces goes through
        assert resolution["resolved_changes"] == {"parking_spaces": 200.0}
        assert resolution["skipped_locked"] == ["green_space_pct"]

    def test_multiple_simultaneous_conflicts(self, proposal):
        outputs = {
            "finance": _make_output("finance", {
                "green_space_pct": 100.0, # vs 95 -> low
                "affordable_housing_pct": 100.0, # vs 80 -> medium
                "parking_spaces": 100.0, # vs 50 -> high
                "housing_units": 500.0, # unopposed
            }),
            "climate": _make_output("climate", {
                "green_space_pct": 95.0,
                "affordable_housing_pct": 80.0,
                "parking_spaces": 50.0,
            })
        }
        conflicts = detect_conflicts(outputs)
        resolution = resolve_conflicts(proposal, outputs, conflicts)
        
        # Unooposed: housing_units = 500
        # Low: green_space_pct = 97.5
        # Medium: affordable_housing_pct = 64/0.7
        assert "housing_units" in resolution["resolved_changes"]
        assert resolution["resolved_changes"]["housing_units"] == 500.0
        
        assert "green_space_pct" in resolution["resolved_changes"]
        assert resolution["resolved_changes"]["green_space_pct"] == 97.5
        
        assert "affordable_housing_pct" in resolution["resolved_changes"]
        assert resolution["resolved_changes"]["affordable_housing_pct"] == pytest.approx(64.0 / 0.7)
        
        assert "parking_spaces" not in resolution["resolved_changes"]
        assert resolution["human_review_params"] == ["parking_spaces"]

    def test_resolve_conflicts_with_explicit_confidence(self, proposal):
        # Climate and Community have equal domain weight (0.3).
        out_climate = _make_output("climate", {"green_space_pct": 100.0})
        out_climate.confidence = 1.0
        out_community = _make_output("community", {"green_space_pct": 80.0}) # 20% delta -> medium
        out_community.confidence = 0.2
        
        outputs = {"climate": out_climate, "community": out_community}
        conflicts = detect_conflicts(outputs)
        resolution = resolve_conflicts(proposal, outputs, conflicts)
        
        # 34.8 / 0.36
        assert resolution["resolved_changes"]["green_space_pct"] == pytest.approx(34.8 / 0.36)



class TestGenerateResolutionSummary:
    def test_empty_resolution(self) -> None:
        res = {
            "resolved_changes": {},
            "requires_human_review": False,
            "human_review_params": [],
            "skipped_locked": []
        }
        assert generate_resolution_summary(res) == "No changes proposed by any agent."
        
    def test_full_resolution(self) -> None:
        res = {
            "resolved_changes": {"green_space_pct": 25.0},
            "requires_human_review": True,
            "human_review_params": ["parking_spaces"],
            "skipped_locked": ["housing_units"]
        }
        summary = generate_resolution_summary(res)
        assert "1 parameter(s) auto-resolved:" in summary
        assert "green_space_pct → 25.0" in summary
        assert "1 parameter(s) require human review:" in summary
        assert "- parking_spaces" in summary
        assert "1 parameter(s) skipped (human-locked):" in summary
        assert "- housing_units" in summary
