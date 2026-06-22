from pydantic import BaseModel
from typing import Literal

class Conflict(BaseModel):
    parameter: str
    agent_a: str
    agent_b: str
    proposed_value_a: float
    proposed_value_b: float
    disagreement_severity: Literal["low", "medium", "high"]
