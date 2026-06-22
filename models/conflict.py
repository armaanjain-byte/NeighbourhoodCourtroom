from pydantic import BaseModel
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
