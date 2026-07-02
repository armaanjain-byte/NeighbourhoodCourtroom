from pydantic import BaseModel, Field, ConfigDict, PrivateAttr
from typing import Any, Dict, List, Optional
import uuid

class Proposal(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    city_slug: str
    version: int = 1
    budget_limit: float = Field(default=0.0, ge=0.0, frozen=True)
    _city_data: dict[str, Any] | None = PrivateAttr(default=None)
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
    
    # Scores & Overrides
    agent_scores: dict[str, float] = Field(default_factory=dict)
    human_locks: dict[str, float] = Field(default_factory=dict)
    
    # Audit Trail
    change_log: list[dict] = Field(default_factory=list)
    @property
    def calculated_construction_cost(self) -> float:
        """Compute construction cost on demand; never negotiated or stored."""
        from tools.cost_calculator import CostCalculator
        from tools.data_loader import DataLoader

        data_loader = DataLoader(skip_validation=True)
        city_data = self._city_data
        if city_data is None:
            try:
                city_data = data_loader.load_city(self.city_slug)
            except Exception:
                city_data = {}
        return CostCalculator(data_loader).calculate_construction_cost(self, city_data).total_estimated_cost
