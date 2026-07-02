"""Base Agent Module.

Purpose:
    Defines the abstract contract for all agents in the Neighborhood Courtroom.
    Provides shared validation, output construction, and parameter filtering
    to ensure deterministic integration with the rest of the engine.

Design (generate_opinion):
    Round 1 (round_number=1):
        Gemini receives the proposal state and this agent's domain data slice.
        It returns tension, position, reasoning, evidence, score, verdict, and
        confidence. No compromise needed. The returned proposed_changes become
        the authoritative output; evaluate() is the fallback.

    Round 2 (round_number=2):
        Gemini additionally receives its own Round 1 opinion and opponents' Round 1
        opinions. It must produce engages_with-grounded objections/supports and provide
        a concession_rationale if its own position changed.

    Round 3 (round_number=3):
        Bounded final round, executed only for agents involved in unresolved HIGH-severity
        conflicts. Uses the same mechanics as Round 2 but framed as a final attempt
        to achieve consensus before human review.

Dependencies:
    models.proposal.Proposal, models.agent_output.AgentOutput, engine.state.MUTABLE_PARAMETERS
"""

import abc
import logging
import re
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
        own_previous_opinion: AgentOpinion | None = None,
    ) -> AgentOpinion:
        """Generate an AgentOpinion by asking Gemini to recommend parameter changes.

        Round 1 (round_number=1):
            Gemini receives only the proposal state. It can fetch its own domain data
            via tool calling. It returns score, verdict, proposed_changes, tension,
            position, reasoning, evidence, objections, supports, and confidence.
            The returned proposed_changes become the authoritative output.

        Round 2 (round_number=2):
            Gemini additionally receives its own Round 1 opinion and opponents' Round 1
            opinions. The prompt instructs Gemini to explicitly address conflicting
            recommendations with engages_with-grounded objections/supports, and provide
            a concession_rationale if its own position changed.

        Round 3 (round_number=3):
            Bounded final round, executed only for agents in unresolved HIGH-severity
            conflicts. Uses the same mechanics as Round 2 but framed as a final attempt
            to achieve consensus before human review.

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
        own_previous_opinion : AgentOpinion | None
            The agent's own opinion from the previous round, used to evaluate concessions.

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
                proposal, context,
                round_number=round_number,
                opponent_opinions=opponent_opinions,
                own_previous_opinion=own_previous_opinion,
                reason="Daily budget exhausted"
            )

        # ── Build system instruction ─────────────────────────────────────────
        # Subclasses may override build_system_prompt() to provide a richer,
        # domain-specific system instruction.  If they do, we use it; otherwise
        # we fall back to the generic template.
        custom_system_instruction = self.build_system_prompt(
            proposal, context,
            round_number=round_number,
            opponent_opinions=opponent_opinions,
        )
        if custom_system_instruction is not None:
            system_instruction = custom_system_instruction
        else:
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

        if round_number in (2, 3):
            if own_previous_opinion:
                user_prompt += (
                    f"## Your Own Previous Position\n"
                    f"- Score: {own_previous_opinion.score}\n"
                    f"- Position: {own_previous_opinion.position}\n"
                    f"- Proposed changes: {json.dumps(own_previous_opinion.recommendation)}\n\n"
                )
            if opponent_opinions:
                # Serialise opponent opinions for Gemini
                opponent_block = "\n".join(
                    f"### {name.capitalize()} Agent (Previous Round)\n"
                    f"- Score: {op.score}\n"
                    f"- Position: {op.position}\n"
                    f"- Proposed changes: {json.dumps(op.recommendation)}\n"
                    f"- Reasoning: {op.reasoning}\n"
                    f"- Evidence: {json.dumps(op.evidence)}"
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
            '  "score_rationale": <string, a one-sentence explanation of why the score is what it is>,\n'
            '  "proposed_changes": <dict of param->value; empty dict {} if no changes>,\n'
            '  "concession_rationale": <string or null, required ONLY when proposed_changes differs from your own previous round position (i.e. when making a concession)>,\n'
            '  "tension": <string, 1-2 sentences. Before giving your position, state the single strongest reason someone might disagree with your domain\'s typical stance on this proposal — a real consideration, not a strawman. Then explain specifically why it doesn\'t change your conclusion (or, if it\'s strong enough that it SHOULD change your conclusion, say so).>,\n'
            '  "position": <string, 1-sentence TLDR of your stance>,\n'
            '  "reasoning": <string, 2-4 sentence explanation. MUST explicitly reference the tension you just identified and explain how your final position accounts for or overrides it — do not ignore the tension you raised.>,\n'
            '  "evidence": [<string>, ...],\n'
        )

        if round_number in (2, 3):
            user_prompt += (
                '  "objections": [{"target_agent": <string>, "engages_with": <string, one short clause>, "reason": <string>}, ...],\n'
                '    -- List every opponent recommendation you REJECT and why.\n'
                '       Leave empty [] only if you agree with all opponents.\n'
                '  "supports": [{"target_agent": <string>, "engages_with": <string, one short clause>, "reason": <string>}, ...],\n'
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
            f"- IMPORTANT: Propose realistic, INCREMENTAL changes (e.g., move a fraction toward your ideal, not snapping to the extreme). You MUST consider the total budget impact of all domains combined; do not push the project dramatically over budget on your own.\n"
            f"- score must be between 0.0 and 100.0\n"
            f"- verdict must be 'accept' when proposed_changes is empty, 'modify' or 'reject' otherwise\n"
            f"- The tension field (1-2 sentences) MUST state the single strongest reason someone might disagree with your domain's typical stance on this proposal — a real consideration, not a strawman — before giving your position. Then explain specifically why it doesn't change your conclusion (or, if it's strong enough that it SHOULD change your conclusion, say so).\n"
            f"- The position field (1-sentence TLDR) MUST be written for a neighbourhood resident, not a planner. It MUST embody your distinct personality archetype, specific concerns, and vocabulary. No parameter names or raw percentages. (e.g. 'This development leaves almost no room for parks...' instead of 'green_space_pct is insufficient at 20%').\n"
            f"- The reasoning field (2-4 sentences max) MUST reflect your personality archetype's specific concerns and vocabulary, strictly adhering to this three-part structure: (1) What I found in my data, (2) Why it matters for the people actually affected by this proposal, and (3) What I'm proposing to change and why it fixes it. Your reasoning MUST explicitly reference the tension you just identified and explain how your final position accounts for or overrides it — do not ignore the tension you raised.\n"
            f"- evidence items MUST be one-sentence facts with real numbers, written in plain English (e.g. 'Phoenix already runs 7°F hotter...' instead of 'heat_island_risk: 5').\n"
        )
        if round_number in (2, 3):
            user_prompt += (
                "- If you are changing your own previous position on any parameter (a concession), you MUST explain in concession_rationale what you are prioritizing over your original position and why - e.g. 'I am accepting a lower green_space_pct than my original recommendation because the proposal's affordable housing target cannot be met within budget otherwise, and housing access matters more here than the marginal heat-island reduction from a few more percentage points of green space.' Do not concede without stating what you are trading and why that trade is acceptable given your domain's priorities.\n"
                "- For each objection, you MUST first quote or closely paraphrase the SPECIFIC evidence or reasoning point from the opponent's opinion you are responding to (the engages_with field), THEN explain why that specific reasoning is flawed, insufficient, or outweighed (the reason field) - do not write generic objections that only reference the opponent's proposed number without engaging their argument.\n"
                "- Keep engages_with to one short clause, not a full quotation.\n"
                "- objections and supports must each name an agent from: "
                f"{[name for name in (opponent_opinions or {}) if name != self.agent_name]}\n"
            )
        user_prompt += "- Return ONLY the JSON object, no markdown fences, no extra text."


        # ── Call LLM Provider ─────────────────────────────────────────────────
        try:
            required = {
                "score", "verdict", "proposed_changes",
                "tension", "position", "reasoning", "evidence", "confidence",
                "objections", "supports",
            }
            from llm.retry import op_deadline
            with op_deadline(25.0):
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

            # Check concession_rationale requirement
            concession_rationale = data.get("concession_rationale")
            own_previous_position = own_previous_opinion.recommendation if own_previous_opinion else None
            if own_previous_position is not None and filtered_changes != own_previous_position:
                if not concession_rationale:
                    raise LLMInvalidResponseError("concession_rationale is required when proposed_changes differs from previous round position")
            else:
                if not concession_rationale:
                    concession_rationale = None

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
                            "engages_with": str(item.get("engages_with", "")).strip(),
                            "reason": str(item.get("reason", "")),
                        })
                return result

            objections_raw = _parse_target_list(data.get("objections", []))
            supports_raw = _parse_target_list(data.get("supports", []))
            evidence_list = list(data.get("evidence", []))
            engagement_warnings = [
                self._engagement_warning_label(obj)
                for obj in objections_raw
                if self._is_superficial_engagement(obj, opponent_opinions or {})
            ]

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
                tension=str(data["tension"]),
                position=str(data["position"]),
                reasoning=str(data["reasoning"]),
                evidence=evidence_list,
                objections=objections_raw,
                supports=supports_raw,
                confidence=float(data.get("confidence", 0.8)),
                grounding_warnings=grounding_warnings,
                engagement_warnings=engagement_warnings,
                concession_rationale=concession_rationale,
                own_previous_position=own_previous_position,
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
                reason = "auth_error"
            elif isinstance(e, LLMRateLimitError):
                reason = "quota_exhausted"
            elif isinstance(e, LLMTransientError):
                reason = "transient_error"
            elif isinstance(e, LLMInvalidResponseError):
                reason = "invalid_response"
            else:
                reason = "provider_error"
            return self._fallback_opinion(
                proposal, context,
                round_number=round_number,
                opponent_opinions=opponent_opinions,
                own_previous_opinion=own_previous_opinion,
                reason=reason
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

    @staticmethod
    def _engagement_warning_label(objection: dict[str, str]) -> str:
        """Return the stable label used to associate an objection with its warning."""
        return f"{objection['target_agent']}:{objection['engages_with']}"

    def _is_superficial_engagement(
        self,
        objection: dict[str, str],
        opponent_opinions: dict[str, AgentOpinion],
    ) -> bool:
        """Flag empty or parameter/number-only references without rejecting them."""
        engages_with = objection["engages_with"].strip()
        if not engages_with:
            return True

        target_opinion = opponent_opinions.get(objection["target_agent"])
        parameter_terms: set[str] = set()
        if target_opinion:
            for parameter in target_opinion.recommendation:
                parameter_terms.update(re.findall(r"[a-z]+", parameter.lower()))

        words = re.findall(r"[a-z]+", engages_with.lower())
        generic_terms = {
            "parameter", "parameters", "proposed", "proposal", "recommendation",
            "value", "values", "number", "numbers", "percent", "percentage", "pct",
        }
        reasoning_words = [
            word for word in words
            if word not in parameter_terms and word not in generic_terms
        ]
        return not reasoning_words

    def _fallback_opinion(
        self,
        proposal: Proposal,
        context: dict[str, Any],
        *,
        round_number: int = 1,
        opponent_opinions: dict[str, AgentOpinion] | None = None,
        own_previous_opinion: AgentOpinion | None = None,
        reason: str,
    ) -> AgentOpinion:
        """Generate a round-aware, cost-grounded deterministic fallback AgentOpinion.

        Delegates to :func:`engine.fallback.generate_fallback_opinion` when a
        CostCalculator is available, so the fallback *actually responds* to what
        the other agents said last round with specific dollar figures (Du et al. 2024).

        Falls back to the old ``evaluate()``-based path only when no cost data is
        accessible (unknown agent type or missing data_loader/cost_calculator).

        Parameters
        ----------
        proposal : Proposal
            The current proposal.
        context : dict[str, Any]
            Full context for evaluate() and cost calculations. Should contain
            ``budget_limit`` and optionally ``city_data``.
        round_number : int
            The debate round number.
        opponent_opinions : dict[str, AgentOpinion] | None
            The previous opinions of other agents.
        own_previous_opinion : AgentOpinion | None
            This agent's own previous opinion.
        reason : str
            Human-readable explanation of why the fallback was triggered.

        Returns
        -------
        AgentOpinion
        """
        from engine.fallback import generate_fallback_opinion
        from tools.cost_calculator import CostCalculator

        budget_limit: float = context.get("budget_limit", 0.0)

        # Resolve city_data — prefer what the context gives us, then fetch it
        city_data: dict[str, Any] = context.get("city_data") or {}
        data_loader = getattr(self, "data_loader", None) or getattr(
            getattr(self, "cost_calculator", None), "data_loader", None
        )
        if not city_data and data_loader:
            try:
                city_data = data_loader.load_city(proposal.city_slug)
            except Exception:
                city_data = {}

        # Resolve a CostCalculator — Finance already has one; Climate/Community
        # can construct one on the fly from their data_loader.
        cost_calculator: CostCalculator | None = getattr(self, "cost_calculator", None)
        if cost_calculator is None and data_loader is not None:
            cost_calculator = CostCalculator(data_loader)

        # ── Structured fallback (Du et al. 2024) ─────────────────────────────
        if cost_calculator is not None and self.agent_name in ("finance", "climate", "community"):
            try:
                opinion = generate_fallback_opinion(
                    agent_type=self.agent_name,
                    round_num=round_number,
                    proposal=proposal,
                    city_data=city_data,
                    budget_limit=budget_limit,
                    opponent_opinions=opponent_opinions,
                    cost_calculator=cost_calculator,
                    own_previous_opinion=own_previous_opinion,
                )
                # Respect human locks — strip locked params from recommendation
                filtered = {
                    k: v for k, v in opinion.recommendation.items()
                    if k not in proposal.human_locks
                }
                dropped = [k for k in opinion.recommendation if k in proposal.human_locks]
                if dropped:
                    from engine.state import PARAM_LABELS
                    labels = [PARAM_LABELS.get(p, p) for p in dropped]
                    suffix = f" (Note: changes to {', '.join(labels)} omitted — locked by human judge.)"
                    opinion = opinion.model_copy(update={
                        "recommendation": filtered,
                        "reasoning": opinion.reasoning + suffix,
                    })
                logger.info(
                    "Agent '%s' used structured fallback (round %d, reason: %s).",
                    self.agent_name, round_number, reason,
                )
                return opinion
            except Exception as exc:
                logger.warning(
                    "Structured fallback failed for '%s': %s — falling back to evaluate().",
                    self.agent_name, exc,
                )

        # ── Legacy evaluate()-based fallback ──────────────────────────────────
        fallback_position = {
            "quota_exhausted": "AI reasoning quota temporarily exhausted — using deterministic fallback with verified baseline calculations instead.",
            "auth_error": "AI reasoning unconfigured (please check API key configuration) — using deterministic fallback with verified baseline calculations instead.",
            "transient_error": "AI reasoning temporarily unavailable (Transient network/server error) — using deterministic fallback with verified baseline calculations instead.",
            "invalid_response": "AI reasoning produced unexpected format (Invalid model response) — using deterministic fallback with verified baseline calculations instead.",
            "provider_error": "AI reasoning temporarily unavailable — using deterministic fallback with verified baseline calculations instead.",
            "Daily budget exhausted": "AI reasoning daily budget exhausted (Daily budget exhausted) — using deterministic fallback with verified baseline calculations instead.",
            "Gemini not configured": "AI reasoning unconfigured (Gemini not configured) — using deterministic fallback with verified baseline calculations instead.",
        }.get(reason, f"{self.agent_name.capitalize()} using deterministic fallback. Reason: {reason}")

        math_results = self.evaluate(proposal, context)

        filtered_changes: dict[str, Any] = {}
        dropped_locks: list[str] = []
        for param, val in math_results.proposed_changes.items():
            if param in proposal.human_locks:
                dropped_locks.append(param)
            else:
                filtered_changes[param] = val

        reasoning = math_results.reasoning_and_evidence
        if dropped_locks:
            from engine.state import PARAM_LABELS
            labels = [PARAM_LABELS.get(p, p) for p in dropped_locks]
            reasoning += f" (Note: Proposed changes to {', '.join(labels)} were omitted because they are locked by the human judge.)"

        return AgentOpinion(
            agent=self.agent_name,
            score=math_results.score,
            score_rationale=getattr(math_results, "score_rationale", "Score calculated deterministically based on domain models."),
            recommendation=filtered_changes,
            tension="Considered alternative viewpoints, but fell back to deterministic mathematical modeling due to execution constraints.",
            position=fallback_position,
            reasoning=reasoning,
            evidence=[],
            objections=[],
            supports=[],
            confidence=0.5,
            grounding_warnings=[],
            engagement_warnings=[],
            is_fallback=True,
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

    def build_system_prompt(
        self,
        proposal: Proposal,
        context: dict[str, Any],
        *,
        round_number: int = 1,
        opponent_opinions: dict[str, "AgentOpinion"] | None = None,
    ) -> str | None:
        """Return a domain-specific system instruction string, or None to use the generic fallback.

        Subclasses should override this to inject pre-computed city data, cost facts,
        and serialised opponent positions into the LLM system instruction.

        Parameters
        ----------
        proposal : Proposal
            The current proposal.
        context : dict[str, Any]
            Full session context (e.g. ``budget_limit``).
        round_number : int
            Current debate round (1 = independent, 2+ = rebuttal).
        opponent_opinions : dict[str, AgentOpinion] | None
            The other agents' opinions from the previous round.

        Returns
        -------
        str | None
            The system instruction to use, or None to fall back to the generic template.
        """
        return None  # default: use the generic template

    @staticmethod
    def _format_opponent_position(agent_name: str, opinion: "AgentOpinion | None") -> str:
        """Serialise an opponent opinion into a compact one-liner for prompt injection.

        Parameters
        ----------
        agent_name : str
            Display name of the opponent agent.
        opinion : AgentOpinion | None
            The opponent's opinion from the previous round, or None if unavailable.

        Returns
        -------
        str
            A compact human-readable summary, e.g.:
            "proposes green_space_pct→20.0, parking_spaces→100 — 'Parks matter for residents'"
        """
        if opinion is None:
            return "(no position submitted yet)"
        changes_str = ", ".join(
            f"{k}→{v}" for k, v in opinion.recommendation.items()
        ) if opinion.recommendation else "no parameter changes"
        position_snippet = opinion.position[:120] if opinion.position else ""
        return f"proposes {changes_str} — \"{position_snippet}\""


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
        score_rationale: str = "",
        standards_flags: list[dict] | None = None,
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
            score_rationale=score_rationale,
            verdict=verdict,  # type: ignore
            proposed_changes=changes,
            reasoning_and_evidence=reasoning,
            standards_flags=standards_flags or [],
        )
