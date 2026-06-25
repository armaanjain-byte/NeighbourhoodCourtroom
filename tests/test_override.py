"""Tests for Override Engine.

Purpose:
    Validate the behavior of human override application and change summary calculations.

Dependencies:
    pytest, engine.override, models.proposal.
"""
import pytest
from typing import Any
from models.proposal import Proposal
from engine.override import apply_human_override, calculate_change_summary


def test_override_initialization() -> None:
    """Verify basic initialization and execution of override utilities."""
    base_proposal = Proposal(
        city_slug="phoenix_az",
        green_space_pct=20.0,
        affordable_housing_pct=15.0,
        housing_units=200,
        parking_spaces=300,
        community_center_sqft=5000.0,
        estimated_cost=45000000.0,
    )
    
    # Act: Apply human override
    updated = apply_human_override(base_proposal, "green_space_pct", 35.0)
    
    # Assert
    assert updated.green_space_pct == 35.0
    assert updated.human_locks["green_space_pct"] == 35.0
    
    # Verify change summary calculation
    diff = calculate_change_summary(base_proposal, updated)
    assert "green_space_pct" in diff
    assert diff["green_space_pct"]["before"] == 20.0
    assert diff["green_space_pct"]["after"] == 35.0
