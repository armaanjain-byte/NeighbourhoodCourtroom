import os

MODELS_DIR = "models"
TESTS_DIR = "tests"

PROPOSAL_CODE = """from pydantic import BaseModel, Field
from typing import Dict, List, Optional
import uuid

class Proposal(BaseModel):
    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    city_slug: str
    version: int = 1
    
    # Core Parameters
    green_space_pct: float
    affordable_housing_pct: float
    housing_units: int
    parking_spaces: int
    community_center_sqft: float
    estimated_cost: float
    
    # Scores & Overrides
    agent_scores: dict[str, float] = Field(default_factory=dict)
    human_locks: dict[str, float] = Field(default_factory=dict)
    
    # Audit Trail
    change_log: list[dict] = Field(default_factory=list)
"""

AGENT_OUTPUT_CODE = """from pydantic import BaseModel, Field
from typing import Dict, Literal

class AgentOutput(BaseModel):
    agent_name: str
    score: float = Field(ge=0, le=100)
    verdict: Literal["accept", "modify", "reject"]
    proposed_changes: dict[str, float]
    reasoning_and_evidence: str
"""

CONFLICT_CODE = """from pydantic import BaseModel
from typing import Literal

class Conflict(BaseModel):
    parameter: str
    agent_a: str
    agent_b: str
    proposed_value_a: float
    proposed_value_b: float
    disagreement_severity: Literal["low", "high"]
"""

DEBATE_ROUND_CODE = """from pydantic import BaseModel
from typing import Dict, List, Optional
from .proposal import Proposal
from .agent_output import AgentOutput
from .conflict import Conflict

class DebateRound(BaseModel):
    round_number: int
    opening_state: Proposal
    agent_outputs: dict[str, AgentOutput]
    detected_conflicts: list[Conflict]
    closing_state: Proposal
    engine_summary: str
"""

TEST_PROPOSAL_CODE = """import pytest
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
"""

TEST_AGENT_OUTPUT_CODE = """import pytest
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
"""

TEST_CONFLICT_CODE = """import pytest
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
"""

TEST_DEBATE_ROUND_CODE = """import pytest
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
        estimated_cost=45000000.0
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
"""

files_to_write = {
    f"{MODELS_DIR}/proposal.py": PROPOSAL_CODE,
    f"{MODELS_DIR}/agent_output.py": AGENT_OUTPUT_CODE,
    f"{MODELS_DIR}/conflict.py": CONFLICT_CODE,
    f"{MODELS_DIR}/debate_round.py": DEBATE_ROUND_CODE,
    f"{TESTS_DIR}/test_proposal.py": TEST_PROPOSAL_CODE,
    f"{TESTS_DIR}/test_agent_output.py": TEST_AGENT_OUTPUT_CODE,
    f"{TESTS_DIR}/test_conflict_model.py": TEST_CONFLICT_CODE,
    f"{TESTS_DIR}/test_debate_round.py": TEST_DEBATE_ROUND_CODE,
}

for path, content in files_to_write.items():
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

print("Scaffolded Middle-Ground architecture models and tests.")
