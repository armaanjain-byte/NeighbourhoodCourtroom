"""Tests for engine/state.py — State Engine.

Covers:
    - Proposal creation with defaults and custom values
    - Version increment on every mutation
    - Lock enforcement (locked fields silently skipped)
    - Audit history generation (change_log entries)
    - Human override behavior (locks + value set)
    - Cloning preserves version and id
    - Change summary diff computation
"""

import pytest
from models.proposal import Proposal
from engine.state import (
    MUTABLE_PARAMETERS,
    create_initial_proposal,
    clone_proposal,
    apply_changes,
    apply_human_override,
    calculate_change_summary,
)


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
        estimated_cost=10_000_000.0,
    )


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
        assert updated.parking_spaces == 200.0
        # Two changed entries
        changed_entries = [e for e in updated.change_log if e["action"] == "changed"]
        assert len(changed_entries) == 2

    def test_unknown_key_ignored(self, base_proposal: Proposal) -> None:
        updated = apply_changes(base_proposal, {"nonexistent_field": 99.0}, "climate")
        # Version still increments but no substantive change logged
        changed_entries = [e for e in updated.change_log if e["action"] == "changed"]
        assert len(changed_entries) == 0

    def test_noop_change_skipped(self, base_proposal: Proposal) -> None:
        updated = apply_changes(base_proposal, {"green_space_pct": 20.0}, "climate")
        changed_entries = [e for e in updated.change_log if e["action"] == "changed"]
        assert len(changed_entries) == 0

    def test_locked_field_skipped(self, base_proposal: Proposal) -> None:
        locked = apply_human_override(base_proposal, "green_space_pct", 30.0)
        updated = apply_changes(locked, {"green_space_pct": 10.0}, "finance")
        # Value should stay at locked value
        assert updated.green_space_pct == 30.0
        # Should have a skipped_locked entry
        skipped = [e for e in updated.change_log if e["action"] == "skipped_locked"]
        assert len(skipped) == 1
        assert skipped[0]["requested_value"] == 10.0
        assert skipped[0]["locked_value"] == 30.0


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
