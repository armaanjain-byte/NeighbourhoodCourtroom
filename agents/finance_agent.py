"""Finance Agent.

Purpose:
    Deterministic agent representing budget discipline.
    Goals: reduce cost, improve affordability, maximize housing units per dollar.
    Ignores climate, green space, community outcomes.

    generate_opinion passes only construction_costs data to Gemini.
    Supports round_number=1 (independent) and round_number=2 (cross-agent rebuttal)
    by forwarding those parameters to BaseAgent.generate_opinion.

Personality Brief:
    Archetype of a pragmatic municipal budget officer who has personally seen projects
    fail from severe cost overruns. Skeptical of idealism, values measurable ROI and
    budget discipline, but remains dedicated to practical civic development.

Risk Tolerance:
    Low risk tolerance on budget overruns.

Dependencies:
    agents.base_agent.BaseAgent, tools.cost_calculator.CostCalculator
"""

from __future__ import annotations

from typing import Any

from models.proposal import Proposal
from models.agent_output import AgentOutput
from models.agent_opinion import AgentOpinion
from agents.base_agent import BaseAgent
from tools.cost_calculator import CostCalculator


class FinanceAgent(BaseAgent):
    """The Finance Agent evaluates proposals strictly on budget and density."""

    BASE_TARGET_BUDGET = 25_000_000.0
    RISK_TOLERANCE = "low risk tolerance on budget overruns"
    PERSONALITY_BRIEF = (
        "You are a pragmatic municipal budget officer who has personally seen projects fail from severe cost overruns. "
        "You are skeptical of unfunded idealism and demand measurable ROI and strict budget discipline, but you are not heartless—you want civic projects to succeed by remaining financially viable."
    )

    def __init__(self, cost_calculator: CostCalculator):
        """Initialize the Finance Agent.

        Parameters
        ----------
        cost_calculator : CostCalculator
            Engine used to compute total estimated cost and fetch city data.
        """
        self.cost_calculator = cost_calculator

    @property
    def agent_name(self) -> str:
        return "finance"

    @property
    def personality_brief(self) -> str:
        return self.PERSONALITY_BRIEF

    @property
    def risk_tolerance(self) -> str:
        return self.RISK_TOLERANCE


    @property
    def tool_declarations(self) -> list[Any]:
        return [
            {
                "name": "get_construction_costs",
                "description": "Get construction cost data (base cost per unit, green space multiplier, parking cost, community center cost per sqft, city index) for a city.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "city_slug": {"type": "STRING"}
                    },
                    "required": ["city_slug"]
                }
            },
            {
                "name": "calculate_cost_estimate",
                "description": "Calculate the total estimated construction cost for a proposal configuration.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "housing_units": {"type": "INTEGER"},
                        "green_space_pct": {"type": "NUMBER"},
                        "parking_spaces": {"type": "INTEGER"},
                        "community_center_sqft": {"type": "NUMBER"},
                        "city_slug": {"type": "STRING"}
                    },
                    "required": ["housing_units", "green_space_pct", "parking_spaces", "community_center_sqft", "city_slug"]
                }
            }
        ]

    def execute_tool_call(self, name: str, args: dict[str, Any]) -> Any:
        if name == "get_construction_costs":
            costs = self.cost_calculator.data_loader.get_construction_costs(args["city_slug"])
            city_index = costs.get("city_index", 1.0)
            return {
                "construction_costs": costs,
                "base_target_budget": self.BASE_TARGET_BUDGET,
                "local_budget": self.BASE_TARGET_BUDGET * city_index
            }
        elif name == "calculate_cost_estimate":
            from models.proposal import Proposal
            proposal = Proposal(
                housing_units=args["housing_units"],
                green_space_pct=args["green_space_pct"],
                parking_spaces=args["parking_spaces"],
                community_center_sqft=args["community_center_sqft"],
                city_slug=args["city_slug"]
            )
            return {"estimated_cost": self.cost_calculator.calculate_estimated_cost(proposal)}
        else:
            return super().execute_tool_call(name, args)

    def generate_opinion(
        self,
        proposal: Proposal,
        context: dict[str, Any],
        *,
        round_number: int = 1,
        opponent_opinions: dict[str, AgentOpinion] | None = None,
        own_previous_opinion: AgentOpinion | None = None,
    ) -> AgentOpinion:
        """Generate a finance-domain AgentOpinion using Gemini.

        In Round 2, passes opponent Round 1 opinions so Gemini can issue explicit
        objections/supports. Falls back to evaluate() if Gemini is unavailable
        or returns invalid output.

        Parameters
        ----------
        proposal : Proposal
            The current proposal state.
        context : dict[str, Any]
            Full context dict (used only in evaluate() fallback).
        round_number : int
            1 for independent opinion, 2 for cross-agent rebuttal.
        opponent_opinions : dict[str, AgentOpinion] | None
            Round 1 opinions of the other agents (required for round_number=2).
        own_previous_opinion : AgentOpinion | None, optional
            The agent's own opinion from the previous round (used for concession rationale).

        Returns
        -------
        AgentOpinion
        """
        return super().generate_opinion(
            proposal,
            context,
            round_number=round_number,
            opponent_opinions=opponent_opinions,
            own_previous_opinion=own_previous_opinion,
        )

    def evaluate(self, proposal: Proposal, context: dict[str, Any]) -> AgentOutput:
        """Evaluate the proposal against city-adjusted budget limits.

        Flow:
        1. Fetch city_index from DataLoader's construction_costs.
        2. Calculate local budget = BASE_TARGET_BUDGET * city_index.
        3. Compare proposal.estimated_cost to local budget.
        4. Over budget: Score drops, verdict "modify", cuts amenities, boosts housing.
        5. Well under budget: High score, verdict "modify", boosts housing.
        6. On budget: High score, verdict "accept", no changes.
        """
        try:
            costs = self.cost_calculator.data_loader.get_construction_costs(proposal.city_slug)
            city_index = costs.get("city_index", 1.0)
        except Exception as e:
            # Invalid dataset handling
            return self.build_output(
                score=0.0,
                verdict="reject",
                changes={},
                reasoning=f"Failed to load cost data for {proposal.city_slug}: {e}"
            )

        local_budget = self.BASE_TARGET_BUDGET * city_index
        cost = self.cost_calculator.calculate_estimated_cost(proposal)

        if cost > local_budget:
            # Over budget
            ratio = cost / local_budget
            # e.g., 30M / 25M = 1.2 -> score = 100 - (1.2 * 40) = 52
            score = max(0.0, 100.0 - (ratio * 40))
            verdict = "modify"

            changes = {
                "green_space_pct": max(0.0, proposal.green_space_pct - 10.0),
                "housing_units": proposal.housing_units + 50,
                "parking_spaces": int(proposal.parking_spaces * 0.8),
            }
            reasoning = (
                f"Project estimated cost (${cost:,.2f}) exceeds local budget limit "
                f"(${local_budget:,.2f}). Proposing to reduce green space "
                f"and parking, and increase housing density to improve budget efficiency."
            )

        elif cost < local_budget * 0.9:
            # Well under budget (more than 10% under) -> under-utilization
            score = 90.0
            verdict = "modify"
            changes = {
                "housing_units": proposal.housing_units + 20
            }
            reasoning = (
                f"Project is well under the local budget limit of ${local_budget:,.2f}. "
                f"Increasing housing units to maximize budget utilization."
            )

        else:
            # Near budget (between 90% and 100% of budget limit)
            score = 95.0
            verdict = "accept"
            changes = {}
            reasoning = "Project budget is utilized efficiently and is within acceptable limits."

        filtered = self.filter_unknown_parameters(changes)

        return self.build_output(
            score=score,
            verdict=verdict,
            changes=filtered,
            reasoning=reasoning
        )
