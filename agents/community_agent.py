"""Community Agent.

Purpose:
    Deterministic agent representing resident wellbeing.
    Goals: improve accessibility, walkability, amenities, quality of life.
    Ignores construction cost and climate metrics.

Dependencies:
    agents.base_agent.BaseAgent, tools.data_loader.DataLoader
"""

from typing import Any

from models.proposal import Proposal
from models.agent_output import AgentOutput
from agents.base_agent import BaseAgent
from tools.data_loader import DataLoader


class CommunityAgent(BaseAgent):
    """The Community Agent evaluates proposals on resident wellbeing and amenities."""

    def __init__(self, data_loader: DataLoader):
        """Initialize the Community Agent.

        Parameters
        ----------
        data_loader : DataLoader
            Data service used to fetch demographics, walkability, and land use data.
        """
        self.data_loader = data_loader

    @property
    def agent_name(self) -> str:
        return "community"

    def evaluate(self, proposal: Proposal, context: dict[str, Any]) -> AgentOutput:
        """Evaluate the proposal against community wellbeing targets.

        Flow:
        1. Fetch demographics, walkability, and land_use data from DataLoader.
        2. Extract target community center area and affordable housing ratios.
        3. Evaluate effective walkability (base score + green space bonus - parking penalty).
        4. Calculate composite score based on amenities, affordability, and walkability.
        5. If poor: Score drops, verdict "modify", boosts amenities and affordability.
        6. If good: High score, verdict "accept".
        """
        try:
            demographics = self.data_loader.get_demographics(proposal.city_slug)
            walkability = self.data_loader.get_walkability(proposal.city_slug)
            _ = self.data_loader.get_land_use(proposal.city_slug) # Ensures land use exists
        except Exception as e:
            # Invalid dataset handling
            return self.build_output(
                score=0.0,
                verdict="reject",
                changes={},
                reasoning=f"Failed to load community-related data for {proposal.city_slug}: {e}"
            )

        target_community_sqft = demographics.get("target_community_center_sqft", 10000.0)
        target_affordable = demographics.get("target_affordable_housing_pct", 20.0)
        base_walkability = walkability.get("walkability_score", 50.0)

        # Derived mock metrics
        # Walkability improves with green space and decreases with excessive parking
        effective_walkability = base_walkability + (proposal.green_space_pct * 0.5) - (proposal.parking_spaces * 0.1)
        effective_walkability = max(0.0, min(100.0, effective_walkability))

        community_ratio = proposal.community_center_sqft / target_community_sqft if target_community_sqft else 1.0
        affordable_ratio = proposal.affordable_housing_pct / target_affordable if target_affordable else 1.0

        # High housing density without adequate community space causes a penalty
        density_penalty = 0.0
        if proposal.housing_units > 150 and community_ratio < 0.8:
            density_penalty = 15.0

        # Score mathematically: 40% amenities, 30% affordability, 30% walkability
        raw_score = (min(1.0, community_ratio) * 40.0) + \
                    (min(1.0, affordable_ratio) * 30.0) + \
                    (effective_walkability * 0.3) - \
                    density_penalty

        score = max(0.0, min(100.0, raw_score))

        if score < 85.0:
            verdict = "modify"
            
            changes = {
                "community_center_sqft": max(proposal.community_center_sqft + 2000.0, target_community_sqft),
                "affordable_housing_pct": max(proposal.affordable_housing_pct + 5.0, target_affordable),
                "parking_spaces": max(0, proposal.parking_spaces - 20),
                "green_space_pct": proposal.green_space_pct + 5.0,
            }
            reasoning = (
                f"Proposal lacks adequate community amenities and accessibility (Score: {score:.1f}). "
                f"Proposing to increase community center space to {changes['community_center_sqft']} sqft, "
                f"boost affordable housing to {changes['affordable_housing_pct']}%, "
                f"and slightly reduce parking to improve the effective walkability score."
            )
        else:
            verdict = "accept"
            changes = {}
            reasoning = (
                f"Proposal supports a high quality of life for residents (Score: {score:.1f}). "
                f"Community amenities ({proposal.community_center_sqft} sqft) and affordable housing "
                f"are well balanced with the local walkability index."
            )

        filtered = self.filter_unknown_parameters(changes)

        return self.build_output(
            score=score,
            verdict=verdict,
            changes=filtered,
            reasoning=reasoning
        )
