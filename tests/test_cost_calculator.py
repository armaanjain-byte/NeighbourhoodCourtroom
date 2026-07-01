"""Tests for tools/cost_calculator.py.

Covers:
    - baseline proposal cost
    - increased / reduced housing costs
    - increased green space / parking costs
    - cost delta between two proposals
    - missing dataset / malformed proposal fallbacks
"""

import pytest
from typing import Any

from models.proposal import Proposal
from engine.state import create_initial_proposal
from tools.cost_calculator import CostCalculator
from tools.data_loader import DataLoader, CityNotFoundError


# ── Mocks ───────────────────────────────────────────────────────────────────

class MockDataLoader(DataLoader):
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self._cache = {}

    def get_construction_costs(self, city_name: str) -> dict[str, Any]:
        if self.should_fail:
            raise CityNotFoundError(f"Missing data for {city_name}")
        
        return {
            "city_index": 92.0,  # Ensure it scales properly (0.92 multiplier)
            "base_costs": {
                "housing_unit": 100000.0,
                # omitting parking and green_space to test default fallbacks
            },
            "soft_cost_multiplier": 1.2,
            "contingency_multiplier": 1.1,
        }


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def calculator() -> CostCalculator:
    return CostCalculator(MockDataLoader())


@pytest.fixture
def base_proposal() -> Proposal:
    return create_initial_proposal(
        "phoenix_az",
        housing_units=100,
        parking_spaces=200,
        green_space_pct=20.0,
        community_center_sqft=5000.0,
    )


# ── Tests ───────────────────────────────────────────────────────────────────

class TestCostCalculator:
    def test_baseline_proposal(self, calculator: CostCalculator, base_proposal: Proposal) -> None:
        breakdown = calculator.calculate_cost_breakdown(base_proposal)
        
        # Test calculations:
        # Housing: 100 units * 100,000 (from mock) * 0.92 (index) = 9,200,000
        # Parking: 200 spaces * 25,000 (default) * 0.92 (index) = 4,600,000
        # Green Space: 20.0 * 500,000 (default) * 0.92 (index) = 9,200,000
        # Community: 5000 * 350 (default) * 0.92 = 1,610,000
        # Subtotal: 9.2M + 4.6M + 9.2M + 1.61M = 24,610,000
        # Soft costs (1.2): 24,610,000 * 0.2 = 4,922,000
        # Contingency (1.1): (24.61M + 4.922M) * 0.1 = 29,532,000 * 0.1 = 2,953,200
        # Total: 29,532,000 + 2,953,200 = 32,485,200
        
        assert breakdown["housing_cost"] == pytest.approx(9_200_000.0)
        assert breakdown["parking_cost"] == pytest.approx(4_600_000.0)
        assert breakdown["green_space_cost"] == pytest.approx(9_200_000.0)
        assert breakdown["community_center_cost"] == pytest.approx(1_610_000.0)
        assert breakdown["subtotal_hard_costs"] == pytest.approx(24_610_000.0)
        assert breakdown["soft_costs"] == pytest.approx(4_922_000.0)
        assert breakdown["contingency_costs"] == pytest.approx(2_953_200.0)
        assert breakdown["total_estimated_cost"] == pytest.approx(32_485_200.0)
        
        # calculate_estimated_cost matches the breakdown total
        assert calculator.calculate_estimated_cost(base_proposal) == pytest.approx(32_485_200.0)

    def test_increased_housing(self, calculator: CostCalculator, base_proposal: Proposal) -> None:
        increased_housing = base_proposal.model_copy(update={"housing_units": 150})
        old_cost = calculator.calculate_estimated_cost(base_proposal)
        new_cost = calculator.calculate_estimated_cost(increased_housing)
        
        assert new_cost > old_cost
        delta = calculator.calculate_cost_delta(base_proposal, increased_housing)
        assert delta == new_cost - old_cost

    def test_reduced_housing(self, calculator: CostCalculator, base_proposal: Proposal) -> None:
        reduced_housing = base_proposal.model_copy(update={"housing_units": 50})
        old_cost = calculator.calculate_estimated_cost(base_proposal)
        new_cost = calculator.calculate_estimated_cost(reduced_housing)
        
        assert new_cost < old_cost
        assert calculator.calculate_cost_delta(base_proposal, reduced_housing) < 0.0

    def test_increased_green_space(self, calculator: CostCalculator, base_proposal: Proposal) -> None:
        more_green = base_proposal.model_copy(update={"green_space_pct": 30.0})
        assert calculator.calculate_estimated_cost(more_green) > calculator.calculate_estimated_cost(base_proposal)

    def test_increased_parking(self, calculator: CostCalculator, base_proposal: Proposal) -> None:
        more_parking = base_proposal.model_copy(update={"parking_spaces": 300})
        assert calculator.calculate_estimated_cost(more_parking) > calculator.calculate_estimated_cost(base_proposal)

    def test_missing_cost_data(self, base_proposal: Proposal) -> None:
        calc_fail = CostCalculator(MockDataLoader(should_fail=True))
        breakdown = calc_fail.calculate_cost_breakdown(base_proposal)
        
        # Fallback values: index 1.0, soft 1.1, cont 1.1
        # Housing: 100 * 150,000 = 15,000,000
        # Parking: 200 * 25,000 = 5,000,000
        # Green Space: 20.0 * 500,000 = 10,000,000
        # Community: 5000 * 350 = 1,750,000
        # Subtotal: 31,750,000
        # Soft: 3,175,000
        # Cont: (31.75M + 3.175M) * 0.1 = 34,925,000 * 0.1 = 3,492,500
        # Total: 34,925,000 + 3,492,500 = 38,417,500
        assert breakdown["housing_cost"] == pytest.approx(15_000_000.0)
        assert breakdown["total_estimated_cost"] == pytest.approx(38_417_500.0)

    def test_city_index_normalization_large_value(self, base_proposal: Proposal) -> None:
        # Test that city_index > 10.0 is divided by 100
        class MockLargeIndexLoader(DataLoader):
            def get_construction_costs(self, city_name: str) -> dict[str, Any]:
                return {"city_index": 120.0, "base_costs": {"housing_unit": 100000.0}}
        calc = CostCalculator(MockLargeIndexLoader())
        breakdown = calc.calculate_cost_breakdown(base_proposal)
        # 120.0 should become 1.2. 100 units * 100k * 1.2 = 12M
        assert breakdown["housing_cost"] == pytest.approx(12_000_000.0)

    def test_city_index_normalization_small_value(self, base_proposal: Proposal) -> None:
        # Test that city_index <= 10.0 is NOT divided by 100
        class MockSmallIndexLoader(DataLoader):
            def get_construction_costs(self, city_name: str) -> dict[str, Any]:
                return {"city_index": 1.2, "base_costs": {"housing_unit": 100000.0}}
        calc = CostCalculator(MockSmallIndexLoader())
        breakdown = calc.calculate_cost_breakdown(base_proposal)
        # 1.2 should stay 1.2. 100 units * 100k * 1.2 = 12M
        assert breakdown["housing_cost"] == pytest.approx(12_000_000.0)

    def test_real_city_calculation(self, base_proposal: Proposal) -> None:
        # Use real DataLoader against data/construction_costs.json
        loader = DataLoader()
        calc = CostCalculator(loader)
        
        # Override proposal to detroit_mi
        detroit_proposal = base_proposal.model_copy(update={"city_slug": "detroit_mi"})
        breakdown = calc.calculate_cost_breakdown(detroit_proposal)
        
        # From JSON for detroit_mi:
        # city_index: 105.0 -> 1.05
        # residential_cost_per_sqft: 210 -> housing_unit = 210,000
        # parking_cost_per_space: 25000
        # green_space_cost_per_sqft: 12 -> 500,000 * (12 / 15.0) = 400,000
        # commercial_cost_per_sqft: 280
        # 
        # base_proposal has:
        # housing_units = 100
        # parking_spaces = 200
        # green_space_pct = 20.0
        # community_center_sqft = 5000.0
        # 
        # Housing: 100 * 210,000 * 1.05 = 22,050,000
        # Parking: 200 * 25,000 * 1.05 = 5,250,000
        # Green: 20.0 * 400,000 * 1.05 = 8,400,000
        # Community: 5000 * 280 * 1.05 = 1,470,000
        
        assert breakdown["housing_cost"] == pytest.approx(22_050_000.0)
        assert breakdown["parking_cost"] == pytest.approx(5_250_000.0)
        assert breakdown["green_space_cost"] == pytest.approx(8_400_000.0)
        assert breakdown["community_center_cost"] == pytest.approx(1_470_000.0)
