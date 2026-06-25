"""Diagnostic script to verify the active LLM provider is reachable and working with structured output + tool calling."""

import sys
import os
import logging
import json
from dotenv import load_dotenv

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath("."))

# Load environment variables from .env with override=True
load_dotenv(override=True)

from llm.provider_factory import get_provider
from tools.cost_calculator import CostCalculator
from tools.data_loader import DataLoader
from models.proposal import Proposal
from agents.finance_agent import FinanceAgent
from engine.state import MUTABLE_PARAMETERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("check_provider")

class NudgeDetector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.nudged = False

    def emit(self, record: logging.LogRecord) -> None:
        if "Nudging model once in same chat" in record.getMessage():
            self.nudged = True

def main() -> None:
    try:
        provider = get_provider()
        logger.info(f"Initialized provider: {provider.__class__.__name__}")
        if hasattr(provider, "provider_name"):
            logger.info(f"Configured provider name: {provider.provider_name}")
        if hasattr(provider, "default_model"):
            logger.info(f"Configured model: {provider.default_model}")
        if hasattr(provider, "api_key") and provider.api_key:
            k = provider.api_key
            logger.info(f"Active API Key in memory: {k[:12]}...{k[-4:]} (Length: {len(k)})")
        
        # Setup FinanceAgent and test data matching base_agent.py generate_opinion
        data_loader = DataLoader()
        cost_calculator = CostCalculator(data_loader)
        agent = FinanceAgent(cost_calculator)
        proposal = Proposal(
            city_slug="phoenix",
            housing_units=100,
            green_space_pct=20.0,
            parking_spaces=50,
            community_center_sqft=5000,
            affordable_housing_pct=15.0,
            estimated_cost=25_000_000.0,
        )
        
        mutable_params = sorted(MUTABLE_PARAMETERS)
        system_instruction = (
            f"You are the {agent.agent_name.capitalize()} Expert in a city planning simulation. "
            f"Your role is to evaluate a neighborhood development proposal purely from a "
            f"{agent.agent_name} perspective. "
            f"{agent.personality_brief} "
            f"Your risk tolerance profile is: {agent.risk_tolerance}. Your verdicts (accept/modify/reject) must reflect this consistent, explainable risk posture across all proposals. "
            "You must base your analysis ONLY on the domain data provided to you via function calls. "
            "Call the appropriate functions to fetch the data you need for your domain. "
            "Do not invent data. Do not reference information not present in the inputs."
        )
        
        user_prompt = (
            f"## Current Proposal State\n"
            f"{proposal.model_dump_json(indent=2)}\n\n"
            f"## Your Task (Round 1 — Independent Assessment)\n"
            f"Based ONLY on the data above, recommend changes to any or all of these "
            f"mutable parameters:\n{mutable_params}\n\n"
            "Return a single strictly-valid JSON object with EXACTLY these fields:\n"
            "{\n"
            '  "score": <float 0.0–100.0, your approval score>,\n'
            '  "verdict": <"accept" | "modify" | "reject">,\n'
            '  "proposed_changes": <dict of param->value; empty dict {} if no changes>,\n'
            '  "concession_rationale": <string or null, required ONLY when proposed_changes differs from your own previous round position (i.e. when making a concession)>,\n'
            '  "tension": <string, 1-2 sentences. Before giving your position, state the single strongest reason someone might disagree with your domain\'s typical stance on this proposal — a real consideration, not a strawman. Then explain specifically why it doesn\'t change your conclusion (or, if it\'s strong enough that it SHOULD change your conclusion, say so).>,\n'
            '  "position": <string, 1-sentence TLDR of your stance>,\n'
            '  "reasoning": <string, 2-4 sentence explanation. MUST explicitly reference the tension you just identified and explain how your final position accounts for or overrides it — do not ignore the tension you raised.>,\n'
            '  "evidence": [<string>, ...],\n'
            '  "objections": [],\n'
            '  "supports": [],\n'
            '  "confidence": <float 0.0–1.0>\n'
            "}\n\n"
            f"RULES:\n"
            f"- proposed_changes keys must be from this list only: {mutable_params}\n"
            f"- score must be between 0.0 and 100.0\n"
            f"- verdict must be 'accept' when proposed_changes is empty, 'modify' or 'reject' otherwise\n"
            f"- The tension field (1-2 sentences) MUST state the single strongest reason someone might disagree with your domain's typical stance on this proposal — a real consideration, not a strawman — before giving your position. Then explain specifically why it doesn't change your conclusion (or, if it's strong enough that it SHOULD change your conclusion, say so).\n"
            f"- The position field (1-sentence TLDR) MUST be written for a neighbourhood resident, not a planner. It MUST embody your distinct personality archetype, specific concerns, and vocabulary. No parameter names or raw percentages. (e.g. 'This development leaves almost no room for parks...' instead of 'green_space_pct is insufficient at 20%').\n"
            f"- The reasoning field (2-4 sentences max) MUST reflect your personality archetype's specific concerns and vocabulary, strictly adhering to this three-part structure: (1) What I found in my data, (2) Why it matters for the people actually affected by this proposal, and (3) What I'm proposing to change and why it fixes it. Your reasoning MUST explicitly reference the tension you just identified and explain how your final position accounts for or overrides it — do not ignore the tension you raised.\n"
            f"- evidence items MUST be one-sentence facts with real numbers, written in plain English (e.g. 'Phoenix already runs 7°F hotter...' instead of 'heat_island_risk: 5').\n"
            "- Return ONLY the JSON object, no markdown fences, no extra text."
        )
        
        required = {
            "score", "verdict", "proposed_changes",
            "tension", "position", "reasoning", "evidence", "confidence",
            "objections", "supports",
        }
        
        nudge_detector = NudgeDetector()
        logging.getLogger("llm.universal_provider").addHandler(nudge_detector)
        logging.getLogger("llm.universal_provider").setLevel(logging.INFO)

        num_runs = 5
        success_count = 0
        
        logger.info(f"Starting {num_runs} test runs with structured JSON + tool calling...")
        for i in range(1, num_runs + 1):
            logger.info(f"--- Run {i}/{num_runs} ---")
            nudge_detector.nudged = False
            try:
                res = provider.generate_structured(
                    system_instruction=system_instruction,
                    user_prompt=user_prompt,
                    tool_declarations=agent.tool_declarations,
                    tool_executor=agent.execute_tool_call,
                    required_keys=required,
                )
                if nudge_detector.nudged:
                    logger.warning(f"Run {i}: Succeeded only after nudge-retry.")
                else:
                    logger.info(f"Run {i}: SUCCESS on first attempt (no nudge needed).")
                    success_count += 1
                logger.info(f"Result tool calls: {len(res.get('tool_results', []))}")
            except Exception as e:
                logger.error(f"Run {i}: FAILED with error: {e}")
        
        success_rate = (success_count / num_runs) * 100
        logger.info(f"\n========================================")
        logger.info(f"Model: {provider.default_model}")
        logger.info(f"First-attempt Success Rate (no nudge): {success_rate:.1f}% ({success_count}/{num_runs})")
        logger.info(f"========================================\n")
        
        if success_count < num_runs:
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"FAILURE: Diagnostic script encountered error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
