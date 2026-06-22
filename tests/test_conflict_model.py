import pytest
from models.conflict import Conflict
from pydantic import ValidationError

def test_conflict_creation():
    c = Conflict(
        parameter="green_space_pct",
        agent_a="finance",
        agent_b="climate",
        proposed_value_a=10.0,
        proposed_value_b=40.0,
        disagreement_severity="high"
    )
    assert c.parameter == "green_space_pct"

def test_conflict_invalid_severity():
    with pytest.raises(ValidationError):
        Conflict(
            parameter="green_space_pct",
            agent_a="finance",
            agent_b="climate",
            proposed_value_a=10.0,
            proposed_value_b=40.0,
            disagreement_severity="medium" # Only low or high allowed
        )
