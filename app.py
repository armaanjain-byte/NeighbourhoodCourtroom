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

import streamlit as st

# ── Engine / model imports ──────────────────────────────────────────────────
from engine.state import create_initial_proposal, MUTABLE_PARAMETERS
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

PARAM_LABELS: dict[str, str] = {
    "green_space_pct": "Green Space (%)",
    "affordable_housing_pct": "Affordable Housing (%)",
    "housing_units": "Housing Units",
    "parking_spaces": "Parking Spaces",
    "community_center_sqft": "Community Center (sqft)",
    "estimated_cost": "Estimated Cost ($)",
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
    """Render the full courtroom transcript grouped by round."""
    entries = session.transcript.entries
    if not entries:
        st.info("No transcript entries recorded.")
        return

    rounds: dict[int, list[TranscriptEntry]] = {}
    for entry in entries:
        rounds.setdefault(entry.round_number, []).append(entry)

    for rnum in sorted(rounds.keys()):
        st.markdown(f'<div class="section-header">⚖️ Debate Round {rnum}</div>',
                    unsafe_allow_html=True)
        for entry in rounds[rnum]:
            css_class = f"tx-{entry.statement_type}"
            badge = _agent_badge(entry.agent)
            tag = _type_tag(entry.statement_type)

            target = ""
            if entry.target_agent:
                target = f' → {_agent_badge(entry.target_agent)}'

            content = entry.content.replace("\n", "<br>")
            html = (
                f'<div class="tx-entry {css_class}">'
                f'{badge}{tag}{target}'
                f'<div style="margin-top:0.4rem; color:#cbd5e0;">{content}</div>'
                f'</div>'
            )
            st.markdown(html, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# UI: render_conflicts
# ─────────────────────────────────────────────────────────────────────────────

def render_conflicts(debate_rounds: list[DebateRound]) -> None:
    all_conflicts = []
    for dr in debate_rounds:
        for c in dr.detected_conflicts:
            all_conflicts.append((dr.round_number, c))

    if not all_conflicts:
        st.success("✅ No conflicts detected across all rounds.")
        return

    for rnum, conflict in all_conflicts:
        sev = conflict.disagreement_severity
        badge = f'<span class="conflict-badge severity-{sev}">{sev}</span>'
        st.markdown(
            f'<div class="card" style="padding:1rem 1.2rem;">'
            f'<strong style="color:#e2e8f0;">{conflict.parameter.replace("_", " ").title()}</strong> '
            f'{badge} &nbsp;·&nbsp; Round {rnum}<br>'
            f'<span style="color:#8892a4; font-size:0.85rem;">'
            f'{_agent_badge(conflict.agent_a)} proposed <strong style="color:#90cdf4;">'
            f'{_fmt_value(conflict.parameter, conflict.proposed_value_a)}</strong> '
            f'vs {_agent_badge(conflict.agent_b)} proposed <strong style="color:#fbd38d;">'
            f'{_fmt_value(conflict.parameter, conflict.proposed_value_b)}</strong>'
            f'</span></div>',
            unsafe_allow_html=True,
        )


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

    with st.form("proposal_form"):
        st.markdown('<div class="section-header">🏙️ City Selection</div>', unsafe_allow_html=True)
        city_slug = st.selectbox(
            "Select City",
            options=list(CITY_OPTIONS.keys()),
            format_func=lambda k: CITY_OPTIONS[k],
            key="form_city",
        )

        st.markdown('<div class="section-header">📐 Site Parameters</div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1:
            housing_units = st.number_input(
                "Housing Units", min_value=10, max_value=2000, value=100, step=10
            )
            green_space_pct = st.number_input(
                "Green Space (%)", min_value=0.0, max_value=100.0, value=20.0, step=1.0
            )
            parking_spaces = st.number_input(
                "Parking Spaces", min_value=0, max_value=1000, value=150, step=10
            )
        with c2:
            affordable_housing_pct = st.number_input(
                "Affordable Housing (%)", min_value=0.0, max_value=100.0, value=15.0, step=1.0
            )
            community_center_sqft = st.number_input(
                "Community Center (sqft)", min_value=0.0, max_value=100_000.0,
                value=5000.0, step=500.0,
            )

        st.markdown('<div class="section-header">💰 Budget</div>', unsafe_allow_html=True)
        total_budget = st.number_input(
            "Total Budget ($)", min_value=100_000, max_value=500_000_000,
            value=25_000_000, step=500_000,
        )

        submitted = st.form_submit_button("🚀 Run Debate", use_container_width=True)

    if submitted:
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

    # Helper to get scores
    def _get_score(sess: CourtroomSession, name: str) -> float:
        if not sess.debate_rounds: return 0.0
        last_round = sess.debate_rounds[-1]
        r2 = last_round.round_2_opinions
        r1 = last_round.round_1_opinions
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
        
        # Build Summary
        finance_changes = []
        community_changes = []
        for entry in new_proposal.change_log:
            if entry["version"] > old_proposal.version and entry["action"] != "locked":
                if entry["actor"] == "finance": finance_changes.append(entry)
                if entry["actor"] == "community": community_changes.append(entry)
                
        def _summarize(actor_changes):
            if not actor_changes: return "making no changes"
            final_chg = {}
            for c in actor_changes: final_chg[c["parameter"]] = c
            parts = []
            for p, c in final_chg.items():
                direction = "increasing" if float(c["new"]) > float(c["old"]) else "decreasing"
                parts.append(f"{direction} {PARAM_LABELS.get(p, p).lower()}")
            return " and ".join(parts)
            
        s_fin = _summarize(finance_changes)
        s_com = _summarize(community_changes)
        locked_str = _fmt_value(locked_param, locked_value)
        param_label = PARAM_LABELS.get(locked_param, locked_param)
        
        st.info(f"**You locked {param_label} at {locked_str}.** Finance responded by {s_fin}. Community responded by {s_com}.")

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

    # ── Tabs: Transcript / Conflicts / Proposal ───────────────────────────
    tab_tx, tab_conf, tab_prop = st.tabs([
        "📜 Debate Transcript",
        "⚡ Conflicts",
        "📋 Final Proposal",
    ])

    with tab_tx:
        render_debate_transcript(session)

    with tab_conf:
        render_conflicts(session.debate_rounds)

    with tab_prop:
        st.markdown(
            '<div class="section-header">Final Proposal Parameters</div>',
            unsafe_allow_html=True,
        )
        with st.container():
            st.markdown('<div class="card">', unsafe_allow_html=True)
            render_proposal_table(session)
            st.markdown('</div>', unsafe_allow_html=True)

    # ── Override panel ────────────────────────────────────────────────────
    st.markdown("### 🔒 Lock a Parameter & Watch Agents Re-Negotiate")
    st.markdown('<div class="override-panel">', unsafe_allow_html=True)
    st.markdown(
        "<small style='color:#8892a4;'>Lock a parameter to a specific value. "
        "Agents will not be able to modify locked parameters in future rounds.</small>",
        unsafe_allow_html=True,
    )

    ov_col1, ov_col2 = st.columns([2, 3])
    
    with ov_col1:
        ov_param = st.selectbox(
            "Parameter to override",
            options=["green_space_pct", "affordable_housing_pct", "parking_spaces", "housing_units"],
            format_func=lambda p: PARAM_LABELS.get(p, p),
            key="ov_param",
        )
        
    current_val = float(getattr(session.current_proposal, ov_param))
    with ov_col2:
        if ov_param == "green_space_pct":
            ov_value = st.slider("New Value", 0.0, 100.0, current_val, 1.0, key="ov_value_gs")
        elif ov_param == "affordable_housing_pct":
            ov_value = st.slider("New Value", 0.0, 100.0, current_val, 1.0, key="ov_value_ah")
        elif ov_param == "parking_spaces":
            ov_value = st.slider("New Value", 0, 1000, int(current_val), 10, key="ov_value_ps")
        elif ov_param == "housing_units":
            ov_value = st.slider("New Value", 10, 2000, int(current_val), 10, key="ov_value_hu")
        else:
            ov_value = current_val
            
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Lock & Re-Negotiate", type="primary", key="apply_override"):
        locked_proposal = apply_human_override(session.current_proposal, ov_param, float(ov_value))
        
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
            new_session.run_round(agents, {}, calc)
            
            st.session_state["locked_param"] = ov_param
            st.session_state["locked_value"] = float(ov_value)
            st.session_state["pre_override_session"] = session
            st.session_state["session"] = new_session
            st.session_state["stage"] = "override_result"
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Reset ─────────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("🔄 Start New Case", key="reset"):
        for key in ["proposal", "session", "error", "pre_override_session", "locked_param", "locked_value"]:
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
