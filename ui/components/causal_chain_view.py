from engine.state import PARAM_LABELS

def _fmt_value(param: str, value: float) -> str:
    if param in ("green_space_pct", "affordable_housing_pct"):
        return f"{value:.1f}%"
    if param in ("housing_units", "parking_spaces"):
        return f"{int(value):,}"
    if param == "community_center_sqft":
        return f"{value:,.0f} sqft"
    return str(value)

def build_causal_chain_html(old_proposal, new_proposal, locked_param: str, locked_value: float, session=None) -> str:
    # 1. Human lock
    locked_str = _fmt_value(locked_param, locked_value)
    param_label = PARAM_LABELS.get(locked_param, locked_param)
    
    steps_html = f'''
        <div style="position:relative;padding-left:1.5rem;">
            <div style="position:absolute;left:0;top:6px;width:14px;height:14px;background:#121212;border:3px solid #121212;"></div>
            <div style="display:flex;flex-direction:column;">
                <span style="font-family:Outfit,sans-serif;font-weight:900;font-size:0.62rem;color:#553c9a;text-transform:uppercase;letter-spacing:0.12em;">Step 1</span>
                <span style="font-family:Outfit,sans-serif;font-size:0.95rem;color:#121212;font-weight:700;">Human locked <strong>{param_label}</strong> at <strong>{locked_str}</strong></span>
            </div>
        </div>
    '''
    
    # 2. Extract changes
    finance_changes = []
    community_changes = []
    for entry in new_proposal.change_log:
        if entry["version"] > old_proposal.version and entry["action"] != "locked":
            if entry["actor"] == "finance": finance_changes.append(entry)
            if entry["actor"] == "community": community_changes.append(entry)
            
    def _summarize(actor_changes):
        if not actor_changes: return "Accepted without changing any parameters"
        final_chg = {}
        for c in actor_changes: final_chg[c["parameter"]] = c
        parts = []
        for p, c in final_chg.items():
            direction = "Increased" if float(c["new"]) > float(c["old"]) else "Decreased"
            lbl = PARAM_LABELS.get(p, p).lower()
            parts.append(f"{direction} {lbl} to {_fmt_value(p, c['new'])}")
        return " and ".join(parts)

    fin_text = _summarize(finance_changes)
    com_text = _summarize(community_changes)
    
    from html import escape
    fin_concession = ""
    com_concession = ""
    if session and session.debate_rounds:
        last_r = session.debate_rounds[-1]
        for op_dict in [getattr(last_r, "round_3_opinions", {}), getattr(last_r, "round_2_opinions", {})]:
            if not fin_concession and op_dict and "finance" in op_dict and op_dict["finance"].concession_rationale:
                fin_concession = f'<div style="margin-top:0.5rem;padding:0.75rem;background:#fefcbf;border:2px solid #744210;font-size:0.78rem;color:#121212;"><div style="font-family:Outfit,sans-serif;font-weight:900;font-size:0.62rem;text-transform:uppercase;letter-spacing:0.1em;color:#744210;margin-bottom:4px;">🤝 Concession Rationale:</div><div style="font-style:italic;">\"{ escape(op_dict["finance"].concession_rationale) }\"</div></div>'
            if not com_concession and op_dict and "community" in op_dict and op_dict["community"].concession_rationale:
                com_concession = f'<div style="margin-top:0.5rem;padding:0.75rem;background:#e9d8fd;border:2px solid #553c9a;font-size:0.78rem;color:#121212;"><div style="font-family:Outfit,sans-serif;font-weight:900;font-size:0.62rem;text-transform:uppercase;letter-spacing:0.1em;color:#553c9a;margin-bottom:4px;">🤝 Concession Rationale:</div><div style="font-style:italic;">\"{ escape(op_dict["community"].concession_rationale) }\"</div></div>'
    
    steps_html += f'''
        <div style="position:relative;padding-left:1.5rem;">
            <div style="position:absolute;left:0;top:6px;width:14px;height:14px;background:#744210;border:3px solid #121212;"></div>
            <div style="display:flex;flex-direction:column;">
                <span style="font-family:Outfit,sans-serif;font-weight:900;font-size:0.62rem;color:#744210;text-transform:uppercase;letter-spacing:0.12em;">Step 2</span>
                <span style="font-family:Outfit,sans-serif;font-size:0.95rem;color:#121212;"><strong>Finance</strong> responded: {fin_text}</span>
                {fin_concession}
            </div>
        </div>
        <div style="position:relative;padding-left:1.5rem;">
            <div style="position:absolute;left:0;top:6px;width:14px;height:14px;background:#553c9a;border:3px solid #121212;"></div>
            <div style="display:flex;flex-direction:column;">
                <span style="font-family:Outfit,sans-serif;font-weight:900;font-size:0.62rem;color:#553c9a;text-transform:uppercase;letter-spacing:0.12em;">Step 3</span>
                <span style="font-family:Outfit,sans-serif;font-size:0.95rem;color:#121212;"><strong>Community</strong> responded: {com_text}</span>
                {com_concession}
            </div>
        </div>
        <div style="position:relative;padding-left:1.5rem;">
            <div style="position:absolute;left:0;top:6px;width:14px;height:14px;background:#276749;border:3px solid #121212;"></div>
            <div style="display:flex;flex-direction:column;">
                <span style="font-family:Outfit,sans-serif;font-weight:900;font-size:0.62rem;color:#276749;text-transform:uppercase;letter-spacing:0.12em;">Step 4</span>
                <span style="font-family:Outfit,sans-serif;font-size:0.95rem;color:#121212;font-weight:900;">Engine settled: Balanced equilibrium achieved</span>
            </div>
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
            body {{ font-family: 'Outfit', sans-serif; background: transparent; margin: 0; padding: 24px; color: #121212; }}
        </style>
    </head>
    <body>
        <div style="background:#ffffff;border:4px solid #121212;padding:1.5rem;box-shadow:8px 8px 0px 0px #121212;border-radius:0;">
            <h3 style="font-family:Outfit,sans-serif;font-weight:900;font-size:0.72rem;color:#121212;text-transform:uppercase;letter-spacing:0.14em;margin-bottom:1.25rem;padding-bottom:0.5rem;border-bottom:3px solid #121212;">Causal Impact Chain</h3>
            <div style="position:relative;padding-left:2rem;display:flex;flex-direction:column;gap:1.5rem;margin-top:1rem;">
                <div style="position:absolute;left:6px;top:8px;bottom:8px;width:2px;background:#121212;"></div>
                {steps_html}
            </div>
        </div>
    </body>
    </html>
    '''
    return html
