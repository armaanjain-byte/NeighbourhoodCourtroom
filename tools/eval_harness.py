import argparse
import json
import os
import sys
import statistics
from typing import Any
from pathlib import Path

# Add project root to sys.path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from engine.session import create_session, CourtroomSession
from engine.state import create_initial_proposal
from tools.data_loader import DataLoader
from tools.cost_calculator import CostCalculator
from agents.community_agent import CommunityAgent
from agents.climate_agent import ClimateAgent
from agents.finance_agent import FinanceAgent


# ── Aggregation Functions (for unit testing) ──────────────────────────────────

def calculate_evidence_grounding_rate(sessions: list[CourtroomSession]) -> float:
    """Calculate the percentage of evidence statements that were grounded."""
    total_evidence = 0
    ungrounded_evidence = 0
    for session in sessions:
        for entry in session.transcript.entries:
            if entry.statement_type == "evidence":
                total_evidence += 1
                if entry.is_grounding_warning:
                    ungrounded_evidence += 1
    if total_evidence == 0:
        return 100.0
    return ((total_evidence - ungrounded_evidence) / total_evidence) * 100.0


def calculate_fallback_rate(sessions: list[CourtroomSession]) -> float:
    """Calculate the percentage of agent opinions that used the deterministic fallback."""
    total_opinions = 0
    fallback_opinions = 0
    for session in sessions:
        for debate_round in session.debate_rounds:
            for ops in (debate_round.round_1_opinions, debate_round.round_2_opinions, debate_round.round_3_opinions):
                if ops:
                    for opinion in ops.values():
                        total_opinions += 1
                        if opinion.is_fallback:
                            fallback_opinions += 1
    if total_opinions == 0:
        return 0.0
    return (fallback_opinions / total_opinions) * 100.0


def calculate_budget_sanity(sessions: list[CourtroomSession], data_loader: DataLoader, cost_calculator: CostCalculator) -> float:
    """Calculate the percentage of sessions where final cost <= local_budget * 1.1."""
    if not sessions:
        return 0.0
    
    sane_count = 0
    for session in sessions:
        proposal = session.get_current_state()
        cost_data = data_loader.get_construction_costs(proposal.city_slug)
        raw_index = cost_data.get("city_index", 1.0)
        city_index = raw_index / 100.0 if raw_index > 10.0 else raw_index
        
        # Base target budget is hardcoded in FinanceAgent, fetching it here.
        base_budget = FinanceAgent.BASE_TARGET_BUDGET
        local_budget = base_budget * city_index
        
        final_cost = cost_calculator.calculate_estimated_cost(proposal)
        if final_cost <= local_budget * 1.1:
            sane_count += 1
            
    return (sane_count / len(sessions)) * 100.0


def calculate_conflict_resolution_escalation(sessions: list[CourtroomSession]) -> dict[str, float]:
    """Calculate the percentage of conflicts resolved by weighted mean vs escalated to HIGH."""
    total_conflicts = 0
    high_conflicts = 0
    
    for session in sessions:
        for debate_round in session.debate_rounds:
            for conflict in debate_round.detected_conflicts:
                total_conflicts += 1
                if conflict.disagreement_severity == "high":
                    high_conflicts += 1
                    
    if total_conflicts == 0:
        return {"escalated_pct": 0.0, "resolved_pct": 100.0}
        
    escalated_pct = (high_conflicts / total_conflicts) * 100.0
    resolved_pct = 100.0 - escalated_pct
    return {"escalated_pct": escalated_pct, "resolved_pct": resolved_pct}


def calculate_score_consistency(sessions: list[CourtroomSession]) -> float:
    """Calculate the average variance (stddev) of final scores for identical scenario runs."""
    # Group sessions by scenario (city_slug)
    groups: dict[str, list[float]] = {}
    
    for session in sessions:
        slug = session.get_current_state().city_slug
        
        # We need final scores of all agents. Let's just average them to get a single 'session score'
        if session.debate_rounds:
            last_round = session.debate_rounds[-1]
            opinions = last_round.round_3_opinions or last_round.round_2_opinions or last_round.round_1_opinions
            if opinions:
                avg_score = sum(op.score for op in opinions.values()) / len(opinions)
                groups.setdefault(slug, []).append(avg_score)
                
    variances = []
    for slug, scores in groups.items():
        if len(scores) > 1:
            variances.append(statistics.stdev(scores))
        else:
            variances.append(0.0)
            
    if not variances:
        return 0.0
    return sum(variances) / len(variances)


# ── Execution Harness ─────────────────────────────────────────────────────────

def run_eval_harness(runs: int, live: bool, scenarios_dir: str = "data/scenarios") -> dict[str, Any]:
    print(f"Starting Eval Harness (Runs per scenario: {runs}, Live LLM: {live})")
    
    data_loader = DataLoader()
    cost_calculator = CostCalculator(data_loader)
    
    scenario_files = list(Path(scenarios_dir).glob("*.json"))
    sessions: list[CourtroomSession] = []
    scenarios: dict[str, dict] = {}
    
    import llm.budget
    if not live:
        # Trick the system into using deterministic fallback
        llm.budget.is_budget_exhausted = lambda: True
        print("[!] Running in HEADLESS FALLBACK mode to preserve LLM quota.")
    else:
        print("[!] Running in LIVE mode making real LLM calls.")

    for sf in scenario_files:
        with open(sf, "r") as f:
            try:
                scenario_data = json.load(f)
            except json.JSONDecodeError:
                print(f"Skipping {sf.name} - Invalid JSON")
                continue
                
        if "city_slug" not in scenario_data or "initial_proposal" not in scenario_data:
            print(f"Skipping {sf.name} - Missing required keys")
            continue
        scenarios[sf.name] = scenario_data

    # Run simulations
    for file_name, scenario_data in scenarios.items():
        scenario_id = scenario_data.get("scenario_id", file_name.replace(".json", ""))
        print(f"\n--- Running scenario: {scenario_id} ---")
        for i in range(runs):
            print(f"  Run {i+1}/{runs}...")
            
            proposal = create_initial_proposal(
                scenario_data["city_slug"],
                **scenario_data["initial_proposal"]
            )
            
            agents = [
                CommunityAgent(data_loader),
                ClimateAgent(data_loader),
                FinanceAgent(cost_calculator)
            ]
            
            session = create_session(proposal)
            try:
                # We can just drain the stream_round generator for a full round.
                # However, a session might require multiple rounds.
                # We'll just call run_round which handles round 1, 2, and 3 internally
                # and stops when it hits consensus or completes round 3.
                session.run_round(agents, {}, cost_calculator)
                sessions.append(session)
            except Exception as e:
                print(f"    Error during run: {e}")
                
    # Calculate metrics
    print("\n--- Aggregating Metrics ---")
    metrics = {
        "total_sessions": len(sessions),
        "evidence_grounding_pct": calculate_evidence_grounding_rate(sessions),
        "fallback_usage_pct": calculate_fallback_rate(sessions),
        "budget_sanity_pct": calculate_budget_sanity(sessions, data_loader, cost_calculator),
        "conflict_escalation": calculate_conflict_resolution_escalation(sessions),
        "score_stddev": calculate_score_consistency(sessions)
    }
    
    print(json.dumps(metrics, indent=2))
    return metrics

def main():
    parser = argparse.ArgumentParser(description="Run the evaluation harness.")
    parser.add_argument("--runs", type=int, default=1, help="Number of times to run each scenario.")
    parser.add_argument("--live", action="store_true", help="Use real LLMs instead of deterministic fallback.")
    args = parser.parse_args()
    
    metrics = run_eval_harness(args.runs, args.live)
    
    # Write JSON
    with open("eval_results.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
        
    # Write Markdown
    md_content = f"""# System Quality Evaluation Report

**Total Sessions Analyzed**: {metrics['total_sessions']}

## Core Metrics

- **Evidence Grounding Rate**: {metrics['evidence_grounding_pct']:.1f}% of factual claims cited real numbers.
- **Agent Fallback Rate**: {metrics['fallback_usage_pct']:.1f}% of opinions triggered deterministic fallback mode.
- **Budget Outcome Sanity**: {metrics['budget_sanity_pct']:.1f}% of proposals stayed within 10% of local targets.
- **Score Consistency (StdDev)**: ±{metrics['score_stddev']:.1f} score variance across identical runs.
- **Conflict Resolution Rate**: {metrics['conflict_escalation']['resolved_pct']:.1f}% of disagreements resolved via weighted mean vs {metrics['conflict_escalation']['escalated_pct']:.1f}% escalated to HIGH severity.
"""
    with open("eval_report.md", "w", encoding="utf-8") as f:
        f.write(md_content)
        
    print("\nResults saved to eval_results.json and eval_report.md")

if __name__ == "__main__":
    main()
