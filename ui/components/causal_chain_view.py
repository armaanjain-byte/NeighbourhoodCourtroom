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
        <div class="relative">
            <div class="absolute -left-6 w-3 h-3 rounded-full bg-[#111d23] ring-4 ring-white"></div>
            <div class="flex flex-col">
                <span class="font-semibold text-[12px] text-gray-500 uppercase">Step 1</span>
                <span class="text-[16px] text-gray-900">Human locked <span class="font-bold">{param_label}</span> at <span class="font-bold">{locked_str}</span></span>
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
                fin_concession = f'<div class="mt-2 p-3 bg-indigo-50 border border-indigo-200 rounded-lg text-xs text-indigo-950 shadow-sm"><div class="font-bold text-indigo-900 mb-1">🤝 Strategic Concession Rationale:</div><div class="italic">"{escape(op_dict["finance"].concession_rationale)}"</div></div>'
            if not com_concession and op_dict and "community" in op_dict and op_dict["community"].concession_rationale:
                com_concession = f'<div class="mt-2 p-3 bg-indigo-50 border border-indigo-200 rounded-lg text-xs text-indigo-950 shadow-sm"><div class="font-bold text-indigo-900 mb-1">🤝 Strategic Concession Rationale:</div><div class="italic">"{escape(op_dict["community"].concession_rationale)}"</div></div>'
    
    steps_html += f'''
        <div class="relative">
            <div class="absolute -left-6 w-3 h-3 rounded-full bg-amber-500 ring-4 ring-white"></div>
            <div class="flex flex-col">
                <span class="font-semibold text-[12px] text-gray-500 uppercase">Step 2</span>
                <span class="text-[16px] text-gray-600"><span class="font-bold">Finance</span> responded: {fin_text}</span>
                {fin_concession}
            </div>
        </div>
        <div class="relative">
            <div class="absolute -left-6 w-3 h-3 rounded-full bg-purple-500 ring-4 ring-white"></div>
            <div class="flex flex-col">
                <span class="font-semibold text-[12px] text-gray-500 uppercase">Step 3</span>
                <span class="text-[16px] text-gray-600"><span class="font-bold">Community</span> responded: {com_text}</span>
                {com_concession}
            </div>
        </div>
        <div class="relative">
            <div class="absolute -left-6 w-3 h-3 rounded-full bg-emerald-500 ring-4 ring-white"></div>
            <div class="flex flex-col">
                <span class="font-semibold text-[12px] text-gray-500 uppercase">Step 4</span>
                <span class="text-[16px] text-gray-900 font-bold">Engine settled: Balanced equilibrium achieved</span>
            </div>
        </div>
    '''
    
    html = f'''

    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8"/>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            body {{ font-family: ui-sans-serif, system-ui, -apple-system, sans-serif; background: transparent; margin: 0; padding: 24px; }}
        </style>
    </head>
    <body>
        <div class="bg-white border border-gray-200 p-6 rounded-xl shadow-sm space-y-4">
            <h3 class="font-bold text-[14px] text-gray-900 uppercase tracking-wider">Causal Impact Chain</h3>
            <div class="relative pl-8 space-y-6 mt-4">
                <div class="absolute left-3.5 top-2 bottom-2 w-0.5 bg-gray-200"></div>
                {steps_html}
            </div>
        </div>
    </body>
    </html>
    '''
    return html
