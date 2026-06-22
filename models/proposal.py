from pydantic import BaseModel, Field
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
