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
    "estimated_cost",
}

# Parameters whose Proposal field type is int (agents send floats)
_INT_PARAMETERS: set[str] = {"housing_units", "parking_spaces"}


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
    estimated_cost: float = 25_000_000.0,
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
    estimated_cost : float
        Total estimated project cost in USD.

    Returns
    -------
    Proposal
        A version-1 Proposal with empty scores, locks, and change log.
    """
    return Proposal(
        city_slug=city_slug,
        version=1,
        green_space_pct=green_space_pct,
        affordable_housing_pct=affordable_housing_pct,
        housing_units=housing_units,
        parking_spaces=parking_spaces,
        community_center_sqft=community_center_sqft,
        estimated_cost=estimated_cost,
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
    updated = proposal.model_copy(deep=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    has_activity = False  # Track whether anything meaningful happened

    # 1. Filter out estimated_cost modifications by agents
    if "estimated_cost" in changes:
        logger.warning(
            f"Agent '{actor}' attempted to modify estimated_cost directly. "
            "estimated_cost is a derived field and was ignored."
        )
        changes = {k: v for k, v in changes.items() if k != "estimated_cost"}

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

    # 2. Recalculate estimated cost using CostCalculator
    if cost_calculator is not None:
        new_cost = cost_calculator.calculate_estimated_cost(updated)
        old_cost = updated.estimated_cost
        if old_cost != new_cost:
            has_activity = True
            updated.estimated_cost = new_cost
            updated.change_log.append({
                "version": proposal.version + 1,
                "actor": "cost_calculator",
                "action": "recalculated",
                "parameter": "estimated_cost",
                "old": old_cost,
                "new": new_cost,
                "timestamp": timestamp,
            })

    if has_activity:
        updated.version = proposal.version + 1

    return updated


def apply_human_override(
    proposal: Proposal,
    parameter: str,
    locked_value: float,
) -> Proposal:
    """Lock a parameter to a specific value via human override.

    Sets both the parameter's current value and adds a lock so agents
    cannot modify it in future rounds.

    Parameters
    ----------
    proposal : Proposal
        The current proposal state.
    parameter : str
        The core parameter to lock (must be in ``MUTABLE_PARAMETERS``).
    locked_value : float
        The value to lock the parameter at.

    Returns
    -------
    Proposal
        A new Proposal with the lock applied and version incremented.

    Raises
    ------
    ValueError
        If *parameter* is not a recognized mutable parameter.
    """
    if parameter not in MUTABLE_PARAMETERS:
        raise ValueError(
            f"Cannot lock unknown parameter '{parameter}'. "
            f"Valid parameters: {sorted(MUTABLE_PARAMETERS)}"
        )

    updated = proposal.model_copy(deep=True)
    updated.version = proposal.version + 1
    timestamp = datetime.now(timezone.utc).isoformat()

    old_value = getattr(proposal, parameter)
    coerced = _coerce_value(parameter, locked_value)
    setattr(updated, parameter, coerced)
    locked_value = coerced  # Use coerced value in lock and log
    updated.human_locks[parameter] = locked_value

    updated.change_log.append({
        "version": updated.version,
        "actor": "human",
        "action": "locked",
        "parameter": parameter,
        "old": old_value,
        "new": locked_value,
        "timestamp": timestamp,
    })

    return updated


def calculate_change_summary(
    before: Proposal,
    after: Proposal,
) -> dict[str, dict[str, Any]]:
    """Compute a structured diff of the core parameters between two proposals.

    Parameters
    ----------
    before : Proposal
        The earlier proposal state.
    after : Proposal
        The later proposal state.

    Returns
    -------
    dict[str, dict[str, Any]]
        Mapping of parameter → ``{"before": old_val, "after": new_val}``
        for every core parameter that changed.  Empty dict if identical.
    """
    diff: dict[str, dict[str, Any]] = {}
    for param in MUTABLE_PARAMETERS:
        old = getattr(before, param)
        new = getattr(after, param)
        if old != new:
            diff[param] = {"before": old, "after": new}
    return diff
