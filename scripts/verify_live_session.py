"""Script to execute a live end-to-end debate session and verify substantive agent output."""

import sys
import os
import json
import logging
from dotenv import load_dotenv

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath("."))

# Load environment variables from .env with override=True
load_dotenv(override=True)

from engine.state import create_initial_proposal
from engine.session import create_session
from agents.climate_agent import ClimateAgent
from agents.community_agent import CommunityAgent
from agents.finance_agent import FinanceAgent
from tools.data_loader import DataLoader
from tools.cost_calculator import CostCalculator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_live_session")


def main() -> None:
    logger.info("Initializing live end-to-end debate session verification...")
    initial_proposal = create_initial_proposal("phoenix_az", green_space_pct=20.0, parking_spaces=100)
    data_loader = DataLoader()
    cost_calculator = CostCalculator(data_loader)
    
    # Initialize real agents
    agents = [ClimateAgent(data_loader), CommunityAgent(data_loader), FinanceAgent(cost_calculator)]
    context = {
        "city": "phoenix_az",
        "budget": 25_000_000.0,
    }
    
    session = create_session(initial_proposal)
    logger.info("Running Round 1 debate with real LLM provider...")
    round_record = session.run_round(agents, context, cost_calculator)
    
    logger.info("Debate round complete! Inspecting agent opinions...")
    
    # Verify outputs are substantive and not fallback
    success = True
    print("\n" + "="*80)
    print(" LIVE AGENT OUTPUT VERIFICATION REPORT ")
    print("="*80)
    
    for agent_name, opinion in round_record.round_1_opinions.items():
        print(f"\n### Agent: {agent_name.upper()}")
        print(f"- Position: {opinion.position}")
        print(f"- Tension: {opinion.tension}")
        print(f"- Reasoning: {opinion.reasoning}")
        print(f"- Recommendation: {opinion.recommendation}")
        
        if "Considered alternative viewpoints, but fell back to deterministic mathematical modeling" in opinion.tension:
            logger.error(f"FAILURE: {agent_name} generated generic fallback text!")
            success = False
            
    print("\n" + "="*80)
    if success:
        logger.info("SUCCESS: All agents produced substantive, varied opinions!")
        sys.exit(0)
    else:
        logger.error("FAILURE: One or more agents used fallback text.")
        sys.exit(1)


if __name__ == "__main__":
    main()
