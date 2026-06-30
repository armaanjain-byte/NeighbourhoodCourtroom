import pytest
from engine.summary import generate_plain_language_summary
from engine.state import create_initial_proposal
from models.proposal import Proposal
from engine.session import create_session
from models.debate_round import DebateRound
from models.conflict import Conflict
from models.agent_output import AgentOutput

def test_summary_no_changes():
    proposal = create_initial_proposal(city_slug="test")
    session = create_session(proposal)
    rnd = DebateRound(
        round_number=1,
        opening_state=proposal,
        closing_state=proposal,
        detected_conflicts=[],
        agent_outputs={
            "finance": AgentOutput(agent_name="finance", score=90, verdict="accept", proposed_changes={}, reasoning_and_evidence="ok", confidence=0.9),
            "climate": AgentOutput(agent_name="climate", score=95, verdict="accept", proposed_changes={}, reasoning_and_evidence="ok", confidence=0.9),
            "community": AgentOutput(agent_name="community", score=92, verdict="accept", proposed_changes={}, reasoning_and_evidence="ok", confidence=0.9),
        },
        engine_summary="ok"
    )
    session.debate_rounds.append(rnd)
    
    summary = generate_plain_language_summary(session)
    assert summary["outcome"] == "All parameters were successfully resolved by the agents without requiring your input."
    assert summary["changes"] == "The agents accepted your original proposal without any modifications."
    assert "90/100" in summary["finance_score"]
    assert "95/100" in summary["climate_score"]
    assert "92/100" in summary["community_score"]
    
def test_summary_with_changes():
    proposal1 = create_initial_proposal(city_slug="test", green_space_pct=20.0, affordable_housing_pct=15.0, housing_units=100, parking_spaces=150, community_center_sqft=5000.0, estimated_cost=25_000_000.0)
    proposal2 = create_initial_proposal(city_slug="test", green_space_pct=25.0, affordable_housing_pct=20.0, housing_units=90, parking_spaces=120, community_center_sqft=6000.0, estimated_cost=26_000_000.0)
    proposal2.version = 2
    session = create_session(proposal1)
    session.current_proposal = proposal2
    rnd = DebateRound(
        round_number=1,
        opening_state=proposal1,
        closing_state=proposal2,
        detected_conflicts=[],
        agent_outputs={
            "finance": AgentOutput(agent_name="finance", score=80, verdict="accept", proposed_changes={}, reasoning_and_evidence="ok", confidence=0.9),
            "climate": AgentOutput(agent_name="climate", score=90, verdict="accept", proposed_changes={}, reasoning_and_evidence="ok", confidence=0.9),
            "community": AgentOutput(agent_name="community", score=95, verdict="accept", proposed_changes={}, reasoning_and_evidence="ok", confidence=0.9),
        },
        engine_summary="ok"
    )
    session.debate_rounds.append(rnd)
    
    summary = generate_plain_language_summary(session)
    assert "All parameters were successfully resolved" in summary["outcome"]
    assert "Green space increased from 20.0% to 25.0%" in summary["changes"]
    assert "Affordable housing increased from 15.0% to 20.0%" in summary["changes"]
    assert "Housing density was reduced from 100 to 90" in summary["changes"]
    assert "Parking was reduced from 150 to 120" in summary["changes"]
    assert "The budget increased from $25,000,000 to $26,000,000" in summary["changes"]
    
    assert "the final budget increased by $1,000,000" in summary["finance_score"]
    assert "green space was expanded to 25.0%" in summary["climate_score"]
    assert "both affordable housing and community center space were expanded" in summary["community_score"]

def test_summary_with_override():
    proposal = create_initial_proposal(city_slug="test")
    session = create_session(proposal)
    session.override_history.append({"parameter": "green_space_pct", "value": 30.0})
    
    summary = generate_plain_language_summary(session)
    assert "You stepped in and applied 1 manual override" in summary["outcome"]

def test_summary_with_escalation():
    proposal = create_initial_proposal(city_slug="test")
    session = create_session(proposal)
    
    rnd = DebateRound(
        round_number=1,
        opening_state=proposal,
        closing_state=proposal,
        detected_conflicts=[Conflict(parameter="green_space_pct", agent_a="climate", agent_b="finance", proposed_value_a=30.0, proposed_value_b=10.0, disagreement_severity="high", reason="very far apart")],
        agent_outputs={},
        engine_summary="ok"
    )
    session.debate_rounds.append(rnd)
    
    summary = generate_plain_language_summary(session)
    assert "escalated 1 to your review" in summary["outcome"]
