"""Base Agent Module.

Purpose:
    Defines the abstract contract for all agents in the Neighborhood Courtroom.
    Provides shared validation, output construction, and parameter filtering
    to ensure deterministic integration with the rest of the engine.

Dependencies:
    models.proposal.Proposal, models.agent_output.AgentOutput, engine.state.MUTABLE_PARAMETERS
"""

import abc
from typing import Any

from models.proposal import Proposal
from models.agent_output import AgentOutput
from engine.state import MUTABLE_PARAMETERS


class AgentValidationError(ValueError):
    """Raised when an agent produces an invalid output or violates schema rules."""
    pass


class AgentExecutionError(RuntimeError):
    """Raised when an agent fails to execute its evaluation logic."""
    pass


class BaseAgent(abc.ABC):
    """Abstract Base Class for all Neighborhood Courtroom agents."""

    @property
    @abc.abstractmethod
    def agent_name(self) -> str:
        """The identifier of the agent (e.g. 'finance', 'climate', 'community')."""
        pass  # pragma: no cover

    @abc.abstractmethod
    def evaluate(self, proposal: Proposal, context: dict[str, Any]) -> AgentOutput:
        """Evaluate a proposal and return recommended changes.

        Parameters
        ----------
        proposal : Proposal
            The current state of the neighborhood proposal.
        context : dict[str, Any]
            Additional domain context (e.g. data JSON payloads, round config).

        Returns
        -------
        AgentOutput
            The structured output containing the agent's verdict and proposed changes.
        """
        pass  # pragma: no cover

    def filter_unknown_parameters(self, changes: dict[str, float]) -> dict[str, float]:
        """Return a new dict containing only parameters that exist in MUTABLE_PARAMETERS.

        Parameters
        ----------
        changes : dict[str, float]
            The raw proposed changes.

        Returns
        -------
        dict[str, float]
            Filtered changes with only known parameters.
        """
        return {k: v for k, v in changes.items() if k in MUTABLE_PARAMETERS}

    def validate_proposed_changes(self, changes: dict[str, float]) -> None:
        """Verify that all proposed changes target known mutable parameters.

        Parameters
        ----------
        changes : dict[str, float]
            The proposed changes.

        Raises
        ------
        AgentValidationError
            If any parameter is not in MUTABLE_PARAMETERS.
        """
        for param in changes:
            if param not in MUTABLE_PARAMETERS:
                raise AgentValidationError(
                    f"Agent '{self.agent_name}' proposed unknown parameter '{param}'. "
                    f"Allowed parameters are: {sorted(MUTABLE_PARAMETERS)}"
                )

    def validate_output(self, score: float, verdict: str, changes: dict[str, float]) -> None:
        """Validate core output constraints (score range, valid verdict, parameters).

        Parameters
        ----------
        score : float
            The confidence/approval score.
        verdict : str
            The outcome (accept, modify, reject).
        changes : dict[str, float]
            The proposed changes.

        Raises
        ------
        AgentValidationError
            If the score is out of bounds [0, 100], the verdict is invalid,
            or the parameters are unknown.
        """
        if not (0.0 <= score <= 100.0):
            raise AgentValidationError(
                f"Agent '{self.agent_name}' produced invalid score {score}. "
                "Score must be between 0 and 100."
            )

        if verdict not in ("accept", "modify", "reject"):
            raise AgentValidationError(
                f"Agent '{self.agent_name}' produced invalid verdict '{verdict}'. "
                "Verdict must be 'accept', 'modify', or 'reject'."
            )

        self.validate_proposed_changes(changes)

    def build_output(
        self,
        score: float,
        verdict: str,
        changes: dict[str, float],
        reasoning: str,
    ) -> AgentOutput:
        """Construct and validate an AgentOutput object.

        Parameters
        ----------
        score : float
            The approval score (0–100).
        verdict : str
            The verdict ('accept', 'modify', 'reject').
        changes : dict[str, float]
            The dictionary of proposed parameter changes.
        reasoning : str
            The justification for the verdict and changes.

        Returns
        -------
        AgentOutput
            The validated AgentOutput object.

        Raises
        ------
        AgentValidationError
            If the inputs violate the validation rules.
        """
        # Enforce validation rules
        self.validate_output(score, verdict, changes)

        return AgentOutput(
            agent_name=self.agent_name,
            score=score,
            verdict=verdict,  # type: ignore
            proposed_changes=changes,
            reasoning_and_evidence=reasoning,
        )
