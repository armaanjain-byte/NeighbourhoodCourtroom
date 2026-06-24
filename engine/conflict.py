"""Conflict Engine — Deterministic disagreement detection and resolution.

Purpose:
    Compares the ``proposed_changes`` dictionaries from multiple AgentOutputs,
    flags parameters where agents disagree, and resolves those disagreements
    using deterministic rules.

Dependencies:
    models.agent_output.AgentOutput, models.conflict.Conflict,
    models.proposal.Proposal

Design:
    Severity is calculated from the absolute difference between two proposed
    values expressed as a percentage of the larger absolute value:

        LOW    — difference < 10 %
        MEDIUM — difference 10–25 %
        HIGH   — difference > 25 %

    Resolution rules:
        LOW    → confidence-weighted mean of all proposing agents' values
        MEDIUM → combined weighted mean (domain_weight * confidence per agent)
        HIGH   → requires human review, parameter excluded from auto-resolve

    Fully deterministic.  No LLM calls.  No network access.
"""

from __future__ import annotations

from itertools import combinations
from typing import Any

from models.agent_output import AgentOutput
from models.conflict import Conflict
from models.proposal import Proposal


# ── Agent weights for weighted-mean resolution (MEDIUM severity) ────────────
AGENT_WEIGHTS: dict[str, float] = {
    "finance": 0.4,
    "climate": 0.3,
    "community": 0.3,
}

DEFAULT_AGENT_WEIGHT: float = 1.0 / 3  # fallback for unknown agent names


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


# ═══════════════════════════════════════════════════════════════════════════
#  CONFLICT RESOLUTION LAYER
# ═══════════════════════════════════════════════════════════════════════════


def resolve_parameter(
    param: str,
    agent_values: dict[str, float],
    worst_severity: str,
    agent_confidences: dict[str, float] | None = None,
) -> float | None:
    """Resolve a single contested parameter according to severity rules.

    Parameters
    ----------
    param : str
        The parameter name (for context only; not used in calculation).
    agent_values : dict[str, float]
        Mapping of agent name → proposed value for this parameter.
    worst_severity : str
        The worst conflict severity across all pairs for this parameter.
        One of ``"low"``, ``"medium"``, ``"high"``.
    agent_confidences : dict[str, float] | None
        Mapping of agent name → confidence value (0.0 to 1.0) for this parameter.
        Defaults to 1.0 for missing agents or if None.

    Returns
    -------
    float | None
        The resolved value, or ``None`` if the conflict is HIGH severity
        and requires human review.

    Resolution Rules
    ----------------
    - **low**: confidence-weighted mean of all proposed values (each agent's value weighted by its own confidence, normalized).
    - **medium**: combined weighted mean multiplying domain weight (finance 0.4, climate 0.3, community 0.3) by each agent's confidence, then normalized.
    - **high**: returns ``None`` (requires human review).
    """
    if worst_severity == "high":
        return None

    if agent_confidences is None:
        agent_confidences = {}

    if worst_severity == "low":
        # Rule 3: confidence-weighted mean
        total_conf = 0.0
        weighted_sum = 0.0
        for agent_name, value in agent_values.items():
            conf = agent_confidences.get(agent_name, 1.0)
            weighted_sum += conf * value
            total_conf += conf
        if total_conf == 0.0:
            values = list(agent_values.values())
            return sum(values) / len(values)
        return weighted_sum / total_conf

    # worst_severity == "medium"
    # Rule 4: domain weight combined with agent confidence (domain_weight * confidence)
    total_weight = 0.0
    weighted_sum = 0.0
    for agent_name, value in agent_values.items():
        w = AGENT_WEIGHTS.get(agent_name, DEFAULT_AGENT_WEIGHT)
        conf = agent_confidences.get(agent_name, 1.0)
        combined_w = w * conf
        weighted_sum += combined_w * value
        total_weight += combined_w

    if total_weight == 0.0:
        # Defensive fallback — should not happen with valid agents/confidences
        values = list(agent_values.values())
        return sum(values) / len(values)

    return weighted_sum / total_weight


def requires_human_review(conflicts: list[Conflict]) -> list[str]:
    """Return the list of parameter names that have HIGH severity conflicts.

    Parameters
    ----------
    conflicts : list[Conflict]
        All detected conflicts.

    Returns
    -------
    list[str]
        Sorted list of parameter names requiring human review.
    """
    grouped = group_conflicts_by_parameter(conflicts)
    params_needing_review: list[str] = []
    for param, param_conflicts in grouped.items():
        if any(c.disagreement_severity == "high" for c in param_conflicts):
            params_needing_review.append(param)
    return sorted(params_needing_review)


def resolve_conflicts(
    proposal: Proposal,
    agent_outputs: dict[str, AgentOutput],
    conflicts: list[Conflict],
) -> dict[str, Any]:
    """Produce a resolved set of proposal changes from agent outputs and conflicts.

    This is the deterministic bridge between conflict detection and state
    updates.  It processes every proposed parameter change and applies the
    resolution rules.

    Parameters
    ----------
    proposal : Proposal
        The current proposal state (used to check human locks).
    agent_outputs : dict[str, AgentOutput]
        Mapping of agent name → AgentOutput.
    conflicts : list[Conflict]
        All detected conflicts (output of ``detect_conflicts``).

    Returns
    -------
    dict[str, Any]
        A dict with the following keys:

        - ``"resolved_changes"`` (dict[str, float]): parameter → resolved value.
          Ready to be passed to ``engine.state.apply_changes``.
        - ``"requires_human_review"`` (bool): ``True`` if any HIGH severity
          conflict was encountered.
        - ``"human_review_params"`` (list[str]): parameters that could not
          be auto-resolved.
        - ``"skipped_locked"`` (list[str]): parameters that were skipped
          because they are human-locked.

    Resolution Rules
    ----------------
    1. **Single proposer, no conflict** → accept the value.
    2. **Multiple proposers agree** → accept the shared value.
    3. **LOW conflict** → confidence-weighted mean.
    4. **MEDIUM conflict** → combined weighted mean (domain_weight * confidence).
    5. **HIGH conflict** → do not resolve; flag for human review.
    6. **Human-locked** → always preserve lock value; skip the parameter.
    """
    # ── Collect all proposed values and confidences per parameter ──────────────────────
    param_proposals: dict[str, dict[str, float]] = {}
    param_confidences: dict[str, dict[str, float]] = {}
    for agent_name, output in agent_outputs.items():
        for param, value in output.proposed_changes.items():
            if param not in param_proposals:
                param_proposals[param] = {}
                param_confidences[param] = {}
            param_proposals[param][agent_name] = value
            param_confidences[param][agent_name] = getattr(output, "confidence", 1.0)

    # ── Determine worst severity per parameter from conflicts ─────────
    conflict_grouped = group_conflicts_by_parameter(conflicts)
    param_severity: dict[str, str] = {}
    for param, param_conflicts in conflict_grouped.items():
        severities = [c.disagreement_severity for c in param_conflicts]
        if "high" in severities:
            param_severity[param] = "high"
        elif "medium" in severities:
            param_severity[param] = "medium"
        else:
            param_severity[param] = "low"

    # ── Resolve each parameter ────────────────────────────────────────
    resolved_changes: dict[str, float] = {}
    human_review_params: list[str] = []
    skipped_locked: list[str] = []

    for param in sorted(param_proposals.keys()):
        agent_values = param_proposals[param]

        # Rule 6: human-locked parameters are untouchable
        if param in proposal.human_locks:
            skipped_locked.append(param)
            continue

        worst = param_severity.get(param)

        if worst is None:
            # No conflict for this parameter — Rules 1 & 2
            # All proposers agree (or only one proposer)
            # Take any value (they're all the same, or there's only one)
            resolved_changes[param] = next(iter(agent_values.values()))
        else:
            # Conflicted parameter — Rules 3, 4, 5
            confidences = param_confidences.get(param, {})
            resolved_value = resolve_parameter(param, agent_values, worst, agent_confidences=confidences)
            if resolved_value is None:
                # Rule 5: HIGH → escalate to human
                human_review_params.append(param)
            else:
                resolved_changes[param] = resolved_value

    return {
        "resolved_changes": resolved_changes,
        "requires_human_review": len(human_review_params) > 0,
        "human_review_params": sorted(human_review_params),
        "skipped_locked": sorted(skipped_locked),
    }


def generate_resolution_summary(resolution: dict[str, Any]) -> str:
    """Produce a human-readable summary of a resolution result.

    Parameters
    ----------
    resolution : dict[str, Any]
        The output of ``resolve_conflicts``.

    Returns
    -------
    str
        Multi-line human-readable summary.
    """
    lines: list[str] = []
    resolved = resolution["resolved_changes"]
    human_params = resolution["human_review_params"]
    locked = resolution["skipped_locked"]

    if resolved:
        lines.append(f"{len(resolved)} parameter(s) auto-resolved:")
        for param, value in sorted(resolved.items()):
            lines.append(f"  - {param} → {value}")

    if human_params:
        lines.append(f"{len(human_params)} parameter(s) require human review:")
        for param in human_params:
            lines.append(f"  - {param}")

    if locked:
        lines.append(f"{len(locked)} parameter(s) skipped (human-locked):")
        for param in locked:
            lines.append(f"  - {param}")

    if not lines:
        return "No changes proposed by any agent."

    return "\n".join(lines)

