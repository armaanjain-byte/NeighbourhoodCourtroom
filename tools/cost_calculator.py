from dataclasses import dataclass
from typing import Dict, Any
from models.proposal import Proposal
from tools.data_loader import DataLoader

COST_CONSTANTS = {
    # Multifamily residential: $200–$400/sqft depending on city tier
    # Source: NAHB 2024, RSMeans
    "residential_cost_per_unit": {
        "tier_1": 450_000,   # NYC, SF, Boston, Seattle
        "tier_2": 300_000,   # Denver, Austin, Atlanta, Chicago
        "tier_3": 200_000,   # midsize/affordable cities
    },
    # Parking structure: $29,900/space median (WGI 2024 Parking Cost Outlook)
    # Surface lot: $3,500–$5,000/space
    "parking_cost_per_space": {
        "structured": 30_000,
        "surface": 4_000,
    },
    # Community center / recreational facility: $403/sqft avg (RSMeans/Autodesk 2024)
    "community_center_cost_per_sqft": 403,
    # Green space / park landscaping: $50–$120/sqft for urban developed park
    "green_space_cost_per_sqft": 80,
    # Affordable housing subsidy premium: 20–30% above market unit cost
    "affordable_housing_premium_pct": 0.25,
    # Soft costs (permits, design, contingency): 25% of hard costs
    "soft_cost_multiplier": 1.25,
}


@dataclass
class CostBreakdown:
    residential_cost: float
    affordable_premium: float
    parking_cost: float
    community_center_cost: float
    green_space_cost: float
    subtotal_hard_costs: float
    soft_costs: float
    total_estimated_cost: float


class CostCalculator:
    """Calculates construction costs based on real-world 2024 benchmarks."""
    def __init__(self, data_loader: DataLoader):
        self.data_loader = data_loader

    def calculate_construction_cost(self, proposal: Proposal, city_data: Dict[str, Any] = None) -> CostBreakdown:
        """Calculate the complete construction cost breakdown for a given proposal."""
        if city_data is None:
            # Fallback to fetching it ourselves if not provided
            city_data = self.data_loader.load_city(proposal.city_slug)
            
        population = city_data.get("population", 0)
        
        # Determine tier
        if population > 1_000_000:
            tier = "tier_1"
        elif population > 500_000:
            tier = "tier_2"
        else:
            tier = "tier_3"
            
        base_unit_cost = COST_CONSTANTS["residential_cost_per_unit"][tier] * proposal.housing_units
        affordable_premium = base_unit_cost * (proposal.affordable_housing_pct / 100.0) * COST_CONSTANTS["affordable_housing_premium_pct"]
        
        if proposal.parking_spaces > 200:
            parking_cost = proposal.parking_spaces * COST_CONSTANTS["parking_cost_per_space"]["structured"]
        else:
            parking_cost = proposal.parking_spaces * COST_CONSTANTS["parking_cost_per_space"]["surface"]
            
        cc_cost = proposal.community_center_sqft * COST_CONSTANTS["community_center_cost_per_sqft"]
        
        lot_sqft = city_data.get("lot_sqft", 1_000_000)
        green_cost = (proposal.green_space_pct / 100.0) * lot_sqft * COST_CONSTANTS["green_space_cost_per_sqft"]
        
        subtotal_hard_costs = base_unit_cost + affordable_premium + parking_cost + cc_cost + green_cost
        soft_costs = subtotal_hard_costs * (COST_CONSTANTS["soft_cost_multiplier"] - 1.0)
        
        total_estimated_cost = subtotal_hard_costs + soft_costs
        
        return CostBreakdown(
            residential_cost=base_unit_cost,
            affordable_premium=affordable_premium,
            parking_cost=parking_cost,
            community_center_cost=cc_cost,
            green_space_cost=green_cost,
            subtotal_hard_costs=subtotal_hard_costs,
            soft_costs=soft_costs,
            total_estimated_cost=total_estimated_cost
        )

    def check_budget(self, proposal: Proposal, city_data: Dict[str, Any], budget_limit: float) -> Dict[str, Any]:
        """Verify if a proposal falls within the hard budget constraint."""
        breakdown = self.calculate_construction_cost(proposal, city_data)
        
        if budget_limit <= 0:
            return {
                "within_budget": True,
                "overage": 0.0,
                "breakdown": breakdown
            }
            
        overage = breakdown.total_estimated_cost - budget_limit
        return {
            "within_budget": overage <= 0,
            "overage": max(0.0, overage),
            "breakdown": breakdown
        }
