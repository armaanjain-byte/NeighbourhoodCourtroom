"""Courtroom Scene Component — Visual judge's-POV animation scene.

Purpose:
    Renders a self-contained HTML/CSS/JS component presenting the courtroom timeline
    as a judge's-POV scene. Features three abstract color-coded silhouettes for
    Finance, Climate, and Community, playing through beats sequentially in real time
    with staged reveals, animated connecting lines, concession settling, and central resolutions.
    Includes playback speed controls, play/pause, and an instant full transcript fallback toggle.

Dependencies:
    engine.session.CourtroomSession, engine.timeline.build_courtroom_timeline,
    ui.components.transcript_view.get_agent_color_class, get_agent_emoji, build_card_html
"""

import json
from html import escape
import streamlit as st
import streamlit.components.v1 as components
from engine.session import CourtroomSession
from engine.timeline import build_courtroom_timeline, build_cinematic_timeline
from ui.components.transcript_view import get_agent_color_class, get_agent_emoji, build_card_html


def render_courtroom_scene(session: CourtroomSession) -> None:
    """Render the courtroom scene UI with a toggle for Real-time vs Cinematic replay modes.

    Parameters
    ----------
    session : CourtroomSession
        The courtroom session containing debate rounds and final state.
    """
    st.markdown('<div class="section-header">🎬 Courtroom Playback Mode</div>', unsafe_allow_html=True)
    mode = st.radio(
        "Playback Mode",
        options=["Real-time", "Cinematic Replay (~3 min, for demo recording)"],
        horizontal=True,
        key="courtroom_playback_mode",
    )
    is_cinematic = mode == "Cinematic Replay (~3 min, for demo recording)"
    html = build_courtroom_scene_html(session, is_cinematic=is_cinematic)
    components.html(html, height=850, scrolling=True)


def build_courtroom_scene_html(session: CourtroomSession, is_cinematic: bool = False) -> str:
    """Generate the self-contained HTML bundle for the courtroom scene animation and transcript fallback.

    Parameters
    ----------
    session : CourtroomSession
        The courtroom session containing debate rounds and final state.
    is_cinematic : bool, optional
        Whether to re-pace the timeline into a fixed-length ~3 minute experience (default False).

    Returns
    -------
    str
        The complete HTML/CSS/JS document string.
    """
    # 1. Generate timeline beats JSON
    beats = build_courtroom_timeline(session)
    if is_cinematic:
        beats = build_cinematic_timeline(beats, target_seconds=180)
    beats_json = json.dumps(beats)

    # 2. Build Full Transcript Fallback DOM (mirroring transcript_view.py)
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
                <h3 class="font-headline-md text-headline-md text-primary capitalize font-bold">{agent_name}</h3>
            </div>
            <div class="space-y-6">
                {cards_html}
            </div>
        </div>
        '''
        columns_html += col

    # Collect conflicts for transcript fallback view
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

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>Courtroom Scene Animation</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Public+Sans:wght@400;500;600;700&display=swap" rel="stylesheet"/>
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
                "body-md": ["Public Sans", "Inter", "sans-serif"],
                "label-md": ["Public Sans", "Inter", "sans-serif"],
                "headline-md": ["Public Sans", "Inter", "sans-serif"],
                "body-lg": ["Public Sans", "Inter", "sans-serif"]
              }},
              scale: {{
                "98": "0.98"
              }}
            }}
          }}
        }}
    </script>
    <style>
        body {{
            margin: 0;
            font-family: 'Inter', 'Public Sans', sans-serif;
            background: transparent;
        }}
        .material-symbols-outlined {{
            font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
        }}
        /* Custom animations */
        @keyframes pulse-flare {{
            0% {{ opacity: 0.4; box-shadow: 0 0 4px currentColor; }}
            50% {{ opacity: 1; box-shadow: 0 0 25px currentColor; }}
            100% {{ opacity: 0.4; box-shadow: 0 0 4px currentColor; }}
        }}
        .animate-pulse-flare {{
            animation: pulse-flare 1.5s infinite ease-in-out;
        }}
        @keyframes concession-settle {{
            0% {{ transform: scale(1.05); box-shadow: 0 0 30px #9f7aea; }}
            50% {{ transform: scale(0.96); box-shadow: 0 0 15px #6b46c1; }}
            100% {{ transform: scale(1.02); box-shadow: 0 0 25px #553c9a; }}
        }}
        .concession-settle {{
            animation: concession-settle 2s ease-in-out forwards;
        }}
        @keyframes fade-in {{
            from {{ opacity: 0; transform: translateY(6px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .animate-fade-in {{
            animation: fade-in 0.4s ease-out forwards;
        }}
        /* Transcript styles */
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
<body>
    <!-- ANIMATION SCENE CONTAINER -->
    <div id="animation-scene" class="relative flex flex-col justify-between w-full h-[820px] rounded-2xl overflow-hidden shadow-2xl border border-white border-opacity-10" style="background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);">
        
        <!-- Connecting lines overlay -->
        <div id="lines-container" class="absolute inset-0 pointer-events-none z-20"></div>

        <!-- Top Banner / Overlay Area -->
        <div id="status-banner" class="absolute top-6 left-0 right-0 z-30 px-8 flex justify-center pointer-events-none min-h-[100px]"></div>

        <!-- Three Silhouette Panels Stage -->
        <div id="stage-panels" class="flex-1 grid grid-cols-3 gap-8 px-8 pt-32 pb-24 z-10 items-stretch">
            
            <!-- FINANCE PANEL -->
            <div id="panel-finance" class="relative flex flex-col rounded-2xl p-6 border border-white border-opacity-20 transition-all duration-500 opacity-40 scale-98 shadow-lg overflow-y-auto hide-scrollbar" style="background-color: #744210; color: #fefcbf;">
                <div class="flex items-center justify-between border-b border-white border-opacity-20 pb-4 mb-6">
                    <div class="flex items-center gap-3">
                        <span class="material-symbols-outlined text-4xl">bar_chart</span>
                        <h3 class="text-2xl font-black tracking-wider uppercase">Finance</h3>
                    </div>
                    <span class="text-xs font-bold px-3 py-1 bg-black bg-opacity-30 rounded-full text-[#fefcbf]">AGENT</span>
                </div>
                <div id="content-finance" class="flex-1 flex flex-col space-y-4"></div>
            </div>

            <!-- CLIMATE PANEL -->
            <div id="panel-climate" class="relative flex flex-col rounded-2xl p-6 border border-white border-opacity-20 transition-all duration-500 opacity-40 scale-98 shadow-lg overflow-y-auto hide-scrollbar" style="background-color: #276749; color: #c6f6d5;">
                <div class="flex items-center justify-between border-b border-white border-opacity-20 pb-4 mb-6">
                    <div class="flex items-center gap-3">
                        <span class="material-symbols-outlined text-4xl">eco</span>
                        <h3 class="text-2xl font-black tracking-wider uppercase">Climate</h3>
                    </div>
                    <span class="text-xs font-bold px-3 py-1 bg-black bg-opacity-30 rounded-full text-[#c6f6d5]">AGENT</span>
                </div>
                <div id="content-climate" class="flex-1 flex flex-col space-y-4"></div>
            </div>

            <!-- COMMUNITY PANEL -->
            <div id="panel-community" class="relative flex flex-col rounded-2xl p-6 border border-white border-opacity-20 transition-all duration-500 opacity-40 scale-98 shadow-lg overflow-y-auto hide-scrollbar" style="background-color: #553c9a; color: #e9d8fd;">
                <div class="flex items-center justify-between border-b border-white border-opacity-20 pb-4 mb-6">
                    <div class="flex items-center gap-3">
                        <span class="material-symbols-outlined text-4xl">other_houses</span>
                        <h3 class="text-2xl font-black tracking-wider uppercase">Community</h3>
                    </div>
                    <span class="text-xs font-bold px-3 py-1 bg-black bg-opacity-30 rounded-full text-[#e9d8fd]">AGENT</span>
                </div>
                <div id="content-community" class="flex-1 flex flex-col space-y-4"></div>
            </div>

        </div>

        <!-- Bottom Judge's Bench Console -->
        <div id="judges-bench" class="relative z-30 flex items-center justify-between px-8 py-5 border-t border-white border-opacity-15 shadow-2xl" style="background: rgba(15, 12, 41, 0.85); backdrop-filter: blur(16px);">
            <!-- Play/Pause and Speed Controls -->
            <div class="flex items-center gap-4">
                <button id="btn-play-pause" onclick="togglePlay()" class="flex items-center gap-2 px-6 py-2.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-extrabold text-sm rounded-xl shadow-lg transition-all transform active:scale-95">
                    ⏸️ Pause
                </button>
                <div class="flex items-center bg-black bg-opacity-40 p-1 rounded-xl border border-white border-opacity-10">
                    <button id="btn-speed-1" onclick="setSpeed(1)" class="speed-btn px-4 py-1.5 rounded-lg text-xs font-bold bg-indigo-600 text-white transition-all">1x</button>
                    <button id="btn-speed-2" onclick="setSpeed(2)" class="speed-btn px-4 py-1.5 rounded-lg text-xs font-bold text-slate-300 hover:text-white transition-all">2x</button>
                    <button id="btn-speed-4" onclick="setSpeed(4)" class="speed-btn px-4 py-1.5 rounded-lg text-xs font-bold text-slate-300 hover:text-white transition-all">4x</button>
                </div>
            </div>

            <!-- Progress & Status Indicator -->
            <div class="flex-1 max-w-md mx-8 flex flex-col items-center">
                <div id="beat-label" class="text-xs font-bold text-slate-300 uppercase tracking-wider mb-2">Initializing Courtroom Scene...</div>
                <div class="w-full h-2 bg-black bg-opacity-50 rounded-full overflow-hidden border border-white border-opacity-10 shadow-inner">
                    <div id="beat-progress-fill" class="h-full bg-gradient-to-r from-pink-500 via-purple-500 to-indigo-500 w-0 transition-all duration-300"></div>
                </div>
            </div>

            <!-- Toggle Full Transcript Fallback -->
            <button onclick="toggleTranscriptView()" class="flex items-center gap-2 px-6 py-2.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-sm rounded-xl border border-white border-opacity-20 shadow-lg transition-all transform active:scale-95">
                📜 View Full Transcript
            </button>
        </div>

    </div>

    <!-- FULL TRANSCRIPT FALLBACK CONTAINER -->
    <div id="full-transcript-view" class="hidden bg-background font-body-md text-[#1a1c1c] w-full min-h-[820px] rounded-2xl border border-outline-variant overflow-hidden shadow-2xl flex flex-col">
        <!-- Top Action Bar -->
        <div class="bg-primary text-on-primary px-8 py-4 flex items-center justify-between border-b border-outline-variant">
            <div class="flex items-center gap-3">
                <span class="material-symbols-outlined text-3xl">history_edu</span>
                <h2 class="text-xl font-bold tracking-wide">Full Debate Transcript & Conflict Mapping</h2>
            </div>
            <button onclick="toggleTranscriptView()" class="flex items-center gap-2 px-6 py-2 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-bold text-sm rounded-xl shadow-lg transition-all transform active:scale-95">
                🎭 Return to Animation Scene
            </button>
        </div>
        <!-- Transcript Columns -->
        <main class="flex-1 flex overflow-hidden">
            <section class="flex-1 overflow-x-auto hide-scrollbar relative p-4">
                <div class="absolute inset-0 pointer-events-none" id="conflict-lines-container"></div>
                <div class="flex h-full min-w-[900px]">
                    {columns_html}
                </div>
            </section>
        </main>
    </div>

    <!-- JAVASCRIPT PLAYBACK ENGINE & TRANSCRIPT MAPPING -->
    <script>
        const beats = {beats_json};
        let currentBeatIndex = 0;
        let isPlaying = true;
        let speedMultiplier = 1;
        let timeoutId = null;
        let subTimeoutIds = [];

        function clearAllTimeouts() {{
            if (timeoutId) clearTimeout(timeoutId);
            subTimeoutIds.forEach(id => clearTimeout(id));
            subTimeoutIds = [];
        }}

        function setSpeed(mult) {{
            speedMultiplier = mult;
            document.querySelectorAll('.speed-btn').forEach(btn => btn.classList.remove('bg-indigo-600', 'text-white'));
            document.getElementById(`btn-speed-${{mult}}`).classList.add('bg-indigo-600', 'text-white');
            if (isPlaying) {{
                playBeat(currentBeatIndex);
            }}
        }}

        function togglePlay() {{
            isPlaying = !isPlaying;
            const btn = document.getElementById('btn-play-pause');
            if (isPlaying) {{
                btn.innerHTML = '⏸️ Pause';
                playBeat(currentBeatIndex);
            }} else {{
                btn.innerHTML = '▶️ Play';
                clearAllTimeouts();
            }}
        }}

        function toggleTranscriptView() {{
            clearAllTimeouts();
            isPlaying = false;
            document.getElementById('btn-play-pause').innerHTML = '▶️ Play';
            document.getElementById('animation-scene').classList.toggle('hidden');
            document.getElementById('full-transcript-view').classList.toggle('hidden');
            setTimeout(drawConflictLines, 200);
        }}

        function drawConnectionLine(fromAgent, toAgent, colorHex, labelText, isPulse = false) {{
            const container = document.getElementById('lines-container');
            const el1 = document.getElementById(`panel-${{fromAgent}}`);
            const el2 = document.getElementById(`panel-${{toAgent}}`);
            if (!el1 || !el2) return;

            const rect1 = el1.getBoundingClientRect();
            const rect2 = el2.getBoundingClientRect();
            const canvasRect = container.getBoundingClientRect();

            // Connect centers
            const x1 = rect1.left + (rect1.width / 2) - canvasRect.left;
            const y1 = rect1.top + (rect1.height / 2) - canvasRect.top;
            const x2 = rect2.left + (rect2.width / 2) - canvasRect.left;
            const y2 = rect2.top + (rect2.height / 2) - canvasRect.top;

            const length = Math.sqrt(Math.pow(x2 - x1, 2) + Math.pow(y2 - y1, 2));
            const angle = Math.atan2(y2 - y1, x2 - x1) * 180 / Math.PI;

            const line = document.createElement('div');
            line.className = `absolute h-1.5 z-20 origin-top-left transition-all duration-300 ${{isPulse ? 'animate-pulse-flare' : ''}}`;
            line.style.width = `${{length}}px`;
            line.style.left = `${{x1}}px`;
            line.style.top = `${{y1}}px`;
            line.style.backgroundColor = colorHex;
            line.style.transform = `rotate(${{angle}}deg)`;
            line.style.boxShadow = `0 0 16px ${{colorHex}}`;
            container.appendChild(line);

            if (labelText) {{
                const label = document.createElement('div');
                label.className = 'absolute bg-slate-900 text-white border-2 px-4 py-1.5 rounded-full text-xs font-extrabold z-30 shadow-2xl transform -translate-x-1/2 -translate-y-1/2';
                label.style.borderColor = colorHex;
                label.style.left = `${{x1 + (x2 - x1) / 2}}px`;
                label.style.top = `${{y1 + (y2 - y1) / 2}}px`;
                label.innerText = labelText;
                container.appendChild(label);
            }}
        }}

        function playBeat(index) {{
            clearAllTimeouts();
            if (index >= beats.length) {{
                isPlaying = false;
                document.getElementById('btn-play-pause').innerHTML = '▶️ Play';
                return;
            }}
            currentBeatIndex = index;

            const beat = beats[index];
            const duration = (beat.duration_hint_seconds || 5) * 1000 / speedMultiplier;

            // Update progress bar & label
            const progressPct = ((index + 1) / beats.length) * 100;
            document.getElementById('beat-progress-fill').style.width = `${{progressPct}}%`;
            document.getElementById('beat-label').innerText = `Round ${{beat.round_number}} · ${{beat.beat_type.replace('_', ' ').toUpperCase()}} (${{index + 1}}/${{beats.length}})`;

            // Reset UI state
            document.getElementById('lines-container').innerHTML = '';
            document.getElementById('status-banner').innerHTML = '';
            ['finance', 'climate', 'community'].forEach(agent => {{
                const panel = document.getElementById(`panel-${{agent}}`);
                if (panel) {{
                    panel.className = panel.className.replace(/scale-105|ring-4|ring-white|opacity-100|concession-settle|shadow-2xl/g, '');
                    panel.classList.add('opacity-40', 'scale-98', 'shadow-lg');
                    document.getElementById(`content-${{agent}}`).innerHTML = '';
                }}
            }});

            function activatePanel(agent) {{
                const panel = document.getElementById(`panel-${{agent}}`);
                if (panel) {{
                    panel.classList.remove('opacity-40', 'scale-98', 'shadow-lg');
                    panel.classList.add('opacity-100', 'scale-105', 'ring-4', 'ring-white', 'shadow-2xl');
                }}
            }}

            // Handle beat types
            if (beat.beat_type === 'round_start') {{
                ['finance', 'climate', 'community'].forEach(agent => {{
                    const p = document.getElementById(`panel-${{agent}}`);
                    p.classList.remove('opacity-40', 'scale-98');
                    p.classList.add('opacity-90');
                }});
                document.getElementById('status-banner').innerHTML = `
                    <div class="bg-indigo-950 bg-opacity-95 text-white border-2 border-indigo-400 p-6 rounded-3xl shadow-2xl text-center animate-bounce max-w-xl mx-auto">
                        <h2 class="text-2xl font-black tracking-wider uppercase">⚖️ Round ${{beat.round_number}} Commencing</h2>
                        <p class="text-indigo-200 text-sm mt-2 font-semibold">${{beat.content.message || ''}}</p>
                    </div>
                `;
            }} 
            else if (beat.beat_type === 'agent_statement') {{
                activatePanel(beat.agent);
                const c = beat.content;
                const container = document.getElementById(`content-${{beat.agent}}`);
                
                container.innerHTML = `
                    <div id="stmt-tension" class="bg-black bg-opacity-25 p-4 rounded-xl border-l-4 border-amber-300 text-xs italic text-white mb-4 shadow-inner">
                        <div class="font-bold text-amber-300 not-italic mb-1.5 flex items-center gap-1.5 text-[13px]">
                            <span class="material-symbols-outlined text-[18px]">balance</span>
                            Internal Deliberation & Tension:
                        </div>
                        "${{c.tension || ''}}"
                    </div>
                    <div id="stmt-position" class="hidden font-black text-xl text-white mb-4 tracking-wide leading-snug"></div>
                    <div id="stmt-reasoning" class="hidden text-sm text-slate-100 mb-4 leading-relaxed bg-black bg-opacity-20 p-4 rounded-xl border border-white border-opacity-10 font-medium"></div>
                    <div id="stmt-evidence" class="hidden bg-black bg-opacity-25 p-4 rounded-xl border border-white border-opacity-10">
                        <div class="font-bold text-xs text-white uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
                            <span class="material-symbols-outlined text-[18px]">plagiarism</span>
                            Supporting Evidence:
                        </div>
                        <ul id="evidence-list" class="list-disc pl-5 text-xs text-slate-200 space-y-1.5 font-medium"></ul>
                    </div>
                `;

                subTimeoutIds.push(setTimeout(() => {{
                    const pEl = document.getElementById('stmt-position');
                    if (pEl) {{
                        pEl.innerText = c.position || '';
                        pEl.classList.remove('hidden');
                        pEl.classList.add('animate-fade-in');
                    }}
                }}, duration * 0.25));

                subTimeoutIds.push(setTimeout(() => {{
                    const rEl = document.getElementById('stmt-reasoning');
                    if (rEl) {{
                        rEl.innerText = c.reasoning || '';
                        rEl.classList.remove('hidden');
                        rEl.classList.add('animate-fade-in');
                    }}
                }}, duration * 0.50));

                subTimeoutIds.push(setTimeout(() => {{
                    const eEl = document.getElementById('stmt-evidence');
                    const eList = document.getElementById('evidence-list');
                    if (eEl && eList) {{
                        (c.evidence || []).forEach(ev => {{
                            const li = document.createElement('li');
                            li.innerText = ev;
                            eList.appendChild(li);
                        }});
                        if (!c.evidence || c.evidence.length === 0) {{
                            eList.innerHTML = '<li>No specific evidence cited.</li>';
                        }}
                        eEl.classList.remove('hidden');
                        eEl.classList.add('animate-fade-in');
                    }}
                }}, duration * 0.75));
            }}
            else if (beat.beat_type === 'objection' || beat.beat_type === 'support') {{
                activatePanel(beat.agent);
                const isObj = beat.beat_type === 'objection';
                const colorHex = isObj ? '#fc8181' : '#48bb78';
                const c = beat.content;
                
                const container = document.getElementById(`content-${{beat.agent}}`);
                container.innerHTML = `
                    <div class="bg-black bg-opacity-35 border-2 p-5 rounded-2xl shadow-2xl mb-4 text-white animate-fade-in" style="border-color: ${{colorHex}}">
                        <div class="flex items-center gap-2 font-black text-sm mb-3" style="color: ${{colorHex}}">
                            <span class="material-symbols-outlined text-[22px]">${{isObj ? 'gavel' : 'handshake'}}</span>
                            ${{isObj ? 'Objection to' : 'Support for'}} ${{beat.target_agent.toUpperCase()}}
                        </div>
                        <div class="text-xs bg-black bg-opacity-50 p-3 rounded-xl mb-4 italic border-l-4 shadow-inner" style="border-color: ${{colorHex}}">
                            Claim: "${{c.engages_with || ''}}"
                        </div>
                        <div class="text-sm leading-relaxed font-semibold">${{c.reason || ''}}</div>
                    </div>
                `;

                drawConnectionLine(beat.target_agent, beat.agent, colorHex, c.engages_with);
            }}
            else if (beat.beat_type === 'conflict_flare') {{
                activatePanel(beat.agent);
                activatePanel(beat.target_agent);
                
                const c = beat.content;
                let colorHex = '#ecc94b'; 
                if (beat.severity === 'medium') colorHex = '#ed8936'; 
                if (beat.severity === 'high') colorHex = '#e53e3e'; 

                drawConnectionLine(beat.agent, beat.target_agent, colorHex, `${{c.parameter}} (${{beat.severity.toUpperCase()}})`, true);

                document.getElementById('status-banner').innerHTML = `
                    <div class="bg-black bg-opacity-90 border-2 p-6 rounded-3xl shadow-2xl text-white text-center animate-bounce max-w-2xl mx-auto" style="border-color: ${{colorHex}}">
                        <div class="flex items-center justify-center gap-2 font-black text-xl tracking-wide uppercase" style="color: ${{colorHex}}">
                            <span class="material-symbols-outlined text-[28px]">warning</span>
                            Conflict Flare: ${{c.parameter}} (${{beat.severity.toUpperCase()}} Severity)
                        </div>
                        <div class="flex items-center justify-center gap-6 mt-4 text-sm font-bold">
                            <div class="bg-white bg-opacity-10 px-5 py-2.5 rounded-xl border border-white border-opacity-10">${{beat.agent.toUpperCase()}} proposed: ${{c.proposed_value_a}}</div>
                            <div class="text-slate-400 font-extrabold">vs</div>
                            <div class="bg-white bg-opacity-10 px-5 py-2.5 rounded-xl border border-white border-opacity-10">${{beat.target_agent.toUpperCase()}} proposed: ${{c.proposed_value_b}}</div>
                        </div>
                    </div>
                `;
            }}
            else if (beat.beat_type === 'concession') {{
                activatePanel(beat.agent);
                const panel = document.getElementById(`panel-${{beat.agent}}`);
                panel.classList.add('concession-settle');

                const c = beat.content;
                const container = document.getElementById(`content-${{beat.agent}}`);
                container.innerHTML = `
                    <div class="bg-indigo-950 bg-opacity-90 border-2 border-indigo-400 p-6 rounded-3xl shadow-2xl text-white animate-fade-in">
                        <div class="flex items-center gap-2 font-black text-indigo-300 text-sm mb-3 tracking-wide uppercase">
                            <span class="material-symbols-outlined text-[24px]">handshake</span>
                            🤝 Strategic Concession Rationale
                        </div>
                        <div class="text-sm italic leading-relaxed bg-black bg-opacity-50 p-4 rounded-xl border border-indigo-500 border-opacity-30 font-medium">
                            "${{c.concession_rationale || ''}}"
                        </div>
                    </div>
                `;
            }}
            else if (beat.beat_type === 'round_resolution' || beat.beat_type === 'final_verdict') {{
                ['finance', 'climate', 'community'].forEach(agent => {{
                    const p = document.getElementById(`panel-${{agent}}`);
                    p.classList.remove('opacity-40', 'scale-98');
                    p.classList.add('opacity-90');
                }});
                
                const isFinal = beat.beat_type === 'final_verdict';
                const c = beat.content;
                
                let title = `⚖️ Round ${{beat.round_number}} Resolution Achieved`;
                let desc = c.engine_summary || '';
                let extraHtml = '';

                if (isFinal) {{
                    title = `🏛️ Final Courtroom Verdict · ${{c.outcome ? c.outcome.toUpperCase() : 'COMPLETED'}}`;
                    desc = `Session status: ${{c.status}}`;
                    if (c.unresolved_conflicts && c.unresolved_conflicts.length > 0) {{
                        extraHtml = `
                            <div class="mt-5 bg-red-950 bg-opacity-90 border border-red-500 p-5 rounded-2xl text-left text-red-200 text-sm shadow-inner">
                                <div class="font-black text-red-400 uppercase mb-2 flex items-center gap-1.5 text-[15px]">
                                    <span class="material-symbols-outlined text-[20px]">gavel</span>
                                    Escalated to Human Review (High Conflicts Persist):
                                </div>
                                <ul class="list-disc pl-6 space-y-1.5 font-bold">
                                    ${{c.unresolved_conflicts.map(p => `<li>${{p}}</li>`).join('')}}
                                </ul>
                            </div>
                        `;
                    }} else {{
                        extraHtml = `
                            <div class="mt-5 bg-emerald-950 bg-opacity-90 border border-emerald-500 p-5 rounded-2xl text-emerald-200 text-sm font-bold flex items-center justify-center gap-2 shadow-inner">
                                <span class="material-symbols-outlined text-[22px]">check_circle</span>
                                All conflicts successfully resolved or auto-settled by engine.
                            </div>
                        `;
                    }}
                }}

                document.getElementById('status-banner').innerHTML = `
                    <div class="bg-slate-900 bg-opacity-95 border-2 border-slate-500 p-8 rounded-3xl shadow-2xl max-w-2xl mx-auto text-center animate-fade-in">
                        <h2 class="text-2xl font-black tracking-wider text-white uppercase">${{title}}</h2>
                        <p class="text-slate-300 text-base mt-3 font-semibold">${{desc}}</p>
                        ${{extraHtml}}
                    </div>
                `;
            }}

            if (isPlaying) {{
                timeoutId = setTimeout(() => {{
                    playBeat(index + 1);
                }}, duration);
            }}
        }}

        // Transcript Conflict Lines Drawing Logic
        function drawConflictLines() {{
            const container = document.getElementById('conflict-lines-container');
            if (!container) return;
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

        window.addEventListener('load', () => {{
            playBeat(0);
        }});
        window.addEventListener('resize', () => {{
            if (document.getElementById('full-transcript-view').classList.contains('hidden')) {{
                // Redraw scene lines if needed
                playBeat(currentBeatIndex);
            }} else {{
                drawConflictLines();
            }}
        }});
        setInterval(() => {{
            if (!document.getElementById('full-transcript-view').classList.contains('hidden')) {{
                drawConflictLines();
            }}
        }}, 1000);
    </script>
</body>
</html>"""
    return html
