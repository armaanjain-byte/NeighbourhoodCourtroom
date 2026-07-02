"""Deterministic Fallback Opinions — Round-Aware, Cost-Grounded.

Purpose:
    Provides a genuine alternative to the generic ``evaluate()``-based fallback.
    When the LLM is unavailable, this module generates an ``AgentOpinion`` that
    *actually responds* to what the other agents said last round, using real cost
    data from ``CostCalculator``.

    This implements the "summarize previous round" approach from:
        Du et al. (2024) "Improving Factuality and Reasoning in Language Models
        through Multiagent Debate"
    and the ReConcile framework (Chen et al. 2023), where agents receive each
    other's previous positions as explicit context before forming a new response.

Design:
    Round 1 — state the cost/environmental/community reality with specific numbers.
    Round 2+ — directly calculate the dollar/impact delta of each opponent's
               proposal and accept, reject, or counter with a specific number.

    Finance:
        - Round 1: report estimated_cost vs budget_limit, propose specific cuts if over.
        - Round 2+: for each Climate/Community proposal, compute the exact cost delta
          and either absorb it or offset it by cutting parking/housing_units.

    Climate:
        - Round 1: report green_space_pct vs city target, compute parking impervious acres.
        - Round 2+: if Finance proposes cuts to green space, explicitly reject and hold
          the line on the EPA minimum; if Finance is within budget, request an increase.

    Community:
        - Round 1: report affordable_housing_pct vs city target, compute sqft/unit.
        - Round 2+: prioritise affordable housing if Finance says budget is tight;
          only advocate for community center if sqft/unit < 10; support Climate's
          green space request (it improves resident quality of life).

Dependencies:
    models.agent_opinion.AgentOpinion, tools.cost_calculator.CostCalculator
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from models.agent_opinion import AgentOpinion, TargetStatement
from models.proposal import Proposal
from tools.cost_calculator import CostBreakdown, CostCalculator, COST_CONSTANTS

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _cost_summary(bd: CostBreakdown) -> str:
    """One-line cost breakdown string."""
    return (
        f"residential ${bd.residential_cost:,.0f} + "
        f"parking ${bd.parking_cost:,.0f} + "
        f"CC ${bd.community_center_cost:,.0f} + "
        f"green ${bd.green_space_cost:,.0f} + "
        f"soft ${bd.soft_costs:,.0f} = "
        f"${bd.total_estimated_cost:,.0f} total"
    )


def _cost_per_unit(bd: CostBreakdown, housing_units: int) -> float:
    """Derive effective cost-per-unit from the breakdown."""
    if housing_units <= 0:
        return COST_CONSTANTS["residential_cost_per_unit"]["tier_3"]
    return bd.residential_cost / housing_units


def _green_space_cost_delta(
    proposal: Proposal,
    new_gs_pct: float,
    lot_sqft: float,
) -> float:
    """Cost delta for changing green_space_pct to new_gs_pct."""
    delta_pct = (new_gs_pct - proposal.green_space_pct) / 100.0
    return delta_pct * lot_sqft * COST_CONSTANTS["green_space_cost_per_sqft"] * COST_CONSTANTS["soft_cost_multiplier"]


def _affordable_housing_cost_delta(
    proposal: Proposal,
    new_ah_pct: float,
    bd: CostBreakdown,
) -> float:
    """Cost delta for changing affordable_housing_pct to new_ah_pct."""
    housing_units = max(proposal.housing_units, 1)
    cpu = _cost_per_unit(bd, housing_units)
    delta_pct = (new_ah_pct - proposal.affordable_housing_pct) / 100.0
    return delta_pct * housing_units * cpu * COST_CONSTANTS["affordable_housing_premium_pct"] * COST_CONSTANTS["soft_cost_multiplier"]


def _community_center_cost_delta(
    proposal: Proposal,
    new_cc_sqft: float,
) -> float:
    """Cost delta for changing community_center_sqft to new_cc_sqft."""
    delta_sqft = new_cc_sqft - proposal.community_center_sqft
    return delta_sqft * COST_CONSTANTS["community_center_cost_per_sqft"] * COST_CONSTANTS["soft_cost_multiplier"]


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_fallback_opinion(
    agent_type: str,
    round_num: int,
    proposal: Proposal,
    city_data: dict[str, Any],
    budget_limit: float,
    opponent_opinions: dict[str, AgentOpinion] | None,
    cost_calculator: CostCalculator,
    own_previous_opinion: AgentOpinion | None = None,
) -> AgentOpinion:
    """Generate a round-aware, cost-grounded deterministic fallback AgentOpinion.

    This replaces the generic ``evaluate()``-based fallback with one that
    actually responds to what the other agents said last round.

    Parameters
    ----------
    agent_type : str
        One of ``"finance"``, ``"climate"``, ``"community"``.
    round_num : int
        Current debate round (1 = independent, 2+ = rebuttal).
    proposal : Proposal
        The current proposal state.
    city_data : dict[str, Any]
        City master record (population, lot_sqft, name, …).
    budget_limit : float
        Hard budget ceiling (never a mutable parameter).
    opponent_opinions : dict[str, AgentOpinion] | None
        Other agents' opinions from the previous round.
    cost_calculator : CostCalculator
        The single source of truth for cost numbers.
    own_previous_opinion : AgentOpinion | None
        This agent's own opinion from the previous round.

    Returns
    -------
    AgentOpinion
        A structured, round-aware fallback opinion.
    """
    ops = opponent_opinions or {}
    lot_sqft = city_data.get("lot_sqft", 1_000_000)

    # Compute current cost breakdown
    try:
        bd = cost_calculator.calculate_construction_cost(proposal, city_data)
    except Exception as exc:
        logger.warning("Fallback cost calculation failed: %s — using zero breakdown", exc)
        bd = CostBreakdown(
            residential_cost=0, affordable_premium=0, parking_cost=0,
            community_center_cost=0, green_space_cost=0,
            subtotal_hard_costs=0, soft_costs=0, total_estimated_cost=0,
        )

    calculated_cost = bd.total_estimated_cost
    over_budget = budget_limit > 0 and calculated_cost > budget_limit
    overage = max(0.0, calculated_cost - budget_limit)
    margin = max(0.0, budget_limit - calculated_cost) if budget_limit > 0 else 0.0

    if agent_type == "finance":
        return _finance_fallback(
            round_num, proposal, city_data, budget_limit,
            bd, calculated_cost, over_budget, overage, margin,
            lot_sqft, ops, own_previous_opinion
        )
    elif agent_type == "climate":
        return _climate_fallback(
            round_num, proposal, city_data, budget_limit,
            bd, calculated_cost, over_budget, margin,
            lot_sqft, ops, own_previous_opinion
        )
    elif agent_type == "community":
        return _community_fallback(
            round_num, proposal, city_data, budget_limit,
            bd, calculated_cost, over_budget, margin,
            lot_sqft, ops, own_previous_opinion
        )
    else:
        # Unknown agent type — generic fallback
        return AgentOpinion(
            agent=agent_type,
            score=50.0,
            recommendation={},
            tension="No domain-specific data available for this agent type in the fallback.",
            position="Using generic deterministic fallback — LLM unavailable.",
            reasoning="Agent type not recognised by the structured fallback engine.",
            evidence=[],
            objections=[],
            supports=[],
            confidence=0.3,
            is_fallback=True,
        )


# ── Per-agent fallback generators ─────────────────────────────────────────────

def _finance_fallback(
    round_num: int,
    proposal: Proposal,
    city_data: dict,
    budget_limit: float,
    bd: CostBreakdown,
    calculated_cost: float,
    over_budget: bool,
    overage: float,
    margin: float,
    lot_sqft: float,
    ops: dict[str, AgentOpinion],
    own_prev: AgentOpinion | None,
) -> AgentOpinion:
    cpu = _cost_per_unit(bd, proposal.housing_units)

    # ── Round 1: state cost reality ───────────────────────────────────────────
    if round_num == 1:
        if over_budget:
            units_to_cut = max(1, int(overage / (cpu * COST_CONSTANTS["soft_cost_multiplier"])))
            parking_to_cut = max(1, int(overage / (COST_CONSTANTS["parking_cost_per_space"]["structured"] * COST_CONSTANTS["soft_cost_multiplier"])))
            # Prefer cutting housing if it solves the problem; otherwise cut parking
            if units_to_cut <= proposal.housing_units * 0.3:
                proposed_changes = {"housing_units": max(0, proposal.housing_units - units_to_cut)}
                action_desc = f"Recommend reducing housing units by {units_to_cut} (saving ~${units_to_cut * cpu * COST_CONSTANTS['soft_cost_multiplier']:,.0f})."
            else:
                proposed_changes = {"parking_spaces": max(0, proposal.parking_spaces - parking_to_cut)}
                action_desc = f"Recommend reducing parking by {parking_to_cut} spaces (saving ~${parking_to_cut * COST_CONSTANTS['parking_cost_per_space']['structured'] * COST_CONSTANTS['soft_cost_multiplier']:,.0f})."

            summary = (
                f"Current estimated cost is ${calculated_cost:,.0f}, exceeding the "
                f"${budget_limit:,.0f} budget by ${overage:,.0f}. {action_desc}"
            )
            score = max(0.0, 100.0 - (overage / budget_limit) * 100.0) if budget_limit > 0 else 50.0
            stance = "objection"
        else:
            proposed_changes = {}
            summary = (
                f"Estimated cost is ${calculated_cost:,.0f}, within the "
                f"${budget_limit:,.0f} budget with ${margin:,.0f} to spare. "
                f"Finance can support modest improvements to other parameters within the remaining ${margin:,.0f}."
            )
            score = min(100.0, 80.0 + (margin / budget_limit * 20.0)) if budget_limit > 0 else 80.0
            stance = "concession"

        return AgentOpinion(
            agent="finance",
            score=score,
            recommendation=proposed_changes,
            tension=(
                "Other agents may argue that cutting housing units or parking harms the community, "
                "but the budget is a hard ceiling — overspending will kill the project entirely."
            ),
            position=summary,
            reasoning=(
                f"Cost breakdown: {_cost_summary(bd)}. "
                f"NAHB 2024: ~${cpu:,.0f}/unit in this city tier. "
                f"WGI 2024: $30,000/structured parking space."
            ),
            evidence=[
                f"Total estimated cost: ${calculated_cost:,.0f} (NAHB 2024 + RSMeans benchmarks)",
                f"Budget limit: ${budget_limit:,.0f} — hard constraint, not negotiable",
            ],
            objections=[],
            supports=[],
            confidence=0.75,
            is_fallback=True,
        )

    # ── Round 2+: directly respond to opponent proposals ─────────────────────
    climate_op = ops.get("climate")
    community_op = ops.get("community")
    response_parts: list[str] = []
    new_changes: dict[str, float] = {}
    objections = []
    supports = []

    # Respond to Climate's green space proposal
    if climate_op and "green_space_pct" in climate_op.recommendation:
        new_gs = float(climate_op.recommendation["green_space_pct"])
        gs_delta = _green_space_cost_delta(proposal, new_gs, lot_sqft)

        if calculated_cost + gs_delta <= budget_limit:
            response_parts.append(
                f"Climate's green space increase to {new_gs}% would cost ~${gs_delta:,.0f} more. "
                f"This fits within the remaining ${margin:,.0f} budget margin — Finance supports this."
            )
            new_changes["green_space_pct"] = new_gs
            supports.append(TargetStatement(
                target_agent="climate",
                engages_with=f"green_space_pct increase to {new_gs}%",
                reason=f"${gs_delta:,.0f} cost delta is within the ${margin:,.0f} remaining budget margin."
            ))
        else:
            spaces_to_cut = max(1, int(gs_delta / (COST_CONSTANTS["parking_cost_per_space"]["structured"] * COST_CONSTANTS["soft_cost_multiplier"])))
            response_parts.append(
                f"Climate's green space increase to {new_gs}% would cost ${gs_delta:,.0f} more, "
                f"which exceeds remaining capacity. Finance proposes absorbing it by cutting "
                f"{spaces_to_cut} parking spaces (saving ~${spaces_to_cut * COST_CONSTANTS['parking_cost_per_space']['structured'] * COST_CONSTANTS['soft_cost_multiplier']:,.0f})."
            )
            new_changes["green_space_pct"] = new_gs
            new_changes["parking_spaces"] = max(0, proposal.parking_spaces - spaces_to_cut)
            supports.append(TargetStatement(
                target_agent="climate",
                engages_with=f"green_space_pct increase to {new_gs}%",
                reason=f"Accepted with parking offset of {spaces_to_cut} spaces to stay within budget."
            ))

    # Respond to Community's affordable housing proposal
    if community_op and "affordable_housing_pct" in community_op.recommendation:
        new_ah = float(community_op.recommendation["affordable_housing_pct"])
        ah_delta = _affordable_housing_cost_delta(proposal, new_ah, bd)

        if calculated_cost + ah_delta <= budget_limit:
            response_parts.append(
                f"Community's affordable housing increase to {new_ah}% adds "
                f"~${ah_delta:,.0f} in subsidy costs — Finance can absorb this."
            )
            new_changes["affordable_housing_pct"] = new_ah
            supports.append(TargetStatement(
                target_agent="community",
                engages_with=f"affordable_housing_pct increase to {new_ah}%",
                reason=f"${ah_delta:,.0f} subsidy cost is affordable within remaining budget margin."
            ))
        else:
            compromise_ah = min(new_ah, proposal.affordable_housing_pct + 5.0)
            response_parts.append(
                f"Community's affordable housing increase to {new_ah}% would add "
                f"${ah_delta:,.0f} which exceeds remaining budget. "
                f"Finance counter-proposes {compromise_ah}% as a compromise."
            )
            new_changes["affordable_housing_pct"] = compromise_ah
            objections.append(TargetStatement(
                target_agent="community",
                engages_with=f"affordable_housing_pct increase to {new_ah}%",
                reason=f"${ah_delta:,.0f} cost delta exceeds remaining budget; counter-proposing {compromise_ah}%."
            ))

    # Respond to Community's community center proposal
    if community_op and "community_center_sqft" in community_op.recommendation:
        new_cc = float(community_op.recommendation["community_center_sqft"])
        cc_delta = _community_center_cost_delta(proposal, new_cc)
        if calculated_cost + cc_delta <= budget_limit:
            response_parts.append(
                f"Community's community center expansion to {new_cc:,.0f} sqft costs "
                f"~${cc_delta:,.0f} — within budget. Finance supports this."
            )
            new_changes["community_center_sqft"] = new_cc
            supports.append(TargetStatement(
                target_agent="community",
                engages_with=f"community_center_sqft increase to {new_cc:,.0f}",
                reason=f"${cc_delta:,.0f} cost is within the remaining budget margin."
            ))
        else:
            objections.append(TargetStatement(
                target_agent="community",
                engages_with=f"community_center_sqft increase to {new_cc:,.0f}",
                reason=f"${cc_delta:,.0f} cost delta would exceed the hard budget limit."
            ))

    if not response_parts:
        response_parts.append(
            f"No affordable changes proposed by other agents. "
            f"Budget status: ${calculated_cost:,.0f} vs ${budget_limit:,.0f} limit."
        )

    score = max(0.0, 100.0 - (overage / budget_limit * 100.0)) if (over_budget and budget_limit > 0) else min(100.0, 80.0 + (margin / budget_limit * 20.0)) if budget_limit > 0 else 80.0
    concession_rationale = (
        "Accepting some opponent proposals because the cost delta is within the remaining budget margin."
        if new_changes and own_prev and new_changes != own_prev.recommendation
        else None
    )

    return AgentOpinion(
        agent="finance",
        score=score,
        recommendation=new_changes,
        tension="Other agents may feel Finance is too restrictive, but every dollar over budget risks project cancellation.",
        position=" | ".join(response_parts),
        reasoning=f"Round {round_num} cost analysis: {_cost_summary(bd)}.",
        evidence=[
            f"Total estimated cost: ${calculated_cost:,.0f}",
            f"Budget limit: ${budget_limit:,.0f}",
        ],
        objections=objections,
        supports=supports,
        confidence=0.7,
        is_fallback=True,
        concession_rationale=concession_rationale,
        own_previous_position=own_prev.recommendation if own_prev else None,
    )


def _climate_fallback(
    round_num: int,
    proposal: Proposal,
    city_data: dict,
    budget_limit: float,
    bd: CostBreakdown,
    calculated_cost: float,
    over_budget: bool,
    margin: float,
    lot_sqft: float,
    ops: dict[str, AgentOpinion],
    own_prev: AgentOpinion | None,
) -> AgentOpinion:
    city_name = city_data.get("name", proposal.city_slug.replace("_", " ").title())
    # Use defaults — climate data is fetched by the agent's build_system_prompt;
    # the fallback does not have an independent data_loader reference here.
    city_green_target: float = 15.0
    city_avg_temp: float = 80.0
    parking_acres = proposal.parking_spaces * 330 / 43560

    # ── Round 1: state environmental reality ─────────────────────────────────
    if round_num == 1:
        green_deficit = proposal.green_space_pct < city_green_target
        target_gs = min(proposal.green_space_pct + 10.0, city_green_target)
        gs_cost = _green_space_cost_delta(proposal, target_gs, lot_sqft)

        if green_deficit:
            proposed_changes: dict[str, float] = {
                "green_space_pct": target_gs,
                "parking_spaces": max(0, int(proposal.parking_spaces * 0.75)),
            }
            summary = (
                f"Green space is {proposal.green_space_pct}%, well below {city_name}'s "
                f"{city_green_target}% target. Requesting increase to {target_gs}% "
                f"(~${gs_cost:,.0f} cost impact) and parking reduction to reduce "
                f"{parking_acres:.1f} acres of impervious surface."
            )
            score = (proposal.green_space_pct / city_green_target) * 80.0
        else:
            proposed_changes = {}
            summary = (
                f"Green space ({proposal.green_space_pct}%) meets or exceeds "
                f"{city_name}'s {city_green_target}% target. Climate standards are satisfied."
            )
            score = min(100.0, 90.0 + (proposal.green_space_pct - city_green_target) * 2.0)

        return AgentOpinion(
            agent="climate",
            score=score,
            recommendation=proposed_changes,
            tension=(
                "Finance may argue that green space increases cost money, "
                "but EPA research shows every 1% of green space prevents "
                "~$200K in downstream flood/heat mitigation costs."
            ),
            position=summary,
            reasoning=(
                f"EPA recommends 15% minimum green space for heat island mitigation. "
                f"{city_name} target: {city_green_target}%. "
                f"At {proposal.parking_spaces} spaces, this development has "
                f"{parking_acres:.1f} acres of impervious surface generating "
                f"7x more stormwater runoff than equivalent green space (USEPA)."
            ),
            evidence=[
                f"Green space {proposal.green_space_pct}% vs {city_green_target}% target (EPA Heat Island Compendium 2023)",
                f"Parking impervious surface: {parking_acres:.1f} acres (330 sqft/space)",
                f"Summer avg temp: {city_avg_temp:.0f}°F — {'HIGH' if city_avg_temp > 85 else 'MODERATE'} heat island risk",
            ],
            objections=[],
            supports=[],
            confidence=0.75,
            is_fallback=True,
        )

    # ── Round 2+: respond directly to Finance and Community proposals ─────────
    finance_op = ops.get("finance")
    community_op = ops.get("community")
    response_parts: list[str] = []
    new_changes: dict[str, float] = {}
    objections = []
    supports = []
    concession_rationale = None

    # Respond to Finance's position on budget / cuts
    if finance_op:
        finance_changes = finance_op.recommendation
        # If Finance proposes cutting housing (to reduce cost), Climate can support this
        if "housing_units" in finance_changes and finance_changes["housing_units"] < proposal.housing_units:
            response_parts.append(
                f"Climate supports Finance's proposal to reduce housing units to "
                f"{int(finance_changes['housing_units'])} — fewer units means less "
                f"impervious infrastructure required."
            )
            supports.append(TargetStatement(
                target_agent="finance",
                engages_with=f"housing_units reduction to {int(finance_changes['housing_units'])}",
                reason="Fewer units reduce overall impervious surface and infrastructure demand."
            ))
        # If Finance proposes cutting green_space_pct, Climate must reject
        if "green_space_pct" in finance_changes and finance_changes["green_space_pct"] < proposal.green_space_pct:
            objections.append(TargetStatement(
                target_agent="finance",
                engages_with=f"green_space_pct cut to {finance_changes['green_space_pct']}%",
                reason=(
                    f"Cutting green space below {proposal.green_space_pct}% risks "
                    f"breaching the EPA 15% minimum. Climate holds firm on the current level "
                    f"or requests an increase toward {city_green_target}%."
                )
            ))
            new_changes["green_space_pct"] = max(proposal.green_space_pct, city_green_target * 0.5)
            response_parts.append(
                f"Finance proposes cutting green space — Climate rejects this. "
                f"EPA requires 15% minimum; we are already {'below' if proposal.green_space_pct < city_green_target else 'at'} target."
            )

    # Core Climate ask — push for green space increase if below target
    if proposal.green_space_pct < city_green_target:
        target_gs = min(proposal.green_space_pct + 10.0, city_green_target)
        gs_cost = _green_space_cost_delta(proposal, target_gs, lot_sqft)
        # Only advocate if within margin or as a counter to Finance
        if margin >= gs_cost or not finance_op:
            new_changes["green_space_pct"] = target_gs
            new_changes["parking_spaces"] = max(0, int(proposal.parking_spaces * 0.75))
            response_parts.append(
                f"Requesting green space increase from {proposal.green_space_pct}% to {target_gs}% "
                f"(~${gs_cost:,.0f} impact). Offsetting cost by reducing parking to free land."
            )
        else:
            # Budget is tight — request minimum viable increase only
            minimal_gs = proposal.green_space_pct + 5.0
            new_changes["green_space_pct"] = minimal_gs
            new_changes["parking_spaces"] = max(0, int(proposal.parking_spaces * 0.80))
            response_parts.append(
                f"Budget is constrained, but Climate requests minimum viable increase "
                f"from {proposal.green_space_pct}% to {minimal_gs}% green space, "
                f"offset by a 20% parking reduction."
            )
            concession_rationale = "Reduced green space ask from ideal to minimum viable given Finance's budget constraint."

    # Respond to Community's community center proposal — multi-story buildings don't reduce green space
    if community_op and "community_center_sqft" in community_op.recommendation:
        new_cc = float(community_op.recommendation["community_center_sqft"])
        response_parts.append(
            f"Community's request for {new_cc:,.0f} sqft community center is a climate non-issue "
            f"if the building is multi-story — indoor rec facilities do NOT reduce green space."
        )
        supports.append(TargetStatement(
            target_agent="community",
            engages_with=f"community_center_sqft expansion to {new_cc:,.0f} sqft",
            reason="Multi-story community centers do not reduce outdoor green space or increase impervious surface."
        ))

    if not response_parts:
        response_parts.append(
            f"Green space ({proposal.green_space_pct}%) vs city target ({city_green_target}%). "
            f"Parking: {proposal.parking_spaces} spaces = {parking_acres:.1f} acres impervious surface."
        )

    score = min(100.0, (proposal.green_space_pct / city_green_target) * 100.0) if city_green_target > 0 else 80.0

    return AgentOpinion(
        agent="climate",
        score=score,
        recommendation=new_changes,
        tension="Finance may see green space as a cost driver, but climate failure costs more in infrastructure damage.",
        position=" | ".join(response_parts),
        reasoning=(
            f"Round {round_num}: green space is {proposal.green_space_pct}% vs {city_green_target}% target. "
            f"Parking generates {parking_acres:.1f} acres of impervious surface. "
            f"EPA minimum is 15% green space for measurable heat island mitigation."
        ),
        evidence=[
            f"Green space {proposal.green_space_pct}% vs {city_green_target}% target",
            f"Parking impervious surface: {parking_acres:.1f} acres",
        ],
        objections=objections,
        supports=supports,
        confidence=0.70,
        is_fallback=True,
        concession_rationale=concession_rationale,
        own_previous_position=own_prev.recommendation if own_prev else None,
    )


def _community_fallback(
    round_num: int,
    proposal: Proposal,
    city_data: dict,
    budget_limit: float,
    bd: CostBreakdown,
    calculated_cost: float,
    over_budget: bool,
    margin: float,
    lot_sqft: float,
    ops: dict[str, AgentOpinion],
    own_prev: AgentOpinion | None,
) -> AgentOpinion:
    city_name = city_data.get("name", proposal.city_slug.replace("_", " ").title())
    # Default community targets
    city_affordable_target: float = 20.0
    housing_units = max(proposal.housing_units, 1)
    sqft_per_unit = proposal.community_center_sqft / housing_units
    cc_adequate = sqft_per_unit > 20.0

    # ── Round 1: state community reality ─────────────────────────────────────
    if round_num == 1:
        proposed_changes: dict[str, float] = {}
        position_parts: list[str] = []

        # Affordable housing — always advocate if below target
        if proposal.affordable_housing_pct < city_affordable_target:
            proposed_changes["affordable_housing_pct"] = min(
                city_affordable_target,
                proposal.affordable_housing_pct + 5.0
            )
            position_parts.append(
                f"Affordable housing at {proposal.affordable_housing_pct}% is below "
                f"{city_name}'s {city_affordable_target}% target — requesting increase "
                f"to {proposed_changes['affordable_housing_pct']}%."
            )

        # Community center — only if below 10 sqft/unit
        if not cc_adequate and sqft_per_unit < 10.0:
            min_needed = housing_units * 7
            proposed_changes["community_center_sqft"] = float(min_needed)
            position_parts.append(
                f"Community center at {sqft_per_unit:.1f} sqft/unit is below the 5–10 sqft/unit minimum. "
                f"Requesting increase to {min_needed:,} sqft."
            )
        elif cc_adequate:
            position_parts.append(
                f"Community center at {sqft_per_unit:.1f} sqft/unit already exceeds the 20 sqft/unit standard — no increase needed."
            )

        score = (
            min(proposal.community_center_sqft / (housing_units * 5.0), 1.0) * 0.4 +
            min(proposal.affordable_housing_pct / city_affordable_target, 1.0) * 0.6
        ) * 100.0 if city_affordable_target > 0 else 50.0

        return AgentOpinion(
            agent="community",
            score=score,
            recommendation=proposed_changes,
            tension=(
                "Finance may push back on affordable housing cost, but HUD data shows "
                "affordable units prevent displacement, which is far more costly to the city."
            ),
            position=" | ".join(position_parts) if position_parts else (
                f"Community standards are broadly met — affordable housing at "
                f"{proposal.affordable_housing_pct}% and community center adequate."
            ),
            reasoning=(
                f"HUD recommends 15–20% affordable housing for mixed-income developments. "
                f"{city_name} target: {city_affordable_target}%. "
                f"Community center: {sqft_per_unit:.1f} sqft/unit "
                f"({'adequate' if cc_adequate else 'below minimum of 5–10 sqft/unit'})."
            ),
            evidence=[
                f"Affordable housing: {proposal.affordable_housing_pct}% vs {city_affordable_target}% target (HUD)",
                f"Community center: {sqft_per_unit:.1f} sqft/unit (standard: 5–10 sqft/unit minimum)",
            ],
            objections=[],
            supports=[],
            confidence=0.75,
            is_fallback=True,
        )

    # ── Round 2+: respond directly to Finance and Climate ────────────────────
    finance_op = ops.get("finance")
    climate_op = ops.get("climate")
    new_changes: dict[str, float] = {}
    response_parts: list[str] = []
    objections = []
    supports = []
    concession_rationale = None

    # Respond to Finance — budget tight: prioritise affordable housing over CC
    finance_over_budget = (
        finance_op and
        finance_op.recommendation and
        any("housing" in k or "parking" in k for k in finance_op.recommendation)
    )

    if finance_over_budget:
        # Budget is strained — only push for affordable housing, not CC
        if proposal.affordable_housing_pct < city_affordable_target:
            ah_delta = _affordable_housing_cost_delta(proposal, proposal.affordable_housing_pct + 3.0, bd)
            new_changes["affordable_housing_pct"] = proposal.affordable_housing_pct + 3.0
            response_parts.append(
                f"Finance signals budget pressure — Community prioritises affordable housing "
                f"(+3% = ${ah_delta:,.0f}) over community center expansion. Housing is more impactful per dollar."
            )
            concession_rationale = "Reduced community center ask to zero given Finance's budget constraint; affordable housing is higher priority."
        else:
            response_parts.append(
                f"Affordable housing already meets the {city_affordable_target}% target. "
                f"Community defers to Finance's budget management."
            )
        # Do NOT push for CC expansion when Finance is already strained
    else:
        # Finance is within budget — advocate for full community needs
        if proposal.affordable_housing_pct < city_affordable_target:
            ah_delta = _affordable_housing_cost_delta(proposal, city_affordable_target, bd)
            new_changes["affordable_housing_pct"] = city_affordable_target
            response_parts.append(
                f"Requesting affordable housing increase to {city_affordable_target}% "
                f"(~${ah_delta:,.0f} subsidy cost)."
            )

        # CC only if genuinely inadequate (< 10 sqft/unit) and Finance not strained
        if not cc_adequate and sqft_per_unit < 10.0:
            min_needed = housing_units * 7
            cc_delta = _community_center_cost_delta(proposal, float(min_needed))
            new_changes["community_center_sqft"] = float(min_needed)
            response_parts.append(
                f"Community center at {sqft_per_unit:.1f} sqft/unit is below minimum; "
                f"requesting {min_needed:,} sqft (~${cc_delta:,.0f})."
            )
        elif cc_adequate:
            response_parts.append(
                f"Community center ({sqft_per_unit:.1f} sqft/unit) already exceeds 20 sqft/unit standard — no increase needed."
            )

    # Respond to Climate's green space request — support it
    if climate_op and "green_space_pct" in climate_op.recommendation:
        new_gs = float(climate_op.recommendation["green_space_pct"])
        response_parts.append(
            f"Community supports Climate's request to increase green space to {new_gs}% — "
            f"parks and green areas directly improve resident quality of life and well-being."
        )
        supports.append(TargetStatement(
            target_agent="climate",
            engages_with=f"green_space_pct increase to {new_gs}%",
            reason="Green space improves resident quality of life and reduces heat stress for vulnerable residents."
        ))

    if not response_parts:
        response_parts.append(
            f"Community standards broadly maintained. Affordable housing: "
            f"{proposal.affordable_housing_pct}% vs {city_affordable_target}% target."
        )

    score = (
        min(proposal.community_center_sqft / (housing_units * 5.0), 1.0) * 0.4 +
        min(proposal.affordable_housing_pct / city_affordable_target, 1.0) * 0.6
    ) * 100.0 if city_affordable_target > 0 else 50.0

    return AgentOpinion(
        agent="community",
        score=score,
        recommendation=new_changes,
        tension="Finance may argue affordable housing costs too much, but the social cost of displacement is higher.",
        position=" | ".join(response_parts),
        reasoning=(
            f"Round {round_num}: affordable housing {proposal.affordable_housing_pct}% vs {city_affordable_target}% target. "
            f"Community center {sqft_per_unit:.1f} sqft/unit "
            f"({'adequate' if cc_adequate else 'below minimum'}). "
            f"{'Prioritising housing over CC given Finance budget constraint.' if finance_over_budget else 'Full community needs advocacy.'}"
        ),
        evidence=[
            f"Affordable housing: {proposal.affordable_housing_pct}% vs {city_affordable_target}% HUD target",
            f"Community center: {sqft_per_unit:.1f} sqft/unit",
        ],
        objections=objections,
        supports=supports,
        confidence=0.70,
        is_fallback=True,
        concession_rationale=concession_rationale,
        own_previous_position=own_prev.recommendation if own_prev else None,
    )


# ── Internal helper to extract data loader from ops (best-effort) ─────────────

def cost_calculator_from_ops(ops: dict) -> Any | None:
    """Try to recover a DataLoader from the agent opinions dict.  Best-effort only."""
    return None  # The caller must pass a CostCalculator explicitly; this is a stub.
