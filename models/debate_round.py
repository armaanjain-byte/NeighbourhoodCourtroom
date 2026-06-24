from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from .proposal import Proposal
from .agent_output import AgentOutput
from .conflict import Conflict
from .agent_opinion import AgentOpinion


class DebateRound(BaseModel):
    round_number: int
    opening_state: Proposal
    agent_outputs: dict[str, AgentOutput]
    detected_conflicts: list[Conflict]
    closing_state: Proposal
    engine_summary: str
    round_1_opinions: dict[str, AgentOpinion] = Field(
        default_factory=dict,
        description="Initial AgentOpinions collected before cross-agent awareness."
    )
    round_2_opinions: dict[str, AgentOpinion] = Field(
        default_factory=dict,
        description="Revised AgentOpinions after each agent has seen Round 1 opponent opinions."
    )
    round_3_opinions: dict[str, AgentOpinion] = Field(
        default_factory=dict,
        description="Final attempt AgentOpinions collected specifically for unresolved high-severity conflicts."
    )

