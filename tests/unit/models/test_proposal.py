import pytest
from pydantic import ValidationError
from models.proposal import Proposal

def test_proposal_creation():
    p = Proposal(
        city_slug="phoenix_az",
        green_space_pct=15.0,
        affordable_housing_pct=10.0,
        housing_units=200,
        parking_spaces=300,
        community_center_sqft=5000,
        
    )
    assert p.version == 1
    assert isinstance(p.proposal_id, str)
    assert p.agent_scores == {}
    assert p.human_locks == {}
    assert p.change_log == []

def test_proposal_out_of_bounds_creation_raises():
    with pytest.raises(ValidationError):
        Proposal(
            city_slug="phoenix_az",
            green_space_pct=105.0,  # invalid > 100
            affordable_housing_pct=10.0,
            housing_units=200,
            parking_spaces=300,
            community_center_sqft=5000,
            
        )

def test_proposal_validate_assignment_raises():
    p = Proposal(
        city_slug="phoenix_az",
        green_space_pct=15.0,
        affordable_housing_pct=10.0,
        housing_units=200,
        parking_spaces=300,
        community_center_sqft=5000,
        
    )
    with pytest.raises(ValidationError):
        p.housing_units = 500000  # invalid > 100000

