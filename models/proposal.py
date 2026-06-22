from pydantic import BaseModel, Field
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
