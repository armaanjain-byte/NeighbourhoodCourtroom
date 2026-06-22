"""Debate Engine — Orchestrates a courtroom round.

Purpose:
    Coordinates the deterministic flow of a debate round: taking agent outputs,
    detecting conflicts, resolving them via mathematical rules, and applying
    the results to the Proposal state.

Dependencies:
    models.proposal.Proposal, models.agent_output.AgentOutput,
    models.debate_round.DebateRound, engine.conflict, engine.state

Design:
    Fully deterministic orchestration. No LLM logic.
"""

from __future__ import annotations

from typing import Any

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
from tools.cost_calculator import CostCalculator


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

    # 2 & 3. Detect and resolve conflicts
    conflicts, resolution, summary = process_conflicts(opening_state, agent_outputs)

    # 4 & 5. Apply resolved changes and produce closing state
    closing_state = apply_resolved_changes(
        opening_state, 
        resolution["resolved_changes"],
        cost_calculator=cost_calculator,
    )

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
