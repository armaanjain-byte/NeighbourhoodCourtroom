"""History Engine — Explainability and audit tracking.

Purpose:
    Stores and reconstructs the debate history, conflicts, overrides, and 
    resolutions across all rounds. It provides deep explainability for any 
    parameter's lifecycle in the courtroom.

Dependencies:
    models.conflict.Conflict
"""

from typing import Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from models.conflict import Conflict


class ConflictHistory(BaseModel):
    round_number: int
    parameter: str
    agent_a: str
    agent_b: str
    proposed_value_a: float
    proposed_value_b: float
    severity: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ResolutionHistory(BaseModel):
    round_number: int
    parameter: str
    resolution_type: str
    resolved_value: Optional[float] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class OverrideHistory(BaseModel):
    round_number: int
    parameter: str
    locked_value: float
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DecisionHistory(BaseModel):
    round_number: int
    agent: str
    parameter: str
    proposed_value: float
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AuditHistory(BaseModel):
    """Tracks all events across the lifecycle of a session."""
    
    conflicts: list[ConflictHistory] = Field(default_factory=list)
    resolutions: list[ResolutionHistory] = Field(default_factory=list)
    overrides: list[OverrideHistory] = Field(default_factory=list)
    decisions: list[DecisionHistory] = Field(default_factory=list)
    
    def record_conflict(self, round_number: int, conflict: Conflict) -> None:
        """Log a detected conflict."""
        self.conflicts.append(
            ConflictHistory(
                round_number=round_number,
                parameter=conflict.parameter,
                agent_a=conflict.agent_a,
                agent_b=conflict.agent_b,
                proposed_value_a=conflict.proposed_value_a,
                proposed_value_b=conflict.proposed_value_b,
                severity=conflict.disagreement_severity
            )
        )
        
    def record_resolution(self, round_number: int, parameter: str, resolution_type: str, resolved_value: Optional[float] = None) -> None:
        """Log how a conflict was resolved or if it was escalated."""
        self.resolutions.append(
            ResolutionHistory(
                round_number=round_number,
                parameter=parameter,
                resolution_type=resolution_type,
                resolved_value=resolved_value
            )
        )
        
    def record_override(self, round_number: int, parameter: str, locked_value: float) -> None:
        """Log a human judge override."""
        self.overrides.append(
            OverrideHistory(
                round_number=round_number,
                parameter=parameter,
                locked_value=locked_value
            )
        )
        
    def record_decision(self, round_number: int, agent: str, parameter: str, proposed_value: float) -> None:
        """Log an agent's proposed parameter modification."""
        self.decisions.append(
            DecisionHistory(
                round_number=round_number,
                agent=agent,
                parameter=parameter,
                proposed_value=proposed_value
            )
        )
        
    def get_conflict_timeline(self) -> list[ConflictHistory]:
        """Return all conflicts in chronological order."""
        return sorted(self.conflicts, key=lambda x: x.round_number)
        
    def get_parameter_history(self, parameter: str) -> dict[str, list[Any]]:
        """Return all events related to a specific parameter."""
        return {
            "decisions": sorted([d for d in self.decisions if d.parameter == parameter], key=lambda x: x.round_number),
            "conflicts": sorted([c for c in self.conflicts if c.parameter == parameter], key=lambda x: x.round_number),
            "resolutions": sorted([r for r in self.resolutions if r.parameter == parameter], key=lambda x: x.round_number),
            "overrides": sorted([o for o in self.overrides if o.parameter == parameter], key=lambda x: x.round_number)
        }
        
    def get_agent_history(self, agent: str) -> list[DecisionHistory]:
        """Return all decisions made by a specific agent."""
        return sorted([d for d in self.decisions if d.agent == agent], key=lambda x: x.round_number)
        
    def generate_audit_report(self) -> dict[str, int]:
        """Summarize the total activity in the session."""
        return {
            "total_decisions": len(self.decisions),
            "total_conflicts": len(self.conflicts),
            "total_resolutions": len(self.resolutions),
            "total_overrides": len(self.overrides)
        }
        
    def explain_parameter(self, parameter_name: str) -> str:
        """Generate a human-readable narrative explaining a parameter's evolution.
        
        Returns formatted text showing what agents proposed, conflicts, and resolutions.
        """
        history = self.get_parameter_history(parameter_name)
        
        if not any(history.values()):
            return f"No history found for parameter: {parameter_name}"
            
        max_round = 0
        for event_list in history.values():
            if event_list:
                max_round = max(max_round, max(x.round_number for x in event_list))
                
        lines = []
        final_value = None
        
        agent_emojis = {"finance": "👔", "climate": "🌳", "community": "🏘️"}
        
        for r in range(1, max_round + 1):
            round_lines = []
            
            # Agent Decisions
            decisions = [d for d in history["decisions"] if d.round_number == r]
            decisions = sorted(decisions, key=lambda d: d.agent)
            for d in decisions:
                emoji = agent_emojis.get(d.agent.lower(), "🤖")
                round_lines.append(f"**{emoji} {d.agent.capitalize()} Agent**")
                round_lines.append(f"Proposed: `{d.proposed_value:g}`\n")
                
            # Conflicts
            conflicts = [c for c in history["conflicts"] if c.round_number == r]
            if conflicts:
                if any(c.severity == "high" for c in conflicts):
                    round_lines.append("🛑 **SYSTEM HALTED: High Severity Conflict Detected**\n")
                else:
                    round_lines.append("⚠️ **Conflict Detected**\n")
                
            # Resolutions
            resolutions = [res for res in history["resolutions"] if res.round_number == r]
            for res in resolutions:
                if res.resolution_type == "human review required":
                    round_lines.append("*Status: Awaiting human review*")
                else:
                    if res.resolved_value is not None:
                        round_lines.append(f"*Resolved by {res.resolution_type} to `{res.resolved_value:g}`*")
                        final_value = res.resolved_value
                    else:
                        round_lines.append(f"*Resolved by {res.resolution_type}*")
                    
            # Overrides
            overrides = [o for o in history["overrides"] if o.round_number == r]
            for o in overrides:
                round_lines.append("────────────────\n")
                round_lines.append("**🧑‍⚖️ Judge Override**\n")
                round_lines.append(f"Forced value to `{o.locked_value:g}`")
                final_value = o.locked_value
                
            if round_lines:
                lines.append(f"### Round {r}\n")
                lines.extend(round_lines)
                lines.append("\n────────────────\n")
                
        if final_value is not None:
            lines.append(f"### Final Outcome\n\nValue locked at `{final_value:g}`")
        else:
            lines.append("### Final Outcome\n\n*Unresolved or unknown*")
            
        return "\n".join(lines)
