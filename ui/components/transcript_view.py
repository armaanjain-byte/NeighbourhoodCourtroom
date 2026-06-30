import json
from html import escape
from engine.session import CourtroomSession
from models.agent_opinion import AgentOpinion

# â”€â”€ Agent identity colours (exact hex, never approximate) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Finance amber:   bg #744210  /  text #fefcbf
# Climate green:   bg #276749  /  text #c6f6d5
# Community violet: bg #553c9a /  text #e9d8fd
AGENT_BG = {"finance": "#fefcbf", "climate": "#c6f6d5", "community": "#e9d8fd"}
AGENT_ACCENT = {"finance": "#744210", "climate": "#276749", "community": "#553c9a"}
AGENT_LIGHT_BG = {"finance": "#fffde7", "climate": "#f0fff8", "community": "#f5f0ff"}

def get_agent_color_class(agent_name: str) -> str:
    # Used by courtroom_scene.py for the transcript fallback columns
    if agent_name == "finance": return "bg-[#fffde7]"
    if agent_name == "climate": return "bg-[#f0fff8]"
    return "bg-[#f5f0ff]"

def get_agent_border_class(agent_name: str) -> str:
    if agent_name == "finance": return "border-[#744210]"
    if agent_name == "climate": return "border-[#276749]"
    return "border-[#553c9a]"

def get_agent_emoji(agent_name: str) -> str:
    if agent_name == "finance": return "ðŸ’°"
    if agent_name == "climate": return "ðŸŒ¿"
    return "ðŸ˜ï¸"

def build_card_html(agent_name: str, phase_idx: int, phase_label: str, op: AgentOpinion) -> str:
    accent = AGENT_ACCENT.get(agent_name, "#121212")
    light_bg = AGENT_LIGHT_BG.get(agent_name, "#ffffff")
    fg = AGENT_BG.get(agent_name, "#F0F0F0")
    card_id = f"{agent_name}-p{phase_idx}"

    callouts = ""
    for obj in op.objections:
        warning_label = f"{obj.target_agent}:{obj.engages_with}"
        warning_badge = ""
        if warning_label in op.engagement_warnings:
            warning_badge = (
                '<span style="display:inline-flex;align-items:center;gap:3px;padding:1px 6px;margin-left:4px;'
                f'background:#fefcbf;color:#744210;border:1px solid #744210;font-size:10px;font-weight:900;'
                'font-family:Outfit,sans-serif;text-transform:uppercase;letter-spacing:0.06em;">weak engagement</span>'
            )
        callouts += f'''
        <div style="margin-bottom:1rem;padding:0.5rem 0.75rem;background:#fff0f0;border-left:4px solid #742a2a;border:2px solid #121212;font-size:0.82rem;">
            <div style="display:flex;align-items:center;gap:6px;font-weight:900;font-family:Outfit,sans-serif;font-size:0.7rem;text-transform:uppercase;letter-spacing:0.08em;color:#742a2a;margin-bottom:3px;">
            âš¡ Responding to {escape(obj.target_agent.title())}\'s claim:
            "{escape(obj.engages_with)}" {warning_badge}
            </div>
            <div style="font-size:0.82rem;color:#121212;">{escape(obj.reason)}</div>
        </div>
        '''
    for sup in op.supports:
        callouts += f'''
        <div style="margin-bottom:0.75rem;display:inline-flex;align-items:center;gap:6px;padding:4px 10px;background:#c6f6d5;color:#276749;border:2px solid #276749;font-size:0.78rem;font-weight:700;font-family:Outfit,sans-serif;">
            âœ“ Support â†’ {sup.target_agent.title()}: {sup.reason}
        </div><br>
        '''

    evidence_items = ""
    for ev in op.evidence:
        if ev in op.grounding_warnings:
            evidence_items += f'<li>{ev} <span style="display:inline;padding:1px 5px;background:#fefcbf;color:#744210;border:1px solid #744210;font-size:10px;font-weight:900;font-family:Outfit,sans-serif;text-transform:uppercase;">âš  unverified</span></li>'
        else:
            evidence_items += f'<li>{ev}</li>'
    if not evidence_items:
        evidence_items = "<li>No specific evidence provided.</li>"

    concession_html = ""
    if op.concession_rationale and op.own_previous_position is not None and op.own_previous_position != op.recommendation:
        concession_html = f'''
        <div style="margin-bottom:1rem;padding:0.75rem;background:#e9d8fd;border:2px solid #553c9a;font-size:0.8rem;color:#121212;">
            <div style="font-weight:900;font-family:Outfit,sans-serif;font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;color:#553c9a;margin-bottom:4px;">
                ðŸ¤ Strategic Concession Rationale:
            </div>
            <div style="font-style:italic;line-height:1.5;">"{escape(op.concession_rationale)}"</div>
        </div>
        '''

    fallback_header = ""
    card_bg = "#ffffff"
    card_border_style = f"border: 4px solid #121212; border-top: 6px solid {accent}; box-shadow: 6px 6px 0px 0px #121212;"

    if getattr(op, "is_fallback", False):
        fallback_header = f'''
        <div style="margin-bottom:1rem;padding:6px 10px;background:#E0E0E0;border:2px dashed #121212;font-size:0.68rem;font-weight:900;font-family:Outfit,sans-serif;letter-spacing:0.08em;text-transform:uppercase;color:#121212;display:flex;align-items:center;gap:6px;">
            âš™ Verified Baseline Calculation (AI reasoning unavailable)
        </div>
        '''
        card_bg = "#F0F0F0"
        card_border_style = f"border: 4px dashed #121212; border-top: 6px solid {accent}; box-shadow: 4px 4px 0px 0px #121212;"

    html = f'''
    <div style="background:{card_bg};{card_border_style};padding:1.25rem;position:relative;margin-bottom:1.5rem;" id="{card_id}">
        <!-- Phase label â€” Bauhaus square tag -->
        <span style="position:absolute;top:-14px;left:12px;background:#121212;color:#F0F0F0;font-family:Outfit,sans-serif;font-size:0.6rem;font-weight:900;letter-spacing:0.12em;text-transform:uppercase;padding:2px 8px;border:2px solid #121212;">{phase_label}</span>
        {fallback_header}
        <!-- Tension block -->
        <div style="margin-bottom:1rem;padding:0.5rem 0.75rem;background:{light_bg};border-left:4px solid {accent};font-size:0.78rem;color:#121212;font-style:italic;">
            <div style="font-weight:900;font-family:Outfit,sans-serif;font-size:0.65rem;text-transform:uppercase;letter-spacing:0.08em;color:{accent};margin-bottom:3px;">âš– Weighing counter-consideration:</div>
            "{op.tension}"
        </div>
        <p style="font-weight:900;font-family:Outfit,sans-serif;font-size:0.95rem;margin-bottom:1rem;color:#121212;line-height:1.4;">{op.position}</p>
        {concession_html}
        {callouts}
        <details style="margin-top:0.5rem;">
            <summary style="cursor:pointer;font-family:Outfit,sans-serif;font-size:0.68rem;font-weight:900;text-transform:uppercase;letter-spacing:0.1em;color:{accent};display:flex;align-items:center;justify-content:between;list-style:none;">
                â–¶ Evidence
            </summary>
            <ul style="margin-top:0.5rem;padding-left:1.2rem;font-size:0.8rem;color:#121212;line-height:1.6;list-style:disc;">
                {evidence_items}
            </ul>
        </details>
    </div>
    '''
    return html

def build_transcript_html(session: CourtroomSession) -> str:
    phases = []
    round_phase_indices = []
    for i, r in enumerate(session.debate_rounds):
        indices = []
        phases.append((f"D{i+1} - R1", r.round_1_opinions))
        indices.append(len(phases) - 1)
        if r.round_2_opinions:
            phases.append((f"D{i+1} - R2", r.round_2_opinions))
            indices.append(len(phases) - 1)
        if getattr(r, "round_3_opinions", None):
            phases.append((f"D{i+1} - R3", r.round_3_opinions))
            indices.append(len(phases) - 1)
        round_phase_indices.append(indices)

    agents = ["finance", "climate", "community"]
    columns_html = ""

    for agent_name in agents:
        accent = AGENT_ACCENT.get(agent_name, "#121212")
        light_bg = AGENT_LIGHT_BG.get(agent_name, "#ffffff")
        fg = AGENT_BG.get(agent_name, "#F0F0F0")
        emoji = get_agent_emoji(agent_name)

        cards_html = ""
        for phase_idx, (phase_label, opinions) in enumerate(phases):
            op = opinions.get(agent_name)
            if op:
                cards_html += build_card_html(agent_name, phase_idx, phase_label, op)

        col = f'''
        <div style="flex:1;border-right:4px solid #121212;background:{light_bg};padding:1.5rem;" id="col-{agent_name}">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:2rem;padding-bottom:0.75rem;border-bottom:4px solid #121212;">
                <span style="font-size:1.5rem;">{emoji}</span>
                <h3 style="font-family:Outfit,sans-serif;font-weight:900;font-size:1rem;text-transform:uppercase;letter-spacing:0.12em;color:{accent};">{agent_name}</h3>
                <!-- Geometric corner accent -->
                <div style="width:12px;height:12px;background:{accent};margin-left:auto;flex-shrink:0;"></div>
            </div>
            <div style="display:flex;flex-direction:column;gap:0;">
                {cards_html}
            </div>
        </div>
        '''
        columns_html += col

    # Collect conflicts
    conflicts_js = []
    for r, phase_indices in zip(session.debate_rounds, round_phase_indices):
        for c in r.detected_conflicts:
            if c.disagreement_severity in ["medium", "high"]:
                phase_a = next((idx for idx in reversed(phase_indices) if c.agent_a in phases[idx][1]), phase_indices[0])
                phase_b = next((idx for idx in reversed(phase_indices) if c.agent_b in phases[idx][1]), phase_indices[0])
                conflicts_js.append({
                    "from": f"{c.agent_a}-p{phase_a}",
                    "to": f"{c.agent_b}-p{phase_b}",
                    "param": c.parameter
                })

    conflicts_json = json.dumps(conflicts_js)

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8"/>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;700;900&display=swap" rel="stylesheet"/>
        <style>
            * {{ box-sizing: border-box; }}
            body {{
                font-family: 'Outfit', sans-serif;
                background-color: #F0F0F0;
                background-image: radial-gradient(#121212 1.5px, transparent 1.5px);
                background-size: 22px 22px;
                margin: 0; padding: 0;
                color: #121212;
            }}
            .conflict-line {{
                position: absolute;
                height: 3px;
                background-color: #742a2a;
                opacity: 0.7;
                z-index: 10;
                pointer-events: none;
            }}
            .conflict-label {{
                position: absolute;
                background: #121212;
                color: #fefcbf;
                border: 2px solid #744210;
                padding: 2px 8px;
                border-radius: 0;
                font-size: 10px;
                font-family: 'Outfit', sans-serif;
                font-weight: 900;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                z-index: 11;
                transform: translate(-50%, -50%);
            }}
            .hide-scrollbar::-webkit-scrollbar {{ display: none; }}
            .hide-scrollbar {{ -ms-overflow-style: none; scrollbar-width: none; }}
            details > summary {{ list-style: none; }}
            details > summary::-webkit-details-marker {{ display: none; }}
            details[open] > summary::first-letter {{ }}
        </style>
    </head>
    <body>
        <main style="display:flex;height:100%;overflow:hidden;">
            <section style="flex:1;overflow-x:auto;position:relative;" class="hide-scrollbar">
                <div style="position:absolute;inset:0;pointer-events:none;" id="conflict-lines-container"></div>
                <div style="display:flex;height:100%;min-width:900px;border:4px solid #121212;box-shadow:8px 8px 0px 0px #121212;">
                    {columns_html}
                </div>
            </section>
        </main>
        <script>
            function drawConflictLines() {{
                const container = document.getElementById('conflict-lines-container');
                container.innerHTML = '';

                const conflicts = {conflicts_json};

                conflicts.forEach(pair => {{
                    const el1 = document.getElementById(pair.from);
                    const el2 = document.getElementById(pair.to);

                    if (el1 && el2) {{
                        const rect1 = el1.getBoundingClientRect();
                        const rect2 = el2.getBoundingClientRect();
                        const canvasRect = container.parentElement.getBoundingClientRect();

                        const line = document.createElement('div');
                        line.className = 'conflict-line';

                        const x1 = rect1.right - canvasRect.left;
                        const x2 = rect2.left - canvasRect.left;

                        const y1 = rect1.top + (rect1.height / 2) - canvasRect.top;
                        const y2 = rect2.top + (rect2.height / 2) - canvasRect.top;

                        const length = Math.sqrt(Math.pow(x2 - x1, 2) + Math.pow(y2 - y1, 2));
                        const angle = Math.atan2(y2 - y1, x2 - x1) * 180 / Math.PI;

                        line.style.width = `${{length}}px`;
                        line.style.left = `${{x1}}px`;
                        line.style.top = `${{y1}}px`;
                        line.style.transform = `rotate(${{angle}}deg)`;
                        line.style.transformOrigin = '0 0';

                        container.appendChild(line);

                        const label = document.createElement('div');
                        label.className = 'conflict-label';
                        label.innerText = pair.param;
                        label.style.left = `${{x1 + (x2 - x1)/2}}px`;
                        label.style.top = `${{y1 + (y2 - y1)/2}}px`;
                        container.appendChild(label);
                    }}
                }});
            }}

            window.addEventListener('load', () => setTimeout(drawConflictLines, 200));
            window.addEventListener('resize', drawConflictLines);

            document.querySelectorAll('details').forEach(detail => {{
                detail.addEventListener('toggle', () => {{
                    setTimeout(drawConflictLines, 150);
                }});
            }});

            setInterval(drawConflictLines, 1000);
        </script>
    </body>
    </html>
    """
    return html

