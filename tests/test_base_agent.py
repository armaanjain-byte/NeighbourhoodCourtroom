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
