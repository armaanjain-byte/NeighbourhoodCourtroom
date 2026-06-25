import json
from html import escape
from engine.session import CourtroomSession
from models.agent_opinion import AgentOpinion

def get_agent_color_class(agent_name: str) -> str:
    if agent_name == "finance": return "bg-[#FFF9E5]"
    if agent_name == "climate": return "bg-[#E8F5E9]"
    return "bg-[#F3E5F5]"

def get_agent_border_class(agent_name: str) -> str:
    if agent_name == "finance": return "border-[#E6DFC9]"
    if agent_name == "climate": return "border-[#D1E1D2]"
    return "border-[#DCCEDD]"

def get_agent_emoji(agent_name: str) -> str:
    if agent_name == "finance": return "💰"
    if agent_name == "climate": return "🌿"
    return "🏘️"

def build_card_html(agent_name: str, phase_idx: int, phase_label: str, op: AgentOpinion) -> str:
    border_class = get_agent_border_class(agent_name)
    card_id = f"{agent_name}-p{phase_idx}"
    
    callouts = ""
    for obj in op.objections:
        warning_label = f"{obj.target_agent}:{obj.engages_with}"
        warning_badge = ""
        if warning_label in op.engagement_warnings:
            warning_badge = (
                '<span class="inline-flex items-center gap-1 px-2 py-0.5 ml-1 '
                'bg-amber-100 text-amber-800 rounded text-[11px] font-bold '
                'border border-amber-300">weak engagement</span>'
            )
        callouts += f'''
        <div class="mb-4 px-3 py-2 bg-red-100 text-error rounded border border-red-200 text-label-sm">
            <div class="flex items-center gap-2 font-semibold">
            <span class="material-symbols-outlined text-[16px]">warning</span>
            Responding to {escape(obj.target_agent.title())}'s claim that
            "{escape(obj.engages_with)}" {warning_badge}
            </div>
            <div class="mt-1">{escape(obj.reason)}</div>
        </div><br>
        '''
    for sup in op.supports:
        callouts += f'''
        <div class="mb-4 inline-flex items-center gap-2 px-3 py-1 bg-green-100 text-[#2E7D32] rounded-full text-label-sm border border-green-200">
            <span class="material-symbols-outlined text-[16px]">check_circle</span>
            Support for {sup.target_agent.title()}: {sup.reason}
        </div><br>
        '''
        
    evidence_items = ""
    for ev in op.evidence:
        if ev in op.grounding_warnings:
            evidence_items += f'<li>{ev} <span class="inline-flex items-center gap-1 px-2 py-0.5 ml-1 bg-amber-100 text-amber-800 rounded text-[11px] font-bold border border-amber-300">⚠️ unverified claim</span></li>'
        else:
            evidence_items += f'<li>{ev}</li>'
    if not evidence_items:
        evidence_items = "<li>No specific evidence provided.</li>"
        
    concession_html = ""
    if op.concession_rationale and op.own_previous_position is not None and op.own_previous_position != op.recommendation:
        concession_html = f'''
        <div class="mb-4 p-3.5 bg-indigo-50 border border-indigo-200 rounded-lg text-xs text-indigo-950 shadow-sm">
            <div class="flex items-center gap-1.5 font-bold text-indigo-900 mb-1 text-[13px]">
                <span class="material-symbols-outlined text-[18px]">handshake</span>
                🤝 Strategic Concession Rationale:
            </div>
            <div class="italic leading-relaxed">"{escape(op.concession_rationale)}"</div>
        </div>
        '''
        
    html = f'''
    <div class="bg-surface-container-lowest border {border_class} p-6 rounded-lg relative mb-6 shadow-sm" id="{card_id}">
        <span class="absolute -top-3 left-4 bg-primary text-on-primary text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider">{phase_label}</span>
        <div class="mb-4 p-3 bg-slate-50 border border-slate-200 rounded text-xs text-slate-700 italic">
            <span class="font-semibold text-slate-900 not-italic block mb-1">⚖️ Weighing counter-consideration:</span>
            "{op.tension}"
        </div>
        <p class="font-bold text-body-lg mb-4">{op.position}</p>
        {concession_html}
        {callouts}
        <details class="group">
            <summary class="flex items-center justify-between cursor-pointer text-primary font-label-md">
                <span>Evidence</span>
                <span class="material-symbols-outlined group-open:rotate-180 transition-transform">expand_more</span>
            </summary>
            <ul class="mt-3 space-y-2 text-body-md text-on-surface-variant list-disc pl-5">
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
        bg_class = get_agent_color_class(agent_name)
        emoji = get_agent_emoji(agent_name)
        
        cards_html = ""
        for phase_idx, (phase_label, opinions) in enumerate(phases):
            op = opinions.get(agent_name)
            if op:
                cards_html += build_card_html(agent_name, phase_idx, phase_label, op)
        
        col = f'''
        <div class="flex-1 border-r border-outline-variant {bg_class} p-6" id="col-{agent_name}">
            <div class="flex items-center gap-3 mb-8">
                <span class="text-2xl">{emoji}</span>
                <h3 class="font-headline-md text-headline-md text-primary capitalize">{agent_name}</h3>
            </div>
            <div class="space-y-6">
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
    <html class="light" lang="en">
    <head>
        <meta charset="utf-8"/>
        <link href="https://fonts.googleapis.com/css2?family=Public+Sans:wght@400;500;600;700&display=swap" rel="stylesheet"/>
        <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
        <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
        <script>
            tailwind.config = {{
              darkMode: "class",
              theme: {{
                extend: {{
                  colors: {{
                    "primary": "#111d23",
                    "on-primary": "#ffffff",
                    "error": "#ba1a1a",
                    "outline-variant": "#c3c7ca",
                    "surface-container-lowest": "#ffffff",
                    "on-surface-variant": "#43474a",
                    "background": "#f9f9f9"
                  }},
                  fontFamily: {{
                    "body-md": ["Public Sans"],
                    "label-md": ["Public Sans"],
                    "headline-md": ["Public Sans"],
                    "body-lg": ["Public Sans"]
                  }}
                }}
              }}
            }}
        </script>
        <style>
            .material-symbols-outlined {{
                font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
            }}
            .conflict-line {{
                position: absolute;
                height: 2px;
                background-color: #ba1a1a;
                opacity: 0.5;
                z-index: 10;
                pointer-events: none;
            }}
            .conflict-label {{
                position: absolute;
                background: white;
                color: #ba1a1a;
                border: 1px solid #ba1a1a;
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 10px;
                font-family: 'Public Sans', sans-serif;
                font-weight: bold;
                z-index: 11;
                transform: translate(-50%, -50%);
            }}
            .hide-scrollbar::-webkit-scrollbar {{ display: none; }}
            .hide-scrollbar {{ -ms-overflow-style: none; scrollbar-width: none; }}
            details > summary {{ list-style: none; }}
            details > summary::-webkit-details-marker {{ display: none; }}
        </style>
    </head>
    <body class="bg-background font-body-md text-[#1a1c1c]">
        <main class="flex h-full overflow-hidden">
            <section class="flex-1 overflow-x-auto hide-scrollbar relative">
                <div class="absolute inset-0 pointer-events-none" id="conflict-lines-container"></div>
                <div class="flex h-full min-w-[900px]">
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
                        
                        // From the right edge of left column, or left edge of right column
                        const x1 = rect1.right - canvasRect.left;
                        const x2 = rect2.left - canvasRect.left;
                        
                        // We want the line to connect the centers vertically
                        const y1 = rect1.top + (rect1.height / 2) - canvasRect.top;
                        const y2 = rect2.top + (rect2.height / 2) - canvasRect.top;

                        const length = Math.sqrt(Math.pow(x2 - x1, 2) + Math.pow(y2 - y1, 2));
                        const angle = Math.atan2(y2 - y1, x2 - x1) * 180 / Math.PI;

                        // Start at x1,y1 (which is the right edge of the left element)
                        line.style.width = `${{length}}px`;
                        line.style.left = `${{x1}}px`;
                        line.style.top = `${{y1}}px`;
                        line.style.transform = `rotate(${{angle}}deg)`;
                        line.style.transformOrigin = '0 0';

                        container.appendChild(line);
                        
                        // Add parameter label in the middle
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
            
            // Re-draw periodically to handle dynamic parent height in Streamlit
            setInterval(drawConflictLines, 1000);
        </script>
    </body>
    </html>
    """
    return html
