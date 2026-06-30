import math
from engine.session import CourtroomSession
from models.debate_round import DebateRound
from engine.state import PARAM_LABELS

# Boundaries for normalizing parameter values to percentages
PARAM_BOUNDS = {
    "housing_units": (10, 2000),
    "green_space_pct": (0.0, 100.0),
    "parking_spaces": (0, 1000),
    "affordable_housing_pct": (0.0, 100.0),
    "community_center_sqft": (0.0, 100000.0)
}

def _fmt_value(param: str, value: float) -> str:
    if param in ("green_space_pct", "affordable_housing_pct"):
        return f"{value:.1f}%"
    if param in ("housing_units", "parking_spaces"):
        return f"{int(value):,}"
    if param == "community_center_sqft":
        return f"{value:,.0f} sqft"
    return str(value)

def get_pct(param: str, value: float) -> float:
    bounds = PARAM_BOUNDS.get(param)
    if not bounds:
        return 50.0
    min_val, max_val = bounds
    pct = ((float(value) - min_val) / (max_val - min_val)) * 100
    return max(0.0, min(100.0, pct))

def build_conflict_meters_html(session: CourtroomSession) -> str:
    # Gather all unique conflicted parameters across all rounds
    conflicted_params = set()
    for dr in session.debate_rounds:
        for c in dr.detected_conflicts:
            conflicted_params.add(c.parameter)
            
    if not conflicted_params:
        return "<div class='text-on-surface p-4'>✅ No conflicts detected.</div>"

    # We use the final debate round's agent outputs to show the final tensions
    last_round = session.debate_rounds[-1]
    
    agent_colors = {
        "finance":   ("#744210", "Finance"),
        "climate":   ("#276749", "Climate"),
        "community": ("#553c9a", "Community")
    }

    items_html = ""
    for param in conflicted_params:
        # Find severity (max severity across rounds)
        severities = [c.disagreement_severity for dr in session.debate_rounds for c in dr.detected_conflicts if c.parameter == param]
        is_high = "high" in severities
        sev_label = "High Severity" if is_high else "Moderate"
        sev_class = "text-error bg-error-container" if is_high else "text-on-surface-variant bg-surface-container-high"
        
        # Get positions
        positions = {}
        for agent_name in ["finance", "climate", "community"]:
            if agent_name in last_round.agent_outputs:
                val = last_round.agent_outputs[agent_name].proposed_changes.get(param, getattr(session.current_proposal, param))
                positions[agent_name] = float(val)
        
        if not positions: continue
        
        # Calculate bar
        min_pct = min(get_pct(param, v) for v in positions.values())
        max_pct = max(get_pct(param, v) for v in positions.values())
        bar_width = max_pct - min_pct
        
        # Build markers
        markers_html = ""
        legend_html = ""
        for agent_name, val in positions.items():
            pct = get_pct(param, val)
            hex_color, label = agent_colors[agent_name]
            markers_html += f'<div class="tension-marker" style="left: {pct}%; background: {hex_color};" title="{label}: {_fmt_value(param, val)}"></div>\n'
            
            legend_html += f'''
            <div style="display:flex;align-items:center;gap:6px;">
                <div style="width:10px;height:10px;background:{hex_color};border:2px solid #121212;"></div>
                <span style="font-family:Outfit,sans-serif;font-size:12px;font-weight:700;color:#121212;">{label}: {_fmt_value(param, val)}</span>
            </div>
            '''
            
        sev_bg = "#744210" if is_high else "#276749"
        sev_fg = "#fefcbf" if is_high else "#c6f6d5"
        sev_label = "HIGH SEVERITY" if is_high else "MODERATE"
        
        final_val = getattr(session.current_proposal, param)
        
        items_html += f'''
        <div style="background:#ffffff;border:4px solid #121212;padding:1.5rem;margin-bottom:1.25rem;box-shadow:6px 6px 0px 0px #121212;position:relative;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem;padding-bottom:0.75rem;border-bottom:2px solid #121212;">
                <span style="font-family:Outfit,sans-serif;font-weight:900;font-size:1rem;color:#121212;">{PARAM_LABELS.get(param, param)}</span>
                <span style="font-family:Outfit,sans-serif;font-weight:900;font-size:0.62rem;text-transform:uppercase;letter-spacing:0.1em;background:{sev_bg};color:{sev_fg};padding:3px 10px;border:2px solid #121212;border-radius:0;">{sev_label}</span>
            </div>
            
            <div style="position:relative;height:2rem;width:100%;display:flex;align-items:center;margin-bottom:0.5rem;">
                <div style="position:absolute;width:100%;height:8px;background:#E0E0E0;border:2px solid #121212;"></div>
                <div class="severity-bar" style="left: {min_pct}%; width: {bar_width}%;"></div>
                {markers_html}
            </div>
            
            <div style="display:flex;flex-wrap:wrap;gap:1rem;margin-top:0.5rem;margin-bottom:1rem;">
                {legend_html}
            </div>
            
            <p style="font-family:Outfit,sans-serif;font-size:0.78rem;color:#121212;opacity:0.6;margin-top:0.5rem;padding-top:0.75rem;border-top:2px solid #E0E0E0;">
                Engine resolved to <span style="font-weight:900;color:#121212;opacity:1;">{_fmt_value(param, final_val)}</span> via weighted average
            </p>
        </div>
        '''

    html = f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8"/>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;700;900&display=swap" rel="stylesheet"/>
        <style>
            * {{ box-sizing: border-box; }}
            body {{ font-family: 'Outfit', sans-serif; background: transparent; margin: 0; padding: 8px; color: #121212; }}
            .severity-bar {{
                height: 8px;
                background-color: #742a2a;
                position: absolute;
                top: 50%;
                transform: translateY(-50%);
                border-radius: 0;
                border: 0;
            }}
            .tension-marker {{
                width: 14px;
                height: 14px;
                border-radius: 0;
                position: absolute;
                top: 50%;
                transform: translate(-50%, -50%);
                border: 2px solid #121212;
                box-shadow: 2px 2px 0px 0px #121212;
            }}
        </style>
    </head>
    <body>
        {items_html}
    </body>
    </html>
    '''
    return html
