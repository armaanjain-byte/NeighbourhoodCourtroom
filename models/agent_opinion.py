from pydantic import BaseModel, Field


class TargetStatement(BaseModel):
    target_agent: str
    engages_with: str
    reason: str


class AgentOpinion(BaseModel):
    agent: str
    score: float
    recommendation: dict[str, float]
    tension: str
    position: str
    reasoning: str
    evidence: list[str] = Field(default_factory=list)
    objections: list[TargetStatement] = Field(default_factory=list)
    supports: list[TargetStatement] = Field(default_factory=list)
    confidence: float
    grounding_warnings: list[str] = Field(default_factory=list)
    engagement_warnings: list[str] = Field(default_factory=list)
    concession_rationale: str | None = None
    own_previous_position: dict[str, float] | None = None
    is_fallback: bool = False
    standards_flags: list[dict] = Field(default_factory=list)
