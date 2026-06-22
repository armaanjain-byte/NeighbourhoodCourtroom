import pytest
from models.proposal import Proposal

def test_proposal_creation():
    p = Proposal(
        city_slug="phoenix_az",
        green_space_pct=15.0,
        affordable_housing_pct=10.0,
        housing_units=200,
        parking_spaces=300,
        community_center_sqft=5000,
        estimated_cost=45000000.0
    )
    assert p.version == 1
    assert isinstance(p.proposal_id, str)
    assert p.agent_scores == {}
    assert p.human_locks == {}
    assert p.change_log == []
