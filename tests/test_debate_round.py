import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from models.proposal import Proposal
from models.agent_output import AgentOutput
from models.conflict import Conflict
from models.debate_round import DebateRound

def create_valid_proposal():
    return Proposal(
        proposal_id="p1",
        agent_name="finance",
        title="Valid Title",
        description="Desc",
        category="transit",
        cost_delta=10.0,
        impact_score=50.0,
        status="proposed",
        created_at=datetime.now(timezone.utc)
    )

def create_valid_agent_output():
    return AgentOutput(
        agent_name="climate",
        summary="summary text",
        proposals=[create_valid_proposal()],
        confidence=0.8
    )

def create_valid_conflict():
    return Conflict(
        conflict_id="c1",
        proposal_a_id="p1",
        proposal_b_id="p2",
        agent_a="climate",
        agent_b="finance",
        reason="Reason",
        severity="medium",
        resolution_status="unresolved"
    )

def test_debate_round_valid():
    dt = datetime.now(timezone.utc)
    dr = DebateRound(
        round_number=1,
        agent_outputs=[create_valid_agent_output()],
        conflicts=[create_valid_conflict()],
        started_at=dt,
        ended_at=dt
    )
    assert dr.round_number == 1
    assert dr.ended_at is not None

def test_debate_round_no_ended_at():
    dt = datetime.now(timezone.utc)
    dr = DebateRound(
        round_number=2,
        agent_outputs=[],
        conflicts=[],
        started_at=dt
    )
    assert dr.ended_at is None

def test_debate_round_invalid_round_number():
    dt = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        DebateRound(
            round_number=0,
            agent_outputs=[],
            conflicts=[],
            started_at=dt
        )

def test_debate_round_nested_validation_failure():
    dt = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        DebateRound(
            round_number=1,
            agent_outputs=[{
                "agent_name": "climate"
                # missing other fields
            }],  # type: ignore
            conflicts=[],
            started_at=dt
        )

def test_debate_round_serialization():
    dt = datetime.now(timezone.utc)
    dr = DebateRound(
        round_number=1,
        agent_outputs=[create_valid_agent_output()],
        conflicts=[create_valid_conflict()],
        started_at=dt
    )
    json_dumped = dr.model_dump_json()
    dr2 = DebateRound.model_validate_json(json_dumped)
    assert dr2.round_number == 1
    assert len(dr2.agent_outputs) == 1
    assert len(dr2.conflicts) == 1
