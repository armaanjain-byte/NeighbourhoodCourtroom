"""Tests for agents/climate_agent.py.

Covers:
    - Poor climate proposal (proposes boosting green space)
    - Strong climate proposal (accepts)
    - Low / High green space
    - Missing / Malformed dataset handling (rejects, scores 0)
    - Output validation
"""

import pytest

from models.proposal import Proposal
from engine.state import create_initial_proposal
from agents.climate_agent import ClimateAgent


# ── Mocks ───────────────────────────────────────────────────────────────────

class MockDataLoader:
    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail

    def get_climate(self, city_name: str) -> dict[str, float]:
        if self.should_fail:
            raise RuntimeError("Climate data corrupted.")
        return {"target_green_space_pct": 35.0}

    def get_land_use(self, city_name: str) -> dict[str, float]:
        if self.should_fail:
            raise RuntimeError("Land use data corrupted.")
        return {"max_parking_spaces": 150}


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def proposal_poor_climate() -> Proposal:
    return create_initial_proposal(
        "phoenix_az",
        green_space_pct=10.0,
        parking_spaces=300,
        community_center_sqft=2000.0,
    )


@pytest.fixture
def proposal_strong_climate() -> Proposal:
    return create_initial_proposal(
        "phoenix_az",
        green_space_pct=40.0,
        parking_spaces=100,
        community_center_sqft=5000.0,
    )


# ── Tests ───────────────────────────────────────────────────────────────────

class TestClimateAgent:
    def test_agent_name(self) -> None:
        agent = ClimateAgent(MockDataLoader())
        assert agent.agent_name == "climate"

    def test_poor_climate_proposal(self, proposal_poor_climate: Proposal) -> None:
        agent = ClimateAgent(MockDataLoader())
        output = agent.evaluate(proposal_poor_climate, {})
        
        # Target green space = 35.0. Actual = 10.0
        # green_ratio = 10.0 / 35.0 = 0.285
        # Max parking = 150. Actual = 300.
        # parking_ratio = 150 / 300 = 0.5
        # raw_score = (0.285 * 80) + (0.5 * 20) = 22.8 + 10 = 32.8
        
        assert output.score < 50.0
        assert output.verdict == "modify"
        
        # Expected changes:
        # green_space_pct min(10+10, 35) = 20.0
        # parking_spaces = 300 * 0.7 = 210
        # community_center_sqft = 2000 + 500 = 2500
        changes = output.proposed_changes
        assert changes["green_space_pct"] == 20.0
        assert changes["parking_spaces"] == 210
        assert changes["community_center_sqft"] == 2500.0
        
        assert "poor environmental resilience" in output.reasoning_and_evidence

    def test_strong_climate_proposal(self, proposal_strong_climate: Proposal) -> None:
        agent = ClimateAgent(MockDataLoader())
        output = agent.evaluate(proposal_strong_climate, {})
        
        # green_ratio = 40/35 = 1.14
        # parking_ratio = 150/100 = 1.5
        # score = 1.14*80 + 1.0*20 = 91.2 + 20 = 111.2 -> capped at 100.0
        
        assert output.score == 100.0
        assert output.verdict == "accept"
        assert output.proposed_changes == {}
        assert "meets environmental standards" in output.reasoning_and_evidence

    def test_low_green_space(self) -> None:
        agent = ClimateAgent(MockDataLoader())
        proposal = create_initial_proposal("phoenix_az", green_space_pct=5.0, parking_spaces=50)
        output = agent.evaluate(proposal, {})
        assert output.verdict == "modify"
        assert output.proposed_changes["green_space_pct"] == 15.0

    def test_high_green_space(self) -> None:
        agent = ClimateAgent(MockDataLoader())
        proposal = create_initial_proposal("phoenix_az", green_space_pct=50.0, parking_spaces=50)
        output = agent.evaluate(proposal, {})
        assert output.verdict == "accept"
        assert output.score == 100.0

    def test_missing_or_malformed_climate_data(self, proposal_strong_climate: Proposal) -> None:
        agent = ClimateAgent(MockDataLoader(should_fail=True))
        output = agent.evaluate(proposal_strong_climate, {})
        
        assert output.score == 0.0
        assert output.verdict == "reject"
        assert output.proposed_changes == {}
        assert "Failed to load climate/land_use data" in output.reasoning_and_evidence

    def test_personality_and_risk_tolerance_in_system_instruction(self, proposal_strong_climate: Proposal) -> None:
        """Verify personality_brief and risk_tolerance are defined, non-empty,
        and included in the system_instruction passed to the LLM provider."""
        from unittest.mock import MagicMock
        agent = ClimateAgent(MockDataLoader())
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
        
        agent.generate_opinion(proposal_strong_climate, {})
        
        mock_provider.generate_structured.assert_called_once()
        _, kwargs = mock_provider.generate_structured.call_args
        sys_inst = kwargs["system_instruction"]
        assert agent.personality_brief in sys_inst
        assert agent.risk_tolerance in sys_inst

    def test_missing_tension_field_triggers_fallback(self, proposal_strong_climate: Proposal) -> None:
        """Test that a mocked LLM response missing the required tension field triggers deterministic fallback."""
        from unittest.mock import MagicMock
        agent = ClimateAgent(MockDataLoader())
        mock_provider = MagicMock()
        # Omit 'tension'
        mock_provider.generate_structured.return_value = {
            "score": 95.0, "verdict": "accept", "proposed_changes": {},
            "position": "Pos", "reasoning": "Res", "evidence": [],
            "confidence": 0.9, "objections": [], "supports": []
        }
        agent.llm_provider = mock_provider
        
        opinion = agent.generate_opinion(proposal_strong_climate, {})
        assert "using deterministic fallback" in opinion.position

