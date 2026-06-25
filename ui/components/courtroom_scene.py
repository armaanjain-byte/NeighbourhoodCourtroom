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


def render_live_feed(events: list) -> None:
    """Render the live chat-bubble courtroom feed during an active debate.

    Parameters
    ----------
    events : list[dict]
        Ordered list of event dicts yielded by ``stream_round``.
    """
    html = build_live_feed_html(events)
    components.html(html, height=900, scrolling=True)


def build_live_feed_html(events: list) -> str:
    """Build a self-contained HTML document showing the live courtroom chat feed.

    The document renders the full event list on every call (safe to call
    repeatedly as Streamlit reruns the page). Bubbles already seen in a
    previous render are detected via ``sessionStorage`` and rendered without
    animation — only genuinely new bubbles animate in, giving a live feel
    without a jarring full-replay flicker on every Streamlit rerun.

    Parameters
    ----------
    events : list[dict]
        Ordered list of event dicts as produced by
        :meth:`~engine.session.CourtroomSession.stream_round`.

    Returns
    -------
    str
        Complete, self-contained ``<!DOCTYPE html>`` document string.
    """
    import json as _json
    events_json = _json.dumps(events)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Live Courtroom Feed</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet"/>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: 'Inter', sans-serif;
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    min-height: 100vh;
    color: #e2e8f0;
}}

/* ── Layout ── */
.courtroom-wrap {{
    display: flex;
    flex-direction: column;
    gap: 0;
    padding: 12px;
    min-height: 880px;
}}
.agent-columns {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 12px;
}}
.system-strip {{
    padding: 4px 0;
}}

/* ── Agent column ── */
.agent-col {{
    display: flex;
    flex-direction: column;
    border-radius: 16px;
    overflow: hidden;
    border: 1px solid rgba(255,255,255,0.12);
    background: rgba(255,255,255,0.04);
    min-height: 200px;
}}
.agent-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 16px 12px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    position: relative;
}}
.agent-icon {{ font-size: 1.6rem; }}
.agent-label {{
    font-size: 0.78rem;
    font-weight: 800;
    letter-spacing: 0.12em;
    text-transform: uppercase;
}}
.presence-dot {{
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #4a5568;
    margin-left: auto;
    transition: background 0.3s;
    flex-shrink: 0;
}}
.presence-dot.thinking {{
    background: #f6ad55;
    animation: presence-pulse 1.0s ease-in-out infinite;
}}
.presence-dot.spoke {{
    background: #68d391;
    animation: none;
}}

@keyframes presence-pulse {{
    0%,100% {{ box-shadow: 0 0 0 0 rgba(246,173,85,0.7); }}
    50% {{ box-shadow: 0 0 0 6px rgba(246,173,85,0); }}
}}

.agent-feed {{
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px;
    overflow-y: auto;
}}

/* ── Column flash overlay ── */
.col-flash {{
    position: absolute;
    inset: 0;
    border-radius: 16px;
    pointer-events: none;
    opacity: 0;
    z-index: 10;
}}
.col-flash.flash-red {{
    background: rgba(252,129,129,0.35);
    animation: col-flash-anim 0.7s ease-out forwards;
}}
.col-flash.flash-green {{
    background: rgba(72,187,120,0.3);
    animation: col-flash-anim 0.7s ease-out forwards;
}}
@keyframes col-flash-anim {{
    0%   {{ opacity: 1; }}
    100% {{ opacity: 0; }}
}}

/* ── Chat bubbles ── */
.bubble {{
    border-radius: 14px;
    padding: 12px 14px;
    font-size: 0.84rem;
    line-height: 1.55;
    border: 1px solid rgba(255,255,255,0.1);
    position: relative;
    word-break: break-word;
}}
.bubble.bubble-new {{
    animation: bubble-popin 0.32s cubic-bezier(0.34,1.56,0.64,1) forwards;
}}
.bubble.bubble-static {{
    animation: none;
    opacity: 1;
    transform: none;
}}
@keyframes bubble-popin {{
    from {{ opacity: 0; transform: scale(0.88) translateY(8px); }}
    to   {{ opacity: 1; transform: scale(1)   translateY(0); }}
}}

/* Position bubble: main statement */
.bubble-position {{
    background: rgba(255,255,255,0.07);
    border-left: 3px solid rgba(255,255,255,0.3);
}}
.bubble-position .position-text {{
    font-weight: 700;
    font-size: 0.92rem;
    margin-bottom: 8px;
}}
.bubble-position .round-tag {{
    display: inline-block;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 20px;
    background: rgba(255,255,255,0.12);
    color: rgba(255,255,255,0.7);
    margin-bottom: 6px;
}}

/* Expandable detail */
details.bubble-detail {{
    margin-top: 6px;
}}
details.bubble-detail summary {{
    font-size: 0.7rem;
    font-weight: 600;
    color: rgba(255,255,255,0.5);
    cursor: pointer;
    user-select: none;
    list-style: none;
    padding: 3px 0;
}}
details.bubble-detail summary::-webkit-details-marker {{ display: none; }}
details.bubble-detail summary::before {{ content: '▶ '; font-size: 0.6rem; }}
details.bubble-detail[open] summary::before {{ content: '▼ '; }}
.detail-body {{
    margin-top: 6px;
    font-size: 0.78rem;
    color: rgba(255,255,255,0.65);
    line-height: 1.5;
}}
.evidence-list {{
    margin-top: 5px;
    padding-left: 14px;
    font-size: 0.75rem;
    color: rgba(255,255,255,0.5);
}}
.evidence-list li {{ margin-bottom: 2px; }}

/* Objection bubble */
.bubble-objection {{
    border: 2px solid #fc8181;
    background: rgba(252,129,129,0.08);
}}
.bubble-objection .obj-header {{
    font-size: 0.72rem;
    font-weight: 800;
    color: #fc8181;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 5px;
}}
.bubble-objection .obj-claim {{
    font-size: 0.74rem;
    color: rgba(252,129,129,0.75);
    font-style: italic;
    margin-bottom: 5px;
    padding: 4px 8px;
    background: rgba(252,129,129,0.06);
    border-radius: 6px;
    border-left: 2px solid rgba(252,129,129,0.4);
}}
.bubble-objection .obj-reason {{ font-size: 0.82rem; font-weight: 500; }}

/* Support bubble */
.bubble-support {{
    border: 2px solid #68d391;
    background: rgba(72,187,120,0.07);
}}
.bubble-support .sup-header {{
    font-size: 0.72rem;
    font-weight: 800;
    color: #68d391;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 5px;
}}

/* Concession bubble */
.bubble-concession {{
    border: 2px solid #fbd38d;
    background: rgba(251,211,141,0.07);
}}
.bubble-concession .con-header {{
    font-size: 0.72rem;
    font-weight: 800;
    color: #fbd38d;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 5px;
}}

/* ── Thinking indicator ── */
.thinking-indicator {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 0.75rem;
    color: rgba(255,255,255,0.45);
    padding: 6px 10px;
    font-style: italic;
}}
.thinking-dots span {{
    display: inline-block;
    width: 5px; height: 5px;
    border-radius: 50%;
    background: rgba(255,255,255,0.4);
    animation: dot-bounce 1.2s infinite;
}}
.thinking-dots span:nth-child(2) {{ animation-delay: 0.2s; }}
.thinking-dots span:nth-child(3) {{ animation-delay: 0.4s; }}
@keyframes dot-bounce {{
    0%,80%,100% {{ transform: translateY(0); }}
    40% {{ transform: translateY(-6px); }}
}}

/* ── System strips (conflict dividers, banners) ── */
.system-banner {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 16px;
    border-radius: 10px;
    font-size: 0.78rem;
    font-weight: 700;
    margin: 6px 0;
    border: 1px solid rgba(255,255,255,0.08);
    animation: banner-fadein 0.5s ease-out forwards;
}}
@keyframes banner-fadein {{
    from {{ opacity: 0; transform: scaleX(0.96); }}
    to   {{ opacity: 1; transform: scaleX(1); }}
}}
.banner-conflict-high  {{ background: rgba(126,34,34,0.55); border-color: #fc8181; color: #fed7d7; }}
.banner-conflict-medium{{ background: rgba(116,66,16,0.55); border-color: #f6ad55; color: #fefcbf; }}
.banner-conflict-low   {{ background: rgba(22,78,51,0.5);  border-color: #68d391; color: #c6f6d5; }}
.banner-neutral        {{ background: rgba(30,30,60,0.7);   border-color: rgba(255,255,255,0.15); color: #e2e8f0; }}
.banner-r3             {{ background: rgba(88,28,135,0.6);  border-color: #b794f4; color: #e9d8fd; }}
.banner-complete       {{ background: rgba(22,78,51,0.6);   border-color: #68d391; color: #c6f6d5; }}
.sev-badge {{
    display: inline-block;
    font-size: 0.65rem;
    font-weight: 800;
    padding: 2px 8px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}}
.sev-badge.high   {{ background: #742a2a; color: #feb2b2; }}
.sev-badge.medium {{ background: #744210; color: #fefcbf; }}
.sev-badge.low    {{ background: #276749; color: #c6f6d5; }}

/* Agent-specific tint colors */
.col-finance  {{ border-top: 3px solid #d69e2e; }}
.col-climate  {{ border-top: 3px solid #38a169; }}
.col-community{{ border-top: 3px solid #6b46c1; }}
.col-finance  .agent-header  {{ background: rgba(116,66,16,0.25); }}
.col-climate  .agent-header  {{ background: rgba(39,103,73,0.25); }}
.col-community .agent-header {{ background: rgba(85,60,154,0.25); }}

.thinking-strip {{
    font-size: 0.68rem;
    font-style: italic;
    color: rgba(255,255,255,0.35);
    padding: 4px 10px;
    display: none;
}}
</style>
</head>
<body>
<div class="courtroom-wrap">
  <!-- Three agent columns -->
  <div class="agent-columns" id="columns-row">
    <div class="agent-col col-finance" id="col-finance">
      <div class="agent-header">
        <span class="agent-icon">💰</span>
        <span class="agent-label">Finance</span>
        <div class="presence-dot" id="dot-finance"></div>
        <div class="col-flash" id="flash-finance"></div>
      </div>
      <div class="agent-feed" id="feed-finance"></div>
    </div>
    <div class="agent-col col-climate" id="col-climate">
      <div class="agent-header">
        <span class="agent-icon">🌿</span>
        <span class="agent-label">Climate</span>
        <div class="presence-dot" id="dot-climate"></div>
        <div class="col-flash" id="flash-climate"></div>
      </div>
      <div class="agent-feed" id="feed-climate"></div>
    </div>
    <div class="agent-col col-community" id="col-community">
      <div class="agent-header">
        <span class="agent-icon">🏘️</span>
        <span class="agent-label">Community</span>
        <div class="presence-dot" id="dot-community"></div>
        <div class="col-flash" id="flash-community"></div>
      </div>
      <div class="agent-feed" id="feed-community"></div>
    </div>
  </div>

  <!-- System events strip (conflict dividers, round3, complete) -->
  <div id="system-strip" class="system-strip"></div>
</div>

<script>
(function() {{
    const events = {events_json};

    // sessionStorage key for tracking rendered bubble IDs
    const STORAGE_KEY = 'ncrt_rendered_bubbles';

    function getRendered() {{
        try {{
            return new Set(JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]'));
        }} catch(e) {{
            return new Set();
        }}
    }}
    function saveRendered(set) {{
        try {{
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...set]));
        }} catch(e) {{}}
    }}

    const rendered = getRendered();
    const newlyRendered = new Set();

    // Helpers
    function feed(agent) {{
        return document.getElementById('feed-' + agent);
    }}
    function dot(agent) {{
        return document.getElementById('dot-' + agent);
    }}
    function flashCol(agent, color) {{
        const el = document.getElementById('flash-' + agent);
        if (!el) return;
        el.className = 'col-flash flash-' + color;
        // reset after animation
        setTimeout(() => {{ el.className = 'col-flash'; }}, 800);
    }}

    function addBubble(agent, id, html) {{
        const container = feed(agent);
        if (!container) return;
        const div = document.createElement('div');
        const isNew = !rendered.has(id);
        div.className = 'bubble ' + (isNew ? 'bubble-new' : 'bubble-static');
        div.dataset.bubbleId = id;
        div.innerHTML = html;
        container.appendChild(div);
        if (isNew) {{
            newlyRendered.add(id);
            container.scrollTop = container.scrollHeight;
        }}
    }}

    function addThinking(agent) {{
        const container = feed(agent);
        if (!container) return;
        // Remove old thinking indicator for this agent
        const old = container.querySelector('.thinking-indicator');
        if (old) old.remove();
        const div = document.createElement('div');
        div.className = 'thinking-indicator';
        div.id = 'thinking-' + agent;
        div.innerHTML = '<span>Thinking</span><span class="thinking-dots"><span></span><span></span><span></span></span>';
        container.appendChild(div);
        container.scrollTop = container.scrollHeight;
    }}

    function removeThinking(agent) {{
        const indicator = document.getElementById('thinking-' + agent);
        if (indicator) indicator.remove();
    }}

    function addSystem(html) {{
        const strip = document.getElementById('system-strip');
        if (!strip) return;
        const div = document.createElement('div');
        div.innerHTML = html;
        strip.appendChild(div);
    }}

    function escHtml(s) {{
        if (!s) return '';
        return String(s)
            .replace(/&/g,'&amp;')
            .replace(/</g,'&lt;')
            .replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;');
    }}

    function renderPositionBubble(ev) {{
        const op = ev.opinion || {{}};
        const rn = ev.round;
        const agent = ev.agent;
        const id = 'pos-' + agent + '-r' + rn + '-' + (op.position || '').slice(0,20).replace(/\W/g,'');

        const reasoning = escHtml(op.reasoning || '');
        const evidence = (op.evidence || []).map(e => `<li>${{escHtml(e)}}</li>`).join('');
        const tension = escHtml(op.tension || '');
        const hasConcession = op.concession_rationale && op.concession_rationale.trim();
        const isFallback = op.is_fallback;
        const fallbackTag = isFallback ? `<span style="display:inline-block;font-size:0.65rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;padding:2px 8px;border-radius:20px;background:rgba(255,255,255,0.08);color:rgba(255,255,255,0.5);margin-bottom:6px;margin-left:6px;">⚙️ Baseline calc</span>` : '';

        let positionHtml;

        if (hasConcession) {{
            positionHtml = `
                <div class="bubble bubble-concession">
                    <div class="con-header">🤝 Concession · Round ${{rn}}${{fallbackTag}}</div>
                    <div class="position-text">${{escHtml(op.position || '')}}</div>
                    <details class="bubble-detail">
                        <summary>Concession rationale &amp; detail</summary>
                        <div class="detail-body">
                            <em style="color:rgba(251,211,141,0.8)">${{escHtml(op.concession_rationale)}}</em>
                            ${{reasoning ? `<p style="margin-top:6px">${{reasoning}}</p>` : ''}}
                            ${{evidence ? `<ul class="evidence-list">${{evidence}}</ul>` : ''}}
                        </div>
                    </details>
                </div>`;
        }} else {{
            positionHtml = `
                <span class="round-tag">Round ${{rn}}</span>${{fallbackTag}}
                <div class="position-text">${{escHtml(op.position || '')}}</div>
                <details class="bubble-detail">
                    <summary>Reasoning &amp; evidence</summary>
                    <div class="detail-body">
                        ${{tension ? `<p style="margin-bottom:4px;font-style:italic;color:rgba(255,255,255,0.45)">"${{tension}}"</p>` : ''}}
                        ${{reasoning ? `<p>${{reasoning}}</p>` : ''}}
                        ${{evidence ? `<ul class="evidence-list">${{evidence}}</ul>` : ''}}
                    </div>
                </details>`;
        }}

        const bubbleId = id + '-pos';
        const isNew = !rendered.has(bubbleId);
        const container = feed(agent);
        if (!container) return;
        const div = document.createElement('div');
        div.className = 'bubble bubble-position ' + (isNew ? 'bubble-new' : 'bubble-static');
        div.dataset.bubbleId = bubbleId;
        div.innerHTML = positionHtml;
        container.appendChild(div);
        if (isNew) {{
            newlyRendered.add(bubbleId);
            container.scrollTop = container.scrollHeight;
        }}

        // Objections
        (op.objections || []).forEach((obj, idx) => {{
            const objId = 'obj-' + agent + '-r' + rn + '-' + idx;
            if (!rendered.has(objId)) {{
                newlyRendered.add(objId);
                // Flash the target column
                if (obj.target_agent) flashCol(obj.target_agent, 'red');
            }}
            const objHtml = `
                <div class="obj-header">⚡ Objection → ${{escHtml((obj.target_agent || '').toUpperCase())}}</div>
                <div class="obj-claim">Claim: "${{escHtml(obj.engages_with || '')}}"</div>
                <div class="obj-reason">${{escHtml(obj.reason || '')}}</div>`;
            const isObjNew = !rendered.has(objId);
            const objDiv = document.createElement('div');
            objDiv.className = 'bubble bubble-objection ' + (isObjNew ? 'bubble-new' : 'bubble-static');
            objDiv.dataset.bubbleId = objId;
            objDiv.innerHTML = objHtml;
            container.appendChild(objDiv);
            if (isObjNew) container.scrollTop = container.scrollHeight;
        }});

        // Supports
        (op.supports || []).forEach((sup, idx) => {{
            const supId = 'sup-' + agent + '-r' + rn + '-' + idx;
            if (!rendered.has(supId)) {{
                newlyRendered.add(supId);
                if (sup.target_agent) flashCol(sup.target_agent, 'green');
            }}
            const supHtml = `
                <div class="sup-header">🤝 Support → ${{escHtml((sup.target_agent || '').toUpperCase())}}</div>
                <div style="font-size:0.82rem;margin-top:4px">${{escHtml(sup.reason || '')}}</div>`;
            const isSupNew = !rendered.has(supId);
            const supDiv = document.createElement('div');
            supDiv.className = 'bubble bubble-support ' + (isSupNew ? 'bubble-new' : 'bubble-static');
            supDiv.dataset.bubbleId = supId;
            supDiv.innerHTML = supHtml;
            container.appendChild(supDiv);
            if (isSupNew) container.scrollTop = container.scrollHeight;
        }});
    }}

    function renderConflictsBanner(ev) {{
        const conflicts = ev.conflicts || [];
        const rn = ev.round;
        if (conflicts.length === 0) {{
            const bannerId = 'banner-noconflict-r' + rn;
            if (!rendered.has(bannerId)) {{
                addSystem(`<div class="system-banner banner-neutral" data-bid="${{bannerId}}">✅ Round ${{rn}} — No material conflicts detected</div>`);
                newlyRendered.add(bannerId);
            }}
            return;
        }}
        conflicts.forEach((c, idx) => {{
            const sev = c.disagreement_severity || 'low';
            const bannerId = 'banner-conflict-r' + rn + '-' + idx;
            if (!rendered.has(bannerId)) {{
                const sevClass = 'banner-conflict-' + sev;
                const sevBadge = `<span class="sev-badge ${{sev}}">${{sev.toUpperCase()}}</span>`;
                const icon = sev === 'high' ? '⚡' : sev === 'medium' ? '⚠️' : '·';
                addSystem(`<div class="system-banner ${{sevClass}}" data-bid="${{bannerId}}">${{icon}} Round ${{rn}} conflict: <strong>${{escHtml(c.parameter)}}</strong>&nbsp;${{sevBadge}}&nbsp;<span style="opacity:0.7">${{escHtml(c.agent_a)}} ${{c.proposed_value_a}} vs ${{escHtml(c.agent_b)}} ${{c.proposed_value_b}}</span></div>`);
                newlyRendered.add(bannerId);
            }}
        }});
    }}

    function renderRound3Banner(ev) {{
        const bannerId = 'banner-r3';
        if (!rendered.has(bannerId)) {{
            const agents = (ev.agents || []).join(', ');
            addSystem(`<div class="system-banner banner-r3" data-bid="${{bannerId}}">⚠️ <strong>Final Attempt — Round 3</strong> &nbsp; Unresolved HIGH conflicts. Agents involved: ${{escHtml(agents)}}</div>`);
            newlyRendered.add(bannerId);
        }}
    }}

    function renderRoundResolved(ev) {{
        const bannerId = 'banner-resolved-r' + ev.round;
        if (!rendered.has(bannerId)) {{
            addSystem(`<div class="system-banner banner-neutral" data-bid="${{bannerId}}">⚖️ <strong>Round ${{ev.round}} resolved</strong> — ${{escHtml(ev.summary || '')}}</div>`);
            newlyRendered.add(bannerId);
        }}
    }}

    function renderComplete(ev) {{
        const bannerId = 'banner-complete';
        if (!rendered.has(bannerId)) {{
            addSystem(`<div class="system-banner banner-complete" data-bid="${{bannerId}}">✅ <strong>Session Complete</strong> — Debate concluded. Review results in the tabs above.</div>`);
            newlyRendered.add(bannerId);
        }}
    }}

    // Process all events in order
    events.forEach(ev => {{
        switch(ev.event) {{
            case 'agent_thinking':
                addThinking(ev.agent);
                dot(ev.agent) && dot(ev.agent).classList.add('thinking');
                dot(ev.agent) && dot(ev.agent).classList.remove('spoke');
                break;
            case 'agent_spoke':
                removeThinking(ev.agent);
                dot(ev.agent) && dot(ev.agent).classList.remove('thinking');
                dot(ev.agent) && dot(ev.agent).classList.add('spoke');
                renderPositionBubble(ev);
                break;
            case 'conflicts_detected':
                renderConflictsBanner(ev);
                break;
            case 'round3_triggered':
                renderRound3Banner(ev);
                break;
            case 'round_resolved':
                renderRoundResolved(ev);
                break;
            case 'session_complete':
                renderComplete(ev);
                // Dim all presence dots
                ['finance','climate','community'].forEach(a => {{
                    const d = dot(a);
                    if (d) {{ d.classList.remove('thinking','spoke'); }}
                }});
                break;
        }}
    }});

    // Persist the updated rendered set
    for (const id of newlyRendered) rendered.add(id);
    saveRendered(rendered);
}})();
</script>
</body>
</html>"""


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
            const attemptStr = (beat.session_attempt > 1) ? `Attempt ${{beat.session_attempt}} · ` : '';
            document.getElementById('beat-label').innerText = `${{attemptStr}}Round ${{beat.negotiation_round || beat.round_number}} · ${{beat.beat_type.replace('_', ' ').toUpperCase()}} (${{index + 1}}/${{beats.length}})`;

            // Reset UI state
            document.getElementById('lines-container').innerHTML = '';
            const sb = document.getElementById('status-banner');
            if (sb) {{
                sb.innerHTML = '';
                sb.className = 'absolute top-6 left-0 right-0 z-30 px-8 flex justify-center pointer-events-none min-h-[100px]';
            }}
            const stage = document.getElementById('stage-panels');
            if (stage) stage.classList.remove('hidden');
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
                const startTitle = (beat.session_attempt > 1) ? `⚖️ Session Attempt ${{beat.session_attempt}} (Round ${{beat.negotiation_round}}) Commencing` : `⚖️ Round ${{beat.negotiation_round || beat.round_number}} Commencing`;
                document.getElementById('status-banner').innerHTML = `
                    <div class="bg-indigo-950 bg-opacity-95 text-white border-2 border-indigo-400 p-6 rounded-3xl shadow-2xl text-center animate-bounce max-w-xl mx-auto">
                        <h2 class="text-2xl font-black tracking-wider uppercase">${{startTitle}}</h2>
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
                const isFinal = beat.beat_type === 'final_verdict';
                const c = beat.content;
                
                let title = (beat.session_attempt > 1) ? `⚖️ Session Attempt ${{beat.session_attempt}} — Negotiation Resolved` : `⚖️ Resolution Achieved`;
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
                                <ul class="list-disc pl-6 space-y-2 font-bold">
                                    ${{c.unresolved_conflicts.map(p => {{
                                        const attempts = (c.unresolved_attempts && c.unresolved_attempts[p]) ? c.unresolved_attempts[p] : 1;
                                        if (attempts > 1) {{
                                            return `<li>${{p}} <span class="ml-2 px-2 py-0.5 bg-red-800 text-white rounded text-xs font-extrabold">This parameter has required human review across ${{attempts}} attempts</span></li>`;
                                        }} else {{
                                            return `<li>${{p}}</li>`;
                                        }}
                                    }}).join('')}}
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

                    if (c.consecutive_unlocked_warnings && c.consecutive_unlocked_warnings.length > 0) {{
                        extraHtml += `
                            <div class="mt-4 bg-amber-950 bg-opacity-90 border border-amber-500 p-5 rounded-2xl text-left text-amber-200 text-sm shadow-inner">
                                <div class="font-black text-amber-400 uppercase mb-2 flex items-center gap-1.5 text-[15px]">
                                    <span class="material-symbols-outlined text-[20px]">lightbulb</span>
                                    Suggested Judge Intervention:
                                </div>
                                <div class="space-y-2 font-bold text-xs leading-relaxed">
                                    ${{c.consecutive_unlocked_warnings.map(w => `<p>${{w}}</p>`).join('')}}
                                </div>
                            </div>
                        `;
                    }}

                    const stage = document.getElementById('stage-panels');
                    if (stage) stage.classList.add('hidden');
                    
                    const sb = document.getElementById('status-banner');
                    if (sb) {{
                        sb.className = 'absolute inset-0 z-30 flex items-center justify-center p-8 pointer-events-auto';
                        sb.innerHTML = `
                            <div class="bg-slate-900 bg-opacity-95 border-2 border-slate-500 p-10 rounded-3xl shadow-2xl max-w-3xl w-full text-center animate-fade-in">
                                <h2 class="text-3xl font-black tracking-wider text-white uppercase">${{title}}</h2>
                                <p class="text-slate-300 text-lg mt-4 font-semibold">${{desc}}</p>
                                ${{extraHtml}}
                            </div>
                        `;
                    }}
                }} else {{
                    ['finance', 'climate', 'community'].forEach(agent => {{
                        const p = document.getElementById(`panel-${{agent}}`);
                        p.classList.remove('opacity-40', 'scale-98');
                        p.classList.add('opacity-90');
                    }});

                    const sb = document.getElementById('status-banner');
                    if (sb) {{
                        sb.className = 'absolute top-6 left-0 right-0 z-30 px-8 flex justify-center pointer-events-none min-h-[100px]';
                        sb.innerHTML = `
                            <div class="bg-slate-900 bg-opacity-95 border-2 border-slate-500 p-8 rounded-3xl shadow-2xl max-w-2xl mx-auto text-center animate-fade-in">
                                <h2 class="text-2xl font-black tracking-wider text-white uppercase">${{title}}</h2>
                                <p class="text-slate-300 text-base mt-3 font-semibold">${{desc}}</p>
                                ${{extraHtml}}
                            </div>
                        `;
                    }}

                    subTimeoutIds.push(setTimeout(() => {{
                        const banner = document.getElementById('status-banner');
                        if (banner) banner.innerHTML = '';
                    }}, duration * 0.85));
                }}
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
