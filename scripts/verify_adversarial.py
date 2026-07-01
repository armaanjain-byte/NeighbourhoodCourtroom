import sys
import os
import json
sys.path.insert(0, os.path.abspath("."))

from engine.session import create_session
from engine.state import create_initial_proposal
from tools.data_loader import DataLoader
from tools.cost_calculator import CostCalculator
from agents.community_agent import CommunityAgent
from agents.climate_agent import ClimateAgent
from agents.finance_agent import FinanceAgent

def run_adversarial_scenario():
    print("--- Running Adversarial Scenario ---")
    data_loader = DataLoader()
    cost_calculator = CostCalculator(data_loader)
    
    # Load scenario config
    with open("data/scenarios/adversarial_exploitative_proposal.json", "r") as f:
        scenario_data = json.load(f)
        
    initial_proposal_data = scenario_data["initial_proposal"]
    
    proposal = create_initial_proposal(
        scenario_data["city_slug"],
        **initial_proposal_data
    )
    
    agents = [
        CommunityAgent(data_loader),
        ClimateAgent(data_loader),
        FinanceAgent(cost_calculator)
    ]
    
    session = create_session(proposal)
    context = {}
    
    # Run a debate round
    print(f"\nInitial Proposal (Affordable Housing: {proposal.affordable_housing_pct}%)\n")
    
    try:
        round_1 = session.run_round(agents, context, cost_calculator)
        
        print("\n=== Agent Outputs ===")
        for agent_name, opinion in round_1.round_1_opinions.items():
            print(f"\n[{agent_name.upper()} AGENT]")
            print(f"Score: {opinion.score}")
            print(f"Verdict: {opinion.recommendation and 'modify' or 'accept'}")
            print(f"Reasoning: {opinion.reasoning}")
            
        print("\n=== Detected Conflicts ===")
        if not round_1.detected_conflicts:
            print("No conflicts detected.")
        for conflict in round_1.detected_conflicts:
            print(f"[{conflict.disagreement_severity.upper()}] Parameter '{conflict.parameter}' between {conflict.agent_a} and {conflict.agent_b}")
            
    except Exception as e:
        print(f"Error during run: {e}")

if __name__ == "__main__":
    run_adversarial_scenario()
