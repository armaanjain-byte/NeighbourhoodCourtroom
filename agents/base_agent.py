"""Base Agent Module.

Purpose:
    Defines the abstract contract for all agents in the Neighborhood Courtroom.
    Provides shared validation, output construction, and parameter filtering
    to ensure deterministic integration with the rest of the engine.

Design (generate_opinion):
    Round 1 (round_number=1):
        Gemini receives the proposal state and this agent's domain data slice.
        It returns score, verdict, proposed_changes, position, reasoning, evidence,
        objections, supports, and confidence.  The returned proposed_changes become
        the authoritative output; evaluate() is the fallback.

    Round 2 (round_number=2):
        Gemini additionally receives the Round 1 AgentOpinion objects of the OTHER
        two agents.  The prompt instructs Gemini to explicitly address every
        conflicting recommendation, maintain its domain position, and propose a
        compromise where a conflict is blocking.  The returned JSON must include
        a non-empty objections[] for each rejection and a supports[] for agreements.

Dependencies:
    models.proposal.Proposal, models.agent_output.AgentOutput, engine.state.MUTABLE_PARAMETERS
"""

import abc
from typing import Any

from models.proposal import Proposal
from models.agent_output import AgentOutput
from models.agent_opinion import AgentOpinion
from engine.state import MUTABLE_PARAMETERS

import os
import json
try:
    import google.generativeai as genai
    HAS_GEMINI = True
except ImportError:
    HAS_GEMINI = False


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
        """Evaluate a proposal and return recommended changes (deterministic fallback).

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

    def generate_opinion(
        self,
        proposal: Proposal,
        context: dict[str, Any],
        data_slice: dict[str, Any] | None = None,
        *,
        round_number: int = 1,
        opponent_opinions: dict[str, AgentOpinion] | None = None,
    ) -> AgentOpinion:
        """Generate an AgentOpinion by asking Gemini to recommend parameter changes.

        Round 1 (round_number=1):
            Gemini receives only the proposal state and this agent's domain data
            slice.  It returns score, verdict, proposed_changes, position,
            reasoning, evidence, objections, supports, and confidence.
            The returned proposed_changes become the authoritative output.

        Round 2 (round_number=2):
            Gemini additionally receives the Round 1 AgentOpinion objects of the
            other agents.  The prompt instructs Gemini to explicitly address every
            conflicting recommendation, maintain its domain position, and propose a
            compromise where a conflict is blocking.

        Falls back to evaluate() if Gemini is unavailable or returns
        invalid/unparseable JSON.

        Parameters
        ----------
        proposal : Proposal
            The current state of the neighborhood proposal.
        context : dict[str, Any]
            Full context dict (passed through to evaluate() fallback only).
        data_slice : dict[str, Any]
            The agent's own domain data (e.g. climate + land_use for ClimateAgent).
            Gemini receives ONLY this slice, not the full context.
        round_number : int
            1 for an independent initial opinion; 2 for a cross-agent-aware rebuttal.
        opponent_opinions : dict[str, AgentOpinion] | None
            Round 1 opinions of the OTHER agents.  Required when round_number == 2;
            ignored when round_number == 1.

        Returns
        -------
        AgentOpinion
            The opinion derived from Gemini's recommendations, or from the
            deterministic fallback if Gemini is unavailable or fails.
        """
        mutable_params = sorted(MUTABLE_PARAMETERS)

        # ── Fallback: no Gemini available ───────────────────────────────────
        if not HAS_GEMINI or not os.environ.get("GEMINI_API_KEY"):
            return self._fallback_opinion(
                proposal, context, reason="Gemini not configured"
            )

        # ── Build system instruction ─────────────────────────────────────────
        system_instruction = (
            f"You are the {self.agent_name.capitalize()} Expert in a city planning simulation. "
            f"Your role is to evaluate a neighborhood development proposal purely from a "
            f"{self.agent_name} perspective. "
            "You must base your analysis ONLY on the domain data provided to you. "
            "Do not invent data. Do not reference information not present in the inputs."
        )

        # ── Build user prompt ────────────────────────────────────────────────
        user_prompt = (
            f"## Current Proposal State\n"
            f"{proposal.model_dump_json(indent=2)}\n\n"
            f"## Your Domain Data ({self.agent_name.upper()})\n"
            f"{json.dumps(data_slice, indent=2)}\n\n"
        )

        if round_number == 2 and opponent_opinions:
            # Serialise opponent Round 1 opinions for Gemini
            opponent_block = "\n".join(
                f"### {name.capitalize()} Agent (Round 1)\n"
                f"- Score: {op.score}\n"
                f"- Position: {op.position}\n"
                f"- Proposed changes: {json.dumps(op.recommendation)}\n"
                f"- Reasoning: {op.reasoning}"
                for name, op in opponent_opinions.items()
                if name != self.agent_name
            )
            user_prompt += (
                f"## Round 1 Results from Other Agents\n"
                f"{opponent_block}\n\n"
                f"## Your Task (Round 2 — Cross-Agent Rebuttal)\n"
                "Round 1 results from other agents are shown above. "
                "You MUST explicitly address any recommendation that conflicts with yours. "
                "Maintain your domain position but propose a compromise if the conflict is blocking.\n\n"
                f"Recommend changes to any or all of these mutable parameters:\n{mutable_params}\n\n"
            )
        else:
            user_prompt += (
                f"## Your Task (Round 1 — Independent Assessment)\n"
                f"Based ONLY on the data above, recommend changes to any or all of these "
                f"mutable parameters:\n{mutable_params}\n\n"
            )

        # ── Shared JSON schema instruction ────────────────────────────────────
        user_prompt += (
            "Return a single strictly-valid JSON object with EXACTLY these fields:\n"
            "{\n"
            '  "score": <float 0.0–100.0, your approval score>,\n'
            '  "verdict": <"accept" | "modify" | "reject">,\n'
            '  "proposed_changes": <dict of param->value; empty dict {} if no changes>,\n'
            '  "position": <string, 1-sentence TLDR of your stance>,\n'
            '  "reasoning": <string, 2-4 sentence explanation>,\n'
            '  "evidence": [<string>, ...],\n'
        )

        if round_number == 2:
            user_prompt += (
                '  "objections": [{"target_agent": <string>, "reason": <string>}, ...],\n'
                '    -- List every opponent recommendation you REJECT and why.\n'
                '       Leave empty [] only if you agree with all opponents.\n'
                '  "supports": [{"target_agent": <string>, "reason": <string>}, ...],\n'
                '    -- List every opponent recommendation you AGREE with.\n'
                '       Leave empty [] only if you object to everything.\n'
            )
        else:
            user_prompt += (
                '  "objections": [],\n'
                '  "supports": [],\n'
            )

        user_prompt += (
            '  "confidence": <float 0.0–1.0>\n'
            "}\n\n"
            f"RULES:\n"
            f"- proposed_changes keys must be from this list only: {mutable_params}\n"
            f"- score must be between 0.0 and 100.0\n"
            f"- verdict must be 'accept' when proposed_changes is empty, 'modify' or 'reject' otherwise\n"
            f"- evidence must be a list of short factual strings referencing the data provided\n"
        )
        if round_number == 2:
            user_prompt += (
                "- objections and supports must each name an agent from: "
                f"{[name for name in (opponent_opinions or {}) if name != self.agent_name]}\n"
            )
        user_prompt += "- Return ONLY the JSON object, no markdown fences, no extra text."

        # ── Call Gemini ───────────────────────────────────────────────────────
        try:
            genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
            model = genai.GenerativeModel(
                "gemini-2.5-flash",
                system_instruction=system_instruction,
            )
            response = model.generate_content(
                user_prompt,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json"
                ),
            )
            raw = response.text.strip()
            data = json.loads(raw)

            # Validate required keys
            required = {
                "score", "verdict", "proposed_changes",
                "position", "reasoning", "evidence", "confidence",
                "objections", "supports",
            }
            if not required.issubset(data.keys()):
                missing = required - data.keys()
                raise ValueError(f"Gemini response missing keys: {missing}")

            # Filter proposed_changes to only known mutable parameters
            filtered_changes = self.filter_unknown_parameters(
                {k: float(v) for k, v in data["proposed_changes"].items()}
            )

            # Validate score and verdict
            score = float(data["score"])
            if not (0.0 <= score <= 100.0):
                raise ValueError(f"Gemini returned out-of-range score: {score}")

            verdict = str(data["verdict"])
            if verdict not in ("accept", "modify", "reject"):
                raise ValueError(f"Gemini returned invalid verdict: {verdict}")

            # Parse objections / supports — tolerate both list-of-dicts and empty
            def _parse_target_list(raw_list: Any) -> list[dict[str, str]]:
                result = []
                for item in raw_list or []:
                    if isinstance(item, dict):
                        result.append({
                            "target_agent": str(item.get("target_agent", "")),
                            "reason": str(item.get("reason", "")),
                        })
                return result

            objections_raw = _parse_target_list(data.get("objections", []))
            supports_raw = _parse_target_list(data.get("supports", []))

            return AgentOpinion(
                agent=self.agent_name,
                score=score,
                recommendation=filtered_changes,
                position=str(data["position"]),
                reasoning=str(data["reasoning"]),
                evidence=list(data.get("evidence", [])),
                objections=objections_raw,
                supports=supports_raw,
                confidence=float(data.get("confidence", 0.8)),
            )

        except Exception as e:
            return self._fallback_opinion(
                proposal, context, reason=f"Gemini call failed: {e}"
            )

    # ── Private helpers ─────────────────────────────────────────────────────

    def _fallback_opinion(
        self,
        proposal: Proposal,
        context: dict[str, Any],
        *,
        reason: str,
    ) -> AgentOpinion:
        """Run evaluate() deterministically and wrap its result as an AgentOpinion.

        Parameters
        ----------
        proposal : Proposal
            The current proposal.
        context : dict[str, Any]
            Full context for evaluate().
        reason : str
            Human-readable explanation of why the fallback was triggered.

        Returns
        -------
        AgentOpinion
        """
        math_results = self.evaluate(proposal, context)
        return AgentOpinion(
            agent=self.agent_name,
            score=math_results.score,
            recommendation=math_results.proposed_changes,
            position=(
                f"{self.agent_name.capitalize()} using deterministic fallback. "
                f"Reason: {reason}"
            ),
            reasoning=math_results.reasoning_and_evidence,
            evidence=[],
            objections=[],
            supports=[],
            confidence=0.5,
        )

    # ── Shared utilities ────────────────────────────────────────────────────

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
