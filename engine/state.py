"""State Engine — Manages the evolving neighborhood proposal state.

Purpose:
    Deterministic state management for the Proposal lifecycle.
    Creates initial proposals, applies agent changes while respecting
    human locks, maintains full audit history, and tracks versions.

Dependencies:
    models.proposal.Proposal

Design:
    All updates are immutable — every mutation returns a *new* Proposal
    with an incremented version and an appended change_log entry.
    Locked fields are silently skipped (never overwritten).
    No LLM calls.  No network access.  Fully deterministic.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from pydantic import ValidationError
from models.proposal import Proposal
from tools.cost_calculator import CostCalculator

logger = logging.getLogger(__name__)


# ── Core parameters that agents are allowed to propose changes on ───────────
MUTABLE_PARAMETERS: set[str] = {
    "green_space_pct",
    "affordable_housing_pct",
    "housing_units",
    "parking_spaces",
    "community_center_sqft",
}

PARAM_BOUNDS: dict[str, tuple[float, float]] = {
    "green_space_pct": (0.0, 100.0),
    "affordable_housing_pct": (0.0, 100.0),
    "housing_units": (0, 100000),
    "parking_spaces": (0, 100000),
    "community_center_sqft": (0.0, 1000000.0),
    # calculated_construction_cost is derived, not negotiable.
}

# Parameters whose Proposal field type is int (agents send floats)
_INT_PARAMETERS: set[str] = {"housing_units", "parking_spaces"}

PARAM_LABELS: dict[str, str] = {
    "green_space_pct": "Green Space",
    "affordable_housing_pct": "Affordable Housing",
    "housing_units": "Housing Density (Units/Hectare)",
    "parking_spaces": "Parking Coverage (Spaces)",
    "community_center_sqft": "Community Center (sqft)",
}

IMMUTABLE_PARAMETERS: set[str] = {"budget_limit", "estimated_cost", "calculated_construction_cost"}


def _coerce_value(param: str, value: float) -> float | int:
    """Coerce *value* to int when *param* is an integer-typed field."""
    if param in _INT_PARAMETERS:
        return int(value)
    return value


def create_initial_proposal(
    city_slug: str,
    *,
    green_space_pct: float = 20.0,
    affordable_housing_pct: float = 15.0,
    housing_units: int = 100,
    parking_spaces: int = 150,
    community_center_sqft: float = 5000.0,
    budget_limit: float = 0.0,
) -> Proposal:
    """Create a fresh Proposal with sensible defaults.

    Parameters
    ----------
    city_slug : str
        City identifier matching the keys in the data JSON files.
    green_space_pct : float
        Percentage of lot allocated to green space (0–100).
    affordable_housing_pct : float
        Percentage of housing units designated affordable.
    housing_units : int
        Total number of housing units.
    parking_spaces : int
        Total number of parking spaces.
    community_center_sqft : float
        Square-footage of community center area.

    Returns
    -------
    Proposal
        A version-1 Proposal with empty scores, locks, and change log.
    """
    return Proposal(
        city_slug=city_slug,
        version=1,
        budget_limit=budget_limit,
        green_space_pct=green_space_pct,
        affordable_housing_pct=affordable_housing_pct,
        housing_units=housing_units,
        parking_spaces=parking_spaces,
        community_center_sqft=community_center_sqft,
    )


def clone_proposal(proposal: Proposal) -> Proposal:
    """Return a deep copy of *proposal* without incrementing the version.

    Parameters
    ----------
    proposal : Proposal
        The source proposal to clone.

    Returns
    -------
    Proposal
        An independent deep copy sharing the same version and id.
    """
    return proposal.model_copy(deep=True)


def apply_changes(
    proposal: Proposal,
    changes: dict[str, float],
    actor: str,
    cost_calculator: CostCalculator | None = None,
) -> Proposal:
    """Apply a dict of parameter changes, respecting human locks.

    Produces a *new* Proposal with:
    - version incremented by 1 (only when at least one change is applied
      or a lock-skip is recorded)
    - each accepted change appended to the change_log
    - locked fields silently skipped

    Parameters
    ----------
    proposal : Proposal
        The current (immutable) proposal state.
    changes : dict[str, float]
        Mapping of parameter name → new value.  Only keys present in
        ``MUTABLE_PARAMETERS`` are considered; unknown keys are ignored.
    actor : str
        Identifier for who is making the change (e.g. ``"climate"``).

    Returns
    -------
    Proposal
        A new Proposal reflecting the accepted changes.  If no
        recognised changes were supplied, returns a deep copy with the
        same version (no version bump).
    """
    assert "budget_limit" not in changes, (
        "BUG: budget_limit was included in negotiated changes - "
        "budget_limit is not a mutable parameter and must never be negotiated."
    )
    assert "estimated_cost" not in changes, (
        "BUG: estimated_cost is not a negotiable parameter - "
        "remove it from agent proposals before applying changes."
    )

    updated = proposal.model_copy(deep=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    has_activity = False  # Track whether anything meaningful happened
    for param, raw_value in changes.items():
        if param not in MUTABLE_PARAMETERS:
            continue

        new_value = _coerce_value(param, raw_value)

        # Respect human locks — skip silently but record the attempt
        if param in proposal.human_locks:
            has_activity = True
            updated.change_log.append({
                "version": proposal.version + 1,
                "actor": actor,
                "action": "skipped_locked",
                "parameter": param,
                "requested_value": new_value,
                "locked_value": proposal.human_locks[param],
                "timestamp": timestamp,
            })
            continue

        old_value = getattr(proposal, param)

        # Skip no-ops
        if old_value == new_value:
            continue

        has_activity = True
        try:
            setattr(updated, param, new_value)
            updated.change_log.append({
                "version": proposal.version + 1,
                "actor": actor,
                "action": "changed",
                "parameter": param,
                "old": old_value,
                "new": new_value,
                "timestamp": timestamp,
            })
        except ValidationError:
            min_bound, max_bound = PARAM_BOUNDS[param]
            clamped_value = max(min_bound, min(max_bound, new_value))
            clamped_value = _coerce_value(param, clamped_value)
            
            bound_str = f"max {max_bound}" if new_value > max_bound else f"min {min_bound}"
            logger.warning(f"Agent {actor} proposed {param}={new_value}, clamped to {bound_str}")
            
            setattr(updated, param, clamped_value)
            updated.change_log.append({
                "version": proposal.version + 1,
                "actor": actor,
                "action": "clamped",
                "parameter": param,
                "old": old_value,
                "requested": new_value,
                "new": clamped_value,
                "timestamp": timestamp,
            })

    # 3. Handle scoring updates
    if has_activity:
        updated.version = proposal.version + 1

    return updated
