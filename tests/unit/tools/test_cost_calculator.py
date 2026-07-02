"""Tests for tools/cost_calculator.py."""

import pytest
from tools.cost_calculator import CostCalculator, CostBreakdown
from tools.data_loader import DataLoader
from models.proposal import Proposal
from engine.state import create_initial_proposal

@pytest.fixture
def data_loader() -> DataLoader:
    return DataLoader()

@pytest.fixture
def calculator(data_loader) -> CostCalculator:
    return CostCalculator(data_loader)

@pytest.fixture
def base_proposal() -> Proposal:
    return create_initial_proposal(
        "phoenix_az",
        housing_units=100,
        parking_spaces=200,
        green_space_pct=20.0,
        community_center_sqft=5000.0,
        affordable_housing_pct=10.0,
    )

class TestCostCalculator:
    def test_calculate_construction_cost(self, calculator: CostCalculator, data_loader: DataLoader, base_proposal: Proposal) -> None:
        city_data = data_loader.load_city("phoenix_az")
        breakdown = calculator.calculate_construction_cost(base_proposal, city_data)
        
        assert isinstance(breakdown, CostBreakdown)
        assert breakdown.residential_cost > 0
        assert breakdown.parking_cost > 0
        assert breakdown.total_estimated_cost > 0
        assert breakdown.soft_costs > 0

    def test_check_budget(self, calculator: CostCalculator, data_loader: DataLoader, base_proposal: Proposal) -> None:
        city_data = data_loader.load_city("phoenix_az")
        breakdown = calculator.calculate_construction_cost(base_proposal, city_data)
        budget_limit = breakdown.total_estimated_cost * 1.1 # Within budget
        
        result = calculator.check_budget(base_proposal, city_data, budget_limit)
        assert result["within_budget"] is True
        assert result["overage"] == 0.0
        
        budget_limit = breakdown.total_estimated_cost * 0.9 # Over budget
        result = calculator.check_budget(base_proposal, city_data, budget_limit)
        assert result["within_budget"] is False
        assert result["overage"] > 0.0
