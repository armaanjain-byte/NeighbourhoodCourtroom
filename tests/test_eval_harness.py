import pytest
from tools.eval_harness import (
    calculate_evidence_grounding_rate,
    calculate_fallback_rate,
    calculate_budget_sanity,
    calculate_conflict_resolution_escalation,
    calculate_score_consistency
)
from engine.session import CourtroomSession
from models.proposal import Proposal
from models.courtroom_transcript import CourtroomTranscript, TranscriptEntry
from models.debate_round import DebateRound
from models.agent_opinion import AgentOpinion
from models.conflict import Conflict
from tools.data_loader import DataLoader
from tools.cost_calculator import CostCalculator

def test_evidence_grounding_rate():
    session = CourtroomSession(current_proposal=Proposal(city_slug="phoenix_az", affordable_housing_pct=10.0, estimated_cost=100.0, green_space_pct=10.0, parking_spaces=100, housing_units=100, community_center_sqft=100.0))
    session.transcript.entries = [
        TranscriptEntry(round_number=1, agent="community", statement_type="evidence", content="grounded 1", is_grounding_warning=False),
        TranscriptEntry(round_number=1, agent="community", statement_type="evidence", content="ungrounded", is_grounding_warning=True),
        TranscriptEntry(round_number=1, agent="finance", statement_type="evidence", content="grounded 2", is_grounding_warning=False),
        TranscriptEntry(round_number=1, agent="climate", statement_type="position", content="position", is_grounding_warning=False), # not evidence
    ]
    
    rate = calculate_evidence_grounding_rate([session])
    assert rate == (2 / 3) * 100.0

def test_fallback_rate():
    prop = Proposal(city_slug="phoenix_az", affordable_housing_pct=10.0, estimated_cost=100.0, green_space_pct=10.0, parking_spaces=100, housing_units=100, community_center_sqft=100.0)
    session = CourtroomSession(current_proposal=prop)
    
    op_normal = AgentOpinion(
        agent="community", score=90.0, recommendation={}, tension="", position="", reasoning="", confidence=0.8, is_fallback=False
    )
    op_fallback = AgentOpinion(
        agent="finance", score=90.0, recommendation={}, tension="", position="", reasoning="", confidence=0.8, is_fallback=True
    )
    
    round1 = DebateRound(
        round_number=1,
        detected_conflicts=[],
        round_1_opinions={"community": op_normal, "finance": op_fallback},
        engine_summary="",
        opening_state=prop,
        agent_outputs={},
        closing_state=prop
    )
    
    session.debate_rounds = [round1]
    
    rate = calculate_fallback_rate([session])
    assert rate == 50.0

from unittest.mock import patch

def test_budget_sanity():
    # Mock data loader and cost calculator
    dl = DataLoader()
    cc = CostCalculator(dl)
    
    with patch.object(dl, "get_construction_costs", return_value={"city_index": 1.0}), \
         patch.object(cc, "calculate_estimated_cost", side_effect=[50_000_000.0, 65_000_000.0]):
        
        s1 = CourtroomSession(current_proposal=Proposal(city_slug="test", affordable_housing_pct=10.0, estimated_cost=100.0, green_space_pct=10.0, parking_spaces=100, housing_units=100, community_center_sqft=100.0))
        s2 = CourtroomSession(current_proposal=Proposal(city_slug="test", affordable_housing_pct=10.0, estimated_cost=100.0, green_space_pct=10.0, parking_spaces=100, housing_units=100, community_center_sqft=100.0))
        
        rate = calculate_budget_sanity([s1, s2], dl, cc)
        assert rate == 50.0

def test_conflict_escalation():
    prop = Proposal(city_slug="phoenix_az", affordable_housing_pct=10.0, estimated_cost=100.0, green_space_pct=10.0, parking_spaces=100, housing_units=100, community_center_sqft=100.0)
    session = CourtroomSession(current_proposal=prop)
    c1 = Conflict(parameter="green_space_pct", agent_a="community", agent_b="finance", proposed_value_a=20.0, proposed_value_b=10.0, disagreement_severity="low")
    c2 = Conflict(parameter="affordable_housing_pct", agent_a="community", agent_b="finance", proposed_value_a=30.0, proposed_value_b=10.0, disagreement_severity="high")
    c3 = Conflict(parameter="housing_units", agent_a="community", agent_b="finance", proposed_value_a=200.0, proposed_value_b=100.0, disagreement_severity="medium")
    
    round1 = DebateRound(
        round_number=1,
        detected_conflicts=[c1, c2, c3],
        round_1_opinions={},
        engine_summary="",
        opening_state=prop,
        agent_outputs={},
        closing_state=prop
    )
    session.debate_rounds = [round1]
    
    res = calculate_conflict_resolution_escalation([session])
    assert res["escalated_pct"] == pytest.approx((1/3) * 100.0)
    assert res["resolved_pct"] == pytest.approx((2/3) * 100.0)

def test_score_consistency():
    prop_phx = Proposal(city_slug="phoenix_az", affordable_housing_pct=10.0, estimated_cost=100.0, green_space_pct=10.0, parking_spaces=100, housing_units=100, community_center_sqft=100.0)
    prop_det = Proposal(city_slug="detroit_mi", affordable_housing_pct=10.0, estimated_cost=100.0, green_space_pct=10.0, parking_spaces=100, housing_units=100, community_center_sqft=100.0)
    s1 = CourtroomSession(current_proposal=prop_phx)
    s2 = CourtroomSession(current_proposal=prop_phx)
    s3 = CourtroomSession(current_proposal=prop_det)
    
    op_phoenix_1 = AgentOpinion(agent="community", score=90.0, recommendation={}, tension="", position="", reasoning="", confidence=0.8)
    op_phoenix_2 = AgentOpinion(agent="community", score=70.0, recommendation={}, tension="", position="", reasoning="", confidence=0.8)
    op_detroit = AgentOpinion(agent="community", score=50.0, recommendation={}, tension="", position="", reasoning="", confidence=0.8)
    
    r1 = DebateRound(round_number=1, detected_conflicts=[], round_1_opinions={"c": op_phoenix_1}, engine_summary="", opening_state=prop_phx, agent_outputs={}, closing_state=prop_phx)
    r2 = DebateRound(round_number=1, detected_conflicts=[], round_1_opinions={"c": op_phoenix_2}, engine_summary="", opening_state=prop_phx, agent_outputs={}, closing_state=prop_phx)
    r3 = DebateRound(round_number=1, detected_conflicts=[], round_1_opinions={"c": op_detroit}, engine_summary="", opening_state=prop_det, agent_outputs={}, closing_state=prop_det)
    
    s1.debate_rounds = [r1]
    s2.debate_rounds = [r2]
    s3.debate_rounds = [r3]
    
    consistency = calculate_score_consistency([s1, s2, s3])
    import statistics
    expected_phoenix_stddev = statistics.stdev([90.0, 70.0])
    expected = (expected_phoenix_stddev + 0.0) / 2
    assert consistency == expected
