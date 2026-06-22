import os

base_dir = r"c:\random\Desktop\NeighbourhoodCourtroom"

files = {
    "models/__init__.py": """from .proposal import Proposal
from .agent_output import AgentOutput
from .conflict import Conflict
from .debate_round import DebateRound

__all__ = ["Proposal", "AgentOutput", "Conflict", "DebateRound"]
""",
    "models/proposal.py": """from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal

class Proposal(BaseModel):
    proposal_id: str
    agent_name: str
    title: str = Field(min_length=1)
    description: str
    category: str
    cost_delta: float
    impact_score: float = Field(ge=0, le=100)
    status: Literal["proposed", "accepted", "rejected", "modified"]
    created_at: datetime
""",
    "models/agent_output.py": """from pydantic import BaseModel, Field
from .proposal import Proposal

class AgentOutput(BaseModel):
    agent_name: str
    summary: str
    proposals: list[Proposal]
    confidence: float = Field(ge=0, le=1)
""",
    "models/conflict.py": """from pydantic import BaseModel
from typing import Literal

class Conflict(BaseModel):
    conflict_id: str
    proposal_a_id: str
    proposal_b_id: str
    agent_a: str
    agent_b: str
    reason: str
    severity: Literal["low", "medium", "high"]
    resolution_status: Literal["unresolved", "resolved"]
""",
    "models/debate_round.py": """from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from .agent_output import AgentOutput
from .conflict import Conflict

class DebateRound(BaseModel):
    round_number: int = Field(ge=1)
    agent_outputs: list[AgentOutput]
    conflicts: list[Conflict]
    started_at: datetime
    ended_at: Optional[datetime] = None
""",
    "tests/test_proposal.py": """import pytest
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
""",
    "tests/test_agent_output.py": """import pytest
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
""",
    "tests/test_conflict_model.py": """import pytest
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
""",
    "tests/test_debate_round.py": """import pytest
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
"""
}

for f, content in files.items():
    filepath = os.path.join(base_dir, f)
    with open(filepath, "w", encoding="utf-8") as file:
        file.write(content)
