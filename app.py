"""Neighbourhood Courtroom — Streamlit Application Entry Point.

Purpose:
    4-stage state machine UI that lets a planner submit a neighbourhood
    development proposal, watches three AI agents debate it across two
    rounds, and then presents results with optional human overrides.

Stages:
    input          → user fills in proposal parameters
    debating       → engine runs Round 1 + Round 2 debate
    result         → scores, transcript, conflicts, final parameters
    override_result → proposal after a human override is applied

Dependencies (real modules only):
    streamlit, engine.state, engine.session, agents.*,
    tools.data_loader, tools.cost_calculator, models.*
"""

from __future__ import annotations

import os
import traceback
from typing import Any
from dotenv import load_dotenv

load_dotenv()

import streamlit as st
import streamlit.components.v1 as components
from ui.components.transcript_view import build_transcript_html
from ui.components.conflict_view import build_conflict_meters_html
from ui.components.override_slider import render_override_slider
from ui.components.causal_chain_view import build_causal_chain_html
from ui.components.courtroom_scene import render_courtroom_scene

# ── Engine / model imports ──────────────────────────────────────────────────
from engine.state import create_initial_proposal, MUTABLE_PARAMETERS, PARAM_LABELS
from engine.override import apply_human_override
from engine.session import CourtroomSession, create_session
from agents.climate_agent import ClimateAgent
from agents.community_agent import CommunityAgent
from agents.finance_agent import FinanceAgent
from agents.base_agent import BaseAgent
from tools.data_loader import DataLoader
from tools.cost_calculator import CostCalculator
from models.debate_round import DebateRound
from models.agent_opinion import AgentOpinion
from models.courtroom_transcript import TranscriptEntry

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Neighbourhood Courtroom",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Inline CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Background */
.stApp {
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    min-height: 100vh;
}

/* Main container */
.block-container {
    padding-top: 2rem;
    max-width: 1100px;
}

/* Hero title */
.hero-title {
    font-size: 3rem;
    font-weight: 800;
    background: linear-gradient(90deg, #f8cdda, #1d8cf8, #a18cd1);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.25rem;
}
.hero-sub {
    color: #8892a4;
    font-size: 1.05rem;
    margin-bottom: 2rem;
}

/* Section headers */
.section-header {
    color: #e2e8f0;
    font-size: 1.1rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin: 1.5rem 0 0.5rem;
    padding-bottom: 0.3rem;
    border-bottom: 1px solid #2d3748;
}

/* Cards */
.card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 14px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    backdrop-filter: blur(8px);
}

/* Score metric cards */
.score-card {
    background: linear-gradient(135deg, rgba(255,255,255,0.08), rgba(255,255,255,0.03));
    border: 1px solid rgba(255,255,255,0.12);
    border-radius: 16px;
    padding: 1.4rem 1.2rem;
    text-align: center;
    backdrop-filter: blur(10px);
}
.score-card .agent-name {
    font-size: 0.78rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #8892a4;
    margin-bottom: 0.4rem;
}
.score-card .score-value {
    font-size: 3rem;
    font-weight: 800;
    line-height: 1;
}
.score-card .score-label {
    font-size: 0.75rem;
    color: #8892a4;
    margin-top: 0.3rem;
}
.score-high { color: #48bb78; }
.score-mid  { color: #ecc94b; }
.score-low  { color: #fc8181; }

/* Transcript entry types */
.tx-entry {
    padding: 0.75rem 1rem;
    border-radius: 10px;
    margin-bottom: 0.5rem;
    font-size: 0.88rem;
    line-height: 1.55;
}
.tx-position  { background: rgba(49,130,206,0.15); border-left: 3px solid #3182ce; }
.tx-evidence  { background: rgba(72,187,120,0.10); border-left: 3px solid #48bb78; }
.tx-objection { background: rgba(252,129,129,0.13); border-left: 3px solid #fc8181; }
.tx-support   { background: rgba(237,211,81,0.12);  border-left: 3px solid #ecc94b; }

.tx-agent-badge {
    display: inline-block;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    padding: 0.15rem 0.55rem;
    border-radius: 20px;
    margin-right: 0.5rem;
}
.badge-climate   { background: #276749; color: #c6f6d5; }
.badge-finance   { background: #744210; color: #fefcbf; }
.badge-community { background: #553c9a; color: #e9d8fd; }
.badge-unknown   { background: #2d3748; color: #e2e8f0; }

.tx-type-tag {
    display: inline-block;
    font-size: 0.68rem;
    font-weight: 600;
    padding: 0.1rem 0.45rem;
    border-radius: 12px;
    margin-right: 0.4rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.tag-position  { background: rgba(49,130,206,0.25);  color: #90cdf4; }
.tag-evidence  { background: rgba(72,187,120,0.25);  color: #9ae6b4; }
.tag-objection { background: rgba(252,129,129,0.3);  color: #feb2b2; }
.tag-support   { background: rgba(237,211,81,0.25);  color: #faf089; }

/* Conflict badges */
.conflict-badge {
    display: inline-block;
    font-size: 0.72rem;
    font-weight: 700;
    padding: 0.2rem 0.7rem;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.07em;
}
.severity-high   { background: #742a2a; color: #feb2b2; }
.severity-medium { background: #744210; color: #fefcbf; }
.severity-low    { background: #276749; color: #c6f6d5; }

/* Proposal table */
.param-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
}
.param-table th {
    text-align: left;
    padding: 0.5rem 0.75rem;
    font-size: 0.72rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #718096;
    border-bottom: 1px solid #2d3748;
}
.param-table td {
    padding: 0.55rem 0.75rem;
    color: #e2e8f0;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.param-table tr:hover td { background: rgba(255,255,255,0.03); }
.param-changed { color: #68d391; font-weight: 600; }

/* Override panel */
.override-panel {
    background: rgba(49,130,206,0.08);
    border: 1px solid rgba(49,130,206,0.25);
    border-radius: 14px;
    padding: 1.5rem;
    margin-top: 1rem;
}

/* Spinner override */
.stSpinner > div { color: #a18cd1 !important; }

/* Streamlit widget label colour */
label { color: #cbd5e0 !important; }

/* Button style override */
div.stButton > button {
    background: linear-gradient(135deg, #667eea, #764ba2);
    color: white;
    border: none;
    border-radius: 10px;
    padding: 0.6rem 2rem;
    font-weight: 600;
    font-size: 1rem;
    transition: opacity 0.2s;
}
div.stButton > button:hover { opacity: 0.88; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

CITY_OPTIONS: dict[str, str] = {
    "phoenix_az": "Phoenix, AZ",
    "detroit_mi": "Detroit, MI",
    "seattle_wa": "Seattle, WA",
    "austin_tx": "Austin, TX",
}

AGENT_COLORS: dict[str, str] = {
    "climate": "badge-climate",
    "finance": "badge-finance",
    "community": "badge-community",
}

# ─────────────────────────────────────────────────────────────────────────────
# Session state initialisation
# ─────────────────────────────────────────────────────────────────────────────

def _init_state() -> None:
    defaults: dict[str, Any] = {
        "stage": "input",
        "proposal": None,
        "session": None,
        "error": None,
        "city_slug": "phoenix_az",
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _score_class(score: float) -> str:
    if score >= 80:
        return "score-high"
    if score >= 55:
        return "score-mid"
    return "score-low"


def _agent_badge(agent: str) -> str:
    css = AGENT_COLORS.get(agent, "badge-unknown")
    return f'<span class="tx-agent-badge {css}">{agent}</span>'


def _type_tag(stmt_type: str) -> str:
    return f'<span class="tx-type-tag tag-{stmt_type}">{stmt_type}</span>'


def _fmt_value(param: str, value: float) -> str:
    if param == "estimated_cost":
        return f"${value:,.0f}"
    if param in ("green_space_pct", "affordable_housing_pct"):
        return f"{value:.1f}%"
    if param in ("housing_units", "parking_spaces"):
        return f"{int(value):,}"
    if param == "community_center_sqft":
        return f"{value:,.0f} sqft"
    return str(value)


# ─────────────────────────────────────────────────────────────────────────────
# UI: render_debate_transcript
# ─────────────────────────────────────────────────────────────────────────────

def render_debate_transcript(session: CourtroomSession) -> None:
    """Render the full courtroom transcript dynamically."""
    if not session.debate_rounds:
        st.info("No debate rounds recorded yet.")
        return

    html = build_transcript_html(session)
    components.html(html, height=1200, scrolling=True)


# ─────────────────────────────────────────────────────────────────────────────
# UI: render_conflicts
# ─────────────────────────────────────────────────────────────────────────────

def render_conflicts(session: CourtroomSession) -> None:
    html = build_conflict_meters_html(session)
    components.html(html, height=600, scrolling=True)


# ─────────────────────────────────────────────────────────────────────────────
# UI: render_proposal_table
# ─────────────────────────────────────────────────────────────────────────────

def render_proposal_table(session: CourtroomSession) -> None:
    opening = session.debate_rounds[0].opening_state if session.debate_rounds else None
    final = session.current_proposal

    rows = ""
    for param, label in PARAM_LABELS.items():
        final_val = getattr(final, param)
        open_val = getattr(opening, param) if opening else final_val
        changed = abs(float(final_val) - float(open_val)) > 0.01
        cls = "param-changed" if changed else ""
        arrow = " ↑" if changed and float(final_val) > float(open_val) else (" ↓" if changed else "")
        rows += (
            f"<tr>"
            f"<td>{label}</td>"
            f"<td>{_fmt_value(param, open_val)}</td>"
            f'<td class="{cls}">{_fmt_value(param, final_val)}{arrow}</td>'
            f"</tr>"
        )

    html = (
        f'<table class="param-table">'
        f"<thead><tr><th>Parameter</th><th>Opening</th><th>Final</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )
    st.markdown(html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Stage: INPUT
# ─────────────────────────────────────────────────────────────────────────────

def stage_input() -> None:
    st.markdown('<div class="hero-title">⚖️ Neighbourhood Courtroom</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-sub">Submit a development proposal and let AI agents '
        'debate its merits across climate, finance, and community dimensions.</div>',
        unsafe_allow_html=True,
    )

    if st.session_state.get("error"):
        st.error(f"Previous run failed: {st.session_state['error']}")
        st.session_state["error"] = None

    # Declare the custom component
    component_dir = os.path.join(os.path.dirname(__file__), "ui_component_dir")
    proposal_intake_form = components.declare_component("proposal_intake_form", path=component_dir)

    # Render the component
    result = proposal_intake_form(key="intake_form")

    # Handle the submission
    if result:
        try:
            city_slug = str(result.get("city_slug", "")).strip()
            if not city_slug:
                city_slug = "phoenix_az"
                
            green_space_pct = max(0.0, min(100.0, float(result.get("green_space_pct", 0.0))))
            affordable_housing_pct = max(0.0, min(100.0, float(result.get("affordable_housing_pct", 0.0))))
            housing_units = max(0, min(100000, int(result.get("housing_units", 0))))
            parking_spaces = max(0, min(100000, int(result.get("parking_spaces", 0))))
            community_center_sqft = max(0.0, min(1000000.0, float(result.get("community_center_sqft", 0.0))))
            total_budget = max(0.0, min(10_000_000_000.0, float(result.get("total_budget", 0.0))))
            
            proposal = create_initial_proposal(
                city_slug=city_slug,
                green_space_pct=green_space_pct,
                affordable_housing_pct=affordable_housing_pct,
                housing_units=housing_units,
                parking_spaces=parking_spaces,
                community_center_sqft=community_center_sqft,
                estimated_cost=total_budget,
            )
            st.session_state["proposal"] = proposal
            st.session_state["city_slug"] = city_slug
            st.session_state["stage"] = "debating"
            st.rerun()
        except (ValueError, TypeError):
            st.error("Invalid input parameters provided. Please check your form values.")


# ─────────────────────────────────────────────────────────────────────────────
# Stage: DEBATING
# ─────────────────────────────────────────────────────────────────────────────

def stage_debating() -> None:
    st.markdown('<div class="hero-title">⚖️ Neighbourhood Courtroom</div>', unsafe_allow_html=True)

    proposal = st.session_state["proposal"]

    with st.spinner("🤝 Three agents are deliberating — this may take a moment…"):
        try:
            # Build infrastructure
            data_loader = DataLoader()
            calc = CostCalculator(data_loader)
            agents: list[BaseAgent] = [
                ClimateAgent(data_loader),
                FinanceAgent(calc),
                CommunityAgent(data_loader),
            ]

            context: dict[str, Any] = {}

            # Create session and run two debate rounds
            session = create_session(proposal)
            session.run_round(agents, context, calc)
            if session.status not in ["WAITING_FOR_JUDGE", "COMPLETED"]:
                session.run_round(agents, context, calc)

            st.session_state["session"] = session
            st.session_state["stage"] = "result"
            st.rerun()

        except Exception as exc:
            st.session_state["error"] = str(exc)
            st.session_state["stage"] = "input"
            # Show traceback in expander for debugging
            with st.expander("Error details"):
                st.code(traceback.format_exc())
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Stage: RESULT
# ─────────────────────────────────────────────────────────────────────────────

def stage_result(is_override: bool = False) -> None:
    session: CourtroomSession = st.session_state["session"]

    heading = "Override Result ✅" if is_override else "Courtroom Verdict"
    st.markdown(f'<div class="hero-title">⚖️ {heading}</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="hero-sub">Session <code>{session.session_id}</code> · '
        f'{len(session.debate_rounds)} debate rounds · '
        f'{len(session.transcript.entries)} transcript entries</div>',
        unsafe_allow_html=True,
    )

    # Check if deterministic fallback was used in any round
    has_fallback = any(
        any("deterministic fallback" in op.position for op in list(rnd.round_1_opinions.values()) + list(rnd.round_2_opinions.values()) + list(getattr(rnd, "round_3_opinions", {}).values()))
        for rnd in session.debate_rounds
    )
    if has_fallback:
        st.info("ℹ️ AI-generated reasoning was unavailable for this debate round. The simulation completed successfully using the robust deterministic fallback engine.")


    # Helper to get scores
    def _get_score(sess: CourtroomSession, name: str) -> float:
        if not sess.debate_rounds: return 0.0
        last_round = sess.debate_rounds[-1]
        r3 = getattr(last_round, "round_3_opinions", {})
        r2 = last_round.round_2_opinions
        r1 = last_round.round_1_opinions
        if name in r3: return r3[name].score
        if name in r2: return r2[name].score
        if name in r1: return r1[name].score
        out = last_round.agent_outputs.get(name)
        return out.score if out else 0.0


    st.markdown('<div class="section-header">📊 Agent Scores</div>', unsafe_allow_html=True)
    cols = st.columns(3)
    
    for i, agent_name in enumerate(["finance", "climate", "community"]):
        new_score = _get_score(session, agent_name)
        if is_override:
            old_session = st.session_state["pre_override_session"]
            old_score = _get_score(old_session, agent_name)
            delta = new_score - old_score
            with cols[i]:
                st.metric(f"{agent_name.title()} Agent", f"{new_score:.0f} / 100", f"{delta:+.0f}")
        else:
            cls = _score_class(new_score)
            with cols[i]:
                st.markdown(
                    f'<div class="score-card">'
                    f'<div class="agent-name">{agent_name} Agent</div>'
                    f'<div class="score-value {cls}">{new_score:.0f}</div>'
                    f'<div class="score-label">/ 100</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    if is_override:
        old_proposal = st.session_state["pre_override_session"].current_proposal
        new_proposal = session.current_proposal
        locked_param = st.session_state["locked_param"]
        locked_value = st.session_state["locked_value"]
        st.markdown('<div class="section-header">📈 Negotiation Delta</div>', unsafe_allow_html=True)
        
        causal_html = build_causal_chain_html(old_proposal, new_proposal, locked_param, locked_value, session=session)
        components.html(causal_html, height=420, scrolling=True)

        # Build Diff Table
        changes = {}
        for entry in new_proposal.change_log:
            if entry["version"] > old_proposal.version:
                changes[entry["parameter"]] = entry["actor"]
                
        rows = []
        for param in MUTABLE_PARAMETERS:
            old_v = getattr(old_proposal, param)
            new_v = getattr(new_proposal, param)
            if abs(float(old_v) - float(new_v)) < 0.01:
                continue
                
            actor = changes.get(param, "unknown")
            is_up = float(new_v) > float(old_v)
            if param in ["estimated_cost", "parking_spaces"]:
                color = "green" if not is_up else "red"
            else:
                color = "green" if is_up else "red"
                
            color_hex = "#48bb78" if color == "green" else "#fc8181"
            arrow = "↑" if is_up else "↓"
            diff_str = f'<span style="color:{color_hex}; font-weight:bold;">{_fmt_value(param, new_v)} {arrow}</span>'
            
            badge_html = '<span class="tx-agent-badge" style="background:#4A5568;color:white">Human</span>'
            if actor != "human":
                badge_html = _agent_badge(actor)
                
            rows.append(f"<tr>"
                        f"<td>{PARAM_LABELS.get(param, param)}</td>"
                        f"<td>{_fmt_value(param, old_v)}</td>"
                        f"<td>{diff_str}</td>"
                        f"<td>{badge_html}</td>"
                        f"</tr>")
        
        if rows:
            html = (
                f'<table class="param-table" style="margin-bottom:1rem;">'
                f"<thead><tr><th>Parameter</th><th>Before Override</th><th>After Negotiation</th><th>Last Changed By</th></tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table>"
            )
            st.markdown(html, unsafe_allow_html=True)
            
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Tabs: Scene / Transcript / Conflicts / Proposal ───────────────────
    tab_scene, tab_tx, tab_conf, tab_prop = st.tabs([
        "🎭 Courtroom Scene",
        "📜 Debate Transcript",
        "⚡ Conflicts",
        "📋 Final Proposal",
    ])

    with tab_scene:
        render_courtroom_scene(session)

    with tab_tx:
        render_debate_transcript(session)

    with tab_conf:
        render_conflicts(session)

    with tab_prop:
        st.markdown(
            '<div class="section-header">Final Proposal Parameters</div>',
            unsafe_allow_html=True,
        )
        st.markdown('<div class="card">', unsafe_allow_html=True)
        render_proposal_table(session)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown(
            '<div class="section-header">🤖 AI Judge Brief</div>',
            unsafe_allow_html=True,
        )
        if st.session_state.get("judge_brief"):
            st.markdown(f'<div class="card">\n\n{st.session_state.judge_brief}\n\n</div>', unsafe_allow_html=True)
        else:
            if st.button("Generate Judge Brief (Gemini)"):
                from services.gemini_explainer import generate_judge_brief
                with st.spinner("Analyzing debate history..."):
                    brief = generate_judge_brief(session)
                    st.session_state.judge_brief = brief
                st.rerun()

    # ── Override panel ────────────────────────────────────────────────────
    st.markdown('<div class="flex items-center justify-between border-b border-gray-300 pb-2 mb-4"><h2 class="font-bold text-2xl text-gray-900">Your Ruling 🔨</h2></div>', unsafe_allow_html=True)
    
    ov_param = st.selectbox(
        "Select parameter to lock",
        options=["green_space_pct", "affordable_housing_pct", "parking_spaces", "housing_units"],
        format_func=lambda p: PARAM_LABELS.get(p, p),
        key="ov_param",
    )
    
    ov_value = render_override_slider(session, ov_param, key="ov_slider")
    
    if ov_value is not None:
        locked_proposal = apply_human_override(session.current_proposal, ov_param, ov_value)
        
        with st.spinner("🤖 Agents are re-negotiating based on your lock..."):
            data_loader = DataLoader()
            calc = CostCalculator(data_loader)
            agents: list[BaseAgent] = [
                ClimateAgent(data_loader),
                FinanceAgent(calc),
                CommunityAgent(data_loader),
            ]
            new_session = create_session(locked_proposal)
            new_session.run_round(agents, {}, calc)
            if new_session.status not in ["WAITING_FOR_JUDGE", "COMPLETED"]:
                new_session.run_round(agents, {}, calc)
            
            st.session_state["locked_param"] = ov_param
            st.session_state["locked_value"] = ov_value
            st.session_state["pre_override_session"] = session
            st.session_state["session"] = new_session
            st.session_state["stage"] = "override_result"
            st.session_state["judge_brief"] = None
            st.rerun()

    # ── Reset ─────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Start New Case", key="reset"):
        for key in ["proposal", "session", "error", "pre_override_session", "locked_param", "locked_value", "judge_brief"]:
            if key in st.session_state:
                st.session_state[key] = None
        st.session_state["stage"] = "input"
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Main router
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    stage = st.session_state.get("stage", "input")

    if stage == "input":
        stage_input()
    elif stage == "debating":
        stage_debating()
    elif stage == "result":
        stage_result(is_override=False)
    elif stage == "override_result":
        stage_result(is_override=True)
    else:
        st.error(f"Unknown stage: {stage}")
        st.session_state["stage"] = "input"
        st.rerun()


if __name__ == "__main__":
    main()
