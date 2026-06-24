"""Climate Agent.

Purpose:
    Deterministic agent representing environmental resilience.
    Goals: increase green space, improve heat resilience, stormwater management.
    Ignores budget, affordability, and housing efficiency.

    generate_opinion passes only the climate + land_use data slice to Gemini.
    Supports round_number=1 (independent) and round_number=2 (cross-agent rebuttal)
    by forwarding those parameters to BaseAgent.generate_opinion.

Personality Brief:
    Archetype of a field-experienced urban resilience planner who has seen specific
    climate failures (heat islands, severe flood damage) up close. Evidence-driven
    and urgent about immediate physical risks, but maintains a calm, non-alarmist tone.

Risk Tolerance:
    Low risk tolerance on environmental harm and climate vulnerability.

Dependencies:
    agents.base_agent.BaseAgent, tools.data_loader.DataLoader
"""

from __future__ import annotations

from typing import Any

from models.proposal import Proposal
from models.agent_output import AgentOutput
from models.agent_opinion import AgentOpinion
from agents.base_agent import BaseAgent
from tools.data_loader import DataLoader


class ClimateAgent(BaseAgent):
    """The Climate Agent evaluates proposals strictly on environmental resilience."""

    RISK_TOLERANCE = "low risk tolerance on environmental harm and climate vulnerability"
    PERSONALITY_BRIEF = (
        "You are a field-experienced urban resilience planner who has seen specific climate failures, like deadly heat islands and storm flood damage, up close. "
        "You are highly evidence-driven and speak with calm urgency about immediate physical risks without resorting to alarmist hysteria."
    )

    def __init__(self, data_loader: DataLoader):
        """Initialize the Climate Agent.

        Parameters
        ----------
        data_loader : DataLoader
            Data service used to fetch local climate and land use targets.
        """
        self.data_loader = data_loader

    @property
    def agent_name(self) -> str:
        return "climate"

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
                "name": "get_climate_data",
                "description": "Get climate data (target green space percentage) for a city.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "city_slug": {"type": "STRING"}
                    },
                    "required": ["city_slug"]
                }
            },
            {
                "name": "get_land_use_data",
                "description": "Get land use data (max parking spaces) for a city.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "city_slug": {"type": "STRING"}
                    },
                    "required": ["city_slug"]
                }
            }
        ]

    def execute_tool_call(self, name: str, args: dict[str, Any]) -> Any:
        if name == "get_climate_data":
            return self.data_loader.get_climate(args["city_slug"])
        elif name == "get_land_use_data":
            return self.data_loader.get_land_use(args["city_slug"])
        else:
            return super().execute_tool_call(name, args)

    def generate_opinion(
        self,
        proposal: Proposal,
        context: dict[str, Any],
        *,
        round_number: int = 1,
        opponent_opinions: dict[str, AgentOpinion] | None = None,
    ) -> AgentOpinion:
        """Generate a climate-domain AgentOpinion using Gemini.

        In Round 2, passes opponent Round 1 opinions so Gemini can issue explicit objections/supports.
        Falls back to evaluate() if Gemini is unavailable or returns invalid output.

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

        Returns
        -------
        AgentOpinion
        """
        return super().generate_opinion(
            proposal,
            context,
            round_number=round_number,
            opponent_opinions=opponent_opinions,
        )

    def evaluate(self, proposal: Proposal, context: dict[str, Any]) -> AgentOutput:
        """Evaluate the proposal against environmental targets.

        Flow:
        1. Fetch climate and land_use data from DataLoader.
        2. Extract target green space percentage.
        3. Evaluate proposal's green space and parking limits.
        4. Calculate derived metrics (tree canopy, heat resilience) based on green space.
        5. If poor: Score drops, verdict "modify", boosts green space, cuts parking.
        6. If good: High score, verdict "accept".
        """
        try:
            climate = self.data_loader.get_climate(proposal.city_slug)
            land_use = self.data_loader.get_land_use(proposal.city_slug)
        except Exception as e:
            # Invalid dataset handling
            return self.build_output(
                score=0.0,
                verdict="reject",
                changes={},
                reasoning=f"Failed to load climate/land_use data for {proposal.city_slug}: {e}"
            )

        # Baseline targets from datasets, fallback to defaults
        target_green_space = climate.get("target_green_space_pct", 35.0)
        max_parking = land_use.get("max_parking_spaces", 150)

        # Derived mock metrics based on physical parameters
        # Green space strongly drives tree canopy and resilience; parking reduces resilience
        tree_canopy_pct = proposal.green_space_pct * 0.8
        heat_resilience_score = (proposal.green_space_pct * 2.0) - (proposal.parking_spaces * 0.1)
        stormwater_capture_pct = proposal.green_space_pct * 1.5

        # Evaluate score mathematically
        # Score heavily penalized if green space is below target
        green_ratio = proposal.green_space_pct / target_green_space
        parking_ratio = max_parking / max(1, proposal.parking_spaces)  # >1 is good

        # Base score on green space ratio, adjusted by parking penalty
        raw_score = (green_ratio * 80.0) + (min(1.0, parking_ratio) * 20.0)
        score = max(0.0, min(100.0, raw_score))

        if score < 85.0:
            verdict = "modify"

            # Propose improving climate outcomes
            changes = {
                "green_space_pct": max(proposal.green_space_pct + 10.0, target_green_space),
                "parking_spaces": int(proposal.parking_spaces * 0.7),
                "community_center_sqft": proposal.community_center_sqft + 500.0,  # for cooling centers
            }
            reasoning = (
                f"Proposal has poor environmental resilience (Score: {score:.1f}). "
                f"Current green space ({proposal.green_space_pct}%) is below target ({target_green_space}%). "
                f"Proposing to increase green space for better tree canopy ({tree_canopy_pct:.1f}%) "
                f"and heat resilience, reduce parking to limit runoff, and expand community "
                f"centers for extreme weather shelters."
            )
        else:
            verdict = "accept"
            changes = {}
            reasoning = (
                f"Proposal meets environmental standards (Score: {score:.1f}). "
                f"Strong green space ({proposal.green_space_pct}%) provides adequate "
                f"stormwater capture ({stormwater_capture_pct:.1f}%) and heat resilience."
            )

        filtered = self.filter_unknown_parameters(changes)

        return self.build_output(
            score=score,
            verdict=verdict,
            changes=filtered,
            reasoning=reasoning
        )
