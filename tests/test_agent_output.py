import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from models.proposal import Proposal
from models.agent_output import AgentOutput

def create_valid_proposal(proposal_id="p1"):
    return Proposal(
        proposal_id=proposal_id,
        agent_name="finance",
        title="Valid Title",
        description="Desc",
        category="transit",
        cost_delta=10.0,
        impact_score=50.0,
        status="proposed",
        created_at=datetime.now(timezone.utc)
    )

def test_agent_output_valid():
    out = AgentOutput(
        agent_name="climate",
        summary="summary text",
        proposals=[create_valid_proposal()],
        confidence=0.8
    )
    assert out.agent_name == "climate"
    assert len(out.proposals) == 1

def test_agent_output_empty_proposals():
    out = AgentOutput(
        agent_name="climate",
        summary="summary text",
        proposals=[],
        confidence=1.0
    )
    assert len(out.proposals) == 0

def test_agent_output_invalid_confidence():
    with pytest.raises(ValidationError):
        AgentOutput(
            agent_name="climate",
            summary="summary text",
            proposals=[],
            confidence=1.1
        )
    with pytest.raises(ValidationError):
        AgentOutput(
            agent_name="climate",
            summary="summary text",
            proposals=[],
            confidence=-0.1
        )

def test_agent_output_nested_validation_failure():
    # Pass an invalid proposal dict
    with pytest.raises(ValidationError):
        AgentOutput(
            agent_name="climate",
            summary="summary text",
            proposals=[{
                "proposal_id": "p1",
                # missing fields
            }],  # type: ignore
            confidence=0.8
        )

def test_agent_output_serialization():
    out = AgentOutput(
        agent_name="climate",
        summary="summary text",
        proposals=[create_valid_proposal()],
        confidence=0.8
    )
    json_dumped = out.model_dump_json()
    out2 = AgentOutput.model_validate_json(json_dumped)
    assert out2.agent_name == "climate"
    assert out2.proposals[0].proposal_id == "p1"
