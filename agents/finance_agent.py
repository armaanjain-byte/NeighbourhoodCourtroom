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

# Filename for the finance domain knowledge base
FINANCE_STANDARDS_FILE = "finance_standards.json"


class FinanceAgent(BaseAgent):
    """The Finance Agent evaluates proposals strictly on budget and density."""

    # Budget is now passed in via proposal.budget_limit.
    # We no longer rely on BASE_TARGET_BUDGET.
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
            },
            {
                "name": "get_cost_benchmarks",
                "description": (
                    "Get nationally recognized cost benchmarks, parking ratio standards, and civic amenity ROI data from published sources "
                    "(RSMeans, ULI, HUD). Use these to compare city-specific costs against industry standards and justify your position "
                    "with authoritative references — e.g. whether parking costs are above typical ranges, or whether green space ROI "
                    "justifies investment. Cite specific benchmark values from this tool as evidence."
                ),
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "category": {
                            "type": "STRING",
                            "description": "One of: 'building_cost_benchmarks', 'parking_ratio_standards', 'civic_amenity_roi', 'affordability_benchmarks', or 'all'"
                        }
                    },
                    "required": ["category"]
                }
            }
        ]

    def execute_tool_call(self, name: str, args: dict[str, Any]) -> Any:
        if name == "get_construction_costs":
            costs = self.cost_calculator.data_loader.get_construction_costs(args["city_slug"])
            city_index = costs.get("city_index", 1.0)
            return {
                "construction_costs": costs,
                "local_budget": args.get("budget_limit", 0.0)
            }
        elif name == "calculate_cost_estimate":
            from models.proposal import Proposal
            proposal = Proposal(
                housing_units=args["housing_units"],
                green_space_pct=args["green_space_pct"],
                parking_spaces=args["parking_spaces"],
                community_center_sqft=args["community_center_sqft"],
                city_slug=args["city_slug"],
                affordable_housing_pct=0.0,
            )
            city_data = self.cost_calculator.data_loader.get_city(args["city_slug"])
            return {"estimated_cost": self.cost_calculator.calculate_construction_cost(proposal, city_data).total_estimated_cost}
        elif name == "get_cost_benchmarks":
            standards = self.cost_calculator.data_loader.get_reference_standards(FINANCE_STANDARDS_FILE)
            category = args.get("category", "all")
            if category == "all":
                return {k: v for k, v in standards.items() if not k.startswith("_")}
            return {category: standards.get(category, {})}
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
        1. Calculate calculated_cost using cost_calculator.
        2. Compare calculated_cost to proposal.budget_limit.
        3. Over budget: Score drops based on overrun, verdict "modify", cuts amenities, boosts housing.
        4. Well under budget: High score, verdict "modify", boosts housing.
        5. On budget: High score, verdict "accept", no changes.
        """
        local_budget = context.get("budget_limit", 0.0)
        
        # We must fetch city_data to pass to check_budget
        city_data = self.cost_calculator.data_loader.load_city(proposal.city_slug)
        budget_status = self.cost_calculator.check_budget(proposal, city_data, local_budget)
        
        cost = budget_status["breakdown"].total_estimated_cost
        
        import logging
        if not local_budget or local_budget <= 0:
            logging.getLogger(__name__).warning("budget_limit is 0 or None, defaulting Finance score to 50")
            local_budget = 50_000_000.0 # fallback if unset
            score = 50.0
        else:
            if not budget_status["within_budget"]:
                # over budget
                score = max(0.0, 100.0 - ((cost - local_budget) / local_budget) * 100.0)
            else:
                score = min(100.0, 80.0 + (local_budget - cost) / local_budget * 20.0)

        if cost > local_budget:
            verdict = "modify"

            changes: dict[str, float] = {
                "green_space_pct": float(max(0.0, proposal.green_space_pct - 10.0)),
                "housing_units": float(proposal.housing_units + 50),
                "parking_spaces": float(int(proposal.parking_spaces * 0.8)),
            }
            reasoning = (
                f"Project estimated cost (${cost:,.2f}) exceeds local budget limit "
                f"(${local_budget:,.2f}). Proposing to reduce green space "
                f"and parking, and increase housing density to improve budget efficiency."
            )

        elif cost < local_budget * 0.9:
            # Well under budget (more than 10% under) -> under-utilization
            verdict = "modify"
            changes: dict[str, float] = {
                "housing_units": float(proposal.housing_units + 20)
            }
            reasoning = (
                f"Project is well under the local budget limit of ${local_budget:,.2f}. "
                f"Increasing housing units to maximize budget utilization."
            )

        else:
            # Near budget (between 90% and 100% of budget limit)
            verdict = "accept"
            changes: dict[str, float] = {}
            reasoning = "Project budget is utilized efficiently and is within acceptable limits."

        filtered = self.filter_unknown_parameters(changes)

        return self.build_output(
            score=score,
            score_rationale="Score based on budget utilization and cost limits.",
            verdict=verdict,
            changes=filtered,
            reasoning=reasoning
        )
