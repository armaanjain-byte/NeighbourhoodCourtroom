from pydantic import BaseModel, Field, ConfigDict
from typing import Dict, List, Optional
import uuid

class Proposal(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    city_slug: str
    version: int = 1
    budget_limit: float = 0.0
    
    # Core Parameters
    # Sensible real-world bounds: green_space_pct as 0.0-100.0 (percentages of lot allocated to green space)
    green_space_pct: float = Field(ge=0.0, le=100.0)
    # Sensible real-world bounds: affordable_housing_pct as 0.0-100.0 (percentages of housing units designated affordable)
    affordable_housing_pct: float = Field(ge=0.0, le=100.0)
    # Sensible real-world bounds: housing_units as 0-100000 to prevent integer overflow/absurd density while allowing large developments
    housing_units: int = Field(ge=0, le=100000)
    # Sensible real-world bounds: parking_spaces as 0-100000 to prevent integer overflow/absurd sprawl while allowing large parking structures
    parking_spaces: int = Field(ge=0, le=100000)
    # Sensible real-world bounds: community_center_sqft as 0.0-1000000.0 to prevent absurd facility sizes while accommodating large community centers up to 1M sqft
    community_center_sqft: float = Field(ge=0.0, le=1000000.0)
    # Sensible real-world bounds: estimated_cost as 0.0 with a high but finite upper bound (10 billion) to prevent overflow-style abuse, not because city budgets are actually capped there
    estimated_cost: float = Field(default=0.0, ge=0.0, le=10_000_000_000.0)
    
    # Scores & Overrides
    agent_scores: dict[str, float] = Field(default_factory=dict)
    human_locks: dict[str, float] = Field(default_factory=dict)
    
    # Audit Trail
    change_log: list[dict] = Field(default_factory=list)

