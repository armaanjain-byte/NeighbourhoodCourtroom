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
import logging
from typing import Any

from models.proposal import Proposal
from models.agent_output import AgentOutput
from models.agent_opinion import AgentOpinion
from engine.state import MUTABLE_PARAMETERS

import os
import json
from llm.base import (
    LLMProvider,
    LLMProviderError,
    LLMAuthError,
    LLMRateLimitError,
    LLMTransientError,
    LLMInvalidResponseError,
)
from llm.budget import is_budget_exhausted

logger = logging.getLogger(__name__)


class AgentValidationError(ValueError):
    """Raised when an agent produces an invalid output or violates schema rules."""
    pass


class AgentExecutionError(RuntimeError):
    """Raised when an agent fails to execute its evaluation logic."""
    pass


class BaseAgent(abc.ABC):
    """Abstract Base Class for all Neighborhood Courtroom agents."""

    @property
    def llm_provider(self) -> LLMProvider:
        """The configured LLMProvider instance."""
        if not hasattr(self, "_llm_provider") or self._llm_provider is None:
            from llm.provider_factory import get_provider
            self._llm_provider = get_provider()
        return self._llm_provider

    @llm_provider.setter
    def llm_provider(self, provider: LLMProvider) -> None:
        self._llm_provider = provider

    @property
    @abc.abstractmethod
    def agent_name(self) -> str:
        """The identifier of the agent (e.g. 'finance', 'climate', 'community')."""
        pass  # pragma: no cover

    @property
    @abc.abstractmethod
    def personality_brief(self) -> str:
        """The distinct personality archetype description (2-3 sentences max)."""
        pass  # pragma: no cover

    @property
    @abc.abstractmethod
    def risk_tolerance(self) -> str:
        """The specific risk tolerance posture for this agent domain."""
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
        *,
        round_number: int = 1,
        opponent_opinions: dict[str, AgentOpinion] | None = None,
    ) -> AgentOpinion:
        """Generate an AgentOpinion by asking Gemini to recommend parameter changes.

        Round 1 (round_number=1):
            Gemini receives only the proposal state. It can fetch its own domain data
            via tool calling. It returns score, verdict, proposed_changes, position,
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

        # ── Check Daily Budget ────────────────────────────────────────────────
        if is_budget_exhausted():
            logger.warning(
                f"Agent '{self.agent_name}' skipping LLM call due to exhausted daily budget. "
                "Triggering deterministic fallback."
            )
            return self._fallback_opinion(
                proposal, context, reason="Daily budget exhausted"
            )

        # ── Build system instruction ─────────────────────────────────────────
        system_instruction = (
            f"You are the {self.agent_name.capitalize()} Expert in a city planning simulation. "
            f"Your role is to evaluate a neighborhood development proposal purely from a "
            f"{self.agent_name} perspective. "
            f"{self.personality_brief} "
            f"Your risk tolerance profile is: {self.risk_tolerance}. Your verdicts (accept/modify/reject) must reflect this consistent, explainable risk posture across all proposals. "
            "You must base your analysis ONLY on the domain data provided to you via function calls. "
            "Call the appropriate functions to fetch the data you need for your domain. "
            "Do not invent data. Do not reference information not present in the inputs."
        )

        # ── Build user prompt ────────────────────────────────────────────────
        user_prompt = (
            f"## Current Proposal State\n"
            f"{proposal.model_dump_json(indent=2)}\n\n"
        )

        if round_number in (2, 3) and opponent_opinions:
            # Serialise opponent opinions for Gemini
            opponent_block = "\n".join(
                f"### {name.capitalize()} Agent (Previous Round)\n"
                f"- Score: {op.score}\n"
                f"- Position: {op.position}\n"
                f"- Proposed changes: {json.dumps(op.recommendation)}\n"
                f"- Reasoning: {op.reasoning}"
                for name, op in opponent_opinions.items()
                if name != self.agent_name
            )
            user_prompt += (
                f"## Previous Round Results from Other Agents\n"
                f"{opponent_block}\n\n"
            )
            if round_number == 3:
                target_conflicts = context.get("target_conflicts", [])
                conflict_details = " ".join(
                    f"You and {tc['opponent'].capitalize()} still disagree significantly on {tc['parameter']}."
                    for tc in target_conflicts
                )
                user_prompt += (
                    f"## Your Task (Round 3 — Final Attempt)\n"
                    f"This is a final round. {conflict_details} Propose your best final compromise — this will go to human review if you cannot converge.\n\n"
                    f"Recommend changes to any or all of these mutable parameters:\n{mutable_params}\n\n"
                )
            else:
                user_prompt += (
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

        if round_number in (2, 3):
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
            f"- The position field (1-sentence TLDR) MUST be written for a neighbourhood resident, not a planner. It MUST embody your distinct personality archetype, specific concerns, and vocabulary. No parameter names or raw percentages. (e.g. 'This development leaves almost no room for parks...' instead of 'green_space_pct is insufficient at 20%').\n"
            f"- The reasoning field (2-4 sentences max) MUST reflect your personality archetype's specific concerns and vocabulary, strictly adhering to this structure: (1) What I found in my data, (2) Why it matters for real people, (3) What I'm proposing to change and why it fixes it.\n"
            f"- evidence items MUST be one-sentence facts with real numbers, written in plain English (e.g. 'Phoenix already runs 7°F hotter...' instead of 'heat_island_risk: 5').\n"
        )
        if round_number in (2, 3):
            user_prompt += (
                "- objections MUST name what the opponent is asking for in plain terms, then explain why it hurts real people. (e.g. 'Finance wants to cut parks to save money, but that leaves zero shade...').\n"
                "- objections and supports must each name an agent from: "
                f"{[name for name in (opponent_opinions or {}) if name != self.agent_name]}\n"
            )
        user_prompt += "- Return ONLY the JSON object, no markdown fences, no extra text."


        # ── Call LLM Provider ─────────────────────────────────────────────────
        try:
            required = {
                "score", "verdict", "proposed_changes",
                "position", "reasoning", "evidence", "confidence",
                "objections", "supports",
            }
            data = self.llm_provider.generate_structured(
                system_instruction=system_instruction,
                user_prompt=user_prompt,
                tool_declarations=self.tool_declarations or None,
                tool_executor=self.execute_tool_call,
                required_keys=required,
            )

            # Validate required keys (redundant check in case provider didn't validate)
            if not required.issubset(data.keys()):
                missing = required - data.keys()
                raise LLMInvalidResponseError(f"LLM response missing keys: {missing}")

            # Filter proposed_changes to only known mutable parameters
            filtered_changes = self.filter_unknown_parameters(
                {k: float(v) for k, v in data["proposed_changes"].items()}
            )

            # Validate score and verdict
            score = float(data["score"])
            if not (0.0 <= score <= 100.0):
                raise ValueError(f"LLM returned out-of-range score: {score}")

            verdict = str(data["verdict"])
            if verdict not in ("accept", "modify", "reject"):
                raise ValueError(f"LLM returned invalid verdict: {verdict}")

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
            evidence_list = list(data.get("evidence", []))

            # Extract tool numbers and check grounding
            def _extract_numbers(obj: Any, numbers: set[float]) -> None:
                if isinstance(obj, (int, float)) and not isinstance(obj, bool):
                    numbers.add(float(obj))
                elif isinstance(obj, dict):
                    for v in obj.values():
                        _extract_numbers(v, numbers)
                elif isinstance(obj, (list, tuple)):
                    for item in obj:
                        _extract_numbers(item, numbers)

            tool_numbers: set[float] = set()
            _extract_numbers(data.get("tool_results", []), tool_numbers)

            grounding_results = self._check_evidence_grounding(evidence_list, tool_numbers)
            grounding_warnings = [g["evidence"] for g in grounding_results if not g["grounded"]]

            return AgentOpinion(
                agent=self.agent_name,
                score=score,
                recommendation=filtered_changes,
                position=str(data["position"]),
                reasoning=str(data["reasoning"]),
                evidence=evidence_list,
                objections=objections_raw,
                supports=supports_raw,
                confidence=float(data.get("confidence", 0.8)),
                grounding_warnings=grounding_warnings,
            )

        except Exception as e:
            error_msg = str(e)
            err_type = type(e).__name__
            logger.error(
                f"Agent '{self.agent_name}' LLM generation failed with {err_type}: {e}. "
                "Triggering deterministic fallback."
            )
            if "Gemini not configured" in error_msg:
                reason = "Gemini not configured"
            elif isinstance(e, LLMAuthError) or "API key" in error_msg or "400" in error_msg or "403" in error_msg or "APIError" in err_type:
                reason = "Invalid or missing Gemini API key. Please check your configuration."
            elif isinstance(e, LLMRateLimitError):
                reason = f"Rate limit or daily quota exhausted: {e}"
            elif isinstance(e, LLMTransientError):
                reason = f"Transient network/server error: {e}"
            elif isinstance(e, LLMInvalidResponseError):
                reason = f"Invalid model response: {e}"
            else:
                reason = f"Gemini call failed: {e}"
            return self._fallback_opinion(
                proposal, context, reason=reason
            )

    # ── Private helpers ─────────────────────────────────────────────────────

    def _check_evidence_grounding(self, evidence: list[str], tool_numbers: set[float]) -> list[dict]:
        """Check whether numbers cited in evidence strings appear in tool results.

        For each evidence string, extract numbers using regex and verify if at least
        one number matches a value in tool_numbers within a reasonable tolerance (e.g., 0.1).
        
        If an evidence string contains no numbers at all, we default to grounded=True.
        Reasoning: Qualitative or structural claims (e.g. 'The zoning is mixed residential') 
        do not contain numerical metrics but are valid qualitative evidence. Rejecting them 
        would penalize legitimate non-numeric factual observations.

        Parameters
        ----------
        evidence : list[str]
            List of evidence strings produced by the LLM.
        tool_numbers : set[float]
            Set of all numeric values recursively extracted from tool call results.

        Returns
        -------
        list[dict]
            List of grounding results, e.g. [{"evidence": "...", "grounded": True/False}].
        """
        import re
        results = []
        # Match integers and decimals
        pattern = re.compile(r'\b\d+(?:\.\d+)?\b')

        for item in evidence:
            matches = pattern.findall(item)
            if not matches:
                # Default to grounded=True for qualitative/structural claims without numbers
                results.append({"evidence": item, "grounded": True})
                continue

            grounded = False
            for m in matches:
                try:
                    val = float(m)
                    # Check if val matches any number in tool_numbers within 0.1 tolerance,
                    # or if val/100 matches within 0.001 tolerance (to handle percentage formatting like 17.2% for 0.172)
                    if any(abs(val - t_val) <= 0.100001 or abs((val / 100.0) - t_val) <= 0.0010001 for t_val in tool_numbers):
                        grounded = True
                        break
                except (ValueError, TypeError):
                    continue
            
            results.append({"evidence": item, "grounded": grounded})

        return results

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
            grounding_warnings=[],
        )

    @property
    def tool_declarations(self) -> list[Any]:
        """Return the list of tool definitions for Gemini function calling.
        
        Subclasses should override this to provide their domain tools.
        """
        return []

    def execute_tool_call(self, name: str, args: dict[str, Any]) -> Any:
        """Execute a tool call requested by Gemini.
        
        Parameters
        ----------
        name : str
            The name of the tool/function.
        args : dict[str, Any]
            The arguments passed to the tool.
            
        Returns
        -------
        Any
            The result of the tool execution (usually a dict).
            
        Raises
        ------
        NotImplementedError
            If the tool name is unknown or not implemented.
        """
        raise NotImplementedError(f"Tool {name} not implemented for {self.agent_name}")

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
