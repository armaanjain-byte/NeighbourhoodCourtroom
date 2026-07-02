"""Summary Engine — Generates plain-language narratives of session outcomes.

Purpose:
    Translates raw parameters, conflicts, and scores into accessible plain English
    summaries for non-expert viewers. Uses deterministic string templating.
"""

from __future__ import annotations

from typing import Any
from engine.session import CourtroomSession
from engine.state import MUTABLE_PARAMETERS


def _fmt_val(param: str, val: float) -> str:
    """Format parameter values for plain-language display."""
    if param == "estimated_cost":
        return f"${val:,.0f}"
    if param in ("green_space_pct", "affordable_housing_pct"):
        return f"{val:.1f}%"
    if param in ("housing_units", "parking_spaces"):
        return f"{int(val):,}"
    if param == "community_center_sqft":
        return f"{val:,.0f} sqft"
    return str(val)


from tools.cost_calculator import CostCalculator

def generate_plain_language_summary(session: CourtroomSession, cost_calculator: CostCalculator) -> dict[str, str]:
    """Generate a plain-language summary dictionary based on the session state.

    Returns a dict with the following keys:
    - 'outcome': Overall resolution outcome (overrides, escalations, auto-resolved).
    - 'changes': English description of parameter deltas.
    - 'finance_score': Narrative context for Finance agent's score.
    - 'climate_score': Narrative context for Climate agent's score.
    - 'community_score': Narrative context for Community agent's score.
    """
    # 1. Outcome Narrative
    override_count = len(session.override_history)
    unresolved_conflicts = []
    
    if session.debate_rounds:
        last_round = session.debate_rounds[-1]
        for c in last_round.detected_conflicts:
            if c.disagreement_severity == "high" and c.parameter not in session.current_proposal.human_locks:
                unresolved_conflicts.append(c.parameter)
                
    if override_count > 0:
        outcome = f"You stepped in and applied {override_count} manual override{'s' if override_count > 1 else ''} to finalize the proposal."
    elif unresolved_conflicts:
        resolved_count = len(MUTABLE_PARAMETERS) - len(unresolved_conflicts)
        outcome = f"The agents reached agreement on {resolved_count} parameters, but escalated {len(unresolved_conflicts)} to your review."
    else:
        outcome = "All parameters were successfully resolved by the agents without requiring your input."

    # 2. Changes Narrative
    opening = session.debate_rounds[0].opening_state if session.debate_rounds else session.current_proposal
    final = session.current_proposal
    
    change_texts = []
    param_names = {
        "green_space_pct": "Green space",
        "affordable_housing_pct": "Affordable housing",
        "housing_units": "Housing density",
        "parking_spaces": "Parking",
        "community_center_sqft": "The community center",
        "estimated_cost": "The budget"
    }
    
    # Sort for deterministic output
    for param in sorted(list(MUTABLE_PARAMETERS)):
        open_val = getattr(opening, param)
        final_val = getattr(final, param)
        if abs(float(final_val) - float(open_val)) > 0.01:
            verb = "increased" if float(final_val) > float(open_val) else "was reduced"
            change_texts.append(f"{param_names.get(param, param)} {verb} from {_fmt_val(param, open_val)} to {_fmt_val(param, final_val)}")
            
    if change_texts:
        changes = "; ".join(change_texts) + "."
    else:
        changes = "The agents accepted your original proposal without any modifications."

    # 3. Score Narratives
    def _get_score(agent_name: str) -> float:
        if not session.debate_rounds: return 0.0
        last_round = session.debate_rounds[-1]
        r3 = getattr(last_round, "round_3_opinions", {})
        r2 = last_round.round_2_opinions
        r1 = last_round.round_1_opinions
        if agent_name in r3: return r3[agent_name].score
        if agent_name in r2: return r2[agent_name].score
        if agent_name in r1: return r1[agent_name].score
        out = last_round.agent_outputs.get(agent_name)
        return out.score if out else 0.0

    scores = {}
    
    # Finance
    finance_score = _get_score("finance")
    
    city_data = cost_calculator.data_loader.load_city(final.city_slug)
    opening_cost = cost_calculator.calculate_construction_cost(opening, city_data).total_estimated_cost
    final_cost = cost_calculator.calculate_construction_cost(final, city_data).total_estimated_cost
    
    cost_diff = final_cost - opening_cost
    if cost_diff > 0.01:
        fin_text = f"the final budget increased by {_fmt_val('estimated_cost', cost_diff)} to accommodate changes"
    elif cost_diff < -0.01:
        fin_text = f"the final budget was reduced, saving {_fmt_val('estimated_cost', abs(cost_diff))}"
    else:
        fin_text = "the final budget stayed exactly within your original target"
    scores["finance"] = f"Finance scored this {finance_score:.0f}/100 — {fin_text}."

    # Climate
    climate_score = _get_score("climate")
    green_diff = float(final.green_space_pct) - float(opening.green_space_pct)
    if green_diff > 0.01:
        cli_text = f"green space was expanded to {_fmt_val('green_space_pct', final.green_space_pct)}"
    elif green_diff < -0.01:
        cli_text = f"green space was reduced to {_fmt_val('green_space_pct', final.green_space_pct)}"
    else:
        cli_text = "green space was preserved at its original level"
    scores["climate"] = f"Climate scored this {climate_score:.0f}/100 — {cli_text}."

    # Community
    community_score = _get_score("community")
    aff_diff = float(final.affordable_housing_pct) - float(opening.affordable_housing_pct)
    com_diff = float(final.community_center_sqft) - float(opening.community_center_sqft)
    
    if aff_diff > 0.01 and com_diff > 0.01:
        com_text = "both affordable housing and community center space were expanded"
    elif aff_diff > 0.01:
        com_text = f"affordable housing was expanded to {_fmt_val('affordable_housing_pct', final.affordable_housing_pct)}"
    elif com_diff > 0.01:
        com_text = f"the community center was expanded to {_fmt_val('community_center_sqft', final.community_center_sqft)}"
    elif aff_diff < -0.01 or com_diff < -0.01:
        com_text = "community amenities or affordable housing were reduced"
    else:
        com_text = "community amenities were preserved at their original levels"
    scores["community"] = f"Community scored this {community_score:.0f}/100 — {com_text}."
    
    return {
        "outcome": outcome,
        "changes": changes,
        "finance_score": scores["finance"],
        "climate_score": scores["climate"],
        "community_score": scores["community"]
    }
