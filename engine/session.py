"""Session Engine — Manages the lifecycle of a courtroom case.

Purpose:
    Maintains the state of an active negotiation session, orchestrating multiple
    debate rounds, recording human overrides, and tracking the final verdict.

Dependencies:
    models.proposal.Proposal, models.debate_round.DebateRound
"""

from typing import Any, Literal
from uuid import uuid4
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from models.proposal import Proposal
from models.debate_round import DebateRound
from models.agent_output import AgentOutput
from engine.debate import run_debate_round
from engine.state import apply_human_override
from agents.base_agent import BaseAgent
from tools.cost_calculator import CostCalculator

SessionStatus = Literal["CREATED", "IN_PROGRESS", "WAITING_FOR_JUDGE", "COMPLETED"]


class CourtroomSession(BaseModel):
    """Represents a single active courtroom negotiation session."""
    
    session_id: str = Field(default_factory=lambda: uuid4().hex[:8])
    current_proposal: Proposal
    debate_rounds: list[DebateRound] = Field(default_factory=list)
    override_history: list[dict[str, Any]] = Field(default_factory=list)
    status: SessionStatus = "CREATED"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def run_round(self, agents: list[BaseAgent], context: dict[str, Any], cost_calculator: CostCalculator) -> DebateRound:
        """Run a single debate round using the provided agents.

        Parameters
        ----------
        agents : list[BaseAgent]
            The specialized agents participating in the round.
        context : dict[str, Any]
            Additional data or configuration provided to the agents.
        cost_calculator : CostCalculator
            The single source of truth for computing costs.

        Returns
        -------
        DebateRound
            The resulting DebateRound after all conflicts are processed.
        """
        if self.status in ["WAITING_FOR_JUDGE", "COMPLETED"]:
            raise ValueError(f"Cannot run debate round in status: {self.status}")

        self.status = "IN_PROGRESS"

        # 1. Collect agent outputs
        agent_outputs: dict[str, AgentOutput] = {}
        for agent in agents:
            output = agent.evaluate(self.current_proposal, context)
            agent_outputs[agent.agent_name] = output

        # 2. Run debate orchestration
        round_number = len(self.debate_rounds) + 1
        debate_round, updated_proposal = run_debate_round(
            self.current_proposal,
            agent_outputs,
            round_number=round_number,
            cost_calculator=cost_calculator
        )

        # 3. Update session state
        self.debate_rounds.append(debate_round)
        self.current_proposal = updated_proposal

        # 4. Check for high-severity conflicts requiring a judge
        if any(c.disagreement_severity == "high" for c in debate_round.detected_conflicts):
            self.status = "WAITING_FOR_JUDGE"

        return debate_round

    def apply_override(self, parameter: str, value: float) -> Proposal:
        """Apply a human override to a parameter, locking it from future agent edits.

        Parameters
        ----------
        parameter : str
            The name of the parameter to lock.
        value : float
            The forced value.

        Returns
        -------
        Proposal
            The newly updated Proposal.
        """
        if self.status == "COMPLETED":
            raise ValueError("Cannot apply overrides to a completed session.")

        updated = apply_human_override(self.current_proposal, parameter, value)
        self.current_proposal = updated

        self.override_history.append({
            "parameter": parameter,
            "value": value,
            "round_number": len(self.debate_rounds),
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        if self.status == "WAITING_FOR_JUDGE":
            self.status = "IN_PROGRESS"

        return self.current_proposal

    def get_current_state(self) -> Proposal:
        """Return the current active proposal."""
        return self.current_proposal

    def get_debate_history(self) -> list[DebateRound]:
        """Return the list of all recorded debate rounds."""
        return self.debate_rounds

    def generate_verdict(self) -> dict[str, Any]:
        """Finalize the session and generate the case verdict.

        Returns
        -------
        dict[str, Any]
            The final verdict dictionary containing the proposal, total rounds,
            unresolved conflicts, and an audit summary.
        """
        self.status = "COMPLETED"

        unresolved_conflicts = []
        if self.debate_rounds:
            last_round = self.debate_rounds[-1]
            for c in last_round.detected_conflicts:
                if c.disagreement_severity == "high" and c.parameter not in self.current_proposal.human_locks:
                    unresolved_conflicts.append(c.parameter)

        audit_summary = (
            f"Courtroom session {self.session_id} concluded. "
            f"Ran {len(self.debate_rounds)} debate rounds. "
            f"Applied {len(self.override_history)} human overrides."
        )

        return {
            "final_proposal": self.current_proposal,
            "total_rounds": len(self.debate_rounds),
            "unresolved_conflicts": unresolved_conflicts,
            "audit_summary": audit_summary
        }


def create_session(initial_proposal: Proposal) -> CourtroomSession:
    """Initialize a new courtroom session.

    Parameters
    ----------
    initial_proposal : Proposal
        The opening state of the neighborhood before any debate.

    Returns
    -------
    CourtroomSession
        A fresh session in the CREATED state.
    """
    return CourtroomSession(current_proposal=initial_proposal)
