import pytest
from unittest.mock import patch, MagicMock
from engine.session import CourtroomSession
from models.proposal import Proposal
from models.debate_round import DebateRound
from models.agent_output import AgentOutput
from models.agent_opinion import AgentOpinion
from services.gemini_explainer import generate_judge_brief, generate_judge_brief_fallback


@pytest.fixture
def sample_session():
    proposal = Proposal(
        city_slug="phoenix_az",
        green_space_pct=10.0,
        affordable_housing_pct=15.0,
        housing_units=1000,
        parking_spaces=500,
        community_center_sqft=5000.0,
        
    )
    
    # Create an initial debate round to give opening_state
    round1 = DebateRound(
        round_number=1,
        opening_state=proposal.model_copy(deep=True),
        closing_state=proposal.model_copy(deep=True),
        agent_outputs={},
        detected_conflicts=[],
        engine_summary="",
    )
    
    # Final round where agents have opinions
    round2 = DebateRound(
        round_number=2,
        opening_state=proposal.model_copy(deep=True),
        closing_state=proposal.model_copy(deep=True),
        agent_outputs={},
        detected_conflicts=[],
        engine_summary="",
    )
    
    # Add opinions to trigger standards flags
    opinion_community = AgentOpinion(
        agent="community",
        score=85.0,
        recommendation={},
        tension="none",
        position="strong",
        reasoning="Because of HUD standard",
        confidence=0.9,
        standards_flags=[{
            "standard_name": "HUD Affordable Housing",
            "source_citation": "HUD/Furman Center",
            "proposal_value": "15.0%",
            "threshold": "10.0% minimum",
            "passed": True
        }]
    )
    round2.round_2_opinions = {"community": opinion_community}
    
    session = CourtroomSession(current_proposal=proposal)
    session.debate_rounds = [round1, round2]
    return session


def test_generate_judge_brief_fallback(sample_session):
    """Test that the fallback generator produces correctly formatted markdown."""
    fallback_text = generate_judge_brief_fallback(sample_session)
    
    assert "[DETERMINISTIC FALLBACK]" in fallback_text
    assert "Resolution Outcome" in fallback_text
    assert "Parameter Adjustments" in fallback_text
    assert "Standards & Compliance Flags" in fallback_text
    assert "HUD Affordable Housing" in fallback_text
    assert "Passed" in fallback_text


@patch("services.gemini_explainer.is_budget_exhausted")
def test_generate_judge_brief_budget_exhausted(mock_budget, sample_session):
    """Test that budget exhaustion triggers the fallback."""
    mock_budget.return_value = True
    
    result = generate_judge_brief(sample_session)
    assert "[DETERMINISTIC FALLBACK]" in result
    assert mock_budget.called


@patch("services.gemini_explainer.get_provider")
@patch("services.gemini_explainer.is_budget_exhausted")
def test_generate_judge_brief_exception_fallback(mock_budget, mock_get_provider, sample_session):
    """Test that an LLM API exception triggers the fallback."""
    mock_budget.return_value = False
    
    mock_provider = MagicMock()
    mock_provider.generate_text.side_effect = Exception("API error")
    mock_get_provider.return_value = mock_provider
    
    result = generate_judge_brief(sample_session)
    assert "[DETERMINISTIC FALLBACK]" in result
    assert mock_provider.generate_text.called
