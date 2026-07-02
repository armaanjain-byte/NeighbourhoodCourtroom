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
            city_data = self.cost_calculator.data_loader.load_city(args["city_slug"])
            return {"estimated_cost": self.cost_calculator.calculate_construction_cost(proposal, city_data).total_estimated_cost}
        elif name == "get_cost_benchmarks":
            standards = self.cost_calculator.data_loader.get_reference_standards(FINANCE_STANDARDS_FILE)
            category = args.get("category", "all")
            if category == "all":
                return {k: v for k, v in standards.items() if not k.startswith("_")}
            return {category: standards.get(category, {})}
        else:
            return super().execute_tool_call(name, args)

    def build_system_prompt(
        self,
        proposal: "Proposal",
        context: dict,
        *,
        round_number: int = 1,
        opponent_opinions: dict | None = None,
    ) -> str:
        """Build a domain-grounded Finance Agent system prompt.

        Pre-computes real construction cost figures via CostCalculator and
        injects the other agents' previous positions so the LLM can engage
        with their specific proposals rather than speaking in the abstract.
        """
        # ── Gather cost facts ────────────────────────────────────────────────
        budget_limit: float = context.get("budget_limit", 0.0)
        try:
            city_raw = self.cost_calculator.data_loader.load_city(proposal.city_slug)
            city_name: str = city_raw.get("name", proposal.city_slug.replace("_", " ").title())
            population: int = city_raw.get("population", 0)
        except Exception:
            city_name = proposal.city_slug.replace("_", " ").title()
            city_raw = {}
            population = 0

        # Determine city tier for residential cost benchmark
        if population > 1_000_000:
            cost_per_unit = 450_000
            tier_label = "Tier 1 (major metro)"
        elif population > 500_000:
            cost_per_unit = 300_000
            tier_label = "Tier 2 (mid-size city)"
        else:
            cost_per_unit = 200_000
            tier_label = "Tier 3 (affordable/midsize)"

        # Compute current estimated cost
        try:
            city_data = self.cost_calculator.data_loader.get_construction_costs(proposal.city_slug)
            breakdown = self.cost_calculator.calculate_construction_cost(proposal, city_data)
            calculated_cost = breakdown.total_estimated_cost
        except Exception:
            calculated_cost = cost_per_unit * proposal.housing_units

        over_budget = budget_limit > 0 and calculated_cost > budget_limit
        if budget_limit > 0:
            if over_budget:
                overage = calculated_cost - budget_limit
                budget_status = f"OVER BUDGET by ${overage:,.0f}"
            else:
                margin = budget_limit - calculated_cost
                budget_status = f"Within budget by ${margin:,.0f}"
        else:
            budget_status = "No budget limit set"

        # ── Serialise opponent positions ─────────────────────────────────────
        ops = opponent_opinions or {}
        climate_pos = self._format_opponent_position("climate", ops.get("climate"))
        community_pos = self._format_opponent_position("community", ops.get("community"))

        # ── Build prompt ─────────────────────────────────────────────────────
        prompt = f"""You are the Finance Agent in an urban development debate. \
Your ONLY job is to ensure the proposed development stays within the hard budget \
limit of ${budget_limit:,.0f}.

REAL CONSTRUCTION COST FACTS you must use (do not invent numbers):
- Each residential unit costs approximately ${cost_per_unit:,} to build in {city_name} \
({tier_label} — NAHB 2024 and RSMeans data)
- Each structured parking space costs ~$30,000 (WGI 2024 Parking Cost Outlook)
- Each surface parking space costs ~$4,000
- Community center / rec facility costs ~$403/sqft (RSMeans commercial 2024)
- Affordable housing units cost 25% more than market-rate units to build
- These are hard costs. Add ~25% for soft costs (permits, design, contingency)

CURRENT ESTIMATED COST: ${calculated_cost:,.0f} (computed from current parameters)
BUDGET LIMIT: ${budget_limit:,.0f}
BUDGET STATUS: {budget_status}

CURRENT PROPOSAL PARAMETERS:
- Housing units: {proposal.housing_units}
- Parking spaces: {proposal.parking_spaces}
- Community center: {proposal.community_center_sqft:,.0f} sqft
- Green space: {proposal.green_space_pct}%
- Affordable housing: {proposal.affordable_housing_pct}%

WHAT THE OTHER AGENTS SAID LAST ROUND:
- Climate Agent: {climate_pos}
- Community Agent: {community_pos}

YOUR TASK THIS ROUND:
You must respond SPECIFICALLY to what Climate and Community said. \
If Climate wants more green space, calculate the exact cost of their proposed \
green space increase and say whether it fits in the budget. \
If Community wants a bigger community center, calculate the exact cost delta and \
say whether it can be absorbed. If you must concede, specify WHICH parameter you \
will reduce and by HOW MUCH to compensate. \
Never say "the project can be brought within limits" without specifying exactly \
which numbers change. Never propose increasing the budget — it is fixed.

DOMAIN CONSTRAINTS: You may ONLY argue about: total cost, housing unit count, \
parking spaces, community center sqft. You may NOT argue about green space \
percentage or affordable housing percentage — those are Climate and Community's \
domains respectively.

{self.PERSONALITY_BRIEF}
Your risk tolerance: {self.RISK_TOLERANCE}."""
        return prompt

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
