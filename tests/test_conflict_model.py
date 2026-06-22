import pytest
from pydantic import ValidationError
from models.conflict import Conflict

def test_conflict_valid():
    c = Conflict(
        conflict_id="c1",
        proposal_a_id="p1",
        proposal_b_id="p2",
        agent_a="climate",
        agent_b="finance",
        reason="Budget vs Green Space",
        severity="high",
        resolution_status="unresolved"
    )
    assert c.conflict_id == "c1"

def test_conflict_invalid_severity():
    with pytest.raises(ValidationError):
        Conflict(
            conflict_id="c1",
            proposal_a_id="p1",
            proposal_b_id="p2",
            agent_a="climate",
            agent_b="finance",
            reason="Budget",
            severity="extreme",  # type: ignore
            resolution_status="unresolved"
        )

def test_conflict_invalid_resolution_status():
    with pytest.raises(ValidationError):
        Conflict(
            conflict_id="c1",
            proposal_a_id="p1",
            proposal_b_id="p2",
            agent_a="climate",
            agent_b="finance",
            reason="Budget",
            severity="high",
            resolution_status="unknown"  # type: ignore
        )

def test_conflict_serialization():
    c = Conflict(
        conflict_id="c1",
        proposal_a_id="p1",
        proposal_b_id="p2",
        agent_a="climate",
        agent_b="finance",
        reason="Budget",
        severity="low",
        resolution_status="resolved"
    )
    json_dumped = c.model_dump_json()
    c2 = Conflict.model_validate_json(json_dumped)
    assert c2.conflict_id == "c1"
