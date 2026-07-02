import pytest
from models.agent_output import AgentOutput
from pydantic import ValidationError

def test_agent_output_creation():
    output = AgentOutput(
        agent_name="climate",
        score=85.5,
        verdict="modify",
        proposed_changes={"green_space_pct": 30.0},
        reasoning_and_evidence="We need more green space because of heat island risk."
    )
    assert output.agent_name == "climate"
    assert output.score == 85.5

def test_agent_output_invalid_verdict():
    with pytest.raises(ValidationError):
        AgentOutput(
            agent_name="finance",
            score=50,
            verdict="ignore",
            proposed_changes={},
            reasoning_and_evidence="..."
        )
