import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from models.proposal import Proposal

def test_proposal_valid():
    dt = datetime.now(timezone.utc)
    p = Proposal(
        proposal_id="p1",
        agent_name="finance",
        title="Valid Title",
        description="A good proposal",
        category="transit",
        cost_delta=-500.5,
        impact_score=85.0,
        status="proposed",
        created_at=dt
    )
    assert p.proposal_id == "p1"
    assert p.cost_delta == -500.5
    assert p.impact_score == 85.0

def test_proposal_invalid_title():
    with pytest.raises(ValidationError):
        Proposal(
            proposal_id="p2",
            agent_name="finance",
            title="",
            description="A good proposal",
            category="transit",
            cost_delta=100.0,
            impact_score=85.0,
            status="proposed",
            created_at=datetime.now(timezone.utc)
        )

def test_proposal_invalid_impact_score():
    # Over 100
    with pytest.raises(ValidationError):
        Proposal(
            proposal_id="p3",
            agent_name="finance",
            title="Title",
            description="Desc",
            category="transit",
            cost_delta=100.0,
            impact_score=105.0,
            status="proposed",
            created_at=datetime.now(timezone.utc)
        )
    # Under 0
    with pytest.raises(ValidationError):
        Proposal(
            proposal_id="p4",
            agent_name="finance",
            title="Title",
            description="Desc",
            category="transit",
            cost_delta=100.0,
            impact_score=-1.0,
            status="proposed",
            created_at=datetime.now(timezone.utc)
        )

def test_proposal_invalid_status():
    with pytest.raises(ValidationError):
        Proposal(
            proposal_id="p5",
            agent_name="finance",
            title="Title",
            description="Desc",
            category="transit",
            cost_delta=100.0,
            impact_score=50.0,
            status="unknown",  # type: ignore
            created_at=datetime.now(timezone.utc)
        )

def test_proposal_serialization():
    dt = datetime.now(timezone.utc)
    p = Proposal(
        proposal_id="p1",
        agent_name="finance",
        title="Valid Title",
        description="A good proposal",
        category="transit",
        cost_delta=100.0,
        impact_score=50.0,
        status="accepted",
        created_at=dt
    )
    dumped = p.model_dump()
    assert dumped["title"] == "Valid Title"
    
    json_dumped = p.model_dump_json()
    p2 = Proposal.model_validate_json(json_dumped)
    assert p2.proposal_id == p.proposal_id
