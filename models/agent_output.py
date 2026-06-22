from pydantic import BaseModel, Field
from typing import Dict, Literal

class AgentOutput(BaseModel):
    agent_name: str
    score: float = Field(ge=0, le=100)
    verdict: Literal["accept", "modify", "reject"]
    proposed_changes: dict[str, float]
    reasoning_and_evidence: str
