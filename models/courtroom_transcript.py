from typing import Literal, Optional
from pydantic import BaseModel, Field

class TranscriptEntry(BaseModel):
    round_number: int
    agent: str
    statement_type: Literal["tension", "position", "evidence", "objection", "support"]
    target_agent: Optional[str] = None
    content: str
    is_grounding_warning: bool = False

class CourtroomTranscript(BaseModel):
    entries: list[TranscriptEntry] = Field(default_factory=list)
