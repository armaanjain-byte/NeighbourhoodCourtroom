"""Tests for agents/community_agent.py.

Covers:
    - Poor community proposal (proposes boosting amenities, affordable housing)
    - Strong community proposal (accepts)
    - Low / High walkability impacts on score
    - Missing / Malformed dataset handling (rejects, scores 0)
    - Output validation
"""

import pytest
from typing import Any

from models.proposal import Proposal
from engine.state import create_initial_proposal
from tools.data_loader import DataLoader
from agents.community_agent import CommunityAgent


# ── Mocks ───────────────────────────────────────────────────────────────────

class MockDataLoader(DataLoader):
    def __init__(self, should_fail: bool = False, base_walkability: float = 50.0):
        self.should_fail = should_fail
        self.base_walkability = base_walkability
        self._cache = {}

    def get_demographics(self, city_name: str) -> dict[str, Any]:
        if self.should_fail:
            raise RuntimeError("Demographics data corrupted.")
        return {
            "target_community_center_sqft": 10000.0,
            "target_affordable_housing_pct": 20.0
        }

    def get_walkability(self, city_name: str) -> dict[str, float]:
        if self.should_fail:
            raise RuntimeError("Walkability data corrupted.")
        return {"walkability_score": self.base_walkability}

    def get_land_use(self, city_name: str) -> dict[str, float]:
        if self.should_fail:
            raise RuntimeError("Land use data corrupted.")
        return {"max_parking_spaces": 150}


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def proposal_poor_community() -> Proposal:
    # 0 sqft community center, 0% affordable housing, excessive housing
    return create_initial_proposal(
        "phoenix_az",
        community_center_sqft=0.0,
        affordable_housing_pct=0.0,
        housing_units=300, # Triggers density penalty
        parking_spaces=200, # Decreases walkability
        green_space_pct=10.0,
    )


@pytest.fixture
def proposal_strong_community() -> Proposal:
    # Meets all targets: 10000 sqft, 20% affordable, balanced housing/parking
    return create_initial_proposal(
        "phoenix_az",
        community_center_sqft=10000.0,
        affordable_housing_pct=20.0,
        housing_units=100,
        parking_spaces=100,
        green_space_pct=30.0,
    )


# ── Tests ───────────────────────────────────────────────────────────────────

class TestCommunityAgent:
    def test_agent_name(self) -> None:
        agent = CommunityAgent(MockDataLoader())
        assert agent.agent_name == "community"

    def test_poor_community_proposal(self, proposal_poor_community: Proposal) -> None:
        agent = CommunityAgent(MockDataLoader())
        output = agent.evaluate(proposal_poor_community, {})
        
        # community_ratio = 0
        # affordable_ratio = 0
        # base_walkability = 50. green = +5. parking = -20. effective = 35.0
        # raw_score = 0 + 0 + (35 * 0.3) - 15 (density penalty) = 10.5 - 15 = 0.0
        assert output.score < 50.0
        assert output.verdict == "modify"
        
        # Expected changes:
        # community_center_sqft min(0+2000, 10000) = 2000.0
        # affordable_housing_pct min(0+5, 20) = 5.0
        # parking_spaces max(0, 200 - 20) = 180
        # green_space_pct = 10.0 + 5.0 = 15.0
        changes = output.proposed_changes
        assert changes["community_center_sqft"] == 2000.0
        assert changes["affordable_housing_pct"] == 5.0
        assert changes["parking_spaces"] == 180
        assert changes["green_space_pct"] == 15.0
        
        assert "lacks adequate community amenities" in output.reasoning_and_evidence

    def test_strong_community_proposal(self, proposal_strong_community: Proposal) -> None:
        agent = CommunityAgent(MockDataLoader())
        output = agent.evaluate(proposal_strong_community, {})
        
        # community_ratio = 1.0 -> 40
        # affordable_ratio = 1.0 -> 30
        # base_walkability = 50. green = +15. parking = -10. effective = 55.0
        # raw_score = 40 + 30 + 16.5 = 86.5
        assert output.score >= 85.0
        assert output.verdict == "accept"
        assert output.proposed_changes == {}
        assert "supports a high quality of life" in output.reasoning_and_evidence

    def test_low_walkability(self, proposal_strong_community: Proposal) -> None:
        # Force low base walkability, causing score to drop below 85.0
        agent = CommunityAgent(MockDataLoader(base_walkability=10.0))
        output = agent.evaluate(proposal_strong_community, {})
        
        # effective = 10 + 15 - 10 = 15.0. 15 * 0.3 = 4.5. score = 40+30+4.5 = 74.5
        assert output.verdict == "modify"
        
        # Since verdict is modify, it should propose small walkability bumps
        changes = output.proposed_changes
        assert changes["green_space_pct"] == proposal_strong_community.green_space_pct + 5.0
        assert changes["parking_spaces"] == proposal_strong_community.parking_spaces - 20

    def test_high_walkability(self, proposal_strong_community: Proposal) -> None:
        # High base walkability ensures accept
        agent = CommunityAgent(MockDataLoader(base_walkability=100.0))
        output = agent.evaluate(proposal_strong_community, {})
        assert output.verdict == "accept"
        assert output.score > 90.0

    def test_missing_or_malformed_data(self, proposal_strong_community: Proposal) -> None:
        agent = CommunityAgent(MockDataLoader(should_fail=True))
        output = agent.evaluate(proposal_strong_community, {})
        
        assert output.score == 0.0
        assert output.verdict == "reject"
        assert output.proposed_changes == {}
        assert "Failed to load community-related data" in output.reasoning_and_evidence

    def test_personality_and_risk_tolerance_in_system_instruction(self, proposal_strong_community: Proposal) -> None:
        """Verify personality_brief and risk_tolerance are defined, non-empty,
        and included in the system_instruction passed to the LLM provider."""
        from unittest.mock import MagicMock
        agent = CommunityAgent(MockDataLoader())
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
        
        agent.generate_opinion(proposal_strong_community, {})
        
        mock_provider.generate_structured.assert_called_once()
        _, kwargs = mock_provider.generate_structured.call_args
        sys_inst = kwargs["system_instruction"]
        assert agent.personality_brief in sys_inst
        assert agent.risk_tolerance in sys_inst

    def test_missing_tension_field_triggers_fallback(self, proposal_strong_community: Proposal) -> None:
        """Test that a mocked LLM response missing the required tension field triggers deterministic fallback."""
        from unittest.mock import MagicMock
        agent = CommunityAgent(MockDataLoader())
        mock_provider = MagicMock()
        # Omit 'tension'
        mock_provider.generate_structured.return_value = {
            "score": 95.0, "verdict": "accept", "proposed_changes": {},
            "position": "Pos", "reasoning": "Res", "evidence": [],
            "confidence": 0.9, "objections": [], "supports": []
        }
        agent.llm_provider = mock_provider
        
        opinion = agent.generate_opinion(proposal_strong_community, {})
        assert "using deterministic fallback" in opinion.position

    def test_incremental_fallback_step(self) -> None:
        agent = CommunityAgent(MockDataLoader())
        proposal = create_initial_proposal("phoenix_az", community_center_sqft=5000.0, affordable_housing_pct=0.0)
        output = agent.evaluate(proposal, {})
        assert output.proposed_changes["community_center_sqft"] == 7000.0

    def test_incremental_fallback_close_to_target(self) -> None:
        agent = CommunityAgent(MockDataLoader())
        proposal = create_initial_proposal("phoenix_az", community_center_sqft=9000.0, affordable_housing_pct=0.0)
        output = agent.evaluate(proposal, {})
        assert output.proposed_changes["community_center_sqft"] == 10000.0

    def test_incremental_fallback_above_target(self) -> None:
        agent = CommunityAgent(MockDataLoader())
        proposal = create_initial_proposal("phoenix_az", community_center_sqft=15000.0, affordable_housing_pct=0.0)
        output = agent.evaluate(proposal, {})
        assert output.proposed_changes["community_center_sqft"] == 15000.0

    def test_budget_scale_back_logic(self) -> None:
        class ModeratelyOverBudgetMockLoader(MockDataLoader):
            def get_construction_costs(self, city_name: str) -> dict[str, Any]:
                return {
                    "city_index": 1.0,
                    "base_costs": {
                        "housing_unit": 250000.0, # 100 units = 25M
                        "community_center_sqft": 1250.0, # 2000 sqft = 2.5M
                    },
                    "soft_cost_multiplier": 1.0,
                    "contingency_multiplier": 1.0,
                }
        agent = CommunityAgent(ModeratelyOverBudgetMockLoader())
        proposal = create_initial_proposal("phoenix_az", community_center_sqft=0.0, affordable_housing_pct=15.0, housing_units=100, parking_spaces=0, green_space_pct=0.0)
        output = agent.evaluate(proposal, {})
        
        assert "scaled back to 25%" in output.reasoning_and_evidence
        assert output.proposed_changes["community_center_sqft"] == 500.0
        assert output.proposed_changes["affordable_housing_pct"] == 16.25

    def test_dramatically_over_budget_scale_back(self) -> None:
        class DramaticBudgetBustingMockLoader(MockDataLoader):
            def get_construction_costs(self, city_name: str) -> dict[str, Any]:
                return {
                    "city_index": 1.0,
                    "base_costs": {
                        "housing_unit": 400000.0, # 100 units = 40M (way over 25M budget!)
                    },
                    "soft_cost_multiplier": 1.0,
                    "contingency_multiplier": 1.0,
                }
        agent = CommunityAgent(DramaticBudgetBustingMockLoader())
        proposal = create_initial_proposal("phoenix_az", community_center_sqft=0.0, affordable_housing_pct=15.0, housing_units=100, parking_spaces=0, green_space_pct=0.0)
        output = agent.evaluate(proposal, {})
        
        assert "scaled back to 10%" in output.reasoning_and_evidence
        assert output.proposed_changes["community_center_sqft"] == 200.0
        assert output.proposed_changes["affordable_housing_pct"] == 15.5
