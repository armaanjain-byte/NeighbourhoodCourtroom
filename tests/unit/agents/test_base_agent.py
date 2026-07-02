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
from pydantic import ValidationError
from typing import Any

from models.proposal import Proposal
from models.agent_output import AgentOutput
from models.agent_opinion import AgentOpinion, TargetStatement
from engine.state import create_initial_proposal
from agents.base_agent import BaseAgent, AgentValidationError, AgentExecutionError


# ── Mock Concrete Implementation ────────────────────────────────────────────

class MockAgent(BaseAgent):
    @property
    def agent_name(self) -> str:
        return "mock_agent"

    @property
    def personality_brief(self) -> str:
        return "Mock personality brief."

    @property
    def risk_tolerance(self) -> str:
        return "mock risk tolerance"

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
    def test_target_statement_requires_engages_with(self) -> None:
        with pytest.raises(ValidationError):
            TargetStatement(target_agent="finance", reason="Generic disagreement")

    def test_generate_opinion_success(self, agent: MockAgent) -> None:
        """Test that generate_opinion parses a valid LLM response."""
        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.generate_structured.return_value = {
            "score": 90.0,
            "verdict": "modify",
            "proposed_changes": {"green_space_pct": 30.0},
            "tension": "Mock tension statement.",
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
        assert opinion.tension == "Mock tension statement."
        assert opinion.position == "Needs green space."

    def test_round_2_objections_capture_engagement_and_flag_superficial_references(
        self, agent: MockAgent
    ) -> None:
        """Round 2 keeps weak objections but identifies number-only engagement."""
        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.generate_structured.return_value = {
            "score": 75.0,
            "verdict": "modify",
            "proposed_changes": {"green_space_pct": 35.0},
            "tension": "More park space competes with housing capacity.",
            "position": "Protect enough park space to keep residents cool.",
            "reasoning": "Heat exposure outweighs the modest capacity tradeoff.",
            "evidence": [],
            "objections": [
                {
                    "target_agent": "finance",
                    "engages_with": "park maintenance would strain the operating budget",
                    "reason": "The avoided heat costs outweigh that recurring expense.",
                },
                {
                    "target_agent": "finance",
                    "engages_with": "green_space_pct 30",
                    "reason": "That amount is too low.",
                },
                {
                    "target_agent": "finance",
                    "engages_with": "",
                    "reason": "The recommendation is unconvincing.",
                },
            ],
            "supports": [
                {
                    "target_agent": "finance",
                    "engages_with": "construction costs must remain manageable",
                    "reason": "Phasing the park work supports that concern.",
                }
            ],
            "confidence": 0.8,
        }
        agent.llm_provider = mock_provider
        opponent = AgentOpinion(
            agent="finance",
            score=60.0,
            recommendation={"green_space_pct": 30.0},
            tension="Parks have an operating cost.",
            position="Keep park spending controlled.",
            reasoning="Park maintenance would strain the operating budget.",
            evidence=["Annual maintenance costs rise with additional park acreage."],
            confidence=0.8,
        )

        opinion = agent.generate_opinion(
            create_initial_proposal("phoenix_az"),
            {},
            round_number=2,
            opponent_opinions={"finance": opponent},
        )

        assert opinion.objections[0].engages_with == (
            "park maintenance would strain the operating budget"
        )
        assert opinion.supports[0].engages_with == (
            "construction costs must remain manageable"
        )
        assert opinion.engagement_warnings == [
            "finance:green_space_pct 30",
            "finance:",
        ]
        prompt = mock_provider.generate_structured.call_args.kwargs["user_prompt"]
        assert "For each objection, you MUST first quote or closely paraphrase" in prompt
        assert "Annual maintenance costs rise" in prompt

    def test_missing_tension_field_triggers_fallback(self, agent: MockAgent) -> None:
        """Test that a mocked LLM response missing the required tension field triggers deterministic fallback."""
        mock_provider = MagicMock(spec=LLMProvider)
        # Omit 'tension' from the response dictionary
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
        
        # We need evaluate() to return a valid AgentOutput for the fallback path
        with patch.object(agent, 'evaluate') as mock_eval:
            mock_eval.return_value = agent.build_output(score=50.0, verdict="modify", changes={"green_space_pct": 21.0}, reasoning="Fallback")
            proposal = create_initial_proposal("phoenix_az")
            opinion = agent.generate_opinion(proposal, {})
            
            # Verify fallback was triggered
            assert opinion.is_fallback is True
            assert opinion.score == 50.0

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
                "tension": "Mock tension statement.",
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
            "tension": "Mock tension statement.",
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

    def test_concession_rationale_required_when_changed(self, agent: MockAgent) -> None:
        """Test concession_rationale is required when proposed_changes differs from previous position."""
        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.generate_structured.return_value = {
            "score": 85.0,
            "verdict": "modify",
            "proposed_changes": {"green_space_pct": 25.0},
            "tension": "Mock tension.",
            "position": "Lower green space.",
            "reasoning": "Budget constraint.",
            "evidence": [],
            "objections": [],
            "supports": [],
            "confidence": 0.9,
        }
        agent.llm_provider = mock_provider
        
        prev_opinion = AgentOpinion(
            agent="mock_agent",
            score=90.0,
            recommendation={"green_space_pct": 35.0},
            tension="Previous tension.",
            position="High green space.",
            reasoning="Heat island effect.",
            confidence=0.9,
        )
        
        # Omitting concession_rationale when position changed triggers fallback
        with patch.object(agent, 'evaluate') as mock_eval:
            mock_eval.return_value = agent.build_output(score=50.0, verdict="modify", changes={"green_space_pct": 21.0}, reasoning="Fallback")
            proposal = create_initial_proposal("phoenix_az")
            op_fallback = agent.generate_opinion(proposal, {}, round_number=2, own_previous_opinion=prev_opinion)
            assert op_fallback.is_fallback is True

        # Providing concession_rationale succeeds
        mock_provider.generate_structured.return_value["concession_rationale"] = "Trading green space for budget."
        op_success = agent.generate_opinion(proposal, {}, round_number=2, own_previous_opinion=prev_opinion)
        assert op_success.concession_rationale == "Trading green space for budget."
        assert op_success.own_previous_position == {"green_space_pct": 35.0}

    def test_concession_rationale_optional_when_unchanged(self, agent: MockAgent) -> None:
        """Test concession_rationale is optional when proposed_changes matches previous position."""
        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.generate_structured.return_value = {
            "score": 90.0,
            "verdict": "modify",
            "proposed_changes": {"green_space_pct": 35.0},
            "tension": "Mock tension.",
            "position": "Holding firm on green space.",
            "reasoning": "Heat island effect remains critical.",
            "evidence": [],
            "objections": [],
            "supports": [],
            "confidence": 0.9,
        }
        agent.llm_provider = mock_provider
        
        prev_opinion = AgentOpinion(
            agent="mock_agent",
            score=90.0,
            recommendation={"green_space_pct": 35.0},
            tension="Previous tension.",
            position="High green space.",
            reasoning="Heat island effect.",
            confidence=0.9,
        )
        
        proposal = create_initial_proposal("phoenix_az")
        op_success = agent.generate_opinion(proposal, {}, round_number=2, own_previous_opinion=prev_opinion)
        assert op_success.concession_rationale is None
        assert op_success.own_previous_position == {"green_space_pct": 35.0}

    def test_fallback_position_never_contains_raw_exception_text(self, agent: MockAgent) -> None:
        """Test that LLM exceptions trigger fallback without leaking raw exception text to UI."""
        from llm.base import LLMRateLimitError, LLMAuthError, LLMTransientError, LLMInvalidResponseError
        
        proposal = create_initial_proposal("phoenix_az")
        raw_error_msg = '{"error": {"message": "Out of quota / raw JSON stack trace leak"}}'
        
        errors = [
            LLMRateLimitError(raw_error_msg),
            LLMAuthError(raw_error_msg),
            LLMTransientError(raw_error_msg),
            LLMInvalidResponseError(raw_error_msg),
            Exception(raw_error_msg),
        ]
        
        for exc in errors:
            mock_provider = MagicMock(spec=LLMProvider)
            mock_provider.generate_structured.side_effect = exc
            agent.llm_provider = mock_provider
            
            with patch.object(agent, 'evaluate') as mock_eval:
                mock_eval.return_value = agent.build_output(score=50.0, verdict="modify", changes={"green_space_pct": 21.0}, reasoning="Fallback")
                opinion = agent.generate_opinion(proposal, {})
                
                assert opinion.is_fallback is True
                assert raw_error_msg not in opinion.position
                assert raw_error_msg not in opinion.reasoning

    def test_fallback_opinion_respects_human_locks(self, agent: MockAgent) -> None:
        """Test that fallback deterministic evaluate omits locked parameters from proposed_changes."""
        proposal = create_initial_proposal("phoenix_az")
        proposal.human_locks = {"green_space_pct": 20.0}
        
        # Force a fallback by raising an exception
        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.generate_structured.side_effect = Exception("force fallback")
        agent.llm_provider = mock_provider
        
        with patch.object(agent, 'evaluate') as mock_eval:
            # Mock evaluate to propose changes to a locked parameter and an unlocked parameter
            mock_eval.return_value = agent.build_output(
                score=50.0, 
                verdict="modify", 
                changes={"green_space_pct": 25.0, "housing_units": 200}, 
                reasoning="Fallback reasoning"
            )
            opinion = agent.generate_opinion(proposal, {})
            
            assert opinion.is_fallback is True
            # The locked parameter should be dropped from recommendation
            assert "green_space_pct" not in opinion.recommendation
            assert opinion.recommendation["housing_units"] == 200
            
            # The reasoning should mention the omission
            assert "Note: Proposed changes to Green Space were omitted because they are locked by the human judge." in opinion.reasoning

    def test_fallback_round_2_structured_response(self) -> None:
        """Round 2 fallback uses structured opponent-response logic, not random deadlock-breaking.

        The new fallback (Du et al. 2024) produces a domain-specific response to opponent
        proposals.  It should produce a different position string from Round 1 and set
        is_fallback=True.
        """
        from agents.finance_agent import FinanceAgent
        from tools.cost_calculator import CostCalculator
        from tools.data_loader import DataLoader

        agent = FinanceAgent(CostCalculator(DataLoader(skip_validation=True)))
        context = {"budget_limit": 25_000_000.0}
        proposal = create_initial_proposal("phoenix_az", green_space_pct=10.0, housing_units=100)

        own_opinion = AgentOpinion(
            agent=agent.agent_name,
            score=80.0,
            recommendation={"green_space_pct": 10.0},
            tension="Tension",
            position="Round 1 position",
            reasoning="Reasoning",
            evidence=[], objections=[], supports=[],
            confidence=0.8,
        )

        opp_opinion = AgentOpinion(
            agent="climate",
            score=50.0,
            recommendation={"green_space_pct": 20.0},
            tension="Tension",
            position="Need green space",
            reasoning="Reasoning",
            evidence=[], objections=[], supports=[],
            confidence=0.8,
        )

        # Run Round 1 fallback
        r1_opinion = agent._fallback_opinion(
            proposal, context,
            round_number=1,
            opponent_opinions=None,
            own_previous_opinion=None,
            reason="test",
        )

        # Run Round 2 fallback with opponent opinion
        r2_opinion = agent._fallback_opinion(
            proposal, context,
            round_number=2,
            opponent_opinions={"climate": opp_opinion},
            own_previous_opinion=own_opinion,
            reason="test",
        )

        # The fallback should have fired and produced an is_fallback opinion
        assert r1_opinion.is_fallback is True
        assert r2_opinion.is_fallback is True
        # Round 2 position must differ from Round 1
        assert r2_opinion.position != r1_opinion.position



