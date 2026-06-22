from pydantic import BaseModel, Field
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
