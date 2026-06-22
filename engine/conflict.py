"""Conflict Engine — Deterministic disagreement detection between agents.

Purpose:
    Compares the ``proposed_changes`` dictionaries from multiple AgentOutputs
    and flags parameters where two agents want materially different values.

Dependencies:
    models.agent_output.AgentOutput, models.conflict.Conflict

Design:
    Severity is calculated from the absolute difference between two proposed
    values expressed as a percentage of the larger absolute value:

        LOW    — difference < 10 %
        MEDIUM — difference 10–25 %
        HIGH   — difference > 25 %

    Fully deterministic.  No LLM calls.  No network access.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

from models.agent_output import AgentOutput
from models.conflict import Conflict


def calculate_conflict_severity(value_a: float, value_b: float) -> str:
    """Return ``"low"``, ``"medium"``, or ``"high"`` based on relative delta.

    The percentage difference is computed as::

        delta_pct = |a - b| / max(|a|, |b|) * 100

    When both values are zero the result is ``"low"`` (no disagreement).

    Parameters
    ----------
    value_a, value_b : float
        The two proposed values to compare.

    Returns
    -------
    str
        One of ``"low"``, ``"medium"``, ``"high"``.
    """
    abs_a = abs(value_a)
    abs_b = abs(value_b)
    max_abs = max(abs_a, abs_b)

    if max_abs == 0.0:
        return "low"

    delta_pct = abs(value_a - value_b) / max_abs * 100

    if delta_pct < 10:
        return "low"
    elif delta_pct <= 25:
        return "medium"
    else:
        return "high"


def detect_conflicts(
    agent_outputs: dict[str, AgentOutput],
) -> list[Conflict]:
    """Compare all agent pairs and flag parameters with disagreements.

    For every parameter that two or more agents both propose a change to,
    a ``Conflict`` object is created if their proposed values differ.

    Parameters
    ----------
    agent_outputs : dict[str, AgentOutput]
        Mapping of agent name → AgentOutput (e.g. ``{"finance": ..., "climate": ...}``).

    Returns
    -------
    list[Conflict]
        All detected conflicts, sorted by parameter name then agent pair.
    """
    conflicts: list[Conflict] = []

    # Collect every (parameter → {agent: value}) mapping
    param_proposals: dict[str, dict[str, float]] = {}
    for agent_name, output in agent_outputs.items():
        for param, value in output.proposed_changes.items():
            if param not in param_proposals:
                param_proposals[param] = {}
            param_proposals[param][agent_name] = value

    # For each parameter, compare every pair of agents that proposed a value
    for param in sorted(param_proposals.keys()):
        agents_for_param = param_proposals[param]
        if len(agents_for_param) < 2:
            continue

        for agent_a, agent_b in combinations(sorted(agents_for_param.keys()), 2):
            val_a = agents_for_param[agent_a]
            val_b = agents_for_param[agent_b]

            if val_a == val_b:
                continue

            severity = calculate_conflict_severity(val_a, val_b)
            conflicts.append(
                Conflict(
                    parameter=param,
                    agent_a=agent_a,
                    agent_b=agent_b,
                    proposed_value_a=val_a,
                    proposed_value_b=val_b,
                    disagreement_severity=severity,
                )
            )

    return conflicts


def group_conflicts_by_parameter(
    conflicts: list[Conflict],
) -> dict[str, list[Conflict]]:
    """Group a list of conflicts by their contested parameter.

    Parameters
    ----------
    conflicts : list[Conflict]
        Flat list of conflicts.

    Returns
    -------
    dict[str, list[Conflict]]
        Mapping of parameter name → list of conflicts on that parameter.
    """
    grouped: dict[str, list[Conflict]] = {}
    for c in conflicts:
        if c.parameter not in grouped:
            grouped[c.parameter] = []
        grouped[c.parameter].append(c)
    return grouped


def generate_conflict_summary(conflicts: list[Conflict]) -> str:
    """Produce a human-readable summary string of all conflicts.

    Parameters
    ----------
    conflicts : list[Conflict]
        The conflicts to summarise.

    Returns
    -------
    str
        A multi-line summary.  Returns ``"No conflicts detected."`` when
        the list is empty.
    """
    if not conflicts:
        return "No conflicts detected."

    grouped = group_conflicts_by_parameter(conflicts)
    lines: list[str] = []
    high_count = sum(1 for c in conflicts if c.disagreement_severity == "high")
    medium_count = sum(1 for c in conflicts if c.disagreement_severity == "medium")
    low_count = sum(1 for c in conflicts if c.disagreement_severity == "low")

    lines.append(
        f"{len(conflicts)} conflict(s) detected: "
        f"{high_count} high, {medium_count} medium, {low_count} low."
    )

    for param, param_conflicts in sorted(grouped.items()):
        severities = [c.disagreement_severity for c in param_conflicts]
        worst = "high" if "high" in severities else ("medium" if "medium" in severities else "low")
        agents_involved = sorted(
            {c.agent_a for c in param_conflicts} | {c.agent_b for c in param_conflicts}
        )
        lines.append(
            f"  - {param} ({worst}): contested by {', '.join(agents_involved)}"
        )

    return "\n".join(lines)
