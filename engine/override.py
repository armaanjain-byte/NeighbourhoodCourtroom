"""Override Engine.

Purpose:
    Handles human overrides on proposals, locking parameters so agents
    cannot modify them in future rounds.
"""

from datetime import datetime, timezone
from typing import Any

from models.proposal import Proposal
from engine.state import MUTABLE_PARAMETERS, _coerce_value


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
    """Compute a structured diff of the core parameters between two proposals."""
    diff: dict[str, dict[str, Any]] = {}
    for param in MUTABLE_PARAMETERS:
        old = getattr(before, param)
        new = getattr(after, param)
        if old != new:
            diff[param] = {"before": old, "after": new}
    return diff
