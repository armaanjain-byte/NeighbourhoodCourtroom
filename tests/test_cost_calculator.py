"""Tests for tools/cost_calculator.py.

Covers:
    - baseline proposal cost
    - increased / reduced housing costs
    - increased green space / parking costs
    - cost delta between two proposals
    - missing dataset / malformed proposal fallbacks
"""

import pytest

from models.proposal import Proposal
from engine.state import create_initial_proposal
from tools.cost_calculator import CostCalculator
from tools.data_loader import CityNotFoundError


# ── Mocks ───────────────────────────────────────────────────────────────────

class MockDataLoader:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail

    def get_construction_costs(self, city_name: str) -> dict[str, float]:
        if self.should_fail:
            raise CityNotFoundError(f"Missing data for {city_name}")
        
        return {
            "city_index": 1.2,
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
        # Housing: 100 units * 100,000 (from mock) * 1.2 (index) = 12,000,000
        # Parking: 200 spaces * 25,000 (default) * 1.2 (index) = 6,000,000
        # Green Space: 20.0 * 500,000 (default) * 1.2 (index) = 12,000,000
        # Community: 5000 * 350 (default) * 1.2 = 2,100,000
        # Subtotal: 12M + 6M + 12M + 2.1M = 32,100,000
        # Soft costs (1.2): 32,100,000 * 0.2 = 6,420,000
        # Contingency (1.1): (32.1M + 6.42M) * 0.1 = 38,520,000 * 0.1 = 3,852,000
        # Total: 38,520,000 + 3,852,000 = 42,372,000
        
        assert breakdown["housing_cost"] == pytest.approx(12_000_000.0)
        assert breakdown["parking_cost"] == pytest.approx(6_000_000.0)
        assert breakdown["green_space_cost"] == pytest.approx(12_000_000.0)
        assert breakdown["community_center_cost"] == pytest.approx(2_100_000.0)
        assert breakdown["subtotal_hard_costs"] == pytest.approx(32_100_000.0)
        assert breakdown["soft_costs"] == pytest.approx(6_420_000.0)
        assert breakdown["contingency_costs"] == pytest.approx(3_852_000.0)
        assert breakdown["total_estimated_cost"] == pytest.approx(42_372_000.0)
        
        # calculate_estimated_cost matches the breakdown total
        assert calculator.calculate_estimated_cost(base_proposal) == pytest.approx(42_372_000.0)

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
