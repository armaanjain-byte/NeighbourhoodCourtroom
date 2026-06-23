import os
import streamlit.components.v1 as components
from engine.state import PARAM_LABELS
from engine.session import CourtroomSession
from ui.components.conflict_view import PARAM_BOUNDS, get_pct

_COMPONENT_NAME = "override_slider"
_component_path = os.path.join(os.path.dirname(__file__), "..", "..", "ui_component_dir", "override_slider")

override_slider_component = components.declare_component(
    _COMPONENT_NAME,
    path=_component_path
)

def render_override_slider(session: CourtroomSession, param_name: str, key: str | None = None) -> float:
    bounds = PARAM_BOUNDS.get(param_name, (0, 100))
    min_val, max_val = bounds
    current_val = float(getattr(session.current_proposal, param_name))
    
    # Calculate step size
    step = 1
    if param_name in ["parking_spaces", "housing_units"]: step = 10
    elif param_name == "community_center_sqft": step = 500
    
    agent_ticks = []
    agent_names = {
        "finance": "FIN",
        "climate": "CLI",
        "community": "COM"
    }
    agent_full = {
        "finance": "Finance",
        "climate": "Climate",
        "community": "Community"
    }
    
    last_round = session.debate_rounds[-1] if session.debate_rounds else None
    if last_round:
        for a_name, a_out in last_round.agent_outputs.items():
            val = float(a_out.proposed_changes.get(param_name, getattr(session.current_proposal, param_name)))
            agent_ticks.append({
                "name": agent_names.get(a_name, a_name[:3].upper()),
                "full_name": agent_full.get(a_name, a_name.title()),
                "raw_val": val,
                "value": f"{val:g}",
                "pct": get_pct(param_name, val)
            })

    # Call the component
    return override_slider_component(
        param_label=PARAM_LABELS.get(param_name, param_name),
        min_val=min_val,
        max_val=max_val,
        current_val=current_val,
        step=step,
        agent_ticks=agent_ticks,
        key=key,
        default=None
    )
