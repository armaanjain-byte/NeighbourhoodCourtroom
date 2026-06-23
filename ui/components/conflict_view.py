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
            conflicted_params.add(c.parameter_name)
            
    if not conflicted_params:
        return "<div class='text-on-surface p-4'>✅ No conflicts detected.</div>"

    # We use the final debate round's agent outputs to show the final tensions
    last_round = session.debate_rounds[-1]
    
    agent_colors = {
        "finance": ("bg-amber-500", "Finance"),
        "climate": ("bg-emerald-500", "Climate"),
        "community": ("bg-purple-500", "Community")
    }

    items_html = ""
    for param in conflicted_params:
        # Find severity (max severity across rounds)
        severities = [c.disagreement_severity for dr in session.debate_rounds for c in dr.detected_conflicts if c.parameter_name == param]
        is_high = "high" in severities
        sev_label = "High Severity" if is_high else "Moderate"
        sev_class = "text-error bg-error-container" if is_high else "text-on-surface-variant bg-surface-container-high"
        
        # Get positions
        positions = {}
        for agent_name in ["finance", "climate", "community"]:
            if agent_name in last_round.agent_outputs:
                val = getattr(last_round.agent_outputs[agent_name].modified_proposal, param)
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
            color_class, label = agent_colors[agent_name]
            markers_html += f'<div class="tension-marker {color_class}" style="left: {pct}%;" title="{label}: {_fmt_value(param, val)}"></div>\n'
            
            legend_html += f'''
            <div class="flex items-center gap-1.5">
                <div class="w-2 h-2 rounded-full {color_class}"></div>
                <span class="font-label-sm text-[12px] text-gray-600">{label}: {_fmt_value(param, val)}</span>
            </div>
            '''
            
        final_val = getattr(session.current_proposal, param)
        
        items_html += f'''
        <div class="bg-white border border-gray-200 p-6 rounded-lg mb-4 shadow-sm">
            <div class="flex justify-between items-center mb-4">
                <span class="font-bold text-[16px] text-gray-900">{PARAM_LABELS.get(param, param)}</span>
                <span class="font-bold text-[10px] uppercase {sev_class} px-2 py-0.5 rounded">{sev_label}</span>
            </div>
            
            <div class="relative h-8 w-full flex items-center mb-2">
                <div class="absolute w-full h-1 bg-gray-200 rounded"></div>
                <div class="severity-bar" style="left: {min_pct}%; width: {bar_width}%;"></div>
                {markers_html}
            </div>
            
            <div class="flex flex-wrap gap-4 mt-2 mb-4">
                {legend_html}
            </div>
            
            <p class="text-[12px] text-gray-500 italic mt-2 border-t border-gray-100 pt-3">
                Engine resolved to <span class="font-bold text-gray-900">{_fmt_value(param, final_val)}</span> via weighted average
            </p>
        </div>
        '''

    html = f'''
    <!DOCTYPE html>
    <html class="light" lang="en">
    <head>
        <meta charset="utf-8"/>
        <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
        <style>
            .severity-bar {{
                height: 4px;
                border-radius: 2px;
                background-color: #ef4444; /* red-500 */
                position: absolute;
                top: 50%;
                transform: translateY(-50%);
            }}
            .tension-marker {{
                width: 14px;
                height: 14px;
                border-radius: 50%;
                position: absolute;
                top: 50%;
                transform: translate(-50%, -50%);
                border: 2px solid white;
                box-shadow: 0 1px 3px rgba(0,0,0,0.3);
            }}
            body {{ font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", sans-serif, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol", "Noto Color Emoji"; background: transparent; margin: 0; padding: 0; }}
        </style>
    </head>
    <body class="p-2">
        {items_html}
    </body>
    </html>
    '''
    return html
