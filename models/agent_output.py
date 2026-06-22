from pydantic import BaseModel, Field
from .proposal import Proposal

class AgentOutput(BaseModel):
    agent_name: str
    summary: str
    proposals: list[Proposal]
    confidence: float = Field(ge=0, le=1)
