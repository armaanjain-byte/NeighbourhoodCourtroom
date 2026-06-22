from pydantic import BaseModel
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
