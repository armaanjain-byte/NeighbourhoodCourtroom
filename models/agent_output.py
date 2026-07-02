from pydantic import BaseModel, Field
from typing import Dict, Literal

class AgentOutput(BaseModel):
    agent_name: str
    score: float = Field(ge=0, le=100)
    score_rationale: str = ""
    verdict: Literal["accept", "modify", "reject"]
    proposed_changes: dict[str, float]
    reasoning_and_evidence: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    standards_flags: list[dict] = Field(default_factory=list)

