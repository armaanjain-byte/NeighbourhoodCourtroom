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
from models.agent_opinion import AgentOpinion
from models.courtroom_transcript import CourtroomTranscript, TranscriptEntry
from engine.debate import run_debate_round
from engine.override import apply_human_override
from agents.base_agent import BaseAgent
from tools.cost_calculator import CostCalculator

SessionStatus = Literal["CREATED", "IN_PROGRESS", "WAITING_FOR_JUDGE", "COMPLETED"]


class CourtroomSession(BaseModel):
    """Represents a single active courtroom negotiation session."""
    
    session_id: str = Field(default_factory=lambda: uuid4().hex[:8])
    current_proposal: Proposal
    debate_rounds: list[DebateRound] = Field(default_factory=list)
    override_history: list[dict[str, Any]] = Field(default_factory=list)
    transcript: CourtroomTranscript = Field(default_factory=CourtroomTranscript)
    status: SessionStatus = "CREATED"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def run_round(self, agents: list[BaseAgent], context: dict[str, Any], cost_calculator: CostCalculator) -> DebateRound:
        """Run a single debate round using the provided agents.

        Two-phase opinion collection:
            Phase A — Round 1 (independent): each agent generates an opinion
                      based only on its own domain data slice.
            Phase B — Round 2 (cross-agent rebuttal): each agent sees the Round 1
                      opinions of the other agents and is instructed to explicitly
                      address conflicts, maintain its domain position, and propose
                      compromises where needed.

        The DebateRound records both round_1_opinions and round_2_opinions.
        The conflict-resolution engine uses the Round 1 deterministic AgentOutputs
        (not the LLM opinions) to determine the closing proposal state.

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
            The resulting DebateRound after all conflicts are processed,
            with both round_1_opinions and round_2_opinions populated.
        """
        if self.status in ["WAITING_FOR_JUDGE", "COMPLETED"]:
            raise ValueError(f"Cannot run debate round in status: {self.status}")

        self.status = "IN_PROGRESS"
        debate_round_number = len(self.debate_rounds) + 1



        # ── Phase A: Round 1 opinions (independent, domain-scoped) ──────────
        round_1_opinions: dict[str, AgentOpinion] = {}
        for agent in agents:
            opinion = agent.generate_opinion(
                self.current_proposal,
                context,
                round_number=1,
                opponent_opinions=None,
            )
            round_1_opinions[agent.agent_name] = opinion

            # Record Round 1 opinion to transcript
            self.transcript.entries.append(TranscriptEntry(
                round_number=debate_round_number,
                agent=agent.agent_name,
                statement_type="position",
                content=f"[R1] **{opinion.position}**\n\n{opinion.reasoning}"
            ))
            for ev in opinion.evidence:
                self.transcript.entries.append(TranscriptEntry(
                    round_number=debate_round_number,
                    agent=agent.agent_name,
                    statement_type="evidence",
                    content=ev
                ))

        # ── Phase B: Round 2 opinions (cross-agent rebuttal) ────────────────
        round_2_opinions: dict[str, AgentOpinion] = {}
        for agent in agents:
            # Each agent receives Round 1 opinions of the OTHER two agents only
            opponent_r1 = {
                name: op
                for name, op in round_1_opinions.items()
                if name != agent.agent_name
            }
            opinion = agent.generate_opinion(
                self.current_proposal,
                context,
                round_number=2,
                opponent_opinions=opponent_r1,
            )
            round_2_opinions[agent.agent_name] = opinion

            # Record Round 2 position to transcript
            self.transcript.entries.append(TranscriptEntry(
                round_number=debate_round_number,
                agent=agent.agent_name,
                statement_type="position",
                content=f"[R2] **{opinion.position}**\n\n{opinion.reasoning}"
            ))
            for ev in opinion.evidence:
                self.transcript.entries.append(TranscriptEntry(
                    round_number=debate_round_number,
                    agent=agent.agent_name,
                    statement_type="evidence",
                    content=ev
                ))
            for obj in opinion.objections:
                self.transcript.entries.append(TranscriptEntry(
                    round_number=debate_round_number,
                    agent=agent.agent_name,
                    statement_type="objection",
                    target_agent=obj.target_agent,
                    content=obj.reason
                ))
            for sup in opinion.supports:
                self.transcript.entries.append(TranscriptEntry(
                    round_number=debate_round_number,
                    agent=agent.agent_name,
                    statement_type="support",
                    target_agent=sup.target_agent,
                    content=sup.reason
                ))

        # ── LLM-derived Phase (Replaces deterministic Phase 1 inputs) ────────
        llm_agent_outputs: dict[str, AgentOutput] = {}
        for agent_name, opinion in round_2_opinions.items():
            llm_agent_outputs[agent_name] = AgentOutput(
                agent_name=agent_name,
                score=opinion.score,
                verdict="modify" if opinion.recommendation else "accept",
                proposed_changes=opinion.recommendation,
                reasoning_and_evidence=opinion.reasoning
            )

        # ── Debate orchestration (deterministic conflict resolution) ─────────
        debate_round, updated_proposal = run_debate_round(
            self.current_proposal,
            llm_agent_outputs,
            round_number=debate_round_number,
            cost_calculator=cost_calculator
        )

        # ── Attach opinion records to the DebateRound ────────────────────────
        debate_round.round_1_opinions = round_1_opinions
        debate_round.round_2_opinions = round_2_opinions

        # ── Update session state ─────────────────────────────────────────────
        self.debate_rounds.append(debate_round)
        self.current_proposal = updated_proposal

        # ── Check for high-severity conflicts requiring a judge ───────────────
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
