# Neighborhood Courtroom — Complete Technical Architecture

## System Overview

Neighborhood Courtroom is a multi-agent civic planning system. Three specialized agents
(Finance, Climate, Community) hold different slices of preprocessed local data and negotiate
redevelopment proposals through a structured two-round debate engine. Every decision is
versioned, attributed, and diffable. Humans can lock parameters and watch agents re-negotiate
in real time.

The deliberate constraint: no live APIs. All location data is preprocessed into a local
dataset covering 40 US cities. This eliminates runtime failure risk while preserving the
core technical claim — agents hold genuinely different data and produce outputs no single
LLM call could replicate.

---

## Repository Structure

```
neighborhood-courtroom/
│
├── README.md
├── requirements.txt
├── .env.example
├── .streamlit/
│   └── secrets.toml.example
│
├── app.py                          # Streamlit entry point
│
├── data/
│   ├── cities.json                 # Master city lookup (40 cities)
│   ├── demographics.json           # Census-derived demographic profiles
│   ├── climate.json                # Climate zone classifications
│   ├── walkability.json            # Walkability + transit scores
│   ├── construction_costs.json     # Cost-per-sqft lookup by type + city tier
│   ├── land_use.json               # Typical zoning + land use by city type
│   └── scenarios/
│       ├── phoenix_vacant_lot.json      # Pre-built demo scenario
│       ├── detroit_brownfield.json
│       └── denver_transit_hub.json
│
├── agents/
│   ├── __init__.py
│   ├── base_agent.py               # Abstract base class + shared interface
│   ├── finance_agent.py
│   ├── climate_agent.py
│   └── community_agent.py
│
├── engine/
│   ├── __init__.py
│   ├── state.py                    # ProposalState dataclass + versioning
│   ├── conflict.py                 # Conflict detection + scoring
│   ├── debate.py                   # Two-round debate loop
│   └── override.py                 # Human override injection
│
├── tools/
│   ├── __init__.py
│   ├── data_loader.py              # Local dataset query interface
│   └── cost_calculator.py          # Budget arithmetic
│
├── models/
│   ├── __init__.py
│   ├── agent_output.py             # Pydantic: AgentOutput
│   ├── proposal.py                 # Pydantic: ProposalState
│   ├── conflict.py                 # Pydantic: Conflict
│   └── debate_round.py             # Pydantic: DebateRound
│
├── tests/
│   ├── test_agents.py
│   ├── test_conflict.py
│   ├── test_debate.py
│   ├── test_override.py
│   └── test_data_loader.py
│
└── scripts/
    ├── preprocess_data.py          # One-time data preparation script
    └── validate_dataset.py         # Sanity-check all 40 city records
```

---

## Data Architecture

### Design Principle

Every data file is a flat JSON dict keyed by city slug (e.g., `"phoenix_az"`).
Agents query by city slug only — no geocoding required at runtime.
All values are pre-validated to be non-null for every city.

---

### data/cities.json

```json
{
  "phoenix_az": {
    "name": "Phoenix, AZ",
    "state": "AZ",
    "region": "southwest",
    "city_tier": "large",
    "population": 1608139,
    "lat": 33.4484,
    "lon": -112.0740
  },
  "detroit_mi": { ... },
  ...
}
```

**40 cities selected to cover:**
- All 4 census regions (Northeast, South, Midwest, West)
- 3 city tiers (large >500k, medium 100-500k, small 50-100k)
- Full climate zone coverage (1A humid tropical → 7 very cold)
- Full economic spectrum (high-income coastal → post-industrial Midwest)
- Mix of high and low walkability baselines

---

### data/demographics.json

Source: ACS 5-Year Estimates, pre-pulled and cleaned offline.

```json
{
  "phoenix_az": {
    "median_household_income": 62055,
    "poverty_rate": 0.172,
    "population_density_per_sqmi": 3120,
    "pct_age_65_plus": 0.114,
    "pct_with_disability": 0.118,
    "pct_renter_occupied": 0.411,
    "unemployment_rate": 0.048,
    "median_home_value": 294800,
    "pct_no_vehicle": 0.089,
    "pct_non_white": 0.582,
    "data_year": 2022,
    "source": "ACS 5-Year Estimates B01001, B17001, B19013, B25077"
  }
}
```

**Community Agent uses:** poverty_rate, pct_age_65_plus, pct_with_disability,
pct_renter_occupied, pct_no_vehicle — these are its primary evidence sources.

---

### data/climate.json

Source: NOAA climate zone classifications + EPA heat island research, preprocessed.

```json
{
  "phoenix_az": {
    "climate_zone": "2B",
    "climate_description": "Hot-Dry",
    "ashrae_zone": 2,
    "annual_hdd": 1350,
    "annual_cdd": 4242,
    "heat_island_risk": 5,
    "flood_risk_fema_zone": "X",
    "flood_risk_score": 1,
    "recommended_min_green_cover_pct": 30,
    "green_cover_cooling_benefit_per_pct": 0.08,
    "native_species_recommendations": [
      "Palo Verde", "Saguaro", "Desert Willow", "Mesquite"
    ],
    "solar_irradiance_kwh_per_sqm": 5.8,
    "avg_summer_temp_f": 104,
    "urban_heat_penalty_degrees_f": 7,
    "permeable_surface_benefit": "high",
    "data_sources": ["NOAA ASHRAE 169-2013", "EPA Heat Island Effect Study 2021"]
  }
}
```

**Climate Agent uses:** heat_island_risk, recommended_min_green_cover_pct,
green_cover_cooling_benefit_per_pct, flood_risk_score, native_species_recommendations.

---

### data/walkability.json

Source: Walk Score methodology re-implemented on OpenStreetMap data, pre-scored.

```json
{
  "phoenix_az": {
    "walk_score": 41,
    "walk_score_label": "Car-Dependent",
    "transit_score": 36,
    "transit_score_label": "Some Transit",
    "bike_score": 59,
    "nearest_park_distance_mi": 0.8,
    "parks_within_half_mile": 1,
    "grocery_within_half_mile": true,
    "transit_stops_within_quarter_mile": 3,
    "ada_infrastructure_score": 52,
    "pedestrian_fatality_rate_per_100k": 4.1,
    "data_source": "OpenStreetMap + Walk Score methodology 2023"
  }
}
```

**Community Agent + Finance Agent both use:** walk_score, transit_score,
parks_within_half_mile — these create genuine cross-agent tension on amenity spending.

---

### data/construction_costs.json

Source: RSMeans 2023 city cost indices, simplified and restructured.

```json
{
  "cost_index_by_city": {
    "phoenix_az": 0.89,
    "new_york_ny": 1.47,
    "detroit_mi": 0.82,
    "denver_co": 0.97
  },
  "base_costs_per_sqft": {
    "surface_parking": 8,
    "structured_parking": 65,
    "green_space_basic": 12,
    "green_space_activated": 28,
    "mixed_use_residential": 185,
    "mixed_use_commercial": 210,
    "community_center": 195,
    "affordable_housing": 165,
    "market_rate_housing": 215,
    "pocket_park": 45,
    "green_roof": 38,
    "permeable_paving": 18,
    "standard_paving": 6,
    "solar_canopy": 55,
    "playground": 35,
    "dog_park": 20
  },
  "soft_cost_multiplier": 1.28,
  "contingency_multiplier": 1.12
}
```

**Finance Agent uses this exclusively.** It is the primary data source that no other
agent accesses, making Finance Agent outputs provably different in provenance.

---

### data/land_use.json

```json
{
  "phoenix_az": {
    "dominant_zoning": "mixed_residential_commercial",
    "typical_far": 2.0,
    "max_height_ft": 45,
    "required_setback_ft": 10,
    "parking_requirement_per_unit": 1.5,
    "affordable_housing_requirement_pct": 15,
    "green_space_requirement_pct": 20,
    "city_sustainability_score": 58,
    "recent_redevelopment_projects": [
      "Roosevelt Row arts district",
      "Downtown Phoenix light rail corridor"
    ]
  }
}
```

---

## Pydantic Models (Complete)

### models/proposal.py

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid

class ZoneAllocation(BaseModel):
    zone_type: str          # "green_space", "housing", "commercial", "community", "parking"
    area_sqft: float
    area_pct: float
    cost_estimate: float
    notes: str

class ProposalState(BaseModel):
    proposal_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    version: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    city_slug: str
    lot_area_sqft: float
    total_budget: float

    # Zone allocation
    zones: list[ZoneAllocation] = []
    green_space_pct: float = 0.0
    housing_units: int = 0
    affordable_housing_pct: float = 0.0
    community_sqft: float = 0.0
    parking_spaces: int = 0

    # Derived metrics
    total_cost_estimate: float = 0.0
    budget_remaining: float = 0.0
    cost_per_unit: Optional[float] = None

    # Scores (set by agents, 0-100)
    finance_score: Optional[float] = None
    climate_score: Optional[float] = None
    community_score: Optional[float] = None
    composite_score: Optional[float] = None

    # Override locks
    locked_green_space_pct: Optional[float] = None
    locked_budget_ceiling: Optional[float] = None

    # Audit
    change_log: list[dict] = []

    def apply_lock(self, parameter: str, value: float) -> "ProposalState":
        """Returns new ProposalState with lock applied."""
        updated = self.model_copy(deep=True)
        updated.version += 1
        if parameter == "green_space_pct":
            updated.locked_green_space_pct = value
        elif parameter == "budget_ceiling":
            updated.locked_budget_ceiling = value
        updated.change_log.append({
            "version": updated.version,
            "actor": "human",
            "action": f"locked_{parameter}",
            "value": value,
            "timestamp": datetime.utcnow().isoformat()
        })
        return updated

    def diff(self, other: "ProposalState") -> dict:
        """Returns structured diff between this state and another."""
        fields = [
            "green_space_pct", "housing_units", "affordable_housing_pct",
            "community_sqft", "parking_spaces", "total_cost_estimate",
            "budget_remaining", "finance_score", "climate_score", "community_score"
        ]
        return {
            f: {"before": getattr(self, f), "after": getattr(other, f)}
            for f in fields
            if getattr(self, f) != getattr(other, f)
        }
```

---

### models/agent_output.py

```python
from pydantic import BaseModel, Field
from typing import Literal
from enum import Enum

class EvidenceItem(BaseModel):
    claim: str
    value: str           # The actual data point: "poverty_rate: 17.2%"
    source: str          # Dataset source: "ACS 2022 demographics"
    implication: str     # Why this matters for the proposal

class ProposedChange(BaseModel):
    element: str                    # "green_space_pct", "housing_units", etc.
    current_value: float | str | None
    proposed_value: float | str
    reasoning: str
    cost_impact: Optional[float] = None   # + means more expensive

class ConflictFlag(BaseModel):
    with_agent: Literal["finance", "climate", "community"]
    over: str                       # "green_space_pct"
    severity: Literal["low", "medium", "high"]
    description: str

class AgentOutput(BaseModel):
    agent: Literal["finance", "climate", "community"]
    round: int                      # 1 or 2
    score: float = Field(ge=0, le=100)   # Agent's score of current proposal
    verdict: Literal["accept", "modify", "reject"]
    proposed_changes: list[ProposedChange]
    evidence: list[EvidenceItem]    # Must cite actual data values
    conflict_flags: list[ConflictFlag]
    reasoning_summary: str          # 2-3 sentences, human-readable
    data_sources_used: list[str]    # Explicit list of which datasets were queried
```

---

### models/debate_round.py

```python
from pydantic import BaseModel
from models.agent_output import AgentOutput, ConflictFlag
from models.proposal import ProposalState

class DebateRound(BaseModel):
    round_number: int
    opening_state: ProposalState
    agent_outputs: dict[str, AgentOutput]    # keyed by agent name
    detected_conflicts: list[ConflictFlag]
    resolution_summary: str
    closing_state: ProposalState
    human_override_applied: bool = False
```

---

## Agent Architecture

### agents/base_agent.py

#### Evidence Grounding and Hallucination Prevention
To directly address the hallucination risk inherent in letting LLMs generate free-text evidence claims from memory, `BaseAgent` implements an active, post-hoc evidence grounding check (`_check_evidence_grounding`):
1. **Tool Result Tracking**: The provider-agnostic `LLMProvider` records all tool call results that occur during the multi-turn function calling loop, exposing them in the returned dictionary (`data["tool_results"]`).
2. **Numeric Harvesting**: `BaseAgent` recursively walks the dict/list structures returned by each tool call to collect every verified numeric data point into a set of `tool_numbers`.
3. **Regex Extraction & Matching**: For each free-text evidence string produced by the model, numbers are extracted using regex (`r'\b\d+(?:\.\d+)?\b'`) and cross-checked against `tool_numbers`. A reasonable tolerance (e.g. `0.1` absolute tolerance or `0.001` for percentage conversions like `17.2%` matching `0.172`) is permitted to accommodate natural language formatting variations.
4. **Non-Numeric Claims**: Evidence strings containing no numbers (e.g., qualitative zoning assessments) default to `grounded=True` so as not to penalize legitimate non-numeric factual observations.
5. **UI Surfacing**: Any unverified claim is recorded in `AgentOpinion.grounding_warnings` and explicitly highlighted with a `⚠️ unverified claim` badge in the Streamlit debate transcript, demonstrating active, visible "Agent Quality" governance to judging panels.

```python
from abc import ABC, abstractmethod
from google import genai

from models.agent_output import AgentOutput
from models.proposal import ProposalState
from tools.data_loader import DataLoader
import json

class BaseAgent(ABC):
    def __init__(self, data_loader: DataLoader):
        self.client = genai.Client()
        self.data_loader = data_loader
        self.agent_name: str = ""
        self.mandate: str = ""

    @abstractmethod
    def load_context(self, city_slug: str) -> dict:
        """Load the data this agent is responsible for. Each agent loads
        different data — this is the core justification for multi-agent."""
        pass

    @abstractmethod
    def build_system_prompt(self) -> str:
        pass

    def run(self, proposal: ProposalState, round_num: int,
            other_outputs: list[AgentOutput] = None) -> AgentOutput:
        """Execute agent reasoning and return structured output."""

        context = self.load_context(proposal.city_slug)
        proposal_dict = proposal.model_dump()
        others_dict = [o.model_dump() for o in (other_outputs or [])]

        user_message = f"""
CURRENT PROPOSAL STATE:
{json.dumps(proposal_dict, indent=2, default=str)}

YOUR DATA CONTEXT:
{json.dumps(context, indent=2)}

ROUND: {round_num}
{"OTHER AGENTS' ROUND 1 OUTPUTS:" if others_dict else ""}
{json.dumps(others_dict, indent=2) if others_dict else ""}

{"You are responding to other agents. Acknowledge their points, maintain your mandate." if round_num == 2 else "Evaluate the initial proposal from your specialized perspective."}

LOCKED CONSTRAINTS (you must respect these):
- green_space_pct lock: {proposal.locked_green_space_pct or "none"}
- budget_ceiling lock: {proposal.locked_budget_ceiling or "none"}

Respond ONLY with a valid JSON object matching the AgentOutput schema.
Every evidence item MUST cite an actual value from YOUR DATA CONTEXT above.
Do not invent data. Do not cite data you were not given.
"""

        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_message,
            config={"system_instruction": self.build_system_prompt()}
        )

        raw = response.text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return AgentOutput.model_validate_json(raw)
```

---

### agents/finance_agent.py

```python
from agents.base_agent import BaseAgent
from tools.data_loader import DataLoader

class FinanceAgent(BaseAgent):
    def __init__(self, client, data_loader: DataLoader):
        super().__init__(client, data_loader)
        self.agent_name = "finance"
        self.mandate = "Maximize financial viability and ROI while minimizing cost overruns."

    def load_context(self, city_slug: str) -> dict:
        """Finance Agent loads ONLY financial data — costs and land use constraints.
        It does NOT see demographic or climate data directly."""
        costs = self.data_loader.get_construction_costs(city_slug)
        land = self.data_loader.get_land_use(city_slug)
        return {
            "data_type": "financial_and_regulatory",
            "cost_index": costs["city_index"],
            "base_costs_per_sqft": costs["base_costs"],
            "soft_cost_multiplier": costs["soft_cost_multiplier"],
            "contingency_multiplier": costs["contingency_multiplier"],
            "zoning": {
                "max_far": land["typical_far"],
                "max_height_ft": land["max_height_ft"],
                "parking_requirement_per_unit": land["parking_requirement_per_unit"],
                "affordable_housing_requirement_pct": land["affordable_housing_requirement_pct"]
            },
            "note": "You have cost and regulatory data only. You do not have climate or demographic data."
        }

    def build_system_prompt(self) -> str:
        return """You are the Finance Agent in a multi-agent urban planning system.

YOUR MANDATE: Maximize financial viability. Control costs. Identify budget risks.
Oppose any element that exceeds budget or produces negative ROI without strong justification.

YOUR DATA: You have access to construction cost indices and zoning regulations only.
You do NOT have climate data or demographic data. When other agents cite climate risk
or community need, acknowledge those concerns but evaluate them through a cost lens.

BEHAVIOR RULES:
1. Every proposed change must cite a specific dollar figure from your cost data
2. Calculate total cost estimates for any zone allocation you propose
3. Flag any element whose cost exceeds 15% of total budget as a high concern
4. Propose specific cost reduction alternatives, not just objections
5. Your score (0-100) represents financial viability: 100 = on budget with ROI,
   0 = massively over budget or financially unviable
6. You MUST advocate for your mandate even when outnumbered

Return ONLY valid JSON matching the AgentOutput schema. No preamble. No explanation outside JSON."""
```

---

### agents/climate_agent.py

```python
class ClimateAgent(BaseAgent):
    def __init__(self, client, data_loader: DataLoader):
        super().__init__(client, data_loader)
        self.agent_name = "climate"
        self.mandate = "Maximize climate resilience and environmental sustainability."

    def load_context(self, city_slug: str) -> dict:
        """Climate Agent loads ONLY climate and physical environment data.
        It does NOT see cost data or demographic data directly."""
        climate = self.data_loader.get_climate(city_slug)
        walk = self.data_loader.get_walkability(city_slug)
        return {
            "data_type": "climate_and_environmental",
            "climate_zone": climate["climate_zone"],
            "climate_description": climate["climate_description"],
            "heat_island_risk": climate["heat_island_risk"],
            "recommended_min_green_cover_pct": climate["recommended_min_green_cover_pct"],
            "green_cover_cooling_benefit_per_pct": climate["green_cover_cooling_benefit_per_pct"],
            "flood_risk_score": climate["flood_risk_score"],
            "native_species_recommendations": climate["native_species_recommendations"],
            "avg_summer_temp_f": climate["avg_summer_temp_f"],
            "urban_heat_penalty_degrees_f": climate["urban_heat_penalty_degrees_f"],
            "permeable_surface_benefit": climate["permeable_surface_benefit"],
            "solar_irradiance_kwh_per_sqm": climate["solar_irradiance_kwh_per_sqm"],
            "ada_infrastructure_score": walk["ada_infrastructure_score"],
            "note": "You have climate and environmental data only. No cost or demographic data."
        }

    def build_system_prompt(self) -> str:
        return """You are the Climate Agent in a multi-agent urban planning system.

YOUR MANDATE: Maximize climate resilience. Minimize urban heat island effect.
Ensure adequate green cover, flood resilience, and sustainable design.

YOUR DATA: You have climate zone classifications, heat island risk scores,
flood risk data, and environmental recommendations. You do NOT have cost data
or demographic data.

BEHAVIOR RULES:
1. Always cite specific climate values (heat_island_risk score, recommended green %)
2. Calculate projected temperature impact of proposed green space levels
3. Flag any proposal where green_space_pct < recommended_min_green_cover_pct
4. Propose specific native species by name when recommending plantings
5. Your score (0-100) represents climate resilience: 100 = optimal environmental
   performance, 0 = dangerous heat island or flood risk
6. You MUST oppose insufficient green cover even when it conflicts with budget

Return ONLY valid JSON matching the AgentOutput schema."""
```

---

### agents/community_agent.py

```python
class CommunityAgent(BaseAgent):
    def __init__(self, client, data_loader: DataLoader):
        super().__init__(client, data_loader)
        self.agent_name = "community"
        self.mandate = "Maximize community equity, accessibility, and long-term neighborhood benefit."

    def load_context(self, city_slug: str) -> dict:
        """Community Agent loads ONLY demographic and accessibility data.
        It does NOT see cost data or climate data directly."""
        demo = self.data_loader.get_demographics(city_slug)
        walk = self.data_loader.get_walkability(city_slug)
        land = self.data_loader.get_land_use(city_slug)
        return {
            "data_type": "demographic_and_accessibility",
            "demographics": {
                "median_household_income": demo["median_household_income"],
                "poverty_rate": demo["poverty_rate"],
                "pct_age_65_plus": demo["pct_age_65_plus"],
                "pct_with_disability": demo["pct_with_disability"],
                "pct_renter_occupied": demo["pct_renter_occupied"],
                "pct_no_vehicle": demo["pct_no_vehicle"],
                "pct_non_white": demo["pct_non_white"],
                "unemployment_rate": demo["unemployment_rate"]
            },
            "accessibility": {
                "walk_score": walk["walk_score"],
                "transit_score": walk["transit_score"],
                "parks_within_half_mile": walk["parks_within_half_mile"],
                "ada_infrastructure_score": walk["ada_infrastructure_score"],
                "pedestrian_fatality_rate_per_100k": walk["pedestrian_fatality_rate_per_100k"]
            },
            "requirements": {
                "affordable_housing_requirement_pct": land["affordable_housing_requirement_pct"]
            },
            "note": "You have demographic and accessibility data only. No cost or climate data."
        }

    def build_system_prompt(self) -> str:
        return """You are the Community Agent in a multi-agent urban planning system.

YOUR MANDATE: Ensure the redevelopment serves the actual community that lives here.
Prioritize affordability, accessibility, anti-displacement, and public space for all.

YOUR DATA: You have demographic profiles (income, poverty, age, disability, race),
walkability scores, accessibility metrics, and housing statistics. No cost or climate data.

BEHAVIOR RULES:
1. Always cite specific demographic values when making claims (e.g., "17.2% poverty rate")
2. Evaluate affordability relative to median household income
3. Flag displacement risk when affordable housing % is below requirement
4. Advocate for elderly and disability access when pct_age_65_plus > 12% or
   pct_with_disability > 10%
5. Your score (0-100) represents community equity: 100 = serves all residents equitably,
   0 = actively harms existing community
6. You MUST oppose market-rate-only development in high-poverty communities

Return ONLY valid JSON matching the AgentOutput schema."""
```

---

## Debate Engine

### engine/debate.py

```python
import asyncio
from typing import AsyncGenerator
from models.proposal import ProposalState
from models.debate_round import DebateRound
from agents.finance_agent import FinanceAgent
from agents.climate_agent import ClimateAgent
from agents.community_agent import CommunityAgent
from engine.conflict import ConflictDetector
from engine.state import StateManager

class DebateEngine:
    def __init__(self, finance: FinanceAgent, climate: ClimateAgent,
                 community: CommunityAgent, conflict_detector: ConflictDetector,
                 state_manager: StateManager):
        self.agents = {
            "finance": finance,
            "climate": climate,
            "community": community
        }
        self.conflict_detector = conflict_detector
        self.state_manager = state_manager

    async def run_round(self, proposal: ProposalState, round_num: int,
                        prior_outputs: list = None) -> DebateRound:
        """Run one round of debate. Round 1: parallel. Round 2: sequential with context."""

        opening_state = proposal.model_copy(deep=True)

        if round_num == 1:
            # Round 1: all agents analyze independently and in parallel
            tasks = [
                asyncio.to_thread(agent.run, proposal, 1, None)
                for agent in self.agents.values()
            ]
            results = await asyncio.gather(*tasks)
            outputs = dict(zip(self.agents.keys(), results))

        else:
            # Round 2: sequential — agents see each other's Round 1 outputs
            outputs = {}
            for name, agent in self.agents.items():
                other_outputs = [v for k, v in prior_outputs.items() if k != name]
                outputs[name] = await asyncio.to_thread(
                    agent.run, proposal, 2, other_outputs
                )

        # Detect conflicts from structured scores
        conflicts = self.conflict_detector.detect(outputs)

        # Generate closing state by applying non-conflicting changes
        closing_state = self.state_manager.synthesize(proposal, outputs, conflicts)

        resolution = self._generate_resolution_summary(outputs, conflicts)

        return DebateRound(
            round_number=round_num,
            opening_state=opening_state,
            agent_outputs=outputs,
            detected_conflicts=conflicts,
            resolution_summary=resolution,
            closing_state=closing_state
        )

    async def run_full_debate(self, initial_proposal: ProposalState,
                               stream_callback=None) -> tuple[list[DebateRound], ProposalState]:
        """Run two-round debate. Returns rounds and final proposal state."""

        rounds = []

        # Round 1
        if stream_callback:
            await stream_callback("round_start", {"round": 1})

        round1 = await self.run_round(initial_proposal, round_num=1)
        rounds.append(round1)

        if stream_callback:
            await stream_callback("round_complete", {"round": 1, "data": round1})

        # Round 2 (with Round 1 context injected)
        if stream_callback:
            await stream_callback("round_start", {"round": 2})

        round2 = await self.run_round(
            round1.closing_state, round_num=2,
            prior_outputs=round1.agent_outputs
        )
        rounds.append(round2)

        if stream_callback:
            await stream_callback("round_complete", {"round": 2, "data": round2})

        return rounds, round2.closing_state

    def _generate_resolution_summary(self, outputs, conflicts) -> str:
        verdicts = {name: out.verdict for name, out in outputs.items()}
        scores = {name: out.score for name, out in outputs.items()}
        conflict_count = len([c for c in conflicts if c.severity in ["medium", "high"]])
        return (
            f"Round complete. Verdicts: {verdicts}. Scores: {scores}. "
            f"{conflict_count} significant conflict(s) detected."
        )
```

---

### engine/conflict.py

```python
from models.agent_output import AgentOutput, ConflictFlag
from models.proposal import ProposalState

class ConflictDetector:
    SCORE_CONFLICT_THRESHOLD = 35   # Score gap that triggers a flagged conflict

    def detect(self, outputs: dict[str, AgentOutput]) -> list[ConflictFlag]:
        conflicts = []
        agents = list(outputs.keys())

        # Pairwise score comparison
        for i, a1 in enumerate(agents):
            for a2 in agents[i+1:]:
                score_gap = abs(outputs[a1].score - outputs[a2].score)
                if score_gap >= self.SCORE_CONFLICT_THRESHOLD:
                    severity = "high" if score_gap >= 50 else "medium"
                    conflicts.append(ConflictFlag(
                        with_agent=a2,
                        over="proposal_acceptability",
                        severity=severity,
                        description=(
                            f"{a1} scores proposal {outputs[a1].score:.0f}/100 "
                            f"but {a2} scores it {outputs[a2].score:.0f}/100 "
                            f"(gap: {score_gap:.0f} points)"
                        )
                    ))

        # Collect agent-declared conflicts
        for name, output in outputs.items():
            conflicts.extend(output.conflict_flags)

        # Deduplicate by (agents, element)
        seen = set()
        unique = []
        for c in conflicts:
            key = (c.with_agent, c.over)
            if key not in seen:
                seen.add(key)
                unique.append(c)

        return unique

    def has_blocking_conflict(self, conflicts: list[ConflictFlag]) -> bool:
        return any(c.severity == "high" for c in conflicts)
```

### Deterministic Conflict Resolution Rules

The conflict resolution engine arbitrates contested parameters based on severity and agent confidence (`opinion.confidence`):
1. **Single proposer, no conflict** → accept the value.
2. **Multiple proposers agree** → accept the shared value.
3. **LOW conflict (<10% delta)** → confidence-weighted mean of all proposing agents' values (each agent's value weighted by its own confidence, normalized).
4. **MEDIUM conflict (10–25% delta)** → combined weighted mean multiplying domain weight (finance 0.4, climate 0.3, community 0.3) by each agent's confidence, then normalized.
5. **HIGH conflict (>25% delta)** → do not auto-resolve; flag for human review (confidence is never used to suppress a human-review escalation).
6. **Human-locked** → always preserve lock value; skip the parameter.

---


### engine/state.py

```python
from models.proposal import ProposalState, ZoneAllocation
from models.agent_output import AgentOutput
from models.conflict import ConflictFlag
from tools.cost_calculator import CostCalculator
from datetime import datetime

class StateManager:
    def __init__(self, cost_calculator: CostCalculator):
        self.calc = cost_calculator

    def create_initial_proposal(self, city_slug: str, lot_area_sqft: float,
                                 budget: float, project_type: str) -> ProposalState:
        """Generate starting proposal from project type template."""
        templates = {
            "mixed_use": {
                "green_space_pct": 15.0, "housing_units": 40,
                "affordable_housing_pct": 15.0, "community_sqft": 2000,
                "parking_spaces": 60
            },
            "community_park": {
                "green_space_pct": 60.0, "housing_units": 0,
                "affordable_housing_pct": 0.0, "community_sqft": 5000,
                "parking_spaces": 30
            },
            "affordable_housing": {
                "green_space_pct": 20.0, "housing_units": 80,
                "affordable_housing_pct": 40.0, "community_sqft": 1500,
                "parking_spaces": 80
            }
        }
        t = templates.get(project_type, templates["mixed_use"])
        proposal = ProposalState(
            city_slug=city_slug,
            lot_area_sqft=lot_area_sqft,
            total_budget=budget,
            **t
        )
        return self._recalculate_costs(proposal, city_slug)

    def synthesize(self, proposal: ProposalState, outputs: dict[str, AgentOutput],
                   conflicts: list[ConflictFlag]) -> ProposalState:
        """Apply non-conflicting agent changes to produce next proposal state."""
        updated = proposal.model_copy(deep=True)
        updated.version += 1

        # Collect all proposed changes
        all_changes = []
        for agent_name, output in outputs.items():
            for change in output.proposed_changes:
                all_changes.append((agent_name, change))

        # Identify contested elements
        contested_elements = {c.over for c in conflicts}

        # Apply only uncontested changes
        for agent_name, change in all_changes:
            if change.element not in contested_elements:
                self._apply_change(updated, agent_name, change)

        # Respect hard locks always
        if proposal.locked_green_space_pct is not None:
            updated.green_space_pct = proposal.locked_green_space_pct
        if proposal.locked_budget_ceiling is not None:
            updated.total_budget = min(updated.total_budget,
                                        proposal.locked_budget_ceiling)

        updated = self._recalculate_costs(updated, proposal.city_slug)
        return updated

    def _apply_change(self, proposal: ProposalState, agent: str, change) -> None:
        if hasattr(proposal, change.element):
            old_val = getattr(proposal, change.element)
            setattr(proposal, change.element, change.proposed_value)
            proposal.change_log.append({
                "version": proposal.version,
                "actor": agent,
                "element": change.element,
                "old_value": old_val,
                "new_value": change.proposed_value,
                "reasoning": change.reasoning,
                "timestamp": datetime.utcnow().isoformat()
            })

    def _recalculate_costs(self, proposal: ProposalState, city_slug: str) -> ProposalState:
        total = self.calc.estimate_total(proposal, city_slug)
        proposal.total_cost_estimate = total
        proposal.budget_remaining = proposal.total_budget - total
        if proposal.housing_units > 0:
            proposal.cost_per_unit = total / proposal.housing_units
        return proposal
```

---

### engine/override.py

```python
from models.proposal import ProposalState
from engine.debate import DebateEngine

class OverrideEngine:
    OVERRIDABLE_PARAMETERS = {
        "green_space_pct": {
            "label": "Green Space Percentage",
            "min": 0.0, "max": 80.0,
            "unit": "%",
            "description": "Percentage of lot area dedicated to green space"
        },
        "budget_ceiling": {
            "label": "Budget Ceiling",
            "min": 500_000, "max": 50_000_000,
            "unit": "$",
            "description": "Maximum total project budget"
        }
    }

    def apply_override(self, proposal: ProposalState,
                       parameter: str, value: float) -> ProposalState:
        """Inject human override into proposal state."""
        if parameter not in self.OVERRIDABLE_PARAMETERS:
            raise ValueError(f"Parameter {parameter} is not overridable.")
        return proposal.apply_lock(parameter, value)

    async def run_post_override_debate(
        self, proposal: ProposalState, debate_engine: DebateEngine
    ) -> tuple[list, ProposalState]:
        """Re-run debate with locked constraint. Agents must negotiate around it."""
        return await debate_engine.run_full_debate(proposal)
```

---

## Tools

### tools/data_loader.py

```python
import json
from pathlib import Path
from functools import lru_cache

class DataLoader:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self._cache = {}

    def _load(self, filename: str) -> dict:
        if filename not in self._cache:
            with open(self.data_dir / filename) as f:
                self._cache[filename] = json.load(f)
        return self._cache[filename]

    def get_city(self, city_slug: str) -> dict:
        return self._load("cities.json")[city_slug]

    def get_demographics(self, city_slug: str) -> dict:
        return self._load("demographics.json")[city_slug]

    def get_climate(self, city_slug: str) -> dict:
        return self._load("climate.json")[city_slug]

    def get_walkability(self, city_slug: str) -> dict:
        return self._load("walkability.json")[city_slug]

    def get_land_use(self, city_slug: str) -> dict:
        return self._load("land_use.json")[city_slug]

    def get_construction_costs(self, city_slug: str) -> dict:
        costs = self._load("construction_costs.json")
        city_index = costs["cost_index_by_city"].get(city_slug, 1.0)
        base = costs["base_costs_per_sqft"]
        # Apply city cost index to base costs
        adjusted = {k: round(v * city_index, 2) for k, v in base.items()}
        return {
            "city_index": city_index,
            "base_costs": adjusted,
            "soft_cost_multiplier": costs["soft_cost_multiplier"],
            "contingency_multiplier": costs["contingency_multiplier"]
        }

    def list_cities(self) -> list[dict]:
        cities = self._load("cities.json")
        return [{"slug": k, "name": v["name"]} for k, v in cities.items()]
```

---

### tools/cost_calculator.py

```python
from models.proposal import ProposalState
from tools.data_loader import DataLoader

class CostCalculator:
    def __init__(self, data_loader: DataLoader):
        self.loader = data_loader

    def estimate_total(self, proposal: ProposalState, city_slug: str) -> float:
        costs = self.loader.get_construction_costs(city_slug)
        base = costs["base_costs"]
        soft = costs["soft_cost_multiplier"]
        contingency = costs["contingency_multiplier"]
        lot = proposal.lot_area_sqft

        green_sqft = lot * (proposal.green_space_pct / 100)
        housing_sqft = proposal.housing_units * 850  # avg unit size

        line_items = {
            "green_space": green_sqft * base.get("green_space_activated", 28),
            "housing": housing_sqft * base.get("mixed_use_residential", 185),
            "community": proposal.community_sqft * base.get("community_center", 195),
            "parking": proposal.parking_spaces * 300 * base.get("surface_parking", 8),
        }

        hard_cost = sum(line_items.values())
        return round(hard_cost * soft * contingency, 2)

    def itemized_breakdown(self, proposal: ProposalState, city_slug: str) -> dict:
        """Returns line-item breakdown for chart rendering."""
        costs = self.loader.get_construction_costs(city_slug)
        base = costs["base_costs"]
        lot = proposal.lot_area_sqft
        return {
            "Green Space": lot * (proposal.green_space_pct / 100) * base.get("green_space_activated", 28),
            "Housing": proposal.housing_units * 850 * base.get("mixed_use_residential", 185),
            "Community Space": proposal.community_sqft * base.get("community_center", 195),
            "Parking": proposal.parking_spaces * 300 * base.get("surface_parking", 8),
        }
```

---

### tools/diff.py

```python
from models.proposal import ProposalState

def generate_diff_table(before: ProposalState, after: ProposalState) -> list[dict]:
    """Returns a list of changed fields suitable for UI rendering."""
    fields = {
        "green_space_pct": ("Green Space", "%", 1),
        "housing_units": ("Housing Units", "units", 0),
        "affordable_housing_pct": ("Affordable Housing", "%", 1),
        "community_sqft": ("Community Space", "sqft", 0),
        "parking_spaces": ("Parking Spaces", "spaces", 0),
        "total_cost_estimate": ("Total Cost", "$", 0),
        "budget_remaining": ("Budget Remaining", "$", 0),
        "finance_score": ("Finance Score", "/100", 1),
        "climate_score": ("Climate Score", "/100", 1),
        "community_score": ("Community Score", "/100", 1),
    }
    rows = []
    for field, (label, unit, decimals) in fields.items():
        before_val = getattr(before, field)
        after_val = getattr(after, field)
        if before_val != after_val and before_val is not None and after_val is not None:
            rows.append({
                "label": label,
                "unit": unit,
                "before": round(before_val, decimals) if decimals else int(before_val),
                "after": round(after_val, decimals) if decimals else int(after_val),
                "delta": round(after_val - before_val, decimals),
                "direction": "up" if after_val > before_val else "down"
            })
    return rows
```

---

## UI Components

### ui/schematic.py

```python
def generate_site_schematic(proposal) -> str:
    """Generate an SVG zone schematic. Returns SVG string."""

    COLORS = {
        "green_space": "#4CAF50",
        "housing": "#2196F3",
        "community": "#FF9800",
        "parking": "#9E9E9E",
        "remainder": "#E0E0E0"
    }

    # Calculate zone widths as % of total (horizontal bar layout)
    total = 100.0
    zones = {
        "green_space": proposal.green_space_pct,
        "housing": min(proposal.housing_units * 0.5, 40.0),
        "community": min(proposal.community_sqft / proposal.lot_area_sqft * 100, 20.0),
        "parking": min(proposal.parking_spaces * 0.3, 15.0),
    }
    remainder = max(0, total - sum(zones.values()))
    zones["other"] = remainder

    svg_width = 700
    svg_height = 200
    bar_height = 80
    bar_y = 60

    rects = []
    labels = []
    x = 0
    for zone, pct in zones.items():
        width = (pct / 100) * svg_width
        color = COLORS.get(zone, "#BDBDBD")
        label = zone.replace("_", " ").title()
        rects.append(
            f'<rect x="{x}" y="{bar_y}" width="{width:.1f}" height="{bar_height}" '
            f'fill="{color}" rx="4"/>'
        )
        if width > 40:
            labels.append(
                f'<text x="{x + width/2:.1f}" y="{bar_y + bar_height/2 + 5}" '
                f'text-anchor="middle" font-size="11" font-family="sans-serif" '
                f'fill="white" font-weight="bold">{label}\n{pct:.0f}%</text>'
            )
        x += width

    # Legend
    legend_items = []
    lx = 20
    for zone, color in COLORS.items():
        if zone in zones and zones[zone] > 0:
            legend_items.append(
                f'<rect x="{lx}" y="165" width="12" height="12" fill="{color}" rx="2"/>'
                f'<text x="{lx + 16}" y="175" font-size="10" font-family="sans-serif" '
                f'fill="#333">{zone.replace("_"," ").title()}</text>'
            )
            lx += 100

    return f"""<svg viewBox="0 0 {svg_width} {svg_height}" xmlns="http://www.w3.org/2000/svg">
  <text x="350" y="30" text-anchor="middle" font-size="14" font-family="sans-serif"
        font-weight="bold" fill="#333">Site Zone Allocation</text>
  {"".join(rects)}
  {"".join(labels)}
  {"".join(legend_items)}
</svg>"""
```

---

### ui/debate_view.py

```python
import streamlit as st

AGENT_COLORS = {
    "finance": "#1565C0",
    "climate": "#2E7D32",
    "community": "#E65100"
}

AGENT_ICONS = {
    "finance": "💰",
    "climate": "🌿",
    "community": "🏘️"
}

VERDICT_COLORS = {
    "accept": "green",
    "modify": "orange",
    "reject": "red"
}

def render_debate_transcript(rounds: list, conflicts: list) -> None:
    for round_data in rounds:
        st.markdown(f"### Round {round_data.round_number}")

        cols = st.columns(3)
        for idx, (agent_name, output) in enumerate(round_data.agent_outputs.items()):
            with cols[idx]:
                color = AGENT_COLORS[agent_name]
                icon = AGENT_ICONS[agent_name]
                verdict_color = VERDICT_COLORS[output.verdict]

                st.markdown(
                    f"""<div style="border-left: 4px solid {color}; padding: 12px;
                    background: #f8f9fa; border-radius: 4px; margin-bottom: 8px;">
                    <strong>{icon} {agent_name.title()} Agent</strong><br/>
                    Score: <strong>{output.score:.0f}/100</strong> &nbsp;
                    Verdict: <span style="color:{verdict_color}">
                    <strong>{output.verdict.upper()}</strong></span><br/><br/>
                    {output.reasoning_summary}</div>""",
                    unsafe_allow_html=True
                )

                if output.evidence:
                    with st.expander("Evidence cited"):
                        for e in output.evidence:
                            st.markdown(f"**{e.claim}:** `{e.value}` — {e.implication}")

        if round_data.detected_conflicts:
            st.markdown("#### ⚡ Conflicts Detected")
            for c in round_data.detected_conflicts:
                severity_color = {"high": "🔴", "medium": "🟡", "low": "🟢"}
                st.markdown(
                    f"{severity_color.get(c.severity, '⚪')} **{c.severity.upper()}** "
                    f"— {c.description}"
                )

        st.markdown("---")


def render_diff_table(diff_rows: list) -> None:
    if not diff_rows:
        st.info("No changes from override.")
        return

    st.markdown("### 🔄 What Changed After Override")
    for row in diff_rows:
        arrow = "↑" if row["direction"] == "up" else "↓"
        color = "green" if row["direction"] == "up" else "red"
        st.markdown(
            f"**{row['label']}**: {row['before']} {row['unit']} → "
            f"<span style='color:{color}'>{row['after']} {row['unit']} "
            f"({arrow} {abs(row['delta'])})</span>",
            unsafe_allow_html=True
        )
```

---

## Main Application

### app.py (Structure)

```python
import streamlit as st
import asyncio
from tools.data_loader import DataLoader
from tools.cost_calculator import CostCalculator
from agents.finance_agent import FinanceAgent
from agents.climate_agent import ClimateAgent
from agents.community_agent import CommunityAgent
from engine.debate import DebateEngine
from engine.conflict import ConflictDetector
from engine.state import StateManager
from engine.override import OverrideEngine
from services.gemini_explainer import generate_judge_brief

# ── Initialization ─────────────────────────────────────────────────────────────

@st.cache_resource
def get_system():
    loader = DataLoader()
    calc = CostCalculator(loader)
    finance = FinanceAgent(loader)
    climate = ClimateAgent(loader)
    community = CommunityAgent(loader)
    conflict = ConflictDetector()
    state_mgr = StateManager(calc)
    debate = DebateEngine(finance, climate, community, conflict, state_mgr)
    override = OverrideEngine()
    return loader, state_mgr, debate, override, calc

# ── Page Config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Neighborhood Courtroom",
    page_icon="⚖️",
    layout="wide"
)

# ── Session State ──────────────────────────────────────────────────────────────

if "stage" not in st.session_state:
    st.session_state.stage = "input"   # input → debating → result → override → override_result
if "proposal" not in st.session_state:
    st.session_state.proposal = None
if "rounds" not in st.session_state:
    st.session_state.rounds = []
if "final_proposal" not in st.session_state:
    st.session_state.final_proposal = None
if "pre_override_proposal" not in st.session_state:
    st.session_state.pre_override_proposal = None

loader, state_mgr, debate_engine, override_engine, calc = get_system()

# ── Stage: Input ───────────────────────────────────────────────────────────────

if st.session_state.stage == "input":
    st.title("⚖️ Neighborhood Courtroom")
    st.caption("Multi-agent urban redevelopment planning with transparent negotiation")

    # Quick-start scenarios
    st.markdown("### Quick Start")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("🌵 Phoenix Mixed-Use"):
            st.session_state.scenario = "phoenix_az"
    with col2:
        if st.button("🏭 Detroit Brownfield"):
            st.session_state.scenario = "detroit_mi"
    with col3:
        if st.button("🚃 Denver Transit Hub"):
            st.session_state.scenario = "denver_co"

    st.markdown("### Or Configure Your Own")
    cities = loader.list_cities()
    city_options = {c["name"]: c["slug"] for c in cities}

    selected_city_name = st.selectbox("City", list(city_options.keys()))
    city_slug = city_options[selected_city_name]

    col1, col2 = st.columns(2)
    with col1:
        lot_area = st.number_input("Lot Area (sq ft)", min_value=5000,
                                    max_value=500000, value=43560, step=1000)
        budget = st.number_input("Budget ($)", min_value=500000,
                                  max_value=50000000, value=5000000, step=100000,
                                  format="%d")
    with col2:
        project_type = st.selectbox(
            "Project Type",
            ["mixed_use", "community_park", "affordable_housing"],
            format_func=lambda x: x.replace("_", " ").title()
        )

    if st.button("⚖️ Convene the Courtroom", type="primary", use_container_width=True):
        proposal = state_mgr.create_initial_proposal(
            city_slug, lot_area, budget, project_type
        )
        st.session_state.proposal = proposal
        st.session_state.city_slug = city_slug
        st.session_state.stage = "debating"
        st.rerun()

# ── Stage: Debating ────────────────────────────────────────────────────────────

elif st.session_state.stage == "debating":
    st.title("⚖️ Agents Are Deliberating...")
    st.info("Three specialized agents are analyzing different aspects of this location. Round 1 runs in parallel. Round 2 agents respond to each other.")

    progress = st.progress(0)
    status = st.empty()

    with st.spinner("Running debate..."):
        status.text("Round 1: Agents analyzing independently...")
        progress.progress(20)

        rounds, final = asyncio.run(
            debate_engine.run_full_debate(st.session_state.proposal)
        )
        progress.progress(100)

    st.session_state.rounds = rounds
    st.session_state.final_proposal = final
    st.session_state.stage = "result"
    st.rerun()

# ── Stage: Result ──────────────────────────────────────────────────────────────

elif st.session_state.stage == "result":
    fp = st.session_state.final_proposal

    st.title("⚖️ Neighborhood Courtroom — Proposal")

    # Scores
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Finance Score", f"{fp.finance_score:.0f}/100" if fp.finance_score else "—")
    col2.metric("🌿 Climate Score", f"{fp.climate_score:.0f}/100" if fp.climate_score else "—")
    col3.metric("🏘️ Community Score", f"{fp.community_score:.0f}/100" if fp.community_score else "—")
    col4.metric("Budget Remaining", f"${fp.budget_remaining:,.0f}")

    # Site schematic
    st.markdown("### Site Zone Allocation")
    st.markdown(generate_site_schematic(fp), unsafe_allow_html=True)

    # Budget breakdown
    breakdown = calc.itemized_breakdown(fp, st.session_state.city_slug)
    render_budget_chart(breakdown, fp.total_budget)

    # Debate transcript
    st.markdown("### 📜 Debate Transcript")
    render_debate_transcript(
        st.session_state.rounds,
        st.session_state.rounds[-1].detected_conflicts
    )

    # Audit trail
    with st.expander("🔍 Full Audit Trail (Change Log)"):
        for entry in fp.change_log:
            st.json(entry)

    # Override panel
    st.markdown("---")
    st.markdown("### 🎛️ Human Override")
    st.caption("Lock a parameter and watch agents renegotiate around your decision.")

    override_param = st.selectbox(
        "Parameter to Lock",
        ["green_space_pct", "budget_ceiling"],
        format_func=lambda x: OverrideEngine.OVERRIDABLE_PARAMETERS[x]["label"]
    )
    param_config = OverrideEngine.OVERRIDABLE_PARAMETERS[override_param]
    override_value = st.slider(
        param_config["label"],
        min_value=float(param_config["min"]),
        max_value=float(param_config["max"]),
        value=float(getattr(fp, override_param) or param_config["min"]),
    )

    if st.button("🔒 Lock & Re-Negotiate", type="primary"):
        locked_proposal = override_engine.apply_override(
            fp, override_param, override_value
        )
        st.session_state.pre_override_proposal = fp
        st.session_state.proposal = locked_proposal
        st.session_state.stage = "override_debating"
        st.rerun()
```

---

## Day-by-Day Implementation Plan

### Days 1–2: Foundation + Kill Test

**Day 1 — Data First (8 hours)**

Morning (0–4h):
- Create the full `data/` directory and JSON schema
- Populate `cities.json` with 40 cities (list below)
- Populate `demographics.json` for all 40 cities using ACS data pulled offline
  (Census Reporter at censusreporter.org provides clean exports — no API key required)
- Write `DataLoader` class and `validate_dataset.py`
- Run validator — zero null values allowed before proceeding

Afternoon (4–8h):
- Populate `climate.json` using ASHRAE climate zone map (free PDF) + NOAA data
- Populate `walkability.json` using Walk Score website manually for 40 cities
  (free at walkscore.com, takes ~90 min for 40 cities)
- Populate `construction_costs.json` using RSMeans city cost index (publicly available)
- Run `validate_dataset.py` again — all 40 cities must return clean data

**Kill Test #1:** `DataLoader().get_demographics("phoenix_az")` returns a dict
with all 9 keys populated with non-null, plausible values.
If this fails, something is wrong with your JSON — fix before proceeding.

---

**Day 2 — Pydantic Models + Base Agent (8 hours)**

Morning (0–4h):
- Implement all Pydantic models (`ProposalState`, `AgentOutput`,
  `ConflictFlag`, `DebateRound`)
- Write `test_models.py` — create instances, serialize to JSON, deserialize back
- Implement `CostCalculator` with itemized breakdown
- Implement `StateManager.create_initial_proposal()` for all 3 project types

Afternoon (4–8h):
- Implement `BaseAgent` with structured output parsing
- Implement `FinanceAgent` (simplest — pure cost reasoning)
- Test: call `FinanceAgent.run()` on a test proposal 5 times
- **Kill Test #2:** All 5 calls return valid `AgentOutput` Pydantic objects
  with non-null evidence citing actual values from `construction_costs.json`
- If >1 in 5 fails JSON validation, fix prompt before Day 3

---

### Days 3–4: Agents Complete + Conflict Engine

**Day 3 — Climate + Community Agents (8 hours)**

Morning (0–4h):
- Implement `ClimateAgent` — test 5 runs, same validation criteria
- Verify: Climate Agent evidence cites `heat_island_risk` values and
  `recommended_min_green_cover_pct` from `climate.json`
- If agents agree too readily: increase adversarial language in system prompts,
  add explicit "you MUST flag anything below your threshold" instructions

Afternoon (4–8h):
- Implement `CommunityAgent` — test 5 runs
- Verify: Community Agent evidence cites poverty_rate, pct_age_65_plus
  from `demographics.json` as actual numbers
- Run all 3 agents on the same Phoenix proposal
- **Kill Test #3:** Finance and Climate scores differ by ≥35 points on at least
  1 of 5 runs. If they never conflict, system is broken — fix prompts.

---

**Day 4 — Conflict Detection + State Management (8 hours)**

Morning (0–4h):
- Implement `ConflictDetector` with score-gap detection
- Implement `StateManager.synthesize()` — apply non-contested changes, respect locks
- Test: given 3 agent outputs with known scores, `ConflictDetector.detect()` returns
  expected conflicts

Afternoon (4–8h):
- Implement `engine/state.py` diff logic
- Implement `tools/diff.py` — `generate_diff_table()`
- **Kill Test #4:** Apply a change via one agent, call `diff()`, get a non-empty
  list of changed fields with correct before/after values
- Write `tests/test_conflict.py` and `tests/test_state.py`

---

### Days 5–6: Debate Engine

**Day 5 — Debate Loop (8 hours)**

Morning (0–4h):
- Implement `DebateEngine.run_round()` — synchronous version first, no async
- Test Round 1: all 3 agents run and return structured output
- Test Round 2: agents receive Round 1 outputs in their prompt and reference them

Afternoon (4–8h):
- Add `asyncio.to_thread()` for parallel Round 1 execution
- Implement `run_full_debate()` — two rounds, returns `(rounds, final_proposal)`
- Time the full run: target <90 seconds
- **Kill Test #5:** Full debate runs end-to-end in <90 seconds and produces
  a `final_proposal` with `change_log` containing ≥2 entries attributed to agents

---

**Day 6 — Override Engine (8 hours)**

Morning (0–4h):
- Implement `OverrideEngine.apply_override()` and `run_post_override_debate()`
- Test: lock `green_space_pct` at 35%, run post-override debate
- Verify: final proposal has `green_space_pct == 35.0` (lock respected)
- Verify: `change_log` contains a "human" entry for the lock
- Verify: at least 1 other field changed as agents adjusted around the lock

Afternoon (4–8h):
- Implement `generate_diff_table(before, after)` with override scenario
- Test all 3 scenarios (phoenix mixed-use, detroit brownfield, denver transit)
  with both override types
- Fix any agents that ignore locked constraints

---

### Days 7–8: Visual Output

**Day 7 — Site Schematic + Charts (8 hours)**

Morning (0–4h):
- Implement `generate_site_schematic()` — SVG zone grid
- Test with various zone allocations — edge cases: 0% housing, 80% green space
- Ensure SVG renders correctly in browser (open as HTML file to verify)

Afternoon (4–8h):
- Implement `render_budget_chart()` — horizontal bar chart using plotly
  (budget by category, with total vs. ceiling line)
- Implement `render_score_radar()` — radar chart showing agent scores
  before/after override
- Generate sample outputs for all 3 pre-built scenarios, save as screenshots
  for documentation

---

**Day 8 — Debate Transcript UI (8 hours)**

Morning (0–4h):
- Implement `render_debate_transcript()` in Streamlit
- Color-code by agent (blue/green/orange)
- Show evidence items in expandable sections
- Show conflict flags with severity indicators

Afternoon (4–8h):
- Implement `render_diff_table()` — before/after override comparison
- Implement full audit trail viewer (JSON formatted with timestamps)
- Test all UI components with all 3 scenarios
- Fix rendering issues (text overflow, long evidence strings, etc.)

---

### Days 9–10: Streamlit Integration

**Day 9 — Wire Everything Together (8 hours)**

Morning (0–4h):
- Build `app.py` stage machine: input → debating → result → override → override_result
- Implement input panel: city selector, lot area, budget, project type
- Implement 3 quick-start scenario buttons (pre-loaded, skip input)

Afternoon (4–8h):
- Wire debate engine to Streamlit session state
- Implement progress indicators during debate
- Implement result stage: schematic + budget chart + score metrics
- End-to-end test: click quick-start Phoenix → see full result

---

**Day 10 — Override UI + Polish (8 hours)**

Morning (0–4h):
- Implement override panel in result stage
- Wire override to post-override debate
- Implement override result stage: shows diff table + new schematic + new scores
- Test both override parameters on all 3 scenarios

Afternoon (4–8h):
- UI polish: consistent styling, readable fonts, clear section headers
- Add city data summary panel (show actual data values agents are using)
- Add "Why multiple agents?" info panel explaining data separation
- Mobile responsiveness check

---

### Days 11–12: Deploy + Pre-built Scenarios

**Day 11 — Deployment (8 hours)**

Morning (0–4h):
- Set up `.streamlit/secrets.toml.example`
- Push to GitHub (public repo, no hardcoded keys)
- Deploy to Streamlit Community Cloud
- Test from fresh browser with no local environment

Afternoon (4–8h):
- Fix any deployment-specific issues (import paths, secret access, file paths)
- Test all 3 quick-start scenarios on live deployment
- Test override flow on live deployment
- Measure live performance — if >2 minutes, profile and optimize

---

**Day 12 — Pre-built Scenarios + Cache (8 hours)**

Morning (0–4h):
- Build `data/scenarios/` — pre-run and serialize 3 complete scenario results
  as JSON (full rounds + final proposals)
- Quick-start buttons load from cache, not from live LLM calls
  → instant demo, zero API cost, zero failure risk during judging

Afternoon (4–8h):
- Add "Live Mode" toggle that runs real LLM calls for any of the 40 cities
- Test cache vs. live mode side by side
- Write `scripts/preprocess_scenarios.py` to regenerate cache

---

### Days 13–14: Documentation + Write-up

**Day 13 — README + Architecture Docs (8 hours)**

Morning (0–4h):
- Write `README.md`:
  - What it is (3 sentences)
  - Why multiple agents (concrete example with data)
  - Live demo URL
  - Architecture diagram (ASCII or Mermaid)
  - Data sources (Census, NOAA, RSMeans — with links to original sources)
  - How to run locally

Afternoon (4–8h):
- Write competition write-up section: "Why agents are essential"
  - Show Finance Agent's context (cost data only)
  - Show Climate Agent's context (climate data only)
  - Show Community Agent's context (demographic data only)
  - Show a real example where their outputs conflicted and the negotiation produced
    something different from any single agent's proposal
- Add screenshots: input form, debate transcript, site schematic, override diff

---

**Day 14 — Final Polish + Submission (8 hours)**

Morning (0–4h):
- Record a 3-minute demo video:
  - 0:00 — Quick-start Phoenix scenario (instant via cache)
  - 0:30 — Walk through debate transcript, point to evidence citations
  - 1:30 — Show a high-severity conflict (Finance vs. Climate)
  - 2:00 — Lock green space at 35%, run live re-negotiation
  - 2:30 — Show diff table and new site schematic
  - 3:00 — "This couldn't come from a single LLM call" — point to data provenance
- Upload to YouTube/Loom, add to README

Afternoon (4–8h):
- Final deployment test
- Review competition submission requirements
- Submit

---

## The 40 Cities

**Northeast (10):** New York NY, Philadelphia PA, Boston MA, Pittsburgh PA,
Buffalo NY, Providence RI, Hartford CT, Newark NJ, Baltimore MD, Washington DC

**South (10):** Houston TX, Phoenix AZ, San Antonio TX, Dallas TX, Jacksonville FL,
Austin TX, Charlotte NC, Memphis TN, Louisville KY, New Orleans LA

**Midwest (10):** Chicago IL, Indianapolis IN, Columbus OH, Detroit MI,
Milwaukee WI, Kansas City MO, Omaha NE, Minneapolis MN, Cleveland OH, St. Louis MO

**West (10):** Los Angeles CA, San Diego CA, Denver CO, Seattle WA,
Portland OR, Las Vegas NV, Sacramento CA, Fresno CA, Tucson AZ, Albuquerque NM

---

## What Makes Judges Say "A Single LLM Couldn't Do This"

There are exactly three moments in the system that prove this claim. Script your demo around them.

**Moment 1 — Data provenance is visible.**
In the debate transcript, Climate Agent says:
*"Phoenix has a heat island risk score of 5/5 and an average summer temperature of 104°F with an urban heat penalty of 7°F. The recommended minimum green cover for climate zone 2B is 30%. The current proposal at 15% is critically insufficient."*

Finance Agent says:
*"Activated green space costs $28.14/sqft in Phoenix (city cost index: 0.89). Increasing green space from 15% to 30% on a 43,560 sqft lot requires 6,534 additional sqft at a hard cost of $183,877 plus 28% soft costs and 12% contingency = $263,400 additional spend. Current budget headroom: $180,000. This creates a $83,400 shortfall."*

These two outputs cite completely different datasets that no single agent — and no single LLM call — was given access to simultaneously. This is the core proof.

**Moment 2 — The negotiated output is different from any individual proposal.**
Finance proposed 15% green space. Climate proposed 40%. The negotiated outcome: 28% green space with a green roof on the parking structure (Climate Agent's compromise proposal from Round 2, accepted because it partially offsets heat risk at lower cost than full ground-level green space). Neither agent proposed exactly this. The synthesis only emerged from the negotiation.

**Moment 3 — The override changes the proposal in a causally traceable way.**
User locks green space at 35%. Finance Agent re-runs and flags a $140,000 budget overrun. Finance proposes reducing housing units from 40 to 32 to compensate. Community Agent objects — 8 fewer units in a tract with 17.2% poverty rate means 14 fewer affordable units. Counter-proposal: reduce parking from 60 to 45 spaces. Accepted. The diff table shows: housing_units unchanged, parking_spaces −15, budget_remaining +$87,000. The causal chain is explicit, attributed, and visible. A single LLM cannot produce a causally attributed multi-step state diff because it has no concept of which agent said what when.

---

## Critical Path Summary

If you run out of time, cut in this order:

1. Cut radar chart (keep budget bar chart — it's more informative)
2. Cut "Live Mode" (pre-built scenarios are enough for judging)
3. Cut mobile optimization
4. Cut second override parameter (one perfect override beats two broken ones)
5. Cut cities below 40 (20 cities is fine — range matters more than count)

Never cut:
- Real preprocessed data (all JSON files fully populated)
- Structured Pydantic output (non-negotiable for audit trail)
- Site schematic SVG (only visual output — cannot be cut)
- Deployed URL (judges who can't access it cannot score it)
- The diff table (primary proof of override causality)