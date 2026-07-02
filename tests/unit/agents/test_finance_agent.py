"""Tests for agents/finance_agent.py.

Covers:
    - Over budget logic (proposes cuts, scores drop)
    - Well under budget logic (proposes boosting utilization)
    - On budget / Near budget logic (accepts without changes)
    - Invalid dataset handling (scores 0, rejects, no changes)
    - Extreme over budget logic (score range bounded to 0)
"""

import pytest

from models.proposal import Proposal
from engine.state import create_initial_proposal
from tools.data_loader import DataLoader
from tools.cost_calculator import CostCalculator
from agents.finance_agent import FinanceAgent


# ── Mocks ───────────────────────────────────────────────────────────────────

class MockDataLoader(DataLoader):
    def __init__(self, city_index: float, should_fail: bool = False):
        self.city_index = city_index
        self.should_fail = should_fail

    def get_construction_costs(self, city_name: str) -> dict[str, float]:
        if self.should_fail:
            raise RuntimeError("Database connection lost.")
        return {"city_index": self.city_index}

    def get_reference_standards(self, filename: str) -> dict:
        """Return a minimal finance standards dict for testing."""
        return {
            "building_cost_benchmarks": {
                "residential_multifamily": {
                    "low_cost_per_sqft": 120,
                    "mid_cost_per_sqft": 200,
                    "high_cost_per_sqft": 320,
                    "unit": "USD per square foot",
                    "source": "RSMeans Construction Cost Data 2024"
                },
                "structured_parking": {
                    "low_cost_per_space": 15000,
                    "mid_cost_per_space": 25000,
                    "high_cost_per_space": 45000,
                    "unit": "USD per structured parking space",
                    "source": "RSMeans Construction Cost Data 2024"
                }
            },
            "parking_ratio_standards": {
                "residential_multifamily_urban": {
                    "min_spaces_per_unit": 0.5,
                    "typical_spaces_per_unit": 1.0,
                    "source": "ITE Parking Generation Manual, 5th Edition (2019)"
                }
            },
            "civic_amenity_roi": {
                "community_center": {
                    "property_value_uplift_pct": 5.0,
                    "payback_years_typical": 20,
                    "source": "Urban Land Institute (2022)"
                },
                "green_space": {
                    "property_value_uplift_pct_within_500ft": 8.0,
                    "source": "Trust for Public Land CityPark Score 2023"
                }
            },
            "affordability_benchmarks": {
                "affordable_unit_cost_subsidy_per_unit": {
                    "low": 30000,
                    "typical": 60000,
                    "high": 120000,
                    "source": "HUD Choice Neighborhoods 2022"
                }
            }
        }


class MockCostCalculator(CostCalculator):
    def __init__(self, city_index: float, should_fail: bool = False):
        self.data_loader = MockDataLoader(city_index, should_fail)

    def calculate_construction_cost(self, proposal: Proposal) -> float:
        if self.data_loader.should_fail:
            raise RuntimeError("Database connection lost.")
        
        # We simulate cost based on the budget limit to trigger different states
        # The test cases will set the budget_limit differently to trigger these states.
        # Let's say cost is always 50M.
        return 50_000_000.0


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def proposal_over_budget() -> Proposal:
    return create_initial_proposal(
        "phoenix_az",
        green_space_pct=30.0,
        housing_units=100,
        parking_spaces=200,
        budget_limit=40_000_000.0,  # 50M cost is over 40M limit
    )


@pytest.fixture
def proposal_well_under_budget() -> Proposal:
    return create_initial_proposal(
        "phoenix_az",
        housing_units=100,
        budget_limit=60_000_000.0,  # well under 60M limit
    )


@pytest.fixture
def proposal_near_budget() -> Proposal:
    return create_initial_proposal(
        "phoenix_az",
        housing_units=100,
        budget_limit=52_000_000.0,  # near 52M limit
    )


@pytest.fixture
def proposal_extreme_over_budget() -> Proposal:
    return create_initial_proposal(
        "phoenix_az",
        budget_limit=10_000_000.0,  # 5x over budget
    )


# ── Tests ───────────────────────────────────────────────────────────────────

class TestFinanceAgent:
    def test_agent_name(self) -> None:
        agent = FinanceAgent(MockCostCalculator(1.0))
        assert agent.agent_name == "finance"

    def test_over_budget_proposal(self, proposal_over_budget: Proposal) -> None:
        agent = FinanceAgent(MockCostCalculator(1.0)) # Local budget = 55M
        output = agent.evaluate(proposal_over_budget, {})
        
        # cost = 50M, limit = 40M
        # overrun = (50M - 40M) / 40M = 0.25
        # score = 100 - (0.25 * 100) = 75.0
        assert round(output.score, 1) == 75.0
        assert output.verdict == "modify"
        
        # Changes expected: green_space -> 20.0, housing -> 150, parking -> 160
        changes = output.proposed_changes
        assert "estimated_cost" not in changes
        assert changes["green_space_pct"] == 20.0
        assert changes["housing_units"] == 150
        assert changes["parking_spaces"] == 160
        
        assert "exceeds local budget limit" in output.reasoning_and_evidence

    def test_well_under_budget_proposal(self, proposal_well_under_budget: Proposal) -> None:
        agent = FinanceAgent(MockCostCalculator(1.0)) # Local budget = 50M
        output = agent.evaluate(proposal_well_under_budget, {})
        
        assert output.score == 90.0
        assert output.verdict == "modify"
        
        # Changes expected: housing_units -> +20
        changes = output.proposed_changes
        assert len(changes) == 1
        assert changes["housing_units"] == 120
        
        assert "well under the local budget limit" in output.reasoning_and_evidence

    def test_near_budget_proposal(self, proposal_near_budget: Proposal) -> None:
        agent = FinanceAgent(MockCostCalculator(1.0)) # Local budget = 50M
        output = agent.evaluate(proposal_near_budget, {})
        
        assert output.score == 95.0
        assert output.verdict == "accept"
        assert output.proposed_changes == {}
        assert "utilized efficiently" in output.reasoning_and_evidence

        # Data loader integration isn't used for calculated cost anymore in this mock,
        # but let's change budget limit directly to trigger modify
        proposal_near_budget.budget_limit = 40_000_000.0
        agent = FinanceAgent(MockCostCalculator(0.5))
        output = agent.evaluate(proposal_near_budget, {})
        
        assert output.verdict == "modify"
        assert "estimated_cost" not in output.proposed_changes
        assert output.proposed_changes["housing_units"] == 150

    def test_invalid_dataset_handling(self, proposal_near_budget: Proposal) -> None:
        agent = FinanceAgent(MockCostCalculator(1.0, should_fail=True))
        # Should crash during calculate_construction_cost
        with pytest.raises(RuntimeError):
            agent.evaluate(proposal_near_budget, {})


    def test_extreme_over_budget_score_bounding(self, proposal_extreme_over_budget: Proposal) -> None:
        """Test that the score does not drop below 0.0 when severely over budget."""
        agent = FinanceAgent(MockCostCalculator(1.0))
        output = agent.evaluate(proposal_extreme_over_budget, {})
        # overrun = 40M / 10M = 4.0
        # 100 - (4.0 * 100) = -300 -> max(0, -300) = 0.0
        assert output.score == 0.0
        assert output.verdict == "modify"

    def test_personality_and_risk_tolerance_in_system_instruction(self, proposal_near_budget: Proposal) -> None:
        """Verify personality_brief and risk_tolerance are defined, non-empty,
        and included in the system_instruction passed to the LLM provider."""
        from unittest.mock import MagicMock
        agent = FinanceAgent(MockCostCalculator(1.0))
        assert agent.personality_brief
        assert agent.risk_tolerance
        
        mock_provider = MagicMock()
        mock_provider.generate_structured.return_value = {
            "score": 95.0, "verdict": "accept", "proposed_changes": {},
            "tension": "Mock tension statement.",
            "position": "Pos", "reasoning": "Res", "evidence": [],
            "confidence": 0.9, "objections": [], "supports": []
        }
        agent.llm_provider = mock_provider
        
        agent.generate_opinion(proposal_near_budget, {})
        
        mock_provider.generate_structured.assert_called_once()
        _, kwargs = mock_provider.generate_structured.call_args
        sys_inst = kwargs["system_instruction"]
        assert agent.personality_brief in sys_inst
        assert agent.risk_tolerance in sys_inst

    def test_missing_tension_field_triggers_fallback(self, proposal_near_budget: Proposal) -> None:
        """Test that a mocked LLM response missing the required tension field triggers deterministic fallback."""
        from unittest.mock import MagicMock
        agent = FinanceAgent(MockCostCalculator(1.0))
        mock_provider = MagicMock()
        # Omit 'tension'
        mock_provider.generate_structured.return_value = {
            "score": 95.0, "verdict": "accept", "proposed_changes": {},
            "position": "Pos", "reasoning": "Res", "evidence": [],
            "confidence": 0.9, "objections": [], "supports": []
        }
        agent.llm_provider = mock_provider
        
        opinion = agent.generate_opinion(proposal_near_budget, {})
        assert "using deterministic fallback" in opinion.position


# ── Tests for get_cost_benchmarks tool ──────────────────────────────────

def test_get_cost_benchmarks_all_categories():
    """get_cost_benchmarks('all') returns all major categories."""
    agent = FinanceAgent(MockCostCalculator(1.0))
    result = agent.execute_tool_call("get_cost_benchmarks", {"category": "all"})
    assert "building_cost_benchmarks" in result
    assert "parking_ratio_standards" in result
    assert "civic_amenity_roi" in result
    assert "affordability_benchmarks" in result


def test_get_cost_benchmarks_building_costs():
    """get_cost_benchmarks returns RSMeans building cost data with correct numeric ranges."""
    agent = FinanceAgent(MockCostCalculator(1.0))
    result = agent.execute_tool_call("get_cost_benchmarks", {"category": "building_cost_benchmarks"})
    assert "building_cost_benchmarks" in result
    assert "parking_ratio_standards" not in result
    residential = result["building_cost_benchmarks"]["residential_multifamily"]
    assert residential["low_cost_per_sqft"] == 120
    assert residential["mid_cost_per_sqft"] == 200
    assert residential["high_cost_per_sqft"] == 320
    parking = result["building_cost_benchmarks"]["structured_parking"]
    assert parking["low_cost_per_space"] == 15000
    assert parking["mid_cost_per_space"] == 25000
    assert parking["high_cost_per_space"] == 45000


def test_get_cost_benchmarks_parking_ratios():
    """get_cost_benchmarks returns ITE parking ratio standards."""
    agent = FinanceAgent(MockCostCalculator(1.0))
    result = agent.execute_tool_call("get_cost_benchmarks", {"category": "parking_ratio_standards"})
    assert "parking_ratio_standards" in result
    ratios = result["parking_ratio_standards"]["residential_multifamily_urban"]
    assert ratios["min_spaces_per_unit"] == 0.5
    assert ratios["typical_spaces_per_unit"] == 1.0


def test_get_cost_benchmarks_civic_roi():
    """get_cost_benchmarks returns ULI green space and community center ROI data."""
    agent = FinanceAgent(MockCostCalculator(1.0))
    result = agent.execute_tool_call("get_cost_benchmarks", {"category": "civic_amenity_roi"})
    assert "civic_amenity_roi" in result
    green = result["civic_amenity_roi"]["green_space"]
    assert green["property_value_uplift_pct_within_500ft"] == 8.0
    community = result["civic_amenity_roi"]["community_center"]
    assert community["payback_years_typical"] == 20
