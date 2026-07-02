"""Tests for engine/state.py — State Engine.

Covers:
    - Proposal creation with defaults and custom values
    - Version increment on every mutation (only when substantive)
    - Lock enforcement (locked fields silently skipped)
    - Audit history generation (change_log entries)
    - Human override behavior (locks + value set)
    - Cloning preserves version and id
    - Change summary diff computation
    - Type coercion (float → int for int-typed fields)
    - No-op and empty changes do not bump version
    - MUTABLE_PARAMETERS / _INT_PARAMETERS sync with Proposal model
"""

import pytest
from models.proposal import Proposal
from engine.state import (
    MUTABLE_PARAMETERS,
    _INT_PARAMETERS,
    _coerce_value,
    create_initial_proposal,
    clone_proposal,
    apply_changes,
)
from engine.override import apply_human_override, calculate_change_summary
from tools.cost_calculator import CostCalculator


class MockDataLoader:
    def get_construction_costs(self, city_slug: str) -> dict:
        return {"city_index": 1.0}


class MockCostCalculator(CostCalculator):
    def __init__(self):
        super().__init__(MockDataLoader())
    
    def calculate_estimated_cost(self, proposal: Proposal) -> float:
        # A simple linear formula for testing recalculation
        return (proposal.housing_units * 1000) + (proposal.parking_spaces * 500) + (proposal.green_space_pct * 100)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def base_proposal() -> Proposal:
    """A minimal proposal for test use."""
    return create_initial_proposal("phoenix_az")


@pytest.fixture
def custom_proposal() -> Proposal:
    """A proposal with non-default values."""
    return create_initial_proposal(
        "detroit_mi",
        green_space_pct=10.0,
        affordable_housing_pct=5.0,
        housing_units=50,
        parking_spaces=80,
        community_center_sqft=2000.0,
    )


# ── MUTABLE_PARAMETERS sync guard ──────────────────────────────────────────

class TestMutableParametersSync:
    def test_mutable_params_are_proposal_fields(self) -> None:
        """Every entry in MUTABLE_PARAMETERS must be a real Proposal field."""
        proposal_fields = set(Proposal.model_fields.keys())
        for param in MUTABLE_PARAMETERS:
            assert param in proposal_fields, f"{param} not in Proposal"

    def test_int_params_subset_of_mutable(self) -> None:
        """_INT_PARAMETERS must be a subset of MUTABLE_PARAMETERS."""
        assert _INT_PARAMETERS.issubset(MUTABLE_PARAMETERS)

    def test_int_params_match_model_types(self) -> None:
        """Every param in _INT_PARAMETERS should be typed int on Proposal."""
        for param in _INT_PARAMETERS:
            field_info = Proposal.model_fields[param]
            assert field_info.annotation is int, (
                f"{param} is listed in _INT_PARAMETERS but is "
                f"{field_info.annotation} on Proposal"
            )


# ── _coerce_value ───────────────────────────────────────────────────────────

class TestCoerceValue:
    def test_float_param_passes_through(self) -> None:
        assert _coerce_value("green_space_pct", 25.7) == 25.7
        assert isinstance(_coerce_value("green_space_pct", 25.7), float)

    def test_int_param_coerced(self) -> None:
        result = _coerce_value("housing_units", 200.0)
        assert result == 200
        assert isinstance(result, int)

    def test_int_param_truncates(self) -> None:
        result = _coerce_value("parking_spaces", 150.9)
        assert result == 150
        assert isinstance(result, int)


# ── create_initial_proposal ────────────────────────────────────────────────

class TestCreateInitialProposal:
    def test_default_values(self, base_proposal: Proposal) -> None:
        assert base_proposal.city_slug == "phoenix_az"
        assert base_proposal.version == 1
        assert base_proposal.green_space_pct == 20.0
        assert base_proposal.affordable_housing_pct == 15.0
        assert base_proposal.housing_units == 100
        assert base_proposal.parking_spaces == 150
        assert base_proposal.community_center_sqft == 5000.0
        assert base_proposal.estimated_cost == 25_000_000.0

    def test_custom_values(self, custom_proposal: Proposal) -> None:
        assert custom_proposal.city_slug == "detroit_mi"
        assert custom_proposal.green_space_pct == 10.0
        assert custom_proposal.housing_units == 50

    def test_empty_defaults(self, base_proposal: Proposal) -> None:
        assert base_proposal.agent_scores == {}
        assert base_proposal.human_locks == {}
        assert base_proposal.change_log == []

    def test_generates_proposal_id(self, base_proposal: Proposal) -> None:
        assert isinstance(base_proposal.proposal_id, str)
        assert len(base_proposal.proposal_id) > 0


# ── clone_proposal ──────────────────────────────────────────────────────────

class TestCloneProposal:
    def test_clone_preserves_values(self, base_proposal: Proposal) -> None:
        cloned = clone_proposal(base_proposal)
        assert cloned.city_slug == base_proposal.city_slug
        assert cloned.version == base_proposal.version
        assert cloned.proposal_id == base_proposal.proposal_id
        assert cloned.green_space_pct == base_proposal.green_space_pct

    def test_clone_is_independent(self, base_proposal: Proposal) -> None:
        cloned = clone_proposal(base_proposal)
        cloned.green_space_pct = 99.0
        assert base_proposal.green_space_pct == 20.0  # unchanged


# ── apply_changes ───────────────────────────────────────────────────────────

class TestApplyChanges:
    def test_version_increments(self, base_proposal: Proposal) -> None:
        updated = apply_changes(base_proposal, {"green_space_pct": 30.0}, "climate")
        assert updated.version == base_proposal.version + 1

    def test_original_unchanged(self, base_proposal: Proposal) -> None:
        apply_changes(base_proposal, {"green_space_pct": 30.0}, "climate")
        assert base_proposal.green_space_pct == 20.0  # immutable

    def test_value_updated(self, base_proposal: Proposal) -> None:
        updated = apply_changes(base_proposal, {"green_space_pct": 30.0}, "climate")
        assert updated.green_space_pct == 30.0

    def test_change_log_entry(self, base_proposal: Proposal) -> None:
        updated = apply_changes(base_proposal, {"green_space_pct": 30.0}, "climate")
        assert len(updated.change_log) == 1
        entry = updated.change_log[0]
        assert entry["actor"] == "climate"
        assert entry["action"] == "changed"
        assert entry["parameter"] == "green_space_pct"
        assert entry["old"] == 20.0
        assert entry["new"] == 30.0

    def test_multiple_changes(self, base_proposal: Proposal) -> None:
        changes = {"green_space_pct": 25.0, "parking_spaces": 200.0}
        updated = apply_changes(base_proposal, changes, "finance")
        assert updated.green_space_pct == 25.0
        assert updated.parking_spaces == 200
        # Two changed entries
        changed_entries = [e for e in updated.change_log if e["action"] == "changed"]
        assert len(changed_entries) == 2

    def test_unknown_key_ignored_no_version_bump(self, base_proposal: Proposal) -> None:
        updated = apply_changes(base_proposal, {"nonexistent_field": 99.0}, "climate")
        # No substantive activity → version must NOT increment
        assert updated.version == base_proposal.version
        assert updated.change_log == []

    def test_noop_change_no_version_bump(self, base_proposal: Proposal) -> None:
        updated = apply_changes(base_proposal, {"green_space_pct": 20.0}, "climate")
        # Same value → no activity → version must NOT increment
        assert updated.version == base_proposal.version
        assert updated.change_log == []

    def test_empty_changes_no_version_bump(self, base_proposal: Proposal) -> None:
        updated = apply_changes(base_proposal, {}, "climate")
        assert updated.version == base_proposal.version
        assert updated.change_log == []

    def test_locked_field_skipped(self, base_proposal: Proposal) -> None:
        locked = apply_human_override(base_proposal, "green_space_pct", 30.0)
        updated = apply_changes(locked, {"green_space_pct": 10.0}, "finance")
        # Value should stay at locked value
        assert updated.green_space_pct == 30.0
        # Version DOES increment because lock-skip is activity
        assert updated.version == locked.version + 1
        # Should have a skipped_locked entry
        skipped = [e for e in updated.change_log if e["action"] == "skipped_locked"]
        assert len(skipped) == 1
        assert skipped[0]["requested_value"] == 10.0
        assert skipped[0]["locked_value"] == 30.0

    def test_int_field_coercion(self, base_proposal: Proposal) -> None:
        """Float values for int fields must be coerced to int."""
        updated = apply_changes(base_proposal, {"housing_units": 200.0}, "finance")
        assert updated.housing_units == 200
        assert isinstance(updated.housing_units, int)

    def test_int_field_coercion_parking(self, base_proposal: Proposal) -> None:
        updated = apply_changes(base_proposal, {"parking_spaces": 75.9}, "finance")
        assert updated.parking_spaces == 75
        assert isinstance(updated.parking_spaces, int)

    def test_chained_changes_accumulate_log(self, base_proposal: Proposal) -> None:
        """Applying changes sequentially accumulates change_log entries."""
        v2 = apply_changes(base_proposal, {"green_space_pct": 25.0}, "climate")
        v3 = apply_changes(v2, {"parking_spaces": 100.0}, "finance")
        assert v3.version == 3
        assert len(v3.change_log) == 2

    def test_estimated_cost_modifications_ignored(self, base_proposal: Proposal, caplog: pytest.LogCaptureFixture) -> None:
        """Agents modifying estimated_cost directly should be ignored with a warning."""
        changes = {"estimated_cost": 50_000_000.0, "housing_units": 150}
        updated = apply_changes(base_proposal, changes, "rogue_agent")
        
        # estimated_cost should remain unchanged
        assert updated.estimated_cost == base_proposal.estimated_cost
        assert updated.housing_units == 150
        
        # Warning should be logged
        assert "rogue_agent" in caplog.text
        assert "estimated_cost is a derived field" in caplog.text

    def test_cost_recalculation_on_housing_increase(self, base_proposal: Proposal) -> None:
        calc = MockCostCalculator()
        updated = apply_changes(base_proposal, {"housing_units": 200}, "agent", cost_calculator=calc)
        
        expected_cost = (200 * 1000) + (150 * 500) + (20.0 * 100)
        assert updated.estimated_cost == expected_cost
        
        # Verify recalculation logged
        recalc_log = [e for e in updated.change_log if e["action"] == "recalculated"]
        assert len(recalc_log) == 1
        assert recalc_log[0]["parameter"] == "estimated_cost"

    def test_cost_recalculation_on_parking_increase(self, base_proposal: Proposal) -> None:
        calc = MockCostCalculator()
        updated = apply_changes(base_proposal, {"parking_spaces": 300}, "agent", cost_calculator=calc)
        expected_cost = (100 * 1000) + (300 * 500) + (20.0 * 100)
        assert updated.estimated_cost == expected_cost

    def test_cost_recalculation_on_green_space_increase(self, base_proposal: Proposal) -> None:
        calc = MockCostCalculator()
        updated = apply_changes(base_proposal, {"green_space_pct": 50.0}, "agent", cost_calculator=calc)
        expected_cost = (100 * 1000) + (150 * 500) + (50.0 * 100)
        assert updated.estimated_cost == expected_cost

    def test_out_of_bounds_change_clamps(self, base_proposal: Proposal, caplog: pytest.LogCaptureFixture) -> None:
        """Agent proposing out of bounds value should be clamped rather than crashing."""
        updated = apply_changes(base_proposal, {"housing_units": 500000}, "community")
        
        assert updated.housing_units == 100000
        assert "community" in caplog.text
        assert "clamped to max 100000" in caplog.text
        
        # Verify clamping event in change_log
        clamped_log = [e for e in updated.change_log if e["action"] == "clamped"]
        assert len(clamped_log) == 1
        assert clamped_log[0]["parameter"] == "housing_units"
        assert clamped_log[0]["requested"] == 500000
        assert clamped_log[0]["new"] == 100000



# ── apply_human_override ───────────────────────────────────────────────────

class TestApplyHumanOverride:
    def test_sets_value_and_lock(self, base_proposal: Proposal) -> None:
        overridden = apply_human_override(base_proposal, "green_space_pct", 35.0)
        assert overridden.green_space_pct == 35.0
        assert overridden.human_locks["green_space_pct"] == 35.0

    def test_version_increments(self, base_proposal: Proposal) -> None:
        overridden = apply_human_override(base_proposal, "green_space_pct", 35.0)
        assert overridden.version == base_proposal.version + 1

    def test_audit_log(self, base_proposal: Proposal) -> None:
        overridden = apply_human_override(base_proposal, "green_space_pct", 35.0)
        assert len(overridden.change_log) == 1
        entry = overridden.change_log[0]
        assert entry["actor"] == "human"
        assert entry["action"] == "locked"
        assert entry["parameter"] == "green_space_pct"

    def test_original_unchanged(self, base_proposal: Proposal) -> None:
        apply_human_override(base_proposal, "green_space_pct", 35.0)
        assert base_proposal.green_space_pct == 20.0
        assert "green_space_pct" not in base_proposal.human_locks

    def test_invalid_parameter_raises(self, base_proposal: Proposal) -> None:
        with pytest.raises(ValueError, match="Cannot lock unknown parameter"):
            apply_human_override(base_proposal, "nonexistent_field", 10.0)

    def test_relock_overwrites(self, base_proposal: Proposal) -> None:
        """Re-locking an already-locked parameter should update the lock value."""
        v2 = apply_human_override(base_proposal, "green_space_pct", 30.0)
        v3 = apply_human_override(v2, "green_space_pct", 40.0)
        assert v3.green_space_pct == 40.0
        assert v3.human_locks["green_space_pct"] == 40.0
        assert v3.version == 3

    def test_int_field_coercion(self, base_proposal: Proposal) -> None:
        """Locking an int field with a float should coerce to int."""
        overridden = apply_human_override(base_proposal, "housing_units", 250.0)
        assert overridden.housing_units == 250
        assert isinstance(overridden.housing_units, int)
        assert overridden.human_locks["housing_units"] == 250


# ── calculate_change_summary ──────────────────────────────────────────────

class TestCalculateChangeSummary:
    def test_no_changes(self, base_proposal: Proposal) -> None:
        cloned = clone_proposal(base_proposal)
        diff = calculate_change_summary(base_proposal, cloned)
        assert diff == {}

    def test_single_change(self, base_proposal: Proposal) -> None:
        updated = apply_changes(base_proposal, {"green_space_pct": 30.0}, "climate")
        diff = calculate_change_summary(base_proposal, updated)
        assert "green_space_pct" in diff
        assert diff["green_space_pct"]["before"] == 20.0
        assert diff["green_space_pct"]["after"] == 30.0

    def test_multiple_changes(self, base_proposal: Proposal) -> None:
        updated = apply_changes(
            base_proposal,
            {"green_space_pct": 30.0, "parking_spaces": 50.0},
            "climate",
        )
        diff = calculate_change_summary(base_proposal, updated)
        assert len(diff) == 2
        assert "green_space_pct" in diff
        assert "parking_spaces" in diff
