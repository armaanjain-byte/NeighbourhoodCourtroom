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
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;700;900&display=swap" rel="stylesheet"/>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: 'Outfit', sans-serif;
    background: transparent;
    min-height: 100vh;
    color: #121212;
}}

/* ── Layout ── */
.courtroom-wrap {{
    display: flex;
    flex-direction: column;
    gap: 0;
    padding: 16px;
    min-height: 880px;
}}
.agent-columns {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 16px;
}}
.system-strip {{
    padding: 8px 0;
}}

/* ── Agent column ── */
.agent-col {{
    display: flex;
    flex-direction: column;
    border-radius: 0;
    overflow: hidden;
    border: 4px solid #121212;
    background: #ffffff;
    box-shadow: 6px 6px 0px 0px #121212;
    min-height: 200px;
}}
.agent-header {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 16px 12px;
    border-bottom: 3px solid #121212;
    position: relative;
}}
.agent-icon {{ font-size: 1.4rem; }}
.agent-label {{
    font-family: 'Outfit', sans-serif;
    font-size: 0.75rem;
    font-weight: 900;
    letter-spacing: 0.14em;
    text-transform: uppercase;
}}
.presence-dot {{
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #e0e0e0;
    border: 2px solid #121212;
    margin-left: auto;
    transition: background 0.3s;
    flex-shrink: 0;
}}
.presence-dot.thinking {{ background: #F6C445; animation: presence-pulse 1.5s infinite; }}
.presence-dot.spoke {{ background: #48BB78; }}

@keyframes presence-pulse {{
    0%,100% {{ box-shadow: 0 0 0 0 rgba(246,196,69,0.7); }}
    50% {{ box-shadow: 0 0 0 4px rgba(246,196,69,0.0); }}
}}

/* Column-specific header tints — identity colors */
.col-finance  {{ border-top: 6px solid #744210; }}
.col-climate  {{ border-top: 6px solid #276749; }}
.col-community{{ border-top: 6px solid #553c9a; }}
.col-finance   .agent-header {{ background: #fefcbf; }}
.col-climate   .agent-header {{ background: #c6f6d5; }}
.col-community .agent-header {{ background: #e9d8fd; }}
.col-finance   .agent-label  {{ color: #744210; }}
.col-climate   .agent-label  {{ color: #276749; }}
.col-community .agent-label  {{ color: #553c9a; }}

.agent-feed {{
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px;
    overflow-y: auto;
    background: #ffffff;
}}

/* ── Column flash overlay ── */
.col-flash {{
    position: absolute;
    inset: 0;
    border-radius: 0;
    pointer-events: none;
    opacity: 0;
    z-index: 10;
}}
.col-flash.flash-red {{
    background: rgba(116,42,42,0.18);
    animation: col-flash-anim 0.7s ease-out forwards;
}}
.col-flash.flash-green {{
    background: rgba(39,103,73,0.18);
    animation: col-flash-anim 0.7s ease-out forwards;
}}
@keyframes col-flash-anim {{
    0%   {{ opacity: 1; }}
    100% {{ opacity: 0; }}
}}

/* ── Chat bubbles — Bauhaus geometric ── */
.bubble {{
    border-radius: 0;
    padding: 12px 14px;
    font-size: 0.84rem;
    line-height: 1.55;
    border: 2px solid #121212;
    box-shadow: 3px 3px 0px 0px #121212;
    position: relative;
    word-break: break-word;
    background: #ffffff;
    color: #121212;
    transition: transform 0.1s ease-out;
}}
.bubble:hover {{
    transform: translate(-1px, -1px);
}}
.bubble.bubble-new {{
    animation: bubble-popin 0.28s cubic-bezier(0.34,1.56,0.64,1) forwards;
}}
.bubble.bubble-static {{
    animation: none;
    opacity: 1;
    transform: none;
}}
@keyframes bubble-popin {{
    from {{ opacity: 0; transform: scale(0.9) translateY(6px); box-shadow: none; }}
    to   {{ opacity: 1; transform: scale(1)  translateY(0);   box-shadow: 3px 3px 0px 0px #121212; }}
}}

/* Position bubble: main statement */
.bubble-position {{
    background: #ffffff;
    border-left: 5px solid #276749;
}}
.bubble .position-text {{
    font-family: 'Outfit', sans-serif;
    font-weight: 700;
    font-size: 0.9rem;
    margin-bottom: 8px;
    color: #121212;
}}
.bubble .round-tag {{
    display: inline-block;
    font-family: 'Outfit', sans-serif;
    font-size: 0.62rem;
    font-weight: 900;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 0;
    border: 1px solid #121212;
    background: #121212;
    color: #F0F0F0;
    margin-bottom: 6px;
}}

/* Fallback bubble */
.bubble-fallback {{
    background: repeating-linear-gradient(45deg, #F0F0F0, #F0F0F0 8px, #ffffff 8px, #ffffff 16px);
    border: 2px dashed #121212;
    padding: 0 !important;
    overflow: hidden;
    box-shadow: 3px 3px 0px 0px #121212;
}}
.bubble-fallback .fallback-header {{
    background: #E0E0E0;
    color: #121212;
    font-family: 'Outfit', sans-serif;
    font-size: 0.68rem;
    font-weight: 900;
    letter-spacing: 0.08em;
    padding: 8px 14px;
    border-bottom: 2px dashed #121212;
    display: flex;
    align-items: center;
    gap: 6px;
    text-transform: uppercase;
}}
.bubble-fallback .fallback-body {{
    padding: 12px 14px;
}}

/* Expandable detail */
details.bubble-detail {{
    margin-top: 6px;
}}
details.bubble-detail summary {{
    font-family: 'Outfit', sans-serif;
    font-size: 0.68rem;
    font-weight: 700;
    color: #121212;
    opacity: 0.85;
    cursor: pointer;
    user-select: none;
    list-style: none;
    padding: 3px 0;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}}
details.bubble-detail summary::-webkit-details-marker {{ display: none; }}
details.bubble-detail summary::before {{ content: '▶ '; font-size: 0.6rem; }}
details.bubble-detail[open] summary::before {{ content: '▼ '; }}
.detail-body {{
    margin-top: 6px;
    font-size: 0.78rem;
    color: #121212;
    opacity: 0.85;
    line-height: 1.5;
}}
.evidence-list {{
    margin-top: 5px;
    padding-left: 14px;
    font-size: 0.75rem;
    color: #121212;
    opacity: 0.85;
}}
.evidence-list li {{ margin-bottom: 2px; }}

/* Objection bubble — red accent, Finance amber role maps to objection warning */
.bubble-objection {{
    border: 2px solid #121212;
    border-left: 5px solid #742a2a;
    background: #fff0f0;
    box-shadow: 3px 3px 0px 0px #121212;
}}
.bubble-objection .obj-header {{
    font-family: 'Outfit', sans-serif;
    font-size: 0.68rem;
    font-weight: 900;
    color: #742a2a;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 5px;
}}
.bubble-objection .obj-claim {{
    font-size: 0.74rem;
    color: #742a2a;
    opacity: 0.85;
    font-style: italic;
    margin-bottom: 5px;
    padding: 4px 8px;
    background: rgba(116,42,42,0.06);
    border-radius: 0;
    border-left: 3px solid #742a2a;
}}
.bubble-objection .obj-reason {{ font-size: 0.82rem; font-weight: 500; color: #121212; }}

/* Support bubble — Climate green */
.bubble-support {{
    border: 2px solid #121212;
    border-left: 5px solid #276749;
    background: #f0fff8;
    box-shadow: 3px 3px 0px 0px #121212;
}}
.bubble-support .sup-header {{
    font-family: 'Outfit', sans-serif;
    font-size: 0.68rem;
    font-weight: 900;
    color: #276749;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 5px;
}}

/* Concession bubble — Finance amber (gold/compromise tone) */
.bubble-concession {{
    border: 2px solid #121212;
    border-left: 5px solid #744210;
    background: #fefcbf;
    box-shadow: 3px 3px 0px 0px #121212;
}}
.bubble-concession .con-header {{
    font-family: 'Outfit', sans-serif;
    font-size: 0.68rem;
    font-weight: 900;
    color: #744210;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 5px;
}}

/* ── Thinking indicator ── */
.thinking-indicator {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-family: 'Outfit', sans-serif;
    font-size: 0.72rem;
    font-weight: 700;
    color: #121212;
    opacity: 0.85;
    padding: 6px 10px;
    font-style: italic;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}}
.thinking-dots span {{
    display: inline-block;
    width: 5px; height: 5px;
    border-radius: 0;
    background: #744210;
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
    border-radius: 0;
    font-family: 'Outfit', sans-serif;
    font-size: 0.72rem;
    font-weight: 900;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin: 8px 0;
    border: 2px solid #121212;
    box-shadow: 3px 3px 0px 0px #121212;
    animation: banner-fadein 0.4s ease-out forwards;
}}
@keyframes banner-fadein {{
    from {{ opacity: 0; transform: scaleX(0.97); }}
    to   {{ opacity: 1; transform: scaleX(1); }}
}}
/* Finance amber = conflict-high (primary-red role) */
.banner-conflict-high   {{ background: #744210; border-color: #121212; color: #fefcbf; }}
/* Finance amber lighter = conflict-medium */
.banner-conflict-medium {{ background: #fefcbf; border-color: #121212; color: #744210; }}
/* Climate green = conflict-low */
.banner-conflict-low    {{ background: #276749; border-color: #121212; color: #c6f6d5; }}
/* Neutral — off-white, black border */
.banner-neutral         {{ background: #F0F0F0; border-color: #121212; color: #121212; }}
/* Round 3 — Community violet (primary-yellow role) */
.banner-r3              {{ background: #553c9a; border-color: #121212; color: #e9d8fd; }}
/* Complete — Climate green */
.banner-complete        {{ background: #276749; border-color: #121212; color: #c6f6d5; }}

.sev-badge {{
    display: inline-block;
    font-family: 'Outfit', sans-serif;
    font-size: 0.62rem;
    font-weight: 900;
    padding: 2px 8px;
    border-radius: 0;
    border: 1px solid currentColor;
    text-transform: uppercase;
    letter-spacing: 0.1em;
}}
.sev-badge.high   {{ background: #742a2a; color: #feb2b2; border-color: #742a2a; }}
.sev-badge.medium {{ background: #744210; color: #fefcbf; border-color: #744210; }}
.sev-badge.low    {{ background: #276749; color: #c6f6d5; border-color: #276749; }}

.thinking-strip {{
    font-family: 'Outfit', sans-serif;
    font-size: 0.65rem;
    font-style: italic;
    color: #121212;
    opacity: 0.85;
    padding: 4px 10px;
    display: none;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
.awaiting-placeholder {{
    font-family: 'Outfit', sans-serif;
    font-size: 0.85rem;
    color: #718096;
    font-style: italic;
    text-align: center;
    padding: 24px 12px;
    opacity: 0.8;
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
      <div class="agent-feed" id="feed-finance">
        <div class="awaiting-placeholder" id="await-finance">Awaiting statement...</div>
      </div>
    </div>
    <div class="agent-col col-climate" id="col-climate">
      <div class="agent-header">
        <span class="agent-icon">🌿</span>
        <span class="agent-label">Climate</span>
        <div class="presence-dot" id="dot-climate"></div>
        <div class="col-flash" id="flash-climate"></div>
      </div>
      <div class="agent-feed" id="feed-climate">
        <div class="awaiting-placeholder" id="await-climate">Awaiting statement...</div>
      </div>
    </div>
    <div class="agent-col col-community" id="col-community">
      <div class="agent-header">
        <span class="agent-icon">🏘️</span>
        <span class="agent-label">Community</span>
        <div class="presence-dot" id="dot-community"></div>
        <div class="col-flash" id="flash-community"></div>
      </div>
      <div class="agent-feed" id="feed-community">
        <div class="awaiting-placeholder" id="await-community">Awaiting statement...</div>
      </div>
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
        const awaitEl = document.getElementById('await-' + agent);
        if (awaitEl) awaitEl.remove();
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
        const awaitEl = document.getElementById('await-' + agent);
        if (awaitEl) awaitEl.remove();
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

        let positionHtml;
        let bubbleClass = isFallback ? 'bubble-fallback' : (hasConcession ? 'bubble-concession' : 'bubble-position');

        if (isFallback) {{
            positionHtml = `
                <div class="fallback-header">⚙️ VERIFIED BASELINE CALCULATION</div>
                <div class="fallback-body">
                    <span class="round-tag">Round ${{rn}} (AI Reasoning Unavailable)</span>
                    <div class="position-text">${{escHtml(op.position || '')}}</div>
                    <details class="bubble-detail">
                        <summary>Deterministic calculations</summary>
                        <div class="detail-body">
                            ${{reasoning ? `<p>${{reasoning}}</p>` : ''}}
                        </div>
                    </details>
                </div>`;
        }} else if (hasConcession) {{
            positionHtml = `
                <div class="con-header">🤝 Concession · Round ${{rn}}</div>
                <div class="position-text">${{escHtml(op.position || '')}}</div>
                <details class="bubble-detail">
                    <summary>Concession rationale &amp; detail</summary>
                    <div class="detail-body">
                        <em style="color:rgba(251,211,141,0.8)">${{escHtml(op.concession_rationale)}}</em>
                        ${{reasoning ? `<p style="margin-top:6px">${{reasoning}}</p>` : ''}}
                        ${{evidence ? `<ul class="evidence-list">${{evidence}}</ul>` : ''}}
                    </div>
                </details>`;
        }} else {{
            positionHtml = `
                <span class="round-tag">Round ${{rn}}</span>
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
        div.className = 'bubble ' + bubbleClass + ' ' + (isNew ? 'bubble-new' : 'bubble-static');
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
                addSystem(`<div class="system-banner ${{sevClass}}" data-bid="${{bannerId}}">${{icon}} Round ${{rn}} conflict: <strong>${{escHtml(c.parameter)}}</strong>&nbsp;${{sevBadge}}&nbsp;<span style="opacity:0.9">${{escHtml(c.agent_a)}} ${{c.proposed_value_a}} vs ${{escHtml(c.agent_b)}} ${{c.proposed_value_b}}</span></div>`);
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
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;700;900&display=swap" rel="stylesheet"/>
    <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
    <script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
    <script>
        tailwind.config = {{
          darkMode: "class",
          theme: {{
            extend: {{
              colors: {{
                "primary": "#121212",
                "on-primary": "#F0F0F0",
                "error": "#742a2a",
                "outline-variant": "#121212",
                "surface-container-lowest": "#ffffff",
                "on-surface-variant": "#121212",
                "background": "#F0F0F0"
              }},
              fontFamily: {{
                "body-md": ["Outfit", "sans-serif"],
                "label-md": ["Outfit", "sans-serif"],
                "headline-md": ["Outfit", "sans-serif"],
                "body-lg": ["Outfit", "sans-serif"]
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
            padding: 2rem;
            font-family: 'Outfit', sans-serif;
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
            background: #121212;
            color: #F0F0F0;
            border: 2px solid #121212;
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
    </style>
</head>
<body>
    <!-- ANIMATION SCENE CONTAINER -->
    <div id="animation-scene" class="relative flex flex-col justify-between w-full h-[820px] overflow-hidden" style="background-color: #F0F0F0; border: 4px solid #121212; box-shadow: 8px 8px 0px 0px #121212;">
        
        <!-- Connecting lines overlay -->
        <div id="lines-container" class="absolute inset-0 pointer-events-none z-20"></div>

        <!-- Top Banner / Overlay Area -->
        <div id="status-banner" class="absolute top-6 left-0 right-0 z-30 px-8 flex justify-center pointer-events-none min-h-[100px]"></div>

        <!-- Three Silhouette Panels Stage -->
        <div id="stage-panels" class="flex-1 grid grid-cols-3 gap-8 px-8 pt-32 pb-24 z-10 items-stretch">
            
            <!-- FINANCE PANEL -->
            <div id="panel-finance" class="relative flex flex-col p-6 transition-all duration-300 opacity-40 scale-98 overflow-y-auto hide-scrollbar" style="background-color: #744210; color: #fefcbf; border: 4px solid #121212; box-shadow: 6px 6px 0px 0px #121212; border-radius: 0;">
                <div class="flex items-center justify-between border-b-2 border-[#fefcbf] pb-4 mb-6">
                    <div class="flex items-center gap-3">
                        <span class="material-symbols-outlined text-4xl text-[#fefcbf]">bar_chart</span>
                        <h3 class="text-2xl font-black tracking-wider uppercase text-[#fefcbf]">Finance</h3>
                    </div>
                    <span class="text-xs font-bold px-3 py-1 bg-[#fefcbf] text-[#744210] border-2 border-[#121212]">AGENT</span>
                </div>
                <div id="content-finance" class="flex-1 flex flex-col space-y-4">
                    <div class="h-full flex items-center justify-center text-sm font-bold italic text-[#fefcbf]">Awaiting statement...</div>
                </div>
            </div>

            <!-- CLIMATE PANEL -->
            <div id="panel-climate" class="relative flex flex-col p-6 transition-all duration-300 opacity-40 scale-98 overflow-y-auto hide-scrollbar" style="background-color: #276749; color: #c6f6d5; border: 4px solid #121212; box-shadow: 6px 6px 0px 0px #121212; border-radius: 0;">
                <div class="flex items-center justify-between border-b-2 border-[#c6f6d5] pb-4 mb-6">
                    <div class="flex items-center gap-3">
                        <span class="material-symbols-outlined text-4xl text-[#c6f6d5]">eco</span>
                        <h3 class="text-2xl font-black tracking-wider uppercase text-[#c6f6d5]">Climate</h3>
                    </div>
                    <span class="text-xs font-bold px-3 py-1 bg-[#c6f6d5] text-[#276749] border-2 border-[#121212]">AGENT</span>
                </div>
                <div id="content-climate" class="flex-1 flex flex-col space-y-4">
                    <div class="h-full flex items-center justify-center text-sm font-bold italic text-[#c6f6d5]">Awaiting statement...</div>
                </div>
            </div>

            <!-- COMMUNITY PANEL -->
            <div id="panel-community" class="relative flex flex-col p-6 transition-all duration-300 opacity-40 scale-98 overflow-y-auto hide-scrollbar" style="background-color: #553c9a; color: #e9d8fd; border: 4px solid #121212; box-shadow: 6px 6px 0px 0px #121212; border-radius: 0;">
                <div class="flex items-center justify-between border-b-2 border-[#e9d8fd] pb-4 mb-6">
                    <div class="flex items-center gap-3">
                        <span class="material-symbols-outlined text-4xl text-[#e9d8fd]">other_houses</span>
                        <h3 class="text-2xl font-black tracking-wider uppercase text-[#e9d8fd]">Community</h3>
                    </div>
                    <span class="text-xs font-bold px-3 py-1 bg-[#e9d8fd] text-[#553c9a] border-2 border-[#121212]">AGENT</span>
                </div>
                <div id="content-community" class="flex-1 flex flex-col space-y-4">
                    <div class="h-full flex items-center justify-center text-sm font-bold italic text-[#e9d8fd]">Awaiting statement...</div>
                </div>
            </div>

        </div>

        <!-- Bottom Judge's Bench Console -->
        <div id="judges-bench" class="relative z-30 flex items-center justify-between px-8 py-4" style="background: #ffffff; border-top: 4px solid #121212; box-shadow: 0 -3px 0 0 #121212;">
            <!-- Play/Pause and Speed Controls -->
            <div class="flex items-center gap-3">
                <button id="btn-play-pause" onclick="togglePlay()" class="flex items-center gap-2 px-5 py-2 font-black text-xs uppercase tracking-widest transition-all" style="background: #553c9a; color: #e9d8fd; border: 3px solid #121212; border-radius: 0; box-shadow: 4px 4px 0px 0px #121212; font-family: Outfit, sans-serif; letter-spacing: 0.1em;" onmouseover="this.style.transform='translate(-1px,-1px)'; this.style.boxShadow='6px 6px 0px 0px #121212'" onmouseout="this.style.transform=''; this.style.boxShadow='4px 4px 0px 0px #121212'" onmousedown="this.style.transform='translate(3px,3px)'; this.style.boxShadow='none'" onmouseup="this.style.transform='translate(-1px,-1px)'; this.style.boxShadow='6px 6px 0px 0px #121212'">
                    ⏸ PAUSE
                </button>
                <div class="flex items-center" style="border: 3px solid #121212; box-shadow: 3px 3px 0px 0px #121212;">
                    <button id="btn-speed-1" onclick="setSpeed(1)" class="speed-btn px-4 py-1.5 text-xs font-black uppercase transition-all" style="background: #744210; color: #fefcbf; border-right: 2px solid #121212; font-family: Outfit, sans-serif;">1×</button>
                    <button id="btn-speed-2" onclick="setSpeed(2)" class="speed-btn px-4 py-1.5 text-xs font-black uppercase transition-all" style="background: #F0F0F0; color: #121212; border-right: 2px solid #121212; font-family: Outfit, sans-serif;">2×</button>
                    <button id="btn-speed-4" onclick="setSpeed(4)" class="speed-btn px-4 py-1.5 text-xs font-black uppercase transition-all" style="background: #F0F0F0; color: #121212; font-family: Outfit, sans-serif;">4×</button>
                </div>
            </div>

            <!-- Progress & Status Indicator -->
            <div class="flex-1 max-w-md mx-6 flex flex-col items-center">
                <div id="beat-label" class="text-xs font-black text-gray-900 uppercase tracking-widest mb-2" style="font-family: Outfit, sans-serif;">Initializing Courtroom Scene...</div>
                <div class="w-full overflow-hidden" style="height: 8px; background: #E0E0E0; border: 2px solid #121212; border-radius: 0;">
                    <div id="beat-progress-fill" class="h-full w-0 transition-all duration-300" style="background: #276749;"></div>
                </div>
            </div>

            <!-- Toggle Full Transcript Fallback -->
            <button onclick="toggleTranscriptView()" class="flex items-center gap-2 px-5 py-2 font-black text-xs uppercase tracking-widest transition-all" style="background: #ffffff; color: #121212; border: 3px solid #121212; border-radius: 0; box-shadow: 4px 4px 0px 0px #121212; font-family: Outfit, sans-serif;" onmouseover="this.style.transform='translate(-1px,-1px)'; this.style.boxShadow='6px 6px 0px 0px #121212'" onmouseout="this.style.transform=''; this.style.boxShadow='4px 4px 0px 0px #121212'">
                📜 Full Transcript
            </button>
        </div>

    </div>

    <!-- FULL TRANSCRIPT FALLBACK CONTAINER -->
    <div id="full-transcript-view" class="hidden bg-background font-body-md text-[#121212] w-full min-h-[820px] overflow-hidden flex flex-col" style="border: 4px solid #121212; box-shadow: 8px 8px 0px 0px #121212; border-radius: 0;">
        <!-- Top Action Bar -->
        <div class="px-8 py-4 flex items-center justify-between" style="background: #121212; color: #F0F0F0; border-bottom: 4px solid #121212;">
            <div class="flex items-center gap-3">
                <span class="material-symbols-outlined text-3xl" style="color: #fefcbf;">history_edu</span>
                <h2 class="text-xl font-black tracking-widest uppercase" style="font-family: Outfit, sans-serif; color: #F0F0F0;">Debate Transcript &amp; Conflict Map</h2>
            </div>
            <button onclick="toggleTranscriptView()" class="flex items-center gap-2 px-5 py-2 font-black text-xs uppercase tracking-widest" style="background: #553c9a; color: #e9d8fd; border: 3px solid #e9d8fd; border-radius: 0; box-shadow: 3px 3px 0px 0px rgba(233,216,253,0.5); font-family: Outfit, sans-serif;">
                🎭 Back to Scene
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
            document.querySelectorAll('.speed-btn').forEach(btn => {{
                btn.style.background = '#F0F0F0';
                btn.style.color = '#121212';
            }});
            const activeBtn = document.getElementById(`btn-speed-${{mult}}`);
            if (activeBtn) {{ activeBtn.style.background = '#744210'; activeBtn.style.color = '#fefcbf'; }}
            if (isPlaying) {{
                playBeat(currentBeatIndex);
            }}
        }}

        function togglePlay() {{
            isPlaying = !isPlaying;
            const btn = document.getElementById('btn-play-pause');
            if (isPlaying) {{
                btn.innerHTML = '⏸ PAUSE';
                btn.style.background = '#553c9a';
                btn.style.color = '#e9d8fd';
                playBeat(currentBeatIndex);
            }} else {{
                btn.innerHTML = '▶ PLAY';
                btn.style.background = '#276749';
                btn.style.color = '#c6f6d5';
                clearAllTimeouts();
            }}
        }}

        function toggleTranscriptView() {{
            clearAllTimeouts();
            isPlaying = false;
            const endBtn = document.getElementById('btn-play-pause');
            if (endBtn) {{ endBtn.innerHTML = '▶ PLAY'; endBtn.style.background = '#276749'; endBtn.style.color = '#c6f6d5'; }}
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
                label.className = 'absolute z-30 transform -translate-x-1/2 -translate-y-1/2';
                label.style.background = '#121212';
                label.style.color = '#F0F0F0';
                label.style.border = `2px solid ${{colorHex}}`;
                label.style.padding = '2px 8px';
                label.style.borderRadius = '0';
                label.style.fontSize = '10px';
                label.style.fontFamily = 'Outfit, sans-serif';
                label.style.fontWeight = '900';
                label.style.letterSpacing = '0.08em';
                label.style.textTransform = 'uppercase';
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
                    let textColor = '#fefcbf';
                    if (agent === 'climate') textColor = '#c6f6d5';
                    if (agent === 'community') textColor = '#e9d8fd';
                    document.getElementById(`content-${{agent}}`).innerHTML = `<div class="h-full flex items-center justify-center text-sm font-bold italic" style="color: ${{textColor}}">Awaiting statement...</div>`;
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
                    <div class="text-center animate-bounce max-w-xl mx-auto" style="background:#121212; color:#F0F0F0; border: 4px solid #F0F0F0; padding: 1.5rem 2rem; box-shadow: 8px 8px 0px 0px rgba(240,240,240,0.3); border-radius: 0; font-family: Outfit, sans-serif;">
                        <h2 style="font-size:1.5rem; font-weight:900; letter-spacing:0.08em; text-transform:uppercase; color:#fefcbf;">${{startTitle}}</h2>
                        <p style="font-size:0.82rem; margin-top:0.5rem; font-weight:700; color:#c6f6d5; letter-spacing:0.04em;">${{beat.content.message || ''}}</p>
                    </div>
                `;
            }} 
            else if (beat.beat_type === 'agent_statement') {{
                activatePanel(beat.agent);
                const c = beat.content;
                const container = document.getElementById(`content-${{beat.agent}}`);
                
                container.innerHTML = `
                    <div id="stmt-tension" class="bg-white p-4 border-2 border-[#121212] shadow-[3px_3px_0px_0px_#121212] text-xs italic text-[#121212] mb-4">
                        <div class="font-bold not-italic mb-1.5 flex items-center gap-1.5 text-[13px] uppercase tracking-wide">
                            <span class="material-symbols-outlined text-[18px]">balance</span>
                            Internal Deliberation & Tension:
                        </div>
                        "${{c.tension || ''}}"
                    </div>
                    <div id="stmt-position" class="hidden font-black text-xl mb-4 tracking-wide leading-snug text-current"></div>
                    <div id="stmt-reasoning" class="hidden text-sm text-[#121212] mb-4 leading-relaxed bg-white p-4 border-2 border-[#121212] shadow-[3px_3px_0px_0px_#121212] font-medium"></div>
                    <div id="stmt-evidence" class="hidden bg-white p-4 border-2 border-[#121212] shadow-[3px_3px_0px_0px_#121212]">
                        <div class="font-bold text-xs text-[#121212] uppercase tracking-wider mb-2.5 flex items-center gap-1.5">
                            <span class="material-symbols-outlined text-[18px]">plagiarism</span>
                            Supporting Evidence:
                        </div>
                        <ul id="evidence-list" class="list-disc pl-5 text-sm text-[#121212] space-y-1.5 font-medium"></ul>
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
                const colorHex = isObj ? '#742a2a' : '#276749';
                const c = beat.content;
                
                const container = document.getElementById(`content-${{beat.agent}}`);
                container.innerHTML = `
                    <div class="bg-white border-2 p-5 shadow-[4px_4px_0px_0px_#121212] mb-4 text-[#121212] animate-fade-in" style="border-color: #121212">
                        <div class="flex items-center gap-2 font-black text-sm mb-3 uppercase tracking-wider" style="color: ${{colorHex}}">
                            <span class="material-symbols-outlined text-[22px]">${{isObj ? 'gavel' : 'handshake'}}</span>
                            ${{isObj ? 'Objection to' : 'Support for'}} ${{beat.target_agent.toUpperCase()}}
                        </div>
                        <div class="text-xs bg-[#F0F0F0] p-3 mb-4 italic border-l-4 border-[#121212]">
                            Claim: "${{c.engages_with || ''}}"
                        </div>
                        <div class="text-sm leading-relaxed font-semibold text-[#121212]">${{c.reason || ''}}</div>
                    </div>
                `;

                drawConnectionLine(beat.target_agent, beat.agent, colorHex, c.engages_with);
            }}
            else if (beat.beat_type === 'conflict_flare') {{
                activatePanel(beat.agent);
                activatePanel(beat.target_agent);
                
                const c = beat.content;
                let colorHex = '#276749'; 
                if (beat.severity === 'medium') colorHex = '#744210'; 
                if (beat.severity === 'high') colorHex = '#742a2a'; 

                drawConnectionLine(beat.agent, beat.target_agent, colorHex, `${{c.parameter}} (${{beat.severity.toUpperCase()}})`, true);

                document.getElementById('status-banner').innerHTML = `
                    <div class="bg-white border-4 border-[#121212] p-6 shadow-[8px_8px_0px_0px_#121212] text-[#121212] text-center animate-bounce max-w-2xl mx-auto">
                        <div class="flex items-center justify-center gap-2 font-black text-xl tracking-wide uppercase" style="color: ${{colorHex}}">
                            <span class="material-symbols-outlined text-[28px]">warning</span>
                            Conflict Flare: ${{c.parameter}} (${{beat.severity.toUpperCase()}} Severity)
                        </div>
                        <div class="flex items-center justify-center gap-6 mt-4 text-sm font-bold">
                            <div class="bg-[#F0F0F0] px-5 py-2.5 border-2 border-[#121212]">${{beat.agent.toUpperCase()}} proposed: ${{c.proposed_value_a}}</div>
                            <div class="text-[#121212] font-extrabold">vs</div>
                            <div class="bg-[#F0F0F0] px-5 py-2.5 border-2 border-[#121212]">${{beat.target_agent.toUpperCase()}} proposed: ${{c.proposed_value_b}}</div>
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
                    <div class="bg-white border-2 border-[#121212] p-6 shadow-[4px_4px_0px_0px_#121212] text-[#121212] animate-fade-in">
                        <div class="flex items-center gap-2 font-black text-[#553c9a] text-sm mb-3 tracking-wide uppercase">
                            <span class="material-symbols-outlined text-[24px]">handshake</span>
                            🤝 Strategic Concession Rationale
                        </div>
                        <div class="text-sm italic leading-relaxed bg-[#F0F0F0] p-4 border-l-4 border-[#553c9a] font-medium text-[#121212]">
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
                            <div class="mt-5 bg-[#fff0f0] border-2 border-[#742a2a] p-5 text-left text-[#121212] text-sm shadow-[4px_4px_0px_0px_#742a2a]">
                                <div class="font-black text-[#742a2a] uppercase mb-2 flex items-center gap-1.5 text-[15px]">
                                    <span class="material-symbols-outlined text-[20px]">gavel</span>
                                    Escalated to Human Review (High Conflicts Persist):
                                </div>
                                <ul class="list-disc pl-6 space-y-2 font-bold">
                                    ${{c.unresolved_conflicts.map(p => {{
                                        const attempts = (c.unresolved_attempts && c.unresolved_attempts[p]) ? c.unresolved_attempts[p] : 1;
                                        if (attempts > 1) {{
                                            return `<li>${{p}} <span class="ml-2 px-2 py-0.5 bg-[#742a2a] text-[#f0f0f0] rounded-none border border-[#121212] text-xs font-extrabold">This parameter has required human review across ${{attempts}} attempts</span></li>`;
                                        }} else {{
                                            return `<li>${{p}}</li>`;
                                        }}
                                    }}).join('')}}
                                </ul>
                            </div>
                        `;
                    }} else {{
                        extraHtml = `
                            <div class="mt-5 bg-[#f0fff8] border-2 border-[#276749] p-5 text-[#121212] text-sm font-bold flex items-center justify-center gap-2 shadow-[4px_4px_0px_0px_#276749]">
                                <span class="material-symbols-outlined text-[22px] text-[#276749]">check_circle</span>
                                All conflicts successfully resolved or auto-settled by engine.
                            </div>
                        `;
                    }}

                    if (c.consecutive_unlocked_warnings && c.consecutive_unlocked_warnings.length > 0) {{
                        extraHtml += `
                            <div class="mt-4 bg-[#fefcbf] border-2 border-[#744210] p-5 text-left text-[#121212] text-sm shadow-[4px_4px_0px_0px_#744210]">
                                <div class="font-black text-[#744210] uppercase mb-2 flex items-center gap-1.5 text-[15px]">
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
                            <div class="bg-white border-4 border-[#121212] p-10 shadow-[8px_8px_0px_0px_#121212] max-w-3xl w-full text-center animate-fade-in">
                                <h2 class="text-3xl font-black tracking-wider text-[#121212] uppercase">${{title}}</h2>
                                <p class="text-[#4A4A4A] text-lg mt-4 font-semibold">${{desc}}</p>
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
                            <div class="bg-white border-4 border-[#121212] p-8 shadow-[8px_8px_0px_0px_#121212] max-w-2xl mx-auto text-center animate-fade-in">
                                <h2 class="text-2xl font-black tracking-wider text-[#121212] uppercase">${{title}}</h2>
                                <p class="text-[#4A4A4A] text-base mt-3 font-semibold">${{desc}}</p>
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
