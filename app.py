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

load_dotenv(override=True)

import streamlit as st
import streamlit.components.v1 as components
from ui.components.transcript_view import build_transcript_html
from ui.components.conflict_view import build_conflict_meters_html
from ui.components.override_slider import render_override_slider
from ui.components.causal_chain_view import build_causal_chain_html
from ui.components.courtroom_scene import render_courtroom_scene, render_live_feed

# ── Engine / model imports ──────────────────────────────────────────────────
from engine.state import create_initial_proposal, MUTABLE_PARAMETERS, PARAM_LABELS
from engine.override import apply_human_override
from engine.session import CourtroomSession, create_session
from engine.summary import generate_plain_language_summary
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

# ── Startup Sanity Check Logging ──────────────────────────────────────────────
import logging
import os
from llm.provider_factory import get_provider

logger = logging.getLogger("streamlit_app")
try:
    provider = get_provider()
    p_name = getattr(provider, "provider_name", "gemini")
    p_model = getattr(provider, "default_model", "gemini-2.5-flash")
    print(f"\n[STARTUP SANITY CHECK] LLM_PROVIDER configured: {p_name.upper()} | Active Model: {p_model}\n")
    logger.info(f"[STARTUP SANITY CHECK] LLM_PROVIDER configured: {p_name.upper()} | Active Model: {p_model}")
except Exception as e:
    print(f"\n[STARTUP SANITY CHECK ERROR] Could not initialize provider: {e}\n")
    logger.warning(f"[STARTUP SANITY CHECK ERROR] Could not initialize provider: {e}")

# ── Inline CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;700;900&display=swap');

html, body, [class*="css"] {
    font-family: 'Outfit', sans-serif;
}

/* ── Bauhaus canvas ──────────────────────────────────────────────────────── */
.stApp {
    background-color: #F0F0F0;
    background-image: radial-gradient(#121212 1.5px, transparent 1.5px);
    background-size: 22px 22px;
    min-height: 100vh;
}

/* ── Streamlit Header Chrome ────────────────────────────────────────────── */
header[data-testid="stHeader"] {
    background-color: #121212 !important;
    border-bottom: 4px solid #121212 !important;
}
/* Force header icons (like "Deploy" or menu) to be light */
header[data-testid="stHeader"] * {
    color: #F0F0F0 !important;
}

/* Main container */
.block-container {
    padding-top: 2rem;
    max-width: 1100px;
}

/* ── Hero title ─────────────────────────────────────────────────────────── */
.hero-title {
    font-family: 'Outfit', sans-serif;
    font-size: 3.2rem;
    font-weight: 900;
    color: #121212;
    letter-spacing: -0.02em;
    text-transform: uppercase;
    margin-bottom: 0.25rem;
    line-height: 1;
    /* left color-block accent tab — Finance amber */
    border-left: 8px solid #744210;
    padding-left: 1rem;
}
.hero-sub {
    color: #121212;
    opacity: 0.65;
    font-size: 1rem;
    font-weight: 500;
    margin-bottom: 2rem;
    padding-left: 1.5rem;
}

/* ── Section headers ────────────────────────────────────────────────────── */
.section-header {
    font-family: 'Outfit', sans-serif;
    color: #121212;
    font-size: 0.78rem;
    font-weight: 900;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin: 2rem 0 0.75rem;
    padding-bottom: 0.4rem;
    border-bottom: 4px solid #121212;
}

/* ── Cards ──────────────────────────────────────────────────────────────── */
.card {
    background: #ffffff;
    border: 4px solid #121212;
    border-radius: 0;
    padding: 1.5rem;
    margin-bottom: 1rem;
    box-shadow: 6px 6px 0px 0px #121212;
}

/* ── Score metric cards (Bauhaus color-blocked) ─────────────────────────── */
/* Finance = amber/gold (primary-red role) */
.score-card-finance {
    background: #744210;
    border: 4px solid #121212;
    border-radius: 0;
    padding: 1.4rem 1.2rem;
    text-align: center;
    box-shadow: 8px 8px 0px 0px #121212;
    position: relative;
}
/* Climate = green (primary-blue role) */
.score-card-climate {
    background: #276749;
    border: 4px solid #121212;
    border-radius: 0;
    padding: 1.4rem 1.2rem;
    text-align: center;
    box-shadow: 8px 8px 0px 0px #121212;
    position: relative;
}
/* Community = violet (primary-yellow role) */
.score-card-community {
    background: #553c9a;
    border: 4px solid #121212;
    border-radius: 0;
    padding: 1.4rem 1.2rem;
    text-align: center;
    box-shadow: 8px 8px 0px 0px #121212;
    position: relative;
}
/* Geometric corner decoration (circle) */
.score-card-finance::after,
.score-card-climate::after,
.score-card-community::after {
    content: '';
    position: absolute;
    top: 10px;
    right: 10px;
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background: #121212;
    opacity: 0.4;
}
/* Fallback .score-card for any unclassified cards */
.score-card {
    background: #ffffff;
    border: 4px solid #121212;
    border-radius: 0;
    padding: 1.4rem 1.2rem;
    text-align: center;
    box-shadow: 8px 8px 0px 0px #121212;
}
.score-card .agent-name,
.score-card-finance .agent-name,
.score-card-climate .agent-name,
.score-card-community .agent-name {
    font-family: 'Outfit', sans-serif;
    font-size: 0.7rem;
    font-weight: 900;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-bottom: 0.5rem;
}
.score-card-finance .agent-name { color: #fefcbf; }
.score-card-climate .agent-name { color: #c6f6d5; }
.score-card-community .agent-name { color: #e9d8fd; }
.score-card .agent-name { color: #121212; }

.score-card .score-value,
.score-card-finance .score-value,
.score-card-climate .score-value,
.score-card-community .score-value {
    font-family: 'Outfit', sans-serif;
    font-size: 3.5rem;
    font-weight: 900;
    line-height: 1;
}
.score-card-finance .score-value { color: #fefcbf; }
.score-card-climate .score-value { color: #c6f6d5; }
.score-card-community .score-value { color: #e9d8fd; }

.score-card .score-label,
.score-card-finance .score-label,
.score-card-climate .score-label,
.score-card-community .score-label {
    font-size: 0.7rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 0.3rem;
    opacity: 0.7;
}
.score-card-finance .score-label { color: #fefcbf; }
.score-card-climate .score-label { color: #c6f6d5; }
.score-card-community .score-label { color: #e9d8fd; }
.score-card .score-label { color: #121212; }

/* Score colour helpers (kept for logic compatibility) */
.score-high { color: #276749; }
.score-mid  { color: #744210; }
.score-low  { color: #742a2a; }

/* ── Transcript entry types ─────────────────────────────────────────────── */
.tx-entry {
    padding: 0.75rem 1rem;
    border-radius: 0;
    margin-bottom: 0.5rem;
    font-size: 0.88rem;
    line-height: 1.55;
    border: 2px solid #121212;
}
.tx-position  { background: #e8f0ff; border-left: 5px solid #276749; }
.tx-evidence  { background: #eafaf0; border-left: 5px solid #276749; }
.tx-objection { background: #fff0f0; border-left: 5px solid #742a2a; }
.tx-support   { background: #fefcbf; border-left: 5px solid #744210; }

.tx-agent-badge {
    display: inline-block;
    font-family: 'Outfit', sans-serif;
    font-size: 0.68rem;
    font-weight: 900;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    padding: 0.15rem 0.55rem;
    border-radius: 0;
    border: 1px solid #121212;
    margin-right: 0.5rem;
}
/* Exact existing identity colours — preserved verbatim */
.badge-climate   { background: #276749; color: #c6f6d5; }
.badge-finance   { background: #744210; color: #fefcbf; }
.badge-community { background: #553c9a; color: #e9d8fd; }
.badge-unknown   { background: #2d3748; color: #e2e8f0; }

.tx-type-tag {
    display: inline-block;
    font-family: 'Outfit', sans-serif;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 0.1rem 0.45rem;
    border-radius: 0;
    border: 1px solid currentColor;
    margin-right: 0.4rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
.tag-position  { background: #c6f6d5; color: #276749; }
.tag-evidence  { background: #c6f6d5; color: #276749; }
.tag-objection { background: #fed7d7; color: #742a2a; }
.tag-support   { background: #fefcbf; color: #744210; }

/* ── Conflict / severity badges ─────────────────────────────────────────── */
.conflict-badge {
    display: inline-block;
    font-family: 'Outfit', sans-serif;
    font-size: 0.68rem;
    font-weight: 900;
    padding: 0.2rem 0.7rem;
    border-radius: 0;
    border: 2px solid #121212;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}
/* Exact existing severity colours — preserved verbatim */
.severity-high   { background: #742a2a; color: #feb2b2; }
.severity-medium { background: #744210; color: #fefcbf; }
.severity-low    { background: #276749; color: #c6f6d5; }

/* ── Proposal table ─────────────────────────────────────────────────────── */
.param-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
    border: 3px solid #121212;
}
.param-table th {
    text-align: left;
    padding: 0.55rem 0.75rem;
    font-family: 'Outfit', sans-serif;
    font-size: 0.68rem;
    font-weight: 900;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #fefcbf;
    background: #744210;
    border-bottom: 3px solid #121212;
    border-right: 1px solid rgba(255,255,255,0.2);
}
.param-table td {
    padding: 0.55rem 0.75rem;
    color: #121212;
    background: #ffffff;
    border-bottom: 1px solid #e0e0e0;
    border-right: 1px solid #e0e0e0;
}
.param-table tr:nth-child(even) td { background: #F0F0F0; }
.param-table tr:hover td { background: #fefcbf; }
.param-changed { color: #276749; font-weight: 700; }

/* ── Override panel ─────────────────────────────────────────────────────── */
.override-panel {
    background: #ffffff;
    border: 4px solid #121212;
    border-radius: 0;
    padding: 1.5rem;
    margin-top: 1rem;
    box-shadow: 6px 6px 0px 0px #121212;
}

/* ── Spinner override ────────────────────────────────────────────────────── */
.stSpinner > div { color: #553c9a !important; }

/* ── Streamlit widget label colour ───────────────────────────────────────── */
label { color: #121212 !important; font-family: 'Outfit', sans-serif !important; font-weight: 700 !important; }

/* ── Bauhaus Button ─────────────────────────────────────────────────────── */
div.stButton > button {
    font-family: 'Outfit', sans-serif;
    background: #553c9a;
    color: #e9d8fd;
    border: 3px solid #121212;
    border-radius: 0;
    padding: 0.65rem 2rem;
    font-weight: 900;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    box-shadow: 4px 4px 0px 0px #121212;
    transition: transform 0.1s ease-out, box-shadow 0.1s ease-out;
}
div.stButton > button:hover {
    background: #6b46c1;
    color: #e9d8fd;
    transform: translate(-1px, -1px);
    box-shadow: 6px 6px 0px 0px #121212;
}
div.stButton > button:active {
    transform: translate(3px, 3px);
    box-shadow: none;
}

/* ── Streamlit selectbox / input overrides ──────────────────────────────── */
div[data-baseweb="select"] > div {
    border: 3px solid #121212 !important;
    border-radius: 0 !important;
    background: #ffffff !important;
    box-shadow: 3px 3px 0px 0px #121212 !important;
    font-family: 'Outfit', sans-serif !important;
    font-weight: 700 !important;
}

/* ── Streamlit tab overrides ─────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    border-bottom: 4px solid #121212;
    gap: 0;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'Outfit', sans-serif;
    font-weight: 900;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #121212;
    background: #E0E0E0;
    border: 3px solid #121212;
    border-bottom: none;
    border-radius: 0;
    padding: 0.5rem 1.2rem;
    margin-right: -3px;
}
.stTabs [aria-selected="true"] {
    background: #744210 !important;
    color: #fefcbf !important;
}

/* ── Streamlit info / warning / error banners ────────────────────────────── */
div[data-testid="stAlert"] {
    border-radius: 0 !important;
    border-width: 3px !important;
    border-style: solid !important;
    border-color: #121212 !important;
    box-shadow: 4px 4px 0px 0px #121212 !important;
    font-family: 'Outfit', sans-serif !important;
}

/* ── Caption / st.caption ───────────────────────────────────────────────── */
div[data-testid="stCaptionContainer"] p {
    font-family: 'Outfit', sans-serif;
    color: #121212;
    opacity: 0.65;
}

/* ── Metric delta ────────────────────────────────────────────────────────── */
div[data-testid="metric-container"] {
    background: #ffffff;
    border: 3px solid #121212;
    border-radius: 0;
    padding: 1rem;
    box-shadow: 5px 5px 0px 0px #121212;
}
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
        "onboarding_dismissed": False,
        # Live debate streaming state
        "live_events": [],
        "debate_gen": None,
        "debate_session": None,
        "debate_agents": None,
        "debate_calc": None,
        "debate_round_num": 1,
        "debate_exhausted": False,
        # Live override streaming state
        "override_live_events": [],
        "override_gen": None,
        "override_session": None,
        "override_calc": None,
        "override_agents": None,
        "override_round_num": 1,
        "override_exhausted": False,
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

    # ── First-time onboarding card ─────────────────────────────────────────
    if not st.session_state.get("onboarding_dismissed"):
        with st.container():
            st.markdown("""
<div style="
    background: #ffffff;
    border: 4px solid #121212;
    border-radius: 0;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    box-shadow: 6px 6px 0px 0px #121212;
">
<div style="font-family:Outfit,sans-serif;font-size:1.1rem;font-weight:900;text-transform:uppercase;letter-spacing:0.1em;color:#121212;margin-bottom:0.75rem;">👋 New here? Here's what this is</div>
<div style="font-family:Outfit,sans-serif;color:#121212;font-size:0.88rem;line-height:1.65;font-weight:500;">
This app simulates a <strong>city council–style review</strong> of a real estate development proposal.
<br><br>
🏗️ <strong>You play the role of a city planner</strong> — pick a city, propose initial numbers (green space, housing units, budget, etc.), and submit.
<br><br>
🤖 <strong>Three AI agents then debate your proposal</strong>, each representing a different stakeholder perspective:
<ul style="margin:0.4rem 0 0.4rem 1.2rem;padding:0;">
  <li><span style="color:#744210;font-weight:900;">💰 Finance</span> — focuses on cost feasibility and return on investment</li>
  <li><span style="color:#276749;font-weight:900;">🌿 Climate</span> — focuses on environmental impact and green infrastructure</li>
  <li><span style="color:#553c9a;font-weight:900;">🏘️ Community</span> — focuses on resident quality of life and social equity</li>
</ul>
Agents negotiate across up to three rounds, proposing changes and responding to each other's objections. Where they disagree sharply on a parameter, you get to make the final ruling as the judge.
<br><br>
⚖️ <strong>You see the final negotiated numbers</strong> — and can use the override slider to lock any parameter to a value of your choosing and watch them re-negotiate.
</div>
</div>
""", unsafe_allow_html=True)
            if st.button("Got it — let's go ✓", key="dismiss_onboarding"):
                st.session_state["onboarding_dismissed"] = True
                st.rerun()

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

def _reset_debate_state() -> None:
    """Clear all live debate streaming keys from session_state."""
    for key in ["live_events", "debate_gen", "debate_session", "debate_agents",
                "debate_calc", "debate_round_num", "debate_exhausted"]:
        st.session_state[key] = None if key not in ("live_events",) else []
    st.session_state["debate_round_num"] = 1
    st.session_state["debate_exhausted"] = False


def stage_debating() -> None:
    """Live-streaming debate stage — advances the generator one event per rerun.

    Each Streamlit rerun:
    1. Renders the full live feed so far (only new bubbles animate).
    2. Advances the generator by one event (one LLM call completion).
    3. Reruns to trigger the next step.
    """
    st.markdown('<div class="hero-title">⚖️ Neighbourhood Courtroom</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-sub">Agents are deliberating live — watch as each speaks…</div>',
        unsafe_allow_html=True,
    )

    events: list = st.session_state.get("live_events") or []

    # Brief contextual hint for first-time viewers
    st.caption(
        "🟡 **Amber dot** = that agent is currently thinking (LLM call in progress). "
        "🟢 **Green dot** = that agent has spoken this round. "
        "Each bubble = one agent's stated position. "
        "Red bubbles = objections directed at another agent. "
        "Gold bubbles = a concession (agent moving toward compromise)."
    )

    # Render the live feed with whatever events we have so far
    render_live_feed(events)

    # If already exhausted, transition to result
    if st.session_state.get("debate_exhausted"):
        st.session_state["session"] = st.session_state["debate_session"]
        st.session_state["stage"] = "result"
        st.rerun()
        return

    try:
        # ── Bootstrap: build infrastructure once ────────────────────────────
        if st.session_state.get("debate_session") is None:
            proposal = st.session_state["proposal"]
            data_loader = DataLoader()
            calc = CostCalculator(data_loader)
            agents: list[BaseAgent] = [
                ClimateAgent(data_loader),
                FinanceAgent(calc),
                CommunityAgent(data_loader),
            ]
            session = create_session(proposal)
            st.session_state["debate_session"] = session
            st.session_state["debate_agents"] = agents
            st.session_state["debate_calc"] = calc

        session = st.session_state["debate_session"]
        agents = st.session_state["debate_agents"]
        calc = st.session_state["debate_calc"]

        # ── Spawn generator for this round if needed ─────────────────────────
        # NOTE: Python generators are not picklable, but Streamlit stores
        # session_state in-memory within the same process, so the generator
        # object survives across reruns within the same browser session.
        if st.session_state.get("debate_gen") is None:
            if session.status in ["WAITING_FOR_JUDGE", "COMPLETED"]:
                # Can't run another round; mark done
                st.session_state["debate_exhausted"] = True
                st.rerun()
                return
            st.session_state["debate_gen"] = session.stream_round(agents, {}, calc)

        gen = st.session_state["debate_gen"]

        # ── Advance the generator by one event ───────────────────────────────
        try:
            event = next(gen)
            st.session_state["live_events"] = events + [event]

            if event["event"] == "session_complete":
                # This round is done. Check if we should run another round.
                st.session_state["debate_gen"] = None
                rnd_num = st.session_state.get("debate_round_num", 1)
                if rnd_num == 1 and session.status not in ["WAITING_FOR_JUDGE", "COMPLETED"]:
                    # Spawn round 2
                    st.session_state["debate_round_num"] = 2
                    # Generator for next round will be created on next rerun
                else:
                    st.session_state["debate_exhausted"] = True

            st.rerun()

        except StopIteration:
            st.session_state["debate_gen"] = None
            st.session_state["debate_exhausted"] = True
            st.rerun()

    except Exception as exc:
        _reset_debate_state()
        st.session_state["error"] = str(exc)
        st.session_state["stage"] = "input"
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

    summary = generate_plain_language_summary(session)
    st.markdown(
        f'''
        <div style="background:#ffffff;border:4px solid #121212;border-radius:0;padding:1.5rem;margin-bottom:1.5rem;box-shadow:6px 6px 0px 0px #121212;">
            <div style="font-family:Outfit,sans-serif;font-size:1.1rem;font-weight:900;text-transform:uppercase;letter-spacing:0.1em;color:#121212;margin-bottom:0.8rem;">📝 Session Summary</div>
            <div style="font-family:Outfit,sans-serif;font-size:0.95rem;color:#121212;line-height:1.6;margin-bottom:0.8rem;font-weight:500;">
                <strong>Outcome:</strong> {summary["outcome"]}<br>
                <strong>Key Changes:</strong> {summary["changes"]}
            </div>
            <ul style="margin:0;padding-left:1.2rem;font-size:0.9rem;color:#121212;line-height:1.5;font-weight:500;">
                <li>{summary["finance_score"]}</li>
                <li>{summary["climate_score"]}</li>
                <li>{summary["community_score"]}</li>
            </ul>
        </div>
        ''',
        unsafe_allow_html=True
    )

    # Calculate fallback metrics
    total_statements = 0
    fallback_statements = 0
    for rnd in session.debate_rounds:
        for phase in [rnd.round_1_opinions, rnd.round_2_opinions, getattr(rnd, "round_3_opinions", {})]:
            if not phase: continue
            for agent, op in phase.items():
                total_statements += 1
                if op.is_fallback:
                    fallback_statements += 1
                    
    if fallback_statements > 0:
        st.warning(
            f"**Note:** {fallback_statements} of {total_statements} agent statements in this session used verified deterministic calculations "
            f"instead of live AI reasoning, due to API unavailability. This does not affect the safety or correctness of the final proposal "
            f"— see flagged statements below.",
            icon="⚙️"
        )


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

    # Agent legend — always visible, one line per agent
    st.markdown("""
<div style="display:flex;gap:1.5rem;flex-wrap:wrap;margin-bottom:0.8rem;font-size:0.8rem;">
  <span><span style="background:#744210;color:#fefcbf;padding:2px 8px;border-radius:12px;font-weight:700;">💰 FINANCE</span>&nbsp; Cost feasibility &amp; ROI — penalises over-budget proposals</span>
  <span><span style="background:#276749;color:#c6f6d5;padding:2px 8px;border-radius:12px;font-weight:700;">🌿 CLIMATE</span>&nbsp; Environmental impact &amp; green infrastructure</span>
  <span><span style="background:#553c9a;color:#e9d8fd;padding:2px 8px;border-radius:12px;font-weight:700;">🏘️ COMMUNITY</span>&nbsp; Resident quality of life &amp; social equity</span>
</div>
<div style="font-size:0.76rem;color:#718096;margin-bottom:0.6rem;">Score = 0–100. Each agent rates how well the final proposal serves their domain. Higher is better.</div>
""", unsafe_allow_html=True)

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
                    f'<div class="score-card-{agent_name}">'
                    f'<div class="agent-name">{agent_name} Agent</div>'
                    f'<div class="score-value">{new_score:.0f}</div>'
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
        # Conflict legend
        st.markdown("""
<div style="
    background:#ffffff;border:4px solid #121212;
    border-radius:0;padding:1rem 1.5rem;margin-bottom:1rem;font-size:0.85rem;color:#121212;
    line-height:1.6;font-family:Outfit,sans-serif;box-shadow:6px 6px 0px 0px #121212;font-weight:500;
">
<strong style="color:#742a2a;font-weight:900;">⚡ What is a conflict?</strong> &nbsp;A conflict occurs when two agents propose
<em>significantly different</em> values for the same parameter (e.g. Finance wants 5% green space, Climate wants 40%).
The coloured dots on the bar below show each agent's proposed value; the red bar spans the disagreement range.
<br><br>
<strong style="font-weight:900;text-transform:uppercase;letter-spacing:0.1em;font-size:0.75rem;">Severity:</strong>&nbsp;
<span style="background:#742a2a;color:#feb2b2;padding:1px 6px;border:2px solid #121212;border-radius:0;font-size:0.72rem;font-weight:900;">HIGH</span> → escalated to your ruling &nbsp;|
<span style="background:#744210;color:#fefcbf;padding:1px 6px;border:2px solid #121212;border-radius:0;font-size:0.72rem;font-weight:900;">MODERATE</span> → resolved by weighted average &nbsp;|
<span style="background:#276749;color:#c6f6d5;padding:1px 6px;border:2px solid #121212;border-radius:0;font-size:0.72rem;font-weight:900;">LOW</span> → accepted directly.
<br><br>
<strong>Weighted average</strong> means the engine splits the difference, giving more weight to the agent with higher confidence. The italic line at the bottom of each card shows the resolved value.
</div>
""", unsafe_allow_html=True)
        render_conflicts(session)

    with tab_prop:
        st.markdown(
            '<div class="section-header">Final Proposal Parameters</div>',
            unsafe_allow_html=True,
        )
        # Proposal table legend
        st.caption(
            "**Opening** = the numbers you originally submitted. "
            "**Final** = the numbers after all rounds of negotiation. "
            "**↑ green** = increased by agents, **↓ green** = decreased. "
            "Unchanged rows mean all agents agreed to keep your number as-is."
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
    st.markdown('<div class="section-header">🔨 Your Ruling</div>', unsafe_allow_html=True)
    st.caption(
        "As the judge, you can **lock any parameter** to a specific value — overriding what the agents negotiated. "
        "Once you lock a value, the agents re-debate the remaining parameters with your ruling as a hard constraint. "
        "Locked parameters cannot be changed again by any agent in future rounds."
    )

    ov_param = st.selectbox(
        "Select parameter to lock",
        options=["green_space_pct", "affordable_housing_pct", "parking_spaces", "housing_units"],
        format_func=lambda p: PARAM_LABELS.get(p, p),
        key="ov_param",
    )
    
    ov_value = render_override_slider(session, ov_param, key="ov_slider")
    
    if ov_value is not None:
        # Store override parameters and switch to a dedicated override-debating stage
        st.session_state["locked_param"] = ov_param
        st.session_state["locked_value"] = ov_value
        st.session_state["pre_override_session"] = session
        # Reset override streaming state
        for key in ["override_live_events", "override_gen", "override_session",
                    "override_calc", "override_agents", "override_round_num", "override_exhausted"]:
            st.session_state[key] = [] if key == "override_live_events" else None
        st.session_state["override_round_num"] = 1
        st.session_state["override_exhausted"] = False
        st.session_state["override_locked_proposal"] = apply_human_override(
            session.current_proposal, ov_param, ov_value
        )
        st.session_state["judge_brief"] = None
        st.session_state["stage"] = "override_debating"
        st.rerun()

    # ── Reset ─────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Start New Case", key="reset"):
        for key in ["proposal", "session", "error", "pre_override_session", "locked_param",
                    "locked_value", "judge_brief", "live_events", "debate_gen",
                    "debate_session", "debate_agents", "debate_calc", "debate_exhausted",
                    "override_live_events", "override_gen", "override_session",
                    "override_agents", "override_calc", "override_exhausted",
                    "override_locked_proposal"]:
            st.session_state[key] = None
        st.session_state["live_events"] = []
        st.session_state["override_live_events"] = []
        st.session_state["debate_round_num"] = 1
        st.session_state["override_round_num"] = 1
        st.session_state["debate_exhausted"] = False
        st.session_state["override_exhausted"] = False
        st.session_state["stage"] = "input"
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Stage: OVERRIDE DEBATING (live stream re-negotiation)
# ─────────────────────────────────────────────────────────────────────────────

def stage_override_debating() -> None:
    """Live-streaming re-negotiation stage after a human override ruling.

    Mirrors stage_debating but uses the override-specific session_state keys
    so the main debate feed is preserved for the result tabs.
    """
    st.markdown('<div class="hero-title">⚖️ Neighbourhood Courtroom</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hero-sub">Agents are re-negotiating your ruling — watch live…</div>',
        unsafe_allow_html=True,
    )

    events: list = st.session_state.get("override_live_events") or []

    render_live_feed(events)

    if st.session_state.get("override_exhausted"):
        new_session = st.session_state["override_session"]
        st.session_state["session"] = new_session
        st.session_state["stage"] = "override_result"
        st.rerun()
        return

    try:
        if st.session_state.get("override_session") is None:
            locked_proposal = st.session_state["override_locked_proposal"]
            data_loader = DataLoader()
            calc = CostCalculator(data_loader)
            agents: list[BaseAgent] = [
                ClimateAgent(data_loader),
                FinanceAgent(calc),
                CommunityAgent(data_loader),
            ]
            new_session = create_session(locked_proposal)
            st.session_state["override_session"] = new_session
            st.session_state["override_agents"] = agents
            st.session_state["override_calc"] = calc

        session = st.session_state["override_session"]
        agents = st.session_state["override_agents"]
        calc = st.session_state["override_calc"]

        if st.session_state.get("override_gen") is None:
            if session.status in ["WAITING_FOR_JUDGE", "COMPLETED"]:
                st.session_state["override_exhausted"] = True
                st.rerun()
                return
            st.session_state["override_gen"] = session.stream_round(agents, {}, calc)

        gen = st.session_state["override_gen"]

        try:
            event = next(gen)
            st.session_state["override_live_events"] = events + [event]

            if event["event"] == "session_complete":
                st.session_state["override_gen"] = None
                rnd_num = st.session_state.get("override_round_num", 1)
                if rnd_num == 1 and session.status not in ["WAITING_FOR_JUDGE", "COMPLETED"]:
                    st.session_state["override_round_num"] = 2
                else:
                    st.session_state["override_exhausted"] = True

            st.rerun()

        except StopIteration:
            st.session_state["override_gen"] = None
            st.session_state["override_exhausted"] = True
            st.rerun()

    except Exception as exc:
        st.session_state["error"] = str(exc)
        st.session_state["stage"] = "result"
        with st.expander("Error details"):
            st.code(traceback.format_exc())
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
    elif stage == "override_debating":
        stage_override_debating()
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
