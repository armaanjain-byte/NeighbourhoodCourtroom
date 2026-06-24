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

class MockDataLoader:
    def __init__(self, city_index: float, should_fail: bool = False):
        self.city_index = city_index
        self.should_fail = should_fail

    def get_construction_costs(self, city_name: str) -> dict[str, float]:
        if self.should_fail:
            raise RuntimeError("Database connection lost.")
        return {"city_index": self.city_index}


class MockCostCalculator(CostCalculator):
    def __init__(self, city_index: float, should_fail: bool = False):
        self.data_loader = MockDataLoader(city_index, should_fail)

    def calculate_estimated_cost(self, proposal: Proposal) -> float:
        # For testing, we just use the proposal's stored estimated_cost
        return proposal.estimated_cost


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def proposal_over_budget() -> Proposal:
    return create_initial_proposal(
        "phoenix_az",
        green_space_pct=30.0,
        housing_units=100,
        parking_spaces=200,
        estimated_cost=30_000_000.0,  # over 25M limit
    )


@pytest.fixture
def proposal_well_under_budget() -> Proposal:
    return create_initial_proposal(
        "phoenix_az",
        housing_units=100,
        estimated_cost=15_000_000.0,  # well under 25M limit
    )


@pytest.fixture
def proposal_near_budget() -> Proposal:
    return create_initial_proposal(
        "phoenix_az",
        housing_units=100,
        estimated_cost=24_000_000.0,  # near 25M limit (96%)
    )


@pytest.fixture
def proposal_extreme_over_budget() -> Proposal:
    return create_initial_proposal(
        "phoenix_az",
        estimated_cost=100_000_000.0,  # 4x over budget
    )


# ── Tests ───────────────────────────────────────────────────────────────────

class TestFinanceAgent:
    def test_agent_name(self) -> None:
        agent = FinanceAgent(MockCostCalculator(1.0))
        assert agent.agent_name == "finance"

    def test_over_budget_proposal(self, proposal_over_budget: Proposal) -> None:
        agent = FinanceAgent(MockCostCalculator(1.0)) # Local budget = 25M
        output = agent.evaluate(proposal_over_budget, {})
        
        # 30M / 25M = 1.2
        # score = 100 - (1.2 * 40) = 52.0
        assert output.score == 52.0
        assert output.verdict == "modify"
        
        # Changes expected: green_space -> 20.0, housing -> 150, parking -> 160
        changes = output.proposed_changes
        assert "estimated_cost" not in changes
        assert changes["green_space_pct"] == 20.0
        assert changes["housing_units"] == 150
        assert changes["parking_spaces"] == 160
        
        assert "exceeds local budget limit" in output.reasoning_and_evidence

    def test_well_under_budget_proposal(self, proposal_well_under_budget: Proposal) -> None:
        agent = FinanceAgent(MockCostCalculator(1.0)) # Local budget = 25M
        output = agent.evaluate(proposal_well_under_budget, {})
        
        assert output.score == 90.0
        assert output.verdict == "modify"
        
        # Changes expected: housing_units -> +20
        changes = output.proposed_changes
        assert len(changes) == 1
        assert changes["housing_units"] == 120
        
        assert "well under the local budget limit" in output.reasoning_and_evidence

    def test_near_budget_proposal(self, proposal_near_budget: Proposal) -> None:
        agent = FinanceAgent(MockCostCalculator(1.0)) # Local budget = 25M
        output = agent.evaluate(proposal_near_budget, {})
        
        assert output.score == 95.0
        assert output.verdict == "accept"
        assert output.proposed_changes == {}
        assert "utilized efficiently" in output.reasoning_and_evidence

    def test_data_loader_integration_city_index(self, proposal_near_budget: Proposal) -> None:
        # If city_index is 0.5, local budget is 12.5M.
        # The 24M proposal is now extremely over budget.
        agent = FinanceAgent(MockCostCalculator(0.5))
        output = agent.evaluate(proposal_near_budget, {})
        
        assert output.verdict == "modify"
        assert "estimated_cost" not in output.proposed_changes
        assert output.proposed_changes["housing_units"] == 150

    def test_invalid_dataset_handling(self, proposal_near_budget: Proposal) -> None:
        agent = FinanceAgent(MockCostCalculator(1.0, should_fail=True))
        output = agent.evaluate(proposal_near_budget, {})
        
        assert output.score == 0.0
        assert output.verdict == "reject"
        assert output.proposed_changes == {}
        assert "Failed to load cost data" in output.reasoning_and_evidence

    def test_extreme_over_budget_score_bounding(self, proposal_extreme_over_budget: Proposal) -> None:
        """Test that the score does not drop below 0.0 when severely over budget."""
        agent = FinanceAgent(MockCostCalculator(1.0))
        output = agent.evaluate(proposal_extreme_over_budget, {})
        
        # 100M / 25M = 4.0. 100 - (4.0 * 40) = -60.0. max(0.0, -60.0) = 0.0
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

