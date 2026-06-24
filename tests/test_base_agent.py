"""Tests for agents/base_agent.py — BaseAgent ABC.

Covers:
    - Concrete implementation instantiation
    - Valid output building
    - Invalid parameter validation (AgentValidationError)
    - Invalid score validation (AgentValidationError)
    - Invalid verdict validation (AgentValidationError)
    - Empty output handling
    - Unknown parameter filtering
"""

import pytest
from typing import Any

from models.proposal import Proposal
from models.agent_output import AgentOutput
from engine.state import create_initial_proposal
from agents.base_agent import BaseAgent, AgentValidationError, AgentExecutionError


# ── Mock Concrete Implementation ────────────────────────────────────────────

class MockAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "mock_agent"

    def evaluate(self, proposal: Proposal, context: dict[str, Any]) -> AgentOutput:
        # Not tested directly here, but required to instantiate
        raise AgentExecutionError("Not implemented")  # pragma: no cover


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def agent() -> MockAgent:
    return MockAgent()


# ── Tests ───────────────────────────────────────────────────────────────────

class TestBaseAgentValidation:
    def test_valid_output_building(self, agent: MockAgent) -> None:
        """Building output with valid parameters, score, and verdict should succeed."""
        output = agent.build_output(
            score=85.0,
            verdict="modify",
            changes={"green_space_pct": 25.0, "housing_units": 150},
            reasoning="Looks good but needs more green space."
        )
        assert isinstance(output, AgentOutput)
        assert output.agent_name == "mock_agent"
        assert output.score == 85.0
        assert output.verdict == "modify"
        assert output.proposed_changes == {"green_space_pct": 25.0, "housing_units": 150}

    def test_empty_output_building(self, agent: MockAgent) -> None:
        """Empty changes should be perfectly valid."""
        output = agent.build_output(
            score=100.0,
            verdict="accept",
            changes={},
            reasoning="Perfect proposal."
        )
        assert output.proposed_changes == {}
        assert output.verdict == "accept"

    def test_invalid_parameter_raises_error(self, agent: MockAgent) -> None:
        """Unknown parameter keys must raise AgentValidationError."""
        with pytest.raises(AgentValidationError, match="proposed unknown parameter 'laser_defense_grid'"):
            agent.validate_proposed_changes({"laser_defense_grid": 1.0})

        with pytest.raises(AgentValidationError):
            agent.build_output(
                score=50.0,
                verdict="modify",
                changes={"green_space_pct": 25.0, "invalid_field": 10.0},
                reasoning="Test"
            )

    def test_invalid_score_raises_error(self, agent: MockAgent) -> None:
        """Scores outside [0, 100] must raise AgentValidationError."""
        with pytest.raises(AgentValidationError, match="invalid score -5.0"):
            agent.validate_output(-5.0, "modify", {"green_space_pct": 30.0})

        with pytest.raises(AgentValidationError, match="invalid score 101.0"):
            agent.build_output(
                score=101.0,
                verdict="modify",
                changes={"green_space_pct": 30.0},
                reasoning="Test"
            )

    def test_invalid_verdict_raises_error(self, agent: MockAgent) -> None:
        """Verdicts other than accept/modify/reject must raise AgentValidationError."""
        with pytest.raises(AgentValidationError, match="invalid verdict 'maybe'"):
            agent.validate_output(50.0, "maybe", {"green_space_pct": 30.0})

        with pytest.raises(AgentValidationError):
            agent.build_output(
                score=50.0,
                verdict="UNKNOWN",
                changes={"green_space_pct": 30.0},
                reasoning="Test"
            )

    def test_filter_unknown_parameters(self, agent: MockAgent) -> None:
        """filter_unknown_parameters should strip invalid keys and keep valid ones."""
        raw_changes = {
            "green_space_pct": 30.0,
            "housing_units": 120,
            "alien_landing_pads": 5,
            "invalid_field": 10.0,
        }
        filtered = agent.filter_unknown_parameters(raw_changes)
        
        assert filtered == {"green_space_pct": 30.0, "housing_units": 120}
        
        # Ensure the filtered output passes validation
        agent.validate_proposed_changes(filtered)

from unittest.mock import MagicMock, patch
from llm.base import LLMProvider

class TestBaseAgentGenerateOpinion:
    def test_generate_opinion_success(self, agent: MockAgent) -> None:
        """Test that generate_opinion parses a valid LLM response."""
        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.generate_structured.return_value = {
            "score": 90.0,
            "verdict": "modify",
            "proposed_changes": {"green_space_pct": 30.0},
            "position": "Needs green space.",
            "reasoning": "Data shows this.",
            "evidence": ["Fact 1."],
            "objections": [],
            "supports": [],
            "confidence": 0.9,
            "text": "{...}"
        }
        agent.llm_provider = mock_provider
        
        proposal = create_initial_proposal("phoenix_az")
        opinion = agent.generate_opinion(proposal, {})
        
        assert opinion.score == 90.0
        assert opinion.recommendation == {"green_space_pct": 30.0}
        assert opinion.position == "Needs green space."

    def test_generate_opinion_function_calling(self) -> None:
        """Test that generate_opinion passes tool declarations and executor correctly."""
        # Override MockAgent for this test
        class ToolMockAgent(MockAgent):
            @property
            def tool_declarations(self):
                return [{"name": "get_weather"}]
            def execute_tool_call(self, name, args):
                if name == "get_weather": return {"temp": 110}
                raise NotImplementedError()
        
        agent = ToolMockAgent()
        mock_provider = MagicMock(spec=LLMProvider)
        
        def fake_generate_structured(system_instruction, user_prompt, tool_declarations, tool_executor, required_keys=None):
            # Simulate executing a tool call
            res = tool_executor("get_weather", {"city": "Phoenix"})
            assert res == {"temp": 110}
            return {
                "score": 80.0,
                "verdict": "accept",
                "proposed_changes": {},
                "position": "Position",
                "reasoning": "Reason",
                "evidence": [],
                "objections": [],
                "supports": [],
                "confidence": 0.8,
                "text": "{...}"
            }
            
        mock_provider.generate_structured.side_effect = fake_generate_structured
        agent.llm_provider = mock_provider
        
        proposal = create_initial_proposal("phoenix_az")
        opinion = agent.generate_opinion(proposal, {})
        
        assert opinion.score == 80.0
        assert mock_provider.generate_structured.call_count == 1

    def test_evidence_grounding_checks(self, agent: MockAgent) -> None:
        """Test evidence grounding check for grounded numbers, ungrounded numbers, percentages, and no numbers.
        
        Reasoning for no numbers: Qualitative or structural claims (e.g., 'The zoning is mixed residential') 
        do not contain numerical metrics but are valid qualitative evidence. Rejecting them would penalize 
        legitimate non-numeric factual observations, so we default to grounded=True.
        """
        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.generate_structured.return_value = {
            "score": 90.0,
            "verdict": "modify",
            "proposed_changes": {"green_space_pct": 30.0},
            "position": "Needs green space.",
            "reasoning": "Data shows this.",
            "evidence": [
                "Phoenix already runs 7°F hotter than surrounding rural areas.",  # grounded=True (matches 7)
                "The poverty rate is 17.2% in this sector.",  # grounded=True (matches 0.172 via percentage check)
                "The city population grew by 500000 residents.",  # grounded=False (500000 not in tool results)
                "The development zoning is purely mixed commercial and residential."  # grounded=True (no numbers)
            ],
            "objections": [],
            "supports": [],
            "confidence": 0.9,
            "text": "{...}",
            "tool_results": [
                {"name": "get_climate_data", "args": {}, "result": {"heat_diff": 7.0}},
                {"name": "get_demographics", "args": {}, "result": {"poverty_rate": 0.172}},
            ]
        }
        agent.llm_provider = mock_provider
        
        proposal = create_initial_proposal("phoenix_az")
        opinion = agent.generate_opinion(proposal, {})
        
        assert opinion.grounding_warnings == ["The city population grew by 500000 residents."]
