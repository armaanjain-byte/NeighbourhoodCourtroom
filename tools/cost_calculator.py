"""Cost Calculator Layer.

Purpose:
    The single source of truth for estimating the financial cost of a proposal.
    Calculates cost deterministically based on physical parameters and DataLoader
    city-specific cost indices.

Dependencies:
    models.proposal.Proposal, tools.data_loader.DataLoader
"""

from typing import Any

from models.proposal import Proposal
from tools.data_loader import DataLoader, CityNotFoundError, DatasetLoadError


class CostCalculator:
    """Computes deterministic financial costs for proposals."""

    # Default fallback base costs if not specified in dataset
    DEFAULT_BASE_COSTS = {
        "housing_unit": 150000.0,
        "parking_space": 25000.0,
        "green_space_pct": 500000.0,  # cost per percentage point of green space
        "community_center_sqft": 350.0,
    }

    def __init__(self, data_loader: DataLoader):
        """Initialize the CostCalculator with a DataLoader instance."""
        self.data_loader = data_loader

    def calculate_cost_breakdown(self, proposal: Proposal) -> dict[str, float]:
        """Compute the itemized financial cost for a proposal.

        Parameters
        ----------
        proposal : Proposal
            The proposal containing the physical parameters.

        Returns
        -------
        dict[str, float]
            A dictionary containing the individual cost components and total cost.
        """
        try:
            cost_data = self.data_loader.get_construction_costs(proposal.city_slug)
        except (CityNotFoundError, DatasetLoadError):
            # Fallback to neutral data if dataset is missing/malformed
            cost_data = {
                "city_index": 1.0,
                "base_costs": {},
                "soft_cost_multiplier": 1.1,
                "contingency_multiplier": 1.1,
            }

        raw_index = cost_data.get("city_index", 1.0)
        # Normalize index (e.g. 92.0 -> 0.92) if it's on a 100-scale
        city_index = raw_index / 100.0 if raw_index > 10.0 else raw_index
        
        base_costs = cost_data.get("base_costs", {})
        soft_mult = cost_data.get("soft_cost_multiplier", 1.1)
        cont_mult = cost_data.get("contingency_multiplier", 1.1)

        def _get_base(key: str) -> float:
            return float(base_costs.get(key, self.DEFAULT_BASE_COSTS[key]))

        housing_base = _get_base("housing_unit")
        parking_base = _get_base("parking_space")
        green_base = _get_base("green_space_pct")
        community_base = _get_base("community_center_sqft")

        # Direct construction costs (hard costs)
        housing_cost = proposal.housing_units * housing_base * city_index
        parking_cost = proposal.parking_spaces * parking_base * city_index
        green_space_cost = proposal.green_space_pct * green_base * city_index
        community_center_cost = proposal.community_center_sqft * community_base * city_index

        subtotal_hard_costs = housing_cost + parking_cost + green_space_cost + community_center_cost

        # Soft costs (e.g. design, permits)
        soft_costs = subtotal_hard_costs * (soft_mult - 1.0)

        # Contingency
        contingency_costs = (subtotal_hard_costs + soft_costs) * (cont_mult - 1.0)

        total_estimated_cost = subtotal_hard_costs + soft_costs + contingency_costs

        return {
            "housing_cost": housing_cost,
            "parking_cost": parking_cost,
            "green_space_cost": green_space_cost,
            "community_center_cost": community_center_cost,
            "subtotal_hard_costs": subtotal_hard_costs,
            "soft_costs": soft_costs,
            "contingency_costs": contingency_costs,
            "total_estimated_cost": total_estimated_cost,
        }

    def calculate_estimated_cost(self, proposal: Proposal) -> float:
        """Compute the total estimated cost for a proposal.

        Parameters
        ----------
        proposal : Proposal
            The proposal to evaluate.

        Returns
        -------
        float
            The total estimated cost.
        """
        breakdown = self.calculate_cost_breakdown(proposal)
        return breakdown["total_estimated_cost"]

    def calculate_cost_delta(self, old_proposal: Proposal, new_proposal: Proposal) -> float:
        """Calculate the change in cost between two proposals.

        Parameters
        ----------
        old_proposal : Proposal
            The original state.
        new_proposal : Proposal
            The new state.

        Returns
        -------
        float
            Positive if new proposal is more expensive, negative if cheaper.
        """
        old_cost = self.calculate_estimated_cost(old_proposal)
        new_cost = self.calculate_estimated_cost(new_proposal)
        return new_cost - old_cost
