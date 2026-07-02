"""Debate Engine — Orchestrates a courtroom round.

Purpose:
    Coordinates the deterministic flow of a debate round: taking agent outputs,
    detecting conflicts, resolving them via mathematical rules, and applying
    the results to the Proposal state.

Dependencies:
    models.proposal.Proposal, models.agent_output.AgentOutput,
    models.debate_round.DebateRound, engine.conflict, engine.state

Design:
    The LLM agents produce the proposed changes via `AgentOutput`, and this module
    deterministically arbitrates the conflicts between them. Supports adaptive round
    flow: early-stop on Round 1 consensus, standard Round 1→2, or Round 1→2→3 only for
    stubborn HIGH conflicts.
"""


from __future__ import annotations

from typing import Any
import logging

from models.proposal import Proposal
from models.agent_output import AgentOutput
from models.debate_round import DebateRound
from models.conflict import Conflict

from engine.state import clone_proposal, apply_changes
from engine.conflict import (
    detect_conflicts,
    resolve_conflicts,
    generate_resolution_summary,
)
from tools.cost_calculator import CostCalculator, check_land_feasibility

logger = logging.getLogger(__name__)
IMMUTABLE_PARAMETERS = {"budget_limit", "estimated_cost", "calculated_construction_cost"}



def strip_immutable_agent_changes(
    agent_outputs: dict[str, AgentOutput],
) -> dict[str, AgentOutput]:
    """Drop frozen/computed fields before conflict resolution."""
    sanitized: dict[str, AgentOutput] = {}
    for agent_name, output in agent_outputs.items():
        immutable_keys = [
            key for key in output.proposed_changes
            if key in IMMUTABLE_PARAMETERS
        ]
        if immutable_keys:
            logger.warning(
                "Agent '%s' proposed immutable parameter(s) %s; stripping before resolution.",
                agent_name,
                immutable_keys,
            )
        filtered_changes = {
            key: value for key, value in output.proposed_changes.items()
            if key not in IMMUTABLE_PARAMETERS
        }
        sanitized[agent_name] = output.model_copy(update={
            "proposed_changes": filtered_changes,
            "verdict": "modify" if filtered_changes else "accept",
        })
    return sanitized


def _resolve_city_data(
    proposal: Proposal,
    cost_calculator: CostCalculator | None,
    city_data: dict[str, Any] | None,
) -> dict[str, Any]:
    if city_data is not None:
        return dict(city_data)
    if cost_calculator is not None:
        try:
            return dict(cost_calculator.data_loader.load_city(proposal.city_slug))
        except Exception:
            return {}
    return {}


def _physical_constraint_conflict(
    parameter: str,
    proposed_value: float,
    reason_agent: str,
) -> Conflict:
    return Conflict(
        parameter=parameter,
        agent_a=reason_agent,
        agent_b="physical_constraints",
        proposed_value_a=proposed_value,
        proposed_value_b=0.0,
        disagreement_severity="high",
    )
def process_conflicts(
    proposal: Proposal,
    agent_outputs: dict[str, AgentOutput],
) -> tuple[list[Conflict], dict[str, Any], str]:
    """Detect and resolve conflicts from agent outputs.

    Parameters
    ----------
    proposal : Proposal
        The current proposal state.
    agent_outputs : dict[str, AgentOutput]
        Mapping of agent name → AgentOutput.

    Returns
    -------
    tuple[list[Conflict], dict[str, Any], str]
        - A list of detected conflicts.
        - The resolution dictionary.
        - A human-readable summary of the resolution.
    """
    conflicts = detect_conflicts(agent_outputs)
    resolution = resolve_conflicts(proposal, agent_outputs, conflicts)
    summary = generate_resolution_summary(resolution)
    return conflicts, resolution, summary


def apply_resolved_changes(
    proposal: Proposal,
    resolved_changes: dict[str, float],
    cost_calculator: CostCalculator | None = None,
) -> Proposal:
    """Apply the auto-resolved changes to the proposal state.

    Parameters
    ----------
    proposal : Proposal
        The current proposal.
    resolved_changes : dict[str, float]
        The auto-resolved parameters from the conflict engine.
    cost_calculator : CostCalculator | None
        The engine responsible for recalculating the total estimated cost.

    Returns
    -------
    Proposal
        The updated proposal state (or same state if no changes).
    """
    if not resolved_changes and cost_calculator is None:
        return clone_proposal(proposal)

    # Actor is "engine" since this is the combined resolution of multiple agents
    # or uncontested single-agent proposals.
    return apply_changes(proposal, resolved_changes, "engine", cost_calculator)


def build_debate_round(
    round_number: int,
    opening_state: Proposal,
    agent_outputs: dict[str, AgentOutput],
    detected_conflicts: list[Conflict],
    closing_state: Proposal,
    engine_summary: str,
) -> DebateRound:
    """Construct the DebateRound object representing this orchestration cycle.

    Parameters
    ----------
    round_number : int
        The sequence number of this round.
    opening_state : Proposal
        The state before changes were applied.
    agent_outputs : dict[str, AgentOutput]
        The outputs provided by the agents.
    detected_conflicts : list[Conflict]
        The conflicts detected between agents.
    closing_state : Proposal
        The state after auto-resolved changes were applied.
    engine_summary : str
        Human-readable summary of the resolution.

    Returns
    -------
    DebateRound
        The constructed DebateRound instance.
    """
    return DebateRound(
        round_number=round_number,
        opening_state=opening_state,
        agent_outputs=agent_outputs,
        detected_conflicts=detected_conflicts,
        closing_state=closing_state,
        engine_summary=engine_summary,
    )


def run_debate_round(
    proposal: Proposal,
    agent_outputs: dict[str, AgentOutput],
    round_number: int = 1,
    cost_calculator: CostCalculator | None = None,
    city_data: dict[str, Any] | None = None,
    budget_limit: float = 0.0,
) -> tuple[DebateRound, Proposal]:
    """Execute a complete, deterministic debate orchestration cycle.

    Flow:
        1. Capture opening state.
        2. Detect conflicts.
        3. Resolve conflicts.
        4. Apply resolved changes (triggering cost recalculation).
        5. Produce closing state.
        6. Create DebateRound.

    Parameters
    ----------
    proposal : Proposal
        The initial proposal state for the round.
    agent_outputs : dict[str, AgentOutput]
        The list of agent outputs proposing changes.
    round_number : int, optional
        The round number (default 1).
    cost_calculator : CostCalculator | None
        The cost calculator used for deriving estimated costs.
    

    Returns
    -------
    tuple[DebateRound, Proposal]
        The generated debate round record and the updated proposal state.
    """
    # 1. Capture opening state
    opening_state = clone_proposal(proposal)
    agent_outputs = strip_immutable_agent_changes(agent_outputs)

    # 2 & 3. Detect and resolve conflicts
    conflicts, resolution, summary = process_conflicts(opening_state, agent_outputs)



    # 4 & 5. Apply resolved changes and produce closing state
    resolved = resolution["resolved_changes"]

    # ── Budget-integrity post-apply guard ────────────────────────────────────
    # These assertions are the second line of defense (first is in apply_changes).
    # If the conflict engine ever accidentally included a frozen parameter in the
    # resolved dict, we catch it here before it reaches the proposal state.
    assert "budget_limit" not in resolved, (
        "BUG: budget_limit was included in negotiated changes — "
        "this is not a mutable parameter and must never be negotiated."
    )
    assert "estimated_cost" not in resolved, (
        "BUG: estimated_cost is not a negotiable parameter — "
        "remove it from agent proposals before passing to the conflict engine."
    )

    candidate_state = apply_resolved_changes(
        opening_state,
        resolved,
        cost_calculator=cost_calculator,
    )

    resolved_city_data = _resolve_city_data(opening_state, cost_calculator, city_data)
    lot_size_sqft = resolved_city_data.get("lot_sqft")
    closing_state = candidate_state

    if lot_size_sqft and lot_size_sqft > 0:
        land_status = check_land_feasibility(candidate_state, float(lot_size_sqft))
        if not land_status["feasible"]:
            conflicts.append(_physical_constraint_conflict(
                "land_feasibility",
                float(land_status["total_footprint"]),
                "land_rules",
            ))
            summary += (
                f" Land feasibility failed: footprint "
                f"{land_status['total_footprint']:,.0f} sqft exceeds available "
                f"{land_status['available']:,.0f} sqft by "
                f"{land_status['overage_sqft']:,.0f} sqft; changes require human review."
            )
            closing_state = opening_state

    active_budget_limit = budget_limit or opening_state.budget_limit
    if cost_calculator is not None and active_budget_limit > 0:
        budget_status = cost_calculator.check_budget(
            closing_state,
            resolved_city_data,
            active_budget_limit,
        )
        if not budget_status["within_budget"]:
            conflicts.append(_physical_constraint_conflict(
                "calculated_construction_cost",
                float(budget_status["breakdown"].total_estimated_cost),
                "budget_rules",
            ))
            summary += (
                f" Budget ceiling failed: estimated construction cost "
                f"${budget_status['breakdown'].total_estimated_cost:,.0f} exceeds "
                f"the hard budget limit ${active_budget_limit:,.0f} by "
                f"${budget_status['overage']:,.0f}; changes require human review."
            )
            closing_state = opening_state

    # 6. Create DebateRound
    debate_round = build_debate_round(
        round_number=round_number,
        opening_state=opening_state,
        agent_outputs=agent_outputs,
        detected_conflicts=conflicts,
        closing_state=closing_state,
        engine_summary=summary,
    )

    return debate_round, closing_state
