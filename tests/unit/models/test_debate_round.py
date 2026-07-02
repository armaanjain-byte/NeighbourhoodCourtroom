import pytest
from models.debate_round import DebateRound
from models.proposal import Proposal
from models.agent_output import AgentOutput
from models.conflict import Conflict

def test_debate_round_creation():
    p = Proposal(
        city_slug="phoenix_az",
        green_space_pct=15.0,
        affordable_housing_pct=10.0,
        housing_units=200,
        parking_spaces=300,
        community_center_sqft=5000,
        
    )
    
    out = AgentOutput(
        agent_name="climate",
        score=85.5,
        verdict="modify",
        proposed_changes={"green_space_pct": 30.0},
        reasoning_and_evidence="..."
    )
    
    c = Conflict(
        parameter="green_space_pct",
        agent_a="finance",
        agent_b="climate",
        proposed_value_a=10.0,
        proposed_value_b=40.0,
        disagreement_severity="high"
    )

    p2 = p.model_copy()
    p2.version = 2
    
    dr = DebateRound(
        round_number=1,
        opening_state=p,
        agent_outputs={"climate": out},
        detected_conflicts=[c],
        closing_state=p2,
        engine_summary="Round complete."
    )
    assert dr.round_number == 1
    assert dr.opening_state.version == 1
    assert dr.closing_state.version == 2
